"""Linked goal obligations projected through the existing native checkpoint chain.

No test-runtime imports or independent scheduling database. Host-supplied statuses
are structural facts, never sufficient evidence for semantic completion.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .continuity import (
    _digest,
    _fail,
    _load_store,
    _resolve_input,
    _safe_relative,
    _validate_graph,
    _value_digest,
    record_execution_checkpoint,
    validate_current_goal_binding,
)
from .goal_binding import BoundGoal, _canonical, _path, _sha, _text, _unique
from .session_continuity import store_evidence_object, verify_evidence_object

NODE_FIELDS = frozenset(
    {
        "id",
        "parent",
        "return_to",
        "children",
        "depends_on",
        "outcome_ids",
        "source_snapshot",
        "evidence",
        "status",
        "next_action",
    }
)


@dataclass(frozen=True)
class GoalProgress:
    canonical_json: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def _references(items: object) -> list[dict[str, str]]:
    if not isinstance(items, (list, tuple)) or len(items) > 50:
        raise _fail("goal_progress_invalid", "References must be bounded.")
    result = []
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {"reference", "sha256"}:
            raise _fail("goal_progress_invalid", "Reference fields differ.")
        result.append(
            {"reference": _path(item["reference"]), "sha256": _sha(item["sha256"], "source")}
        )
    if len({item["reference"] for item in result}) != len(result):
        raise _fail("goal_progress_invalid", "References repeat.")
    return result


def _nodes(
    nodes: Sequence[Mapping[str, object]], root_id: str, outcomes: list[str]
) -> list[dict[str, Any]]:
    if not isinstance(nodes, (list, tuple)) or not 1 <= len(nodes) <= 50:
        raise _fail("goal_progress_invalid", "Hierarchy must contain 1 to 50 nodes.")
    normalized = []
    for raw in nodes:
        if not isinstance(raw, Mapping) or set(raw) != NODE_FIELDS:
            raise _fail("goal_progress_invalid", "Node fields differ.")
        node = dict(raw)
        for key in ("id", "next_action"):
            node[key] = _text(node[key], key)
        for key in ("parent", "return_to"):
            if node[key] is not None:
                node[key] = _text(node[key], key)
        for key in ("children", "depends_on", "outcome_ids"):
            node[key] = _unique(node[key], key)
        for key in ("source_snapshot", "evidence"):
            node[key] = _references(node[key])
        if node["status"] not in {"OPEN", "BLOCKED", "DELIVERED"} or not node["outcome_ids"]:
            raise _fail("goal_progress_invalid", "Invalid status or missing outcomes.")
        if not set(node["outcome_ids"]).issubset(outcomes):
            raise _fail("goal_progress_invalid", "Node belongs to an unrelated outcome.")
        normalized.append(node)
    by_id = {node["id"]: node for node in normalized}
    if len(by_id) != len(nodes) or root_id not in by_id:
        raise _fail("goal_progress_invalid", "Duplicate node or missing root.")
    root = by_id[root_id]
    if (
        root["parent"] is not None
        or root["return_to"] is not None
        or set(root["outcome_ids"]) != set(outcomes)
    ):
        raise _fail("goal_progress_invalid", "Root does not retain the original outcomes.")
    for node in normalized:
        if node["id"] != root_id:
            parent = by_id.get(node["parent"])
            if (
                parent is None
                or node["id"] not in parent["children"]
                or node["return_to"] != parent["id"]
            ):
                raise _fail("goal_progress_invalid", "Child has no exact parent and return.")
        for child in node["children"]:
            if child not in by_id or by_id[child]["parent"] != node["id"]:
                raise _fail("goal_progress_invalid", "Missing child or inconsistent parent.")
        if node["children"]:
            covered = set().union(*(set(by_id[child]["outcome_ids"]) for child in node["children"]))
            if covered != set(node["outcome_ids"]):
                raise _fail("goal_progress_invalid", "Children lose parent outcomes.")
        if any(dep not in by_id or dep == node["id"] for dep in node["depends_on"]):
            raise _fail("goal_progress_invalid", "Missing or self dependency.")
    _acyclic(by_id, root_id)
    return sorted(normalized, key=lambda item: item["id"])


def _acyclic(nodes: dict[str, dict[str, Any]], root_id: str) -> None:
    _validate_graph(list(nodes.values()))
    for identifier in nodes:
        # Every node must reach the one root; a detached parent cycle is invalid.
        seen: set[str] = set()
        cursor = identifier
        while cursor != root_id:
            if cursor in seen or len(seen) >= 8:
                raise _fail("goal_progress_invalid", "Detached or cyclic parent chain.")
            seen.add(cursor)
            cursor = nodes[cursor]["parent"]
        seen.add(root_id)
        if any(
            identifier in nodes[ancestor]["depends_on"]
            or ancestor in nodes[identifier]["depends_on"]
            for ancestor in seen
            if ancestor != identifier
        ):
            raise _fail("goal_progress_invalid", "Ancestor waits for its own descendant.")


def build_goal_progress(
    goal: BoundGoal,
    *,
    root_id: str,
    nodes: Sequence[Mapping[str, object]],
    previous: GoalProgress | None = None,
) -> GoalProgress:
    bound = goal.payload()
    request = bound["request"]
    prior = validate_goal_progress(previous, goal) if previous is not None else None
    if prior is not None and (
        prior["request"] != request or prior["intent_digest"] != bound["intent_v1"]["intent_digest"]
    ):
        raise _fail(
            "goal_progress_stale", "Internal replan must retain the same request and authority."
        )
    normalized = _nodes(nodes, _text(root_id, "root_id"), request["outcome_ids"])
    inherited = [] if prior is None else prior["retained_evidence"]
    retained = {(_canonical(ref)): ref for ref in inherited}
    for node in normalized + ([] if prior is None else prior["nodes"]):
        for ref in node["evidence"] + node["source_snapshot"]:
            retained[_canonical(ref)] = ref
    value = {
        "format": "opencntx-goal-progress",
        "format_version": 2,
        "revision": 1 if prior is None else prior["revision"] + 1,
        "previous_progress_digest": None if prior is None else prior["progress_digest"],
        "request": request,
        "intent_digest": bound["intent_v1"]["intent_digest"],
        "root_id": root_id,
        "nodes": normalized,
        "retained_evidence": [retained[key] for key in sorted(retained)],
    }
    return GoalProgress(_canonical(value | {"progress_digest": _value_digest(value)}))


def validate_goal_progress(progress: GoalProgress, goal: BoundGoal) -> dict[str, Any]:
    value = progress.payload()
    bound = goal.payload()
    fields = {
        "format",
        "format_version",
        "revision",
        "previous_progress_digest",
        "request",
        "intent_digest",
        "root_id",
        "nodes",
        "retained_evidence",
        "progress_digest",
    }
    if (
        set(value) != fields
        or value["format"] != "opencntx-goal-progress"
        or type(value["format_version"]) is not int
        or value["format_version"] != 2
        or type(value["revision"]) is not int
        or value["revision"] < 1
        or value["progress_digest"]
        != _value_digest({k: v for k, v in value.items() if k != "progress_digest"})
        or value["request"] != bound["request"]
        or value["intent_digest"] != bound["intent_v1"]["intent_digest"]
    ):
        raise _fail("goal_progress_stale", "Progress does not bind the current request.")
    if _nodes(value["nodes"], value["root_id"], bound["request"]["outcome_ids"]) != value["nodes"]:
        raise _fail("goal_progress_invalid", "Hierarchy is not canonical.")
    return value


def progress_readiness(progress: GoalProgress, goal: BoundGoal) -> dict[str, Any]:
    value = validate_goal_progress(progress, goal)
    nodes = {node["id"]: node for node in value["nodes"]}

    def ready(node: dict[str, Any]) -> bool:
        if node["children"] or node["status"] != "OPEN":
            return False
        cursor = node
        while True:
            if cursor["status"] == "BLOCKED" or any(
                nodes[dep]["status"] != "DELIVERED" for dep in cursor["depends_on"]
            ):
                return False
            if cursor["parent"] is None:
                return True
            cursor = nodes[cursor["parent"]]

    return {
        "ready_nodes": [node["id"] for node in value["nodes"] if ready(node)],
        "blocked_nodes": [node["id"] for node in value["nodes"] if node["status"] == "BLOCKED"],
        "open_outcome_ids": sorted(
            {
                outcome
                for node in value["nodes"]
                if not node["children"] and node["status"] != "DELIVERED"
                for outcome in node["outcome_ids"]
            }
        ),
        "parent_status": "PARTIAL",
        "completion_proof": "REQUIRED",
    }


def persist_goal_progress(
    root: Path, goal: BoundGoal, progress: GoalProgress, *, evidence_directory: Path
) -> dict[str, Any]:
    """Prepare evidence then CAS its pointer through the sole native writer."""
    validate_current_goal_binding(root, goal.payload(), expected=goal)
    value = validate_goal_progress(progress, goal)
    references = {
        ref["reference"]: ref["sha256"]
        for node in value["nodes"]
        for ref in node["source_snapshot"] + node["evidence"]
    }
    if any(
        references[ref["reference"]] != ref["sha256"]
        for node in value["nodes"]
        for ref in node["source_snapshot"] + node["evidence"]
    ):
        raise _fail("goal_progress_invalid", "One reference has conflicting source digests.")
    for reference, expected in references.items():
        content = _resolve_input(root, _safe_relative(reference, "source_snapshot")).read_bytes()
        if _digest(content) != expected:
            raise _fail(
                "goal_progress_stale", "Source snapshot or evidence changed before binding."
            )
    content = _canonical({"goal": goal.payload(), "progress": value}).encode("utf-8")
    metadata = store_evidence_object(root, content=content, summary="Bound goal progress v2")
    digest = metadata["sha256"]
    relative = _safe_relative(evidence_directory.relative_to(root).as_posix(), "evidence_directory")
    directory = root / relative
    # The supervisor explicitly allocates this directory; never weaken the
    # native prohibition on .opencntx as caller-supplied evidence.
    if not directory.is_dir() or directory.is_symlink() or directory.resolve() != directory:
        raise _fail(
            "goal_progress_invalid", "Evidence directory must already exist without aliases."
        )
    receipt = directory / f"goal-progress-{digest}.json"
    receipt_bytes = _canonical(
        {
            "format": "opencntx-goal-progress-reference",
            "format_version": 2,
            "object_sha256": digest,
            "progress_digest": value["progress_digest"],
        }
    ).encode()
    try:
        with receipt.open("xb") as stream:
            stream.write(receipt_bytes)
    except FileExistsError:
        if receipt.is_symlink() or receipt.read_bytes() != receipt_bytes:
            raise _fail("goal_progress_invalid", "Existing evidence receipt differs.") from None
    return record_execution_checkpoint(
        root,
        checkpoint_id=f"GP-{digest[:32].upper()}",
        current_internal_task="GOAL_PROGRESS_V2",
        next_internal_action="Continue the exact ready outcome from the bound hierarchy.",
        evidence_paths=[receipt.relative_to(root).as_posix(), *sorted(references)],
        expected_state_digest=goal.payload()["execution_capsule_v1"]["state_digest"],
    )


def load_goal_progress(root: Path, goal: BoundGoal) -> GoalProgress:
    """Only native-bound objects are current; unreferenced prepared files are inert."""
    store, _, events, state = _load_store(root)
    assignment = state["current_assignment"]
    if assignment is None and state["status"] == "COMPLETE" and state["completed"]:
        assignment = state["completed"][-1]
    event = next(
        (
            event
            for event in reversed(events)
            if event["type"] == "EXECUTION_CHECKPOINT"
            and event["payload"]["assignment_id"] == assignment
            and event["payload"]["current_internal_task"] == "GOAL_PROGRESS_V2"
        ),
        None,
    )
    if event is None:
        raise _fail("goal_progress_missing", "No native-bound hierarchy is available.")
    paths = event["payload"]["evidence"]
    if not paths:
        raise _fail("goal_progress_invalid", "Checkpoint has no object reference.")
    receipt = json.loads((root / paths[0]["path"]).read_bytes())
    if (
        receipt.get("format") != "opencntx-goal-progress-reference"
        or type(receipt.get("format_version")) is not int
        or receipt.get("format_version") != 2
    ):
        raise _fail("goal_progress_invalid", "Unsupported progress receipt.")
    digest = _sha(receipt["object_sha256"], "object_sha256")
    metadata = verify_evidence_object(root, digest)
    data = json.loads(gzip.decompress((store / metadata["object_path"]).read_bytes()))
    if (
        data["goal"]["execution_capsule_v1"]["state_digest"]
        != event["payload"]["prior_state_digest"]
    ):
        raise _fail(
            "goal_progress_stale", "Progress preparation belongs to different native state."
        )
    progress = GoalProgress(_canonical(data["progress"]))
    validate_goal_progress(progress, goal)
    if progress.payload()["progress_digest"] != receipt["progress_digest"]:
        raise _fail("goal_progress_invalid", "Receipt binds different progress.")
    return progress
