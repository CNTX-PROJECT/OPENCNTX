"""Local, non-executing storage foundation for OPENCNTX workspaces."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from uuid import uuid4

from .integrity import Transaction, state_digest, write_new_bytes, writer_transaction
from .primitives import (
    pretty_json_bytes as _json_bytes,
)
from .primitives import (
    timestamp_microseconds as _timestamp,
)
from .primitives import (
    utc_now as _utc_now,
)

WORKSPACE_FORMAT = "opencntx-workspace"
WORKSPACE_FORMAT_VERSION = 1
SOURCE_RECORD_FORMAT = "opencntx-source"
SOURCE_RECORD_VERSION = 1
RECEIPT_FORMAT = "opencntx-capture-receipt"
RECEIPT_FORMAT_VERSION = 1

DEFAULT_MAX_SOURCE_BYTES = 2 * 1024**3
DEFAULT_MAX_STORAGE_BYTES = 20 * 1024**3
PRIVACY_LABELS = ("PUBLIC", "PRIVATE", "RESTRICTED", "QUARANTINED")
SOURCE_ID_PATTERN = re.compile(r"SRC-\d{8}-[0-9a-f]{12}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
CHUNK_SIZE = 1024 * 1024

VISIBLE_DIRECTORIES = (
    Path("CONTROL"),
    Path("INBOX"),
    Path("SOURCES"),
    Path("CHAPTERS"),
    Path("TASKS"),
    Path("PLAYBOOKS"),
    Path("ROLES"),
)
REQUIRED_DIRECTORIES = VISIBLE_DIRECTORIES + (Path(".opencntx") / "receipts",)
REQUIRED_FILES = (
    Path("CONTROL") / "OWNER.md",
    Path("CONTROL") / "ROADMAP.md",
    Path("CONTROL") / "CURRENT.md",
    Path("CHAPTERS") / "INDEX.md",
)

OWNER_TEMPLATE = """# OWNER

## Authority

Only the OWNER grants final approval.

## Privacy

New sources start as PRIVATE by default. Never lower a privacy label
automatically.
"""

ROADMAP_TEMPLATE = """# ROADMAP

No assignment is active until the OWNER starts it explicitly.

<!-- OPENCNTX:CONTROL:START -->
## Current assignment

None.
<!-- OPENCNTX:CONTROL:END -->
"""

CURRENT_TEMPLATE = f"""---
format: {WORKSPACE_FORMAT}
format_version: {WORKSPACE_FORMAT_VERSION}
max_source_bytes: {DEFAULT_MAX_SOURCE_BYTES}
max_storage_bytes: {DEFAULT_MAX_STORAGE_BYTES}
---

# CURRENT

- Active task: none
- Allowed actions: none
- Next gate: OWNER instruction
"""

INDEX_TEMPLATE = """# Chapter index

