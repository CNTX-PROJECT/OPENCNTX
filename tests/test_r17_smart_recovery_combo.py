from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from opencntx.cli import main
from opencntx.combo import (
    MAX_MARKDOWN_BYTES,
    MAX_MARKDOWN_WORDS,
    build_history_shards,
    compare_roadmap,
    load_combo,
    new_combo,
    query_combo,
    render_combo_markdown,
    set_active_roadmaps,
    update_combo,
    write_combo,
)
from opencntx.continuity import ContinuityError, _value_digest, advance_flow, start_flow
from opencntx.governance import (
    HARD_BLOCK_CHECKS,
    assess_profile,
    assess_profile_with_lease,
    bind_governance_decision,
    classify_check,
    create_verification_lease,
    profile_overhead,
    promote_governance_decision,
    sidecar_decision,
    validate_verification_lease,
)
from opencntx.output_contract import recovery_output_details
from opencntx.recovery import (
    RECOVERY_STAGES,
    build_global_analysis,
    record_failed_attempt,
    recovery_decision,
    recovery_report,
    validate_recovery_history,
)
from opencntx.session_continuity import (
    bind_recovery_handoff,
    load_recovery_handoff,
    persist_recovery_handoff,
)


def _sha(label: str) -> str:
    return _value_digest({"label": label})


def _facts(**changes):
    value = {
        "answer_only": True,
        "writes": 0,
        "reversible": True,
        "target_count": 0,
        "dependent_steps": 0,
        "external_write": False,
        "irreversible": False,
        "protected_resource": False,
        "privacy_clear": True,
        "authority_present": True,
        "integrity_valid": True,
        "goal_ambiguous": False,
        "material_risk": False,
        "failed_attempts": 0,
        "writer_overlap": False,
        "warnings": [],
    }
    value.update(changes)
    return value


def _entry(number: int, *, year: int = 2026, kind: str = "ROADMAP", status: str = "COMPLETED"):
    return {
        "id": f"R{number:03d}_{kind}",
        "roadmap_id": f"R{number:03d}",
        "kind": kind,
        "status": status,
        "statement": f"Outcome {number} for {kind.lower()}",
        "subject_key": f"SUBJECT_{number}",
        "scope_key": "OPENCNTX",
        "tags": ["continuity", f"year-{year}"],
        "sequence": number,
        "year": year,
        "source_digest": _sha(f"source-{number}-{kind}"),
        "supersedes": [],
    }


