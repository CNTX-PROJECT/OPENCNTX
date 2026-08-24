"""Human-readable chapters and a rebuildable local workspace catalog."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from .integrity import (
    IntegrityError,
    Transaction,
    state_digest,
    write_new_bytes,
    writer_transaction,
)
from .primitives import (
    pretty_json_bytes as _json_bytes,
)
from .primitives import (
    timestamp_microseconds as _timestamp,
)
from .primitives import (
    utc_now as _utc_now,
)
from .workspace import (
    INDEX_TEMPLATE,
    PRIVACY_LABELS,
    SHA256_PATTERN,
    SOURCE_ID_PATTERN,
    WorkspaceError,
    validate_workspace,
)

CHAPTER_FORMAT = "opencntx-chapter"
CHAPTER_FORMAT_VERSION = 1
INDEX_FORMAT = "opencntx-chapter-index"
INDEX_FORMAT_VERSION = 1
CATALOG_FORMAT = "opencntx-catalog"
CATALOG_FORMAT_VERSION = 1
CATALOG_RECEIPT_FORMAT = "opencntx-catalog-receipt"
CATALOG_RECEIPT_VERSION = 1
LEGACY_INDEX_TEMPLATE = """# Hoofdstukindex

Nog geen hoofdstukken geregistreerd.
"""

CHAPTER_ID_PATTERN = re.compile(r"CH-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
KNOWLEDGE_STATUSES = ("DRAFT", "OWNER_ACCEPTED", "ARCHIVED")
SOURCE_RELATIONS = ("PRIMARY", "SUPPORTING", "CONFLICTING")
SOURCE_INTEGRITIES = ("EXACT", "MISSING", "DRIFTED")
FRESHNESS_STATUSES = ("CURRENT", "STALE", "INCOMPLETE", "ARCHIVED")
MAX_CHAPTER_ID_LENGTH = 64
MAX_TITLE_LENGTH = 120
MAX_SCOPE_LENGTH = 240
MAX_APPROVAL_LENGTH = 256
MAX_CHAPTER_BYTES = 1024 * 1024
HASH_CHUNK_SIZE = 1024 * 1024

REQUIRED_SECTIONS = (
    "Purpose and boundary",
    "Current summary",
    "Sources",
    "Relationships and dependencies",
    "Effective decisions",
    "Open questions and assumptions",
    "Active and blocked tasks",
    "Latest OWNER approval",
    "Freshness",
)
LEGACY_REQUIRED_SECTIONS = (
    "Doel en grens",
    "Huidige samenvatting",
    "Bronnen",
    "Relaties en afhankelijkheden",
    "Geldende besluiten",
    "Open vragen en aannames",
    "Actieve en geblokkeerde taken",
    "Laatste OWNER-goedkeuring",
    "Freshness",
)

CHAPTER_FIELDS = {
    "format",
    "format_version",
    "chapter_id",
    "title",
    "scope",
    "revision",
    "knowledge_status",
    "last_owner_approval",
    "dependency_ids",
    "source_refs",
}
SOURCE_RECORD_FIELDS = {
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
}


class CatalogError(WorkspaceError):
    """A short, stable error raised by chapter and catalog operations."""


@dataclass(frozen=True)
class SourceEntry:
    source_id: str
    record_path: str
    original_path: str
    byte_count: int
    sha256: str
    privacy: str
    captured_at: str
    supersedes: str | None
    integrity: str


@dataclass(frozen=True)
class SourceReference:
    source_id: str
    sha256: str
    relation: str


@dataclass(frozen=True)
class ChapterEntry:
    chapter_id: str
    title: str
    scope: str
    revision: int
    knowledge_status: str
    last_owner_approval: str
    dependency_ids: tuple[str, ...]
    source_refs: tuple[SourceReference, ...]
    relative_path: str
    digest: str
    open_decisions: int


@dataclass(frozen=True)
class CatalogIssue:
    code: str
    object_id: str
    message: str


@dataclass(frozen=True)
class ChapterCreateResult:
    status: str
    chapter_id: str
    chapter_path: Path


@dataclass(frozen=True)
class CatalogResult:
    status: str
    state_digest: str
    source_count: int
    chapter_count: int
    freshness_counts: dict[str, int]
    catalog_path: Path
    index_path: Path
    receipt_path: Path


def _write_new_file(path: Path, content: bytes) -> None:
    write_new_bytes(path, content)


def _write_atomic(path: Path, content: bytes) -> None:
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        _write_new_file(temporary, content)
        os.replace(temporary, path)
    except OSError as exc:
        raise CatalogError(
            f"Bestand kon niet atomair worden vervangen: {path.name}: {exc}",
            code="catalog_write_failed",
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with path.open("rb") as source:
            while chunk := source.read(HASH_CHUNK_SIZE):
                byte_count += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise CatalogError(
            f"Bestand kon niet worden gecontroleerd: {path.name}: {exc}",
            code="catalog_hash_failed",
        ) from exc
    return byte_count, digest.hexdigest()


def _safe_line(value: object, *, field: str, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise CatalogError(f"{field} moet tekst zijn.", code="chapter_schema_invalid")
    if value != value.strip() or "\n" in value or "\r" in value:
        raise CatalogError(f"{field} moet één nette regel zijn.", code="chapter_schema_invalid")
    if not allow_empty and not value:
        raise CatalogError(f"{field} mag niet leeg zijn.", code="chapter_schema_invalid")
    if len(value) > maximum:
        raise CatalogError(
            f"{field} is te lang: maximaal {maximum} tekens.",
            code="chapter_schema_invalid",
        )
    return value


def _validate_chapter_id(value: object) -> str:
    if not isinstance(value, str):
        raise CatalogError("Hoofdstuk-ID moet tekst zijn.", code="chapter_id_invalid")
    if len(value) > MAX_CHAPTER_ID_LENGTH or CHAPTER_ID_PATTERN.fullmatch(value) is None:
        raise CatalogError(
            "Hoofdstuk-ID moet CH- gevolgd door hoofdletters, cijfers en enkele koppeltekens zijn.",
            code="chapter_id_invalid",
        )
    return value


def _relative_managed_file(root: Path, relative_text: object) -> Path:
    if not isinstance(relative_text, str) or not relative_text:
        raise CatalogError("Bronpad ontbreekt in record.", code="source_record_invalid")
    pure = PurePosixPath(relative_text)
    if pure.is_absolute() or ".." in pure.parts or "\\" in relative_text:
        raise CatalogError("Bronrecord bevat een onveilig pad.", code="source_record_invalid")
    path = root.joinpath(*pure.parts)
    if path.is_symlink():
        raise CatalogError(
            "Bronrecord verwijst naar een symlink.", code="catalog_managed_path_symlink"
        )
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise CatalogError(
            "Bronrecord verwijst naar een ontoegankelijke map.",
            code="source_record_invalid",
        ) from exc
    if not parent.is_relative_to(root):
        raise CatalogError(
            "Bronrecord verlaat de projectwerkruimte.", code="catalog_managed_path_escape"
        )
    return path


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError(
            f"Ongeldig bronrecord: {path.name}.", code="source_record_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise CatalogError("Bronrecord moet een JSON-object zijn.", code="source_record_invalid")
    return value


def _load_sources(root: Path) -> dict[str, SourceEntry]:
    sources_root = root / "SOURCES"
    entries: dict[str, SourceEntry] = {}
    record_paths = sorted(
        sources_root.rglob("record.json"),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for record_path in record_paths:
        if record_path.is_symlink():
            raise CatalogError(
                "Een bronrecord mag geen symlink zijn.",
                code="catalog_managed_path_symlink",
            )
        try:
            resolved_record = record_path.resolve(strict=True)
        except OSError as exc:
            raise CatalogError(
                "Een bronrecord is niet toegankelijk.", code="source_record_invalid"
            ) from exc
        if not resolved_record.is_relative_to(sources_root.resolve(strict=True)):
            raise CatalogError(
                "Een bronrecord verlaat SOURCES.", code="catalog_managed_path_escape"
            )
        value = _read_json_object(record_path)
        if set(value) != SOURCE_RECORD_FIELDS:
            raise CatalogError(
                "Bronrecord heeft onbekende of ontbrekende velden.",
                code="source_record_invalid",
            )
        source_id = value.get("source_id")
        if not isinstance(source_id, str) or SOURCE_ID_PATTERN.fullmatch(source_id) is None:
            raise CatalogError("Ongeldige source-ID in record.", code="source_record_invalid")
        if source_id in entries:
            raise CatalogError(f"Dubbele source-ID: {source_id}.", code="source_id_duplicate")
        if record_path.parent.name != source_id:
            raise CatalogError(
                f"Source-ID en bronmap verschillen: {source_id}.",
                code="source_record_invalid",
            )
        relative_parts = record_path.relative_to(root).parts
        if (
            len(relative_parts) != 5
            or relative_parts[0] != "SOURCES"
            or re.fullmatch(r"\d{4}", relative_parts[1]) is None
            or re.fullmatch(r"(?:0[1-9]|1[0-2])", relative_parts[2]) is None
            or relative_parts[3] != source_id
            or relative_parts[4] != "record.json"
        ):
            raise CatalogError(
                "Bronrecord staat niet onder SOURCES/<jaar>/<maand>/<SOURCE-ID>/.",
                code="source_record_invalid",
            )
        byte_count = value.get("bytes")
        sha256 = value.get("sha256")
        privacy = value.get("privacy")
        captured_at = value.get("captured_at")
        supersedes = value.get("supersedes")
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
            raise CatalogError("Ongeldige bronbytes in record.", code="source_record_invalid")
        if not isinstance(sha256, str) or SHA256_PATTERN.fullmatch(sha256) is None:
            raise CatalogError("Ongeldige bronhash in record.", code="source_record_invalid")
        if privacy not in PRIVACY_LABELS:
            raise CatalogError("Ongeldig privacylabel in record.", code="source_record_invalid")
        if not isinstance(captured_at, str) or not captured_at:
            raise CatalogError("Ontvangsttijd ontbreekt in record.", code="source_record_invalid")
        if supersedes is not None and (
            not isinstance(supersedes, str)
            or SOURCE_ID_PATTERN.fullmatch(supersedes) is None
            or supersedes == source_id
        ):
            raise CatalogError("Ongeldige supersedes-relatie.", code="source_record_invalid")
        if value.get("format") != "opencntx-source" or value.get("format_version") != 1:
            raise CatalogError("Onbekend bronrecordformaat.", code="source_record_invalid")
        if value.get("status") != "CAPTURED":
            raise CatalogError("Bronrecord is niet CAPTURED.", code="source_record_invalid")
        original = _relative_managed_file(root, value.get("stored_path"))
        if original.parent != record_path.parent:
            raise CatalogError(
                "Bronrecord verwijst niet naar het origineel in zijn eigen bronmap.",
                code="source_record_invalid",
            )
        relative_record = record_path.relative_to(root).as_posix()
        relative_original = original.relative_to(root).as_posix()
        if not original.exists():
            integrity = "MISSING"
        elif not original.is_file():
            integrity = "DRIFTED"
        else:
            actual_bytes, actual_hash = _hash_file(original)
            integrity = (
                "EXACT" if actual_bytes == byte_count and actual_hash == sha256 else "DRIFTED"
            )
        entries[source_id] = SourceEntry(
            source_id=source_id,
            record_path=relative_record,
            original_path=relative_original,
            byte_count=byte_count,
            sha256=sha256,
            privacy=privacy,
            captured_at=captured_at,
            supersedes=supersedes,
            integrity=integrity,
        )
    for source in entries.values():
        if source.supersedes is not None and source.supersedes not in entries:
            raise CatalogError(
                f"Bron {source.source_id} verwijst naar onbekende voorganger.",
                code="source_supersedes_unknown",
            )
    return entries


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "+++":
        raise CatalogError("CHAPTER.md mist TOML-frontmatter.", code="chapter_schema_invalid")
    closing: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "+++":
            closing = index
            break
    if closing is None:
        raise CatalogError(
            "CHAPTER.md heeft geen afsluitende +++-regel.",
            code="chapter_schema_invalid",
        )
    try:
        metadata = tomllib.loads("".join(lines[1:closing]))
    except tomllib.TOMLDecodeError as exc:
        raise CatalogError(
            f"Ongeldige TOML in CHAPTER.md: {exc}", code="chapter_schema_invalid"
        ) from exc
    return metadata, "".join(lines[closing + 1 :])


def _validate_sections(body: str) -> int:
    body_lines = body.splitlines()
    valid_positions: list[list[int]] = []
    for sections in (REQUIRED_SECTIONS, LEGACY_REQUIRED_SECTIONS):
        positions: list[int] = []
        for section in sections:
            heading = f"## {section}"
            matches = [index for index, line in enumerate(body_lines) if line == heading]
            if len(matches) != 1:
                break
            positions.append(matches[0])
        if len(positions) == len(sections) and positions == sorted(positions):
            valid_positions.append(positions)
    if len(valid_positions) != 1:
        raise CatalogError(
            "CHAPTER.md must contain exactly one complete current or legacy section set in the fixed order.",
            code="chapter_sections_invalid",
        )
    positions = valid_positions[0]
    decisions_start = positions[4] + 1
    decisions_end = positions[5]
    return sum(
        1
        for line in body_lines[decisions_start:decisions_end]
        if line.strip().upper().startswith("- [OPEN]")
    )


def _parse_source_refs(value: object) -> tuple[SourceReference, ...]:
    if not isinstance(value, list):
        raise CatalogError("source_refs moet een lijst zijn.", code="chapter_schema_invalid")
    refs: list[SourceReference] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"source_id", "sha256", "relation"}:
            raise CatalogError(
                "Iedere source_ref vereist exact source_id, sha256 en relation.",
                code="chapter_schema_invalid",
            )
        source_id = item["source_id"]
        sha256 = item["sha256"]
        relation = item["relation"]
        if not isinstance(source_id, str) or SOURCE_ID_PATTERN.fullmatch(source_id) is None:
            raise CatalogError("Ongeldige source-ID in hoofdstuk.", code="chapter_schema_invalid")
        if not isinstance(sha256, str) or SHA256_PATTERN.fullmatch(sha256) is None:
            raise CatalogError("Ongeldige bronpin in hoofdstuk.", code="chapter_schema_invalid")
        if relation not in SOURCE_RELATIONS:
            raise CatalogError(
                "Ongeldige bronrelatie in hoofdstuk.",
                code="chapter_schema_invalid",
            )
        if source_id in seen:
            raise CatalogError("Dubbele source_ref in hoofdstuk.", code="chapter_schema_invalid")
        seen.add(source_id)
        refs.append(SourceReference(source_id, sha256, relation))
    return tuple(sorted(refs, key=lambda ref: ref.source_id))


def _parse_dependencies(value: object, chapter_id: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CatalogError("dependency_ids moet een lijst zijn.", code="chapter_schema_invalid")
    dependencies: list[str] = []
    for item in value:
        dependency = _validate_chapter_id(item)
        if dependency == chapter_id:
            raise CatalogError(
                "Een hoofdstuk mag niet van zichzelf afhangen.",
                code="chapter_dependency_self",
            )
        if dependency in dependencies:
            raise CatalogError("Dubbele hoofdstukafhankelijkheid.", code="chapter_schema_invalid")
        dependencies.append(dependency)
    return tuple(sorted(dependencies))


def _parse_chapter(root: Path, path: Path) -> ChapterEntry:
    if path.is_symlink() or path.parent.is_symlink():
        raise CatalogError(
            "Een hoofdstukpad mag geen symlink zijn.",
            code="catalog_managed_path_symlink",
        )
    try:
        size = path.stat().st_size
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CatalogError("Hoofdstuk is niet toegankelijk.", code="chapter_unavailable") from exc
    chapters_root = (root / "CHAPTERS").resolve(strict=True)
    if not resolved.is_relative_to(chapters_root):
        raise CatalogError("Hoofdstuk verlaat CHAPTERS.", code="catalog_managed_path_escape")
    if size > MAX_CHAPTER_BYTES:
        raise CatalogError("CHAPTER.md is groter dan 1 MiB.", code="chapter_too_large")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise CatalogError(
            "CHAPTER.md moet geldige UTF-8-tekst zijn.", code="chapter_unavailable"
        ) from exc
    metadata, body = _split_frontmatter(text)
    unknown = set(metadata) - CHAPTER_FIELDS
    missing = CHAPTER_FIELDS - set(metadata)
    if unknown or missing:
        raise CatalogError(
            "CHAPTER.md heeft onbekende of ontbrekende frontmattervelden.",
            code="chapter_schema_invalid",
        )
    if metadata["format"] != CHAPTER_FORMAT or metadata["format_version"] != CHAPTER_FORMAT_VERSION:
        raise CatalogError("Onbekend hoofdstukformaat.", code="chapter_schema_invalid")
    chapter_id = _validate_chapter_id(metadata["chapter_id"])
    if path.parent.name != chapter_id:
        raise CatalogError("Hoofdstuk-ID en mapnaam verschillen.", code="chapter_id_path_mismatch")
    title = _safe_line(metadata["title"], field="title", maximum=MAX_TITLE_LENGTH)
    scope = _safe_line(metadata["scope"], field="scope", maximum=MAX_SCOPE_LENGTH)
    revision = metadata["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision <= 0:
        raise CatalogError("revision moet positief zijn.", code="chapter_schema_invalid")
    knowledge_status = metadata["knowledge_status"]
    if knowledge_status not in KNOWLEDGE_STATUSES:
        raise CatalogError("Onbekende knowledge_status.", code="chapter_schema_invalid")
    approval = _safe_line(
        metadata["last_owner_approval"],
        field="last_owner_approval",
        maximum=MAX_APPROVAL_LENGTH,
        allow_empty=True,
    )
    dependencies = _parse_dependencies(metadata["dependency_ids"], chapter_id)
    source_refs = _parse_source_refs(metadata["source_refs"])
    open_decisions = _validate_sections(body)
    return ChapterEntry(
        chapter_id=chapter_id,
        title=title,
        scope=scope,
        revision=revision,
        knowledge_status=knowledge_status,
        last_owner_approval=approval,
        dependency_ids=dependencies,
        source_refs=source_refs,
        relative_path=path.relative_to(root).as_posix(),
        digest=hashlib.sha256(raw).hexdigest(),
        open_decisions=open_decisions,
    )


def _load_chapters(root: Path) -> dict[str, ChapterEntry]:
    chapter_paths = sorted(
        (root / "CHAPTERS").glob("CH-*/CHAPTER.md"),
        key=lambda path: path.parent.name,
    )
    all_chapter_files = sorted((root / "CHAPTERS").rglob("CHAPTER.md"))
    if set(chapter_paths) != set(all_chapter_files):
        raise CatalogError(
            "CHAPTER.md staat buiten CHAPTERS/<CHAPTER-ID>/.",
            code="chapter_path_invalid",
        )
    chapters: dict[str, ChapterEntry] = {}
    for path in chapter_paths:
        chapter = _parse_chapter(root, path)
        if chapter.chapter_id in chapters:
            raise CatalogError(
                f"Dubbel hoofdstuk-ID: {chapter.chapter_id}.",
                code="chapter_id_duplicate",
            )
        chapters[chapter.chapter_id] = chapter
    return chapters


def _detect_dependency_cycles(chapters: dict[str, ChapterEntry]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(chapter_id: str, path: tuple[str, ...]) -> None:
        if chapter_id in visiting:
            cycle = " -> ".join(path + (chapter_id,))
            raise CatalogError(
                f"Hoofdstukafhankelijkheid bevat een cyclus: {cycle}.",
                code="chapter_dependency_cycle",
            )
        if chapter_id in visited:
            return
        visiting.add(chapter_id)
        chapter = chapters[chapter_id]
        for dependency in chapter.dependency_ids:
            if dependency in chapters:
                visit(dependency, path + (chapter_id,))
        visiting.remove(chapter_id)
        visited.add(chapter_id)

    for chapter_id in sorted(chapters):
        visit(chapter_id, ())


def _calculate_freshness(
    sources: dict[str, SourceEntry], chapters: dict[str, ChapterEntry]
) -> tuple[dict[str, str], list[CatalogIssue]]:
    _detect_dependency_cycles(chapters)
    superseded = {source.supersedes for source in sources.values() if source.supersedes}
    memo: dict[str, str] = {}
    issues: list[CatalogIssue] = []

    def freshness(chapter_id: str) -> str:
        if chapter_id in memo:
            return memo[chapter_id]
        chapter = chapters[chapter_id]
        if chapter.knowledge_status == "ARCHIVED":
            memo[chapter_id] = "ARCHIVED"
            return "ARCHIVED"
        is_stale = False
        is_incomplete = chapter.knowledge_status == "DRAFT" or not chapter.source_refs
        if chapter.knowledge_status == "OWNER_ACCEPTED" and not chapter.last_owner_approval:
            is_incomplete = True
            issues.append(
                CatalogIssue(
                    "owner_approval_missing",
                    chapter_id,
                    "OWNER_ACCEPTED is missing an OWNER reference.",
                )
            )
        for reference in chapter.source_refs:
            source = sources.get(reference.source_id)
            if source is None:
                is_incomplete = True
                issues.append(
                    CatalogIssue(
                        "chapter_source_unknown",
                        chapter_id,
                        f"Unknown source: {reference.source_id}.",
                    )
                )
                continue
            if reference.sha256 != source.sha256:
                is_stale = True
                issues.append(
                    CatalogIssue(
                        "chapter_source_pin_stale",
                        chapter_id,
                        f"Source pin differs: {reference.source_id}.",
                    )
                )
            if source.integrity != "EXACT":
                is_stale = True
                issues.append(
                    CatalogIssue(
                        f"source_{source.integrity.lower()}",
                        chapter_id,
                        f"Source is {source.integrity}: {reference.source_id}.",
                    )
                )
            if reference.source_id in superseded:
                is_stale = True
                issues.append(
                    CatalogIssue(
                        "chapter_source_superseded",
                        chapter_id,
                        f"Source is superseded: {reference.source_id}.",
                    )
                )
        for dependency in chapter.dependency_ids:
            if dependency not in chapters:
                is_incomplete = True
                issues.append(
                    CatalogIssue(
                        "chapter_dependency_unknown",
                        chapter_id,
                        f"Unknown dependency: {dependency}.",
                    )
                )
                continue
            dependency_freshness = freshness(dependency)
            if dependency_freshness in {"STALE", "ARCHIVED"}:
                is_stale = True
            elif dependency_freshness == "INCOMPLETE":
                is_incomplete = True
        if is_stale:
            result = "STALE"
        elif is_incomplete:
            result = "INCOMPLETE"
        else:
            result = "CURRENT"
        memo[chapter_id] = result
        return result

    for chapter_id in sorted(chapters):
        freshness(chapter_id)
    return memo, sorted(issues, key=lambda issue: (issue.object_id, issue.code, issue.message))


def _state_model(
    sources: dict[str, SourceEntry],
    chapters: dict[str, ChapterEntry],
    freshness: dict[str, str],
    issues: list[CatalogIssue],
) -> dict[str, Any]:
    return {
        "format": CATALOG_FORMAT,
        "format_version": CATALOG_FORMAT_VERSION,
        "sources": [
            {
                "source_id": source.source_id,
                "record_path": source.record_path,
                "original_path": source.original_path,
                "bytes": source.byte_count,
                "sha256": source.sha256,
                "privacy": source.privacy,
                "captured_at": source.captured_at,
                "supersedes": source.supersedes,
                "integrity": source.integrity,
            }
            for source in (sources[source_id] for source_id in sorted(sources))
        ],
        "chapters": [
            {
                "chapter_id": chapter.chapter_id,
                "title": chapter.title,
                "scope": chapter.scope,
                "revision": chapter.revision,
                "knowledge_status": chapter.knowledge_status,
                "last_owner_approval": chapter.last_owner_approval,
                "dependency_ids": list(chapter.dependency_ids),
                "source_refs": [
                    {
                        "source_id": reference.source_id,
                        "sha256": reference.sha256,
                        "relation": reference.relation,
                    }
                    for reference in chapter.source_refs
                ],
                "relative_path": chapter.relative_path,
                "digest": chapter.digest,
                "open_decisions": chapter.open_decisions,
                "freshness": freshness[chapter.chapter_id],
            }
            for chapter in (chapters[chapter_id] for chapter_id in sorted(chapters))
        ],
        "issues": [issue.__dict__ for issue in issues],
    }


def _state_digest(model: dict[str, Any]) -> str:
    canonical = json.dumps(model, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(canonical).hexdigest()


def _markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _render_index(
    chapters: dict[str, ChapterEntry],
    freshness: dict[str, str],
    state_digest: str,
    generated_at: datetime,
) -> bytes:
    counts = {status: 0 for status in FRESHNESS_STATUSES}
    for status in freshness.values():
        counts[status] += 1
    body_lines = [
        "# Chapter index",
        "",
        "> Automatically rebuilt map. Official knowledge remains in source records",
        "> and CHAPTER.md files. This index grants no OWNER authority.",
        "",
        "## Overview",
        "",
        f"- CURRENT: {counts['CURRENT']}",
        f"- STALE: {counts['STALE']}",
        f"- INCOMPLETE: {counts['INCOMPLETE']}",
        f"- ARCHIVED: {counts['ARCHIVED']}",
        "",
        "## Chapters",
        "",
    ]
    if not chapters:
        body_lines.append("No chapters registered yet.")
    else:
        body_lines.extend(
            [
                (
                    "| ID | Title | Scope | Knowledge status | Revision | Freshness | "
                    "Dependencies | Open decisions | Path | Digest |"
                ),
                "| --- | --- | --- | --- | ---: | --- | --- | ---: | --- | --- |",
            ]
        )
        for chapter_id in sorted(chapters):
            chapter = chapters[chapter_id]
            dependencies = ", ".join(chapter.dependency_ids) or "-"
            body_lines.append(
                "| "
                + " | ".join(
                    (
                        chapter.chapter_id,
                        _markdown_cell(chapter.title),
                        _markdown_cell(chapter.scope),
                        chapter.knowledge_status,
                        str(chapter.revision),
                        freshness[chapter_id],
                        dependencies,
                        str(chapter.open_decisions),
                        chapter.relative_path,
                        chapter.digest,
                    )
                )
                + " |"
            )
    body = ("\n".join(body_lines) + "\n").encode("utf-8")
    indexed_body = b"\n" + body
    header = (
        "\n".join(
            (
                "---",
                f"format: {INDEX_FORMAT}",
                f"format_version: {INDEX_FORMAT_VERSION}",
                f"generated_at: {_timestamp(generated_at)}",
                f"workspace_state_digest: {state_digest}",
                f"index_body_sha256: {hashlib.sha256(indexed_body).hexdigest()}",
                "---",
            )
        )
        + "\n"
    ).encode("utf-8")
    return header + indexed_body


def _index_is_managed(path: Path, catalog_path: Path) -> bool:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise CatalogError("CHAPTERS/INDEX.md is niet leesbaar.", code="index_unavailable") from exc
    if content in {
        INDEX_TEMPLATE.encode("utf-8"),
        LEGACY_INDEX_TEMPLATE.encode("utf-8"),
    }:
        return True
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        return False
    lines = text.splitlines(keepends=True)
    closing: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            closing = index
            break
    if closing is None:
        return False
    header_lines = [line.rstrip("\r\n") for line in lines[1:closing]]
    body_digest_line = next(
        (line for line in header_lines if line.startswith("index_body_sha256: ")),
        None,
    )
    if (
        f"format: {INDEX_FORMAT}" not in header_lines
        or f"format_version: {INDEX_FORMAT_VERSION}" not in header_lines
        or body_digest_line is None
    ):
        return False
    declared_body_digest = body_digest_line.removeprefix("index_body_sha256: ")
    body = "".join(lines[closing + 1 :]).encode("utf-8")
    if (
        SHA256_PATTERN.fullmatch(declared_body_digest) is None
        or hashlib.sha256(body).hexdigest() != declared_body_digest
    ):
        return False
    if not catalog_path.is_file() or catalog_path.is_symlink():
        return True
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{catalog_path.as_posix()}?mode=ro", uri=True)
        row = connection.execute(
            "SELECT value FROM catalog_meta WHERE key = 'index_sha256'"
        ).fetchone()
    except sqlite3.Error:
        return True
    finally:
        if connection is not None:
            connection.close()
    return (
        row is not None
        and isinstance(row[0], str)
        and row[0] == hashlib.sha256(content).hexdigest()
    )


def _build_sqlite(
    path: Path,
    *,
    generated_at: datetime,
    state_digest: str,
    index_sha256: str,
    sources: dict[str, SourceEntry],
    chapters: dict[str, ChapterEntry],
    freshness: dict[str, str],
    issues: list[CatalogIssue],
) -> None:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE catalog_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE sources (
                source_id TEXT PRIMARY KEY,
                record_path TEXT NOT NULL,
                original_path TEXT NOT NULL,
                bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                privacy TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                supersedes TEXT,
                integrity TEXT NOT NULL
            );
            CREATE TABLE chapters (
                chapter_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                scope TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                revision INTEGER NOT NULL,
                knowledge_status TEXT NOT NULL,
                last_owner_approval TEXT NOT NULL,
                chapter_digest TEXT NOT NULL,
                freshness TEXT NOT NULL,
                open_decisions INTEGER NOT NULL
            );
            CREATE TABLE chapter_sources (
                chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
                source_id TEXT NOT NULL REFERENCES sources(source_id),
                pinned_sha256 TEXT NOT NULL,
                relation TEXT NOT NULL,
                PRIMARY KEY (chapter_id, source_id)
            );
            CREATE TABLE chapter_dependencies (
                chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
                depends_on TEXT NOT NULL REFERENCES chapters(chapter_id),
                PRIMARY KEY (chapter_id, depends_on)
            );
            CREATE TABLE catalog_issues (
                issue_number INTEGER PRIMARY KEY,
                code TEXT NOT NULL,
                object_id TEXT NOT NULL,
                message TEXT NOT NULL
            );
            CREATE INDEX idx_sources_sha256 ON sources(sha256);
            CREATE INDEX idx_sources_privacy ON sources(privacy);
            CREATE INDEX idx_sources_integrity ON sources(integrity);
            CREATE INDEX idx_chapters_title ON chapters(title);
            CREATE INDEX idx_chapters_freshness ON chapters(freshness);
            CREATE INDEX idx_chapter_sources_source ON chapter_sources(source_id);
            CREATE INDEX idx_chapter_dependencies_target ON chapter_dependencies(depends_on);
            """
        )
        metadata = {
            "format": CATALOG_FORMAT,
            "format_version": str(CATALOG_FORMAT_VERSION),
            "generated_at": _timestamp(generated_at),
            "workspace_state_digest": state_digest,
            "index_sha256": index_sha256,
            "source_count": str(len(sources)),
            "chapter_count": str(len(chapters)),
        }
        connection.executemany(
            "INSERT INTO catalog_meta(key, value) VALUES (?, ?)",
            sorted(metadata.items()),
        )
        connection.executemany(
            """INSERT INTO sources(
                source_id, record_path, original_path, bytes, sha256, privacy,
                captured_at, supersedes, integrity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    source.source_id,
                    source.record_path,
                    source.original_path,
                    source.byte_count,
                    source.sha256,
                    source.privacy,
                    source.captured_at,
                    source.supersedes,
                    source.integrity,
                )
                for source in (sources[source_id] for source_id in sorted(sources))
            ],
        )
        connection.executemany(
            """INSERT INTO chapters(
                chapter_id, title, scope, relative_path, revision,
                knowledge_status, last_owner_approval, chapter_digest,
                freshness, open_decisions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    chapter.chapter_id,
                    chapter.title,
                    chapter.scope,
                    chapter.relative_path,
                    chapter.revision,
                    chapter.knowledge_status,
                    chapter.last_owner_approval,
                    chapter.digest,
                    freshness[chapter.chapter_id],
                    chapter.open_decisions,
                )
                for chapter in (chapters[chapter_id] for chapter_id in sorted(chapters))
            ],
        )
        source_rows: list[tuple[str, str, str, str]] = []
        dependency_rows: list[tuple[str, str]] = []
        for chapter_id in sorted(chapters):
            chapter = chapters[chapter_id]
            source_rows.extend(
                (chapter_id, reference.source_id, reference.sha256, reference.relation)
                for reference in chapter.source_refs
                if reference.source_id in sources
            )
            dependency_rows.extend(
                (chapter_id, dependency)
                for dependency in chapter.dependency_ids
                if dependency in chapters
            )
        connection.executemany("INSERT INTO chapter_sources VALUES (?, ?, ?, ?)", source_rows)
        connection.executemany("INSERT INTO chapter_dependencies VALUES (?, ?)", dependency_rows)
        connection.executemany(
            "INSERT INTO catalog_issues(issue_number, code, object_id, message) "
            "VALUES (?, ?, ?, ?)",
            [
                (number, issue.code, issue.object_id, issue.message)
                for number, issue in enumerate(issues, start=1)
            ],
        )
        connection.commit()
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            raise CatalogError(
                "SQLite-integriteitscontrole is mislukt.",
                code="catalog_integrity_failed",
            )
        connection.close()
        connection = None
        with path.open("r+b") as database:
            os.fsync(database.fileno())
    except CatalogError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise CatalogError(
            "SQLite-catalogus kon niet worden gebouwd.",
            code="catalog_build_failed",
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def _receipt_path(root: Path, attempt_id: str) -> Path:
    return root / ".opencntx" / "receipts" / f"{attempt_id}.json"


def _write_catalog_receipt(
    root: Path,
    *,
    attempt_id: str,
    generated_at: datetime,
    status: str,
    state_digest: str | None,
    source_count: int,
    chapter_count: int,
    freshness_counts: dict[str, int],
    error: CatalogError | None = None,
) -> Path:
    receipt = {
        "attempt_id": attempt_id,
        "catalog_path": ".opencntx/catalog.sqlite" if status == "CATALOG_REBUILT" else None,
        "chapter_count": chapter_count,
        "error": (f"Catalog rebuild failed: {error.code}." if error is not None else None),
        "error_code": error.code if error is not None else None,
        "format": CATALOG_RECEIPT_FORMAT,
        "format_version": CATALOG_RECEIPT_VERSION,
        "freshness": freshness_counts,
        "generated_at": _timestamp(generated_at),
        "index_path": "CHAPTERS/INDEX.md" if status == "CATALOG_REBUILT" else None,
        "source_count": source_count,
        "status": status,
        "workspace_state_digest": state_digest,
        "recovery_action": (
            "Check the workspace error and run catalog rebuild again."
            if error is not None
            else None
        ),
    }
    path = _receipt_path(root, attempt_id)
    _write_atomic(path, _json_bytes(receipt))
    return path


def _chapter_toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _chapter_template(
    chapter_id: str,
    title: str,
    scope: str,
    source_refs: Iterable[SourceReference],
    dependency_ids: Iterable[str],
) -> bytes:
    dependencies = ", ".join(_chapter_toml_string(item) for item in dependency_ids)
    lines = [
        "+++",
        f'format = "{CHAPTER_FORMAT}"',
        f"format_version = {CHAPTER_FORMAT_VERSION}",
        f"chapter_id = {_chapter_toml_string(chapter_id)}",
        f"title = {_chapter_toml_string(title)}",
        f"scope = {_chapter_toml_string(scope)}",
        "revision = 1",
        'knowledge_status = "DRAFT"',
        'last_owner_approval = ""',
        f"dependency_ids = [{dependencies}]",
        "source_refs = [",
    ]
    for reference in source_refs:
        lines.append(
            "  { source_id = "
            f"{_chapter_toml_string(reference.source_id)}, sha256 = "
            f"{_chapter_toml_string(reference.sha256)}, relation = "
            f"{_chapter_toml_string(reference.relation)} }},"
        )
    lines.extend(
        [
            "]",
            "+++",
            "",
            f"# {title}",
            "",
            "## Purpose and boundary",
            "",
            scope,
            "",
            "## Current summary",
            "",
            "UNKNOWN - not yet accepted by the OWNER.",
            "",
            "## Sources",
            "",
            "See the exact source_refs in the frontmatter.",
            "",
            "## Relationships and dependencies",
            "",
            "See dependency_ids in the frontmatter.",
            "",
            "## Effective decisions",
            "",
            "- None recorded.",
            "",
            "## Open questions and assumptions",
            "",
            "- UNKNOWN - still to be analyzed.",
            "",
            "## Active and blocked tasks",
            "",
            "- None.",
            "",
            "## Latest OWNER approval",
            "",
            "None.",
            "",
            "## Freshness",
            "",
            "INCOMPLETE - technically calculated by `workspace catalog rebuild`.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _create_chapter_unlocked(
    project_root: Path,
    chapter_id: str,
    *,
    title: str,
    scope: str = "UNKNOWN - to be determined by OWNER and ARCHITECT.",
    source_ids: Iterable[str] = (),
    dependency_ids: Iterable[str] = (),
    _transaction: Transaction | None = None,
) -> ChapterCreateResult:
    """Create one safe DRAFT chapter without changing index or catalog."""
    root = validate_workspace(project_root)
    normalized_id = _validate_chapter_id(chapter_id)
    normalized_title = _safe_line(title, field="title", maximum=MAX_TITLE_LENGTH)
    normalized_scope = _safe_line(scope, field="scope", maximum=MAX_SCOPE_LENGTH)
    normalized_source_ids = tuple(source_ids)
    normalized_dependencies = tuple(dependency_ids)
    if len(set(normalized_source_ids)) != len(normalized_source_ids):
        raise CatalogError("Dubbele --source opgegeven.", code="chapter_source_duplicate")
    if len(set(normalized_dependencies)) != len(normalized_dependencies):
        raise CatalogError("Dubbele --depends-on opgegeven.", code="chapter_dependency_duplicate")
    sources = _load_sources(root)
    chapters = _load_chapters(root)
    references: list[SourceReference] = []
    superseded = {source.supersedes for source in sources.values() if source.supersedes}
    for source_id in normalized_source_ids:
        if SOURCE_ID_PATTERN.fullmatch(source_id) is None or source_id not in sources:
            raise CatalogError(f"Onbekende bron: {source_id}.", code="chapter_source_unknown")
        source = sources[source_id]
        if source.integrity != "EXACT":
            raise CatalogError(f"Bron is niet exact: {source_id}.", code="chapter_source_not_exact")
        if source_id in superseded:
            raise CatalogError(
                f"Bron is reeds vervangen: {source_id}.",
                code="chapter_source_superseded",
            )
        references.append(SourceReference(source_id, source.sha256, "PRIMARY"))
    dependencies: list[str] = []
    for dependency in normalized_dependencies:
        normalized_dependency = _validate_chapter_id(dependency)
        if normalized_dependency == normalized_id:
            raise CatalogError(
                "Een hoofdstuk mag niet van zichzelf afhangen.",
                code="chapter_dependency_self",
            )
        if normalized_dependency not in chapters:
            raise CatalogError(
                f"Onbekend afhankelijk hoofdstuk: {normalized_dependency}.",
                code="chapter_dependency_unknown",
            )
        dependencies.append(normalized_dependency)
    chapters_root = root / "CHAPTERS"
    final_directory = chapters_root / normalized_id
    if final_directory.exists() or final_directory.is_symlink():
        raise CatalogError(f"Hoofdstuk bestaat al: {normalized_id}.", code="chapter_exists")
    temporary = chapters_root / f".chapter-{uuid4().hex}"
    try:
        temporary.mkdir(exist_ok=False)
        _write_new_file(
            temporary / "CHAPTER.md",
            _chapter_template(
                normalized_id,
                normalized_title,
                normalized_scope,
                sorted(references, key=lambda reference: reference.source_id),
                sorted(dependencies),
            ),
        )
        if _transaction is not None:
            _transaction.track_target(final_directory)
        os.replace(temporary, final_directory)
        if _transaction is not None:
            _transaction.mark_published()
    except CatalogError:
        raise
    except OSError as exc:
        raise CatalogError(
            "Hoofdstuk kon niet atomair worden gemaakt.",
            code="chapter_create_failed",
        ) from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return ChapterCreateResult(
        status="CHAPTER_CREATED",
        chapter_id=normalized_id,
        chapter_path=final_directory / "CHAPTER.md",
    )


def create_chapter(
    project_root: Path,
    chapter_id: str,
    *,
    title: str,
    scope: str = "UNKNOWN - to be determined by OWNER and ARCHITECT.",
    source_ids: Iterable[str] = (),
    dependency_ids: Iterable[str] = (),
) -> ChapterCreateResult:
    root = validate_workspace(project_root)
    expected = state_digest((root / "SOURCES", root / "CHAPTERS"))
    with writer_transaction(
        root,
        "chapter-create",
        expected_digest=expected,
        current_digest=lambda: state_digest((root / "SOURCES", root / "CHAPTERS")),
    ) as transaction:
        return _create_chapter_unlocked(
            root,
            chapter_id,
            title=title,
            scope=scope,
            source_ids=source_ids,
            dependency_ids=dependency_ids,
            _transaction=transaction,
        )


def _rebuild_catalog_unlocked(
    project_root: Path,
    *,
    _transaction: Transaction | None = None,
) -> CatalogResult:
    """Rebuild INDEX.md and catalog.sqlite from official workspace files."""
    generated_at = _utc_now()
    attempt_id = f"CAT-{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
    root: Path | None = None
    source_count = 0
    chapter_count = 0
    counts = {status: 0 for status in FRESHNESS_STATUSES}
    digest: str | None = None
    temporary_database: Path | None = None
    temporary_index: Path | None = None
    try:
        root = validate_workspace(project_root)
        index_path = root / "CHAPTERS" / "INDEX.md"
        catalog_path = root / ".opencntx" / "catalog.sqlite"
        if index_path.is_symlink():
            raise CatalogError(
                "CHAPTERS/INDEX.md mag geen symlink zijn.",
                code="catalog_managed_path_symlink",
            )
        if not _index_is_managed(index_path, catalog_path):
            raise CatalogError(
                "CHAPTERS/INDEX.md bevat handmatige of onbekende inhoud; niets overschreven.",
                code="index_unmanaged",
            )
        sources = _load_sources(root)
        chapters = _load_chapters(root)
        source_count = len(sources)
        chapter_count = len(chapters)
        freshness, issues = _calculate_freshness(sources, chapters)
        for status in freshness.values():
            counts[status] += 1
        model = _state_model(sources, chapters, freshness, issues)
        digest = _state_digest(model)
        opencntx = root / ".opencntx"
        temporary_database = opencntx / f".catalog-{uuid4().hex}.sqlite"
        temporary_index = root / "CHAPTERS" / f".index-{uuid4().hex}.md"
        index_bytes = _render_index(chapters, freshness, digest, generated_at)
        _build_sqlite(
            temporary_database,
            generated_at=generated_at,
            state_digest=digest,
            index_sha256=hashlib.sha256(index_bytes).hexdigest(),
            sources=sources,
            chapters=chapters,
            freshness=freshness,
            issues=issues,
        )
        _write_new_file(
            temporary_index,
            index_bytes,
        )
        if _transaction is not None:
            _transaction.track_target(catalog_path)
            _transaction.track_target(index_path)
        try:
            os.replace(temporary_database, catalog_path)
            temporary_database = None
            if _transaction is not None:
                _transaction.mark_target_published(catalog_path)
            os.replace(temporary_index, index_path)
            temporary_index = None
            if _transaction is not None:
                _transaction.mark_target_published(index_path)
        except OSError as exc:
            raise CatalogError(
                "Catalogusoutputs konden niet volledig worden gepubliceerd.",
                code="catalog_publish_failed",
            ) from exc
        if _transaction is not None:
            _transaction.mark_published()
        receipt_path = _write_catalog_receipt(
            root,
            attempt_id=attempt_id,
            generated_at=generated_at,
            status="CATALOG_REBUILT",
            state_digest=digest,
            source_count=source_count,
            chapter_count=chapter_count,
            freshness_counts=counts,
        )
        if _transaction is not None:
            _transaction.mark_receipted(receipt_path)
        return CatalogResult(
            status="CATALOG_REBUILT",
            state_digest=digest,
            source_count=source_count,
            chapter_count=chapter_count,
            freshness_counts=counts,
            catalog_path=catalog_path,
            index_path=index_path,
            receipt_path=receipt_path,
        )
    except WorkspaceError as exc:
        error = exc if isinstance(exc, CatalogError) else CatalogError(str(exc), code=exc.code)
        if root is not None:
            try:
                _write_catalog_receipt(
                    root,
                    attempt_id=attempt_id,
                    generated_at=generated_at,
                    status="CATALOG_NOT_REBUILT",
                    state_digest=digest,
                    source_count=source_count,
                    chapter_count=chapter_count,
                    freshness_counts=counts,
                    error=error,
                )
            except WorkspaceError:
                pass
        raise error
    finally:
        for temporary in (temporary_database, temporary_index):
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def rebuild_catalog(project_root: Path) -> CatalogResult:
    """Rebuild both catalog outputs under one workspace transaction."""
    root = validate_workspace(project_root)
    inputs = (root / "SOURCES", root / "CHAPTERS")
    try:
        expected = state_digest(inputs)
    except IntegrityError as exc:
        raise CatalogError(
            "Catalogusinput bevat een symlink of ander onveilig pad.",
            code="catalog_managed_path_symlink",
        ) from exc
    if _TEST_BEFORE_CATALOG_LOCK is not None:
        _TEST_BEFORE_CATALOG_LOCK()
    with writer_transaction(
        root,
        "catalog-rebuild",
        expected_digest=expected,
        current_digest=lambda: state_digest(inputs),
    ) as transaction:
        return _rebuild_catalog_unlocked(root, _transaction=transaction)


_TEST_BEFORE_CATALOG_LOCK = None
