from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests.r9_conformance.intake_autopilot import (
    EVIDENCE_STATUSES,
    INSPECTION_LIMITS,
    QUESTION_LIMITS,
    IntakeAutopilotError,
    assess_risk,
    build_preview,
    check_inspection_budget,
    check_question_budget,
    classify_evidence,
    derive_questions,
    evaluate_readiness,
    load_intake_corpus,
    propose_mode,
    propose_scale,
    propose_scope,
    propose_team,
    run_intake_corpus,
    validate_read_target,
    verify_snapshot,
)
from tests.r9_conformance.runtime_contracts import canonical_digest

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "r9" / "assignment-31-intake-scenarios-v1.json"
SNAPSHOT = ROOT / "tests" / "fixtures" / "r9" / "assignment-31-opencntx-public-snapshot-v1.json"
FROZEN_72 = ROOT / "tests" / "fixtures" / "r9" / "assignment-29-scenarios-v1.json"
# Git stores LF; core.autocrlf uses CRLF in Windows worktrees.
FROZEN_72_ALLOWED_SHA256 = frozenset(
    {
        "1d89046fcf8a6ef81724a7a2f3ef7754babe4d684fbff5050b599d0343134088",
        "40ffc9d553b02798c6dc625434687bebc585a5ab4f9f791d41183dd3f53ec21f",
    }
)


def actor(actor_id: str, role: str, *, availability: str = "AVAILABLE") -> dict[str, object]:
    return {
        "actor_id": actor_id,
        "availability": availability,
        "capacity": 1,
        "role": role,
    }


def team_value() -> dict[str, object]:
    return {
        "actors": [actor("ACTOR_OWNER", "OWNER"), actor("ACTOR_02", "EXECUTOR")],
        "ai_slots": 0,
        "human_count": 2,
        "reassignment_to": None,
        "resource_conflict": False,
        "shared_integration": False,
        "disjoint_workstreams": False,
        "requested_parallelism": 1,
    }


