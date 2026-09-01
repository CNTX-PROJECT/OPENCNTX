"""Test-only historical guard for the frozen R9 conformance corpus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from .project_runtime import RuntimeState
from .runtime_contracts import canonical_digest, validate_runtime_record

GUARD_TRIGGERS = {
    "SESSION_OPEN",
    "MESSAGE_RECEIVED",
    "BEFORE_CONTEXT_BUILD",
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
    "DRIFT_DETECTED",
}

INTAKE_GUARD_TRIGGERS = {
    "SESSION_OPEN",
    "MESSAGE_RECEIVED",
    "BEFORE_CONTEXT_BUILD",
    "BEFORE_ACTION",
    "AFTER_ACTION",
    "DRIFT_DETECTED",
}
INTAKE_READ_ACTIONS = {
    "read-control",
    "read-metadata",
    "read-owner-approved-text",
}

ALLOW_EXACT_ACTION = "ALLOW_EXACT_ACTION"
READ_ONLY_ONLY = "READ_ONLY_ONLY"


class RoadmapGuardError(ValueError):
    """A malformed guard request, distinct from a normal blocked decision."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.code = reason


@dataclass(frozen=True)
class GuardDecision:
    status: str
    trigger: str
    action: str
    checks: tuple[str, ...]
    state_digest: str
    envelope_digest: str
    decision_digest: str


@dataclass(frozen=True)
class IntakeGuardDecision:
    """A pre-binding guard decision that can authorize read-only inspection only."""

    status: str
    trigger: str
    action: str
    target_path: str
    checks: tuple[str, ...]
    policy_digest: str
    decision_digest: str


def _decision(
    *,
    status: str,
    trigger: str,
    action: str,
    checks: list[str],
    state: RuntimeState,
    envelope: dict[str, Any],
) -> GuardDecision:
    if not checks:
        raise RoadmapGuardError("Guard checkset may not be empty.", reason="roadmap_guard_empty")
    envelope_digest = canonical_digest(envelope)
    value: dict[str, Any] = {
        "action": action,
        "checks": checks,
        "envelope_digest": envelope_digest,
        "state_digest": state.state_digest,
        "status": status,
        "trigger": trigger,
    }
    return GuardDecision(
        status=status,
        trigger=trigger,
        action=action,
        checks=tuple(checks),
        state_digest=state.state_digest,
        envelope_digest=envelope_digest,
        decision_digest=canonical_digest(value),
    )


def _blocked(
    status: str,
    *,
    trigger: str,
    action: str,
    checks: list[str],
    state: RuntimeState,
    envelope: dict[str, Any],
) -> GuardDecision:
    return _decision(
        status=status,
        trigger=trigger,
        action=action,
        checks=checks,
        state=state,
        envelope=envelope,
    )


def _portable_path(value: str) -> str:
    windows_absolute = len(value) >= 3 and value[1:3] == ":/"
    if not value or "\\" in value or windows_absolute:
        raise RoadmapGuardError(
            "Action target is not portable.", reason="roadmap_guard_path_invalid"
        )
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise RoadmapGuardError(
            "Action target is not portable.", reason="roadmap_guard_path_invalid"
        )
    return pure.as_posix()


def _intake_path_matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(f"{prefix}/")
    return path == pattern


def _openspec_path(path: str) -> bool:
    return any(
        "openspec" in part.lower().replace("-", "").replace("_", "")
        for part in PurePosixPath(path).parts
    )


def _intake_decision(
    *,
    status: str,
    trigger: str,
    action: str,
    target_path: str,
    checks: list[str],
    policy_digest: str,
) -> IntakeGuardDecision:
    if not checks:
        raise RoadmapGuardError(
            "Intake guard checkset may not be empty.", reason="roadmap_guard_empty"
        )
    value: dict[str, Any] = {
        "action": action,
        "checks": checks,
        "policy_digest": policy_digest,
        "status": status,
        "target_path": target_path,
        "trigger": trigger,
    }
    return IntakeGuardDecision(
        status=status,
        trigger=trigger,
        action=action,
        target_path=target_path,
        checks=tuple(checks),
        policy_digest=policy_digest,
        decision_digest=canonical_digest(value),
    )


