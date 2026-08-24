"""Safe local registration of text derived from captured media sources."""

from __future__ import annotations

import codecs
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from .integrity import writer_transaction
from .primitives import (
    sha256_bytes,
)
from .primitives import (
    timestamp_microseconds as _timestamp,
)
from .primitives import (
    utc_now as _utc_now,
)
from .workspace import (
    CHUNK_SIZE,
    SHA256_PATTERN,
    SOURCE_ID_PATTERN,
    CaptureResult,
    StoredSource,
    WorkspaceConfig,
    WorkspaceError,
    _derived_storage_bytes,
    _hash_file,
    _source_identity,
    _stored_sources,
    capture_source,
    load_workspace_config,
    validate_workspace,
)

DERIVATION_FORMAT = "opencntx-derived-content"
DERIVATION_FORMAT_VERSION = 1
REVIEW_FORMAT = "opencntx-derived-review"
REVIEW_FORMAT_VERSION = 1
PROMOTION_FORMAT = "opencntx-derived-promotion"
PROMOTION_FORMAT_VERSION = 1
REMOVAL_FORMAT = "opencntx-derived-removal"
REMOVAL_FORMAT_VERSION = 1
MEDIA_RECEIPT_FORMAT = "opencntx-media-receipt"
MEDIA_RECEIPT_VERSION = 1

DERIVATION_ID_PATTERN = re.compile(r"DRV-\d{8}-[0-9a-f]{12}\Z")
KINDS = ("TEXT_EXTRACTION", "OCR", "TRANSCRIPT", "DESCRIPTION")
PRODUCER_CLASSES = ("HUMAN", "LOCAL_TOOL", "EXTERNAL_TOOL", "AI")
DECISIONS = ("ACCEPT", "REJECT")
MAX_SHORT_TEXT = 240
MAX_LOCATORS = 64
MAX_FINDINGS = 64

RECORD_FIELDS = {
    "content_bytes",
    "content_sha256",
    "created_at",
    "derivation_id",
    "format",
    "format_version",
    "kind",
    "locators",
    "privacy",
    "producer",
    "producer_class",
    "source_bytes",
    "source_id",
    "source_record_sha256",
    "source_sha256",
    "supersedes_derivation_id",
}
REVIEW_FIELDS = {
    "content_sha256",
    "decision",
    "derivation_id",
    "findings",
    "format",
    "format_version",
    "record_sha256",
    "reviewed_at",
    "reviewer",
    "source_id",
}
PROMOTION_FIELDS = {
    "capture_status",
    "content_sha256",
    "derivation_id",
    "format",
    "format_version",
    "promoted_at",
    "promoted_source_id",
    "promoted_source_record_sha256",
    "promoted_source_sha256",
    "record_sha256",
    "review_sha256",
    "source_id",
    "source_sha256",
}
REMOVAL_FIELDS = {
    "content_sha256",
    "derivation_id",
    "format",
    "format_version",
    "owner",
    "record_sha256",
    "removed_at",
    "source_id",
    "source_sha256",
}


def _workspace_writer(operation: str):
    def decorate(function):
        @wraps(function)
        def wrapped(project_root: Path, *args, **kwargs):
            root = validate_workspace(project_root)
            with writer_transaction(root, operation):
                return function(root, *args, **kwargs)

        return wrapped

    return decorate


DERIVATION_FILES = {
    "content.txt",
    "record.json",
    "review.json",
    "promotion.json",
    "removed.json",
}

STATUS_STATEMENTS = {
    "NOT_INVESTIGATED": "CONTENT NOT INVESTIGATED",
    "UNREVIEWED": "DERIVED TEXT NOT REVIEWED",
    "REVIEWED": "DERIVED TEXT REVIEWED, NOT AUTOMATICALLY FACT",
    "REJECTED": "DERIVED TEXT REJECTED",
    "PROMOTED": "DERIVED TEXT REVIEWED, NOT AUTOMATICALLY FACT",
    "STALE": "DERIVED TEXT STALE",
    "REMOVED": "DERIVED TEXT REMOVED",
}


class MediaError(WorkspaceError):
    """A stable, user-facing media derivation error."""


@dataclass(frozen=True)
class MediaMutationResult:
    operation: str
    status: str
    source_id: str
    derivation_id: str
    content_sha256: str
    record_sha256: str
    receipt_path: Path
    promoted_source_id: str | None = None


@dataclass(frozen=True)
class MediaStatusEntry:
    source_id: str
    derivation_id: str | None
    status: str
    statement: str
    content_sha256: str | None
    record_sha256: str | None
    review_sha256: str | None
    promoted_source_id: str | None


