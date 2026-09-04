"""Provider-neutral heartbeats, session handoff, and compact evidence."""

from __future__ import annotations

import gzip
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .continuity import (
    AUTHORITY,
    FINALIZATION_DECISIONS,
    _assignment,
    _capsule_from_loaded,
    _digest,
    _fail,
    _identifier,
    _load_store,
    _one_line,
    _pretty,
    _read_json,
    _value_digest,
    _write_atomic,
    _writer_lock,
    decide_finalization,
    store_path,
)
from .security import CONFIDENCE_HIGH, CONFIDENCE_WARNING, scan_text

MIB = 1_048_576
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
METRIC_FIELDS = frozenset(
    {
        "chat_bytes",
        "total_tokens",
        "context_percent",
        "tool_output_bytes",
        "response_latency_ms",
        "compaction_count",
        "failure_density",
    }
)
ROLLOVER_SIGNALS = frozenset(
    {"CONTINUE", "PREPARE_HANDOFF", "HANDOFF_NOW", "METRICS_UNAVAILABLE"}
)
HANDOFF_STATUSES = frozenset(
    {
        "RESUME_AUTOMATICALLY",
        "RECONCILE_REQUIRED",
        "WAIT_FOR_OWNER",
        "STOP_WITH_EVIDENCE",
    }
)


def _safe_number(value: object, field: str, *, maximum: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
        or float(value) > maximum
    ):
        raise _fail("continuity_session_metrics_invalid", f"{field} is outside its bound.")
    return float(value)


def normalize_session_metrics(metrics: Mapping[str, object]) -> dict[str, Any]:
    """Normalize optional provider measurements without changing project state."""
    unknown = set(metrics) - METRIC_FIELDS
    if unknown:
        raise _fail("continuity_session_metrics_invalid", "Session metrics contain unknown fields.")
    normalized: dict[str, int | float | None] = {field: None for field in METRIC_FIELDS}
    integer_fields = {
        "chat_bytes": 10 * 1024 * MIB,
        "total_tokens": 10_000_000_000,
        "tool_output_bytes": 10 * 1024 * MIB,
        "response_latency_ms": 86_400_000,
        "compaction_count": 1_000_000,
    }
    for field, maximum in integer_fields.items():
        value = metrics.get(field)
        if value is None:
            continue
        number = _safe_number(value, field, maximum=maximum)
        if not number.is_integer():
            raise _fail("continuity_session_metrics_invalid", f"{field} must be an integer.")
        normalized[field] = int(number)
    for field, maximum_value in {"context_percent": 100.0, "failure_density": 1.0}.items():
        value = metrics.get(field)
        if value is not None:
            normalized[field] = _safe_number(value, field, maximum=maximum_value)
    available = sorted(field for field, value in normalized.items() if value is not None)
    result = {
        "format": "opencntx-session-metrics",
        "format_version": 1,
        "available": available,
        "metrics": dict(sorted(normalized.items())),
    }
    return result | {"metrics_digest": _value_digest(result)}


def assess_session_rollover(metrics: Mapping[str, object]) -> dict[str, Any]:
    """Return an advisory rollover signal from whatever metrics are available."""
    normalized = normalize_session_metrics(metrics)
    values = normalized["metrics"]
    reasons: list[str] = []
    hard = (
        (values["chat_bytes"] is not None and values["chat_bytes"] >= 35 * MIB)
        or (values["context_percent"] is not None and values["context_percent"] >= 90)
        or (
            values["tool_output_bytes"] is not None
            and values["tool_output_bytes"] >= 16 * MIB
        )
    )
    soft = (
        (values["chat_bytes"] is not None and values["chat_bytes"] >= 30 * MIB)
        or (values["context_percent"] is not None and values["context_percent"] >= 75)
        or (
            values["tool_output_bytes"] is not None
            and values["tool_output_bytes"] >= 8 * MIB
        )
        or (values["response_latency_ms"] is not None and values["response_latency_ms"] >= 60_000)
        or (values["compaction_count"] is not None and values["compaction_count"] >= 2)
        or (values["failure_density"] is not None and values["failure_density"] >= 0.35)
    )
    if values["chat_bytes"] is not None and values["chat_bytes"] >= 30 * MIB:
        reasons.append("CHAT_SIZE")
    if values["context_percent"] is not None and values["context_percent"] >= 75:
        reasons.append("CONTEXT_PRESSURE")
    if values["tool_output_bytes"] is not None and values["tool_output_bytes"] >= 8 * MIB:
        reasons.append("TOOL_OUTPUT_VOLUME")
    if values["response_latency_ms"] is not None and values["response_latency_ms"] >= 60_000:
        reasons.append("LATENCY")
    if values["compaction_count"] is not None and values["compaction_count"] >= 2:
        reasons.append("COMPACTION")
    if values["failure_density"] is not None and values["failure_density"] >= 0.35:
        reasons.append("FAILURE_DENSITY")
    if not normalized["available"]:
        signal = "METRICS_UNAVAILABLE"
    elif hard:
        signal = "HANDOFF_NOW"
    elif soft:
        signal = "PREPARE_HANDOFF"
    else:
        signal = "CONTINUE"
    result = {
        "format": "opencntx-rollover-assessment",
        "format_version": 1,
        "signal": signal,
        "reasons": sorted(reasons),
        "metrics_digest": normalized["metrics_digest"],
        "state_changed": False,
    }
    return result | {"assessment_digest": _value_digest(result)}


