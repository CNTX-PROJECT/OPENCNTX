"""Revision-bound read models of the existing ledger, never a second planner.

Only the native ledger decides progress. A published bundle is disposable and
becomes STALE if either the ledger or the Combo changes. This API does not
authenticate a host or infer OWNER authority from a supplied goal document.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .combo import load_combo, new_combo, set_active_roadmaps, update_combo, write_combo
from .continuity import (
    ContinuityError,
    _capsule_from_loaded,
    _digest,
    _fail,
    _load_store,
    _pretty,
    _value_digest,
    _write_atomic,
    _writer_lock,
    decide_finalization,
    store_path,
)
from .goal_binding import BoundGoal
from .goal_followup import compile_goal_context
from .goal_progress import load_goal_progress, progress_readiness
from .integrity import _is_reparse

FORMAT = "opencntx-connected-state"
MAX_VIEW_BYTES = 20 * 1024


def _view_path(root: Path, relative: str = "") -> Path:
    """Reject existing alias components before any view read or write."""
    try:
        base = root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise _fail(
            "connected_root_missing",
            "The selected project root does not exist.",
        ) from exc
    except OSError as exc:
        raise _fail(
            "connected_path_inaccessible",
            "Connected paths cannot be accessed in this environment.",
        ) from exc
    try:
        path = base / ".opencntx" / "continuity" / "views" / relative
        current = base
        for part in path.relative_to(base).parts:
            current = current / part
            if current.is_symlink() or (current.exists() and _is_reparse(current)):
                raise _fail("connected_path_unsafe", "Connected paths cannot contain aliases.")
        return path
    except OSError as exc:
        raise _fail(
            "connected_path_inaccessible",
            "Connected paths cannot be accessed in this environment.",
        ) from exc


def compile_connected_state(
    root: Path, goal: BoundGoal | None = None, *, synthesis_reference: str | None = None
) -> dict[str, Any]:
    """Read validated native state; an optional supervisor goal adds semantic proof."""
    _, roadmap, events, state = _load_store(root)
    capsule = _capsule_from_loaded(roadmap, events, state)
    decision = decide_finalization(capsule)
    assignments = [
        {
            "id": item["id"],
            "title": item["title"],
            "status": "DELIVERED" if item["id"] in state["completed"] else "OPEN",
            "definition_of_done": item["definition_of_done"],
        }
        for item in roadmap["assignments"]
    ]
    context = None
    nodes: list[dict[str, Any]] = []
    ready: list[str] = []
    if goal is not None:
        context = compile_goal_context(root, goal, synthesis_reference=synthesis_reference)
        progress = load_goal_progress(root, goal)
        nodes = progress.payload()["nodes"]
        ready = progress_readiness(progress, goal)["ready_nodes"]
        decision = {
            "decision": context["decision"],
            "reason": context["reason"],
            "next_action": context["next_outcome_id"],
        }
    value = {
        "format": FORMAT,
        "format_version": 1,
        "project_id": roadmap["project_id"],
        "roadmap_id": roadmap["roadmap_id"],
        "title": roadmap["title"],
        "source_revision": len(events),
        "source_digest": state["state_digest"],
        "capsule": capsule,
        "assignments": assignments,
        "goal_context": context,
        "intent": goal.payload()["intent_v1"] if goal else None,
        "nodes": nodes,
        "ready_nodes": ready,
        "decision": decision,
        "binding": "GOAL_CONNECTED" if context else "FLOW_CONNECTED",
        "host_enforcement": "UNPROVEN",
    }
    return value | {"view_digest": _value_digest(value)}


def render_current(value: dict[str, Any]) -> str:
    """Bounded current view: all obligations survive or rendering fails."""
    lines = [
        f"# {value['title']}",
        "",
        f"Source revision: {value['source_revision']}",
        f"Source digest: {value['source_digest']}",
        f"Binding: {value['binding']}; host enforcement: UNPROVEN",
        "",
        f"Current: {value['capsule']['current_assignment']}",
        f"Decision: {value['decision']['decision']}",
        f"Reason: {value['decision']['reason']}",
        f"Authority: {value['capsule']['authority_state']}",
        f"Recovery round: {value['capsule']['recovery_round']}",
        f"Next: {value['decision']['next_action']}",
        "History: ../../../history/events.jsonl (native ledger); state.json (complete hierarchy)",
        "",
        "## Outcomes",
        "",
    ]
    for item in value["assignments"]:
        lines.append(f"- {item['id']} - {item['status']}: {item['title']}")
        lines.extend(f"  - {criterion}" for criterion in item["definition_of_done"])
    context = value["goal_context"]
    if context:
        lines += ["", "## Original outcomes", ""]
        lines.extend(
            f"- {item}: {'OPEN' if item in context['open_outcome_ids'] else 'DELIVERED'}"
            for item in context["request"]["outcome_ids"]
        )
        lines += [
            "",
            "## Original authority and exclusions",
            "",
            json.dumps(value["intent"], ensure_ascii=False, sort_keys=True),
        ]
    lines += ["", "## Current hierarchy", ""] if value["nodes"] else []
    for node in value["nodes"]:
        if node["status"] != "DELIVERED":
            lines.append(
                f"- {node['id']}: {node['status']}; parent={node['parent']}; "
                f"return={node['return_to']}; {node['next_action']}"
            )
            lines.extend(
                f"  - Evidence: {ref['reference']} ({ref['sha256']})" for ref in node["evidence"]
            )
    text = "\n".join(lines) + "\n"
    if len(text.encode("utf-8")) > MAX_VIEW_BYTES:
        raise _fail("connected_view_budget", "Refine the hierarchy; never truncate open work.")
    return text


def publish_connected_state(
    root: Path,
    *,
    expected_state_digest: str,
    goal: BoundGoal | None = None,
    synthesis_reference: str | None = None,
) -> dict[str, Any]:
    """CAS against the native writer, then atomically publish a complete view bundle.

    A crash before CURRENT leaves the previous bundle intact. Combo is committed
    first; if interrupted between the two pointers, status reports STALE.
    """
    _view_path(root)
    store = store_path(root)
    with _writer_lock(store / ".operation.lock"):
        previous = connected_status(root)
        if goal is None and previous.get("view", {}).get("binding") == "GOAL_CONNECTED":
            raise _fail(
                "connected_goal_required", "Rebind the original supervisor goal; no downgrade."
            )
        value = compile_connected_state(root, goal, synthesis_reference=synthesis_reference)
        if value["source_digest"] != expected_state_digest:
            raise _fail("connected_state_stale", "Native state changed after preparation.")
        markdown = render_current(value)
        combo_root = root.resolve() / ".opencntx" / "combo"
        if combo_root.exists():
            combo = load_combo(root)  # A damaged existing store is never silently reset.
        else:
            combo = new_combo(value["project_id"])
        if combo["project_id"] != value["project_id"]:
            raise _fail("connected_project_mismatch", "Combo belongs to another project.")
        entry = {
            "id": value["roadmap_id"],
            "roadmap_id": value["roadmap_id"],
            "kind": "ROADMAP",
            "status": "ACTIVE",
            "statement": f"{value['title']}: {value['decision']['decision']}",
            "subject_key": value["roadmap_id"],
            "scope_key": value["project_id"],
            "tags": ["connected"],
            "sequence": value["source_revision"],
            "year": datetime.now(UTC).year,
            "source_digest": value["source_digest"],
            "supersedes": [],
        }
        # The current entry is not a historical completion claim. Other roadmaps
        # remain visible; replacing a twelve-entry view must fail rather than drop one.
        active = [item for item in combo["active"] if item["roadmap_id"] != value["roadmap_id"]]
        complete = (
            value["binding"] == "GOAL_CONNECTED"
            and value["decision"]["decision"] == "COMPLETE_ROADMAP"
        )
        updated = combo
        if complete:
            entry["status"] = "COMPLETED"
            if active != combo["active"]:
                updated = set_active_roadmaps(updated, active)
            if entry not in updated["recent_completed"]:
                updated = update_combo(updated, [entry])
        else:
            active.append(entry)
            if sorted(combo["active"], key=lambda item: item["id"]) != sorted(
                active, key=lambda item: item["id"]
            ):
                updated = set_active_roadmaps(combo, active)
        if updated != combo:
            write_combo(
                root,
                updated,
                expected_digest=combo["combo_digest"] if combo_root.exists() else None,
            )
            combo = updated
        value["combo_digest"] = combo["combo_digest"]
        value["view_digest"] = _value_digest(
            {key: item for key, item in value.items() if key != "view_digest"}
        )
        generation = _view_path(root, "generations/" + value["view_digest"])
        generation.mkdir(parents=True, exist_ok=True)
        files = {
            "state.json": _pretty(value),
            "ROADMAP.md": markdown.encode("utf-8"),
            "FOOTER.json": _pretty(
                {
                    "source_revision": value["source_revision"],
                    "source_digest": value["source_digest"],
                    "decision": value["decision"],
                }
            ),
        }
        for name, content in files.items():
            path = _view_path(root, "generations/" + value["view_digest"] + "/" + name)
            if path.exists() and path.read_bytes() != content:
                raise _fail("connected_generation_invalid", "Existing generation differs.")
            _write_atomic(path, content)
        receipt = {"files": {name: _digest(content) for name, content in files.items()}}
        _write_atomic(
            _view_path(root, "generations/" + value["view_digest"] + "/receipt.json"),
            _pretty(receipt),
        )
        _write_atomic(_view_path(root, "CURRENT"), (value["view_digest"] + "\n").encode("ascii"))
        return value


def connected_status(
    root: Path,
    *,
    goal: BoundGoal | None = None,
    synthesis_reference: str | None = None,
) -> dict[str, Any]:
    """Non-mutating preflight. Missing binding is a finding, not a fake empty flow."""
    _view_path(root)
    store = store_path(root)
    if not store.exists():
        return {
            "status": "CONFIGURED_ONLY",
            "missing": ["continuity", "connected_view"],
            "host_enforcement": "UNPROVEN",
        }
    _, _, _, state = _load_store(root)
    pointer = _view_path(root, "CURRENT")
    if not pointer.exists():
        return {
            "status": "BINDING_REQUIRED",
            "source_digest": state["state_digest"],
            "host_enforcement": "UNPROVEN",
        }
    try:
        digest = pointer.read_text(encoding="ascii").strip()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid generation")
        generation = _view_path(root, "generations/" + digest)
        for name in ("state.json", "receipt.json", "ROADMAP.md", "FOOTER.json"):
            _view_path(root, "generations/" + digest + "/" + name)
        value = json.loads((generation / "state.json").read_bytes())
        receipt = json.loads((generation / "receipt.json").read_bytes())
        if set(receipt["files"]) != {"state.json", "ROADMAP.md", "FOOTER.json"}:
            raise ValueError("Invalid manifest")
        for name, expected in receipt["files"].items():
            if _digest((generation / name).read_bytes()) != expected:
                raise ValueError("Changed view")
        if value["view_digest"] != digest or digest != _value_digest(
            {k: v for k, v in value.items() if k != "view_digest"}
        ):
            raise ValueError("Changed state")
        combo = load_combo(root)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ContinuityError) as exc:
        raise _fail("connected_view_invalid", "Connected bundle cannot be verified.") from exc
    if goal is not None:
        if value["binding"] != "GOAL_CONNECTED":
            raise _fail(
                "connected_goal_required",
                "The current view is not bound to the expected goal.",
            )
        expected_context = compile_goal_context(
            root, goal, synthesis_reference=synthesis_reference
        )
        if value["goal_context"] != expected_context:
            raise _fail(
                "connected_goal_mismatch",
                "The current view belongs to another goal or revision.",
            )
    current = (
        value["source_digest"] == state["state_digest"]
        and value["combo_digest"] == combo["combo_digest"]
    )
    return {
        "status": "CURRENT" if current else "STALE",
        "view": value,
        "source_digest": state["state_digest"],
        "host_enforcement": "UNPROVEN",
        "completion_allowed": current
        and value["binding"] == "GOAL_CONNECTED"
        and value["decision"]["decision"] == "COMPLETE_ROADMAP",
    }


def export_status(root: Path, destination: Path) -> dict[str, Any]:
    """Read back an explicitly selected export; unavailable destinations stay pending.

    This performs no external write. A host can export the immutable ROADMAP.md
    through its authorized file tool and call this for idempotent readback.
    """
    status = connected_status(root)
    if status["status"] != "CURRENT":
        return {"status": "SYNC_PENDING", "reason": status["status"]}
    value = status["view"]
    source = store_path(root) / "views/generations" / value["view_digest"] / "ROADMAP.md"
    expected = _digest(source.read_bytes())
    try:
        actual = _digest(destination.read_bytes())
    except OSError:
        actual = None
    return {
        "status": "CURRENT" if actual == expected else "SYNC_PENDING",
        "source_revision": value["source_revision"],
        "source_digest": value["source_digest"],
        "expected_sha256": expected,
        "actual_sha256": actual,
        "delivery_key": _value_digest([str(destination.absolute()), expected]),
    }


def record_export_delivery(root: Path, destination: Path) -> dict[str, Any]:
    """Register pending delivery and readback locally; never write the destination.

    The host must call this before export and again after its authorized delivery.
    Receipts are derived sync state and confer no goal or execution authority.
    """
    _view_path(root)
    with _writer_lock(store_path(root) / ".operation.lock"):
        receipt = export_status(root, destination)
        if "delivery_key" not in receipt:
            return receipt
        directory = _view_path(root, "deliveries")
        directory.mkdir(exist_ok=True)
        path = _view_path(root, "deliveries/" + receipt["delivery_key"] + ".json")
        _write_atomic(path, _pretty(receipt))
        if json.loads(path.read_bytes()) != receipt:
            raise _fail("connected_export_invalid", "Delivery receipt readback differs.")
        return receipt
