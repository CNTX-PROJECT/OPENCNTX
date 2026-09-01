"""Test-only historical reducer for the frozen R9 conformance corpus."""

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


def roadmap_catalog(
    roadmaps: Sequence[dict[str, Any]], *, project_id: str
) -> dict[str, dict[int, dict[str, Any]]]:
    """Validate and index immutable roadmap revisions for one project."""
    records = _validate_records(roadmaps, "opencntx-roadmap-definition")
    catalog: dict[str, dict[int, dict[str, Any]]] = {}
    identities: dict[tuple[str, int], str] = {}
    for record in records:
        validate_roadmap_graph(record)
        if record["project_id"] != project_id:
            raise ProjectRuntimeError(
                "Roadmap belongs to another project.", reason="runtime_definition_invalid"
            )
        identity = (record["roadmap_id"], record["revision"])
        digest = canonical_digest(record)
        previous = identities.get(identity)
        if previous is not None and previous != digest:
            raise ProjectRuntimeError(
                "Roadmap revision identity changed bytes.", reason="runtime_roadmap_drift"
            )
        identities[identity] = digest
        catalog.setdefault(record["roadmap_id"], {})[record["revision"]] = deepcopy(record)
    return catalog


def validate_roadmap_stack(
    *,
    stack: Sequence[dict[str, Any]],
    roadmaps: Sequence[dict[str, Any]],
    project_id: str,
    main_roadmap_id: str,
    current_leaf_id: str,
) -> tuple[tuple[dict[str, Any], ...], str]:
    """Validate a complete nested stack and return its canonical digest."""
    if not 1 <= len(stack) <= 8:
        raise ProjectRuntimeError(
            "Roadmap stack depth is invalid.", reason="runtime_stack_invalid"
        )
    catalog = roadmap_catalog(roadmaps, project_id=project_id)
    normalized = [deepcopy(frame) for frame in stack]
    roadmap_ids = [frame.get("roadmap_id") for frame in normalized]
    if len(set(roadmap_ids)) != len(roadmap_ids):
        raise ProjectRuntimeError(
            "Roadmap stack repeats a roadmap.", reason="runtime_stack_invalid"
        )
    bound: list[dict[str, Any]] = []
    required_frame_fields = {
        "active_node_id",
        "event_head",
        "policy_digest",
        "projection_digest",
        "return_node_id",
        "roadmap_id",
        "roadmap_revision",
        "schema_digest",
    }
    for index, frame in enumerate(normalized):
        if set(frame) != required_frame_fields:
            raise ProjectRuntimeError(
                "Roadmap stack frame differs from the contract.", reason="runtime_stack_invalid"
            )
        roadmap_id = frame["roadmap_id"]
        revision = frame["roadmap_revision"]
        record = catalog.get(roadmap_id, {}).get(revision)
        if record is None:
            raise ProjectRuntimeError(
                "Roadmap stack binds an unavailable revision.", reason="runtime_roadmap_drift"
            )
        node_ids = {node["node_id"] for node in record["nodes"]}
        if frame["active_node_id"] not in node_ids or frame["event_head"] != record["event_head"]:
            raise ProjectRuntimeError(
                "Roadmap stack frame differs from its revision.", reason="runtime_roadmap_drift"
            )
        if index == 0:
            if (
                roadmap_id != main_roadmap_id
                or record["roadmap_type"] != "MAIN_ROADMAP"
                or frame["return_node_id"] is not None
            ):
                raise ProjectRuntimeError(
                    "First stack frame is not the bound main roadmap.",
                    reason="runtime_main_roadmap_invalid",
                )
        else:
            parent = bound[-1]
            parent_nodes = {node["node_id"] for node in parent["nodes"]}
            if (
                record["roadmap_type"] != "SUBROADMAP"
                or record["parent_roadmap_id"] != parent["roadmap_id"]
                or record["parent_node_id"] not in parent_nodes
                or record["return_node_id"] not in parent_nodes
                or frame["return_node_id"] != record["return_node_id"]
            ):
                raise ProjectRuntimeError(
                    "Child frame has an invalid parent or return binding.",
                    reason="runtime_return_invalid",
                )
        bound.append(record)
    if normalized[-1]["active_node_id"] != current_leaf_id:
        raise ProjectRuntimeError(
            "Current leaf differs from the top stack frame.", reason="runtime_stack_invalid"
        )
    return tuple(normalized), canonical_digest(normalized)


