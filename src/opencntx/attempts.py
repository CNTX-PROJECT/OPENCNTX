"""Objective, digest-bound failed-attempt evidence for Advanced / Alpha tasks."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .workspace import WorkspaceError

FINGERPRINT_FORMAT = "opencntx-attempt-fingerprint"
FINGERPRINT_VERSION = 1
MAX_EQUAL_FINGERPRINTS = 3
MAX_TOTAL_ATTEMPTS = 5
MAX_CUMULATIVE_ACTIONS = 25
MAX_CUMULATIVE_DURATION_MS = 1_800_000

ERROR_CLASSES = (
    "conflict",
    "dependency-failure",
    "invalid-input",
    "missing-input",
    "not-found",
    "permission-denied",
    "resource-exhausted",
    "timeout",
    "tool-failure",
    "unexpected",
)
BLOCK_PRIORITY = (
    "SEMANTIC_REPEAT_LIMIT",
    "TOTAL_ATTEMPT_LIMIT",
    "CUMULATIVE_ACTION_LIMIT",
    "CUMULATIVE_TIME_LIMIT",
)

TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class AttemptError(WorkspaceError):
    """A stable, fail-closed objective-attempt error."""


def _canonical(value: object) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise AttemptError(
            "Attempt evidence cannot be canonicalized.",
            code="task_attempt_record_invalid",
        ) from exc
    return text.encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _token(value: object, *, field: str) -> str:
    if not isinstance(value, str) or TOKEN_PATTERN.fullmatch(value) is None:
        raise AttemptError(
            f"{field} must be one bounded lowercase token.",
            code="task_attempt_field_invalid",
        )
    return value


def _integer(
    value: object,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        raise AttemptError(
            f"{field} is outside the bounded integer range.",
            code="task_attempt_budget_invalid",
        )
    return value


def normalize_command_type(value: object) -> str:
    return _token(value, field="Command type")


def normalize_error_class(value: object) -> str:
    normalized = _token(value, field="Error class")
    if normalized not in ERROR_CLASSES:
        raise AttemptError(
            "Error class is not in the fixed public classification.",
            code="task_attempt_error_class_invalid",
        )
    return normalized


def normalize_target(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise AttemptError(
            "Target must be one bounded relative path.",
            code="task_attempt_target_invalid",
        )
    if "\\" in value or any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in value
    ):
        raise AttemptError(
            "Target must be one portable relative path.",
            code="task_attempt_target_invalid",
        )
    normalized = unicodedata.normalize("NFC", value)
    pure = PurePosixPath(normalized)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
        or ":" in pure.parts[0]
        or pure.as_posix() != normalized
    ):
        raise AttemptError(
            "Target must be one canonical workspace-relative path.",
            code="task_attempt_target_invalid",
        )
    return normalized


def normalize_action(value: object) -> str:
    return _token(value, field="Allowed action")


def normalize_exit_status(value: object) -> int:
    return _integer(value, field="Exit status", minimum=-255, maximum=255)


def normalize_actions_used(value: object) -> int:
    return _integer(
        value,
        field="Actions used",
        minimum=1,
        maximum=MAX_CUMULATIVE_ACTIONS,
    )


def normalize_duration_ms(value: object) -> int:
    return _integer(
        value,
        field="Duration",
        minimum=0,
        maximum=MAX_CUMULATIVE_DURATION_MS,
    )


def _input_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value or len(value) > 64:
        raise AttemptError(
            "Attempt inputs must be one bounded non-empty list.",
            code="task_attempt_record_invalid",
        )
    records: list[dict[str, object]] = []
    paths: list[str] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise AttemptError(
                "Attempt input record is invalid.",
                code="task_attempt_record_invalid",
            )
        path = item["path"]
        byte_count = item["bytes"]
        sha256 = item["sha256"]
        if (
            not isinstance(path, str)
            or not path
            or type(byte_count) is not int
            or byte_count < 0
            or not isinstance(sha256, str)
            or DIGEST_PATTERN.fullmatch(sha256) is None
        ):
            raise AttemptError(
                "Attempt input record is invalid.",
                code="task_attempt_record_invalid",
            )
        if normalize_target(path) != path:
            raise AttemptError(
                "Attempt input path is not canonical.",
                code="task_attempt_record_invalid",
            )
        records.append({"path": path, "bytes": byte_count, "sha256": sha256})
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise AttemptError(
            "Attempt inputs contain duplicate paths.",
            code="task_attempt_input_duplicate",
        )
    return sorted(records, key=lambda item: str(item["path"]))


def fingerprint(
    *,
    command_type: object,
    target: object,
    inputs: object,
    exit_status: object,
    error_class: object,
) -> str:
    value = {
        "command_type": normalize_command_type(command_type),
        "error_class": normalize_error_class(error_class),
        "exit_status": normalize_exit_status(exit_status),
        "format": FINGERPRINT_FORMAT,
        "format_version": FINGERPRINT_VERSION,
        "inputs": _input_records(inputs),
        "target": normalize_target(target),
    }
    return _digest(value)


def basis_digest(inputs: object) -> str:
    return _digest(
        {
            "format": "opencntx-attempt-basis",
            "format_version": 1,
            "inputs": _input_records(inputs),
        }
    )


def reached_limits(
    previous: Sequence[dict[str, Any]],
    *,
    current_fingerprint: str,
    current_actions: int,
    current_duration_ms: int,
) -> tuple[list[str], int, int, int]:
    attempt_count = len(previous) + 1
    action_count = sum(item["actions_used"] for item in previous) + current_actions
    duration_ms = sum(item["duration_ms"] for item in previous) + current_duration_ms
    equal_count = sum(item["error_fingerprint"] == current_fingerprint for item in previous) + 1
    reached: list[str] = []
    if equal_count >= MAX_EQUAL_FINGERPRINTS:
        reached.append("SEMANTIC_REPEAT_LIMIT")
    if attempt_count >= MAX_TOTAL_ATTEMPTS:
        reached.append("TOTAL_ATTEMPT_LIMIT")
    if action_count >= MAX_CUMULATIVE_ACTIONS:
        reached.append("CUMULATIVE_ACTION_LIMIT")
    if duration_ms >= MAX_CUMULATIVE_DURATION_MS:
        reached.append("CUMULATIVE_TIME_LIMIT")
    return reached, attempt_count, action_count, duration_ms


def validate_objective_attempt_sequence(payloads: Sequence[dict[str, Any]]) -> None:
    previous: list[dict[str, Any]] = []
    seen_new_evidence: set[str] = set()
    for expected_number, payload in enumerate(payloads, start=1):
        if payload.get("attempt_number") != expected_number:
            raise AttemptError(
                "Objective attempt numbers are not consecutive.",
                code="task_attempt_record_invalid",
            )
        inputs = _input_records(payload.get("inputs"))
        expected_fingerprint = fingerprint(
            command_type=payload.get("command_type"),
            target=payload.get("target"),
            inputs=inputs,
            exit_status=payload.get("exit_status"),
            error_class=payload.get("error_class"),
        )
        if payload.get("error_fingerprint") != expected_fingerprint:
            raise AttemptError(
                "Objective attempt fingerprint does not match its facts.",
                code="task_attempt_record_invalid",
            )
        expected_basis = basis_digest(inputs)
        if payload.get("basis_digest") != expected_basis:
            raise AttemptError(
                "Objective attempt basis digest does not match its inputs.",
                code="task_attempt_record_invalid",
            )
        actions = normalize_actions_used(payload.get("actions_used"))
        duration = normalize_duration_ms(payload.get("duration_ms"))
        new_evidence = payload.get("new_evidence")
        new_digest = None if new_evidence is None else new_evidence.get("sha256")
        if expected_number == 1:
            expected_basis_status = "INITIAL"
        elif expected_basis != previous[-1]["basis_digest"]:
            expected_basis_status = "INPUT_DIGEST_CHANGED"
        elif (
            isinstance(new_digest, str)
            and DIGEST_PATTERN.fullmatch(new_digest) is not None
            and new_digest not in seen_new_evidence
        ):
            expected_basis_status = "NEW_EVIDENCE"
        else:
            raise AttemptError(
                "Repeated attempt has no digest-backed new basis.",
                code="task_attempt_unchanged",
            )
        if payload.get("basis_status") != expected_basis_status:
            raise AttemptError(
                "Objective attempt basis status is invalid.",
                code="task_attempt_record_invalid",
            )
        reached, attempts, actions_total, duration_total = reached_limits(
            previous,
            current_fingerprint=expected_fingerprint,
            current_actions=actions,
            current_duration_ms=duration,
        )
        if (
            payload.get("cumulative_attempts") != attempts
            or payload.get("cumulative_actions") != actions_total
            or payload.get("cumulative_duration_ms") != duration_total
            or payload.get("reached_limits") != reached
            or payload.get("block_reason") != (reached[0] if reached else None)
        ):
            raise AttemptError(
                "Objective attempt budget evidence is invalid.",
                code="task_attempt_record_invalid",
            )
        if isinstance(new_digest, str):
            seen_new_evidence.add(new_digest)
        previous.append(payload)


def record_attempt(
    project_root: Path,
    task_id: str,
    *,
    executor_id: str,
    action: str,
    command_type: str,
    target: str,
    input_paths: Sequence[str],
    exit_status: int,
    error_class: str,
    actions_used: int,
    duration_ms: int,
    result_evidence_path: Path,
    new_evidence_path: Path | None = None,
):
    """Append one objective failed attempt; never execute or retry a command."""
    from . import workflow
    from .integrity import IntegrityError, safe_managed_path
    from .playbook import PlaybookError, attempt_executor_binding

    try:
        root = workflow.validate_workspace(project_root)
        chain = workflow._load_chain(root, task_id)
        workflow._verify_inputs(root, chain)
        if chain.status != "IN_EXECUTION":
            raise AttemptError(
                "Attempt evidence is allowed only during execution.",
                code="task_transition_invalid",
            )
        if any(event.event_type == "attempt" for event in chain.events):
            raise AttemptError(
                "Legacy text attempts require a new explicit task.",
                code="task_attempt_legacy_chain",
            )
        objective = [
            event.payload for event in chain.events if event.event_type == "objective-attempt"
        ]
        validate_objective_attempt_sequence(objective)

        normalized_action = normalize_action(action)
        binding = attempt_executor_binding(
            root,
            task_id,
            executor_id=executor_id,
            allowed_action=normalized_action,
        )
        normalized_command = normalize_command_type(command_type)
        normalized_target = normalize_target(target)
        safe_managed_path(root, normalized_target)
        normalized_exit = normalize_exit_status(exit_status)
        normalized_error = normalize_error_class(error_class)
        normalized_actions = normalize_actions_used(actions_used)
        normalized_duration = normalize_duration_ms(duration_ms)

        if isinstance(input_paths, (str, bytes)) or not input_paths or len(input_paths) > 64:
            raise AttemptError(
                "Attempt inputs must be one bounded non-empty list.",
                code="task_attempt_field_invalid",
            )
        input_records = [workflow._input_record(root, item) for item in input_paths]
        input_records = _input_records(input_records)
        current_fingerprint = fingerprint(
            command_type=normalized_command,
            target=normalized_target,
            inputs=input_records,
            exit_status=normalized_exit,
            error_class=normalized_error,
        )
        current_basis = basis_digest(input_records)
        number = len(objective) + 1
        result_name = f"attempt-{number:04d}-result.bin"
        result_record = workflow._inspect_artifact(result_evidence_path, result_name)
        new_record = None
        if new_evidence_path is not None:
            new_name = f"attempt-{number:04d}-new-evidence.bin"
            new_record = workflow._inspect_artifact(new_evidence_path, new_name)

        if number == 1:
            basis_status = "INITIAL"
        elif current_basis != objective[-1]["basis_digest"]:
            basis_status = "INPUT_DIGEST_CHANGED"
        else:
            seen = {
                item["new_evidence"]["sha256"]
                for item in objective
                if item["new_evidence"] is not None
            }
            if new_record is None or new_record["sha256"] in seen:
                raise AttemptError(
                    "Repeated attempt requires changed input bytes or unique new evidence.",
                    code="task_attempt_unchanged",
                )
            basis_status = "NEW_EVIDENCE"

        reached, attempts, actions_total, duration_total = reached_limits(
            objective,
            current_fingerprint=current_fingerprint,
            current_actions=normalized_actions,
            current_duration_ms=normalized_duration,
        )
        payload = {
            "actions_used": normalized_actions,
            "allowed_action": normalized_action,
            "attempt_number": number,
            "basis_digest": current_basis,
            "basis_status": basis_status,
            "block_reason": reached[0] if reached else None,
            "command_type": normalized_command,
            "context_manifest_digest": binding.context_manifest_digest,
            "cumulative_actions": actions_total,
            "cumulative_attempts": attempts,
            "cumulative_duration_ms": duration_total,
            "duration_ms": normalized_duration,
            "error_class": normalized_error,
            "error_fingerprint": current_fingerprint,
            "executor_id": binding.executor_id,
            "executor_record_digest": binding.record_digest,
            "exit_status": normalized_exit,
            "inputs": input_records,
            "new_evidence": new_record,
            "proposal_digest": chain.proposal_digest,
            "reached_limits": reached,
            "result_evidence": result_record,
            "target": normalized_target,
        }
        validate_objective_attempt_sequence([*objective, payload])
        artifact_sources = [(result_evidence_path, result_record)]
        if new_record is not None and new_evidence_path is not None:
            artifact_sources.append((new_evidence_path, new_record))
        return workflow._append_event(
            root,
            chain,
            event_type="objective-attempt",
            to_status="BLOCKED" if reached else "IN_EXECUTION",
            actor_id=binding.executor_statement,
            payload=payload,
            success_status="TASK_BLOCKED" if reached else "TASK_ATTEMPT_RECORDED",
            artifact_sources=artifact_sources,
        )
    except (AttemptError, IntegrityError, PlaybookError, workflow.WorkflowError) as exc:
        if isinstance(exc, workflow.WorkflowError):
            workflow._try_failure_receipt(
                project_root,
                task_id,
                "record-attempt",
                exc,
            )
            raise
        error = workflow.WorkflowError(str(exc), code=exc.code)
        workflow._try_failure_receipt(project_root, task_id, "record-attempt", error)
        raise error from exc
