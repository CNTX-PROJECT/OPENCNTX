"""Stable provider-neutral navigation identities and rollover ordering."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .continuity import (
    _digest,
    _fail,
    _identifier,
    _one_line,
    _read_json,
    _root,
    _value_digest,
    _write_atomic,
    _writer_lock,
)

CHAT_WIDTH = 6
NOTE_WIDTH = 6
NAVIGATION_FORMAT = "opencntx-navigation-index"
CHAT_STATES = frozenset({"RESERVED", "ACTIVE", "FINALIZED", "HANDED_OFF"})
PROJECTION_KINDS = frozenset({"LOCAL_FOLDER", "SYNCED_FOLDER", "REMOTE_API"})
SORT_ORDERS = frozenset({"CANONICAL", "ALPHABETIC", "ACTIVITY", "MODIFIED"})
GENERIC_WORDS = frozenset(
    {
        "chat",
        "conversation",
        "gesprek",
        "issue",
        "new",
        "nieuw",
        "project",
        "session",
        "sessie",
        "task",
        "taak",
        "test",
        "update",
        "vervolg",
        "work",
        "werk",
    }
)
WORD_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


def _index_path(root: Path) -> Path:
    return root / ".opencntx" / "navigation" / "index.json"


def _empty_index(project_id: str) -> dict[str, Any]:
    value = {
        "format": NAVIGATION_FORMAT,
        "format_version": 1,
        "project_id": project_id,
        "chat_width": CHAT_WIDTH,
        "note_width": NOTE_WIDTH,
        "next_chat_sequence": 1,
        "next_note_sequence": 10,
        "chats": [],
        "notes": [],
        "projections": [],
    }
    return value | {"index_digest": _value_digest(value)}


def _validate_index(value: Mapping[str, object], project_id: str) -> dict[str, Any]:
    basis = {key: item for key, item in value.items() if key != "index_digest"}
    chats = value.get("chats")
    notes = value.get("notes")
    projections = value.get("projections")
    required = {
        "format",
        "format_version",
        "project_id",
        "chat_width",
        "note_width",
        "next_chat_sequence",
        "next_note_sequence",
        "chats",
        "notes",
        "projections",
        "index_digest",
    }
    if (
        set(value) != required
        or value.get("format") != NAVIGATION_FORMAT
        or value.get("format_version") != 1
        or value.get("project_id") != project_id
        or value.get("chat_width") != CHAT_WIDTH
        or value.get("note_width") != NOTE_WIDTH
        or value.get("index_digest") != _value_digest(basis)
        or not isinstance(chats, list)
        or not isinstance(notes, list)
        or not isinstance(projections, list)
    ):
        raise _fail("navigation_index_invalid", "Navigation index is invalid.")
    assert isinstance(chats, list)
    assert isinstance(notes, list)
    chat_ids = [item.get("chat_id") for item in chats if isinstance(item, Mapping)]
    note_ids = [item.get("note_id") for item in notes if isinstance(item, Mapping)]
    reservations = [item.get("reservation_key") for item in chats if isinstance(item, Mapping)]
    expected_chats = [f"C{number:0{CHAT_WIDTH}d}" for number in range(1, len(chats) + 1)]
    expected_notes = [f"N{number:0{NOTE_WIDTH}d}" for number in range(10, 10 * len(notes) + 1, 10)]
    if (
        chat_ids != expected_chats
        or note_ids != expected_notes
        or len(reservations) != len(set(reservations))
        or value.get("next_chat_sequence") != len(chats) + 1
        or value.get("next_note_sequence") != 10 * (len(notes) + 1)
        or any(item.get("state") not in CHAT_STATES for item in chats if isinstance(item, Mapping))
    ):
        raise _fail("navigation_index_invalid", "Navigation sequence or state differs.")
    return dict(value)


def _load_or_create(root: Path, project_id: str) -> dict[str, Any]:
    path = _index_path(root)
    if not path.exists():
        return _empty_index(project_id)
    return _validate_index(_read_json(path, failure_kind="navigation_index_invalid"), project_id)


def _save(root: Path, value: Mapping[str, object]) -> dict[str, Any]:
    basis = {key: item for key, item in value.items() if key != "index_digest"}
    result = dict(basis) | {"index_digest": _value_digest(basis)}
    _write_atomic(_index_path(root), _pretty_navigation(result))
    return result


def _pretty_navigation(value: object) -> bytes:
    import json

    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def initialize_navigation(project_root: Path, *, project_id: str) -> dict[str, Any]:
    """Create or read one local authoritative navigation index."""
    root = _root(project_root)
    selected = _identifier(project_id, "project_id")
    (root / ".opencntx").mkdir(exist_ok=True)
    with _writer_lock(root / ".opencntx" / "navigation.lock"):
        value = _load_or_create(root, selected)
        if not _index_path(root).exists():
            value = _save(root, value)
    return value


def navigation_index(project_root: Path, *, project_id: str) -> dict[str, Any]:
    """Read and validate the local canonical navigation index."""
    root = _root(project_root)
    selected = _identifier(project_id, "project_id")
    path = _index_path(root)
    if not path.is_file():
        raise _fail("navigation_index_missing", "Navigation is not initialized.")
    return _validate_index(_read_json(path, failure_kind="navigation_index_invalid"), selected)


def _title(value: str) -> str:
    title = _one_line(value, "title", 100).strip(" .-_")
    words = WORD_PATTERN.findall(title)
    if not 1 <= len(words) <= 7 or all(word.lower() in GENERIC_WORDS for word in words):
        raise _fail("navigation_title_invalid", "Title must contain one to seven meaningful words.")
    return " ".join(words)


def suggest_compact_title(content_summary: str) -> str:
    """Suggest a deterministic compact title; host review may provide a better one."""
    source = content_summary.strip()
    if not source or len(source) > 32_768:
        raise _fail("navigation_title_invalid", "Content summary is empty or too large.")
    words = WORD_PATTERN.findall(source)
    meaningful = [word for word in words if word.lower() not in GENERIC_WORDS and len(word) > 1]
    if not meaningful:
        raise _fail("navigation_title_invalid", "Content summary has no meaningful title words.")
    counts = Counter(word.lower() for word in meaningful)
    ranked = sorted(
        enumerate(meaningful),
        key=lambda item: (-counts[item[1].lower()], item[0]),
    )
    chosen_positions = sorted(index for index, _ in ranked[:7])
    chosen = [meaningful[index] for index in chosen_positions]
    return _title(" ".join(chosen))


def reserve_chat(
    project_root: Path,
    *,
    project_id: str,
    reservation_key: str,
    provisional_title: str,
    topic_id: str,
    parent_chat_id: str | None = None,
    part: int = 1,
) -> dict[str, Any]:
    """Reserve exactly one chronological chat identity under the writer lock."""
    root = _root(project_root)
    selected_project = _identifier(project_id, "project_id")
    key = _identifier(reservation_key, "reservation_key")
    topic = _identifier(topic_id, "topic_id")
    provisional = _title(provisional_title)
    if isinstance(part, bool) or not isinstance(part, int) or part < 1:
        raise _fail("navigation_chat_invalid", "part must be a positive integer.")
    with _writer_lock(root / ".opencntx" / "navigation.lock"):
        value = _load_or_create(root, selected_project)
        existing = next((item for item in value["chats"] if item["reservation_key"] == key), None)
        if existing is not None:
            comparable = {
                "provisional_title": provisional,
                "topic_id": topic,
                "parent_chat_id": parent_chat_id,
                "part": part,
            }
            if any(existing.get(field) != item for field, item in comparable.items()):
                raise _fail("navigation_reservation_conflict", "Reservation key has different content.")
            return dict(existing)
        if parent_chat_id is not None and not any(
            item["chat_id"] == parent_chat_id for item in value["chats"]
        ):
            raise _fail("navigation_chat_invalid", "Parent chat does not exist.")
        sequence = value["next_chat_sequence"]
        chat_id = f"C{sequence:0{CHAT_WIDTH}d}"
        record = {
            "chat_id": chat_id,
            "sequence": sequence,
            "reservation_key": key,
            "topic_id": topic,
            "parent_chat_id": parent_chat_id,
            "part": part,
            "state": "RESERVED",
            "provisional_title": provisional,
            "final_title": None,
            "visible_title": f"{chat_id} - {provisional}",
            "content_digest": None,
            "successor_chat_id": None,
            "external_metadata": {},
        }
        value["chats"].append(record)
        value["next_chat_sequence"] = sequence + 1
        _save(root, value)
    return record


def activate_chat(
    project_root: Path,
    *,
    project_id: str,
    chat_id: str,
    external_metadata: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Mark a reservation active while keeping provider identifiers as metadata."""
    root = _root(project_root)
    selected_project = _identifier(project_id, "project_id")
    metadata = {} if external_metadata is None else {
        _one_line(key, "metadata key", 80): _one_line(item, "metadata value", 300)
        for key, item in external_metadata.items()
    }
    with _writer_lock(root / ".opencntx" / "navigation.lock"):
        value = _load_or_create(root, selected_project)
        record = next((item for item in value["chats"] if item["chat_id"] == chat_id), None)
        if record is None or record["state"] not in {"RESERVED", "ACTIVE"}:
            raise _fail("navigation_chat_invalid", "Chat cannot be activated.")
        if record["state"] == "ACTIVE" and record["external_metadata"] != metadata:
            raise _fail("navigation_chat_invalid", "Active chat metadata differs.")
        record["state"] = "ACTIVE"
        record["external_metadata"] = dict(sorted(metadata.items()))
        _save(root, value)
        return dict(record)