class GovernanceProfileTests(unittest.TestCase):
    def test_answer_light_and_governed_profiles_are_deterministic(self) -> None:
        answer = assess_profile(_facts())
        light = assess_profile(
            _facts(answer_only=False, writes=1, target_count=1, dependent_steps=1)
        )
        governed = assess_profile(
            _facts(answer_only=False, writes=2, target_count=1, dependent_steps=2)
        )
        self.assertEqual("ANSWER_ONLY", answer["profile"])
        self.assertFalse(answer["writes_allowed"])
        self.assertEqual("LIGHT_TASK", light["profile"])
        self.assertEqual("COMPACT", light["evidence_level"])
        self.assertEqual("GOVERNED_FLOW", governed["profile"])
        self.assertIn("DEPENDENT_STEPS", governed["promotion_reasons"])

    def test_every_hard_guard_blocks_every_candidate_profile(self) -> None:
        mutations = {
            "AUTHORITY_MISSING": {"authority_present": False},
            "TARGET_UNBOUND": {"writes": 1, "target_count": 0},
            "PRIVACY_UNCLEAR": {"privacy_clear": False},
            "PROTECTED_RESOURCE": {"protected_resource": True},
            "INTEGRITY_FAILED": {"integrity_valid": False},
            "EXTERNAL_WRITE_UNAPPROVED": {"external_write": True},
            "IRREVERSIBLE_ACTION": {"irreversible": True},
        }
        self.assertEqual(HARD_BLOCK_CHECKS, frozenset(mutations))
        for expected, change in mutations.items():
            with self.subTest(check=expected):
                result = assess_profile(_facts(**change))
                self.assertEqual("BLOCKED", result["status"])
                self.assertIn(expected, result["hard_blocks"])
                self.assertEqual("HARD_BLOCK", classify_check(expected))

    def test_multiple_concrete_local_targets_promote_without_refusal(self) -> None:
        result = assess_profile(
            _facts(answer_only=False, writes=2, target_count=2, dependent_steps=2)
        )
        self.assertEqual("GOVERNED_FLOW", result["profile"])
        self.assertEqual("READY", result["status"])
        self.assertIn("MULTIPLE_TARGETS", result["promotion_reasons"])

    def test_warn_is_allowlisted_and_cannot_hide_material_drift(self) -> None:
        warning = assess_profile(_facts(warnings=["START_HERE_SOFT_BUDGET"]))
        self.assertEqual("READY", warning["status"])
        blocked = assess_profile(_facts(privacy_clear=False, warnings=["START_HERE_SOFT_BUDGET"]))
        self.assertEqual("BLOCKED", blocked["status"])
        with self.assertRaises(ContinuityError):
            classify_check("UNKNOWN_WARNING")

    def test_verification_lease_invalidates_on_each_bound_change(self) -> None:
        current = {
            "version": "1.5.0",
            "project_root_digest": _sha("root"),
            "context_digest": _sha("context"),
            "instructions_digest": _sha("instructions"),
        }
        lease = create_verification_lease(**current)
        self.assertTrue(validate_verification_lease(lease, **current))
        for field in current:
            changed = dict(current)
            changed[field] = "1.5.1" if field == "version" else _sha(f"changed-{field}")
            with self.subTest(field=field):
                self.assertFalse(validate_verification_lease(lease, **changed))
        promoted = assess_profile_with_lease(_facts(), lease, **changed)
        self.assertEqual("GOVERNED_FLOW", promoted["profile"])
        self.assertIn("VERIFICATION_LEASE_INVALID", promoted["promotion_reasons"])

    def test_promotion_preserves_bindings_and_cannot_downgrade(self) -> None:
        bindings = {
            "goal_digest": _sha("goal"),
            "authority_digest": _sha("authority"),
            "evidence_digest": _sha("evidence"),
        }
        light = assess_profile(
            _facts(answer_only=False, writes=1, target_count=1, dependent_steps=1)
        )
        envelope = bind_governance_decision(light, **bindings)
        promoted = promote_governance_decision(
            envelope,
            _facts(answer_only=False, writes=2, target_count=1, dependent_steps=2),
        )
        self.assertEqual("GOVERNED_FLOW", promoted["decision"]["profile"])
        self.assertEqual(bindings, promoted["bindings"])
        attempted_downgrade = promote_governance_decision(promoted, _facts())
        self.assertEqual("GOVERNED_FLOW", attempted_downgrade["decision"]["profile"])
        self.assertTrue(attempted_downgrade["downgrade_prevented"])
        self.assertEqual(bindings, attempted_downgrade["bindings"])

    def test_sidecar_never_overlaps_or_advances_the_writer(self) -> None:
        self.assertEqual(
            "ISOLATED",
            sidecar_decision(
                active_touches=["src/a.py"], sidecar_touches=["docs/a.md"], advances_roadmap=False
            )["status"],
        )
        for touches, advances in ((["src/a.py"], False), (["docs/a.md"], True)):
            with self.subTest(touches=touches, advances=advances):
                result = sidecar_decision(
                    active_touches=["src/a.py"],
                    sidecar_touches=touches,
                    advances_roadmap=advances,
                )
                self.assertEqual("BLOCKED", result["status"])
                self.assertFalse(result["roadmap_advance_allowed"])

    def test_light_profiles_reduce_artifacts_without_reducing_safety_checks(self) -> None:
        answer = profile_overhead("ANSWER_ONLY")
        light = profile_overhead("LIGHT_TASK")
        governed = profile_overhead("GOVERNED_FLOW")
        self.assertEqual(
            governed["safety_checks"],
            light["safety_checks"],
        )
        self.assertEqual(governed["safety_checks"], answer["safety_checks"])
        self.assertLess(light["durable_artifacts"], governed["durable_artifacts"])
        self.assertLess(light["state_writes"], governed["state_writes"])
        self.assertEqual(0, answer["durable_artifacts"])
        self.assertEqual(0, answer["state_writes"])


