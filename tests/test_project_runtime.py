from __future__ import annotations

import copy
import unittest

from opencntx.project_runtime import (
    ProjectRuntimeError,
    classify_scale,
    compare_and_swap_pointer,
    query_runtime,
    reduce_runtime,
    validate_roadmap_graph,
)
from opencntx.runtime_contracts import canonical_digest
from tests.test_runtime_contracts import DIGEST, ZERO, samples


def runtime_event(
    number: int,
    event_type: str,
    payload: dict[str, object],
    previous: str,
    *,
    actor_id: str = "ACTOR_ARCHITECT",
    actor_role: str = "ARCHITECT",
    to_status: str = "ACTIVE",
) -> dict[str, object]:
    record = samples()["opencntx-runtime-event"]
    record.update(
        {
            "record_id": f"RUNTIME_EVENT_{number:04d}",
            "event_id": f"EVENT_{number:04d}",
            "event_number": number,
            "event_type": event_type,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "previous_record_digest": previous,
            "to_status": to_status,
            "payload": payload,
        }
    )
    return record


def event_chain(project: dict[str, object]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    previous = ZERO

    def append(
        event_type: str,
        payload: dict[str, object],
        *,
        actor_id: str = "ACTOR_ARCHITECT",
        actor_role: str = "ARCHITECT",
        to_status: str = "ACTIVE",
    ) -> None:
        nonlocal previous
        event = runtime_event(
            len(events) + 1,
            event_type,
            payload,
            previous,
            actor_id=actor_id,
            actor_role=actor_role,
            to_status=to_status,
        )
        events.append(event)
        previous = canonical_digest(event)

    append(
        "OWNER_PROJECT_BOUND",
        {"project_definition_digest": canonical_digest(project)},
        actor_id="ACTOR_OWNER",
        actor_role="OWNER",
        to_status="BOUND",
    )
    append(
        "ASSIGNMENT_ACTIVATED",
        {
            "assignment_id": "ASSIGNMENT_30",
            "roadmap_stack": [
                {"roadmap_id": "ROADMAP_MAIN"},
                {"roadmap_id": "ROADMAP_CHILD"},
            ],
        },
    )
    append(
        "DONE_CANDIDATE_RECORDED",
        {"assignment_id": "ASSIGNMENT_30", "result_digest": DIGEST},
        to_status="DONE_CANDIDATE",
    )
    append(
        "OWNER_RESULT_ACCEPTED",
        {"result_digest": DIGEST, "review_digest": DIGEST},
        actor_id="ACTOR_OWNER",
        actor_role="OWNER",
        to_status="OWNER_ACCEPTED",
    )
    append(
        "ASSIGNMENT_CLOSED",
        {"assignment_id": "ASSIGNMENT_30"},
        to_status="CLOSED",
    )
    append(
        "SUBROADMAP_CLOSED",
        {"roadmap_id": "ROADMAP_CHILD"},
        to_status="CLOSED",
    )
    append(
        "RETURNED_TO_PARENT",
        {"closed_roadmap_id": "ROADMAP_CHILD", "return_node_id": "ASSIGNMENT_31"},
        to_status="READY",
    )
    return events


class ProjectRuntimeTests(unittest.TestCase):
    def test_scale_router_uses_highest_axis_and_unknown_zero_assignment(self) -> None:
        cases = (
            ((1, 5, 0, 1), "TINY_TASK"),
            ((2, 6, 1, 1), "SMALL_PROJECT"),
            ((9, 26, 3, 3), "MEDIUM_PROJECT"),
            ((31, 101, 5, 5), "LARGE_PROJECT"),
            ((121, 501, 9, 9), "MEGA_PROJECT"),
            ((0, 0, 0, 0), "UNRESOLVED"),
        )
        for values, expected in cases:
            with self.subTest(values=values):
                self.assertEqual(
                    classify_scale(
                        assignment_count=values[0],
                        source_count=values[1],
                        dependency_depth=values[2],
                        system_count=values[3],
                    ),
                    expected,
                )

    def test_reducer_is_pure_deterministic_and_returns_one_parent_frame(self) -> None:
        records = samples()
        project = records["opencntx-project-definition"]
        actors = [
            records["opencntx-actor-binding"],
            records["opencntx-actor-binding"]
            | {
                "record_id": "ACTOR_BINDING_ARCHITECT_R1",
                "actor_id": "ACTOR_ARCHITECT",
                "role": "ARCHITECT",
            },
        ]
        events = event_chain(project)
        before = copy.deepcopy((project, actors, events))
        first = reduce_runtime(project=project, actors=actors, events=events)
        second = reduce_runtime(project=project, actors=actors, events=events)
        self.assertEqual(first, second)
        self.assertEqual((project, actors, events), before)
        self.assertEqual(first.status, "READY")
        self.assertEqual(first.mode, "LOCKED_EXECUTION")
        self.assertEqual(first.current_leaf_id, "ASSIGNMENT_31")
        self.assertEqual(len(first.roadmap_stack), 1)
        self.assertEqual(query_runtime(first)["next_transition"], "OWNER_ASSIGNMENT_DECISION")

    def test_event_chain_gap_stale_digest_and_wrong_owner_fail_closed(self) -> None:
        project = samples()["opencntx-project-definition"]
        events = event_chain(project)[:1]
        stale = copy.deepcopy(events)
        stale[0]["previous_record_digest"] = DIGEST
        with self.assertRaises(ProjectRuntimeError) as chain:
            reduce_runtime(project=project, events=stale)
        self.assertEqual(chain.exception.code, "runtime_event_chain_invalid")
        wrong_owner = copy.deepcopy(events)
        wrong_owner[0]["actor_role"] = "ARCHITECT"
        wrong_owner[0]["actor_id"] = "ACTOR_ARCHITECT"
        with self.assertRaises(ProjectRuntimeError) as owner:
            reduce_runtime(project=project, events=wrong_owner)
        self.assertEqual(owner.exception.code, "runtime_owner_event_required")

    def test_event_payload_is_closed_and_activation_requires_binding(self) -> None:
        project = samples()["opencntx-project-definition"]
        event = runtime_event(
            1,
            "ASSIGNMENT_ACTIVATED",
            {
                "assignment_id": "ASSIGNMENT_30",
                "roadmap_stack": [{"roadmap_id": "ROADMAP_MAIN"}],
            },
            ZERO,
        )
        with self.assertRaises(ProjectRuntimeError) as transition:
            reduce_runtime(project=project, events=[event])
        self.assertEqual(transition.exception.code, "runtime_transition_invalid")
        event["payload"]["unexpected"] = True
        with self.assertRaises(ProjectRuntimeError) as payload:
            reduce_runtime(project=project, events=[event])
        self.assertEqual(payload.exception.code, "runtime_event_payload_invalid")

    def test_graph_cycle_orphan_and_multiple_parent_are_blocked(self) -> None:
        roadmap = samples()["opencntx-roadmap-definition"]
        cycle = copy.deepcopy(roadmap)
        cycle["relations"] = [
            {"from": "ASSIGNMENT_30", "to": "PHASE_A", "type": "PARENT_OF"},
            {"from": "PHASE_A", "to": "ASSIGNMENT_30", "type": "PARENT_OF"},
        ]
        with self.assertRaises(ProjectRuntimeError) as cycle_error:
            validate_roadmap_graph(cycle)
        self.assertEqual(cycle_error.exception.code, "runtime_graph_cycle")
        orphan = copy.deepcopy(roadmap)
        orphan["relations"] = [{"from": "MISSING_NODE", "to": "PHASE_A", "type": "PARENT_OF"}]
        with self.assertRaises(Exception) as orphan_error:
            validate_roadmap_graph(orphan)
        self.assertIn(
            getattr(orphan_error.exception, "code", ""),
            {"runtime_contract_graph_invalid", "runtime_graph_orphan"},
        )

    def test_compare_and_swap_pointer_allows_one_exact_successor(self) -> None:
        current = samples()["opencntx-runtime-pointer"]
        candidate = copy.deepcopy(current)
        candidate["revision"] = 2
        candidate["expected_previous_digest"] = canonical_digest(current)
        self.assertEqual(compare_and_swap_pointer(current, candidate), candidate)
        stale = copy.deepcopy(candidate)
        stale["expected_previous_digest"] = DIGEST
        with self.assertRaises(ProjectRuntimeError) as conflict:
            compare_and_swap_pointer(current, stale)
        self.assertEqual(conflict.exception.code, "runtime_pointer_conflict")

    def test_conflicting_intake_facts_block_readiness(self) -> None:
        project = samples()["opencntx-project-definition"]
        first = runtime_event(
            1,
            "OWNER_PROJECT_BOUND",
            {"project_definition_digest": canonical_digest(project)},
            ZERO,
            actor_id="ACTOR_OWNER",
            actor_role="OWNER",
            to_status="BOUND",
        )
        second = runtime_event(
            2,
            "INTAKE_CONFLICT_RECORDED",
            {"conflict_id": "CONFLICT_SCOPE", "evidence_digest": DIGEST},
            canonical_digest(first),
            to_status="BOUND",
        )
        state = reduce_runtime(project=project, events=[first, second])
        self.assertEqual(query_runtime(state)["readiness"], "BLOCKED")
        self.assertEqual(state.conflicts, ("CONFLICT_SCOPE",))


if __name__ == "__main__":
    unittest.main()
