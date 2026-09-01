"""Provider-neutral, non-executing host delivery and claim protocol."""

from __future__ import annotations

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


def _host_id(value: str) -> str:
    text = value.strip()
    if HOST_ID_PATTERN.fullmatch(text) is None:
        raise _fail("continuity_host_invalid", "Host ID must be a portable uppercase identifier.")
    return text


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
        "ROADMAP_COMPLETE"
        if phase == "COMPLETE"
        else f"STATUS {state['current_assignment']}"
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