class CliIntegrationTests(unittest.TestCase):
    def _run(self, arguments: list[str]) -> dict[str, object]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, main(arguments))
        return json.loads(output.getvalue())

    def test_profile_recovery_and_combo_routes_reach_the_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            facts = root / "facts.json"
            request = root / "recovery.json"
            combo = root / "combo.json"
            facts.write_text(json.dumps(_facts()), encoding="utf-8")
            request.write_text(
                json.dumps(
                    {
                        "history": [],
                        "assignment_id": "TASK_1",
                        "dependency_class": "CHAIN",
                        "failure_layer": "PRODUCT",
                        "reason": "Bound failure",
                        "evidence_digest": _sha("cli-evidence"),
                        "scope_fingerprint": _sha("cli-scope"),
                        "approach_fingerprint": _sha("cli-approach"),
                        "chain_coverage": ["TASK_1"],
                        "global_analysis_digest": None,
                    }
                ),
                encoding="utf-8",
            )
            combo.write_text(json.dumps({"project_id": "OPENCNTX"}), encoding="utf-8")

            self.assertEqual("ANSWER_ONLY", self._run(["flow", "profile", str(facts)])["profile"])
            self.assertEqual(
                "STANDARD_ATTEMPT_1",
                self._run(["flow", "recovery", "record", str(request)])["stage"],
            )
            receipt = self._run(["flow", "combo", "init", str(combo), "--root", str(root)])
            self.assertEqual(0, receipt["history_index_count"])
            self.assertEqual(
                "opencntx-combo-roadmap",
                self._run(["flow", "combo", "status", "--root", str(root)])["format"],
            )