def session_heartbeat(project_root: Path, *, elapsed_seconds: int) -> dict[str, Any]:
    """Project one compact heartbeat from freshly validated durable state."""
    if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, int) or elapsed_seconds < 0:
        raise _fail("continuity_heartbeat_invalid", "elapsed_seconds must be non-negative.")
    store, roadmap, events, state = _load_store(project_root)
    del store
    capsule = _capsule_from_loaded(roadmap, events, state)
    decision = decide_finalization(capsule)
    intervention = decision["decision"] in {
        "REQUEST_OWNER",
        "BLOCKED",
        "RECONCILE_REQUIRED",
    }
    result = {
        "format": "opencntx-session-heartbeat",
        "format_version": 1,
        "active_assignment": capsule["current_assignment"],
        "active_internal_task": capsule["current_internal_task"],
        "last_checkpoint": capsule["checkpoint_number"],
        "elapsed_seconds": elapsed_seconds,
        "intervention_required": intervention,
        "decision": decision["decision"],
        "state_digest": capsule["state_digest"],
        "evidence_digest": capsule["evidence_digest"],
    }
    return result | {"heartbeat_digest": _value_digest(result)}


def _safe_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or DIGEST_PATTERN.fullmatch(value) is None:
        raise _fail("continuity_session_handoff_invalid", f"{field} must be a SHA-256 digest.")
    return value


def _safe_lines(values: Sequence[str], field: str, *, maximum: int = 20) -> list[str]:
    if isinstance(values, (str, bytes)) or len(values) > maximum:
        raise _fail("continuity_session_handoff_invalid", f"{field} is not bounded.")
    lines = [_one_line(value, field, 500) for value in values]
    if len(lines) != len(set(lines)):
        raise _fail("continuity_session_handoff_invalid", f"{field} contains duplicates.")
    return lines


def _reject_secret_text(path: str, text: str) -> None:
    content = text.encode("utf-8")
    findings = scan_text(path=path, text=text, source_sha256=_digest(content))
    if any(item.confidence in {CONFIDENCE_HIGH, CONFIDENCE_WARNING} for item in findings):
        raise _fail("continuity_session_secret", "Session continuity content triggered the secret filter.")