def finalize_chat(
    project_root: Path,
    *,
    project_id: str,
    chat_id: str,
    content_summary: str,
    proposed_title: str | None = None,
) -> dict[str, Any]:
    """Finalize a chat title from its broad content before any rollover."""
    root = _root(project_root)
    selected_project = _identifier(project_id, "project_id")
    summary = content_summary.strip()
    if not summary or len(summary) > 32_768:
        raise _fail("navigation_title_invalid", "Content summary is empty or too large.")
    final_title = suggest_compact_title(summary) if proposed_title is None else _title(proposed_title)
    content_digest = _digest(summary.encode("utf-8"))
    with _writer_lock(root / ".opencntx" / "navigation.lock"):
        value = _load_or_create(root, selected_project)
        record = next((item for item in value["chats"] if item["chat_id"] == chat_id), None)
        if record is None or record["state"] not in {"ACTIVE", "FINALIZED"}:
            raise _fail("navigation_chat_invalid", "Chat cannot be finalized.")
        if record["state"] == "FINALIZED":
            if record["final_title"] != final_title or record["content_digest"] != content_digest:
                raise _fail("navigation_chat_invalid", "Finalized chat content differs.")
            return dict(record)
        record["state"] = "FINALIZED"
        record["final_title"] = final_title
        record["visible_title"] = f"{chat_id} - {final_title}"
        record["content_digest"] = content_digest
        saved = _save(root, value)
        readback = _validate_index(saved, selected_project)
        return dict(next(item for item in readback["chats"] if item["chat_id"] == chat_id))


