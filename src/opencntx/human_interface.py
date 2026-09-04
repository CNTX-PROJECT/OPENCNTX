"""Human-language intent contracts and explicit presentation profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .continuity import _fail, _one_line, _value_digest

INTENT_FORMAT = "opencntx-human-intent"
OUTPUT_PROFILES = frozenset({"HUMAN_SIMPLE", "TECHNICAL_DETAILED"})
PROFILE_SCOPES = frozenset({"RESPONSE", "SESSION", "PROJECT"})
AUTHORITY_STATES = frozenset({"APPROVED", "OWNER_REQUIRED", "NOT_AUTHORIZED"})
INTENT_FIELDS = frozenset(
    {
        "format",
        "format_version",
        "language",
        "human_intent",
        "goal",
        "scope",
        "exclusions",
        "constraints",
        "authority_state",
        "risks",
        "definition_of_done",
        "next_internal_action",
        "missing_material_decision",
        "intent_digest",
    }
)


def _lines(values: Sequence[str], field: str, *, maximum: int = 50) -> list[str]:
    if isinstance(values, (str, bytes)) or len(values) > maximum:
        raise _fail("human_intent_invalid", f"{field} must be a bounded list.")
    lines = [_one_line(value, field, 500) for value in values]
    if len(lines) != len(set(lines)):
        raise _fail("human_intent_invalid", f"{field} contains duplicates.")
    return lines


def build_intent_contract(
    *,
    human_intent: str,
    language: str,
    goal: str,
    scope: Sequence[str],
    exclusions: Sequence[str],
    constraints: Sequence[str],
    authority_state: str,
    risks: Sequence[str],
    definition_of_done: Sequence[str],
    next_internal_action: str,
    missing_material_decision: str | None = None,
) -> dict[str, Any]:
    """Bind original human language to a host-derived technical interpretation."""
    source = human_intent.strip()
    if not source or len(source) > 32_768:
        raise _fail("human_intent_invalid", "human_intent is empty or too large.")
    selected_language = _one_line(language, "language", 35).lower()
    if authority_state not in AUTHORITY_STATES:
        raise _fail("human_intent_invalid", "authority_state is invalid.")
    missing = (
        None
        if missing_material_decision is None
        else _one_line(missing_material_decision, "missing_material_decision", 500)
    )
    if authority_state == "OWNER_REQUIRED" and missing is None:
        raise _fail("human_intent_invalid", "A missing OWNER decision must be named.")
    if authority_state != "OWNER_REQUIRED" and missing is not None:
        raise _fail("human_intent_invalid", "A missing decision conflicts with authority state.")
    value = {
        "format": INTENT_FORMAT,
        "format_version": 1,
        "language": selected_language,
        "human_intent": source,
        "goal": _one_line(goal, "goal", 1_000),
        "scope": _lines(scope, "scope"),
        "exclusions": _lines(exclusions, "exclusions"),
        "constraints": _lines(constraints, "constraints"),
        "authority_state": authority_state,
        "risks": _lines(risks, "risks"),
        "definition_of_done": _lines(definition_of_done, "definition_of_done"),
        "next_internal_action": _one_line(next_internal_action, "next_internal_action", 500),
        "missing_material_decision": missing,
    }
    return value | {"intent_digest": _value_digest(value)}


def validate_intent_contract(value: Mapping[str, object]) -> dict[str, Any]:
    """Reject altered, incomplete, or structurally ambiguous intent contracts."""
    if set(value) != INTENT_FIELDS:
        raise _fail("human_intent_invalid", "Intent contract fields differ.")
    basis = {key: item for key, item in value.items() if key != "intent_digest"}
    if (
        value.get("format") != INTENT_FORMAT
        or value.get("format_version") != 1
        or value.get("intent_digest") != _value_digest(basis)
    ):
        raise _fail("human_intent_invalid", "Intent contract digest or format differs.")
    rebuilt = build_intent_contract(
        human_intent=str(value["human_intent"]),
        language=str(value["language"]),
        goal=str(value["goal"]),
        scope=value["scope"] if isinstance(value["scope"], list) else (),
        exclusions=value["exclusions"] if isinstance(value["exclusions"], list) else (),
        constraints=value["constraints"] if isinstance(value["constraints"], list) else (),
        authority_state=str(value["authority_state"]),
        risks=value["risks"] if isinstance(value["risks"], list) else (),
        definition_of_done=(
            value["definition_of_done"]
            if isinstance(value["definition_of_done"], list)
            else ()
        ),
        next_internal_action=str(value["next_internal_action"]),
        missing_material_decision=(
            value["missing_material_decision"]
            if isinstance(value["missing_material_decision"], str)
            else None
        ),
    )
    if rebuilt != dict(value):
        raise _fail("human_intent_invalid", "Intent contract values differ.")
    return rebuilt


def intent_readback(value: Mapping[str, object]) -> dict[str, Any]:
    """Return the bounded semantic fields a human-facing host must preserve."""
    contract = validate_intent_contract(value)
    projection = {
        "format": "opencntx-human-intent-readback",
        "format_version": 1,
        "language": contract["language"],
        "goal": contract["goal"],
        "scope": contract["scope"],
        "exclusions": contract["exclusions"],
        "authority_state": contract["authority_state"],
        "definition_of_done": contract["definition_of_done"],
        "next_internal_action": contract["next_internal_action"],
        "missing_material_decision": contract["missing_material_decision"],
        "intent_digest": contract["intent_digest"],
    }
    return projection | {"readback_digest": _value_digest(projection)}


def select_output_profile(profile: str = "HUMAN_SIMPLE", *, scope: str = "RESPONSE") -> dict[str, Any]:
    """Record one explicit presentation choice without changing authority or state."""
    selected = profile.upper()
    selected_scope = scope.upper()
    if selected not in OUTPUT_PROFILES or selected_scope not in PROFILE_SCOPES:
        raise _fail("human_output_profile_invalid", "Output profile or scope is invalid.")
    value = {
        "format": "opencntx-output-profile-selection",
        "format_version": 1,
        "profile": selected,
        "scope": selected_scope,
        "state_changed": False,
        "authority_changed": False,
    }
    return value | {"selection_digest": _value_digest(value)}