def store_evidence_object(
    project_root: Path,
    *,
    content: bytes,
    summary: str,
    error_lines: Sequence[str] = (),
) -> dict[str, Any]:
    """Store one deduplicated gzip evidence object and return compact metadata."""
    if not isinstance(content, bytes) or not content or len(content) > 512 * MIB:
        raise _fail("continuity_evidence_object_invalid", "Evidence bytes are empty or too large.")
    short_summary = _one_line(summary, "summary", 500)
    errors = _safe_lines(error_lines, "error_lines")
    _reject_secret_text("evidence-summary", "\n".join([short_summary, *errors]))
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        decoded = None
    if decoded is not None:
        _reject_secret_text("evidence-object", decoded)
    digest = _digest(content)
    compressed = gzip.compress(content, compresslevel=9, mtime=0)
    store = store_path(project_root)
    with _writer_lock(store / ".operation.lock"):
        _load_store(project_root)
        object_path = store / "evidence-objects" / f"{digest}.gz"
        metadata_path = store / "evidence-objects" / f"{digest}.json"
        metadata = {
            "format": "opencntx-evidence-object",
            "format_version": 1,
            "sha256": digest,
            "bytes": len(content),
            "compressed_bytes": len(compressed),
            "compression": "gzip",
            "object_path": f"evidence-objects/{digest}.gz",
            "summary": short_summary,
            "error_lines": errors,
        }
        metadata["metadata_digest"] = _value_digest(metadata)
        if object_path.exists() or metadata_path.exists():
            if not object_path.is_file() or not metadata_path.is_file():
                raise _fail("continuity_evidence_object_conflict", "Evidence object is incomplete.")
            try:
                existing = gzip.decompress(object_path.read_bytes())
            except (OSError, gzip.BadGzipFile) as exc:
                raise _fail("continuity_evidence_object_invalid", "Evidence object cannot be read.") from exc
            prior = _read_json(metadata_path, failure_kind="continuity_evidence_object_invalid")
            prior_basis = {key: value for key, value in prior.items() if key != "metadata_digest"}
            if (
                existing != content
                or prior.get("sha256") != digest
                or prior.get("metadata_digest") != _value_digest(prior_basis)
            ):
                raise _fail("continuity_evidence_object_conflict", "Evidence digest has conflicting content.")
            return prior
        _write_atomic(object_path, compressed)
        try:
            _write_atomic(metadata_path, _pretty(metadata))
        except Exception:
            object_path.unlink(missing_ok=True)
            raise
    return metadata


def verify_evidence_object(project_root: Path, digest: str) -> dict[str, Any]:
    """Verify one compressed evidence object and its compact metadata."""
    selected = _safe_digest(digest, "digest")
    store = store_path(project_root)
    _load_store(project_root)
    metadata_path = store / "evidence-objects" / f"{selected}.json"
    object_path = store / "evidence-objects" / f"{selected}.gz"
    metadata = _read_json(metadata_path, failure_kind="continuity_evidence_object_invalid")
    basis = {key: value for key, value in metadata.items() if key != "metadata_digest"}
    try:
        compressed = object_path.read_bytes()
        content = gzip.decompress(compressed)
    except (OSError, gzip.BadGzipFile) as exc:
        raise _fail("continuity_evidence_object_invalid", "Evidence object cannot be read.") from exc
    valid = (
        metadata.get("format") == "opencntx-evidence-object"
        and metadata.get("format_version") == 1
        and metadata.get("sha256") == selected == _digest(content)
        and metadata.get("bytes") == len(content)
        and metadata.get("compressed_bytes") == len(compressed)
        and metadata.get("object_path") == f"evidence-objects/{selected}.gz"
        and metadata.get("metadata_digest") == _value_digest(basis)
    )
    if not valid:
        raise _fail("continuity_evidence_object_invalid", "Evidence metadata or bytes differ.")
    return metadata | {"verified": True}


def _provider_capabilities(values: Mapping[str, object]) -> dict[str, bool]:
    fields = {"can_create_target", "can_report_ready", "can_acknowledge"}
    if set(values) != fields or any(not isinstance(values[field], bool) for field in fields):
        raise _fail("continuity_session_handoff_invalid", "Provider capabilities are invalid.")
    return {field: bool(values[field]) for field in sorted(fields)}