class IntakeAutopilotTests(unittest.TestCase):
    def test_frozen_corpus_is_exact_and_all_68_scenarios_pass(self) -> None:
        corpus = load_intake_corpus(CORPUS)
        result = run_intake_corpus(corpus)
        self.assertEqual(
            corpus["scenario_table_sha256"],
            "7b207dad374cddcd67d7fc403d6b7117a63a58cecc75ad26fc962449ceef6f2b",
        )
        self.assertEqual(result.scenario_count, 68)
        self.assertEqual(result.passed, 68)
        self.assertEqual(result.failed, 0)
        self.assertTrue(all(not item.writes for item in result.results))
        self.assertRegex(result.result_digest, r"^[0-9a-f]{64}$")

    def test_existing_72_scenario_corpus_remains_byte_unchanged(self) -> None:
        value = json.loads(FROZEN_72.read_text(encoding="utf-8"))
        self.assertEqual(len(value["records"]), 72)
        raw_sha256 = hashlib.sha256(FROZEN_72.read_bytes()).hexdigest()
        self.assertIn(raw_sha256, FROZEN_72_ALLOWED_SHA256)
        self.assertEqual(
            value["scenario_table_sha256"],
            "dd9f091f30c996324f1472fc40b369228b0cd7cfb5824059284124b38309f4d6",
        )

    def test_corpus_rejects_changed_missing_extra_duplicate_and_non_nfc(self) -> None:
        original = json.loads(CORPUS.read_text(encoding="utf-8"))
        mutations = []
        changed = copy.deepcopy(original)
        changed["records"][0]["input"]["target_path"] = "changed.md"
        mutations.append(changed)
        missing = copy.deepcopy(original)
        missing["records"].pop()
        mutations.append(missing)
        extra = copy.deepcopy(original)
        extra["records"][0]["unexpected"] = True
        mutations.append(extra)
        duplicate = copy.deepcopy(original)
        duplicate["records"][1]["scenario_id"] = "S31-001"
        mutations.append(duplicate)
        non_nfc = copy.deepcopy(original)
        non_nfc["records"][0]["scenario"] = "e\u0301"
        mutations.append(non_nfc)
        for candidate in mutations:
            with (
                self.subTest(records=len(candidate["records"])),
                tempfile.TemporaryDirectory() as tmp,
            ):
                path = Path(tmp) / "corpus.json"
                path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
                with self.assertRaises(IntakeAutopilotError):
                    load_intake_corpus(path)

    def test_read_target_blocks_traversal_absolute_backslash_and_resolved_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            self.assertEqual(validate_read_target(root, "docs/item.md"), "docs/item.md")
            for path in ("../outside", "/absolute", "C:/absolute", "docs\\item.md"):
                with self.subTest(path=path), self.assertRaises(IntakeAutopilotError):
                    validate_read_target(root, path)
            with self.assertRaises(IntakeAutopilotError):
                validate_read_target(root, "linked/item.md", resolved_target=Path(tmp) / "outside")

    def test_all_question_and_inspection_budget_boundaries_are_exact(self) -> None:
        self.assertEqual(QUESTION_LIMITS, {"rounds": 3, "total": 8, "per_round": 5})
        self.assertEqual(
            check_question_budget(rounds=3, total=8, per_round=5), "QUESTION_BUDGET_VALID"
        )
        self.assertEqual(
            check_question_budget(rounds=4, total=8, per_round=5),
            "BLOCKED_INTAKE_BUDGET_EXCEEDED",
        )
        self.assertEqual(INSPECTION_LIMITS["metadata_bytes"], 4_194_304)
        exact = {
            "actions": 40,
            "inventory_records": 1_000,
            "metadata_bytes": 4_194_304,
            "minutes": 30,
        }
        self.assertEqual(check_inspection_budget(**exact), "INSPECTION_BUDGET_VALID")
        for field, value in exact.items():
            with self.subTest(field=field):
                exceeded = exact | {field: value + 1}
                self.assertEqual(
                    check_inspection_budget(**exceeded), "BLOCKED_INTAKE_BUDGET_EXCEEDED"
                )

    def test_evidence_readiness_and_irreducible_questions_are_fail_closed(self) -> None:
        self.assertEqual(len(EVIDENCE_STATUSES), 9)
        self.assertEqual(classify_evidence("OWNER_CONFIRMED"), "EVIDENCE_ACCEPTED")
        self.assertEqual(classify_evidence("HISTORICAL"), "EVIDENCE_ACCEPTED_WITH_LIMITATION")
        self.assertEqual(classify_evidence("CONFLICTING"), "NOT_ENOUGH_INFORMATION")
        required = ["project_root", "owner", "scope"]
        observations = {field: "LIVE_VERIFIED" for field in required}
        self.assertEqual(
            evaluate_readiness(
                required_fields=required, observations=observations, uncertainty="LOW"
            ),
            "ENOUGH_INFORMATION",
        )
        observations["scope"] = "CONFLICTING"
        self.assertEqual(
            evaluate_readiness(
                required_fields=required, observations=observations, uncertainty="LOW"
            ),
            "NOT_ENOUGH_INFORMATION",
        )
        code, questions = derive_questions(
            required_fields=["scope", "goal", "scope"], observations={}, live_facts=[]
        )
        self.assertEqual(code, "QUESTION_REQUIRED")
        self.assertEqual(questions, ("CONFIRM_GOAL", "CONFIRM_SCOPE"))
        code, questions = derive_questions(
            required_fields=[f"field_{index}" for index in range(9)],
            observations={},
            live_facts=[],
        )
        self.assertEqual(code, "BLOCKED_INTAKE_BUDGET_EXCEEDED")
        self.assertEqual(questions, ())

    def test_mode_scope_scale_and_risk_use_closed_contracts(self) -> None:
        self.assertEqual(propose_mode({"new_project": True}), "NEW_PROJECT")
        self.assertEqual(propose_mode({"new_project": True, "migration": True}), "UNRESOLVED")
        self.assertEqual(
            propose_scope(
                requested_scope="SUBPROJECT", parent_project_id=None, no_parent_project=False
            ),
            "BLOCKED_NO_PROJECT_BINDING",
        )
        self.assertEqual(
            propose_scope(
                requested_scope="COMPONENT", parent_project_id=None, no_parent_project=True
            ),
            "PARTIAL_SCOPE_NO_PARENT_CONFIRMED",
        )
        self.assertEqual(
            propose_scale(
                {"assignment_count": 9, "source_count": 1, "dependency_depth": 0, "system_count": 1}
            ),
            "MEDIUM_PROJECT",
        )
        self.assertEqual(
            assess_risk(complexity="LOW", governance="HIGH", uncertainty="LOW"),
            "PROCESS_WEIGHT_PLUS_ONE",
        )
        self.assertEqual(
            assess_risk(complexity="CRITICAL", governance="LOW", uncertainty="LOW"),
            "BLOCKED_CRITICAL_RISK_OWNER_DECISION",
        )

    def test_team_preview_never_invents_owner_role_capacity_or_parallelism(self) -> None:
        value = team_value()
        self.assertEqual(propose_team(value), "TEAM_2")
        self.assertEqual(propose_team(value | {"ai_slots": 64}), "TEAM_COUNT_UNCHANGED")
        self.assertEqual(
            propose_team(value | {"resource_conflict": True}),
            "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
        )
        self.assertEqual(
            propose_team(value | {"shared_integration": True}),
            "SERIALIZED_SHARED_INTEGRATION",
        )
        self.assertEqual(
            propose_team(value | {"disjoint_workstreams": True, "requested_parallelism": 2}),
            "PARALLEL_BOUNDED",
        )
        invalid = copy.deepcopy(value)
        invalid["actors"][1]["role"] = "INVENTED"
        self.assertEqual(propose_team(invalid), "BLOCKED_TEAM_OR_RESOURCE_CONFLICT")

    def test_preview_is_deterministic_unbound_inactive_and_write_free(self) -> None:
        first = build_preview({"scale": "MEDIUM_PROJECT", "goal": "safe", "scope": "FULL"})
        second = build_preview({"scope": "FULL", "goal": "safe", "scale": "MEDIUM_PROJECT"})
        self.assertEqual(first, second)
        self.assertEqual(canonical_digest(first), canonical_digest(second))
        self.assertEqual(first["bindings"], [])
        self.assertEqual(first["activations"], [])
        self.assertEqual(first["owner_events"], [])
        self.assertEqual(first["canonical_writes"], [])

    def test_snapshot_fixture_is_exact_and_drift_is_blocked(self) -> None:
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(verify_snapshot(expected=snapshot, observed=snapshot), "SNAPSHOT_VERIFIED")
        drifted = snapshot | {"tree": "0" * 40}
        self.assertEqual(
            verify_snapshot(expected=snapshot, observed=drifted), "BLOCKED_SNAPSHOT_DRIFT"
        )
        self.assertNotIn("local_path", snapshot)
        self.assertNotIn("content", snapshot)


if __name__ == "__main__":
    unittest.main()
