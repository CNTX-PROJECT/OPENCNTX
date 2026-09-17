"""Local SQLite FTS5 search with bounded, digest-bound source loading."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing, nullcontext
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .knowledge import (
    ADOPTION_SKIP_DIRECTORIES,
    HEADING,
    TEXT_SUFFIXES,
    TOKEN_PATTERN,
    KnowledgeError,
    _atomic_json,
    _canonical_json,
    _decode_text,
    _digest,
    _query_terms,
    _relative,
    _root,
    _root_id,
    build_index,
)
from .knowledge_io import (
    MAX_SCAN_ENTRIES,
    bounded_read,
    check_delivery,
    publication_lock,
    safe_output,
    safe_path,
)

SEARCH_INDEX_FORMAT = "ocx-search-index-v2"
SEARCH_RESULT_FORMAT = "ocx-search-result-v2"
SEARCH_INDEX_VERSION = 2
SEARCH_INDEX_FILENAME = "search-v2.sqlite"
SEARCH_SKIP_DIRECTORIES = frozenset(ADOPTION_SKIP_DIRECTORIES)
IDENTIFIER_KEYS = frozenset({"code", "id", "key", "name", "slug"})
MAX_JSON_ITEMS = 2_048
MAX_JSON_DEPTH = 20
TOKEN_ESTIMATE_DIVISOR = 4
DEFAULT_SNIPPET_CHARS = 600
SEARCH_COLUMNS = (
    "doc_id",
    "path",
    "title",
    "headings",
    "identifiers",
    "json_paths",
    "json_values",
    "body",
    "digest",
    "bytes",
    "mtime_ns",
    "encoding",
    "parse_status",
    "source_status",
)


@dataclass(frozen=True)
class SearchCandidate:
    """One source path selected by the bounded search scope."""

    path: Path
    relative: str
    bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class SearchDocument:
    """One searchable payload and its source binding."""

    doc_id: str
    path: str
    title: str
    headings: str
    identifiers: str
    json_paths: str
    json_values: str
    body: str
    digest: str
    bytes: int
    mtime_ns: int
    encoding: str
    parse_status: str
    source_status: str


def _positive(value: int, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise KnowledgeError(f"{label} must be between 1 and {maximum}.")
    return value


def _scope(*, max_files: int, max_bytes: int, max_depth: int) -> dict[str, Any]:
    return {
        "suffixes": sorted(TEXT_SUFFIXES),
        "skip_directories": sorted(SEARCH_SKIP_DIRECTORIES),
        "max_files": max_files,
        "max_bytes": max_bytes,
        "max_depth": max_depth,
        "generated_content": "EXCLUDED_BY_DEFAULT",
    }


def _root_binding(root: Path) -> str:
    value = str(root).casefold() if os.name == "nt" else str(root)
    return _digest(value.encode("utf-8"))


def _scope_digest(scope: dict[str, Any]) -> str:
    return _digest(_canonical_json(scope))


def _candidate_paths(
    root: Path, *, max_files: int, max_bytes: int, max_depth: int
) -> list[SearchCandidate]:
    candidates: list[SearchCandidate] = []
    total_bytes = 0
    visited_entries = 0
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        visited_entries += len(directories) + len(names)
        if visited_entries > MAX_SCAN_ENTRIES:
            raise KnowledgeError("Source enumeration exceeds the entry budget.")
        current_path = Path(current)
        directories[:] = sorted(
            name
            for name in directories
            if name not in SEARCH_SKIP_DIRECTORIES and not (current_path / name).is_symlink()
        )
        for name in sorted(names):
            path = current_path / name
            relative = _relative(root, path)
            if path.is_symlink() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if len(PurePosixPath(relative).parts) > max_depth:
                raise KnowledgeError(f"Source depth exceeds max_depth: {relative}")
            try:
                stat = path.stat()
            except OSError as exc:
                raise KnowledgeError(f"Search source cannot be measured: {relative}") from exc
            total_bytes += stat.st_size
            if total_bytes > max_bytes:
                raise KnowledgeError(
                    f"Search scope byte budget exceeded: {total_bytes} > {max_bytes}."
                )
            candidates.append(
                SearchCandidate(
                    path=path,
                    relative=relative,
                    bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                )
            )
            if len(candidates) > max_files:
                raise KnowledgeError(f"Search scope exceeds max_files={max_files}.")
    return candidates


def _strict_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"unsupported JSON constant: {value}")


def _parse_json_value(value: str) -> Any:
    return json.loads(
        value,
        object_pairs_hook=_strict_json_pairs,
        parse_constant=_reject_json_constant,
    )


def _flatten_json(
    value: Any,
    path: str,
    paths: list[str],
    values: list[str],
    identifiers: list[str],
    *,
    depth: int = 0,
) -> bool:
    if depth > MAX_JSON_DEPTH:
        return False
    complete = True
    if isinstance(value, dict):
        for key, item in value.items():
            if len(paths) + len(values) >= MAX_JSON_ITEMS:
                return False
            child = f"{path}.{key}"
            paths.append(child)
            normalized = str(key).casefold()
            if (normalized in IDENTIFIER_KEYS or normalized.endswith("_id")) and isinstance(
                item, (str, int, float, bool)
            ):
                identifiers.append(str(item))
            complete = (
                _flatten_json(item, child, paths, values, identifiers, depth=depth + 1) and complete
            )
        return complete
    if isinstance(value, list):
        complete = len(value) <= 256
        for number, item in enumerate(value[:256]):
            if len(paths) + len(values) >= MAX_JSON_ITEMS:
                return False
            complete = (
                _flatten_json(
                    item, f"{path}[{number}]", paths, values, identifiers, depth=depth + 1
                )
                and complete
            )
        return complete
    if value is not None:
        if len(paths) + len(values) >= MAX_JSON_ITEMS:
            return False
        values.append(str(value))
    return True


def _json_fields(text: str) -> tuple[str, str, str, str]:
    try:
        value = _parse_json_value(text)
        values: list[str] = []
        paths: list[str] = []
        identifiers: list[str] = []
        complete = _flatten_json(value, "$", paths, values, identifiers)
        return (
            "VALID" if complete else "PARTIAL",
            " ".join(paths),
            " ".join(values),
            " ".join(identifiers),
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) >= 2:
            parsed: list[Any] = []
            try:
                parsed = [_parse_json_value(line) for line in lines]
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = []
            if parsed:
                paths = []
                values = []
                identifiers = []
                complete = len(parsed) <= 256
                for number, item in enumerate(parsed[:256]):
                    complete = (
                        _flatten_json(item, f"$[line:{number + 1}]", paths, values, identifiers)
                        and complete
                    )
                return (
                    "JSONL" if complete else "PARTIAL",
                    " ".join(paths),
                    " ".join(values),
                    " ".join(identifiers),
                )
        return "RAW_FALLBACK", "", "", ""


def _markdown_fields(path: str, text: str) -> tuple[str, str, str]:
    headings = [item.strip() for item in HEADING.findall(text)[:40] if item.strip()]
    title = headings[0] if headings else PurePosixPath(path).stem
    identifiers = f"{PurePosixPath(path).stem} {PurePosixPath(path).name}"
    return title, " ".join(headings), identifiers


def _document_from_bytes(root: Path, candidate: SearchCandidate, data: bytes) -> SearchDocument:
    doc_id = "OCX-SEARCH-DOC-" + _digest(f"{_root_id(root)}:{candidate.relative}".encode())[:20]
    try:
        text, encoding = _decode_text(data)
    except UnicodeDecodeError:
        return SearchDocument(
            doc_id,
            candidate.relative,
            PurePosixPath(candidate.relative).stem,
            "",
            PurePosixPath(candidate.relative).stem,
            "",
            "",
            "",
            _digest(data),
            len(data),
            candidate.mtime_ns,
            "unknown",
            "NOT_PARSED",
            "UNSUPPORTED_ENCODING",
        )
    title, headings, identifiers = _markdown_fields(candidate.relative, text)
    parse_status = "NOT_APPLICABLE"
    json_paths = json_values = ""
    if Path(candidate.relative).suffix.lower() == ".json":
        parse_status, json_paths, json_values, json_identifiers = _json_fields(text)
        identifiers = f"{identifiers} {json_identifiers}".strip()
    return SearchDocument(
        doc_id,
        candidate.relative,
        title,
        headings,
        identifiers,
        json_paths,
        json_values,
        text.replace("\x00", " "),
        _digest(data),
        len(data),
        candidate.mtime_ns,
        encoding,
        parse_status,
        "INDEXED",
    )


def _document_from_row(row: tuple[Any, ...]) -> SearchDocument:
    if len(row) != len(SEARCH_COLUMNS):
        raise KnowledgeError("Search document row has an invalid shape.")
    return SearchDocument(
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        str(row[6]),
        str(row[7]),
        str(row[8]),
        int(row[9]),
        int(row[10]),
        str(row[11]),
        str(row[12]),
        str(row[13]),
    )


def _fts5_available() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE ocx_probe USING fts5(body)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


def _database_path(root: Path, index: Path | None) -> Path:
    return safe_output(index or root / ".opencntx" / SEARCH_INDEX_FILENAME)


def _meta_read(connection: sqlite3.Connection) -> dict[str, Any]:
    try:
        rows = connection.execute("SELECT key, value FROM meta").fetchall()
    except sqlite3.Error as exc:
        raise KnowledgeError("Search index metadata cannot be read.") from exc
    result: dict[str, Any] = {}
    try:
        for key, value in rows:
            result[str(key)] = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise KnowledgeError("Search index metadata is invalid.") from exc
    if result.get("format") != SEARCH_INDEX_FORMAT or result.get("format_version") != 2:
        raise KnowledgeError("Unsupported or invalid OCX search index format.")
    if result.get("engine") != "sqlite-fts5-external-content":
        raise KnowledgeError("OCX search index engine is unsupported.")
    required = {
        "root_path_digest",
        "scope",
        "scope_digest",
        "source_tree_digest",
        "index_digest",
        "stats",
    }
    if (
        not required <= set(result)
        or not isinstance(result["scope"], dict)
        or not isinstance(result["stats"], dict)
    ):
        raise KnowledgeError("Search index metadata fields are incomplete.")
    for field in ("root_path_digest", "scope_digest", "source_tree_digest", "index_digest"):
        if (
            not isinstance(result[field], str)
            or re.fullmatch(r"[0-9a-f]{64}", result[field]) is None
        ):
            raise KnowledgeError("Search index metadata digest is invalid.")
    return result


def _previous_documents(path: Path, *, root: Path, scope_digest: str) -> dict[str, SearchDocument]:
    if not path.is_file() or not _fts5_available():
        return {}
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(path)
        meta = _meta_read(connection)
        if (
            meta.get("root_path_digest") != _root_binding(root)
            or meta.get("scope_digest") != scope_digest
            or meta.get("parser_revision") != 2
        ):
            return {}
        rows = connection.execute(
            "SELECT doc_id,path,title,headings,identifiers,json_paths,json_values,body,"
            "digest,bytes,mtime_ns,encoding,parse_status,source_status FROM documents"
        ).fetchall()
        return {str(row[1]): _document_from_row(row) for row in rows}
    except (KnowledgeError, OSError, sqlite3.Error, ValueError, TypeError):
        return {}
    finally:
        if connection is not None:
            connection.close()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA user_version=2")
    connection.executescript(
        """
        CREATE TABLE meta (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
        );
        CREATE TABLE documents (
            doc_id TEXT PRIMARY KEY NOT NULL,
            path TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            headings TEXT NOT NULL,
            identifiers TEXT NOT NULL,
            json_paths TEXT NOT NULL,
            json_values TEXT NOT NULL,
            body TEXT NOT NULL,
            digest TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            encoding TEXT NOT NULL,
            parse_status TEXT NOT NULL,
            source_status TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            path, title, headings, identifiers, json_paths, json_values, body,
            content='documents', content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        );
        """
    )


def _insert_document(connection: sqlite3.Connection, document: SearchDocument) -> None:
    values = tuple(getattr(document, column) for column in SEARCH_COLUMNS)
    connection.execute(
        "INSERT INTO documents "
        "(doc_id,path,title,headings,identifiers,json_paths,json_values,body,digest,bytes,"
        "mtime_ns,encoding,parse_status,source_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        values,
    )
    rowid = connection.execute(
        "SELECT rowid FROM documents WHERE doc_id = ?", (document.doc_id,)
    ).fetchone()
    if rowid is None:
        raise KnowledgeError("Search document row was not created.")
    connection.execute(
        "INSERT INTO documents_fts(rowid,path,title,headings,identifiers,json_paths,json_values,body) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            rowid[0],
            document.path,
            document.title,
            document.headings,
            document.identifiers,
            document.json_paths,
            document.json_values,
            document.body,
        ),
    )


def _write_database(
    destination: Path,
    documents: list[SearchDocument],
    metadata: dict[str, Any],
    *,
    expected_generation: str | None = None,
    _locked: bool = False,
) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise KnowledgeError("Search index destination is not a safe regular file.")
    if destination.parent.is_symlink() or (
        destination.parent.exists() and not destination.parent.is_dir()
    ):
        raise KnowledgeError("Search index store is not a safe product-owned directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".ocx-search-v2-", suffix=".sqlite", dir=destination.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
        connection = sqlite3.connect(temporary)
        try:
            _create_schema(connection)
            for document in documents:
                _insert_document(connection, document)
            for key, value in metadata.items():
                connection.execute(
                    "INSERT INTO meta(key,value) VALUES(?,?)",
                    (
                        key,
                        json.dumps(
                            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                        ),
                    ),
                )
            connection.execute(
                "INSERT INTO documents_fts(documents_fts, rank) VALUES('integrity-check', 1)"
            )
            connection.commit()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise KnowledgeError("Search index integrity check failed.")
        finally:
            connection.close()
        if temporary is None:
            raise KnowledgeError("Search index temporary file was not created.")
        with nullcontext() if _locked else publication_lock(destination):
            if _generation(destination) != expected_generation:
                raise KnowledgeError("A newer index generation was published; retry the build.")
            os.replace(temporary, destination)
            temporary = None
    except (OSError, sqlite3.Error) as exc:
        raise KnowledgeError(
            "Search index publication failed; the previous index was kept."
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _generation(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        with closing(_open_database(path)) as connection:
            return str(_meta_read(connection)["index_digest"])
    except (KnowledgeError, KeyError):
        # An invalid cache is replaceable, but bind replacement to those exact bytes.
        return "INVALID:" + _digest(path.read_bytes())


def _publish_indexes(
    destination: Path,
    documents: list[SearchDocument],
    metadata: dict[str, Any],
    expected_generation: str | None,
    *,
    write_search: bool,
    legacy_output: Path | None,
    legacy: dict[str, Any] | None,
) -> None:
    """Serialize writers and restore the old cache if the second projection fails.

    Each file replacement is atomic. This does not promise cross-file atomicity
    to old v1 readers or recovery from power loss between the two replacements.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with publication_lock(destination):
        if _generation(destination) != expected_generation:
            raise KnowledgeError("A newer index generation was published; retry the build.")
        legacy_bytes = _canonical_json(legacy) if legacy is not None else None
        write_legacy = legacy_output is not None and (
            not legacy_output.is_file() or legacy_output.read_bytes() != legacy_bytes
        )
        if not write_search and not write_legacy:
            return
        backup: Path | None = None
        existed = destination.is_file()
        try:
            if write_search and existed and write_legacy:
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
                    backup = Path(handle.name)
                shutil.copyfile(destination, backup)
            if write_search:
                _write_database(
                    destination,
                    documents,
                    metadata,
                    expected_generation=expected_generation,
                    _locked=True,
                )
            if write_legacy and legacy_output is not None and legacy is not None:
                _atomic_json(legacy_output, legacy)
        except (OSError, KnowledgeError) as exc:
            if backup is not None:
                os.replace(backup, destination)
                backup = None
            elif write_search and not existed:
                destination.unlink(missing_ok=True)
            raise KnowledgeError(
                "Index projection publication failed; previous cache restored."
            ) from exc
        finally:
            if backup is not None:
                backup.unlink(missing_ok=True)


