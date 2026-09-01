from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tests.r9_conformance.project_runtime import reduce_runtime
from tests.r9_conformance.roadmap_guard import (
    ALLOW_EXACT_ACTION,
    GUARD_TRIGGERS,
    INTAKE_GUARD_TRIGGERS,
    READ_ONLY_ONLY,
    RoadmapGuardError,
    evaluate_guard,
    evaluate_intake_guard,
)
from tests.r9_conformance.runtime_contracts import canonical_digest
from tests.r9_runtime_simulator import (
    RuntimeSimulatorError,
    load_corpus,
    run_corpus,
)
from tests.test_project_runtime import runtime_event
from tests.test_runtime_contracts import ZERO, samples

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "r9" / "assignment-29-scenarios-v1.json"


def active_state():
    records = samples()
    project = records["opencntx-project-definition"]
    architect = records["opencntx-actor-binding"] | {
        "record_id": "ACTOR_BINDING_ARCHITECT_R1",
        "actor_id": "ACTOR_ARCHITECT",
        "role": "ARCHITECT",
    }
    bound = runtime_event(
        1,
        "OWNER_PROJECT_BOUND",
        {"project_definition_digest": canonical_digest(project)},
        ZERO,
        actor_id="ACTOR_OWNER",
        actor_role="OWNER",
        to_status="BOUND",
    )
    activated = runtime_event(
        2,
        "ASSIGNMENT_ACTIVATED",
        {
            "assignment_id": "ASSIGNMENT_30",
            "roadmap_stack": [{"roadmap_id": "ROADMAP_MAIN"}],
        },
        canonical_digest(bound),
    )
    state = reduce_runtime(project=project, actors=[architect], events=[bound, activated])
    envelope = records["opencntx-action-envelope"]
    envelope["roadmap_stack_digest"] = canonical_digest(list(state.roadmap_stack))
    envelope["allowed_actions"] = ["read-file", "write-file"]
    return state, envelope


