"""Bounded visual-intent and joint-review contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .continuity import _fail, _one_line, _value_digest

ROLE_ID = "VISUAL_ARTIST"
ROLE_LABELS = {"en": "Visual Artist", "nl": "VISUEEL ARTIST"}
VISUAL_INTENT_FORMAT = "opencntx-visual-intent"
VISUAL_REVIEW_FORMAT = "opencntx-visual-review"
MAX_REFINEMENT_ROUNDS = 3
MEDIA = frozenset({"DOCUMENT", "IMAGE", "REPORT", "TERMINAL", "WEB"})
AUTHORITY_STATES = frozenset({"APPROVED_INTERNAL", "OWNER_REQUIRED", "NOT_AUTHORIZED"})
HUMAN_REVIEW_STATES = frozenset({"APPROVED", "PENDING", "REJECTED"})
INTENT_FIELDS = frozenset(
    {
        "accessibility_targets",
        "authority_state",
        "constraints",
        "content_priority",
        "format",
        "format_version",
        "intent_digest",
        "max_refinement_rounds",
        "medium",
        "primary_message",
        "refinement_round",
        "required_states",
        "role_id",
        "surface_id",
        "user_task",
    }
)
REVIEW_FIELDS = frozenset(
    {
        "decision",
        "format",
        "format_version",
        "human_review_status",
        "intent_digest",
        "perfection_findings",
        "perfection_status",
        "refinement_round",
        "review_digest",
        "stop_reason",
        "surface_id",
        "visual_findings",
        "visual_status",
    }
)


def _bounded_lines(values: Sequence[str], field: str, *, maximum: int = 40) -> list[str]:
    if isinstance(values, (str, bytes)) or len(values) > maximum:
        raise _fail("visual_contract_invalid", f"{field} must be a bounded list.")
    result = [_one_line(value, field, 500) for value in values]
    if len(result) != len(set(result)):
        raise _fail("visual_contract_invalid", f"{field} contains duplicates.")
    return result


def build_visual_intent(
    *,
    surface_id: str,
    medium: str,
    user_task: str,
    primary_message: str,
    content_priority: Sequence[str],
    required_states: Sequence[str],
    constraints: Sequence[str],
    accessibility_targets: Sequence[str],
    authority_state: str = "APPROVED_INTERNAL",
    refinement_round: int = 0,
) -> dict[str, Any]:
    """Build one deterministic brief for an OPENCNTX-owned visual surface."""
    selected_medium = medium.upper()
    if selected_medium not in MEDIA or authority_state not in AUTHORITY_STATES:
        raise _fail("visual_contract_invalid", "Medium or authority state is invalid.")
    if not isinstance(refinement_round, int) or isinstance(refinement_round, bool):
        raise _fail("visual_contract_invalid", "Refinement round is invalid.")
    if not 0 <= refinement_round <= MAX_REFINEMENT_ROUNDS:
        raise _fail("visual_contract_invalid", "Refinement round exceeds the bounded limit.")
    value = {
        "format": VISUAL_INTENT_FORMAT,
        "format_version": 1,
        "role_id": ROLE_ID,
        "surface_id": _one_line(surface_id, "surface_id", 100),
        "medium": selected_medium,
        "user_task": _one_line(user_task, "user_task", 1_000),
        "primary_message": _one_line(primary_message, "primary_message", 500),
        "content_priority": _bounded_lines(content_priority, "content_priority"),
        "required_states": _bounded_lines(required_states, "required_states"),
        "constraints": _bounded_lines(constraints, "constraints"),
        "accessibility_targets": _bounded_lines(accessibility_targets, "accessibility_targets"),
        "authority_state": authority_state,
        "refinement_round": refinement_round,
        "max_refinement_rounds": MAX_REFINEMENT_ROUNDS,
    }
    return value | {"intent_digest": _value_digest(value)}


def validate_visual_intent(value: Mapping[str, object]) -> dict[str, Any]:
    """Reject an altered, incomplete, or unbounded visual brief."""
    if set(value) != INTENT_FIELDS:
        raise _fail("visual_contract_invalid", "Visual intent fields differ.")
    basis = {key: item for key, item in value.items() if key != "intent_digest"}
    if value.get("intent_digest") != _value_digest(basis):
        raise _fail("visual_contract_invalid", "Visual intent digest differs.")
    round_value = value.get("refinement_round")
    if not isinstance(round_value, int) or isinstance(round_value, bool):
        raise _fail("visual_contract_invalid", "Refinement round is invalid.")
    rebuilt = build_visual_intent(
        surface_id=str(value["surface_id"]),
        medium=str(value["medium"]),
        user_task=str(value["user_task"]),
        primary_message=str(value["primary_message"]),
        content_priority=value["content_priority"]
        if isinstance(value["content_priority"], list)
        else (),
        required_states=value["required_states"]
        if isinstance(value["required_states"], list)
        else (),
        constraints=value["constraints"] if isinstance(value["constraints"], list) else (),
        accessibility_targets=value["accessibility_targets"]
        if isinstance(value["accessibility_targets"], list)
        else (),
        authority_state=str(value["authority_state"]),
        refinement_round=round_value,
    )
    if rebuilt != dict(value):
        raise _fail("visual_contract_invalid", "Visual intent values differ.")
    return rebuilt


def build_visual_review(
    intent: Mapping[str, object],
    *,
    visual_findings: Sequence[str] = (),
    perfection_findings: Sequence[str] = (),
    human_review_status: str = "PENDING",
) -> dict[str, Any]:
    """Join visual judgment and bounded-perfection evidence without self-approval."""
    brief = validate_visual_intent(intent)
    if human_review_status not in HUMAN_REVIEW_STATES:
        raise _fail("visual_review_invalid", "Human review status is invalid.")
    visual = _bounded_lines(visual_findings, "visual_findings")
    perfection = _bounded_lines(perfection_findings, "perfection_findings")
    visual_status = "PASS" if not visual else "FAIL"
    perfection_status = "PASS" if not perfection else "FAIL"
    round_number = int(brief["refinement_round"])
    if visual_status == perfection_status == "PASS" and human_review_status == "APPROVED":
        decision, stop_reason = "COMPLETE", "DECLARED_CRITERIA_GREEN"
    elif visual_status == perfection_status == "PASS" and human_review_status == "PENDING":
        decision, stop_reason = "AWAITING_HUMAN_REVIEW", "HUMAN_VISUAL_REVIEW_REQUIRED"
    elif round_number < MAX_REFINEMENT_ROUNDS:
        decision, stop_reason = "REFINE", "DECLARED_CRITERIA_NOT_GREEN"
    else:
        decision, stop_reason = "BLOCKED", "REFINEMENT_LIMIT_REACHED"
    value = {
        "format": VISUAL_REVIEW_FORMAT,
        "format_version": 1,
        "surface_id": brief["surface_id"],
        "intent_digest": brief["intent_digest"],
        "refinement_round": round_number,
        "visual_status": visual_status,
        "perfection_status": perfection_status,
        "human_review_status": human_review_status,
        "visual_findings": visual,
        "perfection_findings": perfection,
        "decision": decision,
        "stop_reason": stop_reason,
    }
    return value | {"review_digest": _value_digest(value)}


def validate_visual_review(value: Mapping[str, object]) -> dict[str, Any]:
    """Validate one closed joint visual-review record."""
    if set(value) != REVIEW_FIELDS:
        raise _fail("visual_review_invalid", "Visual review fields differ.")
    basis = {key: item for key, item in value.items() if key != "review_digest"}
    if value.get("review_digest") != _value_digest(basis):
        raise _fail("visual_review_invalid", "Visual review digest differs.")
    return dict(value)
