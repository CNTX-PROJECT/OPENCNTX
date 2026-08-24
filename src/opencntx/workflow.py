"""Local, append-only task workflow with exact digest-bound Owner gates."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import stat
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any
from uuid import uuid4

from .attempts import (
    BLOCK_PRIORITY,
    MAX_CUMULATIVE_ACTIONS,
    MAX_CUMULATIVE_DURATION_MS,
    MAX_TOTAL_ATTEMPTS,
    AttemptError,
    normalize_actions_used,
    normalize_command_type,
    normalize_duration_ms,
    normalize_error_class,
    normalize_exit_status,
    normalize_target,
    validate_objective_attempt_sequence,
)
from .integrity import Transaction, state_digest, write_new_bytes, writer_transaction
from .primitives import utc_now as _utc_now
from .workspace import SHA256_PATTERN, WorkspaceError, validate_workspace

TASK_FORMAT = "opencntx-task-event"
TASK_FORMAT_VERSION = 1
TASK_RECEIPT_FORMAT = "opencntx-task-receipt"
TASK_RECEIPT_VERSION = 1
TASK_VIEW_FORMAT = "opencntx-task-view"
TASK_VIEW_VERSION = 1

TASK_ID_PATTERN = re.compile(r"TASK-\d{8}-\d{4}\Z")
ACTOR_ID_PATTERN = re.compile(r"[^\x00-\x1f\x7f]{1,120}\Z")
ERROR_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
ACTION_TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
EXECUTOR_ID_PATTERN = re.compile(r"EXEC-\d{8}-[0-9a-f]{12}\Z")
EVENT_FILE_PATTERN = re.compile(r"(\d{4})-([a-z][a-z0-9-]*)\.json\Z")

MAX_TEXT_LENGTH = 1000
MAX_LIST_ITEMS = 64
MAX_INPUT_BYTES = 2 * 1024**3
MAX_ARTIFACT_BYTES = 2 * 1024**3
COPY_CHUNK_SIZE = 1024 * 1024

INPUT_ROOTS = {"CONTROL", "SOURCES", "CHAPTERS", "PLAYBOOKS", "ROLES"}
TERMINAL_FOR_NEW_TASK = {"CLOSED", "CANCELLED", "SUPERSEDED"}
ALL_STATUSES = {
    "AWAITING_OWNER_APPROVAL",
    "APPROVED_FOR_EXECUTION",
    "IN_EXECUTION",
    "RESULT_READY",
    "AWAITING_OWNER_ACCEPTANCE",
    "OWNER_ACCEPTED",
    "CLOSED",
    "RETURNED",
    "BLOCKED",
    "CANCELLED",
    "SUPERSEDED",
}

EVENT_SPECS: dict[str, tuple[str | None, frozenset[str], str]] = {
    "proposal": (None, frozenset({"AWAITING_OWNER_APPROVAL"}), "ARCHITECT"),
    "owner-approval": (
        "AWAITING_OWNER_APPROVAL",
        frozenset({"APPROVED_FOR_EXECUTION"}),
        "OWNER",
    ),
    "execution-begun": (
        "APPROVED_FOR_EXECUTION",
        frozenset({"IN_EXECUTION"}),
        "ARCHITECT",
    ),
    "result": ("IN_EXECUTION", frozenset({"RESULT_READY"}), "EXECUTOR"),
    "architect-review": (
        "RESULT_READY",
        frozenset({"AWAITING_OWNER_ACCEPTANCE", "RETURNED"}),
        "ARCHITECT",
    ),
    "owner-acceptance": (
        "AWAITING_OWNER_ACCEPTANCE",
        frozenset({"OWNER_ACCEPTED", "RETURNED"}),
        "OWNER",
    ),
    "closure": ("OWNER_ACCEPTED", frozenset({"CLOSED"}), "ARCHITECT"),
    "attempt": ("IN_EXECUTION", frozenset({"IN_EXECUTION", "BLOCKED"}), "EXECUTOR"),
    "objective-attempt": (
        "IN_EXECUTION",
        frozenset({"IN_EXECUTION", "BLOCKED"}),
        "EXECUTOR",
    ),
    "cancellation": (None, frozenset({"CANCELLED"}), "OWNER"),
    "superseded": (None, frozenset({"SUPERSEDED"}), "OWNER"),
}

EVENT_KEYS = {
    "format",
    "format_version",
    "task_id",
    "revision",
    "event_number",
    "event_type",
    "from_status",
    "to_status",
    "actor_role",
    "actor_id",
    "created_at",
    "previous_record_digest",
    "object_digest",
    "payload",
    "record_digest",
}

PAYLOAD_KEYS: dict[str, set[str]] = {
    "proposal": {
        "title",
        "goal",
        "definition_of_done",
        "executor_role",
        "inputs",
        "allowed_actions",
        "forbidden_actions",
        "expected_output",
        "acceptance_criteria",
    },
    "owner-approval": {"proposal_digest", "decision"},
    "execution-begun": {"proposal_digest", "approval_record_digest"},
    "result": {
        "proposal_digest",
        "execution_record_digest",
        "result",
        "evidence",
        "limitations",
        "open_questions",
    },
    "architect-review": {"result_digest", "outcome", "findings"},
    "owner-acceptance": {"result_digest", "review_digest", "decision"},
    "closure": {
        "proposal_digest",
        "approval_digest",
        "result_digest",
        "review_digest",
        "acceptance_digest",
    },
    "attempt": {
        "proposal_digest",
        "attempt_number",
        "error_code",
        "error_signature",
        "new_basis",
    },
    "objective-attempt": {
        "actions_used",
        "allowed_action",
        "attempt_number",
        "basis_digest",
        "basis_status",
        "block_reason",
        "command_type",
        "context_manifest_digest",
        "cumulative_actions",
        "cumulative_attempts",
        "cumulative_duration_ms",
        "duration_ms",
        "error_class",
        "error_fingerprint",
        "executor_id",
        "executor_record_digest",
        "exit_status",
        "inputs",
        "new_evidence",
        "proposal_digest",
        "reached_limits",
        "result_evidence",
        "target",
    },
    "cancellation": {"proposal_digest", "reason"},
    "superseded": {"proposal_digest", "replacement_task_id", "reason"},
}


class WorkflowError(WorkspaceError):
    """A fail-closed workflow error with a stable public code."""


@dataclass(frozen=True)
class TaskEvent:
    event_number: int
    event_type: str
    from_status: str | None
    to_status: str
    actor_role: str
    actor_id: str
    object_digest: str
    record_digest: str
    payload: dict[str, Any]
    path: Path


@dataclass(frozen=True)
class TaskChain:
    task_id: str
    revision: int
    status: str
    directory: Path
    events: tuple[TaskEvent, ...]

    @property
    def proposal_digest(self) -> str:
        return self.events[0].object_digest


@dataclass(frozen=True)
class TaskResult:
    status: str
    task_id: str
    revision: int
    task_status: str
    object_digest: str
    record_digest: str
    task_path: Path
    receipt_path: Path | None


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


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
        raise WorkflowError(
            f"Taakrecord kan niet canoniek worden gemaakt: {exc}",
            code="task_record_invalid",
        ) from exc
    return text.encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )


def _short_text(
    value: object,
    *,
    field: str,
    maximum: int = MAX_TEXT_LENGTH,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise WorkflowError(
            f"{field} moet niet-lege, begrensde tekst zijn.",
            code="task_field_invalid",
        )
    if any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in value):
        raise WorkflowError(f"{field} bevat verboden besturingstekens.", code="task_field_invalid")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise WorkflowError(f"{field} gebruikt een ongeldig formaat.", code="task_field_invalid")
    return value


def _task_id(value: object) -> str:
    return _short_text(value, field="Taak-ID", maximum=32, pattern=TASK_ID_PATTERN)


def _actor_id(value: object) -> str:
    return _short_text(value, field="Actor-ID", maximum=120, pattern=ACTOR_ID_PATTERN)


def _text_list(values: Sequence[str], *, field: str, required: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise WorkflowError(f"{field} moet een lijst zijn.", code="task_field_invalid")
    if required and not values:
        raise WorkflowError(f"{field} vereist minimaal één waarde.", code="task_field_invalid")
    if len(values) > MAX_LIST_ITEMS:
        raise WorkflowError(f"{field} bevat te veel waarden.", code="task_field_invalid")
    normalized = tuple(_short_text(value, field=field) for value in values)
    if len(set(normalized)) != len(normalized):
        raise WorkflowError(f"{field} bevat dubbele waarden.", code="task_field_invalid")
    return normalized


def _safe_relative(value: str, *, field: str) -> Path:
    text = _short_text(value, field=field, maximum=500)
    if "\\" in text:
        raise WorkflowError(
            f"{field} gebruikt geen draagbaar relatief pad.",
            code="task_input_path_invalid",
        )
    relative = Path(text)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise WorkflowError(
            f"{field} moet binnen de werkruimte blijven.",
            code="task_input_path_invalid",
        )
    return relative


def _assert_no_symlink(root: Path, relative: Path, *, code: str) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise WorkflowError(
                f"Beheerd pad is niet beschikbaar: {relative.as_posix()}", code=code
            ) from exc
        if stat.S_ISLNK(mode):
            raise WorkflowError(f"Symlink geweigerd: {relative.as_posix()}", code=code)
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkflowError(f"Pad verlaat de werkruimte: {relative.as_posix()}", code=code) from exc
    return resolved


def _hash_file(path: Path, *, maximum: int, code: str) -> tuple[int, str]:
    try:
        before = path.stat()
    except OSError as exc:
        raise WorkflowError(f"Bestand is niet leesbaar: {path.name}", code=code) from exc
    if not stat.S_ISREG(before.st_mode):
        raise WorkflowError(f"Alleen reguliere bestanden zijn toegestaan: {path.name}", code=code)
    if before.st_size > maximum:
        raise WorkflowError(f"Bestand overschrijdt het toegestane budget: {path.name}", code=code)
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with path.open("rb") as source:
            while chunk := source.read(COPY_CHUNK_SIZE):
                byte_count += len(chunk)
                if byte_count > maximum:
                    raise WorkflowError(
                        f"Bestand overschrijdt het toegestane budget: {path.name}", code=code
                    )
                digest.update(chunk)
        after = path.stat()
    except WorkflowError:
        raise
    except OSError as exc:
        raise WorkflowError(
            f"Bestand kon niet volledig worden gelezen: {path.name}", code=code
        ) from exc
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or byte_count != before.st_size:
        raise WorkflowError(f"Bestand veranderde tijdens controle: {path.name}", code=code)
    return byte_count, digest.hexdigest()


def _input_record(root: Path, relative_text: str) -> dict[str, object]:
    relative = _safe_relative(relative_text, field="Inputpad")
    if relative.parts[0] not in INPUT_ROOTS:
        raise WorkflowError(
            f"Inputpad valt buiten de officiële invoermappen: {relative.as_posix()}",
            code="task_input_path_invalid",
        )
    path = _assert_no_symlink(root, relative, code="task_input_unsafe")
    byte_count, sha256 = _hash_file(path, maximum=MAX_INPUT_BYTES, code="task_input_unavailable")
    return {"path": relative.as_posix(), "bytes": byte_count, "sha256": sha256}


def _write_new(path: Path, content: bytes) -> None:
    try:
        write_new_bytes(path, content, mode=0o600, private=True)
    except FileExistsError as exc:
        raise WorkflowError(
            f"Bestaand taakbewijs wordt niet overschreven: {path.name}",
            code="task_record_exists",
        ) from exc
    except OSError as exc:
        raise WorkflowError(
            f"Taakbewijs kon niet veilig worden geschreven: {path.name}",
            code="task_write_failed",
        ) from exc


def _write_atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}-{uuid4().hex}.tmp")
    try:
        _write_new(temporary, content)
        os.replace(temporary, path)
    except WorkflowError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise WorkflowError(
            f"Afgeleide taakkaart kon niet atomair worden vervangen: {path.name}",
            code="task_view_write_failed",
        ) from exc


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WorkflowError(
                f"Taakrecord bevat dubbel JSON-veld: {key}", code="task_record_invalid"
            )
        value[key] = item
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise WorkflowError(
            f"Taakrecord is niet leesbaar: {path.name}", code="task_record_unavailable"
        ) from exc
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except WorkflowError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(
            f"Taakrecord is geen geldige UTF-8 JSON: {path.name}",
            code="task_record_invalid",
        ) from exc
    if not isinstance(value, dict):
        raise WorkflowError(
            f"Taakrecord moet een JSON-object zijn: {path.name}",
            code="task_record_invalid",
        )
    return value


def _validate_payload(event_type: str, payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS[event_type]:
        raise WorkflowError(
            f"Onbekende of ontbrekende velden in {event_type}-payload.",
            code="task_record_invalid",
        )
    if event_type == "proposal":
        for field in (
            "title",
            "goal",
            "definition_of_done",
            "executor_role",
            "expected_output",
        ):
            _short_text(payload[field], field=field)
        for field in ("allowed_actions", "forbidden_actions", "acceptance_criteria"):
            values = payload[field]
            if not isinstance(values, list):
                raise WorkflowError(f"{field} moet een lijst zijn.", code="task_record_invalid")
            _text_list(values, field=field, required=True)
        inputs = payload["inputs"]
        if not isinstance(inputs, list) or not inputs or len(inputs) > MAX_LIST_ITEMS:
            raise WorkflowError("Voorstelinputs zijn ongeldig.", code="task_record_invalid")
        paths: list[str] = []
        for item in inputs:
            _validate_artifact_record(item, label="Input")
            paths.append(item["path"])
        if len(set(paths)) != len(paths):
            raise WorkflowError("Voorstel bevat dubbele inputs.", code="task_record_invalid")
    elif event_type == "owner-approval":
        _validate_digest(payload["proposal_digest"], field="Voorsteldigest")
        if payload["decision"] != "APPROVE":
            raise WorkflowError("OWNER-goedkeuring is ongeldig.", code="task_record_invalid")
    elif event_type == "execution-begun":
        _validate_digest(payload["proposal_digest"], field="Voorsteldigest")
        _validate_digest(payload["approval_record_digest"], field="Goedkeuringsrecorddigest")
    elif event_type == "result":
        _validate_digest(payload["proposal_digest"], field="Voorsteldigest")
        _validate_digest(payload["execution_record_digest"], field="Uitvoeringsrecorddigest")
        _validate_artifact_record(payload["result"], label="Resultaat")
        evidence = payload["evidence"]
        if not isinstance(evidence, list) or len(evidence) > MAX_LIST_ITEMS:
            raise WorkflowError("Bewijslijst is ongeldig.", code="task_record_invalid")
        for item in evidence:
            _validate_artifact_record(item, label="Bewijs")
        for field in ("limitations", "open_questions"):
            values = payload[field]
            if not isinstance(values, list):
                raise WorkflowError(f"{field} moet een lijst zijn.", code="task_record_invalid")
            _text_list(values, field=field)
    elif event_type == "architect-review":
        _validate_digest(payload["result_digest"], field="Resultaatdigest")
        if payload["outcome"] not in {"PASS", "RETURN"}:
            raise WorkflowError("Controle-uitkomst is ongeldig.", code="task_record_invalid")
        findings = payload["findings"]
        if not isinstance(findings, list):
            raise WorkflowError(
                "Controlebevindingen moeten een lijst zijn.", code="task_record_invalid"
            )
        _text_list(findings, field="Controlebevindingen", required=True)
    elif event_type == "owner-acceptance":
        _validate_digest(payload["result_digest"], field="Resultaatdigest")
        _validate_digest(payload["review_digest"], field="Controledigest")
        if payload["decision"] not in {"ACCEPT", "RETURN"}:
            raise WorkflowError("OWNER-aanvaarding is ongeldig.", code="task_record_invalid")
    elif event_type == "closure":
        for field in PAYLOAD_KEYS["closure"]:
            _validate_digest(payload[field], field=field)
    elif event_type == "attempt":
        _validate_digest(payload["proposal_digest"], field="Voorsteldigest")
        if type(payload["attempt_number"]) is not int or payload["attempt_number"] < 1:
            raise WorkflowError("Pogingnummer is ongeldig.", code="task_record_invalid")
        _short_text(payload["error_code"], field="Foutcode", maximum=64, pattern=ERROR_CODE_PATTERN)
        _short_text(payload["error_signature"], field="Foutsignatuur", maximum=256)
        _short_text(payload["new_basis"], field="Nieuwe basis")
    elif event_type == "objective-attempt":
        _validate_digest(payload["proposal_digest"], field="Voorsteldigest")
        attempt_number = payload["attempt_number"]
        if type(attempt_number) is not int or attempt_number < 1:
            raise WorkflowError("Pogingnummer is ongeldig.", code="task_record_invalid")
        _short_text(
            payload["executor_id"],
            field="Uitvoerder-ID",
            maximum=40,
            pattern=EXECUTOR_ID_PATTERN,
        )
        for field in (
            "executor_record_digest",
            "context_manifest_digest",
            "error_fingerprint",
            "basis_digest",
        ):
            _validate_digest(payload[field], field=field)
        _short_text(
            payload["allowed_action"],
            field="Toegestane actie",
            maximum=64,
            pattern=ACTION_TOKEN_PATTERN,
        )
        try:
            normalize_command_type(payload["command_type"])
            normalize_target(payload["target"])
            normalize_exit_status(payload["exit_status"])
            normalize_error_class(payload["error_class"])
            normalize_actions_used(payload["actions_used"])
            normalize_duration_ms(payload["duration_ms"])
        except AttemptError as exc:
            raise WorkflowError(str(exc), code="task_record_invalid") from exc
        inputs = payload["inputs"]
        if not isinstance(inputs, list) or not inputs or len(inputs) > MAX_LIST_ITEMS:
            raise WorkflowError("Poginginputs zijn ongeldig.", code="task_record_invalid")
        input_paths: list[str] = []
        for item in inputs:
            _validate_artifact_record(item, label="Poginginput")
            input_paths.append(item["path"])
        if input_paths != sorted(input_paths) or len(set(input_paths)) != len(input_paths):
            raise WorkflowError("Poginginputs zijn niet canoniek.", code="task_record_invalid")
        result_evidence = _validate_artifact_record(
            payload["result_evidence"], label="Pogingresultaatbewijs"
        )
        expected_result_path = f"artifacts/attempt-{attempt_number:04d}-result.bin"
        if result_evidence["path"] != expected_result_path:
            raise WorkflowError("Pogingresultaatpad is ongeldig.", code="task_record_invalid")
        new_evidence = payload["new_evidence"]
        if new_evidence is not None:
            _validate_artifact_record(new_evidence, label="Nieuw pogingbewijs")
            expected_new_path = f"artifacts/attempt-{attempt_number:04d}-new-evidence.bin"
            if new_evidence["path"] != expected_new_path:
                raise WorkflowError("Nieuw-bewijspad is ongeldig.", code="task_record_invalid")
        if payload["basis_status"] not in {
            "INITIAL",
            "INPUT_DIGEST_CHANGED",
            "NEW_EVIDENCE",
        }:
            raise WorkflowError("Pogingbasisstatus is ongeldig.", code="task_record_invalid")
        for field, maximum in (
            ("cumulative_attempts", MAX_TOTAL_ATTEMPTS),
            (
                "cumulative_actions",
                MAX_CUMULATIVE_ACTIONS * MAX_TOTAL_ATTEMPTS,
            ),
            (
                "cumulative_duration_ms",
                MAX_CUMULATIVE_DURATION_MS * MAX_TOTAL_ATTEMPTS,
            ),
        ):
            value = payload[field]
            minimum = 0 if field == "cumulative_duration_ms" else 1
            if type(value) is not int or value < minimum or value > maximum:
                raise WorkflowError("Pogingbudget is ongeldig.", code="task_record_invalid")
        reached = payload["reached_limits"]
        if (
            not isinstance(reached, list)
            or any(item not in BLOCK_PRIORITY for item in reached)
            or reached != [item for item in BLOCK_PRIORITY if item in reached]
            or len(set(reached)) != len(reached)
        ):
            raise WorkflowError("Poginggrenzen zijn ongeldig.", code="task_record_invalid")
        block_reason = payload["block_reason"]
        if block_reason != (reached[0] if reached else None):
            raise WorkflowError("Pogingblokkade is ongeldig.", code="task_record_invalid")
    elif event_type == "cancellation":
        _validate_digest(payload["proposal_digest"], field="Voorsteldigest")
        _short_text(payload["reason"], field="Reden")
    elif event_type == "superseded":
        _validate_digest(payload["proposal_digest"], field="Voorsteldigest")
        _task_id(payload["replacement_task_id"])
        _short_text(payload["reason"], field="Reden")
    return payload


def _validate_artifact_record(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"path", "bytes", "sha256"}:
        raise WorkflowError(f"{label}record is ongeldig.", code="task_record_invalid")
    _safe_relative(value["path"], field=f"{label}pad")
    if type(value["bytes"]) is not int or value["bytes"] < 0:
        raise WorkflowError(f"{label}bytes zijn ongeldig.", code="task_record_invalid")
    _validate_digest(value["sha256"], field=f"{label}digest")
    return value


def _validate_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise WorkflowError(f"{field} is geen geldige SHA-256.", code="task_record_invalid")
    return value


def _event_filename(number: int, event_type: str) -> str:
    return f"{number:04d}-{event_type}.json"


def _validate_event(
    path: Path,
    value: dict[str, Any],
    *,
    expected_task_id: str,
    expected_number: int,
    previous: TaskEvent | None,
) -> TaskEvent:
    if set(value) != EVENT_KEYS:
        raise WorkflowError(
            f"Taakrecord heeft onbekende of ontbrekende velden: {path.name}",
            code="task_record_invalid",
        )
    if value["format"] != TASK_FORMAT or value["format_version"] != TASK_FORMAT_VERSION:
        raise WorkflowError(
            f"Taakrecord gebruikt een onbekend formaat: {path.name}",
            code="task_record_invalid",
        )
    task_id = _task_id(value["task_id"])
    if task_id != expected_task_id:
        raise WorkflowError("Taak-ID en taakdirectory verschillen.", code="task_record_invalid")
    revision = value["revision"]
    number = value["event_number"]
    event_type = value["event_type"]
    if revision != 1 or type(revision) is not int:
        raise WorkflowError(
            "Alleen taakrevisie 1 is in deze versie geldig.", code="task_record_invalid"
        )
    if type(number) is not int or number != expected_number:
        raise WorkflowError("Taakevents zijn niet exact opeenvolgend.", code="task_record_invalid")
    if not isinstance(event_type, str) or event_type not in EVENT_SPECS:
        raise WorkflowError("Onbekend taakevent.", code="task_record_invalid")
    if path.name != _event_filename(number, event_type):
        raise WorkflowError("Eventnaam en eventinhoud verschillen.", code="task_record_invalid")
    from_status = value["from_status"]
    to_status = value["to_status"]
    actor_role = value["actor_role"]
    actor_id = _actor_id(value["actor_id"])
    expected_from, allowed_to, expected_actor = EVENT_SPECS[event_type]
    if to_status not in ALL_STATUSES or to_status not in allowed_to:
        raise WorkflowError("Ongeldige taakstatusovergang.", code="task_transition_invalid")
    if actor_role != expected_actor:
        raise WorkflowError("Event gebruikt niet de vereiste actorrol.", code="task_actor_invalid")
    if event_type in {"cancellation", "superseded"}:
        if previous is None or previous.to_status in {"CLOSED", "CANCELLED", "SUPERSEDED"}:
            raise WorkflowError(
                "Terminale taak kan niet opnieuw wijzigen.", code="task_transition_invalid"
            )
        if from_status != previous.to_status:
            raise WorkflowError(
                "Event begint niet bij de actuele status.", code="task_transition_invalid"
            )
    else:
        if from_status != expected_from:
            raise WorkflowError(
                "Event heeft een ongeldige beginstatus.", code="task_transition_invalid"
            )
        if previous is None:
            if event_type != "proposal":
                raise WorkflowError(
                    "Eerste event moet een voorstel zijn.", code="task_transition_invalid"
                )
        elif from_status != previous.to_status:
            raise WorkflowError("Event slaat een taakstatus over.", code="task_transition_invalid")
    previous_digest = value["previous_record_digest"]
    if previous is None:
        if previous_digest is not None:
            raise WorkflowError(
                "Eerste event mag geen vorige digest hebben.", code="task_record_invalid"
            )
    elif previous_digest != previous.record_digest:
        raise WorkflowError("Taakrecordketen is onderbroken.", code="task_record_digest_mismatch")
    _validate_digest(value["object_digest"], field="Objectdigest")
    _validate_digest(value["record_digest"], field="Recorddigest")
    payload = _validate_payload(event_type, value["payload"])
    if value["object_digest"] != _digest(payload):
        raise WorkflowError("Objectdigest komt niet overeen.", code="task_object_digest_mismatch")
    record_without_digest = {key: item for key, item in value.items() if key != "record_digest"}
    if value["record_digest"] != _digest(record_without_digest):
        raise WorkflowError("Recorddigest komt niet overeen.", code="task_record_digest_mismatch")
    if not isinstance(value["created_at"], str) or not value["created_at"].endswith("Z"):
        raise WorkflowError(
            "Eventtijd gebruikt geen geldige UTC-notatie.", code="task_record_invalid"
        )
    try:
        parsed_time = datetime.fromisoformat(value["created_at"].removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise WorkflowError(
            "Eventtijd gebruikt geen geldige UTC-notatie.", code="task_record_invalid"
        ) from exc
    if parsed_time.tzinfo != UTC:
        raise WorkflowError(
            "Eventtijd gebruikt geen geldige UTC-notatie.", code="task_record_invalid"
        )
    return TaskEvent(
        event_number=number,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_role=actor_role,
        actor_id=actor_id,
        object_digest=value["object_digest"],
        record_digest=value["record_digest"],
        payload=payload,
        path=path,
    )


def _event(chain: TaskChain, event_type: str) -> TaskEvent:
    matches = [event for event in chain.events if event.event_type == event_type]
    if len(matches) != 1:
        raise WorkflowError(
            f"Taak vereist exact één event van type {event_type}.",
            code="task_record_invalid",
        )
    return matches[0]


def _validate_bindings(events: Sequence[TaskEvent]) -> None:
    proposal = events[0]
    if proposal.event_type != "proposal":
        raise WorkflowError("Taak begint niet met een voorstel.", code="task_record_invalid")
    proposal_digest = proposal.object_digest
    attempt_number = 0
    consecutive_signature: str | None = None
    consecutive_count = 0
    previous_attempt_basis: str | None = None
    objective_attempts: list[dict[str, Any]] = []
    saw_legacy_attempt = False
    for index, event in enumerate(events[1:], start=1):
        payload = event.payload
        if "proposal_digest" in payload and payload["proposal_digest"] != proposal_digest:
            raise WorkflowError(
                "Event bindt niet aan het taakvoorstel.", code="task_binding_invalid"
            )
        if event.event_type == "owner-approval":
            if payload["decision"] != "APPROVE":
                raise WorkflowError(
                    "Goedkeuring bevat geen APPROVE-besluit.", code="task_binding_invalid"
                )
        elif event.event_type == "execution-begun":
            approval = events[index - 1]
            if (
                approval.event_type != "owner-approval"
                or payload["approval_record_digest"] != approval.record_digest
            ):
                raise WorkflowError(
                    "Uitvoering bindt niet aan de OWNER-goedkeuring.", code="task_binding_invalid"
                )
        elif event.event_type == "result":
            begun = next(
                (item for item in reversed(events[:index]) if item.event_type == "execution-begun"),
                None,
            )
            if begun is None or payload["execution_record_digest"] != begun.record_digest:
                raise WorkflowError(
                    "Resultaat bindt niet aan de uitvoering.", code="task_binding_invalid"
                )
        elif event.event_type == "architect-review":
            result = next(
                (item for item in reversed(events[:index]) if item.event_type == "result"), None
            )
            if result is None or payload["result_digest"] != result.object_digest:
                raise WorkflowError(
                    "Controle bindt niet aan het resultaat.", code="task_binding_invalid"
                )
            outcome = payload["outcome"]
            expected_status = "AWAITING_OWNER_ACCEPTANCE" if outcome == "PASS" else "RETURNED"
            if outcome not in {"PASS", "RETURN"} or event.to_status != expected_status:
                raise WorkflowError(
                    "Controle-uitkomst en status verschillen.", code="task_binding_invalid"
                )
        elif event.event_type == "owner-acceptance":
            result = _find_before(events, index, "result")
            review = _find_before(events, index, "architect-review")
            if (
                payload["result_digest"] != result.object_digest
                or payload["review_digest"] != review.object_digest
            ):
                raise WorkflowError(
                    "OWNER-aanvaarding bindt niet aan resultaat en controle.",
                    code="task_binding_invalid",
                )
            decision = payload["decision"]
            expected_status = "OWNER_ACCEPTED" if decision == "ACCEPT" else "RETURNED"
            if decision not in {"ACCEPT", "RETURN"} or event.to_status != expected_status:
                raise WorkflowError(
                    "OWNER-besluit en status verschillen.", code="task_binding_invalid"
                )
        elif event.event_type == "closure":
            expected_digests = {
                "proposal_digest": proposal_digest,
                "approval_digest": _find_before(events, index, "owner-approval").object_digest,
                "result_digest": _find_before(events, index, "result").object_digest,
                "review_digest": _find_before(events, index, "architect-review").object_digest,
                "acceptance_digest": _find_before(events, index, "owner-acceptance").object_digest,
            }
            if payload != expected_digests:
                raise WorkflowError(
                    "Sluitingsbewijs bindt niet alle vereiste digests.", code="task_binding_invalid"
                )
        elif event.event_type == "attempt":
            if objective_attempts:
                raise WorkflowError(
                    "Legacy- en objectieve pogingen mogen niet worden gemengd.",
                    code="task_binding_invalid",
                )
            saw_legacy_attempt = True
            attempt_number += 1
            if payload["attempt_number"] != attempt_number:
                raise WorkflowError(
                    "Pogingnummers zijn niet opeenvolgend.", code="task_binding_invalid"
                )
            signature = payload["error_signature"]
            if signature == consecutive_signature:
                if payload["new_basis"] == previous_attempt_basis:
                    raise WorkflowError(
                        "Herhaalde foutpoging bevat geen gewijzigde basis.",
                        code="task_binding_invalid",
                    )
                consecutive_count += 1
            else:
                consecutive_signature = signature
                consecutive_count = 1
            previous_attempt_basis = payload["new_basis"]
            expected = "BLOCKED" if consecutive_count >= 3 else "IN_EXECUTION"
            if event.to_status != expected:
                raise WorkflowError(
                    "Pogingbewijs en blokkadestatus verschillen.", code="task_binding_invalid"
                )
        elif event.event_type == "objective-attempt":
            if saw_legacy_attempt:
                raise WorkflowError(
                    "Legacy- en objectieve pogingen mogen niet worden gemengd.",
                    code="task_binding_invalid",
                )
            objective_attempts.append(payload)
            try:
                validate_objective_attempt_sequence(objective_attempts)
            except AttemptError as exc:
                raise WorkflowError(str(exc), code="task_binding_invalid") from exc
            expected = "BLOCKED" if payload["block_reason"] is not None else "IN_EXECUTION"
            if event.to_status != expected:
                raise WorkflowError(
                    "Objectief pogingbewijs en blokkadestatus verschillen.",
                    code="task_binding_invalid",
                )


def _find_before(events: Sequence[TaskEvent], index: int, event_type: str) -> TaskEvent:
    found = next((item for item in reversed(events[:index]) if item.event_type == event_type), None)
    if found is None:
        raise WorkflowError(f"Vereist event ontbreekt: {event_type}.", code="task_record_invalid")
    return found


def _task_directory(root: Path, task_id: str) -> Path:
    return root / "TASKS" / _task_id(task_id)


def _load_chain(root: Path, task_id: str) -> TaskChain:
    task_id = _task_id(task_id)
    task_directory = _task_directory(root, task_id)
    relative = Path("TASKS") / task_id
    resolved = _assert_no_symlink(root, relative, code="task_path_unsafe")
    if not resolved.is_dir():
        raise WorkflowError("Taakpad is geen directory.", code="task_path_unsafe")
    try:
        layout = {child.name: child for child in resolved.iterdir()}
    except OSError as exc:
        raise WorkflowError("Taakdirectory is niet leesbaar.", code="task_path_unsafe") from exc
    if set(layout) != {"events", "artifacts", "TASK.md"}:
        raise WorkflowError("Taakdirectory bevat onbekende inhoud.", code="task_path_unsafe")
    if layout["TASK.md"].is_symlink() or not layout["TASK.md"].is_file():
        raise WorkflowError("TASK.md is geen veilig regulier bestand.", code="task_path_unsafe")
    events_directory = resolved / "events"
    if not events_directory.is_dir() or events_directory.is_symlink():
        raise WorkflowError("Taak mist een veilige events-directory.", code="task_path_unsafe")
    files = sorted(events_directory.iterdir(), key=lambda item: item.name)
    if not files:
        raise WorkflowError("Taak bevat geen events.", code="task_record_invalid")
    events: list[TaskEvent] = []
    for expected_number, path in enumerate(files, start=1):
        if (
            path.is_symlink()
            or not path.is_file()
            or EVENT_FILE_PATTERN.fullmatch(path.name) is None
        ):
            raise WorkflowError(
                "Events-directory bevat onbekende inhoud.", code="task_record_invalid"
            )
        event = _validate_event(
            path,
            _read_json(path),
            expected_task_id=task_id,
            expected_number=expected_number,
            previous=events[-1] if events else None,
        )
        events.append(event)
    _validate_bindings(events)
    chain = TaskChain(
        task_id=task_id,
        revision=1,
        status=events[-1].to_status,
        directory=task_directory,
        events=tuple(events),
    )
    _validate_artifact_inventory(chain)
    return chain


def _validate_artifact_inventory(chain: TaskChain) -> None:
    artifacts = chain.directory / "artifacts"
    if artifacts.is_symlink() or not artifacts.is_dir():
        raise WorkflowError("Taak mist een veilige artifacts-directory.", code="task_path_unsafe")
    expected: set[str] = set()
    for event in chain.events:
        if event.event_type != "objective-attempt":
            continue
        records = [event.payload["result_evidence"]]
        if event.payload["new_evidence"] is not None:
            records.append(event.payload["new_evidence"])
        expected.update(Path(record["path"]).name for record in records)
    result = next((event for event in chain.events if event.event_type == "result"), None)
    if result is not None:
        records = [result.payload["result"], *result.payload["evidence"]]
        expected.update(Path(record["path"]).name for record in records)
    try:
        children = list(artifacts.iterdir())
    except OSError as exc:
        raise WorkflowError(
            "Artifacts-directory is niet leesbaar.", code="task_path_unsafe"
        ) from exc
    actual: set[str] = set()
    for child in children:
        if child.is_symlink() or not child.is_file():
            raise WorkflowError(
                "Artifacts-directory bevat onveilige inhoud.", code="task_artifact_unsafe"
            )
        actual.add(child.name)
    if actual != expected:
        raise WorkflowError(
            "Artifacts-directory bevat ontbrekende of onbekende inhoud.",
            code="task_artifact_inventory_mismatch",
        )


def _task_directories(root: Path) -> list[Path]:
    tasks = root / "TASKS"
    directories: list[Path] = []
    try:
        children = sorted(tasks.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise WorkflowError("TASKS is niet leesbaar.", code="task_path_unsafe") from exc
    for child in children:
        if child.name.startswith(".task-") and child.name.endswith(".tmp"):
            raise WorkflowError(
                "TASKS bevat een onvoltooide stagingdirectory; controleer deze vóór nieuw werk.",
                code="task_staging_incomplete",
            )
        if (
            child.is_symlink()
            or not child.is_dir()
            or TASK_ID_PATTERN.fullmatch(child.name) is None
        ):
            raise WorkflowError(
                "TASKS bevat onbekende of onveilige inhoud.", code="task_path_unsafe"
            )
        directories.append(child)
    return directories


def _ensure_single_active(root: Path) -> None:
    for directory in _task_directories(root):
        chain = _load_chain(root, directory.name)
        if chain.status not in TERMINAL_FOR_NEW_TASK:
            raise WorkflowError(
                f"Taak {chain.task_id} is nog niet definitief afgesloten.",
                code="task_active_exists",
            )


def _new_event_value(
    chain: TaskChain | None,
    *,
    task_id: str,
    event_type: str,
    to_status: str,
    actor_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    expected_from, allowed_to, actor_role = EVENT_SPECS[event_type]
    previous = chain.events[-1] if chain else None
    from_status = previous.to_status if previous else None
    if event_type not in {"cancellation", "superseded"} and from_status != expected_from:
        raise WorkflowError(
            f"{event_type} is niet toegestaan vanuit {from_status or 'geen status'}.",
            code="task_transition_invalid",
        )
    if event_type in {"cancellation", "superseded"} and (
        chain is None or chain.status in {"CLOSED", "CANCELLED", "SUPERSEDED"}
    ):
        raise WorkflowError(
            "Terminale taak kan niet opnieuw wijzigen.", code="task_transition_invalid"
        )
    if to_status not in allowed_to:
        raise WorkflowError("Doelstatus is niet toegestaan.", code="task_transition_invalid")
    object_digest = _digest(payload)
    value: dict[str, Any] = {
        "format": TASK_FORMAT,
        "format_version": TASK_FORMAT_VERSION,
        "task_id": task_id,
        "revision": 1,
        "event_number": 1 if previous is None else previous.event_number + 1,
        "event_type": event_type,
        "from_status": from_status,
        "to_status": to_status,
        "actor_role": actor_role,
        "actor_id": _actor_id(actor_id),
        "created_at": _timestamp(_utc_now()),
        "previous_record_digest": None if previous is None else previous.record_digest,
        "object_digest": object_digest,
        "payload": payload,
    }
    value["record_digest"] = _digest(value)
    return value


def _task_view_bytes(chain: TaskChain, *, legacy: bool = False) -> bytes:
    proposal = chain.events[0].payload
    latest = chain.events[-1]
    lines = [
        f"# {'Taak' if legacy else 'Task'} {chain.task_id}",
        "",
        (
            "> Gegenereerde taakkaart uit de gevalideerde append-only events. De JSON-events"
            if legacy
            else "> Generated task card from validated append-only events. The JSON events"
        ),
        (
            "> zijn leidend; deze kaart verleent geen OWNER-bevoegdheid."
            if legacy
            else "> are authoritative; this card grants no OWNER authority."
        ),
        "",
        "## Actuele staat" if legacy else "## Current state",
        "",
        f"- {'Revisie' if legacy else 'Revision'}: {chain.revision}",
        f"- Status: {chain.status}",
        f"- {'Laatste actorrol' if legacy else 'Latest actor role'}: {latest.actor_role}",
        f"- {'Laatste actor-ID' if legacy else 'Latest actor ID'}: {_markdown_inline(latest.actor_id)}",
        f"- {'Laatste eventdigest' if legacy else 'Latest event digest'}: `{latest.record_digest}`",
        "",
        "## Opdracht" if legacy else "## Assignment",
        "",
        f"- {'Titel' if legacy else 'Title'}: {_markdown_inline(proposal['title'])}",
        f"- {'Doel' if legacy else 'Goal'}: {_markdown_inline(proposal['goal'])}",
        f"- Definition of Done: {_markdown_inline(proposal['definition_of_done'])}",
        f"- {'Uitvoerderrol' if legacy else 'Executor role'}: {_markdown_inline(proposal['executor_role'])}",
        f"- {'Verwachte output' if legacy else 'Expected output'}: {_markdown_inline(proposal['expected_output'])}",
        "",
        "## Gepinde inputs" if legacy else "## Pinned inputs",
        "",
    ]
    for item in proposal["inputs"]:
        lines.append(
            f"- {'Pad' if legacy else 'Path'}: {_markdown_inline(item['path'])} "
            f"{'—' if legacy else '-'} {item['bytes']} bytes {'—' if legacy else '-'} "
            f"SHA-256 `{item['sha256']}`"
        )
    lines.extend(["", "## Toegestane acties" if legacy else "## Allowed actions", ""])
    lines.extend(f"- {_markdown_inline(item)}" for item in proposal["allowed_actions"])
    lines.extend(["", "## Verboden acties" if legacy else "## Forbidden actions", ""])
    lines.extend(f"- {_markdown_inline(item)}" for item in proposal["forbidden_actions"])
    lines.extend(["", "## Acceptatiecriteria" if legacy else "## Acceptance criteria", ""])
    lines.extend(f"- {_markdown_inline(item)}" for item in proposal["acceptance_criteria"])
    lines.extend(
        [
            "",
            "## Digestketen" if legacy else "## Digest chain",
            "",
            f"- {'Voorstel' if legacy else 'Proposal'}: `{chain.proposal_digest}`",
        ]
    )
    labels = {
        "owner-approval": "OWNER-goedkeuring" if legacy else "OWNER approval",
        "result": "Resultaat" if legacy else "Result",
        "architect-review": "ARCHITECT-controle" if legacy else "ARCHITECT review",
        "owner-acceptance": "OWNER-aanvaarding" if legacy else "OWNER acceptance",
        "closure": "Afronding" if legacy else "Closure",
    }
    for event in chain.events[1:]:
        if event.event_type in labels:
            lines.append(f"- {labels[event.event_type]}: `{event.object_digest}`")
    result_event = next((event for event in chain.events if event.event_type == "result"), None)
    if result_event is not None:
        lines.extend(
            [
                "",
                "## Beperkingen en open vragen" if legacy else "## Limitations and open questions",
                "",
            ]
        )
        limitations = result_event.payload["limitations"]
        questions = result_event.payload["open_questions"]
        if limitations:
            lines.append("- Beperkingen:" if legacy else "- Limitations:")
            lines.extend(f"  - {_markdown_inline(item)}" for item in limitations)
        else:
            lines.append(
                "- Beperkingen: geen opgegeven" if legacy else "- Limitations: none provided"
            )
        if questions:
            lines.append("- Open vragen:" if legacy else "- Open questions:")
            lines.extend(f"  - {_markdown_inline(item)}" for item in questions)
        else:
            lines.append(
                "- Open vragen: geen opgegeven" if legacy else "- Open questions: none provided"
            )
    attempts = [event for event in chain.events if event.event_type == "attempt"]
    if attempts:
        lines.extend(["", "## Pogingen en blokkades" if legacy else "## Attempts and blocks", ""])
        for attempt in attempts:
            payload = attempt.payload
            lines.append(
                f"- {'Poging' if legacy else 'Attempt'} {payload['attempt_number']}: "
                f"{_markdown_inline(payload['error_code'])} {'—' if legacy else '-'} "
                f"{'signatuur' if legacy else 'signature'} {_markdown_inline(payload['error_signature'])} "
                f"{'—' if legacy else '-'} {'nieuwe basis' if legacy else 'new basis'} "
                f"{_markdown_inline(payload['new_basis'])}"
            )
        if chain.status == "BLOCKED":
            lines.append(
                "- Blokkade: drie opeenvolgende gelijke foutsignaturen; OWNER-richting vereist."
                if legacy
                else "- Block: three consecutive identical error signatures; OWNER direction required."
            )
    objective_attempts = [
        event for event in chain.events if event.event_type == "objective-attempt"
    ]
    if objective_attempts:
        lines.extend(["", "## Objective attempts", ""])
        for attempt in objective_attempts:
            payload = attempt.payload
            lines.extend(
                [
                    f"- Attempt {payload['attempt_number']}: fingerprint `{payload['error_fingerprint']}`",
                    f"  - Command: `{_markdown_inline(payload['command_type'])}`",
                    f"  - Target: `{_markdown_inline(payload['target'])}`",
                    f"  - Exit status: {payload['exit_status']}",
                    f"  - Error class: `{_markdown_inline(payload['error_class'])}`",
                    f"  - Allowed action: `{_markdown_inline(payload['allowed_action'])}`",
                    f"  - Executor record: `{payload['executor_record_digest']}`",
                    f"  - Context manifest: `{payload['context_manifest_digest']}`",
                    f"  - Basis: `{payload['basis_digest']}` ({payload['basis_status']})",
                    f"  - Result evidence: `{payload['result_evidence']['sha256']}`",
                    (
                        "  - New evidence: none"
                        if payload["new_evidence"] is None
                        else f"  - New evidence: `{payload['new_evidence']['sha256']}`"
                    ),
                    (
                        "  - Budget: "
                        f"{payload['cumulative_attempts']}/{MAX_TOTAL_ATTEMPTS} attempts; "
                        f"{payload['cumulative_actions']}/{MAX_CUMULATIVE_ACTIONS} actions; "
                        f"{payload['cumulative_duration_ms']}/{MAX_CUMULATIVE_DURATION_MS} ms"
                    ),
                ]
            )
        latest_attempt = objective_attempts[-1].payload
        if chain.status == "BLOCKED":
            limits = ", ".join(latest_attempt["reached_limits"])
            lines.extend(
                [
                    f"- Primary block reason: `{latest_attempt['block_reason']}`",
                    f"- Reached limits: `{limits}`",
                    "- No in-place reset or automatic retry is available.",
                    "- OWNER direction may cancel or supersede this task with one explicit new task ID.",
                ]
            )
    lines.extend(
        [
            "",
            "## Volgende gate" if legacy else "## Next gate",
            "",
            f"- {_next_gate(chain.status, legacy=legacy)}",
            "",
        ]
    )
    body = "\n".join(lines).encode("utf-8")
    header = (
        "<!-- opencntx-task-view\n"
        f"format: {TASK_VIEW_FORMAT}\n"
        f"format_version: {TASK_VIEW_VERSION}\n"
        f"body_sha256: {hashlib.sha256(body).hexdigest()}\n"
        "-->\n"
    ).encode()
    return header + body


def _markdown_inline(value: object) -> str:
    if not isinstance(value, str):
        raise WorkflowError("Taakkaart bevat ongeldige tekst.", code="task_record_invalid")
    return html.escape(value, quote=True).replace("`", "&#96;")


def _next_gate(status: str, *, legacy: bool = False) -> str:
    current = {
        "AWAITING_OWNER_APPROVAL": "OWNER approval of exact task ID, revision, and proposal digest",
        "APPROVED_FOR_EXECUTION": "ARCHITECT may register the approved execution",
        "IN_EXECUTION": "EXECUTOR delivers exact result and evidence",
        "RESULT_READY": "ARCHITECT reviews exact result and evidence",
        "AWAITING_OWNER_ACCEPTANCE": "OWNER accepts or returns exact result and review",
        "OWNER_ACCEPTED": "ARCHITECT may write the local closure evidence",
        "CLOSED": "No continuation without a new explicit task",
        "RETURNED": "New content requires a new explicit revision",
        "BLOCKED": "OWNER direction required; no further attempt",
        "CANCELLED": "No continuation without a new explicit task",
        "SUPERSEDED": "Use only the explicitly identified newer task",
    }
    legacy_values = {
        "AWAITING_OWNER_APPROVAL": "OWNER-goedkeuring van exacte taak-ID, revisie en voorstel-digest",
        "APPROVED_FOR_EXECUTION": "ARCHITECT mag de goedgekeurde uitvoering registreren",
        "IN_EXECUTION": "UITVOERDER levert exact resultaat en bewijs",
        "RESULT_READY": "ARCHITECT controleert exact resultaat en bewijs",
        "AWAITING_OWNER_ACCEPTANCE": "OWNER aanvaardt of retourneert exact resultaat en controle",
        "OWNER_ACCEPTED": "ARCHITECT mag het lokale afrondingsbewijs schrijven",
        "CLOSED": "Geen vervolg zonder nieuwe expliciete taak",
        "RETURNED": "Nieuwe inhoud vereist een nieuwe expliciete revisie",
        "BLOCKED": "OWNER-richting vereist; geen verdere poging",
        "CANCELLED": "Geen vervolg zonder nieuwe expliciete taak",
        "SUPERSEDED": "Gebruik uitsluitend de expliciet aangewezen nieuwere taak",
    }
    return (legacy_values if legacy else current)[status]


def _view_is_managed(path: Path) -> bool:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return False
    try:
        content = path.read_bytes()
    except OSError:
        return False
    marker = b"-->\n"
    if not content.startswith(b"<!-- opencntx-task-view\n") or marker not in content:
        return False
    header, body = content.split(marker, 1)
    digest_line = next(
        (
            line
            for line in header.decode("utf-8", errors="replace").splitlines()
            if line.startswith("body_sha256: ")
        ),
        None,
    )
    if digest_line is None:
        return False
    declared = digest_line.removeprefix("body_sha256: ")
    return (
        SHA256_PATTERN.fullmatch(declared) is not None
        and hashlib.sha256(body).hexdigest() == declared
    )


def _ensure_managed_view(chain: TaskChain) -> None:
    path = chain.directory / "TASK.md"
    if not _view_is_managed(path):
        raise WorkflowError(
            "TASK.md bevat ontbrekende, handmatige of beschadigde inhoud; niets overschreven.",
            code="task_view_unmanaged",
        )
    try:
        actual = path.read_bytes()
    except OSError as exc:
        raise WorkflowError("TASK.md is niet leesbaar.", code="task_view_unmanaged") from exc
    if actual not in {
        _task_view_bytes(chain),
        _task_view_bytes(chain, legacy=True),
    }:
        raise WorkflowError(
            "TASK.md hoort niet bij het laatste gevalideerde event; niets overschreven.",
            code="task_view_stale",
        )


def _write_view(chain: TaskChain) -> None:
    _write_atomic(chain.directory / "TASK.md", _task_view_bytes(chain))


def _verify_inputs(root: Path, chain: TaskChain) -> None:
    inputs = chain.events[0].payload["inputs"]
    if not isinstance(inputs, list) or not inputs:
        raise WorkflowError("Taakvoorstel mist inputs.", code="task_record_invalid")
    for item in inputs:
        if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
            raise WorkflowError("Taakinputrecord is ongeldig.", code="task_record_invalid")
        current = _input_record(root, item["path"])
        if current != item:
            raise WorkflowError(f"Taakinput is gewijzigd: {item['path']}", code="task_input_stale")


def _write_receipt(root: Path, chain: TaskChain, status: str) -> Path:
    receipt_directory = root / ".opencntx" / "receipts"
    relative = Path(".opencntx") / "receipts"
    _assert_no_symlink(root, relative, code="task_receipt_path_unsafe")
    path = receipt_directory / f"TASK-{uuid4().hex}.json"
    latest = chain.events[-1]
    value = {
        "format": TASK_RECEIPT_FORMAT,
        "format_version": TASK_RECEIPT_VERSION,
        "status": status,
        "task_id": chain.task_id,
        "revision": chain.revision,
        "task_status": chain.status,
        "event_number": latest.event_number,
        "event_type": latest.event_type,
        "object_digest": latest.object_digest,
        "record_digest": latest.record_digest,
        "task_path": f"TASKS/{chain.task_id}/TASK.md",
        "created_at": _timestamp(_utc_now()),
    }
    _write_new(path, _json_bytes(value))
    return path


def _try_failure_receipt(
    project_root: Path,
    task_id: object,
    operation: str,
    error: WorkflowError,
) -> None:
    try:
        root = validate_workspace(project_root)
        receipt_directory = root / ".opencntx" / "receipts"
        _assert_no_symlink(
            root,
            Path(".opencntx") / "receipts",
            code="task_receipt_path_unsafe",
        )
        safe_task_id = (
            task_id if isinstance(task_id, str) and TASK_ID_PATTERN.fullmatch(task_id) else None
        )
        value = {
            "format": TASK_RECEIPT_FORMAT,
            "format_version": TASK_RECEIPT_VERSION,
            "status": "TASK_COMMAND_FAILED",
            "operation": operation,
            "task_id": safe_task_id,
            "error_code": error.code,
            "error": f"Task command failed: {error.code}.",
            "next_action": (
                "Check the reported error and retry only with corrected or demonstrably new input."
            ),
            "created_at": _timestamp(_utc_now()),
        }
        _write_new(
            receipt_directory / f"TASK-FAIL-{uuid4().hex}.json",
            _json_bytes(value),
        )
    except (WorkspaceError, OSError):
        return


def _failure_receipt(operation: str):
    def decorate(function):
        @wraps(function)
        def wrapped(project_root: Path, task_id: str, *args, **kwargs):
            try:
                return function(project_root, task_id, *args, **kwargs)
            except WorkflowError as exc:
                _try_failure_receipt(project_root, task_id, operation, exc)
                raise

        return wrapped

    return decorate


_TEST_BEFORE_TASK_LOCK = None


def _append_event(
    root: Path,
    chain: TaskChain,
    *,
    event_type: str,
    to_status: str,
    actor_id: str,
    payload: dict[str, Any],
    success_status: str,
    artifact_sources: Sequence[tuple[Path, dict[str, object]]] = (),
) -> TaskResult:
    expected_head = chain.events[-1].record_digest

    def current_head() -> str:
        event_paths = sorted((chain.directory / "events").glob("*.json"))
        if not event_paths:
            raise WorkflowError("Taakketen bevat geen events.", code="task_chain_invalid")
        value = _read_json(event_paths[-1])
        digest = value.get("record_digest")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise WorkflowError("Laatste task-head is ongeldig.", code="task_chain_invalid")
        return digest

    if _TEST_BEFORE_TASK_LOCK is not None:
        _TEST_BEFORE_TASK_LOCK()
    with writer_transaction(
        root,
        f"task-{event_type}",
        workspace=False,
        task_id=chain.task_id,
        expected_digest=expected_head,
        current_digest=current_head,
    ) as transaction:
        _ensure_managed_view(chain)
        if artifact_sources and event_type != "objective-attempt":
            raise WorkflowError(
                "Artifactpublicatie is niet toegestaan voor dit event.",
                code="task_artifact_unsafe",
            )
        for source, expected_record in artifact_sources:
            artifact_path = expected_record.get("path")
            if not isinstance(artifact_path, str):
                raise WorkflowError(
                    "Pogingartifactpad is ongeldig.",
                    code="task_artifact_unsafe",
                )
            relative = _safe_relative(artifact_path, field="Pogingartifactpad")
            if relative.parts[0] != "artifacts" or len(relative.parts) != 2:
                raise WorkflowError(
                    "Pogingartifact valt buiten de taak.",
                    code="task_artifact_unsafe",
                )
            destination = chain.directory / relative
            transaction.track_target(destination)
            actual_record = _copy_artifact(source, destination)
            if actual_record != expected_record:
                raise WorkflowError(
                    "Pogingbewijs veranderde vóór publicatie.",
                    code="task_artifact_changed",
                )
            transaction.mark_target_published(destination)
        value = _new_event_value(
            chain,
            task_id=chain.task_id,
            event_type=event_type,
            to_status=to_status,
            actor_id=actor_id,
            payload=payload,
        )
        path = chain.directory / "events" / _event_filename(value["event_number"], event_type)
        transaction.track_target(path)
        transaction.track_target(chain.directory / "TASK.md")
        _write_new(path, _json_bytes(value))
        transaction.mark_target_published(path)
        updated = _load_chain(root, chain.task_id)
        _write_view(updated)
        transaction.mark_target_published(chain.directory / "TASK.md")
        transaction.mark_published()
        receipt = _write_receipt(root, updated, success_status)
        transaction.mark_receipted(receipt)
        latest = updated.events[-1]
        return TaskResult(
            status=success_status,
            task_id=updated.task_id,
            revision=updated.revision,
            task_status=updated.status,
            object_digest=latest.object_digest,
            record_digest=latest.record_digest,
            task_path=updated.directory / "TASK.md",
            receipt_path=receipt,
        )


@_failure_receipt("propose")
def _propose_task_unlocked(
    project_root: Path,
    task_id: str,
    *,
    title: str,
    goal: str,
    definition_of_done: str,
    executor_role: str,
    input_paths: Sequence[str],
    allowed_actions: Sequence[str],
    forbidden_actions: Sequence[str],
    expected_output: str,
    acceptance_criteria: Sequence[str],
    architect: str,
    _transaction: Transaction | None = None,
) -> TaskResult:
    root = validate_workspace(project_root)
    task_id = _task_id(task_id)
    _ensure_single_active(root)
    destination = _task_directory(root, task_id)
    if destination.exists() or destination.is_symlink():
        raise WorkflowError("Taak-ID bestaat al en wordt niet hergebruikt.", code="task_exists")
    input_values = _text_list(input_paths, field="Inputs", required=True)
    input_records = [_input_record(root, item) for item in input_values]
    if len({item["path"] for item in input_records}) != len(input_records):
        raise WorkflowError("Inputs bevatten dubbele paden.", code="task_field_invalid")
    payload: dict[str, Any] = {
        "title": _short_text(title, field="Titel", maximum=120),
        "goal": _short_text(goal, field="Doel"),
        "definition_of_done": _short_text(definition_of_done, field="Definition of Done"),
        "executor_role": _short_text(executor_role, field="Uitvoerderrol", maximum=120),
        "inputs": input_records,
        "allowed_actions": list(
            _text_list(allowed_actions, field="Toegestane acties", required=True)
        ),
        "forbidden_actions": list(
            _text_list(forbidden_actions, field="Verboden acties", required=True)
        ),
        "expected_output": _short_text(expected_output, field="Verwachte output"),
        "acceptance_criteria": list(
            _text_list(acceptance_criteria, field="Acceptatiecriteria", required=True)
        ),
    }
    value = _new_event_value(
        None,
        task_id=task_id,
        event_type="proposal",
        to_status="AWAITING_OWNER_APPROVAL",
        actor_id=architect,
        payload=payload,
    )
    temporary = root / "TASKS" / f".task-{uuid4().hex}.tmp"
    try:
        temporary.mkdir(mode=0o700)
        (temporary / "events").mkdir(mode=0o700)
        (temporary / "artifacts").mkdir(mode=0o700)
        _write_new(
            temporary / "events" / _event_filename(1, "proposal"),
            _json_bytes(value),
        )
        provisional = TaskChain(
            task_id=task_id,
            revision=1,
            status="AWAITING_OWNER_APPROVAL",
            directory=temporary,
            events=(
                _validate_event(
                    temporary / "events" / _event_filename(1, "proposal"),
                    value,
                    expected_task_id=task_id,
                    expected_number=1,
                    previous=None,
                ),
            ),
        )
        _write_new(temporary / "TASK.md", _task_view_bytes(provisional))
        if _transaction is not None:
            _transaction.track_target(destination)
        os.replace(temporary, destination)
    except (WorkflowError, OSError) as exc:
        try:
            shutil.rmtree(temporary)
        except OSError:
            pass
        if isinstance(exc, WorkflowError):
            raise
        raise WorkflowError(
            "Taak kon niet atomair worden gemaakt.", code="task_write_failed"
        ) from exc
    chain = _load_chain(root, task_id)
    if _transaction is not None:
        _transaction.mark_target_published(destination)
        _transaction.mark_published()
    receipt = _write_receipt(root, chain, "TASK_PROPOSED")
    if _transaction is not None:
        _transaction.mark_receipted(receipt)
    latest = chain.events[-1]
    return TaskResult(
        status="TASK_PROPOSED",
        task_id=task_id,
        revision=1,
        task_status=chain.status,
        object_digest=latest.object_digest,
        record_digest=latest.record_digest,
        task_path=destination / "TASK.md",
        receipt_path=receipt,
    )


def propose_task(
    project_root: Path,
    task_id: str,
    *,
    title: str,
    goal: str,
    definition_of_done: str,
    executor_role: str,
    input_paths: Sequence[str],
    allowed_actions: Sequence[str],
    forbidden_actions: Sequence[str],
    expected_output: str,
    acceptance_criteria: Sequence[str],
    architect: str,
) -> TaskResult:
    root = validate_workspace(project_root)
    expected = state_digest((root / "TASKS",))
    with writer_transaction(
        root,
        "task-propose",
        expected_digest=expected,
        current_digest=lambda: state_digest((root / "TASKS",)),
    ) as transaction:
        return _propose_task_unlocked(
            root,
            task_id,
            title=title,
            goal=goal,
            definition_of_done=definition_of_done,
            executor_role=executor_role,
            input_paths=input_paths,
            allowed_actions=allowed_actions,
            forbidden_actions=forbidden_actions,
            expected_output=expected_output,
            acceptance_criteria=acceptance_criteria,
            architect=architect,
            _transaction=transaction,
        )


@_failure_receipt("approve")
def approve_task(
    project_root: Path,
    task_id: str,
    *,
    revision: int,
    proposal_digest: str,
    owner: str,
) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    _require_revision_and_proposal(chain, revision, proposal_digest)
    _verify_inputs(root, chain)
    return _append_event(
        root,
        chain,
        event_type="owner-approval",
        to_status="APPROVED_FOR_EXECUTION",
        actor_id=owner,
        payload={"proposal_digest": proposal_digest, "decision": "APPROVE"},
        success_status="TASK_APPROVED",
    )


@_failure_receipt("begin")
def begin_task(project_root: Path, task_id: str, *, architect: str) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    _verify_inputs(root, chain)
    approval = _event(chain, "owner-approval")
    return _append_event(
        root,
        chain,
        event_type="execution-begun",
        to_status="IN_EXECUTION",
        actor_id=architect,
        payload={
            "proposal_digest": chain.proposal_digest,
            "approval_record_digest": approval.record_digest,
        },
        success_status="TASK_IN_EXECUTION",
    )


def _copy_artifact(source_path: Path, destination: Path) -> dict[str, object]:
    try:
        if source_path.is_symlink():
            raise WorkflowError(
                "Symlink als resultaat of bewijs geweigerd.", code="task_artifact_unsafe"
            )
        source = source_path.resolve(strict=True)
        before = source.stat()
    except OSError as exc:
        raise WorkflowError(
            "Resultaat of bewijs is niet beschikbaar.", code="task_artifact_unavailable"
        ) from exc
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_ARTIFACT_BYTES:
        raise WorkflowError(
            "Resultaat of bewijs is geen begrensd regulier bestand.", code="task_artifact_unsafe"
        )
    temporary = destination.with_name(f".{destination.name}-{uuid4().hex}.tmp")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with source.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            while chunk := input_handle.read(COPY_CHUNK_SIZE):
                byte_count += len(chunk)
                if byte_count > MAX_ARTIFACT_BYTES:
                    raise WorkflowError(
                        "Artifact overschrijdt het budget.", code="task_artifact_too_large"
                    )
                digest.update(chunk)
                output_handle.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        after = source.stat()
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity_before != identity_after or byte_count != before.st_size:
            raise WorkflowError(
                "Artifact veranderde tijdens kopiëren.", code="task_artifact_changed"
            )
        if destination.exists() or destination.is_symlink():
            raise WorkflowError(
                "Bestaand artifact wordt niet overschreven.", code="task_artifact_exists"
            )
        os.replace(temporary, destination)
    except WorkflowError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise WorkflowError(
            "Artifact kon niet veilig worden opgeslagen.", code="task_artifact_write_failed"
        ) from exc
    return {
        "path": f"artifacts/{destination.name}",
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
    }


def _inspect_artifact(source_path: Path, destination_name: str) -> dict[str, object]:
    if (
        not destination_name
        or "/" in destination_name
        or "\\" in destination_name
        or destination_name in {".", ".."}
    ):
        raise WorkflowError(
            "Artifactdoel gebruikt geen veilige bestandsnaam.",
            code="task_artifact_unsafe",
        )
    try:
        if source_path.is_symlink():
            raise WorkflowError(
                "Symlink als resultaat of bewijs geweigerd.",
                code="task_artifact_unsafe",
            )
        source = source_path.resolve(strict=True)
    except OSError as exc:
        raise WorkflowError(
            "Resultaat of bewijs is niet beschikbaar.",
            code="task_artifact_unavailable",
        ) from exc
    byte_count, sha256 = _hash_file(
        source,
        maximum=MAX_ARTIFACT_BYTES,
        code="task_artifact_unavailable",
    )
    return {
        "path": f"artifacts/{destination_name}",
        "bytes": byte_count,
        "sha256": sha256,
    }


@_failure_receipt("submit-result")
def submit_result(
    project_root: Path,
    task_id: str,
    *,
    result_path: Path,
    evidence_paths: Sequence[Path],
    limitations: Sequence[str],
    open_questions: Sequence[str],
    executor: str,
) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    _verify_inputs(root, chain)
    if chain.status != "IN_EXECUTION":
        raise WorkflowError(
            "Resultaat is niet toegestaan in de actuele status.", code="task_transition_invalid"
        )
    _ensure_managed_view(chain)
    if len(evidence_paths) > MAX_LIST_ITEMS:
        raise WorkflowError("Te veel bewijsbestanden.", code="task_field_invalid")
    artifacts = chain.directory / "artifacts"
    created: list[Path] = []
    try:
        result_destination = artifacts / "result-r0001.bin"
        result_record = _copy_artifact(result_path, result_destination)
        created.append(result_destination)
        evidence_records: list[dict[str, object]] = []
        for number, evidence in enumerate(evidence_paths, start=1):
            destination = artifacts / f"evidence-r0001-{number:04d}.bin"
            evidence_records.append(_copy_artifact(evidence, destination))
            created.append(destination)
        execution = _event(chain, "execution-begun")
        payload = {
            "proposal_digest": chain.proposal_digest,
            "execution_record_digest": execution.record_digest,
            "result": result_record,
            "evidence": evidence_records,
            "limitations": list(_text_list(limitations, field="Beperkingen")),
            "open_questions": list(_text_list(open_questions, field="Open vragen")),
        }
    except WorkflowError:
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    expected_event = (
        chain.directory / "events" / _event_filename(chain.events[-1].event_number + 1, "result")
    )
    try:
        return _append_event(
            root,
            chain,
            event_type="result",
            to_status="RESULT_READY",
            actor_id=executor,
            payload=payload,
            success_status="TASK_RESULT_SUBMITTED",
        )
    except WorkflowError:
        if not expected_event.exists():
            for path in created:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        raise


def _artifact_records(chain: TaskChain) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in chain.events:
        if event.event_type == "objective-attempt":
            records.append(event.payload["result_evidence"])
            if event.payload["new_evidence"] is not None:
                records.append(event.payload["new_evidence"])
        elif event.event_type == "result":
            records.extend([event.payload["result"], *event.payload["evidence"]])
    return records


def _verify_artifacts(chain: TaskChain) -> None:
    records = _artifact_records(chain)
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "bytes", "sha256"}:
            raise WorkflowError("Artifactrecord is ongeldig.", code="task_record_invalid")
        relative = _safe_relative(record["path"], field="Artifactpad")
        if relative.parts[0] != "artifacts" or len(relative.parts) != 2:
            raise WorkflowError("Artifactpad valt buiten de taak.", code="task_artifact_unsafe")
        path = _assert_no_symlink(chain.directory, relative, code="task_artifact_unsafe")
        byte_count, sha256 = _hash_file(
            path, maximum=MAX_ARTIFACT_BYTES, code="task_artifact_unavailable"
        )
        if byte_count != record["bytes"] or sha256 != record["sha256"]:
            raise WorkflowError(
                "Artifactbytes of digest zijn gewijzigd.", code="task_artifact_stale"
            )


def _verify_objective_attempt_authority(root: Path, chain: TaskChain) -> None:
    from .playbook import PlaybookError, attempt_executor_binding

    for event in chain.events:
        if event.event_type != "objective-attempt":
            continue
        payload = event.payload
        try:
            binding = attempt_executor_binding(
                root,
                chain.task_id,
                executor_id=payload["executor_id"],
                allowed_action=payload["allowed_action"],
                require_active=False,
            )
        except PlaybookError as exc:
            raise WorkflowError(
                "Objectief pogingbewijs bindt niet meer aan de uitvoerder.",
                code="task_attempt_authority_stale",
            ) from exc
        if (
            binding.record_digest != payload["executor_record_digest"]
            or binding.context_manifest_digest != payload["context_manifest_digest"]
            or binding.executor_statement != event.actor_id
        ):
            raise WorkflowError(
                "Objectief pogingbewijs wijkt af van uitvoerder of context.",
                code="task_attempt_authority_stale",
            )


@_failure_receipt("review-result")
def review_result(
    project_root: Path,
    task_id: str,
    *,
    result_digest: str,
    outcome: str,
    findings: Sequence[str],
    architect: str,
) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    _verify_inputs(root, chain)
    _verify_artifacts(chain)
    result = _event(chain, "result")
    _require_exact_digest(result_digest, result.object_digest, "Resultaatdigest")
    if outcome not in {"PASS", "RETURN"}:
        raise WorkflowError(
            "Controle-uitkomst moet PASS of RETURN zijn.", code="task_field_invalid"
        )
    payload = {
        "result_digest": result.object_digest,
        "outcome": outcome,
        "findings": list(_text_list(findings, field="Controlebevindingen", required=True)),
    }
    return _append_event(
        root,
        chain,
        event_type="architect-review",
        to_status="AWAITING_OWNER_ACCEPTANCE" if outcome == "PASS" else "RETURNED",
        actor_id=architect,
        payload=payload,
        success_status="TASK_RESULT_REVIEWED",
    )


@_failure_receipt("accept-result")
def accept_result(
    project_root: Path,
    task_id: str,
    *,
    result_digest: str,
    review_digest: str,
    decision: str,
    owner: str,
) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    _verify_inputs(root, chain)
    _verify_artifacts(chain)
    result = _event(chain, "result")
    review = _event(chain, "architect-review")
    _require_exact_digest(result_digest, result.object_digest, "Resultaatdigest")
    _require_exact_digest(review_digest, review.object_digest, "Controledigest")
    if decision not in {"ACCEPT", "RETURN"}:
        raise WorkflowError("OWNER-besluit moet ACCEPT of RETURN zijn.", code="task_field_invalid")
    payload = {
        "result_digest": result.object_digest,
        "review_digest": review.object_digest,
        "decision": decision,
    }
    return _append_event(
        root,
        chain,
        event_type="owner-acceptance",
        to_status="OWNER_ACCEPTED" if decision == "ACCEPT" else "RETURNED",
        actor_id=owner,
        payload=payload,
        success_status="TASK_RESULT_ACCEPTED" if decision == "ACCEPT" else "TASK_RESULT_RETURNED",
    )


@_failure_receipt("close")
def close_task(project_root: Path, task_id: str, *, architect: str) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    _verify_inputs(root, chain)
    _verify_artifacts(chain)
    proposal = _event(chain, "proposal")
    approval = _event(chain, "owner-approval")
    result = _event(chain, "result")
    review = _event(chain, "architect-review")
    acceptance = _event(chain, "owner-acceptance")
    payload = {
        "proposal_digest": proposal.object_digest,
        "approval_digest": approval.object_digest,
        "result_digest": result.object_digest,
        "review_digest": review.object_digest,
        "acceptance_digest": acceptance.object_digest,
    }
    return _append_event(
        root,
        chain,
        event_type="closure",
        to_status="CLOSED",
        actor_id=architect,
        payload=payload,
        success_status="TASK_CLOSED",
    )


@_failure_receipt("cancel")
def cancel_task(project_root: Path, task_id: str, *, reason: str, owner: str) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    return _append_event(
        root,
        chain,
        event_type="cancellation",
        to_status="CANCELLED",
        actor_id=owner,
        payload={
            "proposal_digest": chain.proposal_digest,
            "reason": _short_text(reason, field="Reden"),
        },
        success_status="TASK_CANCELLED",
    )


@_failure_receipt("supersede")
def supersede_task(
    project_root: Path,
    task_id: str,
    *,
    replacement_task_id: str,
    reason: str,
    owner: str,
) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    replacement = _task_id(replacement_task_id)
    if replacement == chain.task_id:
        raise WorkflowError("Vervangende taak-ID moet anders zijn.", code="task_field_invalid")
    replacement_path = _task_directory(root, replacement)
    if replacement_path.exists() or replacement_path.is_symlink():
        raise WorkflowError(
            "Vervangende taak-ID bestaat al en kan geen nieuw voorstel worden.",
            code="task_exists",
        )
    return _append_event(
        root,
        chain,
        event_type="superseded",
        to_status="SUPERSEDED",
        actor_id=owner,
        payload={
            "proposal_digest": chain.proposal_digest,
            "replacement_task_id": replacement,
            "reason": _short_text(reason, field="Reden"),
        },
        success_status="TASK_SUPERSEDED",
    )


@_failure_receipt("status")
def task_status(project_root: Path, task_id: str) -> TaskResult:
    root = validate_workspace(project_root)
    chain = _load_chain(root, task_id)
    _ensure_managed_view(chain)
    _verify_inputs(root, chain)
    if _artifact_records(chain):
        _verify_artifacts(chain)
    if any(event.event_type == "objective-attempt" for event in chain.events):
        _verify_objective_attempt_authority(root, chain)
    latest = chain.events[-1]
    return TaskResult(
        status="TASK_STATUS_VALID",
        task_id=chain.task_id,
        revision=chain.revision,
        task_status=chain.status,
        object_digest=latest.object_digest,
        record_digest=latest.record_digest,
        task_path=chain.directory / "TASK.md",
        receipt_path=None,
    )


def _require_revision_and_proposal(chain: TaskChain, revision: int, digest: str) -> None:
    if type(revision) is not int or revision != chain.revision:
        raise WorkflowError("Taakrevisie komt niet overeen.", code="task_revision_mismatch")
    _require_exact_digest(digest, chain.proposal_digest, "Voorsteldigest")


def _require_exact_digest(provided: str, expected: str, field: str) -> None:
    _validate_digest(provided, field=field)
    if provided != expected:
        raise WorkflowError(f"{field} komt niet overeen.", code="task_digest_mismatch")
