"""Mandatory fail-closed Roadmap Guard for the isolated R9 foundation."""

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
    if not value or "\\" in value:
        raise RoadmapGuardError(
            "Action target is not portable.", reason="roadmap_guard_path_invalid"
        )
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise RoadmapGuardError(
            "Action target is not portable.", reason="roadmap_guard_path_invalid"
        )
    return pure.as_posix()


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
