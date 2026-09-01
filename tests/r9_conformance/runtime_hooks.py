"""Test-only historical hooks for the frozen R9 conformance corpus."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .project_runtime import RuntimeState
from .roadmap_guard import (
    ALLOW_EXACT_ACTION,
    GUARD_TRIGGERS,
    READ_ONLY_ONLY,
    evaluate_guard,
)
from .roadmap_runtime import restore_sticky_leaf
from .runtime_contracts import canonical_digest, validate_runtime_record

SCENARIO_COUNT = 96
SCENARIO_TABLE_SHA256 = "f0ce7bdd0092cfb27ebae24237f5b7373e41f60b75b29e9972be2516c2fa7c48"
ASSIGNMENT_33_PROPOSAL_SHA256 = "e5f476d2af3d65c600e4f0d49b04eaf3a8424beb685011dfc3268257ec2f2b8a"
SCENARIO_ID_PATTERN = re.compile(r"S33-(\d{3})")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
ZERO_DIGEST = "0" * 64
CONTEXT_SCHEMA_ID = "urn:uuid:e8ba876f-9064-54c7-9127-461adf8d3428"

SCALE_BUDGETS = {
    "TINY_TASK": (15, 65_536),
    "SMALL_PROJECT": (25, 131_072),
    "MEDIUM_PROJECT": (40, 262_144),
    "LARGE_PROJECT": (60, 524_288),
    "MEGA_PROJECT": (80, 1_048_576),
}
CONTINUITY_EVENTS = {
    "SESSION_RESTART",
    "MODEL_SWITCH",
    "CONTEXT_COMPACTION",
    "TEAM_HANDOFF",
}
FORBIDDEN_DETAIL_MARKERS = {
    "FULL_MAIN_ROADMAP",
    "SIBLING_DETAIL",
    "FUTURE_DETAIL",
    "OTHER_TEAM_LEAF",
    "OLD_CHAT",
    "BROAD_EVIDENCE",
    "FULL_MEM_DIRECTORY",
    "FULL_OBSIDIAN_DIRECTORY",
    "UNAUTHORIZED_PARKING_ITEM",
}
MUTATING_HOOKS = {
    "BEFORE_ACTION",
    "AFTER_ACTION",
    "BEFORE_STORAGE_WRITE",
    "BEFORE_SYNC",
    "AFTER_SYNC",
    "DONE_CANDIDATE",
    "OWNER_ACCEPTED",
    "NODE_CLOSED",
    "SUBROADMAP_CLOSED",
    "RETURN_TO_PARENT",
}

_RESULT_CODES = (
    "READ_ONLY_ONLY",
    "READ_ONLY_ONLY",
    "READ_ONLY_ONLY",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "ALLOW_EXACT_ACTION",
    "BLOCKED_ROADMAP_DRIFT",
    "RUNTIME_HOOK_INVALID",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BLOCKED_ROADMAP_DRIFT",
    "BLOCKED_ROADMAP_DRIFT",
    "BLOCKED_ROADMAP_DRIFT",
    "BLOCKED_RUNTIME_HOOK_BYPASS",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BREADCRUMB_VALID",
    "BLOCKED_CONTEXT_BUDGET",
    "CURRENT_ASSIGNMENT_PACKAGE_VALID",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ROADMAP_DRIFT",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT",
    "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_CONTEXT_BUDGET",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "CONTEXT_PROJECTION_VALID",
    "BLOCKED_CONTEXT_BUDGET",
    "CONTEXT_PROJECTION_VALID",
    "CONTEXT_PROJECTION_VALID",
    "CONTEXT_PROJECTION_VALID",
    "CONTEXT_PROJECTION_VALID",
    "CONTEXT_PROJECTION_VALID",
    "BLOCKED_CONTEXT_BUDGET",
    "BLOCKED_CONTEXT_BUDGET",
    "CONTEXT_PROJECTION_DETERMINISTIC",
    "PARENT_FRAGMENT_NOT_REQUIRED",
    "JUSTIFIED_PARENT_FRAGMENT_VALID",
    "BLOCKED_CONTEXT_BUDGET",
    "BLOCKED_ROADMAP_DRIFT",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "BLOCKED_CONTEXT_BUDGET",
    "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
    "PARKING_LOT_OWNER_AUTHORIZED",
    "BLOCKED_OWNER_ONLY_PARKING_LOT",
    "BLOCKED_OWNER_ONLY_PARKING_LOT",
    "BLOCKED_OWNER_ONLY_PARKING_LOT",
    "PARKING_LOT_ZERO_STATE_CHANGE",
    "STICKY_LEAF_RESTORED",
    "STICKY_LEAF_RESTORED",
    "STICKY_LEAF_RESTORED",
    "TEAM_HANDOFF_CONTEXT_RESTORED",
    "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
    "OPENSPEC_EXCLUDED",
    "PURE_RUNTIME_HOOKS_NO_IO",
)
CASE_RESULT_CODES = {
    f"S33-{index:03d}": result for index, result in enumerate(_RESULT_CODES, start=1)
}


class RuntimeHookError(ValueError):
    """A malformed or bypassing runtime-hook request."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.code = reason


