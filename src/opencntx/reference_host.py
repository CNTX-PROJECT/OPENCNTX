"""Closed Windows fixture host joining R15's goal and physical boundaries.

Only dispatch receives client data. Constructor arguments and the native project
root belong to the trusted fixture supervisor, not the client message stream.
This module registers no CLI or hook and offers no general file/shell operation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO, TextIO

from . import fixture_files as files
from .continuity import (
    ContinuityError,
    _value_digest,
    _writer_lock,
    decide_finalization,
    execution_state_capsule,
    store_path,
    validate_current_goal_binding,
)
from .goal_binding import HostSource, build_goal_binding
from .goal_progress import load_goal_progress
from .task_assessment import TaskFacts, assess_bound_task, require_assessed_broad_execution

MAX_REQUEST = 65_536


def serve_reference_host(host: ReferenceHost, source: BinaryIO, output: TextIO) -> int:
    """Bounded actual JSON-lines route; no client authority or shell command."""

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    while raw := source.readline(MAX_REQUEST + 1):
        if len(raw) > MAX_REQUEST:
            output.write(json.dumps(host._denied("NOT_PERFORMED", "oversize_request")) + "\n")
            output.flush()
            return 2
        try:
            message = json.loads(raw, object_pairs_hook=unique)
        except (ValueError, UnicodeError, RecursionError):
            message = None
        output.write(json.dumps(host.dispatch(message)) + "\n")
        output.flush()
    return 0


class ReferenceHost:
    """One exact approved fixture action, with no client binding/approval method."""

    def __init__(
        self,
        *,
        project_root: Path,
        fixture_root: Path,
        intent: Mapping[str, object],
        source: HostSource | None,
        request_id: str,
        revision: int,
        assessment_facts: TaskFacts | None = None,
        progress_node_id: str | None = None,
    ) -> None:
        self.project_root = project_root
        self.consumed = False
        self.progress_node_id = progress_node_id
        exclusions = intent.get("exclusions")
        if (
            intent.get("scope") != ["parent"]
            or not isinstance(exclusions, list)
            or "parent/child" not in exclusions
        ):
            raise files.Refused("intent_does_not_match_fixed_fixture_scope")
        with _writer_lock(store_path(project_root) / ".operation.lock"):
            capsule = execution_state_capsule(project_root)
            self.physical = files.bind(fixture_root, allowed_root=project_root)
            action = {
                "outcome_id": "PARENT-RESULT",
                "operation": "REPLACE_EXACT",
                "targets": list(files.NAMES),
                "recursive": False,
                "protected_targets": list(files.WATCHED[3:]),
                "preconditions": [
                    {
                        "target": name,
                        "sha256": files.digest(data),
                        "identity_ref": ":".join(str(part) for part in identity),
                    }
                    for name, data, identity in zip(
                        files.NAMES, self.physical.originals, self.physical.identities
                    )
                ],
                "capability_ref": "closed-reference-windows-fixture",
            }
            self.expected = build_goal_binding(
                intent=intent,
                execution_capsule=capsule,
                request_id=request_id,
                revision=revision,
                parent_request_id=None,
                outcome_ids=["PARENT-RESULT", "CHILD-PRESERVATION"],
                action=action,
                source=source,
            )
            self.assessment = assess_bound_task(
                self.expected,
                assessment_facts or TaskFacts(),
                reason="Trusted supervisor facts for the fixed parent fixture action.",
            )

    def dispatch(self, message: object) -> dict[str, Any]:
        """The whole client surface; no fixture mutation precedes bound validation."""
        try:
            if not isinstance(message, Mapping):
                raise files.Refused("message_not_object")
            if self.consumed:
                raise files.Refused("already_consumed")
            with _writer_lock(store_path(self.project_root) / ".operation.lock"):
                if self.consumed:
                    raise files.Refused("already_consumed")
                bound = validate_current_goal_binding(
                    self.project_root, message, expected=self.expected
                )
                progress = (
                    None
                    if self.progress_node_id is None
                    else load_goal_progress(self.project_root, self.expected)
                )
                require_assessed_broad_execution(
                    self.assessment, self.expected, progress=progress, node_id=self.progress_node_id
                )
                if (
                    bound["request"]["source"]["role"] != "OWNER"
                    or bound["intent_v1"]["authority_state"] != "APPROVED"
                    or decide_finalization(bound["execution_capsule_v1"])["decision"] != "CONTINUE"
                ):
                    raise files.Refused("approved_host_source_required")
                self.consumed = True
                files.execute(self.physical)
                result = {
                    "decision": "ALLOW",
                    "execution": "PERFORMED",
                    "binding_digest": bound["binding_digest"],
                    "request_id": bound["request"]["id"],
                    "revision": bound["request"]["revision"],
                    "targets": list(files.NAMES),
                    "retained": list(files.RETAINED),
                    "boundary": "closed_windows_reference_fixture_only",
                }
                return result | {"result_digest": _value_digest(result)}
        except files.RecoveryRequired as exc:
            return self._denied("PARTIAL_RECOVERY_REQUIRED", str(exc))
        except (files.Refused, ContinuityError) as exc:
            return self._denied("NOT_PERFORMED_OR_ROLLED_BACK", str(exc))

    @staticmethod
    def _denied(execution: str, reason: str) -> dict[str, Any]:
        return {
            "decision": "DENY",
            "execution": execution,
            "reason": reason,
            "boundary": "closed_windows_reference_fixture_only",
        }
