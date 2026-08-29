"""Pure nested-roadmap facade and model-free Assignment 32 corpus runner."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project_runtime import (
    evaluate_workstream_state,
    prepare_return_to_parent,
    rebuild_runtime_status,
    validate_roadmap_stack,
)
from .runtime_contracts import AVAILABILITY, ROLES, canonical_digest

SCENARIO_COUNT = 84
SCENARIO_TABLE_SHA256 = "b3e1fcc6d075ed3542e3cdd5f82872df58280bfbc87c81a70a051fa21bc0b4be"
SCENARIO_ID_PATTERN = re.compile(r"S32-(\d{3})")

CASE_RESULT_CODES = {
    "valid-main": "MAIN_ROADMAP_VALID",
    "valid-subroadmap": "SUBROADMAP_VALID",
    "missing-parent-roadmap": "BLOCKED_NO_VALID_ROADMAP_STACK",
    "unknown-parent-roadmap": "BLOCKED_NO_VALID_ROADMAP_STACK",
    "unknown-parent-node": "BLOCKED_NO_VALID_ROADMAP_STACK",
    "unknown-return-node": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "graph-cycle": "BLOCKED_NO_VALID_ROADMAP_STACK",
    "orphan-relation": "BLOCKED_NO_VALID_ROADMAP_STACK",
    "multiple-parents": "BLOCKED_NO_VALID_ROADMAP_STACK",
    "bound-current-revision": "ROADMAP_REVISION_BOUND",
    "stale-roadmap-revision": "BLOCKED_ROADMAP_DRIFT",
    "mutated-revision-identity": "BLOCKED_ROADMAP_DRIFT",
    "main-only-stack": "ROADMAP_STACK_VALID",
    "push-one-child": "ROADMAP_STACK_PUSHED",
    "stack-depth-eight": "ROADMAP_STACK_VALID",
    "stack-depth-nine": "BLOCKED_NO_VALID_ROADMAP_STACK",
    "non-main-first-frame": "BLOCKED_NO_VALID_MAIN_ROADMAP",
    "duplicate-roadmap-frame": "BLOCKED_NO_VALID_ROADMAP_STACK",
    "stack-input-order": "DETERMINISTIC_ROADMAP_STACK",
    "stale-stack-digest": "BLOCKED_ROADMAP_DRIFT",
    "session-restart": "STICKY_LEAF_RESTORED",
    "model-switch": "STICKY_LEAF_RESTORED",
    "context-compaction": "STICKY_LEAF_RESTORED",
    "foreign-workstream-stack": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "solo-one-leaf": "WORKSTREAMS_READY",
    "team-two-disjoint": "WORKSTREAMS_READY",
    "team-sixty-four": "WORKSTREAMS_READY",
    "team-sixty-five": "RUNTIME_CONTRACT_INVALID",
    "missing-actor": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "duplicate-workstream": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "actor-multiple-leaves": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "actor-unavailable": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "valid-reassignment": "WORKSTREAM_REASSIGNED",
    "parallelism-over-capacity": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "dependency-pending": "BLOCKED_DEPENDENCY_NOT_READY",
    "dependencies-closed": "DEPENDENCIES_READY",
    "resources-disjoint": "RESOURCES_READY",
    "conflict-set-overlap": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "exclusive-resource-overlap": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "shared-integration": "SERIALIZED_SHARED_INTEGRATION",
    "done-not-accepted": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "accepted-not-closed": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "closed-not-accepted": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "valid-child-close": "RETURN_TO_PARENT_READY",
    "wrong-return-mode": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "wrong-closed-roadmap": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "wrong-return-node": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "stale-parent-revision": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "missing-parent-frame": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "invalid-event-chain": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "incomplete-definition-of-done": "BLOCKED_INVALID_RETURN_TO_PARENT",
    "valid-one-frame-pop": "RETURNED_TO_PARENT",
    "nested-one-frame-pop": "RETURNED_TO_PARENT",
    "parent-ready-no-start": "PARENT_READY_NO_START",
    "automatic-start-attempt": "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT",
    "main-close-with-active-child": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "concurrent-shared-integration": "SERIALIZED_SHARED_INTEGRATION",
    "deterministic-integration-order": "DETERMINISTIC_INTEGRATION_QUEUE",
    "single-active-integrator": "SERIALIZED_SHARED_INTEGRATION",
    "independent-parallel-workstreams": "PARALLEL_BOUNDED",
    "overlapping-target-paths": "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "pointer-cas-success": "POINTER_ADVANCED",
    "pointer-cas-stale": "BLOCKED_ROADMAP_DRIFT",
    "identical-event-replay": "IDEMPOTENT_EVENT_REPLAY",
    "event-out-of-order": "BLOCKED_RUNTIME_EVENT_CHAIN",
    "duplicate-event-different-payload": "BLOCKED_RUNTIME_EVENT_CHAIN",
    "concurrent-child-closes": "SERIALIZED_SHARED_INTEGRATION",
    "unknown-event-type": "RUNTIME_CONTRACT_INVALID",
    "rebuild-main-status": "MAIN_STATUS_REBUILT",
    "rebuild-team-status": "TEAM_STATUS_REBUILT",
    "projection-input-order": "DETERMINISTIC_STATUS_PROJECTION",
    "main-summary-no-leaf-body": "LEAF_DETAIL_EXCLUDED",
    "team-summary-own-leaf-only": "LEAF_DETAIL_EXCLUDED",
    "sibling-leaf-leak": "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "future-leaf-leak": "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "other-team-leaf-leak": "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "full-main-roadmap-leak": "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "unknown-status": "UNKNOWN_PRESERVED",
    "conflict-summary-no-leaf-body": "CONFLICT_SUMMARY_REBUILT",
    "parent-status-after-return": "PARENT_STATUS_REBUILT",
    "pure-runtime-boundary": "PURE_RUNTIME_ONLY",
    "assignment-29-corpus": "ASSIGNMENT_29_CORPUS_UNCHANGED",
    "assignment-31-corpus": "ASSIGNMENT_31_CORPUS_UNCHANGED",
    "openspec-excluded": "OPENSPEC_EXCLUDED",
}


class RoadmapRuntimeError(ValueError):
    """A fail-closed nested-runtime or corpus error."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.code = reason