def evaluate_workstream_state(
    *,
    project: dict[str, Any],
    actors: Sequence[dict[str, Any]],
    roadmaps: Sequence[dict[str, Any]],
    workstreams: Sequence[dict[str, Any]],
    resources: Sequence[dict[str, Any]],
    dependencies: dict[str, str] | None = None,
    target_paths: dict[str, Sequence[str]] | None = None,
    shared_integration: bool = False,
) -> dict[str, Any]:
    """Evaluate dependency, actor, resource, and bounded parallelism readiness."""
    validate_runtime_record(project)
    actor_records = _validate_records(actors, "opencntx-actor-binding")
    workstream_records = _validate_records(workstreams, "opencntx-workstream-binding")
    resource_records = _validate_records(resources, "opencntx-resource-claim")
    catalog = roadmap_catalog(roadmaps, project_id=project["project_id"])
    actor_map = {record["actor_id"]: record for record in actor_records}
    claim_map: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()
    for claim in resource_records:
        if claim["claim_id"] in claim_map:
            conflicts.add(f"DUPLICATE_CLAIM:{claim['claim_id']}")
        claim_map[claim["claim_id"]] = claim
    actor_owners: dict[str, str] = {}
    workstream_map: dict[str, dict[str, Any]] = {}
    for workstream in workstream_records:
        workstream_id = workstream["workstream_id"]
        actor_id = workstream["actor_id"]
        if workstream_id in workstream_map:
            conflicts.add(f"DUPLICATE_WORKSTREAM:{workstream_id}")
        workstream_map[workstream_id] = workstream
        actor = actor_map.get(actor_id)
        if actor is None or actor["availability"] != "AVAILABLE":
            conflicts.add(f"ACTOR_UNAVAILABLE:{actor_id}")
        if actor_id in actor_owners:
            conflicts.add(f"ACTOR_MULTI_LEAF:{actor_id}")
        actor_owners[actor_id] = workstream_id
        roadmap_revisions = catalog.get(workstream["roadmap_id"], {})
        if not roadmap_revisions:
            conflicts.add(f"ROADMAP_UNKNOWN:{workstream['roadmap_id']}")
        else:
            latest = roadmap_revisions[max(roadmap_revisions)]
            node_ids = {node["node_id"] for node in latest["nodes"]}
            if workstream["current_leaf_id"] not in node_ids:
                conflicts.add(f"LEAF_UNKNOWN:{workstream['current_leaf_id']}")
        for claim_id in workstream["resource_claim_ids"]:
            if claim_id not in claim_map:
                conflicts.add(f"CLAIM_UNKNOWN:{claim_id}")
    dependency_values = dependencies or {}
    pending = sorted(key for key, value in dependency_values.items() if value != "CLOSED")
    claims_by_workstream = {
        item["workstream_id"]: [
            claim_map[claim_id]
            for claim_id in item["resource_claim_ids"]
            if claim_id in claim_map
        ]
        for item in workstream_records
    }
    ids = sorted(claims_by_workstream)
    for left_index, left_id in enumerate(ids):
        for right_id in ids[left_index + 1 :]:
            for left in claims_by_workstream[left_id]:
                for right in claims_by_workstream[right_id]:
                    resources_overlap = set(left["resource_ids"]) & set(right["resource_ids"])
                    conflict_sets_overlap = set(left["conflict_set_ids"]) & set(
                        right["conflict_set_ids"]
                    )
                    if conflict_sets_overlap or (
                        resources_overlap and (left["exclusive"] or right["exclusive"])
                    ):
                        conflicts.add(f"RESOURCE_CONFLICT:{left_id}:{right_id}")
    paths = target_paths or {}
    for left_index, left_id in enumerate(sorted(paths)):
        for right_id in sorted(paths)[left_index + 1 :]:
            if set(paths[left_id]) & set(paths[right_id]):
                conflicts.add(f"TARGET_PATH_CONFLICT:{left_id}:{right_id}")
    available = sum(record["availability"] == "AVAILABLE" for record in actor_records)
    parallel_limit = min(16, available, len(workstream_records))
    if any(record["max_parallelism"] > parallel_limit for record in workstream_records):
        conflicts.add("PARALLELISM_EXCEEDS_CAPACITY")
    if pending:
        result_code = "BLOCKED_DEPENDENCY_NOT_READY"
    elif conflicts:
        result_code = "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"
    elif shared_integration:
        result_code = "SERIALIZED_SHARED_INTEGRATION"
    else:
        result_code = "WORKSTREAMS_READY"
    value = {
        "active_workstreams": len(workstream_records),
        "conflicts": sorted(conflicts),
        "integration_queue": sorted(workstream_map) if shared_integration else [],
        "parallel_limit": parallel_limit,
        "pending_dependencies": pending,
        "result_code": result_code,
    }
    return value | {"state_digest": canonical_digest(value)}