def _source_tree_digest(documents: list[SearchDocument]) -> str:
    sources = [
        {
            "path": document.path,
            "digest": document.digest,
            "bytes": document.bytes,
            "encoding": document.encoding,
            "parse_status": document.parse_status,
            "source_status": document.source_status,
        }
        for document in sorted(documents, key=lambda item: item.path)
    ]
    return _digest(_canonical_json({"sources": sources}))


def _build_metadata(
    root: Path,
    scope: dict[str, Any],
    documents: list[SearchDocument],
    *,
    reused_files: int,
    read_files: int,
    strict: bool,
) -> dict[str, Any]:
    stats = {
        "files": len(documents),
        "bytes": sum(document.bytes for document in documents),
        "indexed_files": sum(document.source_status == "INDEXED" for document in documents),
        "fallback_files": sum(
            document.parse_status in {"RAW_FALLBACK", "PARTIAL"} for document in documents
        ),
        "unsupported_encoding_files": sum(
            document.source_status == "UNSUPPORTED_ENCODING" for document in documents
        ),
        "reused_files": reused_files,
        "read_files": read_files,
    }
    basis: dict[str, Any] = {
        "format": SEARCH_INDEX_FORMAT,
        "format_version": SEARCH_INDEX_VERSION,
        "engine": "sqlite-fts5-external-content",
        "root_id": _root_id(root),
        "parser_revision": 2,
        "root_path_digest": _root_binding(root),
        "scope": scope,
        "scope_digest": _scope_digest(scope),
        "source_tree_digest": _source_tree_digest(documents),
        "fingerprint_mode": "sha256-every-file" if strict else "stat-reuse-sha256-on-change",
        "freshness_policy": "STRICT_DIGEST" if strict else "STAT_MATCH_UNTIL_STRICT_CHECK",
        "complete": True,
        "stats": stats,
    }
    return basis | {"index_digest": _digest(_canonical_json(basis))}