No chapters registered yet.
"""


class WorkspaceError(Exception):
    """A short, user-facing workspace error with a stable receipt code."""

    def __init__(self, message: str, *, code: str = "workspace_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WorkspaceConfig:
    max_source_bytes: int
    max_storage_bytes: int


@dataclass(frozen=True)
class WorkspaceInitResult:
    root: Path
    created: bool


@dataclass(frozen=True)
class CaptureResult:
    status: str
    source_id: str
    byte_count: int
    sha256: str
    receipt_path: Path


@dataclass(frozen=True)
class StoredSource:
    source_id: str
    byte_count: int
    sha256: str
    privacy: str
    original_path: Path
    record_path: Path


@dataclass(frozen=True)
class _CapturePlan:
    root: Path
    config: WorkspaceConfig
    stored: dict[str, StoredSource]
    captured_at: datetime
    attempt_id: str
    original_name: str
    original_filename: str
    privacy: str
    origin: str | None
    supersedes: str | None
    resolved_source: Path
    initial_stat: os.stat_result


def _write_new_file(path: Path, content: bytes) -> None:
    write_new_bytes(path, content, mode=0o600, private=True)


def _resolve_root(project_root: Path, *, create: bool) -> tuple[Path, bool]:
    requested = project_root.absolute()
    if requested.is_symlink():
        raise WorkspaceError(
            "De projectwerkruimte mag geen symlink zijn.",
            code="workspace_root_symlink",
        )
    created = False
    if not requested.exists():
        if not create:
            raise WorkspaceError(
                "De projectwerkruimte bestaat niet; voer eerst 'opencntx workspace init' uit.",
                code="workspace_missing",
            )
        try:
            requested.mkdir(parents=True, exist_ok=False)
            created = True
        except OSError as exc:
            raise WorkspaceError(
                f"De projectwerkruimte kon niet worden gemaakt: {exc}",
                code="workspace_create_failed",
            ) from exc
    if not requested.is_dir():
        raise WorkspaceError(
            "De projectwerkruimte is geen map.",
            code="workspace_not_directory",
        )
    try:
        return requested.resolve(strict=True), created
    except OSError as exc:
        raise WorkspaceError(
            f"De projectwerkruimte is niet toegankelijk: {exc}",
            code="workspace_unavailable",
        ) from exc


def _managed_path_state(root: Path) -> tuple[bool, bool]:
    paths = tuple(root / path for path in REQUIRED_DIRECTORIES + REQUIRED_FILES)
    present = [path.exists() or path.is_symlink() for path in paths]
    return all(present), any(present)


def _validate_managed_path(root: Path, relative: Path, *, directory: bool) -> Path:
    path = root / relative
    if path.is_symlink():
        raise WorkspaceError(
            f"Beheerd werkruimtepad mag geen symlink zijn: {relative.as_posix()}",
            code="managed_path_symlink",
        )
    if directory and not path.is_dir():
        raise WorkspaceError(
            f"Vereiste werkruimtemap ontbreekt: {relative.as_posix()}",
            code="workspace_incomplete",
        )
    if not directory and not path.is_file():
        raise WorkspaceError(
            f"Vereist werkruimtebestand ontbreekt: {relative.as_posix()}",
            code="workspace_incomplete",
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise WorkspaceError(
            f"Beheerd werkruimtepad is niet toegankelijk: {relative.as_posix()}: {exc}",
            code="managed_path_unavailable",
        ) from exc
    if not resolved.is_relative_to(root):
        raise WorkspaceError(
            f"Beheerd werkruimtepad verlaat de projectroot: {relative.as_posix()}",
            code="managed_path_escape",
        )
    return resolved


def validate_workspace(project_root: Path) -> Path:
    """Validate the fixed workspace foundation without modifying it."""
    root, _ = _resolve_root(project_root, create=False)
    for relative in REQUIRED_DIRECTORIES:
        _validate_managed_path(root, relative, directory=True)
    for relative in REQUIRED_FILES:
        _validate_managed_path(root, relative, directory=False)
    opencntx = root / ".opencntx"
    if opencntx.is_symlink() or not opencntx.is_dir():
        raise WorkspaceError(
            ".opencntx moet een gewone map binnen de projectwerkruimte zijn.",
            code="managed_path_invalid",
        )
    return root


def _build_staging_workspace(staging: Path) -> None:
    for relative in REQUIRED_DIRECTORIES:
        (staging / relative).mkdir(mode=0o700, parents=True, exist_ok=False)
    templates = {
        Path("CONTROL") / "OWNER.md": OWNER_TEMPLATE,
        Path("CONTROL") / "ROADMAP.md": ROADMAP_TEMPLATE,
        Path("CONTROL") / "CURRENT.md": CURRENT_TEMPLATE,
        Path("CHAPTERS") / "INDEX.md": INDEX_TEMPLATE,
    }
    for relative, text in templates.items():
        _write_new_file(staging / relative, text.encode("utf-8"))
    from .lifecycle import initialize_lifecycle_state

    initialize_lifecycle_state(staging)


def init_workspace(project_root: Path) -> WorkspaceInitResult:
    """Create the fixed workspace structure without overwriting existing paths."""
    from .lifecycle import require_disk_capacity

    requested = project_root.absolute()
    probe = requested if requested.exists() else requested.parent
    template_bytes = sum(
        len(value.encode("utf-8"))
        for value in (OWNER_TEMPLATE, ROADMAP_TEMPLATE, CURRENT_TEMPLATE, INDEX_TEMPLATE)
    )
    require_disk_capacity(probe, template_bytes * 2 + 16 * 1024, "workspace-init")
    root, root_created = _resolve_root(project_root, create=True)
    fully_present, partly_present = _managed_path_state(root)
    if fully_present:
        validate_workspace(root)
        return WorkspaceInitResult(root=root, created=False)
    if partly_present:
        raise WorkspaceError(
            "De werkruimte bevat al een deel van de beheerde structuur; er is niets overschreven.",
            code="workspace_conflict",
        )

    opencntx = root / ".opencntx"
    if opencntx.is_symlink() or (opencntx.exists() and not opencntx.is_dir()):
        raise WorkspaceError(
            ".opencntx bestaat maar is geen veilige gewone map.",
            code="workspace_conflict",
        )

    staging = root / f".opencntx-init-{uuid4().hex}"
    moved: list[tuple[Path, Path]] = []
    created_opencntx = False
    try:
        staging.mkdir(mode=0o700)
        _build_staging_workspace(staging)
        for relative in VISIBLE_DIRECTORIES:
            source = staging / relative
            destination = root / relative
            os.replace(source, destination)
            moved.append((destination, source))
        if not opencntx.exists():
            opencntx.mkdir(mode=0o700)
            created_opencntx = True
        for name in ("receipts", "lifecycle"):
            source = staging / ".opencntx" / name
            destination = opencntx / name
            os.replace(source, destination)
            moved.append((destination, source))
        shutil.rmtree(staging, ignore_errors=True)
        validate_workspace(root)
        return WorkspaceInitResult(root=root, created=True)
    except (WorkspaceError, OSError) as exc:
        for destination, source in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() and not source.exists():
                    os.replace(destination, source)
            except OSError:
                pass
        if isinstance(exc, WorkspaceError):
            raise
        raise WorkspaceError(
            f"De werkruimte kon niet volledig worden geïnitialiseerd: {exc}",
            code="workspace_init_failed",
        ) from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if created_opencntx:
            try:
                opencntx.rmdir()
            except OSError:
                pass
        if root_created:
            try:
                root.rmdir()
            except OSError:
                pass


def _parse_frontmatter(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkspaceError(
            f"CONTROL/CURRENT.md is niet leesbaar als UTF-8: {exc}",
            code="current_unreadable",
        ) from exc
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise WorkspaceError(
            "CONTROL/CURRENT.md mist geldige frontmatter.",
            code="current_invalid",
        )
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise WorkspaceError(
            "CONTROL/CURRENT.md mist het einde van de frontmatter.",
            code="current_invalid",
        ) from exc
    values: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip() or ":" not in line:
            raise WorkspaceError(
                "CONTROL/CURRENT.md bevat ongeldige frontmatter.",
                code="current_invalid",
            )
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value or key in values:
            raise WorkspaceError(
                "CONTROL/CURRENT.md bevat dubbele of lege instellingen.",
                code="current_invalid",
            )
        values[key] = value
    return values


def load_workspace_config(project_root: Path) -> WorkspaceConfig:
    """Read strict operational budgets from the human-readable CURRENT file."""
    root = validate_workspace(project_root)
    values = _parse_frontmatter(root / "CONTROL" / "CURRENT.md")
    expected = {
        "format",
        "format_version",
        "max_source_bytes",
        "max_storage_bytes",
    }
    unknown = set(values) - expected
    missing = expected - set(values)
    if unknown or missing:
        key = min(unknown or missing)
        raise WorkspaceError(
            f"CONTROL/CURRENT.md bevat een onbekende of ontbrekende instelling: {key}",
            code="current_invalid",
        )
    if values["format"] != WORKSPACE_FORMAT or values["format_version"] != str(
        WORKSPACE_FORMAT_VERSION
    ):
        raise WorkspaceError(
            "CONTROL/CURRENT.md gebruikt een onbekend werkruimteformaat.",
            code="current_invalid",
        )

    def positive_integer(key: str) -> int:
        try:
            value = int(values[key])
        except ValueError as exc:
            raise WorkspaceError(
                f"CONTROL/CURRENT.md vereist een positief geheel getal voor {key}.",
                code="current_invalid",
            ) from exc
        if value <= 0:
            raise WorkspaceError(
                f"CONTROL/CURRENT.md vereist een positief geheel getal voor {key}.",
                code="current_invalid",
            )
        return value

    max_source_bytes = positive_integer("max_source_bytes")
    max_storage_bytes = positive_integer("max_storage_bytes")
    if max_source_bytes > max_storage_bytes:
        raise WorkspaceError(
            "max_source_bytes mag niet groter zijn dan max_storage_bytes.",
            code="current_invalid",
        )
    return WorkspaceConfig(
        max_source_bytes=max_source_bytes,
        max_storage_bytes=max_storage_bytes,
    )


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(
            f"{label} is ongeldig of onleesbaar: {path.name}: {exc}",
            code="stored_record_invalid",
        ) from exc
    if not isinstance(value, dict):
        raise WorkspaceError(
            f"{label} moet een JSON-object zijn: {path.name}",
            code="stored_record_invalid",
        )
    return value


def _iter_child_directories(parent: Path, *, label: str) -> list[Path]:
    try:
        children = sorted(parent.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise WorkspaceError(
            f"{label} kan niet worden gelezen: {exc}",
            code="stored_record_unavailable",
        ) from exc
    directories: list[Path] = []
    for child in children:
        if child.is_symlink() or not child.is_dir():
            raise WorkspaceError(
                f"Onverwacht of onveilig pad in {label}: {child.name}",
                code="stored_record_invalid",
            )
        directories.append(child)
    return directories


def _stored_sources(root: Path) -> dict[str, StoredSource]:
    sources_root = _validate_managed_path(root, Path("SOURCES"), directory=True)
    stored: dict[str, StoredSource] = {}
    for year in _iter_child_directories(sources_root, label="SOURCES"):
        if re.fullmatch(r"\d{4}", year.name) is None:
            raise WorkspaceError(
                f"Ongeldige jaarmap in SOURCES: {year.name}",
                code="stored_record_invalid",
            )
        for month in _iter_child_directories(year, label=f"SOURCES/{year.name}"):
            if re.fullmatch(r"\d{2}", month.name) is None:
                raise WorkspaceError(
                    f"Ongeldige maandmap in SOURCES: {month.name}",
                    code="stored_record_invalid",
                )
            for source_directory in _iter_child_directories(
                month, label=f"SOURCES/{year.name}/{month.name}"
            ):
                source_id = source_directory.name
                if SOURCE_ID_PATTERN.fullmatch(source_id) is None:
                    raise WorkspaceError(
                        f"Ongeldige bronmap in SOURCES: {source_id}",
                        code="stored_record_invalid",
                    )
                record_path = source_directory / "record.json"
                if record_path.is_symlink() or not record_path.is_file():
                    raise WorkspaceError(
                        f"Bronregistratie ontbreekt of is onveilig: {source_id}",
                        code="stored_record_invalid",
                    )
                record = _load_json_object(record_path, label="Bronregistratie")
                byte_count = record.get("bytes")
                digest = record.get("sha256")
                privacy = record.get("privacy")
                stored_path_value = record.get("stored_path")
                if (
                    record.get("format") != SOURCE_RECORD_FORMAT
                    or record.get("format_version") != SOURCE_RECORD_VERSION
                    or record.get("source_id") != source_id
                    or isinstance(byte_count, bool)
                    or not isinstance(byte_count, int)
                    or byte_count < 0
                    or not isinstance(digest, str)
                    or SHA256_PATTERN.fullmatch(digest) is None
                    or privacy not in PRIVACY_LABELS
                    or record.get("status") != "CAPTURED"
                    or not isinstance(stored_path_value, str)
                ):
                    raise WorkspaceError(
                        f"Bronregistratie bevat ongeldige velden: {source_id}",
                        code="stored_record_invalid",
                    )
                relative = PurePosixPath(stored_path_value)
                if relative.is_absolute() or ".." in relative.parts:
                    raise WorkspaceError(
                        f"Bronregistratie bevat een onveilig opslagpad: {source_id}",
                        code="stored_record_invalid",
                    )
                original = root.joinpath(*relative.parts)
                if original.is_symlink() or not original.is_file():
                    raise WorkspaceError(
                        f"Opgeslagen origineel ontbreekt of is onveilig: {source_id}",
                        code="stored_record_invalid",
                    )
                try:
                    resolved_original = original.resolve(strict=True)
                    resolved_source_directory = source_directory.resolve(strict=True)
                    actual_size = resolved_original.stat().st_size
                except OSError as exc:
                    raise WorkspaceError(
                        f"Opgeslagen origineel is niet toegankelijk: {source_id}: {exc}",
                        code="stored_record_unavailable",
                    ) from exc
                if (
                    resolved_original.parent != resolved_source_directory
                    or re.fullmatch(r"original\.[a-z0-9]{1,16}", resolved_original.name) is None
                    or tuple(relative.parts[:-1]) != ("SOURCES", year.name, month.name, source_id)
                    or source_id[4:8] != year.name
                    or source_id[8:10] != month.name
                    or actual_size != byte_count
                ):
                    raise WorkspaceError(
                        f"Opgeslagen origineel en registratie verschillen: {source_id}",
                        code="stored_record_invalid",
                    )
                if source_id in stored:
                    raise WorkspaceError(
                        f"Dubbele source-ID gevonden: {source_id}",
                        code="stored_record_invalid",
                    )
                stored[source_id] = StoredSource(
                    source_id=source_id,
                    byte_count=byte_count,
                    sha256=digest,
                    privacy=privacy,
                    original_path=resolved_original,
                    record_path=record_path,
                )
    return stored


def _validate_privacy(privacy: str) -> str:
    normalized = privacy.strip().upper()
    if normalized not in PRIVACY_LABELS:
        raise WorkspaceError(
            f"Onbekend privacylabel: {privacy}",
            code="privacy_invalid",
        )
    return normalized


def _validate_origin(origin: str | None) -> str | None:
    if origin is None:
        return None
    value = origin.strip()
    if not value:
        return None
    if len(value) > 200 or any(ord(character) < 32 for character in value):
        raise WorkspaceError(
            "Herkomst moet één korte regel van maximaal 200 tekens zijn.",
            code="origin_invalid",
        )
    return value


def _safe_original_name(name: str) -> str:
    value = "".join(character if ord(character) >= 32 else "_" for character in name)
    return value[:255] or "unknown"


def _original_suffix(name: str) -> str:
    suffix = Path(name).suffix
    if re.fullmatch(r"\.[A-Za-z0-9]{1,16}", suffix or "") is None:
        return ".bin"
    return suffix.lower()


def _source_identity(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )


def _copy_and_hash(source: BinaryIO, destination: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    while True:
        chunk = source.read(CHUNK_SIZE)
        if not chunk:
            break
        destination.write(chunk)
        digest.update(chunk)
        byte_count += len(chunk)
    destination.flush()
    os.fsync(destination.fileno())
    return byte_count, digest.hexdigest()


def _hash_file(path: Path) -> tuple[int, str]:
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
    except OSError as exc:
        raise WorkspaceError(
            f"De tijdelijke bronkopie kon niet worden gecontroleerd: {exc}",
            code="temporary_verify_failed",
        ) from exc
    return byte_count, digest.hexdigest()


def _derived_storage_bytes(root: Path) -> int:
    """Count active derived text bytes without following managed symlinks."""
    derived_root = root / ".opencntx" / "derived"
    if not derived_root.exists():
        return 0
    if derived_root.is_symlink() or not derived_root.is_dir():
        raise WorkspaceError(
            ".opencntx/derived moet een veilige gewone map zijn.",
            code="derived_storage_invalid",
        )
    total = 0
    try:
        for current, directory_names, file_names in os.walk(
            derived_root, topdown=True, followlinks=False
        ):
            current_path = Path(current)
            for name in directory_names:
                if (current_path / name).is_symlink():
                    raise WorkspaceError(
                        "Een afleidingsmap mag geen symlink zijn.",
                        code="derived_storage_invalid",
                    )
            for name in file_names:
                path = current_path / name
                if path.is_symlink():
                    raise WorkspaceError(
                        "Een afleidingsbestand mag geen symlink zijn.",
                        code="derived_storage_invalid",
                    )
                if name == "content.txt":
                    if not path.is_file():
                        raise WorkspaceError(
                            "Afgeleide content moet een regulier bestand zijn.",
                            code="derived_storage_invalid",
                        )
                    total += path.stat().st_size
    except WorkspaceError:
        raise
    except OSError as exc:
        raise WorkspaceError(
            f"Afgeleide opslag kan niet veilig worden gemeten: {exc}",
            code="derived_storage_unavailable",
        ) from exc
    return total


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        _write_new_file(temporary, _json_bytes(value))
        os.replace(temporary, path)
    except OSError as exc:
        raise WorkspaceError(
            f"Registratie kon niet atomair worden geschreven: {exc}",
            code="receipt_write_failed",
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _receipt_name(attempt_id: str) -> str:
    return f"{attempt_id}.json"


def _write_receipt(
    root: Path,
    *,
    attempt_id: str,
    captured_at: datetime,
    status: str,
    original_name: str,
    privacy: str,
    origin: str | None,
    source_id: str | None = None,
    byte_count: int | None = None,
    sha256: str | None = None,
    error_code: str | None = None,
    error: str | None = None,
) -> Path:
    receipts = _validate_managed_path(root, Path(".opencntx") / "receipts", directory=True)
    receipt_path = receipts / _receipt_name(attempt_id)
    receipt = {
        "attempt_id": attempt_id,
        "bytes": byte_count,
        "captured_at": _timestamp(captured_at),
        "error": error,
        "error_code": error_code,
        "format": RECEIPT_FORMAT,
        "format_version": RECEIPT_FORMAT_VERSION,
        "origin": origin,
        "original_name": original_name,
        "privacy": privacy,
        "sha256": sha256,
        "source_id": source_id,
        "status": status,
    }
    _atomic_json(receipt_path, receipt)
    return receipt_path


def _try_failure_receipt(
    root: Path,
    *,
    attempt_id: str,
    captured_at: datetime,
    original_name: str,
    privacy: str,
    origin: str | None,
    error: WorkspaceError,
) -> None:
    try:
        _write_receipt(
            root,
            attempt_id=attempt_id,
            captured_at=captured_at,
            status="NOT_CAPTURED",
            original_name=original_name,
            privacy=privacy,
            origin=origin,
            error_code=error.code,
            error=f"Capture failed: {error.code}",
        )
    except WorkspaceError:
        pass


def _new_source_id(captured_at: datetime, existing: dict[str, StoredSource]) -> str:
    date = captured_at.strftime("%Y%m%d")
    for _ in range(10):
        source_id = f"SRC-{date}-{uuid4().hex[:12]}"
        if source_id not in existing:
            return source_id
    raise WorkspaceError(
        "Er kon geen unieke source-ID worden gemaakt.",
        code="source_id_failed",
    )


def _safe_month_directory(root: Path, captured_at: datetime) -> Path:
    sources = _validate_managed_path(root, Path("SOURCES"), directory=True)
    current = sources
    for name in (captured_at.strftime("%Y"), captured_at.strftime("%m")):
        candidate = current / name
        if candidate.is_symlink():
            raise WorkspaceError(
                f"Bronopslagpad mag geen symlink zijn: {candidate.relative_to(root).as_posix()}",
                code="managed_path_symlink",
            )
        try:
            candidate.mkdir(exist_ok=True)
        except OSError as exc:
            raise WorkspaceError(
                f"Bronopslagmap kon niet worden gemaakt: {exc}",
                code="source_directory_failed",
            ) from exc
        if not candidate.is_dir():
            raise WorkspaceError(
                "Bronopslagpad is geen gewone map.",
                code="source_directory_failed",
            )
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise WorkspaceError(
                "Bronopslagpad verlaat de projectroot.",
                code="managed_path_escape",
            )
        current = resolved
    return current


def _prepare_capture_plan(
    root: Path,
    source_path: Path,
    *,
    config: WorkspaceConfig,
    stored: dict[str, StoredSource],
    captured_at: datetime,
    attempt_id: str,
    original_name: str,
    privacy: str,
    origin: str | None,
    supersedes: str | None,
) -> _CapturePlan:
    if supersedes is not None and (
        SOURCE_ID_PATTERN.fullmatch(supersedes) is None or supersedes not in stored
    ):
        raise WorkspaceError(
            f"Onbekende supersedes-bron: {supersedes}",
            code="supersedes_invalid",
        )

    requested_source = source_path.absolute()
    if requested_source.is_symlink():
        raise WorkspaceError(
            "Het bronbestand mag geen symlink zijn.",
            code="source_symlink",
        )
    if not requested_source.is_file():
        raise WorkspaceError(
            "De bron moet één bestaand regulier bestand zijn.",
            code="source_not_file",
        )
    try:
        resolved_source = requested_source.resolve(strict=True)
        initial_stat = resolved_source.stat()
    except OSError as exc:
        raise WorkspaceError(
            f"Het bronbestand is niet toegankelijk: {exc}",
            code="source_unavailable",
        ) from exc
    if resolved_source.is_relative_to(root / "SOURCES") or resolved_source.is_relative_to(
        root / ".opencntx"
    ):
        raise WorkspaceError(
            "Een beheerde bron of interne OPENCNTX-staat kan niet opnieuw worden gecaptured.",
            code="source_managed_path",
        )
    if initial_stat.st_size > config.max_source_bytes:
        raise WorkspaceError(
            f"Bronbudget overschreden: {initial_stat.st_size} > {config.max_source_bytes} bytes.",
            code="source_budget_exceeded",
        )

    from .lifecycle import require_disk_capacity

    require_disk_capacity(
        root,
        initial_stat.st_size * 2 + 16 * 1024,
        "workspace-capture",
    )
    return _CapturePlan(
        root=root,
        config=config,
        stored=stored,
        captured_at=captured_at,
        attempt_id=attempt_id,
        original_name=original_name,
        original_filename=f"original{_original_suffix(original_name)}",
        privacy=privacy,
        origin=origin,
        supersedes=supersedes,
        resolved_source=resolved_source,
        initial_stat=initial_stat,
    )


def _stage_capture(plan: _CapturePlan) -> tuple[Path, int, str]:
    opencntx = plan.root / ".opencntx"
    if opencntx.is_symlink() or not opencntx.is_dir():
        raise WorkspaceError(
            ".opencntx moet een veilige gewone map zijn.",
            code="managed_path_invalid",
        )
    temporary = opencntx / f".capture-{uuid4().hex}"
    try:
        temporary.mkdir(mode=0o700)
        temporary_original = temporary / plan.original_filename
        try:
            with plan.resolved_source.open("rb") as source, temporary_original.open("xb") as output:
                byte_count, digest = _copy_and_hash(source, output)
            if os.name != "nt":
                os.chmod(temporary_original, 0o600)
            final_stat = plan.resolved_source.stat()
        except OSError as exc:
            raise WorkspaceError(
                f"Het bronbestand kon niet volledig worden gecaptured: {exc}",
                code="source_read_failed",
            ) from exc
        changed = (
            _source_identity(plan.initial_stat) != _source_identity(final_stat)
            or byte_count != plan.initial_stat.st_size
        )
        if changed:
            raise WorkspaceError(
                "Het bronbestand veranderde tijdens capture; er is niets opgeslagen.",
                code="source_changed",
            )
        verified_bytes, verified_digest = _hash_file(temporary_original)
        if verified_bytes != byte_count or verified_digest != digest:
            raise WorkspaceError(
                "De tijdelijke bronkopie wijkt af na schrijven; er is niets opgeslagen.",
                code="temporary_verify_failed",
            )
        return temporary, byte_count, digest
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise


def _duplicate_capture(
    plan: _CapturePlan,
    temporary: Path,
    byte_count: int,
    digest: str,
) -> CaptureResult | None:
    duplicate = next(
        (
            item
            for item in plan.stored.values()
            if item.byte_count == byte_count and item.sha256 == digest
        ),
        None,
    )
    if duplicate is None:
        return None
    duplicate_bytes, duplicate_digest = _hash_file(duplicate.original_path)
    if duplicate_bytes != duplicate.byte_count or duplicate_digest != duplicate.sha256:
        raise WorkspaceError(
            "De bestaande identieke bron wijkt af van haar registratie; "
            "capture is gestopt voor controle.",
            code="stored_source_drift",
        )
    if duplicate.privacy != plan.privacy:
        raise WorkspaceError(
            "Een identieke bron bestaat al met een ander privacylabel; "
            "de bestaande classificatie is niet gewijzigd.",
            code="duplicate_privacy_conflict",
        )
    if plan.supersedes is not None:
        raise WorkspaceError(
            "Een identieke bron kan niet als nieuwe vervangende versie worden opgeslagen.",
            code="supersedes_duplicate",
        )
    shutil.rmtree(temporary, ignore_errors=True)
    receipt = _write_receipt(
        plan.root,
        attempt_id=plan.attempt_id,
        captured_at=plan.captured_at,
        status="DUPLICATE",
        original_name=plan.original_name,
        privacy=plan.privacy,
        origin=plan.origin,
        source_id=duplicate.source_id,
        byte_count=byte_count,
        sha256=digest,
    )
    return CaptureResult(
        status="DUPLICATE",
        source_id=duplicate.source_id,
        byte_count=byte_count,
        sha256=digest,
        receipt_path=receipt,
    )


def _publish_capture(
    plan: _CapturePlan,
    temporary: Path,
    byte_count: int,
    digest: str,
    transaction: Transaction | None,
) -> CaptureResult:
    current_total = sum(item.byte_count for item in plan.stored.values())
    current_total += _derived_storage_bytes(plan.root)
    if current_total + byte_count > plan.config.max_storage_bytes:
        raise WorkspaceError(
            "Totaal opslagbudget wordt overschreden: "
            f"{current_total + byte_count} > {plan.config.max_storage_bytes} bytes.",
            code="storage_budget_exceeded",
        )

    source_id = _new_source_id(plan.captured_at, plan.stored)
    month_directory = _safe_month_directory(plan.root, plan.captured_at)
    final_directory = month_directory / source_id
    if final_directory.exists() or final_directory.is_symlink():
        raise WorkspaceError(
            f"Doelbron bestaat onverwacht al: {source_id}",
            code="source_id_conflict",
        )
    stored_path = (
        Path("SOURCES")
        / plan.captured_at.strftime("%Y")
        / plan.captured_at.strftime("%m")
        / source_id
        / plan.original_filename
    ).as_posix()
    record = {
        "bytes": byte_count,
        "captured_at": _timestamp(plan.captured_at),
        "format": SOURCE_RECORD_FORMAT,
        "format_version": SOURCE_RECORD_VERSION,
        "origin": plan.origin,
        "original_name": plan.original_name,
        "privacy": plan.privacy,
        "sha256": digest,
        "source_id": source_id,
        "status": "CAPTURED",
        "stored_path": stored_path,
        "supersedes": plan.supersedes,
    }
    _write_new_file(temporary / "record.json", _json_bytes(record))
    if transaction is not None:
        transaction.track_target(final_directory)
    try:
        os.replace(temporary, final_directory)
    except OSError as exc:
        raise WorkspaceError(
            f"De bron kon niet atomair zichtbaar worden gemaakt: {exc}",
            code="source_publish_failed",
        ) from exc
    if transaction is not None:
        transaction.mark_target_published(final_directory)
        transaction.mark_published()
    try:
        receipt = _write_receipt(
            plan.root,
            attempt_id=plan.attempt_id,
            captured_at=plan.captured_at,
            status="CAPTURED",
            original_name=plan.original_name,
            privacy=plan.privacy,
            origin=plan.origin,
            source_id=source_id,
            byte_count=byte_count,
            sha256=digest,
        )
        if transaction is not None:
            transaction.mark_receipted(receipt)
    except WorkspaceError:
        shutil.rmtree(final_directory, ignore_errors=True)
        raise
    return CaptureResult(
        status="CAPTURED",
        source_id=source_id,
        byte_count=byte_count,
        sha256=digest,
        receipt_path=receipt,
    )


def _execute_capture(
    plan: _CapturePlan,
    transaction: Transaction | None,
) -> CaptureResult:
    temporary, byte_count, digest = _stage_capture(plan)
    try:
        duplicate = _duplicate_capture(plan, temporary, byte_count, digest)
        if duplicate is not None:
            return duplicate
        return _publish_capture(plan, temporary, byte_count, digest, transaction)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def _capture_source_unlocked(
    project_root: Path,
    source_path: Path,
    *,
    privacy: str = "PRIVATE",
    origin: str | None = None,
    supersedes: str | None = None,
    _transaction: Transaction | None = None,
) -> CaptureResult:
    """Capture one regular local file without executing or interpreting it."""
    captured_at = _utc_now()
    attempt_id = f"ATT-{captured_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
    original_name = _safe_original_name(source_path.name)
    root: Path | None = None
    normalized_privacy = privacy.strip().upper() or "PRIVATE"
    normalized_origin: str | None = origin
    try:
        root = validate_workspace(project_root)
        config = load_workspace_config(root)
        normalized_privacy = _validate_privacy(privacy)
        normalized_origin = _validate_origin(origin)
        stored = _stored_sources(root)
        plan = _prepare_capture_plan(
            root,
            source_path,
            config=config,
            stored=stored,
            captured_at=captured_at,
            attempt_id=attempt_id,
            original_name=original_name,
            privacy=normalized_privacy,
            origin=normalized_origin,
            supersedes=supersedes,
        )
        return _execute_capture(plan, _transaction)
    except WorkspaceError as exc:
        if root is not None:
            _try_failure_receipt(
                root,
                attempt_id=attempt_id,
                captured_at=captured_at,
                original_name=original_name,
                privacy=normalized_privacy,
                origin=normalized_origin,
                error=exc,
            )
        raise
    except OSError as exc:
        error = WorkspaceError(
            f"De capture kon niet veilig worden voltooid: {exc}",
            code="capture_io_failed",
        )
        if root is not None:
            _try_failure_receipt(
                root,
                attempt_id=attempt_id,
                captured_at=captured_at,
                original_name=original_name,
                privacy=normalized_privacy,
                origin=normalized_origin,
                error=error,
            )
        raise error from exc


_TEST_BEFORE_CAPTURE_LOCK = None


def capture_source(
    project_root: Path,
    source_path: Path,
    *,
    privacy: str = "PRIVATE",
    origin: str | None = None,
    supersedes: str | None = None,
) -> CaptureResult:
    """Capture one source under a workspace-wide lock and source-inventory CAS."""
    root = validate_workspace(project_root)
    expected = state_digest((root / "SOURCES",))
    if _TEST_BEFORE_CAPTURE_LOCK is not None:
        _TEST_BEFORE_CAPTURE_LOCK()
    with writer_transaction(
        root,
        "capture",
        expected_digest=expected,
        current_digest=lambda: state_digest((root / "SOURCES",)),
    ) as transaction:
        return _capture_source_unlocked(
            root,
            source_path,
            privacy=privacy,
            origin=origin,
            supersedes=supersedes,
            _transaction=transaction,
        )