def evaluate_intake_guard(
    *,
    trigger: str,
    action: str,
    target_path: str,
    allowed_paths: list[str],
    protected_paths: list[str] | None = None,
    inspection_actions: int = 0,
    inventory_records: int = 0,
    metadata_bytes: int = 0,
    elapsed_minutes: int = 0,
) -> IntakeGuardDecision:
    """Evaluate an unbound intake request without granting execution authority."""
    if trigger not in INTAKE_GUARD_TRIGGERS:
        raise RoadmapGuardError(
            "Unknown intake guard trigger.", reason="roadmap_guard_trigger_unknown"
        )
    if not isinstance(allowed_paths, list) or not allowed_paths:
        raise RoadmapGuardError(
            "Intake read allowlist must not be empty.", reason="roadmap_guard_envelope_invalid"
        )
    if any(
        type(value) is not int or value < 0
        for value in (
            inspection_actions,
            inventory_records,
            metadata_bytes,
            elapsed_minutes,
        )
    ):
        raise RoadmapGuardError(
            "Intake budget values must be non-negative integers.",
            reason="roadmap_guard_envelope_invalid",
        )
    target = _portable_path(target_path)
    allowed = sorted({_portable_path(value) for value in allowed_paths})
    protected = sorted({_portable_path(value) for value in (protected_paths or [])})
    policy = {
        "allowed_paths": allowed,
        "budgets": {
            "max_inspection_actions": 40,
            "max_inventory_records": 1_000,
            "max_metadata_bytes": 4 * 1024**2,
            "max_minutes": 30,
        },
        "mode": "INTAKE_PLANNING",
        "protected_paths": protected,
        "read_actions": sorted(INTAKE_READ_ACTIONS),
    }
    policy_digest = canonical_digest(policy)
    checks = ["INTAKE_TRIGGER_VALID", "INTAKE_POLICY_VALID"]
    if trigger == "DRIFT_DETECTED":
        return _intake_decision(
            status="BLOCKED_SNAPSHOT_DRIFT",
            trigger=trigger,
            action=action,
            target_path=target,
            checks=checks,
            policy_digest=policy_digest,
        )
    if action not in INTAKE_READ_ACTIONS:
        return _intake_decision(
            status="BLOCKED_INTAKE_MUTATION",
            trigger=trigger,
            action=action,
            target_path=target,
            checks=checks,
            policy_digest=policy_digest,
        )
    checks.append("INTAKE_ACTION_READ_ONLY")
    if (
        inspection_actions > 40
        or inventory_records > 1_000
        or metadata_bytes > 4 * 1024**2
        or elapsed_minutes > 30
    ):
        return _intake_decision(
            status="BLOCKED_INTAKE_BUDGET_EXCEEDED",
            trigger=trigger,
            action=action,
            target_path=target,
            checks=checks,
            policy_digest=policy_digest,
        )
    checks.append("INTAKE_BUDGET_VALID")
    if _openspec_path(target):
        return _intake_decision(
            status="BLOCKED_INTAKE_READ_SCOPE",
            trigger=trigger,
            action=action,
            target_path=target,
            checks=checks,
            policy_digest=policy_digest,
        )
    if any(_intake_path_matches(target, pattern) for pattern in protected) or not any(
        _intake_path_matches(target, pattern) for pattern in allowed
    ):
        return _intake_decision(
            status="BLOCKED_INTAKE_READ_SCOPE",
            trigger=trigger,
            action=action,
            target_path=target,
            checks=checks,
            policy_digest=policy_digest,
        )
    checks.extend(("INTAKE_TARGET_ALLOWED", "INTAKE_ZERO_MUTATION"))
    return _intake_decision(
        status=READ_ONLY_ONLY,
        trigger=trigger,
        action=action,
        target_path=target,
        checks=checks,
        policy_digest=policy_digest,
    )