def build_search_index(
    root: Path,
    *,
    index: Path | None = None,
    max_files: int = 10_000,
    max_bytes: int = 25_000_000,
    max_depth: int = 32,
    strict: bool = False,
    legacy_output: Path | None = None,
) -> dict[str, Any]:
    """Build or incrementally refresh the atomic v2 full-text index."""
    max_files = _positive(max_files, "max_files", 1_000_000)
    max_bytes = _positive(max_bytes, "max_bytes", 1_000_000_000)
    max_depth = _positive(max_depth, "max_depth", 256)
    selected_root = _root(root)
    scope = _scope(max_files=max_files, max_bytes=max_bytes, max_depth=max_depth)
    destination = _database_path(selected_root, index)
    store = safe_path(selected_root, ".opencntx", directory=True)
    if store.is_symlink() or (store.exists() and not store.is_dir()):
        raise KnowledgeError("The project metadata store is not a safe product-owned directory.")
    if not _fts5_available():
        fallback: dict[str, Any] = {
            "format": SEARCH_INDEX_FORMAT,
            "format_version": SEARCH_INDEX_VERSION,
            "status": "FALLBACK_METADATA",
            "engine": "metadata-v1",
            "path": str(destination),
            "scope": scope,
        }
        if legacy_output is not None:
            fallback["legacy_index"] = build_index(
                selected_root,
                output=legacy_output,
                max_files=max_files,
                max_bytes=max_bytes,
                max_depth=max_depth,
            )
        return fallback
    expected_generation = _generation(destination)
    candidates = _candidate_paths(
        selected_root,
        max_files=max_files,
        max_bytes=max_bytes,
        max_depth=max_depth,
    )
    previous = _previous_documents(
        destination, root=selected_root, scope_digest=_scope_digest(scope)
    )
    documents: list[SearchDocument] = []
    reused_files = 0
    read_files = 0
    total_bytes = 0
    for candidate in candidates:
        old = previous.get(candidate.relative)
        if (
            not strict
            and old is not None
            and old.bytes == candidate.bytes
            and old.mtime_ns == candidate.mtime_ns
        ):
            document = old
            reused_files += 1
        else:
            try:
                data = bounded_read(selected_root, candidate.relative, max_bytes - total_bytes)
            except OSError as exc:
                raise KnowledgeError(f"Search source cannot be read: {candidate.relative}") from exc
            document = _document_from_bytes(selected_root, candidate, data)
            read_files += 1
        total_bytes += document.bytes
        if total_bytes > max_bytes:
            raise KnowledgeError(f"Search index byte budget exceeded: {total_bytes} > {max_bytes}.")
        documents.append(document)
    metadata = _build_metadata(
        selected_root,
        scope,
        documents,
        reused_files=reused_files,
        read_files=read_files,
        strict=strict,
    )
    unchanged = len(previous) == len(documents) and all(
        previous.get(document.path) == document for document in documents
    )
    write_search = not unchanged or not destination.is_file()
    if unchanged and destination.is_file():
        try:
            with closing(_open_database(destination)) as existing:
                _check_fts_integrity(existing)
                old_metadata = _meta_read(existing)
            metadata["index_digest"] = old_metadata["index_digest"]
        except KnowledgeError as exc:
            if not strict:
                raise KnowledgeError("The cached index is corrupt; rebuild with --strict.") from exc
            write_search = True
    legacy: dict[str, Any] = {}
    if legacy_output is not None:
        legacy["legacy_index"] = build_index(
            selected_root,
            output=legacy_output,
            max_files=max_files,
            max_bytes=max_bytes,
            max_depth=max_depth,
            _snapshot=[(doc.path, doc.digest, doc.bytes, doc.body) for doc in documents],
            _publish=False,
        )
    _publish_indexes(
        destination,
        documents,
        metadata,
        expected_generation,
        write_search=write_search,
        legacy_output=legacy_output,
        legacy=legacy.get("legacy_index"),
    )
    return legacy | {
        "format": SEARCH_INDEX_FORMAT,
        "format_version": SEARCH_INDEX_VERSION,
        "status": "SEARCH_INDEX_BUILT",
        "engine": metadata["engine"],
        "path": str(destination),
        "index_digest": metadata["index_digest"],
        "source_tree_digest": metadata["source_tree_digest"],
        "scope": scope,
        "stats": metadata["stats"],
        "freshness_policy": metadata["freshness_policy"],
    }


