"""Compact goal evidence attached to the existing session handoff and ACK.

The retained goal is supplied by the trusted supervisor, not the receiving
action client. ACK is never a claim to have executed the attached action.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .continuity import _fail, _identifier, _value_digest, store_path, validate_current_goal_binding
from .goal_binding import BoundGoal, _canonical
from .goal_followup import compile_goal_context, load_followup_evidence
from .goal_progress import load_goal_progress
from .session_continuity import (
    _read_handoff,
    accept_session_handoff,
    prepare_session_handoff,
    store_evidence_object,
    verify_evidence_object,
)

MAX_HANDOFF_BYTES = 65_536


def _snapshot(root: Path, expected: BoundGoal) -> dict[str, Any]:
    goal = expected.payload()
    validate_current_goal_binding(root, goal, expected=expected)
    progress = load_goal_progress(root, expected).payload()
    context = compile_goal_context(root, expected)
    followup = load_followup_evidence(root, expected)
    value = {
        "format": "opencntx-goal-handoff-evidence",
        "format_version": 2,
        "goal": goal,
        "progress_digest": progress["progress_digest"],
        "positions": [
            {key: node[key] for key in ("id", "parent", "return_to", "outcome_ids", "status")}
            for node in progress["nodes"]
        ],
        "context": context,
        "followup": followup,
        "execution": "NOT_PERFORMED",
    }
    value["snapshot_digest"] = _value_digest(value)
    if len(_canonical(value).encode()) > MAX_HANDOFF_BYTES:
        raise _fail("goal_handoff_invalid", "Compact goal handoff exceeds its byte bound.")
    return value


def prepare_goal_handoff(
    root: Path,
    expected: BoundGoal,
    *,
    handoff_id: str,
    source_part: str,
    target_part: str,
    provider_capabilities: Mapping[str, object],
    rollback_boundary: str,
) -> dict[str, Any]:
    snapshot = _snapshot(root, expected)
    metadata = store_evidence_object(
        root, content=_canonical(snapshot).encode(), summary="Bound R15 goal handoff v2"
    )
    return prepare_session_handoff(
        root,
        handoff_id=handoff_id,
        source_part=source_part,
        target_part=target_part,
        provider_capabilities=provider_capabilities,
        rollback_boundary=rollback_boundary,
        exclusions=expected.payload()["action"]["protected_targets"],
        evidence_object_digests=[metadata["sha256"]],
        expected_state_digest=expected.payload()["execution_capsule_v1"]["state_digest"],
    )


def accept_goal_handoff(
    root: Path, expected: BoundGoal, *, handoff_id: str, target_part: str
) -> dict[str, Any]:
    # All content checks precede the native ACK. Native CAS closes the race
    # between these read-only checks and its one serialized durable write.
    snapshot = _snapshot(root, expected)
    record = _read_handoff(store_path(root), _identifier(handoff_id, "handoff_id"))
    references = record.get("evidence_objects")
    if not isinstance(references, list) or len(references) != 1:
        raise _fail("goal_handoff_invalid", "Exactly one bound goal snapshot is required.")
    metadata = verify_evidence_object(root, references[0]["sha256"])
    content = gzip.decompress((store_path(root) / metadata["object_path"]).read_bytes())
    if len(content) > MAX_HANDOFF_BYTES or json.loads(content) != snapshot:
        raise _fail("goal_handoff_stale", "Goal, progress, recovery or original outcomes differ.")
    if snapshot["context"]["decision"] != "CONTINUE":
        raise _fail("goal_handoff_blocked", "Goal continuation is blocked; evidence is preserved.")
    return accept_session_handoff(
        root,
        handoff_id=handoff_id,
        target_part=target_part,
        expected_state_digest=expected.payload()["execution_capsule_v1"]["state_digest"],
    )
