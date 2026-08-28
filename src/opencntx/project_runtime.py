"""Pure reducer and query engine for the isolated R9 runtime foundation."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .runtime_contracts import (
    AVAILABILITY,
    NODE_STATUSES,
    canonical_digest,
    validate_runtime_record,
)

ZERO_DIGEST = "0" * 64
OWNER_EVENT_TYPES = {
    "OWNER_PROJECT_BOUND",
    "OWNER_PLAN_ACCEPTED",
    "ROADMAP_REVISION_BOUND",
    "ACTOR_BOUND",
    "ACTOR_AVAILABILITY_CHANGED",
    "WORKSTREAM_BOUND",
    "ASSIGNMENT_APPROVED",
    "OWNER_RESULT_ACCEPTED",
    "ASSIGNMENT_RETURNED",
    "ASSIGNMENT_REJECTED",
    "ROADMAP_SUPERSEDED",
}

EVENT_PAYLOAD_FIELDS = {
    "PROJECT_PROPOSED": {"project_definition_digest"},
    "OWNER_PROJECT_BOUND": {"project_definition_digest"},
    "INTAKE_FACT_RECORDED": {"evidence_digest", "fact_id"},
    "INTAKE_CONFLICT_RECORDED": {"conflict_id", "evidence_digest"},
    "OWNER_PLAN_ACCEPTED": {"roadmap_digest", "roadmap_id", "roadmap_revision"},
    "ROADMAP_REVISION_BOUND": {"roadmap_digest", "roadmap_id", "roadmap_revision"},
    "ACTOR_BOUND": {"actor_binding_digest", "actor_id"},
    "ACTOR_AVAILABILITY_CHANGED": {"actor_id", "availability"},
    "WORKSTREAM_BOUND": {"workstream_binding_digest", "workstream_id"},
    "ASSIGNMENT_APPROVED": {"assignment_id", "proposal_digest"},
    "ASSIGNMENT_ACTIVATED": {"assignment_id", "roadmap_stack"},
    "ACTION_ATTEMPT_RECORDED": {"action", "evidence_digest", "outcome"},
    "DONE_CANDIDATE_RECORDED": {"assignment_id", "result_digest"},
    "ARCHITECT_REVIEWED": {"outcome", "result_digest", "review_digest"},
    "OWNER_RESULT_ACCEPTED": {"result_digest", "review_digest"},
    "ASSIGNMENT_CLOSED": {"assignment_id"},
    "SUBROADMAP_CLOSED": {"roadmap_id"},
    "RETURNED_TO_PARENT": {"closed_roadmap_id", "return_node_id"},
    "ASSIGNMENT_RETURNED": {"assignment_id", "reason"},
    "ASSIGNMENT_REJECTED": {"assignment_id", "reason"},
    "ASSIGNMENT_PAUSED": {"assignment_id", "reason"},
    "ASSIGNMENT_BLOCKED": {"assignment_id", "reason"},
    "ROADMAP_SUPERSEDED": {"replacement_roadmap_id", "roadmap_id"},
    "STORAGE_WRITTEN": {"object_id", "record_digest"},
    "SYNC_PREVIEWED": {"preview_digest"},
    "SYNC_APPLIED": {"preview_digest", "receipt_digest"},
    "RECOVERY_RECORDED": {"recovery_digest"},
}


class ProjectRuntimeError(ValueError):
    """A fail-closed reducer or graph error."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.code = reason


@dataclass(frozen=True)
class RuntimeState:
    project_id: str
    status: str
    mode: str
    current_leaf_id: str | None
    roadmap_stack: tuple[dict[str, Any], ...]
    event_head: str
    event_count: int
    actors: tuple[tuple[str, str, str], ...]
    workstreams: tuple[tuple[str, str, str], ...]
    conflicts: tuple[str, ...]
    facts: tuple[str, ...]
    state_digest: str


def classify_scale(
    *, assignment_count: int, source_count: int, dependency_depth: int, system_count: int
) -> str:
    values = (assignment_count, source_count, dependency_depth, system_count)
    if any(type(value) is not int or value < 0 for value in values):
        raise ProjectRuntimeError(
            "Scale inputs must be non-negative integers.", reason="runtime_scale_invalid"
        )
    classes = (
        ("TINY_TASK", (1, 5, 0, 1)),
        ("SMALL_PROJECT", (8, 25, 2, 2)),
        ("MEDIUM_PROJECT", (30, 100, 4, 4)),
        ("LARGE_PROJECT", (120, 500, 8, 8)),
    )
    if assignment_count == 0:
        return "UNRESOLVED"
    for name, limits in classes:
        if all(value <= limit for value, limit in zip(values, limits, strict=True)):
            return name
    return "MEGA_PROJECT"