def rollover_chat(
    project_root: Path,
    *,
    project_id: str,
    source_chat_id: str,
    source_content_summary: str,
    source_final_title: str,
    successor_reservation_key: str,
    successor_provisional_title: str,
) -> dict[str, Any]:
    """Finalize the source, read it back, then reserve exactly one successor atomically."""
    root = _root(project_root)
    selected_project = _identifier(project_id, "project_id")
    key = _identifier(successor_reservation_key, "successor_reservation_key")
    final_title = _title(source_final_title)
    provisional = _title(successor_provisional_title)
    summary = source_content_summary.strip()
    if not summary or len(summary) > 32_768:
        raise _fail("navigation_title_invalid", "Source summary is empty or too large.")
    content_digest = _digest(summary.encode("utf-8"))
    with _writer_lock(root / ".opencntx" / "navigation.lock"):
        value = _load_or_create(root, selected_project)
        source = next((item for item in value["chats"] if item["chat_id"] == source_chat_id), None)
        if source is None or source["state"] not in {"ACTIVE", "FINALIZED", "HANDED_OFF"}:
            raise _fail("navigation_chat_invalid", "Source chat cannot roll over.")
        existing = next((item for item in value["chats"] if item["reservation_key"] == key), None)
        if source["state"] == "HANDED_OFF":
            if existing is None or source["successor_chat_id"] != existing["chat_id"]:
                raise _fail("navigation_index_invalid", "Source handoff has no exact successor.")
            return {"source": dict(source), "successor": dict(existing), "index_digest": value["index_digest"]}
        if existing is not None:
            raise _fail("navigation_reservation_conflict", "Successor key already belongs elsewhere.")
        source["state"] = "FINALIZED"
        source["final_title"] = final_title
        source["visible_title"] = f"{source_chat_id} - {final_title}"
        source["content_digest"] = content_digest
        sequence = value["next_chat_sequence"]
        successor_id = f"C{sequence:0{CHAT_WIDTH}d}"
        successor = {
            "chat_id": successor_id,
            "sequence": sequence,
            "reservation_key": key,
            "topic_id": source["topic_id"],
            "parent_chat_id": source_chat_id,
            "part": source["part"] + 1,
            "state": "RESERVED",
            "provisional_title": provisional,
            "final_title": None,
            "visible_title": f"{successor_id} - {provisional}",
            "content_digest": None,
            "successor_chat_id": None,
            "external_metadata": {},
        }
        value["chats"].append(successor)
        value["next_chat_sequence"] = sequence + 1
        source["state"] = "HANDED_OFF"
        source["successor_chat_id"] = successor_id
        saved = _save(root, value)
        readback = _validate_index(saved, selected_project)
        read_source = next(item for item in readback["chats"] if item["chat_id"] == source_chat_id)
        read_successor = next(item for item in readback["chats"] if item["chat_id"] == successor_id)
        return {
            "source": dict(read_source),
            "successor": dict(read_successor),
            "index_digest": readback["index_digest"],
        }


