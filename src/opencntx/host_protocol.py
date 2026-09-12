"""Provider-neutral, non-executing host delivery and claim protocol."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .continuity import (
    AUTHORITY,
    _append_events,
    _assignment,
    _cache_state,
    _claim_for_assignment,
    _digest,
    _fail,
    _load_store,
    _pretty,
    _value_digest,
    _write_atomic,
    _writer_lock,
    store_path,
)

HOST_ID_PATTERN = re.compile(r"[A-Z][A-Z0-9._-]{1,79}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
INPUT_CLASSIFICATIONS = frozenset(
    {"FEEDBACK", "CORRECTION", "EXTENSION", "SIDE_TOPIC", "REPLACEMENT"}
)
GUARDED_COPY_FORMAT = "opencntx-guarded-copy"
GUARDED_COPY_FIELDS = frozenset(
    {
        "format",
        "format_version",
        "source",
        "source_sha256",
        "target",
        "target_sha256",
        "approved_target",
    }
)


def _host_id(value: str) -> str:
    text = value.strip()
    if HOST_ID_PATTERN.fullmatch(text) is None:
        raise _fail("continuity_host_invalid", "Host ID must be a portable uppercase identifier.")
    return text


def _guarded_relative_path(value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise _fail("guarded_copy_invalid", f"{field} must be a portable relative path.")
    candidate = Path(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise _fail("guarded_copy_invalid", f"{field} must be a portable relative path.")
    return candidate


def _guarded_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise _fail("guarded_copy_invalid", f"{field} must be a lowercase SHA-256 digest.")
    return value


def _guarded_path(root: Path, relative: Path, *, field: str) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise _fail("guarded_copy_escape", f"{field} must not traverse a symbolic link.")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _fail("guarded_copy_escape", f"{field} escapes the guarded root.") from exc
    if not resolved.is_file():
        raise _fail("guarded_copy_invalid", f"{field} must name one existing regular file.")
    return resolved


def _guarded_action(root: Path, action_path: Path) -> tuple[dict[str, object], Path, Path]:
    try:
        selected_root = root.resolve(strict=True)
        selected_action = action_path.resolve(strict=True)
        selected_action.relative_to(selected_root)
        raw = json.loads(selected_action.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise _fail(
            "guarded_copy_invalid", "Guarded-copy action must be readable JSON below root."
        ) from exc
    if not isinstance(raw, dict) or set(raw) != GUARDED_COPY_FIELDS:
        raise _fail("guarded_copy_invalid", "Guarded-copy action has unknown or missing fields.")
    if raw.get("format") != GUARDED_COPY_FORMAT or raw.get("format_version") != 1:
        raise _fail("guarded_copy_invalid", "Guarded-copy action format is unsupported.")
    source_relative = _guarded_relative_path(raw["source"], field="source")
    target_relative = _guarded_relative_path(raw["target"], field="target")
    approved_relative = _guarded_relative_path(raw["approved_target"], field="approved_target")
    if target_relative != approved_relative:
        raise _fail(
            "guarded_copy_target_mismatch", "Target does not equal the approved exact target."
        )
    source = _guarded_path(selected_root, source_relative, field="source")
    target = _guarded_path(selected_root, target_relative, field="target")
    if source == target:
        raise _fail("guarded_copy_invalid", "Source and target must be different files.")
    if _digest(source.read_bytes()) != _guarded_digest(raw["source_sha256"], field="source_sha256"):
        raise _fail("guarded_copy_source_drift", "Source bytes differ from the bound action.")
    if _digest(target.read_bytes()) != _guarded_digest(raw["target_sha256"], field="target_sha256"):
        raise _fail("guarded_copy_target_drift", "Target bytes differ from the bound action.")
    return raw, source, target


def guarded_copy(root: Path, action_path: Path) -> dict[str, object]:
    """Refuse the retired pilot until an independent host binding is proven.

    The original prototype trusted caller-owned ``approved_target`` and could
    overwrite concurrent user edits. No request supplied through that format
    establishes execution authority. Refuse before reading action paths or
    creating temporary files; preserving the CLI makes stale callers fail closed.
    """
    raise _fail(
        "guarded_copy_host_unbound",
        "The copy pilot has no independently verified host binding; no files were changed.",
    )


def _last_handoff(store: Path, state: dict[str, Any]) -> tuple[str | None, str | None]:
    if not state["completed"]:
        return None, None
    relative = f"handoffs/{state['completed'][-1]}.json"
    path = store / relative
    if not path.is_file():
        return None, None
    return relative, _digest(path.read_bytes())


def _delivery(
    store: Path,
    roadmap: dict[str, Any],
    events: list[dict[str, Any]],
    state: dict[str, Any],
    host_id: str,
) -> dict[str, Any]:
    current = state["current_assignment"]
    handoff_path, handoff_sha256 = _last_handoff(store, state)
    claim = None if current is None else _claim_for_assignment(store, events, str(current))
    if current is None:
        phase = "COMPLETE" if state["status"] == "COMPLETE" else state["status"]
        next_action = "ROADMAP_COMPLETE" if phase == "COMPLETE" else "STOP_FAIL_CLOSED"
        detail_path = detail_sha256 = None
    else:
        detail_path = f"details/{current}.md"
        detail_sha256 = _digest((store / detail_path).read_bytes())
        if claim is None:
            phase, next_action = "DETAIL", f"CLAIM {current}"
        elif claim["host_id"] == host_id:
            phase, next_action = "EXECUTE", f"RESUME {current}"
        else:
            phase, next_action = "CLAIMED", f"WAIT {current}"
    value = {
        "format": "opencntx-host-delivery",
        "format_version": 1,
        "project_id": roadmap["project_id"],
        "roadmap_id": roadmap["roadmap_id"],
        "authority": AUTHORITY,
        "host_id": host_id,
        "phase": phase,
        "current_assignment": current,
        "detail_path": detail_path,
        "detail_sha256": detail_sha256,
        "handoff_path": handoff_path,
        "handoff_sha256": handoff_sha256,
        "claim_digest": (
            claim["claim_digest"] if claim is not None and claim["host_id"] == host_id else None
        ),
        "event_head": state["event_head"],
        "next_action": next_action,
        "execution": "NOT_PERFORMED",
    }
    return value | {"delivery_digest": _value_digest(value)}


def host_status(project_root: Path, host_id: str) -> dict[str, Any]:
    """Deliver exactly one current assignment without writing or executing it."""
    selected_host = _host_id(host_id)
    store, roadmap, events, state = _load_store(project_root)
    return _delivery(store, roadmap, events, state, selected_host)


def _claim_transition(record: dict[str, Any]) -> dict[str, Any]:
    value = {
        "format": "opencntx-host-transition",
        "format_version": 1,
        "phase": "EXECUTE",
        "host_id": record["host_id"],
        "claimed_assignment": record["assignment_id"],
        "current_assignment": record["assignment_id"],
        "detail_path": record["detail_path"],
        "detail_sha256": record["detail_sha256"],
        "claim_digest": record["claim_digest"],
        "next_action": f"EXECUTE {record['assignment_id']}",
        "execution": "NOT_PERFORMED",
    }
    return value | {"transition_digest": _value_digest(value)}


def claim_host(project_root: Path, host_id: str, delivery_digest: str) -> dict[str, Any]:
    """Claim the one delivered assignment once, with idempotent retry behavior."""
    selected_host = _host_id(host_id)
    continuity_store = store_path(project_root)
    with _writer_lock(continuity_store / ".operation.lock"):
        store, roadmap, events, state = _load_store(project_root)
        current = state["current_assignment"]
        if current is None or state["status"] != "RUNNING":
            raise _fail("continuity_claim_unavailable", "No running assignment can be claimed.")
        identifier = str(current)
        existing = _claim_for_assignment(store, events, identifier)
        if existing is not None:
            if (
                existing["host_id"] == selected_host
                and existing["delivery_digest"] == delivery_digest
            ):
                return _claim_transition(existing)
            raise _fail("continuity_claim_conflict", "The assignment already has another claim.")
        delivery = _delivery(store, roadmap, events, state, selected_host)
        if delivery["delivery_digest"] != delivery_digest:
            raise _fail("continuity_delivery_drift", "Host delivery changed before claim.")
        assignment = _assignment(roadmap, identifier)
        record = {
            "format": "opencntx-host-claim",
            "format_version": 1,
            "project_id": roadmap["project_id"],
            "roadmap_id": roadmap["roadmap_id"],
            "assignment_id": assignment["id"],
            "host_id": selected_host,
            "authority": AUTHORITY,
            "delivery_digest": delivery_digest,
            "detail_path": delivery["detail_path"],
            "detail_sha256": delivery["detail_sha256"],
            "context_digest": _selection_context(events, identifier),
            "claimed_event_previous_head": state["event_head"],
        }
        record["claim_digest"] = _value_digest(record)
        relative = f"claims/{identifier}.json"
        _write_atomic(store / relative, _pretty(record))
        appended = _append_events(
            store,
            (
                (
                    "ASSIGNMENT_CLAIMED",
                    {
                        "assignment_id": identifier,
                        "host_id": selected_host,
                        "delivery_digest": delivery_digest,
                        "claim_digest": record["claim_digest"],
                        "claim_path": relative,
                    },
                ),
            ),
            expected_head=state["event_head"],
            existing_events=events,
        )
        _cache_state(store, roadmap, [*events, *appended])
    _load_store(project_root)
    return _claim_transition(record)


def _selection_context(events: list[dict[str, Any]], identifier: str) -> str:
    for event in events:
        if (
            event["type"] == "ASSIGNMENT_SELECTED"
            and event["payload"].get("assignment_id") == identifier
        ):
            return str(event["payload"]["context_digest"])
    raise _fail("continuity_store_invalid", "Host delivery has no selected context.")


def resume_host(project_root: Path, host_id: str, claim_digest: str) -> dict[str, Any]:
    """Resume an active claim or route a completed claim to the next status step."""
    selected_host = _host_id(host_id)
    store, roadmap, events, state = _load_store(project_root)
    claims = [
        _claim_for_assignment(store, events, identifier)
        for identifier in roadmap_assignment_ids(roadmap)
    ]
    record = next(
        (
            item
            for item in claims
            if item is not None
            and item["host_id"] == selected_host
            and item["claim_digest"] == claim_digest
        ),
        None,
    )
    if record is None:
        raise _fail("continuity_claim_invalid", "Host claim cannot be resumed.")
    if state["current_assignment"] == record["assignment_id"]:
        return _claim_transition(record)
    if record["assignment_id"] not in state["completed"]:
        raise _fail("continuity_claim_invalid", "Host claim is not active or completed.")
    phase = "COMPLETE" if state["status"] == "COMPLETE" else "NEXT"
    next_action = (
        "ROADMAP_COMPLETE" if phase == "COMPLETE" else f"STATUS {state['current_assignment']}"
    )
    value = {
        "format": "opencntx-host-transition",
        "format_version": 1,
        "phase": phase,
        "host_id": selected_host,
        "claimed_assignment": record["assignment_id"],
        "current_assignment": state["current_assignment"],
        "claim_digest": claim_digest,
        "next_action": next_action,
        "execution": "NOT_PERFORMED",
    }
    return value | {"transition_digest": _value_digest(value)}


def roadmap_assignment_ids(roadmap: dict[str, Any]) -> tuple[str, ...]:
    """Return the bounded assignment order for internal claim lookup."""
    return tuple(item["id"] for item in roadmap["assignments"])


def _host_input_records(store: Path) -> list[dict[str, Any]]:
    directory = store / "host-inputs"
    records: list[dict[str, Any]] = []
    if not directory.is_dir():
        return records
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise _fail("continuity_host_input_invalid", "A durable host input is unreadable.") from exc
        basis = {key: item for key, item in value.items() if key != "input_digest"}
        if value.get("format") != "opencntx-host-input-anchor" or value.get(
            "input_digest"
        ) != _value_digest(basis):
            raise _fail("continuity_host_input_invalid", "A durable host input has drifted.")
        records.append(value)
    return records


def park_host_input(
    project_root: Path,
    host_id: str,
    claim_digest: str,
    *,
    input_id: str,
    classification: str,
    step_id: str,
    open_outcome_ids: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Persist one nested input and an exact return anchor for a claimed task."""
    selected_host = _host_id(host_id)
    selected_input = _host_id(input_id)
    selected_step = _host_id(step_id)
    if classification not in INPUT_CLASSIFICATIONS:
        raise _fail("continuity_host_input_invalid", "Host input classification is unsupported.")
    outcomes = [_host_id(value) for value in open_outcome_ids]
    if len(outcomes) != len(set(outcomes)):
        raise _fail("continuity_host_input_invalid", "Open outcome IDs must be unique.")
    continuity_store = store_path(project_root)
    with _writer_lock(continuity_store / ".operation.lock"):
        store, roadmap, events, state = _load_store(project_root)
        current = state["current_assignment"]
        if current is None:
            raise _fail("continuity_host_input_unavailable", "No active task can be parked.")
        claim = _claim_for_assignment(store, events, str(current))
        if (
            claim is None
            or claim["host_id"] != selected_host
            or claim["claim_digest"] != claim_digest
        ):
            raise _fail("continuity_host_input_unbound", "The host input is not bound to the active claim.")
        directory = store / "host-inputs"
        acknowledgements = store / "host-input-acks"
        existing_path = directory / f"{selected_input}.json"
        records = _host_input_records(store)
        active = [
            item
            for item in records
            if not (acknowledgements / f"{item['input_id']}.json").is_file()
        ]
        parent = active[-1]["input_id"] if active else None
        basis = {
            "format": "opencntx-host-input-anchor",
            "format_version": 1,
            "input_id": selected_input,
            "classification": classification,
            "project_id": roadmap["project_id"],
            "roadmap_id": roadmap["roadmap_id"],
            "roadmap_revision": _value_digest(roadmap),
            "task_id": current,
            "step_id": selected_step,
            "open_outcome_ids": outcomes,
            "authority": claim["authority"],
            "host_id": selected_host,
            "claim_digest": claim_digest,
            "state_digest": state["state_digest"],
            "event_head": state["event_head"],
            "parent_input_id": parent,
            "sequence": len(records) + 1,
            "action": {
                "SIDE_TOPIC": "PARK_AND_HANDLE",
                "FEEDBACK": "PARK_AND_HANDLE",
                "CORRECTION": "RECONCILE_CURRENT_STEP",
                "EXTENSION": "EXTEND_CURRENT_TASK",
                "REPLACEMENT": "REPLACE_AFTER_CONFIRMATION",
            }[classification],
            "execution": "RECORDED",
        }
        record = basis | {"input_digest": _value_digest(basis)}
        if existing_path.is_file():
            existing = next(item for item in records if item["input_id"] == selected_input)
            if existing != record:
                raise _fail("continuity_host_input_conflict", "Host input ID has different content.")
            return existing
        directory.mkdir(exist_ok=True)
        _write_atomic(existing_path, _pretty(record))
    return record