def prepare_session_handoff(
    project_root: Path,
    *,
    handoff_id: str,
    source_part: str,
    target_part: str,
    provider_capabilities: Mapping[str, object],
    rollback_boundary: str,
    exclusions: Sequence[str] = (),
    evidence_object_digests: Sequence[str] = (),
) -> dict[str, Any]:
    """Atomically prepare one compact state-bound handoff before target creation."""
    selected_id = _identifier(handoff_id, "handoff_id")
    source = _one_line(source_part, "source_part", 120)
    target = _one_line(target_part, "target_part", 120)
    if source == target:
        raise _fail("continuity_session_handoff_invalid", "Source and target parts must differ.")
    capabilities = _provider_capabilities(provider_capabilities)
    boundary = _one_line(rollback_boundary, "rollback_boundary", 500)
    safe_exclusions = _safe_lines(exclusions, "exclusions")
    evidence_digests = [_safe_digest(value, "evidence_object_digest") for value in evidence_object_digests]
    if len(evidence_digests) > 50 or len(evidence_digests) != len(set(evidence_digests)):
        raise _fail("continuity_session_handoff_invalid", "Evidence references are invalid.")
    store = store_path(project_root)
    with _writer_lock(store / ".operation.lock"):
        store, roadmap, events, state = _load_store(project_root)
        evidence = [verify_evidence_object(project_root, value) for value in evidence_digests]
        capsule = _capsule_from_loaded(roadmap, events, state)
        current = state["current_assignment"]
        scope = [] if current is None else list(_assignment(roadmap, str(current))["touches"])
        authority = {
            "authority": AUTHORITY,
            "authority_state": capsule["authority_state"],
        }
        next_owner_gate = (
            "NONE"
            if capsule["authority_state"] == "APPROVED_AUTO_PILOT"
            else "REQUEST_EXACT_OWNER_DECISION"
        )
        creation = "CREATE_ONE_TARGET" if capabilities["can_create_target"] else "COPY_ACTION_REQUIRED"
        continuation_action = None if capabilities["can_create_target"] else f"OPEN HANDOFF {selected_id}"
        record = {
            "format": "opencntx-session-handoff",
            "format_version": 1,
            "handoff_id": selected_id,
            "project_id": roadmap["project_id"],
            "roadmap_id": roadmap["roadmap_id"],
            "roadmap_revision": capsule["roadmap_revision"],
            "source_part": source,
            "target_part": target,
            "current_assignment": capsule["current_assignment"],
            "current_internal_task": capsule["current_internal_task"],
            "assignment_status": capsule["assignment_status"],
            "next_internal_action": capsule["next_internal_action"],
            "next_owner_gate": next_owner_gate,
            "authority_digest": _value_digest(authority),
            "scope": scope,
            "exclusions": safe_exclusions,
            "recovery_round": capsule["recovery_round"],
            "rollback_boundary": boundary,
            "evidence_digest": capsule["evidence_digest"],
            "evidence_objects": [
                {
                    "sha256": item["sha256"],
                    "bytes": item["bytes"],
                    "summary": item["summary"],
                    "metadata_digest": item["metadata_digest"],
                }
                for item in evidence
            ],
            "state_digest": capsule["state_digest"],
            "execution_capsule_digest": capsule["capsule_digest"],
            "provider_capabilities": capabilities,
            "target_creation": creation,
            "continuation_action": continuation_action,
        }
        record["handoff_digest"] = _value_digest(record)
        content = _pretty(record)
        _reject_secret_text(f"session-handoffs/{selected_id}.json", content.decode("utf-8"))
        path = store / "session-handoffs" / f"{selected_id}.json"
        if path.exists():
            existing = _read_json(path, failure_kind="continuity_session_handoff_invalid")
            if existing != record:
                raise _fail("continuity_session_handoff_conflict", "Handoff ID has different content.")
            return existing
        _write_atomic(path, content)
    return record


def _read_handoff(store: Path, handoff_id: str) -> dict[str, Any]:
    path = store / "session-handoffs" / f"{handoff_id}.json"
    record = _read_json(path, failure_kind="continuity_session_handoff_invalid")
    basis = {key: value for key, value in record.items() if key != "handoff_digest"}
    if (
        record.get("format") != "opencntx-session-handoff"
        or record.get("format_version") != 1
        or record.get("handoff_id") != handoff_id
        or record.get("handoff_digest") != _value_digest(basis)
    ):
        raise _fail("continuity_session_handoff_invalid", "Handoff capsule is invalid.")
    return record


