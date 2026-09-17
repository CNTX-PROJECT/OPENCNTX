"""Negotiated presentation adapters; legacy footer and visual contracts stay intact."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .knowledge import (
    KnowledgeError,
    _canonical_json,
    _digest,
    _format_host_chat,
    _format_host_tokens,
    _host_digest,
    _text,
    make_footer_contract,
    render_footer,
)

HOST_FORMAT = "ocx-footer-host-envelope-v2"
HOST_FIELDS = frozenset(
    {
        "format",
        "format_version",
        "session_id",
        "context_generation",
        "source_digest",
        "metrics",
        "proposal",
        "envelope_digest",
    }
)
METRICS = frozenset({"chat_bytes", "total_tokens", "model", "reasoning"})


def validate_host_presentation(
    envelope: Mapping[str, Any], *, session_id: str, context_generation: str, source_digest: str
) -> dict[str, Any]:
    """Validate a closed v2 envelope against the caller's current context binding."""
    if set(envelope) != HOST_FIELDS:
        raise KnowledgeError("Presentation envelope fields differ from closed v2.")
    if (
        envelope["format"] != HOST_FORMAT
        or type(envelope["format_version"]) is not int
        or envelope["format_version"] != 2
    ):
        raise KnowledgeError("Presentation envelope version is unsupported.")
    if (envelope["session_id"], envelope["context_generation"], envelope["source_digest"]) != (
        session_id,
        context_generation,
        source_digest,
    ):
        raise KnowledgeError("Presentation telemetry belongs to another context or source.")
    _text(session_id, "session_id", 256)
    _text(context_generation, "context_generation", 256)
    _host_digest(source_digest, "source_digest")
    basis = {key: value for key, value in envelope.items() if key != "envelope_digest"}
    if envelope["envelope_digest"] != _digest(_canonical_json(basis)):
        raise KnowledgeError("Presentation envelope digest differs.")
    metrics = envelope["metrics"]
    if not isinstance(metrics, dict) or set(metrics) != METRICS:
        raise KnowledgeError("Presentation metric fields differ.")
    for name, metric in metrics.items():
        if not isinstance(metric, dict) or set(metric) != {"value", "source", "measured_at"}:
            raise KnowledgeError("Presentation metric provenance is invalid.")
        value = metric["value"]
        if value is None:
            if metric["source"] is not None or metric["measured_at"] is not None:
                raise KnowledgeError("Unavailable metrics must have unavailable provenance.")
            continue
        if name in {"chat_bytes", "total_tokens"}:
            if type(value) is not int or value < 0:
                raise KnowledgeError("Measured counters must be non-negative integers.")
        else:
            _text(value, name, 200)
        _text(metric["source"], "metric source", 256)
        try:
            measured_at = datetime.fromisoformat(metric["measured_at"])
        except (TypeError, ValueError) as exc:
            raise KnowledgeError("Metric timestamp is invalid.") from exc
        if measured_at.tzinfo is None:
            raise KnowledgeError("Metric timestamp must include its timezone.")
    if envelope["proposal"] is not None:
        _text(envelope["proposal"], "proposal", 200)
    return dict(envelope)


def presentation_footer(
    envelope: Mapping[str, Any],
    *,
    session_id: str,
    context_generation: str,
    source_digest: str,
    locale: str = "en",
    output_kind: str = "text",
    profile: str = "commonmark",
    task_note: str | None = None,
    status: str | None = None,
    now: str | None = None,
    thereafter: str | None = None,
) -> str:
    """Render partial measured telemetry; structured deliveries never receive prose."""
    if output_kind not in {"text", "json", "tool", "code"} or locale != "en":
        raise KnowledgeError("Presentation output kind or locale is unsupported.")
    valid = validate_host_presentation(
        envelope,
        session_id=session_id,
        context_generation=context_generation,
        source_digest=source_digest,
    )
    if output_kind != "text":
        return ""
    values = {name: metric["value"] for name, metric in valid["metrics"].items()}
    unknown = "unknown"
    unavailable = "not measured"
    model = str(values["model"] or unknown)
    if values["reasoning"] is not None:
        model += "/" + str(values["reasoning"])
    contract = make_footer_contract(
        task_note=task_note,
        status=status or unknown,
        now=now or unknown,
        thereafter=thereafter or unknown,
        chat=_format_host_chat(values["chat_bytes"] / 1_000_000)
        if values["chat_bytes"] is not None
        else unavailable,
        tokens=_format_host_tokens(values["total_tokens"])
        if values["total_tokens"] is not None
        else unavailable,
        model=model,
        proposal=valid["proposal"] or "not specified",
        profile=profile,
    )
    return render_footer(contract)


def append_footer_once(body: str, footer: str) -> str:
    """Idempotently append one already validated human-facing footer."""
    if not footer or body.rstrip().endswith(footer.rstrip()):
        return body
    return body.rstrip() + "\n\n" + footer


def visual_projection(
    intent: Mapping[str, object], *, graphical_preview: bool = False
) -> dict[str, Any]:
    """Project the original role and intent without fabricating a visual review."""
    from .visual_design import ROLE_ID, validate_visual_intent

    valid = validate_visual_intent(intent)
    basis = {
        "format": "ocx-visual-host-projection-v1",
        "format_version": 1,
        "role_id": ROLE_ID,
        "intent_digest": valid["intent_digest"],
        "mode": "PREVIEW_REQUIRED" if graphical_preview else "TEXT_FALLBACK",
        "visual_inspection_performed": False,
        "text": f"{valid['primary_message']}\n\n"
        + "\n".join(f"- {item}" for item in valid["content_priority"]),
    }
    return basis | {"projection_digest": _digest(_canonical_json(basis))}