def return_host_input(
    project_root: Path,
    host_id: str,
    *,
    input_id: str,
    input_digest: str,
) -> dict[str, Any]:
    """Acknowledge the newest nested input once and resume its verified anchor."""
    selected_host = _host_id(host_id)
    selected_input = _host_id(input_id)
    continuity_store = store_path(project_root)
    with _writer_lock(continuity_store / ".operation.lock"):
        store, roadmap, _events, state = _load_store(project_root)
        records = _host_input_records(store)
        selected = next((item for item in records if item["input_id"] == selected_input), None)
        if selected is None or selected["input_digest"] != input_digest:
            raise _fail("continuity_host_input_invalid", "Host input identity is invalid.")
        if selected["host_id"] != selected_host or selected["project_id"] != roadmap["project_id"]:
            raise _fail("continuity_host_input_unbound", "Host input belongs to another host or project.")
        acknowledgement_path = store / "host-input-acks" / f"{selected_input}.json"
        if acknowledgement_path.is_file():
            existing = json.loads(acknowledgement_path.read_text(encoding="utf-8"))
            basis = {key: item for key, item in existing.items() if key != "ack_digest"}
            if existing.get("ack_digest") != _value_digest(basis):
                raise _fail("continuity_host_input_invalid", "Host input acknowledgement drifted.")
            return existing
        active = [
            item
            for item in records
            if not (store / "host-input-acks" / f"{item['input_id']}.json").is_file()
        ]
        if not active or active[-1]["input_id"] != selected_input:
            raise _fail("continuity_host_input_order", "Nested host inputs must return newest first.")
        if selected["roadmap_revision"] != _value_digest(roadmap):
            raise _fail("continuity_host_input_drift", "Roadmap revision changed; reconcile first.")
        current = state["current_assignment"]
        same_task = current == selected["task_id"]
        if same_task and state["state_digest"] != selected["state_digest"]:
            raise _fail("continuity_host_input_drift", "Current task state changed; reconcile first.")
        action = f"RESUME {selected['task_id']} {selected['step_id']}" if same_task else (
            "ROADMAP_COMPLETE" if current is None else f"STATUS {current}"
        )
        basis = {
            "format": "opencntx-host-input-ack",
            "format_version": 1,
            "input_id": selected_input,
            "input_digest": input_digest,
            "host_id": selected_host,
            "resumed_task_id": selected["task_id"] if same_task else current,
            "resumed_step_id": selected["step_id"] if same_task else None,
            "route": "SAME_STEP" if same_task else "REVISED_NEXT_STEP",
            "next_action": action,
            "execution": "ACKNOWLEDGED",
        }
        acknowledgement = basis | {"ack_digest": _value_digest(basis)}
        acknowledgement_path.parent.mkdir(exist_ok=True)
        _write_atomic(acknowledgement_path, _pretty(acknowledgement))
    return acknowledgement