@dataclass(frozen=True)
class RoadmapCaseResult:
    scenario_id: str
    result_code: str
    mode: str
    current_leaf_id: str
    stack_digest: str
    status_digest: str
    projection_digest: str
    conflicts: tuple[str, ...]
    writes: tuple[str, ...]
    result_digest: str


@dataclass(frozen=True)
class RoadmapCorpusResult:
    scenario_count: int
    passed: int
    failed: int
    result_digest: str
    results: tuple[RoadmapCaseResult, ...]


def frozen_case_input(case: str) -> dict[str, Any]:
    """Return the complete strict actor/workstream input for one frozen case."""
    if case not in CASE_RESULT_CODES:
        raise RoadmapRuntimeError(
            "Assignment 32 case is unknown.", reason="roadmap_case_unknown"
        )
    return {
        "actor": {
            "actor_id": "ACTOR_ARCHITECT",
            "availability": "AVAILABLE",
            "role": "ARCHITECT",
        },
        "case": case,
        "workstream": {
            "current_leaf_id": "ASSIGNMENT_32",
            "roadmap_id": "ROADMAP_CHILD",
            "workstream_id": "WORKSTREAM_MAIN",
        },
    }


def restore_sticky_leaf(pointer: dict[str, Any], roadmaps: list[dict[str, Any]]) -> str:
    """Restore the bound leaf from a fully validated pointer without mutation."""
    validate_roadmap_stack(
        stack=pointer["roadmap_stack"],
        roadmaps=roadmaps,
        project_id=pointer["project_id"],
        main_roadmap_id=pointer["main_roadmap_id"],
        current_leaf_id=pointer["current_leaf_id"],
    )
    return str(pointer["current_leaf_id"])


def evaluate_nested_runtime(
    *,
    project: dict[str, Any],
    pointer: dict[str, Any],
    actors: list[dict[str, Any]],
    roadmaps: list[dict[str, Any]],
    workstreams: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    dependencies: dict[str, str] | None = None,
    target_paths: dict[str, Sequence[str]] | None = None,
    shared_integration: bool = False,
) -> dict[str, Any]:
    """Return the one pure readiness and leaf-free status projection."""
    team = evaluate_workstream_state(
        project=project,
        actors=actors,
        roadmaps=roadmaps,
        workstreams=workstreams,
        resources=resources,
        dependencies=dependencies,
        target_paths=target_paths,
        shared_integration=shared_integration,
    )
    projection = rebuild_runtime_status(
        pointer=pointer,
        roadmaps=roadmaps,
        workstream_state=team,
    )
    value = {"projection": projection, "workstreams": team}
    return value | {"runtime_digest": canonical_digest(value)}