class SmartRecoveryTests(unittest.TestCase):
    def _append(self, history, number, dependency_class="CHAIN", coverage=None):
        coverage = coverage or ["TASK_1"]
        return [
            *history,
            record_failed_attempt(
                history,
                assignment_id="TASK_1",
                dependency_class=dependency_class,
                failure_layer=("PRODUCT", "TEST", "PLATFORM", "CONTROL_PLANE")[number],
                reason=f"Bound failure {number}",
                evidence_digest=_sha(f"evidence-{number}"),
                scope_fingerprint=_sha(f"scope-{number}"),
                approach_fingerprint=_sha(f"approach-{number}"),
                chain_coverage=coverage,
                global_analysis_digest=None if number < 2 else _sha(f"analysis-{number}"),
            ),
        ]

    def test_exact_four_stage_order_survives_json_restart(self) -> None:
        history = []
        for number in range(4):
            coverage = ["TASK_1"] if number < 3 else ["TASK_1", "TASK_0"]
            history = self._append(history, number, coverage=coverage)
        restarted = json.loads(json.dumps(history))
        self.assertEqual(list(RECOVERY_STAGES), [item["stage"] for item in restarted])
        self.assertEqual(history, validate_recovery_history(restarted))
        self.assertEqual("BLOCKED_CHAIN", recovery_decision(restarted)["status"])
        report = recovery_report(
            restarted,
            rollback="Restore the prior candidate tree",
            minimum_continuation="Resolve platform access",
        )
        self.assertEqual(4, len(report["attempt_timeline"]))
        self.assertTrue(report["open_required_outcomes"])

    def test_second_global_round_accepts_new_evidence_and_changed_approach_in_full_scope(
        self,
    ) -> None:
        history = []
        for number in range(3):
            history = self._append(history, number)
        completed = self._append(history, 3, coverage=["TASK_1"])
        self.assertEqual(4, len(completed))
        self.assertEqual("GLOBAL_RECOVERY_2", completed[-1]["stage"])

    def test_second_global_round_rejects_unchanged_evidence_and_scope(self) -> None:
        history = []
        for number in range(3):
            history = self._append(history, number)
        with self.assertRaises(ContinuityError):
            record_failed_attempt(
                history,
                assignment_id="TASK_1",
                dependency_class="CHAIN",
                failure_layer="CONTROL_PLANE",
                reason="No new evidence or scope",
                evidence_digest=history[-1]["evidence_digest"],
                scope_fingerprint=history[-1]["scope_fingerprint"],
                approach_fingerprint=_sha("different-approach"),
                chain_coverage=["TASK_1"],
                global_analysis_digest=_sha("different-analysis"),
            )

    def test_global_approach_cannot_be_repeated(self) -> None:
        history = []
        for number in range(3):
            history = self._append(history, number)
        with self.assertRaises(ContinuityError):
            record_failed_attempt(
                history,
                assignment_id="TASK_1",
                dependency_class="CHAIN",
                failure_layer="CONTROL_PLANE",
                reason="Same smart approach",
                evidence_digest=_sha("new-evidence"),
                scope_fingerprint=_sha("new-scope"),
                approach_fingerprint=history[2]["approach_fingerprint"],
                chain_coverage=["TASK_1", "TASK_0"],
                global_analysis_digest=_sha("new-analysis"),
            )

    def test_standalone_exhaustion_skips_only_to_proven_independent_work(self) -> None:
        history = []
        for number in range(4):
            coverage = ["TASK_1"] if number < 3 else ["TASK_1", "TASK_0"]
            history = self._append(history, number, "STANDALONE", coverage)
        with self.assertRaises(ContinuityError):
            recovery_decision(history)
        result = recovery_decision(history, next_assignment_independent=True)
        self.assertEqual("SKIPPED_STANDALONE", result["status"])
        self.assertFalse(result["roadmap_complete_allowed"])

    def test_global_analysis_keeps_history_and_current_rules_win(self) -> None:
        conflicts = [{"id": "CONFLICT_1", "status": "OPEN", "source_digest": _sha("conflict")}]
        rules = [
            {
                "id": "RULE_CURRENT",
                "status": "CURRENT",
                "approved": True,
                "source_digest": _sha("current"),
            },
            {
                "id": "RULE_OLD",
                "status": "SUPERSEDED",
                "approved": True,
                "source_digest": _sha("old"),
            },
        ]
        first = build_global_analysis(
            round_number=1,
            assignment_id="TASK_1",
            chain_coverage=["TASK_1"],
            failure_layers=["PRODUCT", "CONTROL_PLANE"],
            prior_failure_digests=[_sha("failure-1"), _sha("failure-2")],
            evidence_digest=_sha("evidence-1"),
            conflicts=conflicts,
            rules=rules,
        )
        self.assertEqual(["RULE_CURRENT"], first["effective_rule_ids"])
        self.assertEqual(["RULE_OLD"], first["superseded_rule_ids"])
        second = build_global_analysis(
            round_number=2,
            assignment_id="TASK_1",
            chain_coverage=["TASK_1", "ROOT"],
            failure_layers=["PRODUCT", "CONTROL_PLANE", "PLATFORM"],
            prior_failure_digests=[_sha("failure-1"), _sha("failure-2"), _sha("failure-3")],
            evidence_digest=_sha("evidence-2"),
            conflicts=conflicts,
            rules=rules,
            previous=first,
        )
        self.assertEqual(first["analysis_digest"], second["previous_analysis_digest"])
        self.assertFalse(second["provider_call_required"])
        with self.assertRaises(ContinuityError):
            build_global_analysis(
                round_number=2,
                assignment_id="TASK_1",
                chain_coverage=["TASK_1"],
                failure_layers=["PRODUCT"],
                prior_failure_digests=[_sha("failure-1")],
                evidence_digest=_sha("evidence-1"),
                conflicts=conflicts,
                rules=rules,
                previous=first,
            )

    def test_detailed_handoff_keeps_timeline_rollback_and_open_outcomes(self) -> None:
        history = []
        for number in range(4):
            coverage = ["TASK_1"] if number < 3 else ["TASK_1", "ROOT"]
            history = self._append(history, number, coverage=coverage)
        report = recovery_report(
            history,
            rollback="Restore the previous candidate tree",
            minimum_continuation="Resolve the classified platform blocker",
        )
        handoff = bind_recovery_handoff(
            report,
            state_digest=_sha("state"),
            execution_capsule_digest=_sha("capsule"),
            evidence_digest=_sha("evidence"),
        )
        details = recovery_output_details(handoff)
        self.assertEqual(8, len(details))
        self.assertIn("GLOBAL_RECOVERY_2", details[3])
        self.assertIn("Rollback:", details[-3])
        self.assertIn("Required outcomes remain open", details[-1])
        self.assertFalse(handoff["authority_changed"])