def _check_context_projection(
    context_projection: dict[str, Any] | None,
    *,
    state: RuntimeState,
    envelope: dict[str, Any],
    trigger: str,
    action: str,
    checks: list[str],
    stack_digest: str,
) -> GuardDecision | None:
    if context_projection is None:
        return None
    validate_runtime_record(context_projection)
    if (
        context_projection["format"] != "opencntx-context-projection"
        or context_projection["current_leaf_id"] != state.current_leaf_id
        or context_projection["roadmap_stack_digest"] != stack_digest
        or context_projection["total_files"] > context_projection["max_files"]
        or context_projection["total_bytes"] > context_projection["max_bytes"]
    ):
        return _blocked(
            "BLOCKED_CONTEXT_BUDGET",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    forbidden_markers = {
        "FULL_MAIN_ROADMAP",
        "SIBLING_DETAIL",
        "FUTURE_DETAIL",
        "OTHER_TEAM_LEAF",
    }
    if forbidden_markers.intersection(context_projection["included"]):
        return _blocked(
            "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("CONTEXT_LEAF_ONLY")
    return None


def _check_storage_policy(
    storage_policy: dict[str, Any] | None,
    *,
    state: RuntimeState,
    envelope: dict[str, Any],
    trigger: str,
    action: str,
    checks: list[str],
) -> GuardDecision | None:
    if storage_policy is None:
        return None
    validate_runtime_record(storage_policy)
    if storage_policy["format"] != "opencntx-storage-policy" or (
        trigger in {"BEFORE_SYNC", "AFTER_SYNC"} and not storage_policy["private_git_sync_enabled"]
    ):
        return _blocked(
            "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("STORAGE_POLICY_VALID")
    return None


def _check_actor_and_claims(
    *,
    state: RuntimeState,
    envelope: dict[str, Any],
    trigger: str,
    action: str,
    actor_id: str,
    checks: list[str],
    unverified_ai_claim: bool,
) -> GuardDecision | None:
    actor = next((item for item in state.actors if item[0] == actor_id), None)
    if actor is None or actor[2] != "AVAILABLE" or envelope["actor_id"] != actor_id:
        return _blocked(
            "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("ACTOR_AVAILABLE")
    if state.conflicts:
        return _blocked(
            "BLOCKED_TEAM_OR_RESOURCE_CONFLICT",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("NO_TEAM_OR_RESOURCE_CONFLICT")
    if unverified_ai_claim:
        return _blocked(
            "BLOCKED_UNVERIFIED_AI_CLAIM",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("CLAIMS_VERIFIED")
    return None


def evaluate_guard(
    *,
    state: RuntimeState,
    envelope: dict[str, Any],
    trigger: str,
    action: str,
    actor_id: str,
    target_path: str | None = None,
    context_projection: dict[str, Any] | None = None,
    storage_policy: dict[str, Any] | None = None,
    unverified_ai_claim: bool = False,
    action_count: int = 0,
    attempt_count: int = 0,
    elapsed_minutes: int = 0,
) -> GuardDecision:
    if trigger not in GUARD_TRIGGERS:
        raise RoadmapGuardError(
            "Unknown Roadmap Guard trigger.", reason="roadmap_guard_trigger_unknown"
        )
    validate_runtime_record(envelope)
    if envelope["format"] != "opencntx-action-envelope":
        raise RoadmapGuardError(
            "Guard requires an action envelope.", reason="roadmap_guard_envelope_invalid"
        )
    checks: list[str] = ["TRIGGER_VALID", "ENVELOPE_VALID"]
    if state.status == "UNBOUND" or envelope["project_id"] != state.project_id:
        return _blocked(
            "BLOCKED_NO_PROJECT_BINDING",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("PROJECT_BOUND")
    if not state.roadmap_stack:
        return _blocked(
            "BLOCKED_NO_VALID_MAIN_ROADMAP",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("MAIN_ROADMAP_VALID")
    stack_digest = canonical_digest(list(state.roadmap_stack))
    if envelope["roadmap_stack_digest"] != stack_digest or len(state.roadmap_stack) > 8:
        return _blocked(
            "BLOCKED_NO_VALID_ROADMAP_STACK",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("ROADMAP_STACK_VALID")
    if state.current_leaf_id is None:
        return _blocked(
            "BLOCKED_NO_ACTIVE_ASSIGNMENT",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("CURRENT_LEAF_PRESENT")
    if envelope["current_leaf_id"] != state.current_leaf_id:
        return _blocked(
            "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("CURRENT_LEAF_MATCHES")
    actor_decision = _check_actor_and_claims(
        state=state,
        envelope=envelope,
        trigger=trigger,
        action=action,
        actor_id=actor_id,
        checks=checks,
        unverified_ai_claim=unverified_ai_claim,
    )
    if actor_decision is not None:
        return actor_decision
    budgets = envelope["budgets"]
    if (
        action_count >= budgets["max_actions"]
        or attempt_count >= budgets["max_attempts"]
        or elapsed_minutes >= budgets["max_minutes"]
    ):
        return _blocked(
            "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("EXECUTION_BUDGET_AVAILABLE")
    context_decision = _check_context_projection(
        context_projection,
        state=state,
        envelope=envelope,
        trigger=trigger,
        action=action,
        checks=checks,
        stack_digest=stack_digest,
    )
    if context_decision is not None:
        return context_decision
    storage_decision = _check_storage_policy(
        storage_policy,
        state=state,
        envelope=envelope,
        trigger=trigger,
        action=action,
        checks=checks,
    )
    if storage_decision is not None:
        return storage_decision
    if action not in envelope["allowed_actions"]:
        return _blocked(
            "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("ACTION_ALLOWED")
    if target_path is not None:
        target = _portable_path(target_path)
        if target in envelope["protected_paths"] or target not in envelope["allowed_paths"]:
            return _blocked(
                "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT",
                trigger=trigger,
                action=action,
                checks=checks,
                state=state,
                envelope=envelope,
            )
        checks.append("TARGET_ALLOWED")
    if trigger == "DRIFT_DETECTED":
        return _blocked(
            "BLOCKED_ROADMAP_DRIFT",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    if trigger == "RETURN_TO_PARENT" and state.mode != "RETURN_TO_PARENT":
        return _blocked(
            "BLOCKED_INVALID_RETURN_TO_PARENT",
            trigger=trigger,
            action=action,
            checks=checks,
            state=state,
            envelope=envelope,
        )
    checks.append("STOP_AND_ROLLBACK_KNOWN")
    status = READ_ONLY_ONLY if action.startswith("read-") else ALLOW_EXACT_ACTION
    return _decision(
        status=status,
        trigger=trigger,
        action=action,
        checks=checks,
        state=state,
        envelope=envelope,
    )
