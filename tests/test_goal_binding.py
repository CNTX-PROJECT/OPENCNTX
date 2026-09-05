from __future__ import annotations

import json
import tempfile
import unittest
from importlib import resources
from pathlib import Path

from opencntx.continuity import (
    ContinuityError,
    _digest,
    _value_digest,
    execution_state_capsule,
    record_execution_checkpoint,
    start_flow,
    validate_current_goal_binding,
)
from opencntx.goal_binding import (
    HostSource,
    build_goal_binding,
    read_legacy_intent,
    validate_goal_binding,
)
from opencntx.human_interface import build_intent_contract, validate_intent_contract


class GoalBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.intent = build_intent_contract(
            human_intent="Update only the three parent files; preserve children.",
            language="en",
            goal="Parent-only result",
            scope=["parent"],
            exclusions=["parent/child"],
            constraints=["Preserve new user bytes"],
            authority_state="APPROVED",
            risks=["Wrong target"],
            definition_of_done=["Exact parent result and child preservation"],
            next_internal_action="Inspect bound targets",
        )
        basis = {
            "format": "opencntx-execution-state-capsule",
            "format_version": 1,
            "roadmap_revision": "a" * 64,
            "current_assignment": "TASK-1",
            "current_internal_task": "READ_BOUND_DETAIL",
            "assignment_status": "ACTIVE",
            "next_internal_action": "Inspect bound targets",
            "next_assignment_after_completion": "TASK-2",
            "authority_state": "APPROVED_AUTO_PILOT",
            "continuation_mode": "CONTINUE_AUTOMATICALLY",
            "recovery_round": 0,
            "checkpoint_number": 0,
            "evidence_digest": "b" * 64,
            "state_digest": "c" * 64,
        }
        self.capsule = basis | {"capsule_digest": _value_digest(basis)}
        self.action = {
            "outcome_id": "PARENT-RESULT",
            "operation": "REPLACE_EXACT",
            "targets": ["parent/00.txt", "parent/90.txt", "parent/99.txt"],
            "recursive": False,
            "protected_targets": ["parent/child/00.txt"],
            "preconditions": [
                {
                    "target": f"parent/{name}.txt",
                    "sha256": "d" * 64,
                    "identity_ref": f"fixture-handle-{name}",
                }
                for name in ("00", "90", "99")
            ],
            "capability_ref": "closed-reference-windows-fixture",
        }
        self.source = HostSource(
            "OWNER", "host-message-1", _digest(self.intent["human_intent"].encode())
        )
        self.args = {
            "intent": self.intent,
            "execution_capsule": self.capsule,
            "request_id": "REQUEST-1",
            "revision": 1,
            "parent_request_id": None,
            "outcome_ids": ["PARENT-RESULT", "CHILD-PRESERVATION"],
            "action": self.action,
            "source": self.source,
            "evidence": [
                {
                    "outcome_id": "PARENT-RESULT",
                    "reference": "evidence/fixture.json",
                    "sha256": "e" * 64,
                }
            ],
        }
        self.bound = build_goal_binding(**self.args)

    def validate(self, value: dict) -> dict:
        return validate_goal_binding(
            value, expected=self.bound, current_execution_capsule=self.capsule
        )

    def test_roundtrip_no_authority_or_execution_claim(self) -> None:
        value = self.bound.payload()
        self.assertEqual(self.validate(json.loads(json.dumps(value))), value)
        self.assertFalse(value["authority_granted"])
        self.assertEqual(value["execution"], "NOT_PERFORMED")
        self.assertEqual(value["request"]["outcome_ids"], self.args["outcome_ids"])

    def test_shipped_schema_matches_shared_contract_fields(self) -> None:
        root = resources.files("opencntx").joinpath("schemas")
        schema = json.loads(
            root.joinpath("goal-binding-v2.schema.json").read_text(encoding="utf-8")
        )
        value = self.bound.payload()
        self.assertEqual(set(schema["required"]), set(value))
        self.assertEqual(set(schema["properties"]), set(value))
        self.assertIs(schema["additionalProperties"], False)
        for key in ("request", "action"):
            self.assertEqual(set(schema["properties"][key]["required"]), set(value[key]))
            self.assertIs(schema["properties"][key]["additionalProperties"], False)
        for key in ("intent_v1", "execution_capsule_v1"):
            embedded = json.loads(
                root.joinpath(schema["properties"][key]["$ref"]).read_text(encoding="utf-8")
            )
            self.assertEqual(set(embedded["required"]), set(value[key]))

    def test_unknown_extra_fields_and_wrong_outer_version_rejected(self) -> None:
        for change in ({"extra": "caller approval"}, {"format_version": 1}, {"format_version": 3}):
            with self.subTest(change=change), self.assertRaises(ContinuityError):
                self.validate(self.bound.payload() | change)

    def test_rehashed_mutations_still_refused(self) -> None:
        for mutate in (
            lambda v: v["action"]["targets"].__setitem__(0, "parent/child/00.txt"),
            lambda v: v["request"].__setitem__("revision", 2),
            lambda v: v["request"].__setitem__("parent_id", "OTHER"),
            lambda v: v["request"]["source"].__setitem__("reference", "invented-source"),
            lambda v: v["evidence"][0].__setitem__("sha256", "f" * 64),
            lambda v: v["request"]["outcome_ids"].pop(),
        ):
            with self.subTest(mutation=mutate):
                value = self.bound.payload()
                mutate(value)
                with self.assertRaises(ContinuityError):
                    self.validate(value)
                value["binding_digest"] = _value_digest(
                    {k: x for k, x in value.items() if k != "binding_digest"}
                )
                with self.assertRaises(ContinuityError):
                    self.validate(value)

    def test_unknown_stays_unknown(self) -> None:
        bound = build_goal_binding(**(self.args | {"source": None}))
        value = bound.payload()
        self.assertEqual(value["request"]["source"]["role"], "UNKNOWN")
        self.assertIsNone(value["request"]["source"]["reference"])
        self.assertFalse(value["authority_granted"])

    def test_ai_proposal_origin_is_preserved(self) -> None:
        source = HostSource(
            "AI_PROPOSAL", "forwarded-message", self.source.content_sha256, "proposal-1"
        )
        bound = build_goal_binding(**(self.args | {"source": source}))
        value = bound.payload()
        self.assertEqual(value["request"]["source"]["role"], "AI_PROPOSAL")
        self.assertEqual(value["request"]["source"]["derived_from"], "proposal-1")

    def test_unrelated_host_source_rejected(self) -> None:
        with self.assertRaises(ContinuityError):
            build_goal_binding(**(self.args | {"source": HostSource("OWNER", "other", "f" * 64)}))

    def test_nested_input_cannot_mutate_retained_expectation(self) -> None:
        before = self.bound.canonical_json
        self.action["targets"][0] = "parent/child/00.txt"
        self.intent["scope"].append("elsewhere")
        self.assertEqual(self.bound.canonical_json, before)
        self.assertEqual(self.validate(self.bound.payload()), self.bound.payload())

    def test_stale_execution_rejected_even_with_its_own_valid_hash(self) -> None:
        current = self.capsule | {"state_digest": "f" * 64}
        current["capsule_digest"] = _value_digest(
            {k: v for k, v in current.items() if k != "capsule_digest"}
        )
        with self.assertRaises(ContinuityError):
            validate_goal_binding(
                self.bound.payload(), expected=self.bound, current_execution_capsule=current
            )

    def test_version_matrix(self) -> None:
        before = json.dumps(self.intent, sort_keys=True).encode()
        self.assertEqual(read_legacy_intent(self.intent), self.intent)
        self.assertEqual(self.bound.payload()["intent_v1"], self.intent)
        self.assertEqual(self.bound.payload()["execution_capsule_v1"], self.capsule)
        self.assertEqual(json.dumps(self.intent, sort_keys=True).encode(), before)
        with self.assertRaises(ContinuityError):
            validate_intent_contract(self.bound.payload())
        for version in (0, 1, 3, True, 2.0, "2", None):
            with self.subTest(version=version), self.assertRaises(ContinuityError):
                build_goal_binding(**(self.args | {"write_version": version}))
        for version in (2, True, "1"):
            with self.subTest(legacy_version=version), self.assertRaises(ContinuityError):
                read_legacy_intent(self.intent | {"format_version": version})

    def test_mismatched_action_relationships_rejected(self) -> None:
        for change in (
            {"outcome_id": "OTHER"},
            {"operation": "SHELL"},
            {"operation": []},
            {"recursive": True},
            {"recursive": 0},
            {"targets": []},
            {"targets": ["../escape"]},
            {"targets": ["D:/other"]},
            {"targets": ["parent//00.txt"]},
            {"targets": ["parent/00.txt"] * 3},
            {"protected_targets": ["parent/00.txt"]},
            {"preconditions": []},
            {"approved_target": "parent/00.txt"},
        ):
            with self.subTest(change=change), self.assertRaises(ContinuityError):
                build_goal_binding(**(self.args | {"action": self.action | change}))

    def test_evidence_and_parent_relationships_rejected(self) -> None:
        for change in (
            {"revision": True},
            {"revision": 0},
            {"parent_request_id": "REQUEST-1"},
            {"outcome_ids": ["PARENT-RESULT", "PARENT-RESULT"]},
            {"evidence": [{"outcome_id": "OTHER", "reference": "evidence/a", "sha256": "a" * 64}]},
            {"evidence": self.args["evidence"] * 2},
        ):
            with self.subTest(change=change), self.assertRaises(ContinuityError):
                build_goal_binding(**(self.args | change))

    def test_projection_reads_actual_state_and_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            definition = {
                "format": "opencntx-continuity-roadmap",
                "format_version": 1,
                "project_id": "FIXTURE",
                "roadmap_id": "R15-FIXTURE",
                "title": "Binding",
                "assignments": [
                    {
                        "id": "TASK-1",
                        "title": "Test binding",
                        "detail": "Fixture only",
                        "depends_on": [],
                        "touches": [],
                        "conflict": "NO_CONFLICT",
                        "migration": "",
                        "definition_of_done": ["Binding proven"],
                    }
                ],
            }
            (root / "roadmap.json").write_text(json.dumps(definition), encoding="utf-8")
            start_flow(root, root / "roadmap.json", "AUTO PILOT")
            capsule = execution_state_capsule(root)
            bound = build_goal_binding(**(self.args | {"execution_capsule": capsule}))

            def snapshot() -> dict:
                return {
                    str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
                }

            before = snapshot()
            self.assertEqual(
                validate_current_goal_binding(root, bound.payload(), expected=bound),
                bound.payload(),
            )
            self.assertEqual(snapshot(), before)
            (root / "proof.txt").write_text("Fixture checkpoint", encoding="utf-8")
            record_execution_checkpoint(
                root,
                checkpoint_id="CHECK-1",
                current_internal_task="TEST",
                next_internal_action="Continue fixture test",
                evidence_paths=["proof.txt"],
                expected_state_digest=capsule["state_digest"],
            )
            before = snapshot()
            with self.assertRaises(ContinuityError):
                validate_current_goal_binding(root, bound.payload(), expected=bound)
            self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