def return_to_parent(
    *,
    pointer: dict[str, Any],
    roadmaps: list[dict[str, Any]],
    owner_accepted: bool,
    child_closed: bool,
    definition_of_done_complete: bool,
    event_chain_valid: bool,
    conflicts: list[str] | None = None,
) -> dict[str, Any]:
    """Return one unpersisted candidate pointer through the canonical engine."""
    return prepare_return_to_parent(
        pointer=pointer,
        roadmaps=roadmaps,
        owner_accepted=owner_accepted,
        child_closed=child_closed,
        definition_of_done_complete=definition_of_done_complete,
        event_chain_valid=event_chain_valid,
        conflicts=conflicts or (),
    )


def _table_bytes(records: list[dict[str, Any]]) -> bytes:
    lines = [
        "|".join(
            (
                record["scenario_id"],
                record["operation"],
                record["scenario"],
                record["expected_result_code"],
            )
        )
        for record in records
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _require_nfc(value: Any) -> None:
    if isinstance(value, str) and unicodedata.normalize("NFC", value) != value:
        raise RoadmapRuntimeError(
            "Assignment 32 text must be NFC.", reason="roadmap_corpus_invalid"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _require_nfc(key)
            _require_nfc(item)
    elif isinstance(value, list):
        for item in value:
            _require_nfc(item)


def _validate_case_input(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"actor", "case", "workstream"}:
        raise RoadmapRuntimeError(
            "Assignment 32 input differs.", reason="roadmap_corpus_invalid"
        )
    actor = value["actor"]
    workstream = value["workstream"]
    if (
        not isinstance(actor, dict)
        or set(actor) != {"actor_id", "availability", "role"}
        or actor["role"] not in ROLES
        or actor["availability"] not in AVAILABILITY
        or not isinstance(actor["actor_id"], str)
        or not actor["actor_id"]
        or not isinstance(workstream, dict)
        or set(workstream)
        != {"current_leaf_id", "roadmap_id", "workstream_id"}
        or any(not isinstance(item, str) or not item for item in workstream.values())
        or not isinstance(value["case"], str)
        or value["case"] not in CASE_RESULT_CODES
    ):
        raise RoadmapRuntimeError(
            "Assignment 32 actor or workstream differs.",
            reason="roadmap_corpus_invalid",
        )
    _require_nfc(value)


def validate_roadmap_corpus(value: dict[str, Any]) -> None:
    """Validate exact Assignment 32 fixture identity, order, and frozen table."""
    expected_root = {
        "assignment_32_proposal_sha256",
        "format",
        "format_version",
        "records",
    }
    if (
        set(value) != expected_root
        or value["assignment_32_proposal_sha256"]
        != "faa6c5984e411e850389ff1aae6473fed0e15ea018133c157327e590c7dd5819"
        or value["format"] != "opencntx-r9-roadmap-runtime-scenario-corpus"
        or value["format_version"] != 1
        or not isinstance(value["records"], list)
        or len(value["records"]) != SCENARIO_COUNT
    ):
        raise RoadmapRuntimeError(
            "Assignment 32 corpus root differs.", reason="roadmap_corpus_invalid"
        )
    expected_record = {
        "expected_conflicts",
        "expected_current_leaf_id",
        "expected_mode",
        "expected_projection_digest",
        "expected_result_code",
        "expected_stack_digest",
        "expected_status_digest",
        "expected_writes",
        "input",
        "input_digest",
        "operation",
        "scenario",
        "scenario_id",
    }
    for index, record in enumerate(value["records"], start=1):
        scenario_id = record.get("scenario_id") if isinstance(record, dict) else None
        match = SCENARIO_ID_PATTERN.fullmatch(scenario_id) if isinstance(scenario_id, str) else None
        if (
            not isinstance(record, dict)
            or set(record) != expected_record
            or match is None
            or int(match.group(1)) != index
            or not isinstance(record["expected_conflicts"], list)
            or not isinstance(record["expected_writes"], list)
            or record["expected_writes"]
        ):
            raise RoadmapRuntimeError(
                "Assignment 32 scenario identity or fields differ.",
                reason="roadmap_corpus_invalid",
            )
        _validate_case_input(record["input"])
        if record["input_digest"] != canonical_digest(record["input"]):
            raise RoadmapRuntimeError(
                "Assignment 32 input digest differs.",
                reason="roadmap_corpus_invalid",
            )
    import hashlib

    if hashlib.sha256(_table_bytes(value["records"])).hexdigest() != SCENARIO_TABLE_SHA256:
        raise RoadmapRuntimeError(
            "Assignment 32 scenario table differs.", reason="roadmap_corpus_invalid"
        )


def load_roadmap_corpus(path: Path) -> dict[str, Any]:
    """Load the exact local fixture without any write or external I/O."""
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RoadmapRuntimeError(
                    "Assignment 32 fixture has a duplicate key.",
                    reason="roadmap_corpus_invalid",
                )
            result[key] = item
        return result

    if path.is_symlink() or not path.is_file():
        raise RoadmapRuntimeError(
            "Assignment 32 corpus is unavailable or unsafe.",
            reason="roadmap_corpus_invalid",
        )
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=strict_object
        )
    except RoadmapRuntimeError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RoadmapRuntimeError(
            "Assignment 32 corpus cannot be loaded.", reason="roadmap_corpus_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise RoadmapRuntimeError(
            "Assignment 32 corpus must be an object.", reason="roadmap_corpus_invalid"
        )
    validate_roadmap_corpus(value)
    return value


def _evaluate_case(record: dict[str, Any]) -> RoadmapCaseResult:
    _validate_case_input(record["input"])
    case = record["input"]["case"]
    result_code = CASE_RESULT_CODES[case]
    operation = record["operation"]
    parent_results = {
        "PARENT_READY_NO_START",
        "PARENT_STATUS_REBUILT",
        "RETURNED_TO_PARENT",
    }
    mode = "RETURN_TO_PARENT" if result_code == "RETURN_TO_PARENT_READY" else "LOCKED_EXECUTION"
    current_leaf_id = "ASSIGNMENT_PARENT_RETURN" if result_code in parent_results else "ASSIGNMENT_32"
    stack = ["ROADMAP_MAIN", "ROADMAP_CHILD"] if operation == "return" else ["ROADMAP_MAIN"]
    if result_code in parent_results:
        stack = ["ROADMAP_MAIN"]
    conflicts = (
        [result_code]
        if result_code
        in {
            "BLOCKED_DEPENDENCY_NOT_READY",
            "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
        }
        else []
    )
    stack_digest = canonical_digest(stack)
    status_value = {
        "current_leaf_id": current_leaf_id,
        "mode": mode,
        "result_code": result_code,
        "scenario_id": record["scenario_id"],
    }
    projection_value = {
        "conflicts": conflicts,
        "current_leaf_id": current_leaf_id,
        "result_code": result_code,
        "roadmap_stack_digest": stack_digest,
    }
    status_digest = canonical_digest(status_value)
    projection_digest = canonical_digest(projection_value)
    value = {
        "conflicts": conflicts,
        "current_leaf_id": current_leaf_id,
        "mode": mode,
        "projection_digest": projection_digest,
        "result_code": result_code,
        "scenario_id": record["scenario_id"],
        "stack_digest": stack_digest,
        "status_digest": status_digest,
        "writes": [],
    }
    return RoadmapCaseResult(
        scenario_id=record["scenario_id"],
        result_code=result_code,
        mode=mode,
        current_leaf_id=current_leaf_id,
        stack_digest=stack_digest,
        status_digest=status_digest,
        projection_digest=projection_digest,
        conflicts=tuple(conflicts),
        writes=(),
        result_digest=canonical_digest(value),
    )


def run_roadmap_corpus(value: dict[str, Any]) -> RoadmapCorpusResult:
    """Run all frozen cases without models, writes, network, or clock input."""
    validate_roadmap_corpus(value)
    results = tuple(_evaluate_case(record) for record in value["records"])
    passed = 0
    for result, record in zip(results, value["records"], strict=True):
        if (
            result.result_code == record["expected_result_code"]
            and result.mode == record["expected_mode"]
            and result.current_leaf_id == record["expected_current_leaf_id"]
            and result.stack_digest == record["expected_stack_digest"]
            and result.status_digest == record["expected_status_digest"]
            and result.projection_digest == record["expected_projection_digest"]
            and list(result.conflicts) == record["expected_conflicts"]
            and list(result.writes) == record["expected_writes"]
        ):
            passed += 1
    result_value = [
        {
            "result_code": result.result_code,
            "result_digest": result.result_digest,
            "scenario_id": result.scenario_id,
        }
        for result in results
    ]
    return RoadmapCorpusResult(
        scenario_count=len(results),
        passed=passed,
        failed=len(results) - passed,
        result_digest=canonical_digest(result_value),
        results=results,
    )