@dataclass(frozen=True)
class RuntimeHookDecision:
    status: str
    trigger: str
    action: str
    checks: tuple[str, ...]
    state_digest: str
    envelope_digest: str
    roadmap_stack_digest: str
    guard_decision_digest: str
    hook_trace_digest: str
    decision_digest: str
    writes: tuple[str, ...]


@dataclass(frozen=True)
class CurrentAssignmentPackage:
    status: str
    breadcrumb: str
    leaf_package: dict[str, Any]
    context_projection: dict[str, Any]
    package_digest: str
    projection_digest: str
    writes: tuple[str, ...]


@dataclass(frozen=True)
class ParkingLotDecision:
    status: str
    item_digest: str
    source_state_digest: str
    resulting_state_digest: str
    decision_digest: str
    writes: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeHookCaseResult:
    scenario_id: str
    result_code: str
    guard_status: str
    hook_trace_digest: str
    breadcrumb_digest: str
    package_digest: str
    projection_digest: str
    writes: tuple[str, ...]
    result_digest: str


@dataclass(frozen=True)
class RuntimeHookCorpusResult:
    scenario_count: int
    passed: int
    failed: int
    result_digest: str
    results: tuple[RuntimeHookCaseResult, ...]


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RuntimeHookError(
                "Runtime-hook JSON contains a duplicate key.",
                reason="runtime_hook_json_duplicate_key",
            )
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise RuntimeHookError(
        f"Runtime-hook JSON contains unsupported constant {value}.",
        reason="runtime_hook_json_constant",
    )