def reserve_note(
    project_root: Path,
    *,
    project_id: str,
    note_key: str,
    title: str,
) -> dict[str, Any]:
    """Reserve one broad living-note identity in a separate namespace."""
    root = _root(project_root)
    selected_project = _identifier(project_id, "project_id")
    key = _identifier(note_key, "note_key")
    selected_title = _title(title)
    with _writer_lock(root / ".opencntx" / "navigation.lock"):
        value = _load_or_create(root, selected_project)
        existing = next((item for item in value["notes"] if item["note_key"] == key), None)
        if existing is not None:
            if existing["title"] != selected_title:
                raise _fail("navigation_reservation_conflict", "Note key has a different title.")
            return dict(existing)
        sequence = value["next_note_sequence"]
        note_id = f"N{sequence:0{NOTE_WIDTH}d}"
        record = {
            "note_id": note_id,
            "sequence": sequence,
            "note_key": key,
            "title": selected_title,
            "visible_title": f"{note_id} - {selected_title}",
        }
        value["notes"].append(record)
        value["next_note_sequence"] = sequence + 10
        _save(root, value)
        return record


def register_projection(
    project_root: Path,
    *,
    project_id: str,
    stable_id: str,
    adapter_kind: str,
    external_id: str,
    sort_order: str,
) -> dict[str, Any]:
    """Bind an external view as metadata without replacing local identity or order."""
    root = _root(project_root)
    selected_project = _identifier(project_id, "project_id")
    kind = adapter_kind.upper()
    order = sort_order.upper()
    if kind not in PROJECTION_KINDS or order not in SORT_ORDERS:
        raise _fail("navigation_projection_invalid", "Projection kind or order is invalid.")
    external = _one_line(external_id, "external_id", 300)
    with _writer_lock(root / ".opencntx" / "navigation.lock"):
        value = _load_or_create(root, selected_project)
        known = {item["chat_id"] for item in value["chats"]} | {
            item["note_id"] for item in value["notes"]
        }
        if stable_id not in known:
            raise _fail("navigation_projection_invalid", "Stable identity is unknown.")
        record = {
            "stable_id": stable_id,
            "adapter_kind": kind,
            "external_id": external,
            "sort_order": order,
            "canonical_order_preserved": order in {"CANONICAL", "ALPHABETIC"},
        }
        existing = next(
            (
                item
                for item in value["projections"]
                if item["stable_id"] == stable_id and item["adapter_kind"] == kind
            ),
            None,
        )
        if existing is not None:
            if existing != record:
                raise _fail("navigation_projection_conflict", "Projection metadata differs.")
            return dict(existing)
        value["projections"].append(record)
        value["projections"].sort(key=lambda item: (item["stable_id"], item["adapter_kind"]))
        _save(root, value)
        return record


def render_navigation_index(project_root: Path, *, project_id: str) -> str:
    """Render a small canonical human index independent of external UI sorting."""
    value = navigation_index(project_root, project_id=project_id)
    lines = ["# Navigation", "", "## Chats", ""]
    lines.extend(f"- {item['visible_title']} [{item['state']}]" for item in value["chats"])
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {item['visible_title']}" for item in value["notes"])
    lines.extend(["", f"Index digest: `{value['index_digest']}`", ""])
    return "\n".join(lines)


def preview_name_migration(existing_names: Sequence[str]) -> dict[str, Any]:
    """Produce a read-only unique mapping preview for an existing visible name list."""
    names = [_one_line(item, "existing_name", 200) for item in existing_names]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    mapping = [
        {
            "old_name": name,
            "new_name": f"C{number:0{CHAT_WIDTH}d} - {_title(name)}",
        }
        for number, name in enumerate(names, 1)
    ]
    result = {
        "format": "opencntx-navigation-migration-preview",
        "format_version": 1,
        "writes_performed": False,
        "duplicates": duplicates,
        "mapping": mapping,
    }
    return result | {"preview_digest": _value_digest(result)}