@dataclass(frozen=True)
class MediaVerifyReport:
    ok: bool
    entries: tuple[MediaStatusEntry, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class _ExactSource:
    stored: StoredSource
    record_sha256: str


@dataclass(frozen=True)
class _Derivation:
    directory: Path
    record: dict[str, Any]
    record_sha256: str
    review: dict[str, Any] | None
    review_sha256: str | None
    promotion: dict[str, Any] | None
    removal: dict[str, Any] | None
    status: str


@dataclass(frozen=True)
class _RegistrationPlan:
    root: Path
    source_id: str
    exact_source: _ExactSource
    config: WorkspaceConfig
    kind: str
    producer_class: str
    producer: str
    locators: tuple[str, ...]
    existing: dict[str, _Derivation]
    supersedes: str | None
    resolved_text: Path
    initial_stat: os.stat_result


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _write_new(path: Path, content: bytes) -> None:
    created = False
    try:
        with path.open("xb") as destination:
            created = True
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
    except FileExistsError as exc:
        raise MediaError(
            f"Beheerd mediabestand bestaat al: {path.name}.",
            code="media_record_exists",
        ) from exc
    except OSError as exc:
        if created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        raise MediaError(
            f"Beheerd mediabestand kon niet veilig worden geschreven: {path.name}: {exc}",
            code="media_write_failed",
        ) from exc


def _read_json(path: Path, fields: set[str], *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise MediaError(f"{label} ontbreekt of is onveilig.", code="media_record_invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MediaError(f"{label} is ongeldig.", code="media_record_invalid") from exc
    if not isinstance(value, dict) or set(value) != fields:
        raise MediaError(
            f"{label} heeft onbekende of ontbrekende velden.",
            code="media_record_invalid",
        )
    return value


def _short_text(value: object, *, field: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise MediaError(f"{field} moet tekst zijn.", code="media_input_invalid")
    normalized = value.strip()
    if (not normalized and not allow_empty) or len(normalized) > MAX_SHORT_TEXT:
        raise MediaError(f"{field} heeft een ongeldige lengte.", code="media_input_invalid")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise MediaError(f"{field} bevat onveilige tekens.", code="media_input_invalid")
    if re.match(r"^(?:[A-Za-z]:[\\/]|[/\\]{1,2})", normalized):
        raise MediaError(
            f"{field} mag geen absoluut persoonlijk pad bevatten.",
            code="media_input_invalid",
        )
    return normalized


def _text_list(
    values: object, *, field: str, maximum: int, allow_empty: bool = True
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise MediaError(f"{field} moet een lijst zijn.", code="media_input_invalid")
    if (not values and not allow_empty) or len(values) > maximum:
        raise MediaError(f"{field} heeft een ongeldige lengte.", code="media_input_invalid")
    result = tuple(_short_text(value, field=field) for value in values)
    if len(set(result)) != len(result):
        raise MediaError(f"{field} bevat dubbele waarden.", code="media_input_invalid")
    return result


def _source_id(value: object) -> str:
    if not isinstance(value, str) or SOURCE_ID_PATTERN.fullmatch(value) is None:
        raise MediaError("Ongeldige source-ID.", code="media_source_id_invalid")
    return value


def _derivation_id(value: object) -> str:
    if not isinstance(value, str) or DERIVATION_ID_PATTERN.fullmatch(value) is None:
        raise MediaError("Ongeldige derivation-ID.", code="media_derivation_id_invalid")
    return value


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise MediaError(f"Ongeldige SHA-256 voor {field}.", code="media_digest_invalid")
    return value


def _exact_source(root: Path, source_id: str, *, allow_quarantined: bool) -> _ExactSource:
    normalized = _source_id(source_id)
    stored = _stored_sources(root)
    source = stored.get(normalized)
    if source is None:
        raise MediaError(f"Onbekende bron: {normalized}.", code="media_source_unknown")
    byte_count, source_sha256 = _hash_file(source.original_path)
    if byte_count != source.byte_count or source_sha256 != source.sha256:
        raise MediaError(
            f"Originele bronbytes wijken af: {normalized}.",
            code="media_source_stale",
        )
    _, record_sha256 = _hash_file(source.record_path)
    if source.privacy == "QUARANTINED" and not allow_quarantined:
        raise MediaError(
            f"Bron {normalized} is QUARANTINED en wordt niet verwerkt.",
            code="media_source_quarantined",
        )
    return _ExactSource(stored=source, record_sha256=record_sha256)


def _derived_root(root: Path, *, create: bool) -> Path:
    opencntx = root / ".opencntx"
    if opencntx.is_symlink() or not opencntx.is_dir():
        raise MediaError(".opencntx is onveilig.", code="media_storage_invalid")
    derived = opencntx / "derived"
    if derived.exists():
        if derived.is_symlink() or not derived.is_dir():
            raise MediaError(
                ".opencntx/derived moet een veilige gewone map zijn.",
                code="media_storage_invalid",
            )
    elif create:
        try:
            derived.mkdir()
        except OSError as exc:
            raise MediaError(
                f"Afleidingsopslag kon niet worden gemaakt: {exc}",
                code="media_storage_write_failed",
            ) from exc
    return derived


def _validate_utf8_file(path: Path, expected_bytes: int, expected_sha256: str) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with path.open("rb") as source:
            while True:
                chunk = source.read(CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                byte_count += len(chunk)
                text = decoder.decode(chunk)
                if "\x00" in text or any(
                    (ord(character) < 32 and character not in "\t\n\r") or ord(character) == 127
                    for character in text
                ):
                    raise MediaError(
                        "Afgeleide tekst bevat onveilige controltekens.",
                        code="media_text_invalid",
                    )
            tail = decoder.decode(b"", final=True)
            if "\x00" in tail or any(
                (ord(character) < 32 and character not in "\t\n\r") or ord(character) == 127
                for character in tail
            ):
                raise MediaError(
                    "Afgeleide tekst bevat onveilige controltekens.",
                    code="media_text_invalid",
                )
    except MediaError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise MediaError(
            "Afgeleide tekst is niet veilig leesbaar als UTF-8.",
            code="media_text_invalid",
        ) from exc
    if byte_count != expected_bytes or digest.hexdigest() != expected_sha256:
        raise MediaError("Afgeleide tekstbytes wijken af.", code="media_content_stale")


def _validate_record(
    value: dict[str, Any], source: _ExactSource, source_id: str, derivation_id: str
) -> None:
    if (
        value.get("format") != DERIVATION_FORMAT
        or value.get("format_version") != DERIVATION_FORMAT_VERSION
        or value.get("source_id") != source_id
        or value.get("derivation_id") != derivation_id
        or value.get("source_bytes") != source.stored.byte_count
        or value.get("source_sha256") != source.stored.sha256
        or value.get("source_record_sha256") != source.record_sha256
        or value.get("privacy") != source.stored.privacy
        or value.get("kind") not in KINDS
        or value.get("producer_class") not in PRODUCER_CLASSES
        or not isinstance(value.get("content_bytes"), int)
        or isinstance(value.get("content_bytes"), bool)
        or value["content_bytes"] < 0
    ):
        raise MediaError("Afleidingsrecord is ongeldig.", code="media_record_invalid")
    _digest(value.get("content_sha256"), field="content_sha256")
    _short_text(value.get("created_at"), field="created_at")
    _short_text(value.get("producer"), field="producer")
    _text_list(value.get("locators"), field="locators", maximum=MAX_LOCATORS)
    supersedes = value.get("supersedes_derivation_id")
    if supersedes is not None:
        _derivation_id(supersedes)
        if supersedes == derivation_id:
            raise MediaError(
                "Een afleiding kan zichzelf niet vervangen.",
                code="media_supersedes_invalid",
            )


def _validate_review(value: dict[str, Any], record: dict[str, Any], record_sha256: str) -> None:
    if (
        value.get("format") != REVIEW_FORMAT
        or value.get("format_version") != REVIEW_FORMAT_VERSION
        or value.get("source_id") != record["source_id"]
        or value.get("derivation_id") != record["derivation_id"]
        or value.get("record_sha256") != record_sha256
        or value.get("content_sha256") != record["content_sha256"]
        or value.get("decision") not in DECISIONS
    ):
        raise MediaError("Reviewrecord is ongeldig.", code="media_review_invalid")
    _short_text(value.get("reviewed_at"), field="reviewed_at")
    _short_text(value.get("reviewer"), field="reviewer")
    _text_list(value.get("findings"), field="findings", maximum=MAX_FINDINGS, allow_empty=False)


def _promotion_origin(record: dict[str, Any]) -> str:
    return (
        f"DERIVED:{record['derivation_id']};ORIGINAL:{record['source_id']}"
        f"@{record['source_sha256']}"
    )


def _validate_promotion(
    root: Path,
    value: dict[str, Any],
    record: dict[str, Any],
    record_sha256: str,
    review: dict[str, Any] | None,
    review_sha256: str | None,
) -> None:
    if review is None or review.get("decision") != "ACCEPT" or review_sha256 is None:
        raise MediaError(
            "Promotie mist een geaccepteerde exacte review.",
            code="media_promotion_invalid",
        )
    if (
        value.get("format") != PROMOTION_FORMAT
        or value.get("format_version") != PROMOTION_FORMAT_VERSION
        or value.get("source_id") != record["source_id"]
        or value.get("derivation_id") != record["derivation_id"]
        or value.get("source_sha256") != record["source_sha256"]
        or value.get("record_sha256") != record_sha256
        or value.get("review_sha256") != review_sha256
        or value.get("content_sha256") != record["content_sha256"]
        or value.get("capture_status") not in {"CAPTURED", "DUPLICATE"}
    ):
        raise MediaError("Promotierecord is ongeldig.", code="media_promotion_invalid")
    _short_text(value.get("promoted_at"), field="promoted_at")
    promoted_source_id = _source_id(value.get("promoted_source_id"))
    promoted_digest = _digest(value.get("promoted_source_sha256"), field="promoted_source_sha256")
    sources = _stored_sources(root)
    promoted = sources.get(promoted_source_id)
    if promoted is None:
        raise MediaError("Gepromoveerde bron ontbreekt.", code="media_promotion_stale")
    size, digest = _hash_file(promoted.original_path)
    if (
        digest != promoted_digest
        or digest != record["content_sha256"]
        or size != record["content_bytes"]
        or promoted.privacy != record["privacy"]
    ):
        raise MediaError(
            "Gepromoveerde bronbytes of privacy wijken af.",
            code="media_promotion_stale",
        )
    promoted_record = _read_json(
        promoted.record_path,
        {
            "bytes",
            "captured_at",
            "format",
            "format_version",
            "origin",
            "original_name",
            "privacy",
            "sha256",
            "source_id",
            "status",
            "stored_path",
            "supersedes",
        },
        label="Gepromoveerd bronrecord",
    )
    _, promoted_record_sha256 = _hash_file(promoted.record_path)
    if value.get("promoted_source_record_sha256") != promoted_record_sha256:
        raise MediaError(
            "Gepromoveerd bronrecord wijkt af.",
            code="media_promotion_stale",
        )
    if value.get("capture_status") == "CAPTURED" and promoted_record.get(
        "origin"
    ) != _promotion_origin(record):
        raise MediaError(
            "Gepromoveerde bron mist de exacte mediaherkomst.",
            code="media_promotion_stale",
        )


def _validate_removal(value: dict[str, Any], record: dict[str, Any], record_sha256: str) -> None:
    if (
        value.get("format") != REMOVAL_FORMAT
        or value.get("format_version") != REMOVAL_FORMAT_VERSION
        or value.get("source_id") != record["source_id"]
        or value.get("derivation_id") != record["derivation_id"]
        or value.get("source_sha256") != record["source_sha256"]
        or value.get("record_sha256") != record_sha256
        or value.get("content_sha256") != record["content_sha256"]
    ):
        raise MediaError("Verwijderrecord is ongeldig.", code="media_removal_invalid")
    _short_text(value.get("removed_at"), field="removed_at")
    _short_text(value.get("owner"), field="owner")


def _load_derivations(root: Path, source_id: str) -> dict[str, _Derivation]:
    source = _exact_source(root, source_id, allow_quarantined=True)
    derived_root = _derived_root(root, create=False)
    if not derived_root.exists():
        return {}
    try:
        source_children = sorted(derived_root.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise MediaError(
            "Afleidingsopslag is niet leesbaar.", code="media_storage_invalid"
        ) from exc
    for child in source_children:
        if (
            child.is_symlink()
            or not child.is_dir()
            or SOURCE_ID_PATTERN.fullmatch(child.name) is None
        ):
            raise MediaError(
                "Afleidingsopslag bevat een onverwacht of onveilig bronpad.",
                code="media_storage_invalid",
            )
    source_directory = derived_root / source_id
    if not source_directory.exists():
        return {}
    derivations: dict[str, _Derivation] = {}
    try:
        children = sorted(source_directory.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise MediaError(
            "Bronafleidingen zijn niet leesbaar.", code="media_storage_invalid"
        ) from exc
    for directory in children:
        if (
            directory.is_symlink()
            or not directory.is_dir()
            or DERIVATION_ID_PATTERN.fullmatch(directory.name) is None
        ):
            raise MediaError(
                "Bronafleidingen bevatten een onverwacht of onveilig pad.",
                code="media_storage_invalid",
            )
        names = {path.name for path in directory.iterdir()}
        if not names.issubset(DERIVATION_FILES) or "record.json" not in names:
            raise MediaError(
                f"Afleiding {directory.name} bevat onverwachte of ontbrekende bestanden.",
                code="media_storage_invalid",
            )
        for path in directory.iterdir():
            if path.is_symlink() or not path.is_file():
                raise MediaError(
                    f"Afleiding {directory.name} bevat een onveilig bestand.",
                    code="media_storage_invalid",
                )
        record_path = directory / "record.json"
        record = _read_json(record_path, RECORD_FIELDS, label="Afleidingsrecord")
        _, record_sha256 = _hash_file(record_path)
        _validate_record(record, source, source_id, directory.name)

        removal: dict[str, Any] | None = None
        removal_path = directory / "removed.json"
        if removal_path.exists():
            removal = _read_json(removal_path, REMOVAL_FIELDS, label="Verwijderrecord")
            _validate_removal(removal, record, record_sha256)

        content_path = directory / "content.txt"
        if removal is None:
            if content_path.is_symlink() or not content_path.is_file():
                raise MediaError(
                    f"Afgeleide tekst ontbreekt: {directory.name}.",
                    code="media_content_stale",
                )
            _validate_utf8_file(content_path, record["content_bytes"], record["content_sha256"])
        elif content_path.exists() or content_path.is_symlink():
            raise MediaError(
                f"Verwijderde afleiding bevat nog actieve tekst: {directory.name}.",
                code="media_removal_invalid",
            )

        review: dict[str, Any] | None = None
        review_sha256: str | None = None
        review_path = directory / "review.json"
        if review_path.exists():
            review = _read_json(review_path, REVIEW_FIELDS, label="Reviewrecord")
            _, review_sha256 = _hash_file(review_path)
            _validate_review(review, record, record_sha256)

        promotion: dict[str, Any] | None = None
        promotion_path = directory / "promotion.json"
        if promotion_path.exists():
            promotion = _read_json(promotion_path, PROMOTION_FIELDS, label="Promotierecord")
            _validate_promotion(root, promotion, record, record_sha256, review, review_sha256)

        if removal is not None:
            status = "REMOVED"
        elif promotion is not None:
            status = "PROMOTED"
        elif review is None:
            status = "UNREVIEWED"
        elif review["decision"] == "ACCEPT":
            status = "REVIEWED"
        else:
            status = "REJECTED"
        derivations[directory.name] = _Derivation(
            directory=directory,
            record=record,
            record_sha256=record_sha256,
            review=review,
            review_sha256=review_sha256,
            promotion=promotion,
            removal=removal,
            status=status,
        )

    for derivation in derivations.values():
        supersedes = derivation.record["supersedes_derivation_id"]
        if supersedes is not None and supersedes not in derivations:
            raise MediaError(
                "Afleiding verwijst naar een onbekende voorganger.",
                code="media_supersedes_invalid",
            )
    for derivation_id in derivations:
        seen: set[str] = set()
        current: str | None = derivation_id
        while current is not None:
            if current in seen:
                raise MediaError(
                    "Afleidingen bevatten een supersedes-cyclus.",
                    code="media_supersedes_cycle",
                )
            seen.add(current)
            current = derivations[current].record["supersedes_derivation_id"]
    return derivations


def _new_derivation_id(created_at: datetime, existing: dict[str, _Derivation]) -> str:
    for _ in range(100):
        value = f"DRV-{created_at.strftime('%Y%m%d')}-{uuid4().hex[:12]}"
        if value not in existing:
            return value
    raise MediaError("Kon geen uniek derivation-ID maken.", code="media_id_conflict")


def _receipt_path(root: Path, operation: str) -> Path:
    now = _utc_now()
    name = f"ATT-{now.strftime('%Y%m%dT%H%M%S%fZ')}-media-{operation}-{uuid4().hex[:8]}.json"
    return root / ".opencntx" / "receipts" / name


def _write_receipt(
    root: Path,
    *,
    operation: str,
    status: str,
    source_id: str,
    derivation_id: str,
    content_sha256: str,
    record_sha256: str,
    promoted_source_id: str | None = None,
) -> Path:
    path = _receipt_path(root, operation.lower())
    value = {
        "content_sha256": content_sha256,
        "created_at": _timestamp(_utc_now()),
        "derivation_id": derivation_id,
        "format": MEDIA_RECEIPT_FORMAT,
        "format_version": MEDIA_RECEIPT_VERSION,
        "operation": operation,
        "promoted_source_id": promoted_source_id,
        "record_sha256": record_sha256,
        "source_id": source_id,
        "status": status,
    }
    _write_new(path, _json_bytes(value))
    return path


def _copy_utf8(source: BinaryIO, destination: BinaryIO, maximum: int) -> tuple[int, str]:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            byte_count += len(chunk)
            if byte_count > maximum:
                raise MediaError(
                    f"Afgeleide tekst overschrijdt max_source_bytes: {byte_count} > {maximum}.",
                    code="media_source_budget_exceeded",
                )
            text = decoder.decode(chunk)
            if "\x00" in text or any(
                (ord(character) < 32 and character not in "\t\n\r") or ord(character) == 127
                for character in text
            ):
                raise MediaError(
                    "Afgeleide tekst bevat onveilige controltekens.",
                    code="media_text_invalid",
                )
            destination.write(chunk)
            digest.update(chunk)
        tail = decoder.decode(b"", final=True)
        if "\x00" in tail or any(
            (ord(character) < 32 and character not in "\t\n\r") or ord(character) == 127
            for character in tail
        ):
            raise MediaError(
                "Afgeleide tekst bevat onveilige controltekens.",
                code="media_text_invalid",
            )
    except UnicodeDecodeError as exc:
        raise MediaError(
            "Afgeleide tekst moet volledig geldig UTF-8 zijn.",
            code="media_text_invalid",
        ) from exc
    destination.flush()
    os.fsync(destination.fileno())
    return byte_count, digest.hexdigest()


def _prepare_registration_plan(
    project_root: Path,
    source_id: str,
    text_path: Path,
    *,
    kind: str,
    producer_class: str,
    producer: str,
    locators: Sequence[str],
    supersedes_derivation_id: str | None,
) -> _RegistrationPlan:
    root = validate_workspace(project_root)
    normalized_source_id = _source_id(source_id)
    exact_source = _exact_source(root, normalized_source_id, allow_quarantined=False)
    config = load_workspace_config(root)
    normalized_kind = kind.strip().upper()
    normalized_class = producer_class.strip().upper()
    if normalized_kind not in KINDS:
        raise MediaError("Onbekende afleidingssoort.", code="media_kind_invalid")
    if normalized_class not in PRODUCER_CLASSES:
        raise MediaError(
            "Onbekende producer-class.",
            code="media_producer_class_invalid",
        )
    normalized_producer = _short_text(producer, field="producer")
    normalized_locators = _text_list(
        list(locators),
        field="locators",
        maximum=MAX_LOCATORS,
    )
    existing = _load_derivations(root, normalized_source_id)
    supersedes: str | None = None
    if supersedes_derivation_id is not None:
        supersedes = _derivation_id(supersedes_derivation_id)
        if supersedes not in existing:
            raise MediaError(
                "Onbekende supersedes-afleiding.",
                code="media_supersedes_invalid",
            )

    requested = text_path.absolute()
    if requested.is_symlink() or not requested.is_file():
        raise MediaError(
            "Afgeleide tekst moet één regulier bestand zijn.",
            code="media_text_not_file",
        )
    try:
        resolved = requested.resolve(strict=True)
        initial_stat = resolved.stat()
    except OSError as exc:
        raise MediaError(
            "Afgeleide tekst is niet toegankelijk.",
            code="media_text_unavailable",
        ) from exc
    if resolved.is_relative_to(root / "SOURCES") or resolved.is_relative_to(root / ".opencntx"):
        raise MediaError(
            "Beheerde bron- of afleidingsopslag kan niet als invoer worden gebruikt.",
            code="media_text_managed_path",
        )
    if initial_stat.st_size > config.max_source_bytes:
        raise MediaError(
            "Afgeleide tekst overschrijdt max_source_bytes.",
            code="media_source_budget_exceeded",
        )

    from .lifecycle import require_disk_capacity

    require_disk_capacity(root, initial_stat.st_size * 2 + 24 * 1024, "media-register")
    return _RegistrationPlan(
        root=root,
        source_id=normalized_source_id,
        exact_source=exact_source,
        config=config,
        kind=normalized_kind,
        producer_class=normalized_class,
        producer=normalized_producer,
        locators=normalized_locators,
        existing=existing,
        supersedes=supersedes,
        resolved_text=resolved,
        initial_stat=initial_stat,
    )


def _stage_derivation(plan: _RegistrationPlan) -> tuple[Path, int, str]:
    staging = plan.root / ".opencntx" / f".media-register-{uuid4().hex}"
    try:
        staging.mkdir(mode=0o700)
        with (
            plan.resolved_text.open("rb") as source,
            (staging / "content.txt").open("xb") as output,
        ):
            content_bytes, content_sha256 = _copy_utf8(
                source,
                output,
                plan.config.max_source_bytes,
            )
        if os.name != "nt":
            os.chmod(staging / "content.txt", 0o600)
        final_stat = plan.resolved_text.stat()
        if _source_identity(plan.initial_stat) != _source_identity(final_stat):
            raise MediaError(
                "Afgeleide tekst wijzigde tijdens het lezen.",
                code="media_text_changed",
            )
        return staging, content_bytes, content_sha256
    except BaseException as exc:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if isinstance(exc, OSError):
            raise MediaError(
                f"Afleiding kon niet atomair worden geregistreerd: {exc}",
                code="media_register_failed",
            ) from exc
        raise


def _duplicate_derivation(
    plan: _RegistrationPlan,
    staging: Path,
    content_bytes: int,
    content_sha256: str,
) -> MediaMutationResult | None:
    for derivation in plan.existing.values():
        record = derivation.record
        identical = (
            record["content_sha256"] == content_sha256
            and record["content_bytes"] == content_bytes
            and record["kind"] == plan.kind
            and record["producer_class"] == plan.producer_class
            and record["producer"] == plan.producer
            and tuple(record["locators"]) == plan.locators
            and record["supersedes_derivation_id"] == plan.supersedes
            and derivation.status != "REMOVED"
        )
        if not identical:
            continue
        shutil.rmtree(staging)
        receipt = _write_receipt(
            plan.root,
            operation="REGISTER",
            status="DUPLICATE_DERIVATION",
            source_id=plan.source_id,
            derivation_id=record["derivation_id"],
            content_sha256=content_sha256,
            record_sha256=derivation.record_sha256,
        )
        return MediaMutationResult(
            operation="REGISTER",
            status="DUPLICATE_DERIVATION",
            source_id=plan.source_id,
            derivation_id=record["derivation_id"],
            content_sha256=content_sha256,
            record_sha256=derivation.record_sha256,
            receipt_path=receipt,
        )
    return None


def _build_derivation_record(
    plan: _RegistrationPlan,
    staging: Path,
    content_bytes: int,
    content_sha256: str,
) -> tuple[str, str]:
    source_total = sum(item.byte_count for item in _stored_sources(plan.root).values())
    total = source_total + _derived_storage_bytes(plan.root) + content_bytes
    if total > plan.config.max_storage_bytes:
        raise MediaError(
            f"Totaal opslagbudget wordt overschreden: {total} > "
            f"{plan.config.max_storage_bytes} bytes.",
            code="media_storage_budget_exceeded",
        )
    created_at = _utc_now()
    derivation_id = _new_derivation_id(created_at, plan.existing)
    record = {
        "content_bytes": content_bytes,
        "content_sha256": content_sha256,
        "created_at": _timestamp(created_at),
        "derivation_id": derivation_id,
        "format": DERIVATION_FORMAT,
        "format_version": DERIVATION_FORMAT_VERSION,
        "kind": plan.kind,
        "locators": list(plan.locators),
        "privacy": plan.exact_source.stored.privacy,
        "producer": plan.producer,
        "producer_class": plan.producer_class,
        "source_bytes": plan.exact_source.stored.byte_count,
        "source_id": plan.source_id,
        "source_record_sha256": plan.exact_source.record_sha256,
        "source_sha256": plan.exact_source.stored.sha256,
        "supersedes_derivation_id": plan.supersedes,
    }
    record_bytes = _json_bytes(record)
    record_sha256 = sha256_bytes(record_bytes)
    _write_new(staging / "record.json", record_bytes)
    return derivation_id, record_sha256


def _publish_derivation(
    plan: _RegistrationPlan,
    staging: Path,
    derivation_id: str,
    content_sha256: str,
    record_sha256: str,
) -> MediaMutationResult:
    final_directory: Path | None = None
    published = False
    created_source_directory: Path | None = None
    try:
        derived_root = _derived_root(plan.root, create=True)
        source_directory = derived_root / plan.source_id
        if source_directory.exists():
            if source_directory.is_symlink() or not source_directory.is_dir():
                raise MediaError(
                    "Bronafleidingsmap is onveilig.",
                    code="media_storage_invalid",
                )
        else:
            source_directory.mkdir()
            created_source_directory = source_directory
        final_directory = source_directory / derivation_id
        if final_directory.exists() or final_directory.is_symlink():
            raise MediaError(
                "Derivation-ID bestaat onverwacht al.",
                code="media_id_conflict",
            )
        os.replace(staging, final_directory)
        published = True
        receipt = _write_receipt(
            plan.root,
            operation="REGISTER",
            status="REGISTERED",
            source_id=plan.source_id,
            derivation_id=derivation_id,
            content_sha256=content_sha256,
            record_sha256=record_sha256,
        )
        return MediaMutationResult(
            operation="REGISTER",
            status="REGISTERED",
            source_id=plan.source_id,
            derivation_id=derivation_id,
            content_sha256=content_sha256,
            record_sha256=record_sha256,
            receipt_path=receipt,
        )
    except Exception as exc:
        if published and final_directory is not None and final_directory.exists():
            shutil.rmtree(final_directory, ignore_errors=True)
        if created_source_directory is not None:
            try:
                created_source_directory.rmdir()
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise MediaError(
                f"Afleiding kon niet atomair worden geregistreerd: {exc}",
                code="media_register_failed",
            ) from exc
        raise


@_workspace_writer("media-register")
def register_derivation(
    project_root: Path,
    source_id: str,
    text_path: Path,
    *,
    kind: str,
    producer_class: str,
    producer: str,
    locators: Sequence[str] = (),
    supersedes_derivation_id: str | None = None,
) -> MediaMutationResult:
    """Atomically register supplied UTF-8 text without running a media tool."""
    plan = _prepare_registration_plan(
        project_root,
        source_id,
        text_path,
        kind=kind,
        producer_class=producer_class,
        producer=producer,
        locators=locators,
        supersedes_derivation_id=supersedes_derivation_id,
    )
    staging, content_bytes, content_sha256 = _stage_derivation(plan)
    try:
        duplicate = _duplicate_derivation(
            plan,
            staging,
            content_bytes,
            content_sha256,
        )
        if duplicate is not None:
            return duplicate
        derivation_id, record_sha256 = _build_derivation_record(
            plan,
            staging,
            content_bytes,
            content_sha256,
        )
        return _publish_derivation(
            plan,
            staging,
            derivation_id,
            content_sha256,
            record_sha256,
        )
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _one_derivation(root: Path, source_id: str, derivation_id: str) -> _Derivation:
    normalized_source_id = _source_id(source_id)
    normalized_derivation_id = _derivation_id(derivation_id)
    derivations = _load_derivations(root, normalized_source_id)
    derivation = derivations.get(normalized_derivation_id)
    if derivation is None:
        raise MediaError(
            f"Onbekende afleiding: {normalized_derivation_id}.",
            code="media_derivation_unknown",
        )
    return derivation


@_workspace_writer("media-review")
def review_derivation(
    project_root: Path,
    source_id: str,
    derivation_id: str,
    *,
    content_sha256: str,
    decision: str,
    findings: Sequence[str],
    reviewer: str,
) -> MediaMutationResult:
    root = validate_workspace(project_root)
    _exact_source(root, source_id, allow_quarantined=False)
    derivation = _one_derivation(root, source_id, derivation_id)
    if derivation.status != "UNREVIEWED":
        raise MediaError(
            "Alleen een UNREVIEWED afleiding kan exact één review krijgen.",
            code="media_review_state_invalid",
        )
    expected_content = _digest(content_sha256, field="content_sha256")
    if expected_content != derivation.record["content_sha256"]:
        raise MediaError("Contentdigest verschilt.", code="media_digest_mismatch")
    normalized_decision = decision.strip().upper()
    if normalized_decision not in DECISIONS:
        raise MediaError(
            "Reviewbeslissing moet ACCEPT of REJECT zijn.", code="media_decision_invalid"
        )
    normalized_findings = _text_list(
        list(findings), field="findings", maximum=MAX_FINDINGS, allow_empty=False
    )
    normalized_reviewer = _short_text(reviewer, field="reviewer")
    review = {
        "content_sha256": expected_content,
        "decision": normalized_decision,
        "derivation_id": derivation.record["derivation_id"],
        "findings": list(normalized_findings),
        "format": REVIEW_FORMAT,
        "format_version": REVIEW_FORMAT_VERSION,
        "record_sha256": derivation.record_sha256,
        "reviewed_at": _timestamp(_utc_now()),
        "reviewer": normalized_reviewer,
        "source_id": derivation.record["source_id"],
    }
    review_path = derivation.directory / "review.json"
    _write_new(review_path, _json_bytes(review))
    try:
        status = "REVIEWED" if normalized_decision == "ACCEPT" else "REJECTED"
        receipt = _write_receipt(
            root,
            operation="REVIEW",
            status=status,
            source_id=source_id,
            derivation_id=derivation_id,
            content_sha256=expected_content,
            record_sha256=derivation.record_sha256,
        )
    except Exception:
        review_path.unlink(missing_ok=True)
        raise
    return MediaMutationResult(
        operation="REVIEW",
        status=status,
        source_id=source_id,
        derivation_id=derivation_id,
        content_sha256=expected_content,
        record_sha256=derivation.record_sha256,
        receipt_path=receipt,
    )


def _rollback_capture(root: Path, result: CaptureResult) -> None:
    try:
        result.receipt_path.unlink(missing_ok=True)
    except OSError:
        return
    if result.status != "CAPTURED":
        return
    try:
        stored = _stored_sources(root).get(result.source_id)
        if stored is not None and stored.sha256 == result.sha256:
            shutil.rmtree(stored.record_path.parent)
    except (OSError, WorkspaceError):
        return


@_workspace_writer("media-promote")
def promote_derivation(
    project_root: Path,
    source_id: str,
    derivation_id: str,
    *,
    review_digest: str,
) -> MediaMutationResult:
    root = validate_workspace(project_root)
    _exact_source(root, source_id, allow_quarantined=False)
    derivation = _one_derivation(root, source_id, derivation_id)
    expected_review = _digest(review_digest, field="review_digest")
    if derivation.status != "REVIEWED" or derivation.review_sha256 is None:
        raise MediaError(
            "Alleen een exact REVIEWED afleiding kan worden gepromoveerd.",
            code="media_promotion_state_invalid",
        )
    if derivation.review_sha256 != expected_review:
        raise MediaError("Reviewdigest verschilt.", code="media_digest_mismatch")

    temporary_path: Path | None = None
    capture_result: CaptureResult | None = None
    promotion_path = derivation.directory / "promotion.json"
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix="opencntx-derived-", suffix=".txt", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with (derivation.directory / "content.txt").open("rb") as content:
                shutil.copyfileobj(content, temporary, length=CHUNK_SIZE)
            temporary.flush()
            os.fsync(temporary.fileno())
        capture_result = capture_source(
            root,
            temporary_path,
            privacy=derivation.record["privacy"],
            origin=_promotion_origin(derivation.record),
        )
        if capture_result.sha256 != derivation.record["content_sha256"]:
            raise MediaError(
                "Gepromoveerde capture verschilt van de afleiding.",
                code="media_promotion_stale",
            )
        promoted_source = _stored_sources(root).get(capture_result.source_id)
        if promoted_source is None:
            raise MediaError(
                "Gepromoveerde bronregistratie ontbreekt.",
                code="media_promotion_stale",
            )
        _, promoted_source_record_sha256 = _hash_file(promoted_source.record_path)
        promotion = {
            "capture_status": capture_result.status,
            "content_sha256": derivation.record["content_sha256"],
            "derivation_id": derivation.record["derivation_id"],
            "format": PROMOTION_FORMAT,
            "format_version": PROMOTION_FORMAT_VERSION,
            "promoted_at": _timestamp(_utc_now()),
            "promoted_source_id": capture_result.source_id,
            "promoted_source_record_sha256": promoted_source_record_sha256,
            "promoted_source_sha256": capture_result.sha256,
            "record_sha256": derivation.record_sha256,
            "review_sha256": derivation.review_sha256,
            "source_id": derivation.record["source_id"],
            "source_sha256": derivation.record["source_sha256"],
        }
        _write_new(promotion_path, _json_bytes(promotion))
        receipt = _write_receipt(
            root,
            operation="PROMOTE",
            status="PROMOTED",
            source_id=source_id,
            derivation_id=derivation_id,
            content_sha256=derivation.record["content_sha256"],
            record_sha256=derivation.record_sha256,
            promoted_source_id=capture_result.source_id,
        )
    except Exception as exc:
        promotion_path.unlink(missing_ok=True)
        if capture_result is not None:
            _rollback_capture(root, capture_result)
        if isinstance(exc, OSError):
            raise MediaError(
                f"Afleiding kon niet veilig worden gepromoveerd: {exc}",
                code="media_promotion_failed",
            ) from exc
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return MediaMutationResult(
        operation="PROMOTE",
        status="PROMOTED",
        source_id=source_id,
        derivation_id=derivation_id,
        content_sha256=derivation.record["content_sha256"],
        record_sha256=derivation.record_sha256,
        receipt_path=receipt,
        promoted_source_id=capture_result.source_id,
    )


@_workspace_writer("media-remove")
def remove_derivation(
    project_root: Path,
    source_id: str,
    derivation_id: str,
    *,
    record_digest: str,
    content_sha256: str,
    owner: str,
) -> MediaMutationResult:
    root = validate_workspace(project_root)
    _exact_source(root, source_id, allow_quarantined=True)
    derivation = _one_derivation(root, source_id, derivation_id)
    if derivation.status == "REMOVED":
        raise MediaError("Afgeleide tekst is al verwijderd.", code="media_removal_state_invalid")
    expected_record = _digest(record_digest, field="record_digest")
    expected_content = _digest(content_sha256, field="content_sha256")
    if (
        expected_record != derivation.record_sha256
        or expected_content != derivation.record["content_sha256"]
    ):
        raise MediaError("Verwijderdigests verschillen.", code="media_digest_mismatch")
    normalized_owner = _short_text(owner, field="owner")
    removal = {
        "content_sha256": expected_content,
        "derivation_id": derivation_id,
        "format": REMOVAL_FORMAT,
        "format_version": REMOVAL_FORMAT_VERSION,
        "owner": normalized_owner,
        "record_sha256": expected_record,
        "removed_at": _timestamp(_utc_now()),
        "source_id": source_id,
        "source_sha256": derivation.record["source_sha256"],
    }
    content_path = derivation.directory / "content.txt"
    temporary_content = derivation.directory / f".content-removing-{uuid4().hex}"
    temporary_record = derivation.directory / f".removed-{uuid4().hex}.tmp"
    removed_path = derivation.directory / "removed.json"
    receipt: Path | None = None
    _write_new(temporary_record, _json_bytes(removal))
    try:
        os.replace(content_path, temporary_content)
        os.replace(temporary_record, removed_path)
        receipt = _write_receipt(
            root,
            operation="REMOVE",
            status="REMOVED",
            source_id=source_id,
            derivation_id=derivation_id,
            content_sha256=expected_content,
            record_sha256=expected_record,
            promoted_source_id=(
                derivation.promotion["promoted_source_id"]
                if derivation.promotion is not None
                else None
            ),
        )
        temporary_content.unlink()
    except Exception as exc:
        if receipt is not None:
            receipt.unlink(missing_ok=True)
        removed_path.unlink(missing_ok=True)
        if temporary_content.exists() and not content_path.exists():
            os.replace(temporary_content, content_path)
        if isinstance(exc, OSError):
            raise MediaError(
                f"Afgeleide tekst kon niet veilig worden verwijderd: {exc}",
                code="media_removal_failed",
            ) from exc
        raise
    finally:
        temporary_record.unlink(missing_ok=True)
        temporary_content.unlink(missing_ok=True)
    return MediaMutationResult(
        operation="REMOVE",
        status="REMOVED",
        source_id=source_id,
        derivation_id=derivation_id,
        content_sha256=expected_content,
        record_sha256=expected_record,
        receipt_path=receipt,
        promoted_source_id=(
            derivation.promotion["promoted_source_id"] if derivation.promotion is not None else None
        ),
    )


def media_status(
    project_root: Path, source_id: str, derivation_id: str | None = None
) -> tuple[MediaStatusEntry, ...]:
    root = validate_workspace(project_root)
    normalized_source_id = _source_id(source_id)
    normalized_derivation_id = _derivation_id(derivation_id) if derivation_id is not None else None
    try:
        _exact_source(root, normalized_source_id, allow_quarantined=True)
        derivations = _load_derivations(root, normalized_source_id)
    except MediaError as exc:
        if exc.code not in {
            "media_source_stale",
            "media_content_stale",
            "media_promotion_stale",
            "media_record_invalid",
            "media_review_invalid",
            "media_promotion_invalid",
            "media_removal_invalid",
            "media_supersedes_invalid",
            "media_supersedes_cycle",
        }:
            raise
        return (
            MediaStatusEntry(
                source_id=normalized_source_id,
                derivation_id=normalized_derivation_id,
                status="STALE",
                statement=STATUS_STATEMENTS["STALE"],
                content_sha256=None,
                record_sha256=None,
                review_sha256=None,
                promoted_source_id=None,
            ),
        )
    if derivation_id is not None:
        if normalized_derivation_id is None:
            raise MediaError(
                "De afleidings-ID is intern onvolledig.",
                code="media_record_invalid",
            )
        selected = derivations.get(normalized_derivation_id)
        if selected is None:
            raise MediaError(
                f"Onbekende afleiding: {normalized_derivation_id}.",
                code="media_derivation_unknown",
            )
        derivations = {normalized_derivation_id: selected}
    if not derivations:
        return (
            MediaStatusEntry(
                source_id=normalized_source_id,
                derivation_id=None,
                status="NOT_INVESTIGATED",
                statement=STATUS_STATEMENTS["NOT_INVESTIGATED"],
                content_sha256=None,
                record_sha256=None,
                review_sha256=None,
                promoted_source_id=None,
            ),
        )
    return tuple(
        MediaStatusEntry(
            source_id=normalized_source_id,
            derivation_id=identifier,
            status=item.status,
            statement=STATUS_STATEMENTS[item.status],
            content_sha256=item.record["content_sha256"],
            record_sha256=item.record_sha256,
            review_sha256=item.review_sha256,
            promoted_source_id=(
                item.promotion["promoted_source_id"] if item.promotion is not None else None
            ),
        )
        for identifier, item in sorted(derivations.items())
    )


def verify_media(
    project_root: Path, source_id: str, derivation_id: str | None = None
) -> MediaVerifyReport:
    _source_id(source_id)
    if derivation_id is not None:
        _derivation_id(derivation_id)
    try:
        entries = media_status(project_root, source_id, derivation_id)
    except MediaError as exc:
        if exc.code in {"media_source_unknown", "media_derivation_unknown"}:
            raise
        return MediaVerifyReport(
            ok=False,
            entries=(),
            issues=(f"{exc.code}: media verification failed",),
        )
    if any(entry.status == "STALE" for entry in entries):
        return MediaVerifyReport(
            ok=False,
            entries=entries,
            issues=("media_stale: derived or original bytes differ",),
        )
    return MediaVerifyReport(ok=True, entries=entries, issues=())


def format_media_verify_report(report: MediaVerifyReport) -> str:
    if report.ok:
        statuses = ", ".join(
            f"{entry.derivation_id or entry.source_id}={entry.status}" for entry in report.entries
        )
        return f"OK: media registration is exact ({statuses})."
    return "NOT OK:\n" + "\n".join(f"- {issue}" for issue in report.issues)