class ComboRoadmapTests(unittest.TestCase):
    def test_update_rejects_partial_roadmap(self) -> None:
        item = _entry(1, status="ACTIVE")
        with self.assertRaises(ContinuityError):
            update_combo(new_combo("OPENCNTX"), [item])

    def test_query_compare_and_explicit_supersession(self) -> None:
        combo = update_combo(new_combo("OPENCNTX"), [_entry(1)])
        query = query_combo(combo, tags=["continuity"])
        self.assertEqual(1, query["match_count"])
        self.assertEqual(
            "CLEAR",
            compare_roadmap(
                combo,
                {
                    "roadmap_id": "R002",
                    "references": ["R001"],
                    "tags": ["continuity"],
                    "touches": ["src"],
                    "supersedes": [],
                },
            )["status"],
        )
        self.assertEqual(
            "RECONCILE_REQUIRED",
            compare_roadmap(
                combo,
                {
                    "roadmap_id": "R002",
                    "references": ["UNKNOWN"],
                    "tags": [],
                    "touches": [],
                    "supersedes": [],
                },
            )["status"],
        )
        conflict = _entry(1, kind="CONFLICT", status="BLOCKED")
        blocked_combo = update_combo(new_combo("OPENCNTX"), [_entry(1), conflict])
        self.assertEqual(
            "BLOCKED",
            compare_roadmap(
                blocked_combo,
                {
                    "roadmap_id": "R002",
                    "references": ["R001"],
                    "tags": ["continuity"],
                    "touches": ["src"],
                    "supersedes": [],
                },
            )["status"],
        )
        replacement = _entry(2)
        replacement["supersedes"] = ["R001_ROADMAP"]
        combo = update_combo(combo, [replacement])
        previous = next(item for item in combo["recent_completed"] if item["id"] == "R001_ROADMAP")
        self.assertEqual("SUPERSEDED", previous["status"])
        self.assertIn(
            {"from": "R002_ROADMAP", "type": "SUPERSEDES", "to": "R001_ROADMAP"},
            combo["relations"],
        )

    def test_active_view_is_bounded_and_never_enters_completed_history(self) -> None:
        active = _entry(1, status="ACTIVE")
        combo = set_active_roadmaps(new_combo("OPENCNTX"), [active])
        self.assertEqual([active], combo["active"])
        self.assertEqual([], combo["recent_completed"])
        self.assertEqual([], combo["source_roadmap_ids"])

    def test_atomic_generation_roundtrip_and_tamper_detection(self) -> None:
        combo = update_combo(new_combo("OPENCNTX"), [_entry(1)])
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            receipt = write_combo(root, combo)
            self.assertEqual(combo, load_combo(root))
            self.assertEqual(combo["combo_digest"], receipt["combo_digest"])
            current = root / ".opencntx" / "combo" / "CURRENT"
            current.write_text("0" * 64 + "\n", encoding="ascii")
            with self.assertRaises(ContinuityError):
                load_combo(root)

    def test_unicode_data_is_preserved_and_credential_signals_are_rejected(self) -> None:
        international = _entry(1)
        international["statement"] = "Café context for 東京"
        combo = update_combo(new_combo("OPENCNTX"), [international])
        self.assertEqual("Café context for 東京", combo["recent_completed"][0]["statement"])

        unsafe = _entry(2)
        unsafe["statement"] = 'api_key = "abcdefghijklmno"'
        with self.assertRaises(ContinuityError):
            update_combo(combo, [unsafe])

    def test_pointer_failure_keeps_the_previous_generation_readable(self) -> None:
        first = update_combo(new_combo("OPENCNTX"), [_entry(1)])
        second = update_combo(first, [_entry(2)])
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            write_combo(root, first)
            real_replace = os.replace

            def fail_pointer(source, destination):
                if Path(destination).name == "CURRENT":
                    raise OSError("simulated pointer failure")
                real_replace(source, destination)

            with (
                mock.patch("opencntx.combo.os.replace", side_effect=fail_pointer),
                self.assertRaises(OSError),
            ):
                write_combo(root, second)
            self.assertEqual(first, load_combo(root))

    def test_ten_year_growth_stays_bounded_and_deterministic(self) -> None:
        combo = new_combo("OPENCNTX")
        for number in range(1, 121):
            combo = update_combo(combo, [_entry(number, year=2020 + (number % 10))])
        rendered = render_combo_markdown(combo)
        self.assertLessEqual(len(rendered.encode("utf-8")), MAX_MARKDOWN_BYTES)
        self.assertLessEqual(len(rendered.split()), MAX_MARKDOWN_WORDS)
        self.assertEqual(3, len(combo["recent_completed"]))
        self.assertLessEqual(len(combo["epochs"]), 12)
        self.assertEqual(120, len(combo["source_roadmap_ids"]))
        self.assertEqual(combo, json.loads(json.dumps(combo, sort_keys=True)))
        archived = query_combo(combo, identifiers=["R001_ROADMAP"])
        self.assertEqual(1, archived["match_count"])
        self.assertEqual("R001_ROADMAP", archived["results"][0]["id"])

    def test_thirty_year_history_shards_at_one_hundred_roadmaps(self) -> None:
        entries = [_entry(number, year=2020 + number % 30) for number in range(1, 361)]
        shards = build_history_shards(entries)
        self.assertEqual([100, 100, 100, 60], [item["entry_count"] for item in shards])
        self.assertEqual(shards, build_history_shards(entries))


