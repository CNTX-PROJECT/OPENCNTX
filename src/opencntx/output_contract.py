"""Localized, provider-neutral human output compiled from durable state."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .continuity import _digest, _fail, _one_line, _value_digest, decide_finalization
from .human_interface import OUTPUT_PROFILES

METRIC_STATUSES = frozenset(
    {"OK", "SESSION_NOT_FOUND", "TOKEN_EVENT_NOT_FOUND", "PARSE_ERROR"}
)
NEXT_ACTION_STATES = frozenset(
    {
        "CONTINUE_AUTOMATICALLY",
        "OWNER_DECISION_REQUIRED",
        "EXTERNAL_ACTION_REQUIRED",
        "BLOCKED",
        "NO_FURTHER_ACTION",
    }
)
LABEL_KEYS = frozenset(
    {
        "roadmap",
        "now",
        "thereafter",
        "next_assignment",
        "chat",
        "tokens",
        "required_model",
        "unavailable",
    }
)
DEFAULT_LABELS = {
    "nl": {
        "roadmap": "Roadmap",
        "now": "Nu",
        "thereafter": "Daarna",
        "next_assignment": "Volgende opdracht",
        "chat": "Chat",
        "tokens": "Tokens",
        "required_model": "Vereist model",
        "unavailable": "niet betrouwbaar beschikbaar",
    },
    "en": {
        "roadmap": "Roadmap",
        "now": "Now",
        "thereafter": "Then",
        "next_assignment": "Next assignment",
        "chat": "Chat",
        "tokens": "Tokens",
        "required_model": "Required model",
        "unavailable": "not reliably available",
    },
}


def extract_bound_session_metrics(
    *,
    session_id: str,
    source_session_id: str,
    chat_bytes: int | None,
    records: Sequence[Mapping[str, object]],
    adapter: str = "nested-token-count-v1",
) -> dict[str, Any]:
    """Read exact metrics from one explicitly bound session record stream."""
    selected = _one_line(session_id, "session_id", 200)
    source = _one_line(source_session_id, "source_session_id", 200)
    if adapter != "nested-token-count-v1":
        raise _fail("output_metric_adapter_unknown", "Metric adapter is unsupported.")
    if chat_bytes is not None and (
        isinstance(chat_bytes, bool) or not isinstance(chat_bytes, int) or chat_bytes < 0
    ):
        raise _fail("output_metric_parse_error", "chat_bytes is invalid.")
    source_digest = _digest(
        (json.dumps(list(records), ensure_ascii=False, sort_keys=True, default=str) + "\n").encode(
            "utf-8"
        )
    )
    if selected != source:
        status = "SESSION_NOT_FOUND"
        tokens = None
        size = None
    else:
        size = None if chat_bytes is None else round(chat_bytes / 1_048_576, 2)
        token_events = [record for record in records if record.get("type") == "token_count"]
        if not token_events:
            status = "TOKEN_EVENT_NOT_FOUND"
            tokens = None
        else:
            newest = token_events[-1]
            try:
                payload = newest["payload"]
                if not isinstance(payload, Mapping):
                    raise TypeError
                info = payload["info"]
                if not isinstance(info, Mapping):
                    raise TypeError
                usage = info["total_token_usage"]
                if not isinstance(usage, Mapping):
                    raise TypeError
                value = usage["total_tokens"]
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise TypeError
                tokens = value
                status = "OK"
            except (KeyError, TypeError):
                tokens = None
                status = "PARSE_ERROR"
    result = {
        "format": "opencntx-session-footer-metrics",
        "format_version": 1,
        "adapter": adapter,
        "session_id": selected,
        "source_session_id": source,
        "status": status,
        "chat_megabytes": size,
        "total_tokens": tokens,
        "source_digest": source_digest,
    }
    return result | {"metrics_digest": _value_digest(result)}


def _labels(language: str, supplied: Mapping[str, object] | None) -> dict[str, str]:
    selected = language.lower()
    raw: Mapping[str, object] | None = DEFAULT_LABELS.get(selected)
    if raw is None:
        raw = supplied
    if raw is None or set(raw) != LABEL_KEYS:
        raise _fail("output_labels_missing", "A complete localized label set is required.")
    return {key: _one_line(raw[key], f"label.{key}", 60) for key in sorted(LABEL_KEYS)}


def _next_state(decision: str, *, external_action: bool) -> str:
    if external_action:
        return "EXTERNAL_ACTION_REQUIRED"
    return {
        "CONTINUE": "CONTINUE_AUTOMATICALLY",
        "REQUEST_OWNER": "OWNER_DECISION_REQUIRED",
        "BLOCKED": "BLOCKED",
        "RECONCILE_REQUIRED": "BLOCKED",
        "COMPLETE_ASSIGNMENT": "OWNER_DECISION_REQUIRED",
        "COMPLETE_ROADMAP": "NO_FURTHER_ACTION",
    }[decision]


def build_output_contract(
    *,
    execution_capsule: Mapping[str, object],
    roadmap_label: str,
    summary: str,
    language: str,
    metrics: Mapping[str, object],
    required_capability: str,
    reasoning_level: str,
    output_profile: str = "HUMAN_SIMPLE",
    labels: Mapping[str, object] | None = None,
    thereafter: str | None = None,
    exact_human_action: str | None = None,
    external_action: bool = False,
    uncertainty: str | None = None,
    duration: str | None = None,
    technical_details: Sequence[str] = (),
) -> dict[str, Any]:
    """Compile one closed output contract from a validated execution capsule."""
    decision = decide_finalization(execution_capsule)
    if decision["decision"] == "RECONCILE_REQUIRED" and decision["reason"] == "CAPSULE_INVALID":
        raise _fail("output_state_invalid", "Execution capsule is invalid.")
    if metrics.get("status") not in METRIC_STATUSES:
        raise _fail("output_metrics_invalid", "Metrics status is invalid.")
    metrics_basis = {key: value for key, value in metrics.items() if key != "metrics_digest"}
    if metrics.get("metrics_digest") != _value_digest(metrics_basis):
        raise _fail("output_metrics_invalid", "Metrics digest differs.")
    profile = output_profile.upper()
    if profile not in OUTPUT_PROFILES:
        raise _fail("human_output_profile_invalid", "Output profile is invalid.")
    next_state = _next_state(str(decision["decision"]), external_action=external_action)
    action = (
        None
        if exact_human_action is None
        else _one_line(exact_human_action, "exact_human_action", 500)
    )
    requires_action = next_state in {"OWNER_DECISION_REQUIRED", "EXTERNAL_ACTION_REQUIRED"}
    if requires_action != (action is not None):
        raise _fail("output_action_invalid", "Exact human action does not match terminal state.")
    if technical_details and profile != "TECHNICAL_DETAILED":
        raise _fail("human_output_profile_invalid", "Technical detail requires explicit profile.")
    details = [_one_line(item, "technical_detail", 500) for item in technical_details]
    localized = _labels(language, labels)
    value = {
        "format": "opencntx-human-output",
        "format_version": 1,
        "language": language.lower(),
        "profile": profile,
        "summary": _one_line(summary, "summary", 2_000),
        "uncertainty": None if uncertainty is None else _one_line(uncertainty, "uncertainty", 500),
        "duration": None if duration is None else _one_line(duration, "duration", 200),
        "roadmap": _one_line(roadmap_label, "roadmap_label", 500),
        "current_assignment": execution_capsule.get("current_assignment"),
        "assignment_status": execution_capsule.get("assignment_status"),
        "thereafter": None if thereafter is None else _one_line(thereafter, "thereafter", 500),
        "next_assignment": execution_capsule.get("next_assignment_after_completion"),
        "next_action_state": next_state,
        "exact_human_action": action,
        "metrics": dict(metrics),
        "required_capability": _one_line(required_capability, "required_capability", 120),
        "reasoning_level": _one_line(reasoning_level, "reasoning_level", 60),
        "labels": localized,
        "technical_details": details,
        "state_digest": execution_capsule.get("state_digest"),
        "evidence_digest": execution_capsule.get("evidence_digest"),
        "execution_capsule_digest": execution_capsule.get("capsule_digest"),
        "decision_digest": decision["decision_digest"],
        "authority_changed": False,
    }
    return value | {"output_digest": _value_digest(value)}


def _number(value: float, language: str) -> str:
    if isinstance(value, int):
        rendered = f"{value:,}"
    else:
        rendered = f"{value:,.2f}"
    if language == "nl":
        rendered = rendered.replace(",", "_").replace(".", ",").replace("_", ".")
    return rendered


def render_output(value: Mapping[str, object]) -> str:
    """Render the quiet footer shape; the contract remains the source of truth."""
    basis = {key: item for key, item in value.items() if key != "output_digest"}
    if value.get("format") != "opencntx-human-output" or value.get("output_digest") != _value_digest(basis):
        raise _fail("output_contract_invalid", "Output contract differs from its digest.")
    labels = value["labels"]
    metrics = value["metrics"]
    if not isinstance(labels, Mapping) or not isinstance(metrics, Mapping):
        raise _fail("output_contract_invalid", "Output labels or metrics are invalid.")
    body = [str(value["summary"])]
    if value.get("uncertainty") is not None:
        body.append(str(value["uncertainty"]))
    if value.get("duration") is not None:
        body.append(str(value["duration"]))
    technical_details = value.get("technical_details")
    if not isinstance(technical_details, list):
        raise _fail("output_contract_invalid", "Technical details are invalid.")
    for detail in technical_details:
        body.append(f"- {detail}")
    action = value.get("exact_human_action")
    if action is not None:
        body.extend(["", "```text", str(action), "```"])
    roadmap = [f"**{labels['roadmap']}:** {value['roadmap']}"]
    if value.get("current_assignment") is not None:
        roadmap.append(
            f"**{labels['now']}:** {value['current_assignment']} — {value['assignment_status']}"
        )
    if value.get("thereafter") is not None:
        roadmap.append(f"**{labels['thereafter']}:** {value['thereafter']}")
    if value.get("next_assignment") is not None:
        roadmap.append(
            f"**{labels['next_assignment']}:** {value['next_assignment']} — {value['next_action_state']}"
        )
    language = str(value["language"])
    unavailable = str(labels["unavailable"])
    chat = metrics.get("chat_megabytes")
    tokens = metrics.get("total_tokens")
    chat_text = unavailable if chat is None else f"{_number(chat, language)} MB"
    token_text = unavailable if tokens is None else _number(tokens, language)
    metric_line = (
        f"**{labels['chat']}:** {chat_text}  |  **{labels['tokens']}:** {token_text}  |  "
        f"**{labels['required_model']}:** {value['required_capability']} - {value['reasoning_level']}"
    )
    return "\n".join([*body, "", "", "---", "", *roadmap, "", "---", "", metric_line, ""])