def accept_session_handoff(
    project_root: Path,
    *,
    handoff_id: str,
    target_part: str,
) -> dict[str, Any]:
    """Reread live durable state and atomically acknowledge one handoff."""
    selected_id = _identifier(handoff_id, "handoff_id")
    target = _one_line(target_part, "target_part", 120)
    store = store_path(project_root)
    with _writer_lock(store / ".operation.lock"):
        store, roadmap, events, state = _load_store(project_root)
        record = _read_handoff(store, selected_id)
        if record.get("project_id") != roadmap["project_id"] or record.get("roadmap_id") != roadmap["roadmap_id"]:
            raise _fail("continuity_session_handoff_cross_project", "Handoff belongs to another project.")
        if record.get("target_part") != target:
            raise _fail("continuity_session_handoff_conflict", "Target part differs from the handoff.")
        for item in record.get("evidence_objects", []):
            verified = verify_evidence_object(project_root, str(item.get("sha256")))
            if item.get("metadata_digest") != verified["metadata_digest"]:
                raise _fail("continuity_session_handoff_invalid", "Evidence reference differs.")
        capsule = _capsule_from_loaded(roadmap, events, state)
        decision = decide_finalization(capsule)
        authority_digest = _value_digest(
            {"authority": AUTHORITY, "authority_state": capsule["authority_state"]}
        )
        bindings_equal = (
            record.get("roadmap_revision") == capsule["roadmap_revision"]
            and record.get("state_digest") == capsule["state_digest"]
            and record.get("execution_capsule_digest") == capsule["capsule_digest"]
            and record.get("evidence_digest") == capsule["evidence_digest"]
            and record.get("authority_digest") == authority_digest
        )
        if decision["decision"] == "REQUEST_OWNER":
            status = "WAIT_FOR_OWNER"
        elif decision["decision"] == "BLOCKED" or decision["decision"] in {
            "COMPLETE_ASSIGNMENT",
            "COMPLETE_ROADMAP",
        }:
            status = "STOP_WITH_EVIDENCE"
        elif (
            not bindings_equal
            or decision["decision"] not in FINALIZATION_DECISIONS
            or decision["decision"] == "RECONCILE_REQUIRED"
        ):
            status = "RECONCILE_REQUIRED"
        else:
            status = "RESUME_AUTOMATICALLY"
        acknowledgement = {
            "format": "opencntx-session-handoff-ack",
            "format_version": 1,
            "handoff_id": selected_id,
            "handoff_digest": record["handoff_digest"],
            "target_part": target,
            "status": status,
            "live_state_digest": capsule["state_digest"],
            "live_capsule_digest": capsule["capsule_digest"],
            "next_action": capsule["next_internal_action"] if status == "RESUME_AUTOMATICALLY" else decision["next_action"],
            "execution": "NOT_PERFORMED",
        }
        acknowledgement["ack_digest"] = _value_digest(acknowledgement)
        path = store / "session-acks" / f"{selected_id}.json"
        if path.exists():
            existing = _read_json(path, failure_kind="continuity_session_handoff_invalid")
            if existing != acknowledgement:
                raise _fail("continuity_session_handoff_conflict", "Acknowledgement conflicts with live state.")
            return existing
        _write_atomic(path, _pretty(acknowledgement))
    return acknowledgement


def session_handoff_status(project_root: Path, handoff_id: str) -> dict[str, Any]:
    """Report whether the source may become idle after target acknowledgement."""
    selected_id = _identifier(handoff_id, "handoff_id")
    store = store_path(project_root)
    _load_store(project_root)
    record = _read_handoff(store, selected_id)
    ack_path = store / "session-acks" / f"{selected_id}.json"
    acknowledgement = None
    if ack_path.exists():
        acknowledgement = _read_json(ack_path, failure_kind="continuity_session_handoff_invalid")
        ack_basis = {key: value for key, value in acknowledgement.items() if key != "ack_digest"}
        if (
            acknowledgement.get("handoff_digest") != record["handoff_digest"]
            or acknowledgement.get("ack_digest") != _value_digest(ack_basis)
            or acknowledgement.get("status") not in HANDOFF_STATUSES
        ):
            raise _fail("continuity_session_handoff_invalid", "Acknowledgement is invalid.")
    target_status = None if acknowledgement is None else acknowledgement["status"]
    source_may_idle = target_status in {"RESUME_AUTOMATICALLY", "STOP_WITH_EVIDENCE"}
    result = {
        "format": "opencntx-session-handoff-status",
        "format_version": 1,
        "handoff_id": selected_id,
        "acknowledged": acknowledgement is not None,
        "target_status": target_status,
        "source_may_idle": source_may_idle,
        "next_action": (
            record["continuation_action"]
            if acknowledgement is None and record["continuation_action"] is not None
            else "WAIT_FOR_TARGET_ACK"
            if acknowledgement is None
            else "SOURCE_MAY_IDLE"
            if source_may_idle
            else "SOURCE_REMAINS_ACTIVE"
        ),
    }
    return result | {"status_digest": _value_digest(result)}