class ContinuityGenerationTests(unittest.TestCase):
    @staticmethod
    def _roadmap(identifier: str) -> dict[str, object]:
        return {
            "format": "opencntx-continuity-roadmap",
            "format_version": 1,
            "project_id": "OPENCNTX",
            "roadmap_id": identifier,
            "title": f"Roadmap {identifier}",
            "assignments": [
                {
                    "id": f"{identifier}_TASK",
                    "title": "Complete one task",
                    "detail": "Use the bound evidence and complete this task.",
                    "depends_on": [],
                    "touches": [],
                    "conflict": "NO_CONFLICT",
                    "migration": "No migration.",
                    "definition_of_done": ["Evidence is bound"],
                }
            ],
        }

    def test_new_flow_archives_only_a_verified_complete_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            evidence = root / "evidence.txt"
            evidence.write_text("verified\n", encoding="utf-8")
            first = root / "first.json"
            second = root / "second.json"
            first.write_text(json.dumps(self._roadmap("ROADMAP_ONE")), encoding="utf-8")
            second.write_text(json.dumps(self._roadmap("ROADMAP_TWO")), encoding="utf-8")
            start_flow(root, first, "AUTO PILOT")
            with self.assertRaises(ContinuityError):
                start_flow(root, second, "AUTO PILOT")
            advance_flow(root, outcome="PASS", evidence_paths=["evidence.txt"])
            result = start_flow(root, second, "AUTO PILOT")
            self.assertEqual("ROADMAP_TWO_TASK", result.current_assignment)
            history = root / ".opencntx" / "continuity-history"
            archived = list(history.iterdir())
            self.assertEqual(1, len(archived))
            self.assertTrue((archived[0] / "state.json").is_file())

    def test_classified_standalone_skips_to_independent_work_but_cannot_finish(self) -> None:
        roadmap = self._roadmap("ROADMAP_CLASSIFIED")
        first = roadmap["assignments"][0]
        first["detail"] = "STANDALONE. Complete an independent task."
        roadmap["assignments"].append(
            {
                "id": "ROADMAP_CLASSIFIED_NEXT",
                "title": "Independent next task",
                "detail": "CHAIN. Complete the remaining required task.",
                "depends_on": [],
                "touches": [],
                "conflict": "NO_CONFLICT",
                "migration": "No migration.",
                "definition_of_done": ["Evidence is bound"],
            }
        )
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            path = root / "roadmap.json"
            evidence = root / "evidence.txt"
            path.write_text(json.dumps(roadmap), encoding="utf-8")
            start_flow(root, path, "AUTO PILOT")
            for number in range(4):
                evidence.write_text(f"failure {number}\n", encoding="utf-8")
                result = advance_flow(
                    root,
                    outcome="FAIL",
                    evidence_paths=[evidence.name],
                    reason=f"Approach {number} failed",
                    dependency_class="STANDALONE",
                    failure_layer=("PRODUCT", "TEST", "PLATFORM", "CONTROL_PLANE")[number],
                    scope_fingerprint=_sha(f"scope-{number}"),
                    approach_fingerprint=_sha(f"approach-{number}"),
                    chain_coverage=(
                        ["ROADMAP_CLASSIFIED_TASK"]
                        if number < 3
                        else ["ROADMAP_CLASSIFIED_TASK", "ROADMAP_CLASSIFIED"]
                    ),
                    global_analysis_digest=None if number < 2 else _sha(f"analysis-{number}"),
                )
            self.assertEqual("ROADMAP_CLASSIFIED_NEXT", result.current_assignment)
            state = json.loads(
                (root / ".opencntx" / "continuity" / "state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(2, state["format_version"])
            self.assertEqual(["ROADMAP_CLASSIFIED_TASK"], state["skipped"])
            evidence.write_text("next passed\n", encoding="utf-8")
            blocked = advance_flow(root, outcome="PASS", evidence_paths=[evidence.name])
            self.assertEqual("BLOCKED", blocked.status)

    def test_classified_chain_blocks_only_after_four_failed_stages(self) -> None:
        roadmap = self._roadmap("ROADMAP_CHAIN")
        roadmap["assignments"][0]["detail"] = "CHAIN. Complete the required chain task."
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            path = root / "roadmap.json"
            evidence = root / "evidence.txt"
            path.write_text(json.dumps(roadmap), encoding="utf-8")
            start_flow(root, path, "AUTO PILOT")
            for number in range(4):
                evidence.write_text(f"failure {number}\n", encoding="utf-8")
                result = advance_flow(
                    root,
                    outcome="FAIL",
                    evidence_paths=[evidence.name],
                    reason=f"Approach {number} failed",
                    failure_layer="PRODUCT",
                    scope_fingerprint=_sha(f"scope-{number}"),
                    approach_fingerprint=_sha(f"approach-{number}"),
                    chain_coverage=(
                        ["ROADMAP_CHAIN_TASK"]
                        if number < 3
                        else ["ROADMAP_CHAIN_TASK", "ROADMAP_CHAIN"]
                    ),
                    global_analysis_digest=None if number < 2 else _sha(f"analysis-{number}"),
                )
                self.assertEqual("BLOCKED" if number == 3 else "RECOVERY_REQUIRED", result.status)

    def test_recovery_handoff_persists_byte_equal_across_restart_readback(self) -> None:
        roadmap = self._roadmap("ROADMAP_HANDOFF")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            path = root / "roadmap.json"
            path.write_text(json.dumps(roadmap), encoding="utf-8")
            start_flow(root, path, "AUTO PILOT")
            history = []
            builder = SmartRecoveryTests()
            for number in range(4):
                coverage = ["TASK_1"] if number < 3 else ["TASK_1", "ROOT"]
                history = builder._append(history, number, coverage=coverage)
            report = recovery_report(
                history, rollback="Restore prior state", minimum_continuation="Resolve blocker"
            )
            handoff = bind_recovery_handoff(
                report,
                state_digest=_sha("state"),
                execution_capsule_digest=_sha("capsule"),
                evidence_digest=_sha("evidence"),
            )
            self.assertEqual(handoff, persist_recovery_handoff(root, handoff))
            self.assertEqual(handoff, load_recovery_handoff(root, "TASK_1"))


if __name__ == "__main__":
    unittest.main()