def validate_roadmap_graph(roadmap: dict[str, Any]) -> None:
    validate_runtime_record(roadmap)
    if roadmap["format"] != "opencntx-roadmap-definition":
        raise ProjectRuntimeError(
            "Graph input is not a roadmap definition.", reason="runtime_graph_invalid"
        )
    node_ids = {node["node_id"] for node in roadmap["nodes"]}
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    parent_counts = {node_id: 0 for node_id in node_ids}
    for relation in roadmap["relations"]:
        source = relation["from"]
        target = relation["to"]
        relation_type = relation["type"]
        if source not in node_ids or target not in node_ids:
            raise ProjectRuntimeError(
                "Roadmap relation has an orphan endpoint.", reason="runtime_graph_orphan"
            )
        if relation_type in {"PARENT_OF", "DEPENDS_ON", "BLOCKS"}:
            adjacency[source].add(target)
        if relation_type == "PARENT_OF":
            parent_counts[target] += 1
    if any(count > 1 for count in parent_counts.values()):
        raise ProjectRuntimeError(
            "Roadmap node has multiple parents.", reason="runtime_graph_multiple_parents"
        )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ProjectRuntimeError("Roadmap graph has a cycle.", reason="runtime_graph_cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in sorted(adjacency[node_id]):
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(node_ids):
        visit(node_id)


def _validate_records(records: Sequence[dict[str, Any]], format_name: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for record in records:
        validate_runtime_record(record)
        if record["format"] != format_name or record["record_id"] in ids:
            raise ProjectRuntimeError(
                "Runtime definition set is inconsistent.", reason="runtime_definition_invalid"
            )
        ids.add(record["record_id"])
        result.append(deepcopy(record))
    return result


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event["payload"]
    expected = EVENT_PAYLOAD_FIELDS[event["event_type"]]
    if set(payload) != expected:
        raise ProjectRuntimeError(
            "Runtime event payload has unknown or missing fields.",
            reason="runtime_event_payload_invalid",
        )
    return payload


def _require_owner(event: dict[str, Any]) -> None:
    if event["event_type"] in OWNER_EVENT_TYPES and event["actor_role"] != "OWNER":
        raise ProjectRuntimeError(
            "Only OWNER may apply this transition.", reason="runtime_owner_event_required"
        )


def _state_value(
    *,
    project_id: str,
    status: str,
    mode: str,
    current_leaf_id: str | None,
    roadmap_stack: list[dict[str, Any]],
    event_head: str,
    event_count: int,
    actors: dict[str, dict[str, Any]],
    workstreams: dict[str, dict[str, Any]],
    conflicts: set[str],
    facts: set[str],
) -> dict[str, Any]:
    return {
        "actors": [
            {
                "actor_id": key,
                "availability": actors[key]["availability"],
                "role": actors[key]["role"],
            }
            for key in sorted(actors)
        ],
        "conflicts": sorted(conflicts),
        "current_leaf_id": current_leaf_id,
        "event_count": event_count,
        "event_head": event_head,
        "facts": sorted(facts),
        "mode": mode,
        "project_id": project_id,
        "roadmap_stack": roadmap_stack,
        "status": status,
        "workstreams": [
            {
                "actor_id": workstreams[key]["actor_id"],
                "current_leaf_id": workstreams[key]["current_leaf_id"],
                "workstream_id": key,
            }
            for key in sorted(workstreams)
        ],
    }


def reduce_runtime(
    *,
    project: dict[str, Any],
    actors: Sequence[dict[str, Any]] = (),
    roadmaps: Sequence[dict[str, Any]] = (),
    workstreams: Sequence[dict[str, Any]] = (),
    resources: Sequence[dict[str, Any]] = (),
    events: Sequence[dict[str, Any]] = (),
) -> RuntimeState:
    validate_runtime_record(project)
    if project["format"] != "opencntx-project-definition":
        raise ProjectRuntimeError(
            "Project definition is required.", reason="runtime_project_invalid"
        )
    actor_records = _validate_records(actors, "opencntx-actor-binding")
    roadmap_records = _validate_records(roadmaps, "opencntx-roadmap-definition")
    workstream_records = _validate_records(workstreams, "opencntx-workstream-binding")
    _validate_records(resources, "opencntx-resource-claim")
    for roadmap in roadmap_records:
        validate_roadmap_graph(roadmap)
    actor_map = {record["actor_id"]: record for record in actor_records}
    workstream_map = {record["workstream_id"]: record for record in workstream_records}
    status = "UNBOUND"
    mode = "INTAKE_PLANNING"
    current_leaf_id: str | None = None
    roadmap_stack: list[dict[str, Any]] = []
    event_head = ZERO_DIGEST
    conflicts: set[str] = set()
    facts: set[str] = set()
    for index, event in enumerate(events, start=1):
        validate_runtime_record(event)
        if (
            event["format"] != "opencntx-runtime-event"
            or event["project_id"] != project["project_id"]
        ):
            raise ProjectRuntimeError(
                "Runtime event belongs to another project.", reason="runtime_event_invalid"
            )
        if event["event_number"] != index or event["previous_record_digest"] != event_head:
            raise ProjectRuntimeError(
                "Runtime event chain is stale or discontinuous.",
                reason="runtime_event_chain_invalid",
            )
        _require_owner(event)
        payload = _payload(event)
        event_type = event["event_type"]
        if event_type == "OWNER_PROJECT_BOUND":
            if payload["project_definition_digest"] != canonical_digest(project):
                raise ProjectRuntimeError(
                    "OWNER project binding digest differs.", reason="runtime_binding_invalid"
                )
            status = "BOUND"
        elif event_type == "INTAKE_FACT_RECORDED":
            facts.add(str(payload["fact_id"]))
        elif event_type == "INTAKE_CONFLICT_RECORDED":
            conflicts.add(str(payload["conflict_id"]))
        elif event_type == "ACTOR_AVAILABILITY_CHANGED":
            actor_id = str(payload["actor_id"])
            availability = payload["availability"]
            if actor_id not in actor_map or availability not in AVAILABILITY:
                raise ProjectRuntimeError(
                    "Actor availability transition is invalid.", reason="runtime_actor_invalid"
                )
            actor_map[actor_id]["availability"] = availability
        elif event_type == "ASSIGNMENT_ACTIVATED":
            if status == "UNBOUND" or conflicts:
                raise ProjectRuntimeError(
                    "Assignment cannot activate in current state.",
                    reason="runtime_transition_invalid",
                )
            stack = payload["roadmap_stack"]
            if not isinstance(stack, list) or not 1 <= len(stack) <= 8:
                raise ProjectRuntimeError(
                    "Activated roadmap stack is invalid.", reason="runtime_stack_invalid"
                )
            roadmap_stack = deepcopy(stack)
            current_leaf_id = str(payload["assignment_id"])
            mode = "LOCKED_EXECUTION"
            status = "ACTIVE"
        elif event_type == "DONE_CANDIDATE_RECORDED":
            status = "DONE_CANDIDATE"
        elif event_type == "OWNER_RESULT_ACCEPTED":
            status = "OWNER_ACCEPTED"
        elif event_type == "ASSIGNMENT_CLOSED":
            if status != "OWNER_ACCEPTED":
                raise ProjectRuntimeError(
                    "Assignment closure requires OWNER acceptance.",
                    reason="runtime_transition_invalid",
                )
            status = "CLOSED"
        elif event_type == "SUBROADMAP_CLOSED":
            if status != "CLOSED" or len(roadmap_stack) < 2:
                raise ProjectRuntimeError(
                    "Subroadmap closure is invalid.", reason="runtime_transition_invalid"
                )
            mode = "RETURN_TO_PARENT"
        elif event_type == "RETURNED_TO_PARENT":
            if mode != "RETURN_TO_PARENT" or len(roadmap_stack) < 2:
                raise ProjectRuntimeError(
                    "Return to parent is invalid.", reason="runtime_return_invalid"
                )
            child = roadmap_stack[-1]
            if payload["closed_roadmap_id"] != child.get("roadmap_id"):
                raise ProjectRuntimeError(
                    "Closed child differs from stack head.", reason="runtime_return_invalid"
                )
            roadmap_stack.pop()
            current_leaf_id = str(payload["return_node_id"])
            mode = "LOCKED_EXECUTION"
            status = "READY"
        elif event_type == "ASSIGNMENT_RETURNED":
            status = "RETURNED"
        elif event_type == "ASSIGNMENT_REJECTED":
            status = "REJECTED"
        elif event_type == "ASSIGNMENT_PAUSED":
            status = "PAUSED"
        elif event_type == "ASSIGNMENT_BLOCKED":
            status = "BLOCKED"
        elif event_type == "ROADMAP_SUPERSEDED":
            status = "SUPERSEDED"
        if event["to_status"] not in NODE_STATUSES | {"BOUND", "UNBOUND"}:
            raise ProjectRuntimeError(
                "Event target status is invalid.", reason="runtime_transition_invalid"
            )
        event_head = canonical_digest(event)
    value = _state_value(
        project_id=project["project_id"],
        status=status,
        mode=mode,
        current_leaf_id=current_leaf_id,
        roadmap_stack=roadmap_stack,
        event_head=event_head,
        event_count=len(events),
        actors=actor_map,
        workstreams=workstream_map,
        conflicts=conflicts,
        facts=facts,
    )
    return RuntimeState(
        project_id=project["project_id"],
        status=status,
        mode=mode,
        current_leaf_id=current_leaf_id,
        roadmap_stack=tuple(deepcopy(roadmap_stack)),
        event_head=event_head,
        event_count=len(events),
        actors=tuple(
            (key, actor_map[key]["role"], actor_map[key]["availability"])
            for key in sorted(actor_map)
        ),
        workstreams=tuple(
            (key, workstream_map[key]["actor_id"], workstream_map[key]["current_leaf_id"])
            for key in sorted(workstream_map)
        ),
        conflicts=tuple(sorted(conflicts)),
        facts=tuple(sorted(facts)),
        state_digest=canonical_digest(value),
    )


def query_runtime(state: RuntimeState) -> dict[str, Any]:
    available = {
        actor_id for actor_id, _, availability in state.actors if availability == "AVAILABLE"
    }
    workstreams = [item for item in state.workstreams if item[1] in available]
    readiness = (
        "BLOCKED"
        if state.conflicts
        else "READY"
        if state.status in {"BOUND", "READY", "ACTIVE"}
        else "NOT_READY"
    )
    return {
        "active_workstreams": len(workstreams),
        "conflicts": list(state.conflicts),
        "current_leaf_id": state.current_leaf_id,
        "event_head": state.event_head,
        "mode": state.mode,
        "next_transition": _next_transition(state),
        "project_id": state.project_id,
        "readiness": readiness,
        "roadmap_stack_depth": len(state.roadmap_stack),
        "state_digest": state.state_digest,
        "status": state.status,
    }


def _next_transition(state: RuntimeState) -> str:
    transitions = {
        "UNBOUND": "OWNER_PROJECT_BOUND",
        "BOUND": "OWNER_PLAN_ACCEPTED",
        "ACTIVE": "DONE_CANDIDATE_RECORDED",
        "DONE_CANDIDATE": "ARCHITECT_REVIEWED",
        "OWNER_ACCEPTED": "ASSIGNMENT_CLOSED",
        "CLOSED": "SUBROADMAP_CLOSED" if len(state.roadmap_stack) > 1 else "NONE",
        "READY": "OWNER_ASSIGNMENT_DECISION",
        "BLOCKED": "OWNER_DIRECTION_REQUIRED",
    }
    return transitions.get(state.status, "NONE")


def compare_and_swap_pointer(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    validate_runtime_record(current)
    validate_runtime_record(candidate)
    if current["format"] != "opencntx-runtime-pointer" or candidate["format"] != current["format"]:
        raise ProjectRuntimeError(
            "CAS requires runtime pointers.", reason="runtime_pointer_invalid"
        )
    if (
        candidate["project_id"] != current["project_id"]
        or candidate["revision"] != current["revision"] + 1
        or candidate["expected_previous_digest"] != canonical_digest(current)
    ):
        raise ProjectRuntimeError(
            "Runtime pointer compare-and-swap conflict.", reason="runtime_pointer_conflict"
        )
    return deepcopy(candidate)
