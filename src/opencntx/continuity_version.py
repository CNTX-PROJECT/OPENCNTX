"""Explicit v2 storage envelope; portable roadmap and v1 event bytes stay v1.

Old readers validate the stored roadmap before writing and reject this distinct
format. New readers unwrap the original bytes without changing the old event
binding. Downgrade uses a complete retained snapshot, never strips this fence.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .continuity import (
    _digest,
    _fail,
    _load_store,
    _pretty,
    _value_digest,
    _write_atomic,
    _writer_lock,
    store_path,
    validate_roadmap,
)

FORMAT = "opencntx-goal-storage-envelope"
FIELDS = {"format", "format_version", "legacy_roadmap_base64", "legacy_sha256", "envelope_digest"}


def _retained_legacy_bytes(value: Mapping[str, Any]) -> bytes | None:
    if value.get("format") != FORMAT:
        return None
    if (
        set(value) != FIELDS
        or type(value.get("format_version")) is not int
        or value["format_version"] != 2
        or value["envelope_digest"] != _value_digest(
            {key: item for key, item in value.items() if key != "envelope_digest"}
        )
    ):
        raise _fail("goal_storage_invalid", "Unsupported or changed goal storage envelope.")
    try:
        content = base64.b64decode(value["legacy_roadmap_base64"], validate=True)
        legacy = json.loads(content)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise _fail("goal_storage_invalid", "Invalid retained v1 roadmap bytes.") from exc
    if _digest(content) != value["legacy_sha256"] or not isinstance(legacy, dict):
        raise _fail("goal_storage_invalid", "Retained v1 roadmap digest differs.")
    validate_roadmap(legacy)
    return content


def unwrap_goal_storage(value: Mapping[str, Any]) -> dict[str, Any]:
    content = _retained_legacy_bytes(value)
    if content is None:
        return dict(value)
    legacy = json.loads(content)
    return validate_roadmap(legacy)


def upgrade_goal_storage(
    root: Path, *, expected_state_digest: str, approval: str
) -> dict[str, Any]:
    """Explicitly fence one already isolated, backed-up store from old writers.

    Callers stage and back up using the existing transactional update workflow.
    This operation never installs a runtime, chooses a project or grants consent.
    """
    if approval != f"UPGRADE GOAL STORAGE {expected_state_digest}":
        raise _fail("goal_storage_approval_missing", "Exact storage upgrade approval is required.")
    store = store_path(root)
    with _writer_lock(store / ".operation.lock"):
        _, _, _, state = _load_store(root)
        if state["state_digest"] != expected_state_digest:
            raise _fail("goal_storage_stale", "Storage upgrade state changed.")
        path = store / "roadmaps" / "roadmap.json"
        content = path.read_bytes()
        existing = json.loads(content)
        if existing.get("format") == FORMAT:
            unwrap_goal_storage(existing)
            return existing
        validate_roadmap(existing)
        value = {
            "format": FORMAT,
            "format_version": 2,
            "legacy_roadmap_base64": base64.b64encode(content).decode("ascii"),
            "legacy_sha256": _digest(content),
        }
        value["envelope_digest"] = _value_digest(value)
        _write_atomic(path, _pretty(value))
        _load_store(root)
        return value