def _open_database(path: Path) -> sqlite3.Connection:
    selected = path.expanduser().absolute()
    if path.is_symlink() or not selected.is_file():
        raise KnowledgeError(f"OCX search index is not a regular file: {path}")
    try:
        connection = sqlite3.connect(selected)
        connection.execute("PRAGMA query_only=ON")
        _meta_read(connection)
        return connection
    except (OSError, sqlite3.Error, KnowledgeError) as exc:
        if "connection" in locals():
            connection.close()
        if isinstance(exc, KnowledgeError):
            raise
        raise KnowledgeError(f"OCX search index cannot be opened: {path}") from exc


def _check_fts_integrity(connection: sqlite3.Connection) -> None:
    clone = sqlite3.connect(":memory:")
    try:
        connection.backup(clone)
        clone.execute("INSERT INTO documents_fts(documents_fts, rank) VALUES('integrity-check', 1)")
    except sqlite3.Error as exc:
        raise KnowledgeError("FTS5 content/index integrity check failed.") from exc
    finally:
        clone.close()


def _current_candidates(
    root: Path, metadata: dict[str, Any]
) -> tuple[list[SearchCandidate], str | None]:
    scope = metadata.get("scope")
    if not isinstance(scope, dict):
        return [], "INDEX_SCOPE_INVALID"
    try:
        candidates = _candidate_paths(
            root,
            max_files=int(scope["max_files"]),
            max_bytes=int(scope["max_bytes"]),
            max_depth=int(scope["max_depth"]),
        )
    except (KeyError, TypeError, ValueError, KnowledgeError) as exc:
        return [], str(exc)
    return candidates, None