def serialize_integration_queue(items: Sequence[dict[str, str]]) -> tuple[dict[str, str], ...]:
    """Return the one deterministic shared-integration order."""
    required = {"event_digest", "node_id", "roadmap_id", "workstream_id"}
    normalized: list[dict[str, str]] = []
    for item in items:
        if set(item) != required or any(not isinstance(value, str) for value in item.values()):
            raise ProjectRuntimeError(
                "Integration queue item is invalid.", reason="runtime_integration_invalid"
            )
        normalized.append(dict(item))
    return tuple(
        sorted(
            normalized,
            key=lambda item: (
                item["roadmap_id"],
                item["node_id"],
                item["workstream_id"],
                item["event_digest"],
            ),
        )
    )


def prepare_return_to_parent(
    *,
    pointer: dict[str, Any],
    roadmaps: Sequence[dict[str, Any]],
    owner_accepted: bool,
    child_closed: bool,
    definition_of_done_complete: bool,
    event_chain_valid: bool,
    conflicts: Sequence[str] = (),
) -> dict[str, Any]:
    """Build but never persist the exact one-frame return pointer candidate."""
    validate_runtime_record(pointer)
    if pointer["format"] != "opencntx-runtime-pointer":
        raise ProjectRuntimeError(
            "Return requires a runtime pointer.", reason="runtime_pointer_invalid"
        )
    validate_roadmap_stack(
        stack=pointer["roadmap_stack"],
        roadmaps=roadmaps,
        project_id=pointer["project_id"],
        main_roadmap_id=pointer["main_roadmap_id"],
        current_leaf_id=pointer["current_leaf_id"],
    )
    if (
        pointer["mode"] != "RETURN_TO_PARENT"
        or len(pointer["roadmap_stack"]) < 2
        or not owner_accepted
        or not child_closed
        or not definition_of_done_complete
        or not event_chain_valid
        or conflicts
    ):
        raise ProjectRuntimeError(
            "Return-to-parent gate is not fully satisfied.", reason="runtime_return_invalid"
        )
    child = pointer["roadmap_stack"][-1]
    return_node = child["return_node_id"]
    if return_node is None:
        raise ProjectRuntimeError(
            "Child frame has no return node.", reason="runtime_return_invalid"
        )
    candidate = deepcopy(pointer)
    candidate["roadmap_stack"] = candidate["roadmap_stack"][:-1]
    candidate["current_leaf_id"] = return_node
    candidate["mode"] = "LOCKED_EXECUTION"
    candidate["revision"] += 1
    candidate["record_id"] = f"{pointer['pointer_id']}_R{candidate['revision']}"
    candidate["expected_previous_digest"] = canonical_digest(pointer)
    projection_value = {
        "current_leaf_id": return_node,
        "mode": candidate["mode"],
        "roadmap_stack": candidate["roadmap_stack"],
    }
    candidate["projected_state_digest"] = canonical_digest(projection_value)
    validate_runtime_record(candidate)
    return compare_and_swap_pointer(pointer, candidate)


def rebuild_runtime_status(
    *,
    pointer: dict[str, Any],
    roadmaps: Sequence[dict[str, Any]],
    workstream_state: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic summary without titles or any leaf body text."""
    stack, stack_digest = validate_roadmap_stack(
        stack=pointer["roadmap_stack"],
        roadmaps=roadmaps,
        project_id=pointer["project_id"],
        main_roadmap_id=pointer["main_roadmap_id"],
        current_leaf_id=pointer["current_leaf_id"],
    )
    frames = [
        {
            "active_node_id": frame["active_node_id"],
            "roadmap_id": frame["roadmap_id"],
            "roadmap_revision": frame["roadmap_revision"],
        }
        for frame in stack
    ]
    value = {
        "conflicts": list(workstream_state["conflicts"]),
        "current_leaf_id": pointer["current_leaf_id"],
        "main_roadmap_id": pointer["main_roadmap_id"],
        "mode": pointer["mode"],
        "parallel_limit": workstream_state["parallel_limit"],
        "pending_dependency_count": len(workstream_state["pending_dependencies"]),
        "roadmap_stack": frames,
        "roadmap_stack_digest": stack_digest,
        "workstream_count": workstream_state["active_workstreams"],
    }
    return value | {"projection_digest": canonical_digest(value)}


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