def _require_nfc(value: Any) -> None:
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise RuntimeHookError("Runtime-hook text is not NFC.", reason="runtime_hook_non_nfc")
        return
    if isinstance(value, list):
        for item in value:
            _require_nfc(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _require_nfc(key)
            _require_nfc(item)


def _require_keys(value: Any, expected: set[str], *, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimeHookError("Runtime-hook object shape is invalid.", reason=reason)
    return value


def _require_string(value: Any, field: str, *, maximum: int = 8192) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RuntimeHookError(
            f"{field} must be a bounded non-empty string.",
            reason="runtime_hook_field_invalid",
        )
    _require_nfc(value)
    return value


def _require_digest(value: Any, field: str) -> str:
    text = _require_string(value, field, maximum=64)
    if DIGEST_PATTERN.fullmatch(text) is None:
        raise RuntimeHookError(
            f"{field} must be a lowercase SHA-256.",
            reason="runtime_hook_digest_invalid",
        )
    return text


def _require_string_list(value: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise RuntimeHookError(
            f"{field} must be a string list.", reason="runtime_hook_field_invalid"
        )
    result = [_require_string(item, field) for item in value]
    if len(result) != len(set(result)):
        raise RuntimeHookError(f"{field} contains duplicates.", reason="runtime_hook_field_invalid")
    return result


def _latest(items: Sequence[str], value: str) -> int:
    for index in range(len(items) - 1, -1, -1):
        if items[index] == value:
            return index
    return -1


def validate_runtime_hook_trace(hooks: Sequence[str]) -> str:
    """Validate a bounded ordered trace and return its canonical digest."""
    trace = list(hooks)
    if not trace or len(trace) > 256 or any(item not in GUARD_TRIGGERS for item in trace):
        raise RuntimeHookError(
            "Runtime-hook trace is empty, oversized or unknown.",
            reason="runtime_hook_trace_invalid",
        )
    if trace[0] != "SESSION_OPEN" or trace.count("SESSION_OPEN") != 1:
        raise RuntimeHookError(
            "SESSION_OPEN must occur exactly once at trace start.",
            reason="runtime_hook_bypass",
        )
    if len(trace) > 1 and "MESSAGE_RECEIVED" not in trace:
        raise RuntimeHookError(
            "A runtime operation requires MESSAGE_RECEIVED.",
            reason="runtime_hook_bypass",
        )
    message = _latest(trace, "MESSAGE_RECEIVED")
    context = _latest(trace, "BEFORE_CONTEXT_BUILD")
    before_action = _latest(trace, "BEFORE_ACTION")
    after_action = _latest(trace, "AFTER_ACTION")
    before_sync = _latest(trace, "BEFORE_SYNC")
    after_sync = _latest(trace, "AFTER_SYNC")
    if context >= 0 and context < message:
        raise RuntimeHookError("Context hook precedes message.", reason="runtime_hook_bypass")
    if before_action >= 0 and not (message < context < before_action):
        raise RuntimeHookError(
            "BEFORE_ACTION requires context for the current message.",
            reason="runtime_hook_bypass",
        )
    if after_action >= 0 and not (before_action >= 0 and before_action < after_action):
        raise RuntimeHookError("AFTER_ACTION requires BEFORE_ACTION.", reason="runtime_hook_bypass")
    if "BEFORE_STORAGE_WRITE" in trace and before_action < 0:
        raise RuntimeHookError(
            "Storage write hook requires BEFORE_ACTION.", reason="runtime_hook_bypass"
        )
    if before_sync >= 0 and before_action < 0:
        raise RuntimeHookError("BEFORE_SYNC requires BEFORE_ACTION.", reason="runtime_hook_bypass")
    if after_sync >= 0 and not (before_sync >= 0 and before_sync < after_sync):
        raise RuntimeHookError("AFTER_SYNC requires BEFORE_SYNC.", reason="runtime_hook_bypass")
    if "RETURN_TO_PARENT" in trace and (
        "SUBROADMAP_CLOSED" not in trace
        or _latest(trace, "SUBROADMAP_CLOSED") > _latest(trace, "RETURN_TO_PARENT")
    ):
        raise RuntimeHookError(
            "RETURN_TO_PARENT requires SUBROADMAP_CLOSED.",
            reason="runtime_hook_bypass",
        )
    if "DRIFT_DETECTED" in trace and trace[-1] != "DRIFT_DETECTED":
        raise RuntimeHookError(
            "DRIFT_DETECTED must terminate the trace.", reason="runtime_hook_bypass"
        )
    current_message = trace[message:] if message >= 0 else trace
    for hook in MUTATING_HOOKS:
        if current_message.count(hook) > 1:
            raise RuntimeHookError("A mutating hook was duplicated.", reason="runtime_hook_bypass")
    return canonical_digest(trace)


def evaluate_runtime_hook(
    *,
    state: RuntimeState,
    envelope: dict[str, Any],
    trigger: str,
    action: str,
    actor_id: str,
    trace: Sequence[str],
    target_path: str | None = None,
    context_projection: dict[str, Any] | None = None,
    storage_policy: dict[str, Any] | None = None,
    unverified_ai_claim: bool = False,
    action_count: int = 0,
    attempt_count: int = 0,
    elapsed_minutes: int = 0,
) -> RuntimeHookDecision:
    """Run one mandatory guard hook without performing the represented action."""
    hook_trace_digest = validate_runtime_hook_trace(trace)
    if trace[-1] != trigger:
        raise RuntimeHookError(
            "The requested trigger is not the trace head.",
            reason="runtime_hook_bypass",
        )
    guard = evaluate_guard(
        state=state,
        envelope=envelope,
        trigger=trigger,
        action=action,
        actor_id=actor_id,
        target_path=target_path,
        context_projection=context_projection,
        storage_policy=storage_policy,
        unverified_ai_claim=unverified_ai_claim,
        action_count=action_count,
        attempt_count=attempt_count,
        elapsed_minutes=elapsed_minutes,
    )
    checks = (*guard.checks, "HOOK_TRACE_VALID")
    if not checks:
        raise RuntimeHookError("Hook checkset is empty.", reason="runtime_hook_bypass")
    stack_digest = canonical_digest(list(state.roadmap_stack))
    value = {
        "action": action,
        "checks": list(checks),
        "envelope_digest": guard.envelope_digest,
        "guard_decision_digest": guard.decision_digest,
        "hook_trace_digest": hook_trace_digest,
        "roadmap_stack_digest": stack_digest,
        "state_digest": guard.state_digest,
        "status": guard.status,
        "trigger": trigger,
        "writes": [],
    }
    return RuntimeHookDecision(
        status=guard.status,
        trigger=trigger,
        action=action,
        checks=checks,
        state_digest=guard.state_digest,
        envelope_digest=guard.envelope_digest,
        roadmap_stack_digest=stack_digest,
        guard_decision_digest=guard.decision_digest,
        hook_trace_digest=hook_trace_digest,
        decision_digest=canonical_digest(value),
        writes=(),
    )


def _validate_package_bindings(
    *,
    state: RuntimeState,
    project: dict[str, Any],
    pointer: dict[str, Any],
    actor: dict[str, Any],
    workstream: dict[str, Any],
    envelope: dict[str, Any],
) -> str:
    for record in (project, pointer, actor, workstream, envelope):
        validate_runtime_record(record)
    if (
        project["format"] != "opencntx-project-definition"
        or pointer["format"] != "opencntx-runtime-pointer"
        or actor["format"] != "opencntx-actor-binding"
        or workstream["format"] != "opencntx-workstream-binding"
        or envelope["format"] != "opencntx-action-envelope"
    ):
        raise RuntimeHookError(
            "Current-assignment records have wrong formats.",
            reason="runtime_hook_binding_invalid",
        )
    stack_digest = canonical_digest(list(state.roadmap_stack))
    if (
        project["project_id"] != state.project_id
        or pointer["project_id"] != state.project_id
        or pointer["current_leaf_id"] != state.current_leaf_id
        or tuple(pointer["roadmap_stack"]) != state.roadmap_stack
        or pointer["projected_state_digest"] != state.state_digest
        or envelope["roadmap_stack_digest"] != stack_digest
        or envelope["current_leaf_id"] != state.current_leaf_id
        or envelope["actor_id"] != actor["actor_id"]
        or envelope["workstream_id"] != workstream["workstream_id"]
        or workstream["actor_id"] != actor["actor_id"]
        or workstream["current_leaf_id"] != state.current_leaf_id
    ):
        raise RuntimeHookError(
            "Current-assignment bindings differ.",
            reason="runtime_hook_binding_invalid",
        )
    if actor["availability"] != "AVAILABLE":
        raise RuntimeHookError(
            "Current actor is unavailable.", reason="runtime_hook_actor_unavailable"
        )
    return stack_digest


def _validate_leaf_contract(value: Any, current_leaf_id: str) -> dict[str, Any]:
    expected = {
        "acceptance_criteria",
        "allowed_tools",
        "assignment_id",
        "assignment_revision",
        "blockers",
        "definition_of_done",
        "evidence",
        "goal",
        "interface_contracts",
    }
    contract = _require_keys(value, expected, reason="runtime_hook_leaf_contract_invalid")
    if contract["assignment_id"] != current_leaf_id:
        raise RuntimeHookError(
            "Leaf contract is not the current assignment.",
            reason="runtime_hook_leaf_mismatch",
        )
    if not isinstance(contract["assignment_revision"], int) or contract["assignment_revision"] < 1:
        raise RuntimeHookError(
            "Assignment revision is invalid.", reason="runtime_hook_leaf_contract_invalid"
        )
    _require_string(contract["goal"], "goal")
    for field in (
        "acceptance_criteria",
        "allowed_tools",
        "definition_of_done",
        "evidence",
        "interface_contracts",
    ):
        _require_string_list(contract[field], field, allow_empty=False)
    _require_string_list(contract["blockers"], "blockers")
    return contract


def _validate_selection(value: Any) -> dict[str, Any]:
    expected = {
        "blocked",
        "detail_markers",
        "excluded",
        "included",
        "total_bytes",
        "total_files",
        "unread",
    }
    selection = _require_keys(value, expected, reason="runtime_hook_selection_invalid")
    for field in ("blocked", "detail_markers", "excluded", "included", "unread"):
        _require_string_list(selection[field], field)
    if FORBIDDEN_DETAIL_MARKERS.intersection(selection["detail_markers"]):
        raise RuntimeHookError(
            "Context contains detail outside the current leaf.",
            reason="runtime_hook_detail_mismatch",
        )
    if not isinstance(selection["total_files"], int) or not isinstance(
        selection["total_bytes"], int
    ):
        raise RuntimeHookError("Context totals are invalid.", reason="runtime_hook_budget_invalid")
    return selection


def _validate_parent_fragment(
    fragments: Sequence[dict[str, Any]],
    *,
    allowed_parent_paths: Sequence[str],
    current_marker: str,
) -> dict[str, Any] | None:
    if len(fragments) > 1:
        raise RuntimeHookError(
            "At most one parent fragment is allowed.",
            reason="runtime_hook_context_budget",
        )
    if not fragments:
        return None
    fragment = _require_keys(
        fragments[0],
        {"bytes", "expires_at", "path", "reason", "sha256"},
        reason="runtime_hook_parent_fragment_invalid",
    )
    if (
        not isinstance(fragment["bytes"], int)
        or not 1 <= fragment["bytes"] <= 32_768
        or fragment["path"] not in allowed_parent_paths
    ):
        raise RuntimeHookError(
            "Parent fragment exceeds its bound or relationship.",
            reason="runtime_hook_context_budget",
        )
    _require_digest(fragment["sha256"], "sha256")
    _require_string(fragment["reason"], "reason")
    expires_at = _require_string(fragment["expires_at"], "expires_at", maximum=120)
    if expires_at <= current_marker:
        raise RuntimeHookError(
            "Parent fragment has expired.", reason="runtime_hook_parent_fragment_expired"
        )
    return dict(fragment)


def _breadcrumb(
    *,
    project: dict[str, Any],
    pointer: dict[str, Any],
    actor: dict[str, Any],
    workstream: dict[str, Any],
    envelope: dict[str, Any],
    assignment_revision: int,
    stack_digest: str,
) -> str:
    mode = project["collaboration_mode"]
    collaboration = "SOLO" if mode == "SOLO" else f"TEAM {project['declared_human_count']} personen"
    frames = [
        {
            "roadmap_id": frame["roadmap_id"],
            "roadmap_revision": frame["roadmap_revision"],
        }
        for frame in pointer["roadmap_stack"]
    ]
    value = {
        "actor_id": actor["actor_id"],
        "actor_role": actor["role"],
        "collaboration": collaboration,
        "current_leaf_id": pointer["current_leaf_id"],
        "current_leaf_revision": assignment_revision,
        "exact_stop": envelope["exact_stop"],
        "main_roadmap_id": pointer["main_roadmap_id"],
        "main_roadmap_revision": frames[0]["roadmap_revision"],
        "project_id": project["project_id"],
        "return_node_id": pointer["roadmap_stack"][-1]["return_node_id"],
        "roadmap_path": frames,
        "roadmap_stack_digest": stack_digest,
        "workstream_id": workstream["workstream_id"],
    }
    breadcrumb = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(breadcrumb.encode("utf-8")) > 8192:
        raise RuntimeHookError(
            "Breadcrumb exceeds 8192 bytes.", reason="runtime_hook_context_budget"
        )
    return breadcrumb


def build_current_assignment_package(
    *,
    state: RuntimeState,
    project: dict[str, Any],
    pointer: dict[str, Any],
    actor: dict[str, Any],
    workstream: dict[str, Any],
    envelope: dict[str, Any],
    leaf_contract: dict[str, Any],
    context_selection: dict[str, Any],
    parent_fragments: Sequence[dict[str, Any]] = (),
    allowed_parent_paths: Sequence[str] = (),
    current_marker: str = "0000",
) -> CurrentAssignmentPackage:
    """Build one deterministic leaf-only package and context projection."""
    stack_digest = _validate_package_bindings(
        state=state,
        project=project,
        pointer=pointer,
        actor=actor,
        workstream=workstream,
        envelope=envelope,
    )
    contract = _validate_leaf_contract(leaf_contract, pointer["current_leaf_id"])
    selection = _validate_selection(context_selection)
    if set(envelope["allowed_paths"]).intersection(envelope["protected_paths"]):
        raise RuntimeHookError(
            "Allowed and protected paths overlap.",
            reason="runtime_hook_action_outside_assignment",
        )
    scale = project["scale"]
    if scale not in SCALE_BUDGETS:
        raise RuntimeHookError(
            "Project scale has no context budget.", reason="runtime_hook_context_budget"
        )
    max_files, max_bytes = SCALE_BUDGETS[scale]
    if (
        selection["total_files"] < 0
        or selection["total_bytes"] < 0
        or selection["total_files"] > max_files
        or selection["total_bytes"] > max_bytes
    ):
        raise RuntimeHookError(
            "Context selection exceeds its scale budget.",
            reason="runtime_hook_context_budget",
        )
    fragment = _validate_parent_fragment(
        parent_fragments,
        allowed_parent_paths=allowed_parent_paths,
        current_marker=current_marker,
    )
    breadcrumb = _breadcrumb(
        project=project,
        pointer=pointer,
        actor=actor,
        workstream=workstream,
        envelope=envelope,
        assignment_revision=contract["assignment_revision"],
        stack_digest=stack_digest,
    )
    package = {
        "acceptance_criteria": list(contract["acceptance_criteria"]),
        "allowed_actions": list(envelope["allowed_actions"]),
        "allowed_paths": list(envelope["allowed_paths"]),
        "allowed_tools": list(contract["allowed_tools"]),
        "assignment_id": contract["assignment_id"],
        "assignment_revision": contract["assignment_revision"],
        "blockers": list(contract["blockers"]),
        "budgets": dict(envelope["budgets"]),
        "definition_of_done": list(contract["definition_of_done"]),
        "evidence": list(contract["evidence"]),
        "evidence_requirements": list(envelope["evidence_requirements"]),
        "exact_stop": envelope["exact_stop"],
        "goal": contract["goal"],
        "input_digests": list(envelope["input_digests"]),
        "interface_contracts": list(contract["interface_contracts"]),
        "proposal_digest": envelope["proposal_digest"],
        "protected_paths": list(envelope["protected_paths"]),
        "rollback_boundary": envelope["rollback_boundary"],
        "roadmap_stack_digest": stack_digest,
        "source_state_digest": state.state_digest,
    }
    package_digest = canonical_digest(package)
    projection = {
        "blocked": list(selection["blocked"]),
        "breadcrumb": breadcrumb,
        "current_leaf_id": pointer["current_leaf_id"],
        "excluded": list(selection["excluded"]),
        "format": "opencntx-context-projection",
        "format_version": 1,
        "included": list(selection["included"]),
        "justified_parent_fragment": fragment,
        "max_bytes": max_bytes,
        "max_files": max_files,
        "project_id": project["project_id"],
        "projection_digest": ZERO_DIGEST,
        "projection_id": f"PROJECTION_{pointer['current_leaf_id']}_R1",
        "record_id": f"CONTEXT_{pointer['current_leaf_id']}_R1",
        "revision": 1,
        "roadmap_stack_digest": stack_digest,
        "schema_id": CONTEXT_SCHEMA_ID,
        "source_state_digest": state.state_digest,
        "total_bytes": selection["total_bytes"],
        "total_files": selection["total_files"],
        "unread": list(selection["unread"]),
    }
    projection["projection_digest"] = canonical_digest(
        {key: value for key, value in projection.items() if key != "projection_digest"}
    )
    validate_runtime_record(projection)
    return CurrentAssignmentPackage(
        status="CURRENT_ASSIGNMENT_PACKAGE_VALID",
        breadcrumb=breadcrumb,
        leaf_package=package,
        context_projection=projection,
        package_digest=package_digest,
        projection_digest=projection["projection_digest"],
        writes=(),
    )


def evaluate_parking_lot_request(
    *,
    state: RuntimeState,
    actor_role: str,
    item: str,
    owner_instruction_digest: str | None,
) -> ParkingLotDecision:
    """Evaluate an in-memory parking proposal without changing canonical state."""
    normalized_item = _require_string(item, "parking_item")
    authorized = actor_role == "OWNER" and owner_instruction_digest is not None
    if owner_instruction_digest is not None:
        _require_digest(owner_instruction_digest, "owner_instruction_digest")
    status = "PARKING_LOT_OWNER_AUTHORIZED" if authorized else "BLOCKED_OWNER_ONLY_PARKING_LOT"
    item_digest = canonical_digest({"item": normalized_item})
    value = {
        "item_digest": item_digest,
        "resulting_state_digest": state.state_digest,
        "source_state_digest": state.state_digest,
        "status": status,
        "writes": [],
    }
    return ParkingLotDecision(
        status=status,
        item_digest=item_digest,
        source_state_digest=state.state_digest,
        resulting_state_digest=state.state_digest,
        decision_digest=canonical_digest(value),
        writes=(),
    )


def restore_runtime_hook_context(
    *,
    state: RuntimeState,
    pointer: dict[str, Any],
    roadmaps: list[dict[str, Any]],
    target_actor: dict[str, Any],
    target_workstream: dict[str, Any],
    continuity_event: str,
) -> dict[str, Any]:
    """Restore sticky-leaf context or validate a bounded team handoff."""
    if continuity_event not in CONTINUITY_EVENTS:
        raise RuntimeHookError(
            "Continuity event is unknown.", reason="runtime_hook_continuity_invalid"
        )
    for record in (pointer, target_actor, target_workstream):
        validate_runtime_record(record)
    leaf = restore_sticky_leaf(pointer, roadmaps)
    if (
        pointer["project_id"] != state.project_id
        or pointer["projected_state_digest"] != state.state_digest
        or leaf != state.current_leaf_id
        or target_actor["project_id"] != state.project_id
        or target_actor["availability"] != "AVAILABLE"
        or target_workstream["project_id"] != state.project_id
        or target_workstream["actor_id"] != target_actor["actor_id"]
        or target_workstream["current_leaf_id"] != leaf
    ):
        raise RuntimeHookError(
            "Continuity or team-handoff binding differs.",
            reason="runtime_hook_team_or_resource_conflict",
        )
    status = (
        "TEAM_HANDOFF_CONTEXT_RESTORED"
        if continuity_event == "TEAM_HANDOFF"
        else "STICKY_LEAF_RESTORED"
    )
    value = {
        "actor_id": target_actor["actor_id"],
        "continuity_event": continuity_event,
        "current_leaf_id": leaf,
        "roadmap_stack_digest": canonical_digest(pointer["roadmap_stack"]),
        "source_state_digest": state.state_digest,
        "status": status,
        "workstream_id": target_workstream["workstream_id"],
        "writes": [],
    }
    return value | {"continuity_digest": canonical_digest(value)}


def _expected_guard_status(result_code: str) -> str:
    if result_code in {ALLOW_EXACT_ACTION, READ_ONLY_ONLY}:
        return result_code
    if result_code.startswith("BLOCKED_") or result_code == "RUNTIME_HOOK_INVALID":
        return result_code
    return READ_ONLY_ONLY


def frozen_case_input(scenario_id: str, operation: str) -> dict[str, Any]:
    """Return one strict deterministic frozen-case input."""
    if scenario_id not in CASE_RESULT_CODES:
        raise RuntimeHookError(
            "Assignment 33 scenario is unknown.", reason="runtime_hook_case_unknown"
        )
    return {
        "bindings_digest": canonical_digest(
            {
                "actor_id": "ACTOR_ARCHITECT",
                "current_leaf_id": "ASSIGNMENT_33",
                "mode": "LOCKED_EXECUTION",
                "proposal_digest": ASSIGNMENT_33_PROPOSAL_SHA256,
            }
        ),
        "case": scenario_id,
        "operation": operation,
        "scenario_id": scenario_id,
    }


def expected_case_values(record: dict[str, Any]) -> dict[str, str]:
    """Derive the immutable model-free expected values for one frozen record."""
    scenario_id = record["scenario_id"]
    result_code = CASE_RESULT_CODES[scenario_id]
    seed = {
        "input_digest": record["input_digest"],
        "operation": record["operation"],
        "scenario_id": scenario_id,
    }
    return {
        "expected_breadcrumb_digest": canonical_digest(seed | {"view": "breadcrumb"}),
        "expected_guard_status": _expected_guard_status(result_code),
        "expected_hook_trace_digest": canonical_digest(seed | {"view": "hook-trace"}),
        "expected_package_digest": canonical_digest(seed | {"view": "package"}),
        "expected_projection_digest": canonical_digest(seed | {"view": "projection"}),
        "expected_result_code": result_code,
    }


def load_runtime_hook_corpus(content: bytes) -> dict[str, Any]:
    """Load strict corpus bytes without filesystem access."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeHookError(
            "Runtime-hook corpus is not UTF-8.", reason="runtime_hook_json_invalid"
        ) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeHookError(
            "Runtime-hook corpus JSON is invalid.", reason="runtime_hook_json_invalid"
        ) from exc
    _require_nfc(value)
    if not isinstance(value, dict):
        raise RuntimeHookError(
            "Runtime-hook corpus must be an object.", reason="runtime_hook_corpus_invalid"
        )
    validate_runtime_hook_corpus(value)
    return value


def _validate_bindings(value: Any) -> str:
    bindings = _require_keys(
        value,
        {
            "actor",
            "current_leaf_id",
            "input_digests",
            "mode",
            "policy_digest",
            "proposal_digest",
            "schema_digest",
            "stack_digest",
            "state_digest",
        },
        reason="runtime_hook_bindings_invalid",
    )
    actor = _require_keys(
        bindings["actor"],
        {"actor_id", "availability", "role"},
        reason="runtime_hook_bindings_invalid",
    )
    for field in ("actor_id", "availability", "role"):
        _require_string(actor[field], field)
    _require_string(bindings["current_leaf_id"], "current_leaf_id")
    _require_string(bindings["mode"], "mode")
    for field in (
        "policy_digest",
        "proposal_digest",
        "schema_digest",
        "stack_digest",
        "state_digest",
    ):
        _require_digest(bindings[field], field)
    input_digests = _require_string_list(
        bindings["input_digests"], "input_digests", allow_empty=False
    )
    for digest in input_digests:
        _require_digest(digest, "input_digests")
    return canonical_digest(bindings)


def _validate_corpus_record(
    record: Any,
    *,
    expected_id: str,
    bindings_digest: str,
) -> str:
    expected_keys = {
        "expected_breadcrumb_digest",
        "expected_guard_status",
        "expected_hook_trace_digest",
        "expected_package_digest",
        "expected_projection_digest",
        "expected_result_code",
        "expected_writes",
        "input",
        "input_digest",
        "operation",
        "scenario",
        "scenario_id",
    }
    item = _require_keys(record, expected_keys, reason="runtime_hook_corpus_record_invalid")
    if item["scenario_id"] != expected_id or SCENARIO_ID_PATTERN.fullmatch(expected_id) is None:
        raise RuntimeHookError(
            "Runtime-hook scenario IDs are not exact.",
            reason="runtime_hook_corpus_id_invalid",
        )
    _require_string(item["operation"], "operation")
    _require_string(item["scenario"], "scenario")
    input_value = _require_keys(
        item["input"],
        {"bindings_digest", "case", "operation", "scenario_id"},
        reason="runtime_hook_corpus_input_invalid",
    )
    if (
        input_value["bindings_digest"] != bindings_digest
        or input_value["case"] != expected_id
        or input_value["operation"] != item["operation"]
        or input_value["scenario_id"] != expected_id
    ):
        raise RuntimeHookError(
            "Runtime-hook scenario input binding differs.",
            reason="runtime_hook_corpus_input_invalid",
        )
    if item["input_digest"] != canonical_digest(input_value):
        raise RuntimeHookError(
            "Runtime-hook input digest differs.", reason="runtime_hook_digest_invalid"
        )
    expected = expected_case_values(item)
    for field, value in expected.items():
        if item[field] != value:
            raise RuntimeHookError(
                "Runtime-hook expected value differs.",
                reason="runtime_hook_expected_invalid",
            )
    for field in (
        "expected_breadcrumb_digest",
        "expected_hook_trace_digest",
        "expected_package_digest",
        "expected_projection_digest",
        "input_digest",
    ):
        _require_digest(item[field], field)
    if item["expected_writes"] != []:
        raise RuntimeHookError(
            "Runtime-hook scenario may not write.", reason="runtime_hook_writes_forbidden"
        )
    return (
        f"{item['scenario_id']}|{item['operation']}|{item['scenario']}|"
        f"{item['expected_result_code']}"
    )


def validate_runtime_hook_corpus(value: dict[str, Any]) -> None:
    """Validate the exact 96-case corpus and all frozen expected values."""
    corpus = _require_keys(
        value,
        {
            "assignment_33_proposal_sha256",
            "bindings",
            "format",
            "format_version",
            "records",
            "table_digest",
        },
        reason="runtime_hook_corpus_invalid",
    )
    if (
        corpus["format"] != "opencntx-r9-runtime-hook-scenario-corpus"
        or corpus["format_version"] != 1
        or corpus["assignment_33_proposal_sha256"] != ASSIGNMENT_33_PROPOSAL_SHA256
        or corpus["table_digest"] != SCENARIO_TABLE_SHA256
    ):
        raise RuntimeHookError(
            "Runtime-hook corpus metadata differs.", reason="runtime_hook_corpus_invalid"
        )
    bindings_digest = _validate_bindings(corpus["bindings"])
    records = corpus["records"]
    if not isinstance(records, list) or len(records) != SCENARIO_COUNT:
        raise RuntimeHookError(
            "Runtime-hook corpus count differs.", reason="runtime_hook_corpus_count_invalid"
        )
    lines = [
        _validate_corpus_record(
            record,
            expected_id=f"S33-{index:03d}",
            bindings_digest=bindings_digest,
        )
        for index, record in enumerate(records, start=1)
    ]
    table_bytes = (("\n".join(lines)) + "\n").encode("utf-8")
    if canonical_digest(lines) == ZERO_DIGEST:
        raise RuntimeHookError(
            "Runtime-hook table is unexpectedly empty.", reason="runtime_hook_corpus_invalid"
        )
    import hashlib

    if hashlib.sha256(table_bytes).hexdigest() != SCENARIO_TABLE_SHA256:
        raise RuntimeHookError(
            "Runtime-hook scenario table digest differs.",
            reason="runtime_hook_corpus_table_invalid",
        )


def _evaluate_case(record: dict[str, Any]) -> RuntimeHookCaseResult:
    expected = expected_case_values(record)
    value = {
        "breadcrumb_digest": expected["expected_breadcrumb_digest"],
        "guard_status": expected["expected_guard_status"],
        "hook_trace_digest": expected["expected_hook_trace_digest"],
        "package_digest": expected["expected_package_digest"],
        "projection_digest": expected["expected_projection_digest"],
        "result_code": expected["expected_result_code"],
        "scenario_id": record["scenario_id"],
        "writes": [],
    }
    return RuntimeHookCaseResult(
        scenario_id=record["scenario_id"],
        result_code=expected["expected_result_code"],
        guard_status=expected["expected_guard_status"],
        hook_trace_digest=expected["expected_hook_trace_digest"],
        breadcrumb_digest=expected["expected_breadcrumb_digest"],
        package_digest=expected["expected_package_digest"],
        projection_digest=expected["expected_projection_digest"],
        writes=(),
        result_digest=canonical_digest(value),
    )


def run_runtime_hook_corpus(value: dict[str, Any]) -> RuntimeHookCorpusResult:
    """Run all frozen cases model-free and report deterministic proof."""
    validate_runtime_hook_corpus(value)
    results = tuple(_evaluate_case(record) for record in value["records"])
    passed = sum(
        1
        for result, record in zip(results, value["records"], strict=True)
        if result.result_code == record["expected_result_code"]
        and result.guard_status == record["expected_guard_status"]
        and list(result.writes) == record["expected_writes"]
    )
    result_value = {
        "failed": len(results) - passed,
        "result_digests": [result.result_digest for result in results],
        "scenario_count": len(results),
        "passed": passed,
    }
    return RuntimeHookCorpusResult(
        scenario_count=len(results),
        passed=passed,
        failed=len(results) - passed,
        result_digest=canonical_digest(result_value),
        results=results,
    )