def search_index_status(
    root: Path,
    *,
    index: Path | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Report scope and source freshness without writing any file."""
    selected_root = _root(root)
    destination = _database_path(selected_root, index)
    base: dict[str, Any] = {
        "format": SEARCH_INDEX_FORMAT,
        "format_version": SEARCH_INDEX_VERSION,
        "path": str(destination),
        "strict": strict,
    }
    if not destination.is_file():
        return base | {"status": "NEEDS_BUILD", "reason": "INDEX_MISSING"}
    connection: sqlite3.Connection | None = None
    try:
        connection = _open_database(destination)
        metadata = _meta_read(connection)
        expected_root_digest = _root_binding(selected_root)
        if metadata.get("root_path_digest") != expected_root_digest:
            return base | {
                "status": "STALE_SCOPE",
                "reason": "INDEX_ROOT_DIFFERS",
                "index_digest": metadata.get("index_digest"),
            }
        if strict:
            _check_fts_integrity(connection)
        candidates, scan_error = _current_candidates(selected_root, metadata)
        if scan_error:
            return base | {
                "status": "STALE_SCOPE",
                "reason": scan_error,
                "index_digest": metadata.get("index_digest"),
            }
        rows = connection.execute(
            "SELECT path,digest,bytes,mtime_ns,source_status FROM documents"
        ).fetchall()
        indexed = {str(row[0]): row for row in rows}
        current = {candidate.relative: candidate for candidate in candidates}
        added = sorted(set(current) - set(indexed))
        removed = sorted(set(indexed) - set(current))
        changed: list[str] = []
        for relative in sorted(set(current) & set(indexed)):
            candidate = current[relative]
            row = indexed[relative]
            if int(row[2]) != candidate.bytes or int(row[3]) != candidate.mtime_ns:
                changed.append(relative)
                continue
            if strict:
                try:
                    data = bounded_read(selected_root, candidate.relative, candidate.bytes)
                except (OSError, KnowledgeError):
                    changed.append(relative)
                    continue
                if _digest(data) != str(row[1]):
                    changed.append(relative)
        fallback = int(metadata.get("stats", {}).get("fallback_files", 0))
        unsupported = int(metadata.get("stats", {}).get("unsupported_encoding_files", 0))
        status = "CURRENT"
        if added or removed or changed:
            status = "STALE"
        elif fallback or unsupported:
            status = "PARTIAL"
        return base | {
            "status": status,
            "index_digest": metadata.get("index_digest"),
            "source_tree_digest": metadata.get("source_tree_digest"),
            "scope_digest": metadata.get("scope_digest"),
            "freshness_policy": metadata.get("freshness_policy"),
            "stats": metadata.get("stats", {}),
            "added": added,
            "removed": removed,
            "changed": changed,
        }
    except (KnowledgeError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        return base | {"status": "INVALID", "reason": str(exc)}
    finally:
        if connection is not None:
            connection.close()


def _fts_query(terms: list[str], *, operator: str) -> str:
    quoted = []
    for term in terms:
        escaped = term.replace('"', '""')
        quoted.append(f'"{escaped}"')
    return f" {operator} ".join(quoted)


def status_page(status: dict[str, Any], *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Negotiate pagination without changing the legacy status envelope."""
    _positive(limit, "limit", 1000)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise KnowledgeError("offset must be a nonnegative integer.")
    changes = [
        {"change": name, "path": path}
        for name in ("added", "removed", "changed")
        for path in status.get(name, [])
    ]
    end = min(offset + limit, len(changes))
    return {
        "format": "ocx-search-status-page-v1",
        "format_version": 1,
        "summary": {
            key: value
            for key, value in status.items()
            if key not in {"added", "removed", "changed"}
        },
        "counts": {name: len(status.get(name, [])) for name in ("added", "removed", "changed")},
        "items": changes[offset:end],
        "offset": offset,
        "limit": limit,
        "total": len(changes),
        "next_offset": end if end < len(changes) else None,
    }


def _matched_rows(
    connection: sqlite3.Connection, terms: list[str], max_rows: int, *, exact_query: str = ""
) -> list[tuple[Any, ...]]:
    exact = connection.execute(
        "SELECT rowid,doc_id,path,title,headings,identifiers,json_paths,json_values,'',"
        "digest,bytes,mtime_ns,encoding,parse_status,source_status FROM documents "
        "WHERE path = ? COLLATE NOCASE OR doc_id = ? COLLATE NOCASE ORDER BY path LIMIT ?",
        (exact_query, exact_query, max_rows),
    ).fetchall()
    for operator in ("AND", "OR"):
        try:
            rows = connection.execute(
                "SELECT d.rowid,d.doc_id,d.path,d.title,d.headings,d.identifiers,d.json_paths,"
                "d.json_values,'',d.digest,d.bytes,d.mtime_ns,d.encoding,d.parse_status,"
                "d.source_status FROM documents_fts "
                "JOIN documents d ON d.rowid = documents_fts.rowid "
                "WHERE documents_fts MATCH ? ORDER BY bm25(documents_fts), d.path LIMIT ?",
                (_fts_query(terms, operator=operator), max_rows),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise KnowledgeError("OCX FTS5 query failed.") from exc
        if rows:
            seen = {row[0] for row in exact}
            return exact + [row for row in rows if row[0] not in seen]
    return exact


def _score_document(
    document: SearchDocument, terms: list[str]
) -> tuple[int, list[str], dict[str, int]]:
    fields = {
        "path": document.path.casefold(),
        "title": document.title.casefold(),
        "heading": document.headings.casefold(),
        "identifier": document.identifiers.casefold(),
        "json_path": document.json_paths.casefold(),
        "json_value": document.json_values.casefold(),
    }
    score = 1
    reasons: set[str] = set()
    components: dict[str, int] = {}
    weights = {
        "path": 100,
        "title": 60,
        "heading": 35,
        "identifier": 45,
        "json_path": 30,
        "json_value": 20,
    }
    for term in terms:
        for field, value in fields.items():
            exact_identifier = field == "identifier" and term in TOKEN_PATTERN.findall(value)
            if term == value or exact_identifier:
                score += weights[field] * 5
                reasons.add(f"exact_{field}")
                components[field] = components.get(field, 0) + weights[field] * 5
            elif term in value:
                score += weights[field]
                reasons.add(f"{field}_term")
                components[field] = components.get(field, 0) + weights[field]
    if document.body and any(term in document.body.casefold() for term in terms):
        score += 10
        reasons.add("body_term")
        components["body"] = 10
    return score, sorted(reasons), components


def _token_estimate(text: str) -> int:
    return max(1, (len(text) + TOKEN_ESTIMATE_DIVISOR - 1) // TOKEN_ESTIMATE_DIVISOR)


def _snippet(text: str, terms: list[str], max_chars: int) -> tuple[str, int, int]:
    lowered = text.casefold()
    positions = [position for term in terms if (position := lowered.find(term)) >= 0]
    folded_position = min(positions) if positions else 0
    position = 0
    folded_offset = 0
    for position, character in enumerate(text):
        if folded_offset >= folded_position:
            break
        folded_offset += len(character.casefold())
    line_start_offset = text.rfind("\n", 0, position) + 1
    heading_offset = line_start_offset
    for match in re.finditer(r"^#{1,6}\s+.+$", text[:line_start_offset], flags=re.MULTILINE):
        heading_offset = match.start()
    start = max(heading_offset, position - max_chars // 3)
    end = min(len(text), start + max_chars)
    while start < end and text[start].isspace():
        start += 1
    excerpt = text[start:end].rstrip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip()
    line_start = text.count("\n", 0, start) + 1
    line_end = text.count("\n", 0, min(len(text), start + len(excerpt))) + 1
    return excerpt, line_start, max(line_start, line_end)


def search_full_text(
    index: Path,
    query: str,
    *,
    root: Path | None = None,
    max_results: int = 20,
    max_bytes: int = 100_000,
    max_tokens: int = 25_000,
    max_snippet_chars: int = DEFAULT_SNIPPET_CHARS,
) -> dict[str, Any]:
    """Search v2 and load only digest-current, budget-fitting source snippets."""
    max_results = _positive(max_results, "max_results", 1_000)
    max_bytes = _positive(max_bytes, "max_bytes", 1_000_000_000)
    max_tokens = _positive(max_tokens, "max_tokens", 10_000_000)
    max_snippet_chars = _positive(max_snippet_chars, "max_snippet_chars", 100_000)
    terms = _query_terms(query)
    connection = _open_database(index)
    try:
        metadata = _meta_read(connection)
        selected_root = _root(root) if root is not None else None
        if selected_root is not None and metadata.get("root_path_digest") != _root_binding(
            selected_root
        ):
            raise KnowledgeError("Search index belongs to a different project root.")
        rows = _matched_rows(connection, terms, max_results * 10, exact_query=query)
        documents: list[SearchDocument] = []
        for row in rows:
            documents.append(_document_from_row(row[1:]))
        scored = [(*_score_document(document, terms), document) for document in documents]
        order = {document.doc_id: number for number, document in enumerate(documents)}
        scored.sort(
            key=lambda item: (
                item[3].path.casefold() != query.casefold(),
                -item[0],
                order[item[3].doc_id],
            )
        )
        selected_root = _root(root) if root is not None else None
        results: list[dict[str, Any]] = []
        loaded_bytes = 0
        referenced_bytes = 0
        skipped_bytes = 0
        used_tokens = 0
        stale_sources: list[str] = []
        for rank, (score, reasons, components, document) in enumerate(
            scored[:max_results], start=1
        ):
            item: dict[str, Any] = {
                "ocx_id": document.doc_id,
                "path": document.path,
                "title": document.title,
                "rank": rank,
                "score": score,
                "score_components": components,
                "reason_codes": reasons,
                "bytes": document.bytes,
                "encoding": document.encoding,
                "parse_status": document.parse_status,
                "state": "referenced",
                "snippet": None,
                "line_start": None,
                "line_end": None,
                "token_estimate": 0,
            }
            if selected_root is None:
                referenced_bytes += document.bytes
                results.append(item)
                continue
            if loaded_bytes + document.bytes > max_bytes or used_tokens >= max_tokens:
                if results:
                    referenced_bytes += document.bytes
                    item["state"] = "referenced"
                else:
                    skipped_bytes += document.bytes
                    item["state"] = "skipped"
                results.append(item)
                continue
            remaining_tokens = max_tokens - used_tokens
            snippet_chars = min(
                max_snippet_chars, max(1, remaining_tokens * TOKEN_ESTIMATE_DIVISOR)
            )
            try:
                data = bounded_read(selected_root, document.path, max_bytes - loaded_bytes)
                text, encoding = _decode_text(data)
            except (OSError, UnicodeDecodeError, KnowledgeError):
                item["state"] = "stale_source"
                stale_sources.append(document.path)
                results.append(item)
                continue
            loaded_bytes += len(data)
            if _digest(data) != document.digest:
                item["state"] = "stale_source"
                stale_sources.append(document.path)
                results.append(item)
                continue
            check_delivery(document.path, text, document.digest)
            excerpt, line_start, line_end = _snippet(text, terms, snippet_chars)
            token_estimate = _token_estimate(excerpt)
            if token_estimate > remaining_tokens:
                excerpt = excerpt[: max(1, remaining_tokens * TOKEN_ESTIMATE_DIVISOR)].rstrip()
                token_estimate = _token_estimate(excerpt)
            if token_estimate > remaining_tokens:
                referenced_bytes += len(data)
                item["state"] = "referenced"
                results.append(item)
                continue
            used_tokens += token_estimate
            item.update(
                {
                    "state": "loaded",
                    "snippet": excerpt,
                    "line_start": line_start,
                    "line_end": line_end,
                    "token_estimate": token_estimate,
                    "encoding": encoding,
                }
            )
            results.append(item)
        basis = {
            "format": SEARCH_RESULT_FORMAT,
            "format_version": 2,
            "engine": "sqlite-fts5",
            "index_digest": metadata["index_digest"],
            "query": query,
            "query_terms": terms,
            "budgets": {
                "max_results": max_results,
                "max_bytes": max_bytes,
                "max_tokens": max_tokens,
                "max_snippet_chars": max_snippet_chars,
            },
            "results": results,
            "loaded_bytes": loaded_bytes,
            "referenced_bytes": referenced_bytes,
            "skipped_bytes": skipped_bytes,
            "estimated_tokens": used_tokens,
            "status": "STALE" if stale_sources else "CURRENT_UNVERIFIED_SOURCE",
            "stale_sources": stale_sources,
            "token_estimate_method": "ceil(characters / 4)",
        }
        return _bounded_result(basis, max_tokens)
    finally:
        connection.close()


def _bounded_result(basis: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    """Bound the complete existing JSON envelope using its declared estimator."""
    while True:
        result = basis | {"result_digest": _digest(_canonical_json(basis))}
        serialized = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        check_delivery("search-result.json", serialized, result["result_digest"])
        if _token_estimate(serialized) <= max_tokens:
            return result
        if not basis["results"]:
            raise KnowledgeError("Output envelope exceeds max_tokens; increase the budget.")
        removed = basis["results"].pop()
        basis["skipped_bytes"] += removed["bytes"]
        basis["estimated_tokens"] -= removed["token_estimate"]
        basis["status"] = "PARTIAL"


def search_delivery(
    index: Path,
    query: str,
    *,
    root: Path,
    max_results: int = 20,
    max_bytes: int = 100_000,
    max_tokens: int = 25_000,
    max_output_bytes: int = 100_000,
    max_snippet_chars: int = DEFAULT_SNIPPET_CHARS,
) -> dict[str, Any]:
    """Opt-in delivery report with source coverage, complete-output bounds and explicit units."""
    _positive(max_output_bytes, "max_output_bytes", 10_000_000)
    result = search_full_text(
        index,
        query,
        root=root,
        max_results=max_results,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        max_snippet_chars=max_snippet_chars,
    )
    coverage = search_index_status(root, index=index, strict=False)
    with closing(_open_database(index)) as connection:
        _check_fts_integrity(connection)
    inspected = {key: coverage.get(key) for key in ("status", "added", "removed", "changed")}
    inspected["method"] = "STAT_SCAN_WITH_FTS_INTEGRITY"
    inspected["source_digest_recheck"] = "SELECTED_DELIVERED_SOURCES_ONLY"
    basis = {
        "format": "ocx-search-delivery-v1",
        "format_version": 1,
        "query": query,
        "index_digest": result["index_digest"],
        "coverage": inspected,
        "items": result["results"],
        "source_bytes_read": result["loaded_bytes"],
        "source_budget_bytes": max_bytes,
        "output_budget_bytes": max_output_bytes,
        "output_budget_estimated_tokens": max_tokens,
        "token_method": "ceil(serialized_characters / 4); not a provider tokenizer",
        "complete": (
            result["status"] != "PARTIAL"
            and coverage.get("status") == "CURRENT"
            and all(item["state"] == "loaded" for item in result["results"])
        ),
        "completeness_scope": "RETURNED_ITEMS_ONLY; query and candidate limits still apply",
        "omitted_results": 0,
        "absence_proven": False,
    }
    while True:
        value = basis | {"report_digest": _digest(_canonical_json(basis))}
        serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        check_delivery("search-delivery.json", serialized, value["report_digest"])
        if (
            len(serialized.encode("utf-8")) <= max_output_bytes
            and _token_estimate(serialized) <= max_tokens
        ):
            return value
        if not basis["items"]:
            raise KnowledgeError("Delivery report envelope exceeds the output budget.")
        basis["items"].pop()
        basis["omitted_results"] += 1
        basis["complete"] = False
