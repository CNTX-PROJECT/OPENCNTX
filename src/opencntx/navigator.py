"""Deterministic task-bound navigation into a normal OPENCNTX package."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from .catalog import (
    CATALOG_FORMAT,
    CATALOG_FORMAT_VERSION,
    CatalogIssue,
    ChapterEntry,
    SourceEntry,
    _calculate_freshness,
    _load_chapters,
    _load_sources,
    _state_digest,
    _state_model,
)
from .control import (
    CONTROL_SNAPSHOT_PATH,
    ControlState,
    inspect_control,
    refresh_control_snapshot,
)
from .core import (
    DEFAULT_EXCLUDE_PATTERNS,
    ContextConfig,
    OpenCntxError,
    Selection,
    Source,
    _atomic_package_write,
    _manifest,
    read_sources,
    render_context,
    verify_package,
)
from .integrity import Transaction, state_digest, writer_transaction
from .primitives import (
    sha256_bytes as _digest_bytes,
)
from .primitives import (
    timestamp_microseconds as _timestamp,
)
from .primitives import (
    utc_now as _utc_now,
)
from .workflow import (
    TASK_ID_PATTERN,
    TaskChain,
    _assert_no_symlink,
    _ensure_managed_view,
    _load_chain,
    _verify_inputs,
)
from .workspace import SHA256_PATTERN, WorkspaceError, validate_workspace

NAVIGATION_FORMAT = "opencntx-navigation"
NAVIGATION_FORMAT_VERSION = 1
NAVIGATION_RECEIPT_FORMAT = "opencntx-navigation-receipt"
NAVIGATION_RECEIPT_VERSION = 1

HOT_PATHS = (
    "CONTROL/OWNER.md",
    "CONTROL/ROADMAP.md",
    "CONTROL/CURRENT.md",
)
CATALOG_TABLE_COLUMNS = {
    "catalog_meta": ("key", "value"),
    "sources": (
        "source_id",
        "record_path",
        "original_path",
        "bytes",
        "sha256",
        "privacy",
        "captured_at",
        "supersedes",
        "integrity",
    ),
    "chapters": (
        "chapter_id",
        "title",
        "scope",
        "relative_path",
        "revision",
        "knowledge_status",
        "last_owner_approval",
        "chapter_digest",
        "freshness",
        "open_decisions",
    ),
    "chapter_sources": ("chapter_id", "source_id", "pinned_sha256", "relation"),
    "chapter_dependencies": ("chapter_id", "depends_on"),
    "catalog_issues": ("issue_number", "code", "object_id", "message"),
}
CATALOG_SELECT_QUERIES = {
    "catalog_meta": 'SELECT "key", "value" FROM "catalog_meta"',
    "sources": (
        'SELECT "source_id", "record_path", "original_path", "bytes", "sha256", '
        '"privacy", "captured_at", "supersedes", "integrity" FROM "sources"'
    ),
    "chapters": (
        'SELECT "chapter_id", "title", "scope", "relative_path", "revision", '
        '"knowledge_status", "last_owner_approval", "chapter_digest", "freshness", '
        '"open_decisions" FROM "chapters"'
    ),
    "chapter_sources": (
        'SELECT "chapter_id", "source_id", "pinned_sha256", "relation" FROM "chapter_sources"'
    ),
    "chapter_dependencies": ('SELECT "chapter_id", "depends_on" FROM "chapter_dependencies"'),
    "catalog_issues": (
        'SELECT "issue_number", "code", "object_id", "message" FROM "catalog_issues"'
    ),
}
CURRENT_TASK_PATTERN = re.compile(
    r"^- (?:Active task|Actieve taak): (TASK-\d{8}-\d{4}) "
    r"(?:revision|revisie) ([1-9]\d*)$",
    re.MULTILINE,
)


class NavigatorError(WorkspaceError):
    """A short fail-closed workspace context error."""


@dataclass(frozen=True)
class RouteFile:
    layer: str
    path: str


@dataclass(frozen=True)
class NavigationRoute:
    root: Path
    chain: TaskChain
    goal: str
    approval_digest: str
    execution_digest: str
    catalog_digest: str
    control: ControlState
    sources: dict[str, SourceEntry]
    chapters: dict[str, ChapterEntry]
    freshness: dict[str, str]
    selected_chapter_ids: tuple[str, ...]
    selected_source_ids: tuple[str, ...]
    files: tuple[RouteFile, ...]

    @property
    def fingerprint(self) -> tuple[object, ...]:
        return (
            self.chain.task_id,
            self.chain.revision,
            self.chain.events[-1].record_digest,
            self.chain.proposal_digest,
            self.approval_digest,
            self.execution_digest,
            self.catalog_digest,
            self.control.fingerprint,
            self.selected_chapter_ids,
            self.selected_source_ids,
            tuple((item.layer, item.path) for item in self.files),
        )


@dataclass(frozen=True)
class ContextBuildResult:
    status: str
    task_id: str
    revision: int
    proposal_digest: str
    package_path: Path
    context_digest: str
    manifest_digest: str
    file_count: int
    total_bytes: int
    receipt_path: Path


@dataclass(frozen=True)
class ContextVerifyReport:
    ok: bool
    task_id: str
    errors: tuple[str, ...]


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _validate_task_id(value: object) -> str:
    if not isinstance(value, str) or TASK_ID_PATTERN.fullmatch(value) is None:
        raise NavigatorError(
            "Taak-ID moet TASK-YYYYMMDD-NNNN gebruiken.", code="context_task_id_invalid"
        )
    return value


def _validate_digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise NavigatorError(f"{label} is geen geldige SHA-256.", code="context_digest_invalid")
    return value


def _positive_budget(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise NavigatorError(
            f"{label} moet een positief geheel getal zijn.",
            code="context_budget_invalid",
        )
    return value


def _path_parts(relative_text: str) -> tuple[str, ...]:
    pure = PurePosixPath(relative_text)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts or "\\" in relative_text:
        raise NavigatorError(
            "Contextpad moet draagbaar binnen de werkruimte blijven.",
            code="context_path_invalid",
        )
    return pure.parts


def _safe_file(root: Path, relative_text: str) -> Path:
    relative = Path(*_path_parts(relative_text))
    path = _assert_no_symlink(root, relative, code="context_path_unsafe")
    if not path.is_file():
        raise NavigatorError(
            f"Contextbestand ontbreekt of is geen regulier bestand: {relative_text}.",
            code="context_path_invalid",
        )
    return path


def _proposal_inputs(chain: TaskChain) -> tuple[str, ...]:
    payload = chain.events[0].payload
    values = payload.get("inputs")
    if not isinstance(values, list):
        raise NavigatorError("Taakvoorstel mist geldige inputs.", code="context_task_invalid")
    paths: list[str] = []
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise NavigatorError(
                "Taakvoorstel bevat een ongeldig inputrecord.",
                code="context_task_invalid",
            )
        paths.append(item["path"])
    return tuple(paths)


def _current_task(root: Path) -> tuple[str, int]:
    path = _safe_file(root, "CONTROL/CURRENT.md")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise NavigatorError(
            "CONTROL/CURRENT.md is niet als UTF-8 leesbaar.",
            code="context_current_invalid",
        ) from exc
    matches = CURRENT_TASK_PATTERN.findall(text)
    if len(matches) != 1:
        raise NavigatorError(
            "CONTROL/CURRENT.md moet exact één actieve taak en revisie noemen.",
            code="context_current_invalid",
        )
    return matches[0][0], int(matches[0][1])


def _catalog_rows(
    sources: dict[str, SourceEntry],
    chapters: dict[str, ChapterEntry],
    freshness: dict[str, str],
    issues: Sequence[CatalogIssue],
) -> dict[str, list[tuple[object, ...]]]:
    source_rows: list[tuple[object, ...]] = [
        (
            item.source_id,
            item.record_path,
            item.original_path,
            item.byte_count,
            item.sha256,
            item.privacy,
            item.captured_at,
            item.supersedes,
            item.integrity,
        )
        for item in (sources[source_id] for source_id in sorted(sources))
    ]
    chapter_rows: list[tuple[object, ...]] = [
        (
            item.chapter_id,
            item.title,
            item.scope,
            item.relative_path,
            item.revision,
            item.knowledge_status,
            item.last_owner_approval,
            item.digest,
            freshness[item.chapter_id],
            item.open_decisions,
        )
        for item in (chapters[chapter_id] for chapter_id in sorted(chapters))
    ]
    chapter_source_rows: list[tuple[object, ...]] = []
    dependency_rows: list[tuple[object, ...]] = []
    for chapter_id in sorted(chapters):
        chapter = chapters[chapter_id]
        chapter_source_rows.extend(
            (chapter_id, item.source_id, item.sha256, item.relation)
            for item in chapter.source_refs
            if item.source_id in sources
        )
        dependency_rows.extend(
            (chapter_id, dependency)
            for dependency in chapter.dependency_ids
            if dependency in chapters
        )
    issue_rows: list[tuple[object, ...]] = [
        (number, item.code, item.object_id, item.message)
        for number, item in enumerate(issues, start=1)
    ]
    return {
        "sources": source_rows,
        "chapters": chapter_rows,
        "chapter_sources": chapter_source_rows,
        "chapter_dependencies": dependency_rows,
        "catalog_issues": issue_rows,
    }


def _read_catalog(
    root: Path,
) -> tuple[
    str,
    dict[str, SourceEntry],
    dict[str, ChapterEntry],
    dict[str, str],
]:
    try:
        catalog_path = _safe_file(root, ".opencntx/catalog.sqlite")
        index_path = _safe_file(root, "CHAPTERS/INDEX.md")
    except WorkspaceError as exc:
        raise NavigatorError(
            "Catalogus of hoofdstukindex ontbreekt of is onveilig; rebuild vereist.",
            code="catalog_rebuild_required",
        ) from exc
    try:
        index_bytes = index_path.read_bytes()
    except OSError as exc:
        raise NavigatorError(
            "CHAPTERS/INDEX.md kan niet worden gecontroleerd.",
            code="catalog_rebuild_required",
        ) from exc

    sources = _load_sources(root)
    chapters = _load_chapters(root)
    freshness, issues = _calculate_freshness(sources, chapters)
    state_digest = _state_digest(_state_model(sources, chapters, freshness, issues))
    expected_rows = _catalog_rows(sources, chapters, freshness, issues)

    connection: sqlite3.Connection | None = None
    try:
        uri = f"{catalog_path.resolve(strict=True).as_uri()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise NavigatorError(
                "SQLite-catalogus faalt de integriteitscontrole.",
                code="catalog_rebuild_required",
            )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        }
        if tables != set(CATALOG_TABLE_COLUMNS):
            raise NavigatorError(
                "SQLite-catalogus gebruikt een onbekend schema.",
                code="catalog_rebuild_required",
            )
        forbidden_objects = connection.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE type IN ('view', 'trigger') ORDER BY type, name"
        ).fetchall()
        if forbidden_objects:
            raise NavigatorError(
                "SQLite-catalogus bevat onbekende views of triggers.",
                code="catalog_rebuild_required",
            )
        for table, expected_columns in CATALOG_TABLE_COLUMNS.items():
            column_names = tuple(
                row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
            )
            if column_names != expected_columns:
                raise NavigatorError(
                    "SQLite-catalogus gebruikt een onbekend schema.",
                    code="catalog_rebuild_required",
                )
        metadata = dict(connection.execute("SELECT key, value FROM catalog_meta"))
        expected_meta_keys = {
            "format",
            "format_version",
            "generated_at",
            "workspace_state_digest",
            "index_sha256",
            "source_count",
            "chapter_count",
        }
        if set(metadata) != expected_meta_keys:
            raise NavigatorError(
                "SQLite-catalogus mist bekende metadata.",
                code="catalog_rebuild_required",
            )
        if (
            metadata["format"] != CATALOG_FORMAT
            or metadata["format_version"] != str(CATALOG_FORMAT_VERSION)
            or metadata["workspace_state_digest"] != state_digest
            or metadata["index_sha256"] != _digest_bytes(index_bytes)
            or metadata["source_count"] != str(len(sources))
            or metadata["chapter_count"] != str(len(chapters))
            or not metadata["generated_at"]
        ):
            raise NavigatorError(
                "Catalogus en officiële werkruimtebytes verschillen; rebuild vereist.",
                code="catalog_rebuild_required",
            )
        for table, expected in expected_rows.items():
            actual = list(connection.execute(CATALOG_SELECT_QUERIES[table]))
            if sorted(actual, key=repr) != sorted(expected, key=repr):
                raise NavigatorError(
                    "Catalogusrijen verschillen van de officiële werkruimtebytes.",
                    code="catalog_rebuild_required",
                )
    except NavigatorError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise NavigatorError(
            "Catalogus is ontbrekend, onleesbaar of verouderd; rebuild vereist.",
            code="catalog_rebuild_required",
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    return state_digest, sources, chapters, freshness


def _chapter_id_from_path(path: str) -> str | None:
    parts = _path_parts(path)
    if len(parts) == 3 and parts[0] == "CHAPTERS" and parts[2] == "CHAPTER.md":
        return parts[1]
    return None


def _dependency_closure(
    root_ids: Sequence[str], chapters: dict[str, ChapterEntry]
) -> tuple[str, ...]:
    selected: set[str] = set()

    def visit(chapter_id: str) -> None:
        if chapter_id in selected:
            return
        chapter = chapters.get(chapter_id)
        if chapter is None:
            raise NavigatorError(
                f"Taak verwijst naar onbekend hoofdstuk: {chapter_id}.",
                code="context_chapter_invalid",
            )
        selected.add(chapter_id)
        for dependency in sorted(chapter.dependency_ids):
            visit(dependency)

    for chapter_id in sorted(set(root_ids)):
        visit(chapter_id)
    return tuple(sorted(selected))


def _prepare_route(
    root_path: Path,
    task_id: str,
    proposal_digest: str,
    *,
    refresh_snapshot: bool = False,
) -> NavigationRoute:
    root = validate_workspace(root_path)
    task_id = _validate_task_id(task_id)
    proposal_digest = _validate_digest(proposal_digest, label="Voorsteldigest")
    chain = _load_chain(root, task_id)
    _ensure_managed_view(chain)
    _verify_inputs(root, chain)
    if chain.proposal_digest != proposal_digest:
        raise NavigatorError(
            "Voorsteldigest komt niet overeen met de actieve taak.",
            code="context_proposal_mismatch",
        )
    if chain.status != "IN_EXECUTION":
        raise NavigatorError(
            "Contextbouw vereist een exact goedgekeurde taak in IN_EXECUTION.",
            code="context_task_not_executing",
        )
    approval = next((event for event in chain.events if event.event_type == "owner-approval"), None)
    execution = next(
        (event for event in chain.events if event.event_type == "execution-begun"), None
    )
    if approval is None or execution is None:
        raise NavigatorError(
            "Taak mist geldige approval- of executionrecords.",
            code="context_task_invalid",
        )

    input_paths = _proposal_inputs(chain)
    control_inputs = {path for path in input_paths if path.startswith("CONTROL/")}
    if control_inputs != set(HOT_PATHS):
        raise NavigatorError(
            "Taakinputs moeten exact OWNER.md, ROADMAP.md en CURRENT.md als CONTROL-inputs pinnen.",
            code="context_control_inputs_invalid",
        )
    content_inputs = tuple(path for path in input_paths if not path.startswith("CONTROL/"))
    if not content_inputs:
        raise NavigatorError(
            "Taak vereist minimaal één inhoudelijke input buiten CONTROL.",
            code="context_content_input_missing",
        )
    current_task_id, current_revision = _current_task(root)
    if current_task_id != chain.task_id or current_revision != chain.revision:
        raise NavigatorError(
            "CONTROL/CURRENT.md noemt niet exact dezelfde taak en revisie.",
            code="context_current_mismatch",
        )

    catalog_digest, sources, chapters, freshness = _read_catalog(root)
    root_chapters: list[str] = []
    direct_source_ids: set[str] = set()
    source_by_path: dict[str, str] = {}
    for source in sources.values():
        source_by_path[source.record_path] = source.source_id
        source_by_path[source.original_path] = source.source_id

    warm_inputs: set[str] = set()
    for path in content_inputs:
        parts = _path_parts(path)
        if parts[0] == "CHAPTERS":
            chapter_id = _chapter_id_from_path(path)
            if path != "CHAPTERS/INDEX.md" and chapter_id is None:
                raise NavigatorError(
                    f"Onbekende hoofdstukinput: {path}.",
                    code="context_input_invalid",
                )
            warm_inputs.add(path)
            if chapter_id is not None:
                root_chapters.append(chapter_id)
        elif parts[0] in {"PLAYBOOKS", "ROLES"}:
            warm_inputs.add(path)
        elif parts[0] == "SOURCES":
            source_id = source_by_path.get(path)
            if source_id is None:
                raise NavigatorError(
                    f"Taakinput is geen bekend bronrecord of origineel: {path}.",
                    code="context_input_invalid",
                )
            direct_source_ids.add(source_id)
        else:
            raise NavigatorError(
                f"Inhoudelijke taakinput heeft geen ondersteunde route: {path}.",
                code="context_input_invalid",
            )

    selected_chapters = _dependency_closure(root_chapters, chapters)
    selected_source_ids = set(direct_source_ids)
    for chapter_id in selected_chapters:
        chapter = chapters[chapter_id]
        if chapter.knowledge_status != "OWNER_ACCEPTED" or freshness[chapter_id] != "CURRENT":
            raise NavigatorError(
                f"Hoofdstuk {chapter_id} is niet OWNER_ACCEPTED en CURRENT.",
                code="context_chapter_not_current",
            )
        warm_inputs.add(chapter.relative_path)
        selected_source_ids.update(item.source_id for item in chapter.source_refs)

    explicit_inputs = set(input_paths)
    for source_id in sorted(selected_source_ids):
        selected_source = sources.get(source_id)
        if selected_source is None or selected_source.integrity != "EXACT":
            raise NavigatorError(
                f"Bron {source_id} is ontbrekend of niet exact.",
                code="context_source_stale",
            )
        if selected_source.privacy == "QUARANTINED":
            raise NavigatorError(
                f"Bron {source_id} is QUARANTINED en wordt niet geladen.",
                code="context_source_quarantined",
            )
        if selected_source.privacy == "RESTRICTED" and not (
            selected_source.record_path in explicit_inputs
            or selected_source.original_path in explicit_inputs
        ):
            raise NavigatorError(
                f"RESTRICTED bron {source_id} vereist een expliciete taakinput.",
                code="context_source_restricted",
            )

    control = inspect_control(root)
    if control.mode == "COMPACT_MARKED":
        if refresh_snapshot:
            refresh_control_snapshot(root, write_receipt=False)
        control = inspect_control(root, require_snapshot=True)
    hot_paths = (
        ("CONTROL/OWNER.md", CONTROL_SNAPSHOT_PATH, "CONTROL/CURRENT.md")
        if control.mode == "COMPACT_MARKED"
        else HOT_PATHS
    )
    route_files: list[RouteFile] = [RouteFile("HOT", path) for path in hot_paths]
    route_files.append(RouteFile("HOT", f"TASKS/{chain.task_id}/TASK.md"))
    route_files.extend(RouteFile("WARM", path) for path in sorted(warm_inputs))
    for source_id in sorted(selected_source_ids):
        source = sources[source_id]
        route_files.append(RouteFile("COLD", source.record_path))
        route_files.append(RouteFile("COLD", source.original_path))

    unique: list[RouteFile] = []
    seen: set[str] = set()
    for item in route_files:
        if item.path not in seen:
            _safe_file(root, item.path)
            unique.append(item)
            seen.add(item.path)

    goal = chain.events[0].payload.get("goal")
    if not isinstance(goal, str) or not goal:
        raise NavigatorError("Taakdoel is ongeldig.", code="context_task_invalid")
    return NavigationRoute(
        root=root,
        chain=chain,
        goal=goal,
        approval_digest=approval.record_digest,
        execution_digest=execution.record_digest,
        catalog_digest=catalog_digest,
        control=control,
        sources=sources,
        chapters=chapters,
        freshness=freshness,
        selected_chapter_ids=selected_chapters,
        selected_source_ids=tuple(sorted(selected_source_ids)),
        files=tuple(unique),
    )


def _read_route(
    route: NavigationRoute, max_files: int, max_bytes: int
) -> tuple[tuple[Source, ...], ContextConfig, Selection]:
    max_files = _positive_budget(max_files, label="max-files")
    max_bytes = _positive_budget(max_bytes, label="max-bytes")
    required_count = len(route.files)
    sizes: list[tuple[str, int]] = []
    for item in route.files:
        path = _safe_file(route.root, item.path)
        try:
            sizes.append((item.path, path.stat().st_size))
        except OSError as exc:
            raise NavigatorError(
                f"Contextbestand kan niet worden gemeten: {item.path}.",
                code="context_source_unavailable",
            ) from exc
    required_bytes = sum(size for _, size in sizes)
    if required_count > max_files or required_bytes > max_bytes:
        largest = ", ".join(
            path for path, _ in sorted(sizes, key=lambda item: (-item[1], item[0]))[:5]
        )
        raise NavigatorError(
            "Contextbudget onvoldoende: "
            f"vereist {required_count} bestanden en {required_bytes} bytes; "
            f"grootste kandidaten: {largest}.",
            code="context_budget_exceeded",
        )
    paths = tuple(item.path for item in route.files)
    exclude_patterns = (
        tuple(pattern for pattern in DEFAULT_EXCLUDE_PATTERNS if pattern != ".opencntx/**")
        if route.control.mode == "COMPACT_MARKED"
        else DEFAULT_EXCLUDE_PATTERNS
    )
    config = ContextConfig(
        goal=route.goal,
        include=paths,
        required=paths,
        exclude=exclude_patterns,
        max_files=max_files,
        max_bytes=max_bytes,
    )
    selection = Selection(
        files=tuple((item.path, _safe_file(route.root, item.path)) for item in route.files),
        excluded=(),
        ignored=(),
    )
    try:
        context_sources = read_sources(route.root, selection, config)
    except OpenCntxError as exc:
        raise NavigatorError(
            f"Contextbron kan niet veilig worden geladen: {exc}",
            code="context_source_invalid",
        ) from exc
    return context_sources, config, selection


def _navigation(
    route: NavigationRoute,
    context_sources: tuple[Source, ...],
    max_files: int,
    max_bytes: int,
    *,
    include_control_metadata: bool = True,
    legacy: bool = False,
) -> dict[str, Any]:
    layers = {item.path: item.layer for item in route.files}
    selected_chapters = [
        {
            "chapter_id": chapter_id,
            "digest": route.chapters[chapter_id].digest,
            "freshness": route.freshness[chapter_id],
            "revision": route.chapters[chapter_id].revision,
        }
        for chapter_id in route.selected_chapter_ids
    ]
    selected_sources = []
    for source_id in route.selected_source_ids:
        item = route.sources[source_id]
        record_bytes = _safe_file(route.root, item.record_path).read_bytes()
        selected_sources.append(
            {
                "original_sha256": item.sha256,
                "privacy": item.privacy,
                "record_sha256": _digest_bytes(record_bytes),
                "source_id": source_id,
            }
        )
    navigation: dict[str, Any] = {
        "format": NAVIGATION_FORMAT,
        "format_version": NAVIGATION_FORMAT_VERSION,
        "task": {
            "task_id": route.chain.task_id,
            "revision": route.chain.revision,
            "proposal_digest": route.chain.proposal_digest,
            "approval_record_digest": route.approval_digest,
            "execution_record_digest": route.execution_digest,
            "latest_task_record_digest": route.chain.events[-1].record_digest,
        },
        "catalog_state_digest": route.catalog_digest,
        "budget": {"max_files": max_files, "max_bytes": max_bytes},
        "read": [
            {
                "layer": layers[source.path],
                "path": source.path,
                "bytes": source.byte_count,
                "sha256": source.sha256,
            }
            for source in context_sources
        ],
        "chapters": selected_chapters,
        "sources": selected_sources,
        "not_read": {
            "chapters": [
                {
                    "chapter_id": chapter_id,
                    "reason": "OUTSIDE_APPROVED_TASK_SCOPE",
                }
                for chapter_id in sorted(set(route.chapters) - set(route.selected_chapter_ids))
            ],
            "sources": [
                {"source_id": source_id, "reason": "OUTSIDE_APPROVED_TASK_SCOPE"}
                for source_id in sorted(set(route.sources) - set(route.selected_source_ids))
            ],
        },
        "warnings": [],
        "scope_statement": (
            (
                "Alleen de genoemde goedgekeurde taakscope is onderzocht; "
                "dit is geen claim over het volledige project."
            )
            if legacy
            else (
                "Only the stated approved task scope was examined; "
                "this is not a claim about the complete project."
            )
        ),
    }
    if include_control_metadata:
        navigation["control"] = {
            "block_bytes": route.control.block_bytes,
            "block_sha256": route.control.block_sha256,
            "current_sha256": route.control.current_sha256,
            "mode": route.control.mode,
            "owner_sha256": route.control.owner_sha256,
            "roadmap_body_loaded": route.control.mode == "LEGACY_FULL_ROADMAP",
            "roadmap_sha256": route.control.roadmap_sha256,
            "snapshot_path": (
                CONTROL_SNAPSHOT_PATH if route.control.mode == "COMPACT_MARKED" else None
            ),
            "snapshot_sha256": route.control.snapshot_sha256,
        }
        if route.control.mode == "COMPACT_MARKED":
            navigation["not_read"]["control"] = [
                {
                    "path": "CONTROL/ROADMAP.md",
                    "reason": "FULL_DIGEST_PINNED_COMPACT_BLOCK_LOADED",
                }
            ]
    return navigation


def _package_bytes(
    route: NavigationRoute,
    max_files: int,
    max_bytes: int,
    *,
    include_control_metadata: bool = True,
    legacy: bool = False,
) -> tuple[bytes, bytes, dict[str, Any]]:
    context_sources, config, selection = _read_route(route, max_files, max_bytes)
    context_bytes = render_context(route.goal, context_sources, legacy=legacy).encode("utf-8")
    manifest = _manifest(config, selection, context_sources, context_bytes)
    manifest["navigation"] = _navigation(
        route,
        context_sources,
        max_files=max_files,
        max_bytes=max_bytes,
        include_control_metadata=include_control_metadata,
        legacy=legacy,
    )
    return context_bytes, _json_bytes(manifest), manifest


def _receipt_path(root: Path, attempt_id: str) -> Path:
    return root / ".opencntx" / "receipts" / f"{attempt_id}.json"


def _write_receipt(root: Path, value: dict[str, Any]) -> Path:
    receipt_path = _receipt_path(root, str(value["attempt_id"]))
    content = _json_bytes(value)
    try:
        with receipt_path.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise NavigatorError(
            "Contextreceipt kon niet worden geschreven.",
            code="context_receipt_write_failed",
        ) from exc
    return receipt_path


def _try_failure_receipt(
    project_root: Path, task_id: object, operation: str, error: NavigatorError
) -> None:
    try:
        root = validate_workspace(project_root)
        now = _utc_now()
        attempt_id = f"CTX-{now.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
        message = f"Context operation failed: {error.code}."
        if error.code == "catalog_rebuild_required":
            next_action = "Run workspace catalog rebuild and check again."
        elif error.code == "context_budget_exceeded":
            next_action = (
                "Ask the OWNER to reduce the task scope or deliberately choose larger "
                "context budgets."
            )
        elif error.code in {
            "context_source_invalid",
            "context_source_quarantined",
            "context_source_restricted",
            "context_source_stale",
        }:
            next_action = "Check the named source and request a new OWNER decision if needed."
        else:
            next_action = "Fix the named gate or present the block to the OWNER."
        _write_receipt(
            root,
            {
                "attempt_id": attempt_id,
                "created_at": _timestamp(now),
                "error": message,
                "error_code": error.code,
                "format": NAVIGATION_RECEIPT_FORMAT,
                "format_version": NAVIGATION_RECEIPT_VERSION,
                "operation": operation,
                "next_action": next_action,
                "package_path": None,
                "status": "CONTEXT_NOT_BUILT",
                "task_id": task_id if isinstance(task_id, str) else None,
            },
        )
    except (NavigatorError, WorkspaceError, OSError):
        pass


def _build_context_package_unlocked(
    project_root: Path,
    task_id: str,
    *,
    proposal_digest: str,
    max_files: int,
    max_bytes: int,
    _transaction: Transaction | None = None,
) -> ContextBuildResult:
    """Build one deterministic package for an approved task in execution."""
    root = project_root
    try:
        max_files = _positive_budget(max_files, label="max-files")
        max_bytes = _positive_budget(max_bytes, label="max-bytes")
        route = _prepare_route(root, task_id, proposal_digest, refresh_snapshot=True)
        context_bytes, manifest_bytes, manifest = _package_bytes(route, max_files, max_bytes)
        confirmed = _prepare_route(root, task_id, proposal_digest)
        if confirmed.fingerprint != route.fingerprint:
            raise NavigatorError(
                "Taak- of catalogusstaat veranderde tijdens contextbouw.",
                code="context_state_changed",
            )
        package_path = _atomic_package_write(
            route.root,
            context_bytes,
            manifest_bytes,
            _transaction=_transaction,
        )
        now = _utc_now()
        attempt_id = f"CTX-{now.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
        receipt_path = _write_receipt(
            route.root,
            {
                "attempt_id": attempt_id,
                "created_at": _timestamp(now),
                "context_sha256": _digest_bytes(context_bytes),
                "file_count": manifest["package"]["file_count"],
                "format": NAVIGATION_RECEIPT_FORMAT,
                "format_version": NAVIGATION_RECEIPT_VERSION,
                "manifest_sha256": _digest_bytes(manifest_bytes),
                "operation": "build",
                "package_path": ".opencntx/latest",
                "proposal_digest": route.chain.proposal_digest,
                "status": "CONTEXT_BUILT",
                "task_id": route.chain.task_id,
                "total_bytes": manifest["package"]["total_bytes"],
            },
        )
        if _transaction is not None:
            _transaction.mark_receipted(receipt_path)
        return ContextBuildResult(
            status="CONTEXT_BUILT",
            task_id=route.chain.task_id,
            revision=route.chain.revision,
            proposal_digest=route.chain.proposal_digest,
            package_path=package_path,
            context_digest=_digest_bytes(context_bytes),
            manifest_digest=_digest_bytes(manifest_bytes),
            file_count=manifest["package"]["file_count"],
            total_bytes=manifest["package"]["total_bytes"],
            receipt_path=receipt_path,
        )
    except NavigatorError as exc:
        _try_failure_receipt(root, task_id, "build", exc)
        raise
    except (OpenCntxError, WorkspaceError) as exc:
        wrapped = NavigatorError(str(exc), code=getattr(exc, "code", "context_build_failed"))
        _try_failure_receipt(root, task_id, "build", wrapped)
        raise wrapped from exc


def build_context_package(
    project_root: Path,
    task_id: str,
    *,
    proposal_digest: str,
    max_files: int,
    max_bytes: int,
) -> ContextBuildResult:
    """Build one task-bound package under workspace and task writer locks."""
    root = validate_workspace(project_root)
    normalized_task_id = _validate_task_id(task_id)
    chain = _load_chain(root, normalized_task_id)
    state_paths = (chain.directory / "events", root / ".opencntx" / "latest")
    expected_state = state_digest(state_paths)
    if _TEST_BEFORE_CONTEXT_LOCK is not None:
        _TEST_BEFORE_CONTEXT_LOCK()
    with writer_transaction(
        root,
        "context-build",
        task_id=normalized_task_id,
        expected_digest=expected_state,
        current_digest=lambda: state_digest(state_paths),
    ) as transaction:
        return _build_context_package_unlocked(
            root,
            normalized_task_id,
            proposal_digest=proposal_digest,
            max_files=max_files,
            max_bytes=max_bytes,
            _transaction=transaction,
        )


_TEST_BEFORE_CONTEXT_LOCK = None


def _load_package_manifest(root: Path) -> tuple[Path, dict[str, Any], bytes, bytes]:
    package_path = root / ".opencntx" / "latest"
    if package_path.is_symlink() or not package_path.is_dir():
        raise NavigatorError(
            "Contextpakket .opencntx/latest ontbreekt of is onveilig.",
            code="context_package_invalid",
        )
    manifest_path = _safe_file(root, ".opencntx/latest/manifest.json")
    context_path = _safe_file(root, ".opencntx/latest/CONTEXT.md")
    try:
        manifest_bytes = manifest_path.read_bytes()
        context_bytes = context_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NavigatorError(
            "Contextpakket bevat een ongeldig manifest.",
            code="context_package_invalid",
        ) from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "format",
        "format_version",
        "task",
        "selection",
        "package",
        "sources",
        "excluded",
        "ignored",
        "navigation",
    }:
        raise NavigatorError(
            "Contextmanifest heeft onbekende of ontbrekende velden.",
            code="context_package_invalid",
        )
    return package_path, manifest, context_bytes, manifest_bytes


def verify_context_package(
    project_root: Path, task_id: str, *, proposal_digest: str
) -> ContextVerifyReport:
    """Read-only verification of package bytes and the live task route."""
    root = validate_workspace(project_root)
    task_id = _validate_task_id(task_id)
    proposal_digest = _validate_digest(proposal_digest, label="Voorsteldigest")
    package_path, manifest, actual_context, actual_manifest = _load_package_manifest(root)
    navigation = manifest.get("navigation")
    selection = manifest.get("selection")
    if not isinstance(navigation, dict) or not isinstance(selection, dict):
        raise NavigatorError(
            "Contextmanifest mist geldige navigatie of selectie.",
            code="context_package_invalid",
        )
    task_value = navigation.get("task")
    if (
        navigation.get("format") != NAVIGATION_FORMAT
        or navigation.get("format_version") != NAVIGATION_FORMAT_VERSION
        or not isinstance(task_value, dict)
        or task_value.get("task_id") != task_id
        or task_value.get("proposal_digest") != proposal_digest
    ):
        raise NavigatorError(
            "Contextmanifest hoort niet bij de opgegeven taak en voorstel-digest.",
            code="context_package_mismatch",
        )
    max_files = _positive_budget(selection.get("max_files"), label="manifest max-files")
    max_bytes = _positive_budget(selection.get("max_bytes"), label="manifest max-bytes")
    errors: list[str] = []
    try:
        ordinary = verify_package(package_path)
        errors.extend(f"changed: {path}" for path in ordinary.changed)
        errors.extend(f"missing: {path}" for path in ordinary.missing)
        errors.extend(f"unexpected: {path}" for path in ordinary.unexpected)
        errors.extend(ordinary.errors)
    except OpenCntxError as exc:
        errors.append(str(exc))
    try:
        route = _prepare_route(root, task_id, proposal_digest)
        include_control_metadata = (
            isinstance(navigation.get("control"), dict) or route.control.mode == "COMPACT_MARKED"
        )
        expected_context, expected_manifest, _ = _package_bytes(
            route,
            max_files,
            max_bytes,
            include_control_metadata=include_control_metadata,
        )
        legacy_context, legacy_manifest, _ = _package_bytes(
            route,
            max_files,
            max_bytes,
            include_control_metadata=include_control_metadata,
            legacy=True,
        )
        current_matches = (
            actual_context == expected_context and actual_manifest == expected_manifest
        )
        legacy_matches = actual_context == legacy_context and actual_manifest == legacy_manifest
        if not current_matches and not legacy_matches:
            if actual_context not in {expected_context, legacy_context}:
                errors.append("CONTEXT.md differs from the current task route")
            if actual_manifest not in {expected_manifest, legacy_manifest}:
                errors.append("manifest.json differs from the current task route")
    except OpenCntxError as exc:
        errors.append(str(exc))
    except WorkspaceError as exc:
        errors.append(f"{exc.code}: context verification failed")
    unique = tuple(sorted(set(errors)))
    return ContextVerifyReport(ok=not unique, task_id=task_id, errors=unique)


def format_context_verify_report(report: ContextVerifyReport) -> str:
    """Render the complete task-bound context verification result."""
    lines = [f"task: {report.task_id}", f"errors ({len(report.errors)}):"]
    lines.extend(f"  {error}" for error in report.errors)
    lines.append("result: OK" if report.ok else "result: DRIFT OR INCOMPLETE")
    return "\n".join(lines)