class RoadmapGuardTests(unittest.TestCase):
    def test_intake_guard_allows_only_allowlisted_read_only_targets(self) -> None:
        decision = evaluate_intake_guard(
            trigger="BEFORE_ACTION",
            action="read-metadata",
            target_path="docs/runtime.md",
            allowed_paths=["docs/**", "pyproject.toml"],
            protected_paths=["docs/private/**"],
        )
        self.assertEqual(decision.status, READ_ONLY_ONLY)
        self.assertIn("INTAKE_ZERO_MUTATION", decision.checks)
        self.assertRegex(decision.policy_digest, r"^[0-9a-f]{64}$")
        self.assertRegex(decision.decision_digest, r"^[0-9a-f]{64}$")

    def test_intake_guard_blocks_scope_mutation_budget_and_drift(self) -> None:
        base = {
            "trigger": "BEFORE_ACTION",
            "action": "read-control",
            "target_path": "README.md",
            "allowed_paths": ["README.md"],
        }
        cases = (
            ({"target_path": "outside.md"}, "BLOCKED_INTAKE_READ_SCOPE"),
            (
                {"target_path": "Open_Spec/plan.md", "allowed_paths": ["Open_Spec/**"]},
                "BLOCKED_INTAKE_READ_SCOPE",
            ),
            ({"action": "write-file"}, "BLOCKED_INTAKE_MUTATION"),
            ({"inspection_actions": 41}, "BLOCKED_INTAKE_BUDGET_EXCEEDED"),
            ({"inventory_records": 1_001}, "BLOCKED_INTAKE_BUDGET_EXCEEDED"),
            ({"metadata_bytes": 4 * 1024**2 + 1}, "BLOCKED_INTAKE_BUDGET_EXCEEDED"),
            ({"elapsed_minutes": 31}, "BLOCKED_INTAKE_BUDGET_EXCEEDED"),
            ({"trigger": "DRIFT_DETECTED"}, "BLOCKED_SNAPSHOT_DRIFT"),
        )
        for override, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(evaluate_intake_guard(**(base | override)).status, expected)

    def test_intake_guard_rejects_malformed_requests(self) -> None:
        base = {
            "trigger": "BEFORE_ACTION",
            "action": "read-control",
            "target_path": "README.md",
            "allowed_paths": ["README.md"],
        }
        cases = (
            {"trigger": "BEFORE_STORAGE_WRITE"},
            {"target_path": "../outside"},
            {"target_path": "C:/outside"},
            {"target_path": "docs\\outside"},
            {"allowed_paths": []},
            {"inspection_actions": -1},
        )
        for override in cases:
            with self.subTest(override=override), self.assertRaises(RoadmapGuardError):
                evaluate_intake_guard(**(base | override))
        self.assertEqual(
            INTAKE_GUARD_TRIGGERS,
            {
                "SESSION_OPEN",
                "MESSAGE_RECEIVED",
                "BEFORE_CONTEXT_BUILD",
                "BEFORE_ACTION",
                "AFTER_ACTION",
                "DRIFT_DETECTED",
            },
        )

    def test_exact_action_and_read_only_decisions_are_digest_bound(self) -> None:
        state, envelope = active_state()
        write = evaluate_guard(
            state=state,
            envelope=envelope,
            trigger="BEFORE_ACTION",
            action="write-file",
            actor_id="ACTOR_ARCHITECT",
            target_path="src/opencntx/runtime_contracts.py",
        )
        read = evaluate_guard(
            state=state,
            envelope=envelope,
            trigger="MESSAGE_RECEIVED",
            action="read-file",
            actor_id="ACTOR_ARCHITECT",
        )
        self.assertEqual(write.status, ALLOW_EXACT_ACTION)
        self.assertEqual(read.status, READ_ONLY_ONLY)
        self.assertTrue(write.checks)
        self.assertRegex(write.decision_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(write.state_digest, state.state_digest)

    def test_unknown_trigger_and_malformed_path_are_request_errors(self) -> None:
        state, envelope = active_state()
        with self.assertRaises(RoadmapGuardError) as trigger:
            evaluate_guard(
                state=state,
                envelope=envelope,
                trigger="UNKNOWN_TRIGGER",
                action="write-file",
                actor_id="ACTOR_ARCHITECT",
            )
        self.assertEqual(trigger.exception.code, "roadmap_guard_trigger_unknown")
        with self.assertRaises(RoadmapGuardError) as path:
            evaluate_guard(
                state=state,
                envelope=envelope,
                trigger="BEFORE_ACTION",
                action="write-file",
                actor_id="ACTOR_ARCHITECT",
                target_path="../outside",
            )
        self.assertEqual(path.exception.code, "roadmap_guard_path_invalid")

    def test_wrong_actor_action_path_and_unverified_claim_block(self) -> None:
        state, envelope = active_state()
        cases = (
            ({"actor_id": "ACTOR_UNKNOWN"}, "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"),
            ({"action": "delete-file"}, "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT"),
            ({"target_path": "src/opencntx/core.py"}, "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT"),
            ({"unverified_ai_claim": True}, "BLOCKED_UNVERIFIED_AI_CLAIM"),
        )
        base = {
            "state": state,
            "envelope": envelope,
            "trigger": "BEFORE_ACTION",
            "action": "write-file",
            "actor_id": "ACTOR_ARCHITECT",
            "target_path": "src/opencntx/runtime_contracts.py",
        }
        for override, expected in cases:
            with self.subTest(expected=expected):
                arguments = base | override
                self.assertEqual(evaluate_guard(**arguments).status, expected)

    def test_context_budget_and_detail_leak_fail_closed(self) -> None:
        state, envelope = active_state()
        projection = samples()["opencntx-context-projection"]
        projection["roadmap_stack_digest"] = envelope["roadmap_stack_digest"]
        projection["total_files"] = projection["max_files"]
        projection["total_bytes"] = projection["max_bytes"]
        valid = evaluate_guard(
            state=state,
            envelope=envelope,
            trigger="BEFORE_CONTEXT_BUILD",
            action="read-file",
            actor_id="ACTOR_ARCHITECT",
            context_projection=projection,
        )
        self.assertEqual(valid.status, READ_ONLY_ONLY)
        leak = copy.deepcopy(projection)
        leak["included"] = ["SIBLING_DETAIL"]
        blocked = evaluate_guard(
            state=state,
            envelope=envelope,
            trigger="BEFORE_CONTEXT_BUILD",
            action="read-file",
            actor_id="ACTOR_ARCHITECT",
            context_projection=leak,
        )
        self.assertEqual(blocked.status, "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH")

    def test_sync_disabled_drift_return_and_budget_exhaustion_block(self) -> None:
        state, envelope = active_state()
        policy = samples()["opencntx-storage-policy"]
        sync = evaluate_guard(
            state=state,
            envelope=envelope,
            trigger="BEFORE_SYNC",
            action="write-file",
            actor_id="ACTOR_ARCHITECT",
            storage_policy=policy,
        )
        drift = evaluate_guard(
            state=state,
            envelope=envelope,
            trigger="DRIFT_DETECTED",
            action="write-file",
            actor_id="ACTOR_ARCHITECT",
        )
        returned = evaluate_guard(
            state=state,
            envelope=envelope,
            trigger="RETURN_TO_PARENT",
            action="write-file",
            actor_id="ACTOR_ARCHITECT",
        )
        budget = evaluate_guard(
            state=state,
            envelope=envelope,
            trigger="BEFORE_ACTION",
            action="write-file",
            actor_id="ACTOR_ARCHITECT",
            action_count=envelope["budgets"]["max_actions"],
        )
        self.assertEqual(sync.status, "BLOCKED_STORAGE_OR_SYNC_CONFLICT")
        self.assertEqual(drift.status, "BLOCKED_ROADMAP_DRIFT")
        self.assertEqual(returned.status, "BLOCKED_INVALID_RETURN_TO_PARENT")
        self.assertEqual(budget.status, "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT")

    def test_every_declared_trigger_has_one_visible_decision(self) -> None:
        state, envelope = active_state()
        statuses = {}
        for trigger in sorted(GUARD_TRIGGERS):
            statuses[trigger] = evaluate_guard(
                state=state,
                envelope=envelope,
                trigger=trigger,
                action="write-file",
                actor_id="ACTOR_ARCHITECT",
            ).status
        self.assertEqual(set(statuses), GUARD_TRIGGERS)
        self.assertEqual(statuses["DRIFT_DETECTED"], "BLOCKED_ROADMAP_DRIFT")
        self.assertEqual(statuses["RETURN_TO_PARENT"], "BLOCKED_INVALID_RETURN_TO_PARENT")
        self.assertTrue(all(status for status in statuses.values()))

    def test_frozen_corpus_is_exact_and_all_72_scenarios_pass(self) -> None:
        corpus = load_corpus(CORPUS)
        result = run_corpus(corpus)
        self.assertEqual(result.scenario_count, 72)
        self.assertEqual(result.passed, 72)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.results[0].scenario_id, "S29-001")
        self.assertEqual(result.results[-1].scenario_id, "S29-072")
        self.assertRegex(result.result_digest, r"^[0-9a-f]{64}$")
        self.assertTrue(all(not item.writes for item in result.results))

    def test_frozen_corpus_rejects_changed_missing_extra_or_duplicate_scenario(self) -> None:
        value = json.loads(CORPUS.read_text(encoding="utf-8"))
        mutations = []
        changed = copy.deepcopy(value)
        changed["records"][0]["expected"] = "changed"
        mutations.append(changed)
        missing = copy.deepcopy(value)
        missing["records"].pop()
        mutations.append(missing)
        duplicate = copy.deepcopy(value)
        duplicate["records"][1]["scenario_id"] = "S29-001"
        mutations.append(duplicate)
        for candidate in mutations:
            with (
                self.subTest(length=len(candidate["records"])),
                tempfile.TemporaryDirectory() as temporary_directory,
            ):
                path = Path(temporary_directory) / "corpus.json"
                path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.assertRaises(RuntimeSimulatorError):
                    load_corpus(path)

    def test_openspec_scenarios_are_excluded_without_placeholder_writes(self) -> None:
        corpus = load_corpus(CORPUS)
        result = run_corpus(corpus)
        excluded = result.results[-2:]
        self.assertEqual(
            [item.result_code for item in excluded],
            ["OPENSPEC_EXCLUDED", "OPENSPEC_EXCLUDED"],
        )
        self.assertEqual([item.writes for item in excluded], [(), ()])


if __name__ == "__main__":
    unittest.main()
