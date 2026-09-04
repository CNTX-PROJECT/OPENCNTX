"""Adaptive local-first storage, bounded search, retention, and team CAS contracts."""

from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any, Protocol

from .continuity import (
    _digest,
    _fail,
    _identifier,
    _one_line,
    _value_digest,
    _write_atomic,
    _writer_lock,
)

PROFILES = ("TINY_LOCAL", "LOCAL_INDEXED", "LARGE_LOCAL", "TEAM_SHARED")
DATA_CLASSES = (
    "STRUCTURED_FACT",
    "SEARCHABLE_TEXT",
    "LARGE_IMMUTABLE_BLOB",
    "HUMAN_NOTE",
    "SECRET",
    "SCRATCH",
)
LOCAL_PROFILES = frozenset(PROFILES[:3])
STATE_FORMAT = "opencntx-adaptive-storage-state"
PLAN_FORMAT = "opencntx-storage-profile-plan"
QUERY_FORMAT = "opencntx-storage-query"
RESULT_FORMAT = "opencntx-storage-query-result"


class TeamStorageAdapter(Protocol):
    """Minimal backend-neutral contract required from an optional team adapter."""

    def capabilities(self) -> Mapping[str, object]: ...

    def read_state(self, project_id: str) -> Mapping[str, object] | None: ...

    def compare_and_swap(
        self, project_id: str, expected_revision: int, state: Mapping[str, object]
    ) -> bool: ...


def _pretty(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _storage_root(project_root: Path) -> Path:
    root = project_root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise _fail("continuity_root_invalid", "Storage project root is not a real directory.")
    return root / ".opencntx" / "adaptive-storage"


def _state_path(project_root: Path) -> Path:
    return _storage_root(project_root) / "state.json"


def _blob_path(storage_root: Path, digest: str) -> Path:
    return storage_root / "objects" / digest[:2] / f"{digest}.gz"


def _state_digest(value: Mapping[str, object]) -> str:
    return _value_digest({key: item for key, item in value.items() if key != "state_digest"})


def _int_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail("continuity_store_invalid", f"{label} is not an integer.")
    return value


def _validate_state(value: Mapping[str, object], project_id: str) -> dict[str, Any]:
    required = {
        "format",
        "format_version",
        "project_id",
        "profile",
        "revision",
        "soft_limit_bytes",
        "hard_limit_bytes",
        "rollback_reserve_bytes",
        "objects",
        "records",
        "generations",
        "audit",
        "state_digest",
    }
    if (
        set(value) != required
        or value.get("format") != STATE_FORMAT
        or value.get("format_version") != 1
        or value.get("project_id") != project_id
        or value.get("profile") not in LOCAL_PROFILES
        or isinstance(value.get("revision"), bool)
        or not isinstance(value.get("revision"), int)
        or _int_value(value["revision"], "revision") < 0
        or not isinstance(value.get("objects"), dict)
        or not isinstance(value.get("records"), dict)
        or not isinstance(value.get("generations"), list)
        or not isinstance(value.get("audit"), list)
        or value.get("state_digest") != _state_digest(value)
    ):
        raise _fail("continuity_store_invalid", "Adaptive storage state is invalid.")
    for name in ("soft_limit_bytes", "hard_limit_bytes", "rollback_reserve_bytes"):
        item = value.get(name)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise _fail("continuity_store_invalid", "Adaptive storage budget is invalid.")
    if _int_value(value["soft_limit_bytes"], "soft limit") > _int_value(
        value["hard_limit_bytes"], "hard limit"
    ):
        raise _fail("continuity_store_invalid", "Adaptive storage budget order is invalid.")
    return dict(value)


def recommend_storage_profile(measurements: Mapping[str, object]) -> str:
    """Recommend a profile from measured facts without changing storage."""
    required = {
        "object_count",
        "total_bytes",
        "monthly_change_bytes",
        "queries_per_day",
        "concurrent_writers",
    }
    if set(measurements) != required:
        raise _fail("continuity_store_invalid", "Storage measurements differ from the contract.")
    values: dict[str, int] = {}
    for name in required:
        item = measurements[name]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise _fail("continuity_store_invalid", "Storage measurements are invalid.")
        values[name] = item
    if values["concurrent_writers"] > 1:
        return "TEAM_SHARED"
    if (
        values["object_count"] >= 250_000
        or values["total_bytes"] >= 5 * 1024**3
        or values["monthly_change_bytes"] >= 1024**3
    ):
        return "LARGE_LOCAL"
    if values["object_count"] >= 2_000 or values["queries_per_day"] >= 100:
        return "LOCAL_INDEXED"
    return "TINY_LOCAL"


def build_storage_profile_plan(
    project_root: Path,
    *,
    project_id: str,
    current_profile: str,
    measurements: Mapping[str, object],
    soft_limit_bytes: int,
    hard_limit_bytes: int,
    rollback_reserve_bytes: int,
    requested_profile: str | None = None,
    migration_approved: bool = False,
) -> dict[str, Any]:
    """Build a read-only recommendation and explicit profile-change gate."""
    root = project_root.resolve(strict=True)
    selected_project = _identifier(project_id, "project_id")
    if current_profile not in PROFILES or (
        requested_profile is not None and requested_profile not in PROFILES
    ):
        raise _fail("continuity_store_invalid", "Storage profile is unknown.")
    for value in (soft_limit_bytes, hard_limit_bytes, rollback_reserve_bytes):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise _fail("continuity_store_invalid", "Storage budget is invalid.")
    if soft_limit_bytes > hard_limit_bytes or rollback_reserve_bytes >= hard_limit_bytes:
        raise _fail("continuity_store_invalid", "Storage budget cannot preserve rollback space.")
    measured = dict(measurements)
    recommendation = recommend_storage_profile(measured)
    requested = requested_profile or current_profile
    changing = requested != current_profile
    migration_status = (
        "NOT_REQUESTED"
        if not changing
        else "APPROVED"
        if migration_approved
        else "OWNER_APPROVAL_REQUIRED"
    )
    target = requested if migration_status == "APPROVED" else current_profile
    basis = {
        "format": PLAN_FORMAT,
        "format_version": 1,
        "project_id": selected_project,
        "project_root": str(root),
        "current_profile": current_profile,
        "recommended_profile": recommendation,
        "requested_profile": requested,
        "target_profile": target,
        "migration_status": migration_status,
        "measurements": measured,
        "soft_limit_bytes": soft_limit_bytes,
        "hard_limit_bytes": hard_limit_bytes,
        "rollback_reserve_bytes": rollback_reserve_bytes,
        "writes_performed": False,
    }
    return basis | {"plan_digest": _value_digest(basis)}


def _validate_plan(plan: Mapping[str, object]) -> dict[str, Any]:
    basis = {key: item for key, item in plan.items() if key != "plan_digest"}
    if (
        plan.get("format") != PLAN_FORMAT
        or plan.get("format_version") != 1
        or plan.get("writes_performed") is not False
        or plan.get("target_profile") not in PROFILES
        or plan.get("migration_status") not in {"NOT_REQUESTED", "APPROVED", "OWNER_APPROVAL_REQUIRED"}
        or plan.get("plan_digest") != _value_digest(basis)
    ):
        raise _fail("continuity_store_invalid", "Storage plan is invalid or drifted.")
    return dict(plan)


def initialize_adaptive_storage(project_root: Path, plan: Mapping[str, object]) -> dict[str, Any]:
    """Initialize one local profile; team profiles must use an external adapter."""
    value = _validate_plan(plan)
    if value["migration_status"] == "OWNER_APPROVAL_REQUIRED":
        raise _fail("continuity_authority_missing", "Storage profile migration needs OWNER approval.")
    profile = str(value["target_profile"])
    if profile == "TEAM_SHARED":
        raise _fail("continuity_adapter_unavailable", "TEAM_SHARED requires an explicit adapter.")
    root = project_root.resolve(strict=True)
    if str(root) != value["project_root"]:
        raise _fail("continuity_root_invalid", "Storage plan belongs to another project root.")
    selected_project = str(value["project_id"])
    path = _state_path(root)
    lock = path.parent / ".writer.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _writer_lock(lock):
        if path.exists():
            current = _validate_state(json.loads(path.read_text(encoding="utf-8")), selected_project)
            if current["profile"] != profile:
                raise _fail("continuity_store_invalid", "Existing storage uses another profile.")
            return current
        state: dict[str, Any] = {
            "format": STATE_FORMAT,
            "format_version": 1,
            "project_id": selected_project,
            "profile": profile,
            "revision": 0,
            "soft_limit_bytes": int(value["soft_limit_bytes"]),
            "hard_limit_bytes": int(value["hard_limit_bytes"]),
            "rollback_reserve_bytes": int(value["rollback_reserve_bytes"]),
            "objects": {},
            "records": {},
            "generations": [],
            "audit": [],
        }
        state["state_digest"] = _state_digest(state)
        _write_atomic(path, _pretty(state))
        return _validate_state(state, selected_project)


def adaptive_storage_state(project_root: Path, *, project_id: str) -> dict[str, Any]:
    path = _state_path(project_root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail("continuity_store_missing", "Adaptive storage state is unavailable.") from exc
    if not isinstance(value, dict):
        raise _fail("continuity_store_invalid", "Adaptive storage state is invalid.")
    return _validate_state(value, _identifier(project_id, "project_id"))


def _managed_bytes(storage_root: Path) -> int:
    total = 0
    for base in (storage_root / "objects", storage_root / "indexes"):
        if base.exists():
            total += sum(path.stat().st_size for path in base.rglob("*") if path.is_file())
    state = storage_root / "state.json"
    return total + (state.stat().st_size if state.is_file() else 0)


def _verify_blob(path: Path, expected_digest: str) -> bytes:
    try:
        raw = gzip.decompress(path.read_bytes())
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        raise _fail("continuity_store_invalid", "Managed content object is unreadable.") from exc
    if _digest(raw) != expected_digest:
        raise _fail("continuity_store_invalid", "Managed content object digest differs.")
    return raw


def _index_paths(storage_root: Path, profile: str, digest: str | None = None) -> list[Path]:
    if profile == "LOCAL_INDEXED":
        return [storage_root / "indexes" / "catalog.sqlite"]
    if profile == "LARGE_LOCAL":
        if digest is not None:
            return [storage_root / "indexes" / "shards" / f"{digest[:2]}.sqlite"]
        directory = storage_root / "indexes" / "shards"
        return sorted(directory.glob("*.sqlite")) if directory.is_dir() else []
    return []


def _prepare_index(connection: sqlite3.Connection) -> str:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS records ("
        "record_id TEXT PRIMARY KEY, digest TEXT NOT NULL, data_class TEXT NOT NULL, "
        "source TEXT NOT NULL, freshness TEXT NOT NULL, text_content TEXT NOT NULL)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS records_digest ON records(digest)")
    connection.execute("CREATE INDEX IF NOT EXISTS records_class ON records(data_class)")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS relations ("
        "record_id TEXT NOT NULL, target TEXT NOT NULL, PRIMARY KEY(record_id, target))"
    )
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(record_id UNINDEXED, text_content)"
        )
    except sqlite3.Error:
        return "BOUNDED_LIKE"
    return "FTS5"


def _upsert_index(
    storage_root: Path, state: Mapping[str, Any], record: Mapping[str, Any], text: str
) -> None:
    profile = str(state["profile"])
    target_paths = _index_paths(storage_root, profile, str(record["object_digest"]))
    if profile == "LARGE_LOCAL":
        for existing_path in _index_paths(storage_root, profile):
            if existing_path in target_paths:
                continue
            with closing(sqlite3.connect(existing_path)) as connection:
                _prepare_index(connection)
                connection.execute(
                    "DELETE FROM records WHERE record_id = ?", (record["record_id"],)
                )
                connection.execute(
                    "DELETE FROM relations WHERE record_id = ?", (record["record_id"],)
                )
                try:
                    connection.execute(
                        "DELETE FROM records_fts WHERE record_id = ?", (record["record_id"],)
                    )
                except sqlite3.Error:
                    pass
                connection.commit()
    for path in target_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection:
            strategy = _prepare_index(connection)
            connection.execute(
                "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record["record_id"],
                    record["object_digest"],
                    record["data_class"],
                    record["source"],
                    record["freshness"],
                    text,
                ),
            )
            connection.execute("DELETE FROM relations WHERE record_id = ?", (record["record_id"],))
            connection.executemany(
                "INSERT INTO relations(record_id, target) VALUES (?, ?)",
                [(record["record_id"], target) for target in record["relations"]],
            )
            if strategy == "FTS5":
                connection.execute("DELETE FROM records_fts WHERE record_id = ?", (record["record_id"],))
                connection.execute(
                    "INSERT INTO records_fts(record_id, text_content) VALUES (?, ?)",
                    (record["record_id"], text),
                )
            connection.execute("PRAGMA optimize")
            connection.commit()


def put_storage_record(
    project_root: Path,
    *,
    project_id: str,
    expected_revision: int,
    record_id: str,
    content: bytes,
    data_class: str,
    source: str,
    relations: Sequence[str] = (),
    freshness: str = "CURRENT",
) -> dict[str, Any]:
    """Add one record with pre-write budget enforcement and physical deduplication."""
    if data_class not in DATA_CLASSES or data_class == "SECRET":
        raise _fail("continuity_store_invalid", "This data class cannot enter project storage.")
    selected_record = _identifier(record_id, "record_id")
    selected_project = _identifier(project_id, "project_id")
    selected_source = _one_line(source, "source", 500)
    relation_values = sorted({_identifier(item, "relation") for item in relations})
    if len(content) > 1024**3:
        raise _fail("continuity_store_invalid", "One storage object exceeds the bounded input limit.")
    digest = _digest(content)
    compressed = gzip.compress(content, compresslevel=9, mtime=0)
    searchable = (
        content.decode("utf-8", errors="replace")
        if data_class in {"SEARCHABLE_TEXT", "HUMAN_NOTE", "STRUCTURED_FACT"}
        else ""
    )
    storage_root = _storage_root(project_root)
    state_path = storage_root / "state.json"
    with _writer_lock(storage_root / ".writer.lock"):
        state = adaptive_storage_state(project_root, project_id=selected_project)
        records: dict[str, Any] = dict(state["records"])
        existing = records.get(selected_record)
        proposed_record = {
            "record_id": selected_record,
            "object_digest": digest,
            "data_class": data_class,
            "source": selected_source,
            "relations": relation_values,
            "freshness": _one_line(freshness, "freshness", 80),
        }
        if existing == proposed_record:
            return {
                "format": "opencntx-storage-write-receipt",
                "format_version": 1,
                "status": "UNCHANGED",
                "record_id": selected_record,
                "object_digest": digest,
                "revision": state["revision"],
                "physical_object_written": False,
                "deduplicated": True,
                "state_digest": state["state_digest"],
            }
        if expected_revision != state["revision"]:
            raise _fail("continuity_write_conflict", "Storage revision changed before write.")
        blob = _blob_path(storage_root, digest)
        physical_new = not blob.exists()
        if not physical_new:
            _verify_blob(blob, digest)
        objects: dict[str, Any] = dict(state["objects"])
        if digest not in objects:
            objects[digest] = {
                "raw_bytes": len(content),
                "compressed_bytes": len(compressed),
                "verified": True,
            }
        records[selected_record] = proposed_record
        next_state = dict(state)
        next_state["records"] = records
        next_state["objects"] = objects
        next_state["revision"] = int(state["revision"]) + 1
        next_state["audit"] = list(state["audit"]) + [
            {
                "revision": next_state["revision"],
                "action": "PUT_RECORD",
                "record_id": selected_record,
                "object_digest": digest,
            }
        ]
        next_state.pop("state_digest", None)
        next_state["state_digest"] = _state_digest(next_state)
        current_bytes = _managed_bytes(storage_root)
        metadata_growth = max(0, len(_pretty(next_state)) - state_path.stat().st_size)
        physical_growth = len(compressed) if physical_new else 0
        predicted_peak = (
            current_bytes + metadata_growth + physical_growth + int(state["rollback_reserve_bytes"])
        )
        if predicted_peak > int(state["hard_limit_bytes"]):
            raise _fail("continuity_store_invalid", "Storage hard limit would be exceeded before write.")
        if physical_new:
            _write_atomic(blob, compressed)
        _write_atomic(state_path, _pretty(next_state))
        _upsert_index(storage_root, next_state, proposed_record, searchable)
        receipt = {
            "format": "opencntx-storage-write-receipt",
            "format_version": 1,
            "status": "STORED",
            "record_id": selected_record,
            "object_digest": digest,
            "revision": next_state["revision"],
            "physical_object_written": physical_new,
            "deduplicated": not physical_new,
            "soft_limit_warning": predicted_peak > int(state["soft_limit_bytes"]),
            "predicted_peak_bytes": predicted_peak,
            "state_digest": next_state["state_digest"],
        }
        return receipt | {"receipt_digest": _value_digest(receipt)}


def _retained_generations(values: Sequence[Mapping[str, object]]) -> list[dict[str, Any]]:
    """Keep recent, daily, and monthly points while always preserving the newest two."""
    if len(values) <= 4:
        return [dict(item) for item in values]
    selected: set[int] = set(range(max(0, len(values) - 4), len(values)))
    days: set[str] = set()
    months: set[str] = set()
    for index in range(len(values) - 5, -1, -1):
        created = str(values[index]["created_at"])
        day = created[:10]
        month = created[:7]
        if len(days) < 7 and day not in days:
            days.add(day)
            selected.add(index)
        elif len(months) < 12 and month not in months:
            months.add(month)
            selected.add(index)
    return [dict(values[index]) for index in sorted(selected)]


def create_storage_generation(
    project_root: Path,
    *,
    project_id: str,
    expected_revision: int,
    created_at: str,
) -> dict[str, Any]:
    storage_root = _storage_root(project_root)
    with _writer_lock(storage_root / ".writer.lock"):
        state = adaptive_storage_state(project_root, project_id=project_id)
        records: Mapping[str, Mapping[str, object]] = state["records"]
        objects = {record_id: str(record["object_digest"]) for record_id, record in sorted(records.items())}
        generation_basis = {"created_at": _one_line(created_at, "created_at", 80), "objects": objects}
        generation = generation_basis | {
            "generation_id": f"GEN-{_value_digest(generation_basis)[:24].upper()}"
        }
        existing = next(
            (item for item in reversed(state["generations"]) if item["objects"] == objects), None
        )
        if existing is not None:
            return dict(existing) | {"status": "UNCHANGED", "revision": state["revision"]}
        if expected_revision != state["revision"]:
            raise _fail("continuity_write_conflict", "Storage revision changed before generation.")
        next_state = dict(state)
        next_state["generations"] = _retained_generations(list(state["generations"]) + [generation])
        next_state["revision"] = int(state["revision"]) + 1
        next_state["audit"] = list(state["audit"]) + [
            {
                "revision": next_state["revision"],
                "action": "CREATE_GENERATION",
                "generation_id": generation["generation_id"],
            }
        ]
        next_state.pop("state_digest", None)
        next_state["state_digest"] = _state_digest(next_state)
        _write_atomic(storage_root / "state.json", _pretty(next_state))
        return generation | {"status": "CREATED", "revision": next_state["revision"]}


def release_storage_record(
    project_root: Path, *, project_id: str, expected_revision: int, record_id: str
) -> dict[str, Any]:
    storage_root = _storage_root(project_root)
    selected = _identifier(record_id, "record_id")
    with _writer_lock(storage_root / ".writer.lock"):
        state = adaptive_storage_state(project_root, project_id=project_id)
        if selected not in state["records"]:
            return {"status": "UNCHANGED", "record_id": selected, "revision": state["revision"]}
        if expected_revision != state["revision"]:
            raise _fail("continuity_write_conflict", "Storage revision changed before release.")
        records = dict(state["records"])
        removed = records.pop(selected)
        next_state = dict(state)
        next_state["records"] = records
        next_state["revision"] = int(state["revision"]) + 1
        next_state["audit"] = list(state["audit"]) + [
            {"revision": next_state["revision"], "action": "RELEASE_RECORD", "record_id": selected}
        ]
        next_state.pop("state_digest", None)
        next_state["state_digest"] = _state_digest(next_state)
        _write_atomic(storage_root / "state.json", _pretty(next_state))
        for path in _index_paths(storage_root, str(state["profile"]), str(removed["object_digest"])):
            if path.is_file():
                with closing(sqlite3.connect(path)) as connection:
                    _prepare_index(connection)
                    connection.execute("DELETE FROM records WHERE record_id = ?", (selected,))
                    connection.execute("DELETE FROM relations WHERE record_id = ?", (selected,))
                    try:
                        connection.execute("DELETE FROM records_fts WHERE record_id = ?", (selected,))
                    except sqlite3.Error:
                        pass
                    connection.commit()
        return {"status": "RELEASED", "record_id": selected, "revision": next_state["revision"]}


def build_storage_cleanup_plan(project_root: Path, *, project_id: str) -> dict[str, Any]:
    storage_root = _storage_root(project_root)
    state = adaptive_storage_state(project_root, project_id=project_id)
    referenced = {str(item["object_digest"]) for item in state["records"].values()}
    for generation in state["generations"]:
        referenced.update(str(item) for item in generation["objects"].values())
    candidates: list[dict[str, Any]] = []
    objects_root = storage_root / "objects"
    if objects_root.is_dir():
        for path in sorted(objects_root.glob("[0-9a-f][0-9a-f]/*.gz")):
            digest = path.stem
            if len(digest) != 64 or digest in referenced:
                continue
            _verify_blob(path, digest)
            candidates.append(
                {
                    "digest": digest,
                    "relative_path": path.relative_to(storage_root).as_posix(),
                    "bytes": path.stat().st_size,
                }
            )
    basis = {
        "format": "opencntx-storage-cleanup-plan",
        "format_version": 1,
        "project_id": state["project_id"],
        "state_digest": state["state_digest"],
        "revision": state["revision"],
        "candidates": candidates,
        "reclaimable_bytes": sum(item["bytes"] for item in candidates),
        "writes_performed": False,
    }
    return basis | {"plan_digest": _value_digest(basis)}


def apply_storage_cleanup(
    project_root: Path,
    *,
    project_id: str,
    plan: Mapping[str, object],
    fault_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    basis = {key: item for key, item in plan.items() if key != "plan_digest"}
    if plan.get("plan_digest") != _value_digest(basis) or plan.get("writes_performed") is not False:
        raise _fail("continuity_store_invalid", "Storage cleanup plan is invalid.")
    storage_root = _storage_root(project_root)
    receipt_path = storage_root / "cleanup" / f"{plan['plan_digest']}.json"
    if receipt_path.is_file():
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value
    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
        raise _fail("continuity_store_invalid", "Storage cleanup candidates are invalid.")
    staging_root = storage_root / "cleanup" / "staging" / str(plan["plan_digest"])
    with _writer_lock(storage_root / ".writer.lock"):
        state = adaptive_storage_state(project_root, project_id=project_id)
        committed = next(
            (
                item
                for item in reversed(state["audit"])
                if item.get("action") == "CLEANUP"
                and item.get("plan_digest") == plan["plan_digest"]
            ),
            None,
        )
        if committed is not None:
            receipt = {
                "format": "opencntx-storage-cleanup-receipt",
                "format_version": 1,
                "project_id": state["project_id"],
                "plan_digest": plan["plan_digest"],
                "removed_digests": sorted(str(item["digest"]) for item in candidates),
                "reclaimed_bytes": sum(
                    _int_value(item["bytes"], "cleanup bytes") for item in candidates
                ),
                "unknown_files_untouched": True,
                "status": "COMPLETED",
                "revision": committed["revision"],
                "state_digest": state["state_digest"],
            }
            final = receipt | {"receipt_digest": _value_digest(receipt)}
            _write_atomic(receipt_path, _pretty(final))
            shutil.rmtree(staging_root, ignore_errors=True)
            return final
        if state["state_digest"] != plan.get("state_digest") or state["revision"] != plan.get(
            "revision"
        ):
            raise _fail("continuity_write_conflict", "Storage changed after cleanup preview.")
        removed: list[str] = []
        state_committed = False
        try:
            for item in candidates:
                relative = Path(str(item["relative_path"]))
                digest = str(item["digest"])
                if (
                    len(relative.parts) != 3
                    or relative.parts[0] != "objects"
                    or relative.parts[1] != digest[:2]
                    or relative.name != f"{digest}.gz"
                ):
                    raise _fail("continuity_path_unsafe", "Storage cleanup path escapes objects.")
                source = storage_root / relative
                staged = staging_root / f"{digest}.gz"
                if source.is_file():
                    _verify_blob(source, digest)
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, staged)
                elif staged.is_file():
                    _verify_blob(staged, digest)
                else:
                    raise _fail("continuity_evidence_missing", "Cleanup candidate is missing.")
                removed.append(digest)
                if fault_hook is not None:
                    fault_hook(f"AFTER_STAGE:{digest}")
            objects = dict(state["objects"])
            for digest in removed:
                objects.pop(digest, None)
            next_state = dict(state)
            next_state["objects"] = objects
            next_state["revision"] = int(state["revision"]) + 1
            next_state["audit"] = list(state["audit"])
            cleanup_event = {
                "revision": next_state["revision"],
                "action": "CLEANUP",
                "plan_digest": plan["plan_digest"],
                "removed_digests": sorted(removed),
            }
            next_state["audit"] = list(next_state["audit"]) + [cleanup_event]
            next_state.pop("state_digest", None)
            next_state["state_digest"] = _state_digest(next_state)
            _write_atomic(storage_root / "state.json", _pretty(next_state))
            state_committed = True
            if fault_hook is not None:
                fault_hook("AFTER_STATE")
            receipt = {
                "format": "opencntx-storage-cleanup-receipt",
                "format_version": 1,
                "project_id": state["project_id"],
                "plan_digest": plan["plan_digest"],
                "removed_digests": sorted(removed),
                "reclaimed_bytes": sum(
                    _int_value(item["bytes"], "cleanup bytes") for item in candidates
                ),
                "unknown_files_untouched": True,
                "status": "COMPLETED",
                "revision": next_state["revision"],
                "state_digest": next_state["state_digest"],
            }
            final = receipt | {"receipt_digest": _value_digest(receipt)}
            _write_atomic(receipt_path, _pretty(final))
            shutil.rmtree(staging_root, ignore_errors=True)
            return final
        except BaseException:
            if not state_committed:
                for digest in reversed(removed):
                    staged = staging_root / f"{digest}.gz"
                    source = _blob_path(storage_root, digest)
                    if staged.is_file() and not source.exists():
                        source.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(staged, source)
                shutil.rmtree(staging_root, ignore_errors=True)
            raise


def restore_storage_generation(
    project_root: Path, *, project_id: str, generation_id: str
) -> dict[str, bytes]:
    storage_root = _storage_root(project_root)
    state = adaptive_storage_state(project_root, project_id=project_id)
    selected = _identifier(generation_id, "generation_id")
    generation = next(
        (item for item in state["generations"] if item["generation_id"] == selected), None
    )
    if generation is None:
        raise _fail("continuity_evidence_missing", "Storage generation is missing.")
    return {
        record_id: _verify_blob(_blob_path(storage_root, digest), digest)
        for record_id, digest in generation["objects"].items()
    }


def build_storage_query(
    *,
    project_id: str,
    exact: str | None = None,
    text: str | None = None,
    relation_to: str | None = None,
    data_class: str | None = None,
    cursor: int = 0,
    limit: int = 25,
    scan_budget: int = 5_000,
    semantic_requested: bool = False,
) -> dict[str, Any]:
    if limit < 1 or limit > 100 or cursor < 0 or scan_budget < limit or scan_budget > 100_000:
        raise _fail("continuity_store_invalid", "Storage query budget is invalid.")
    if data_class is not None and data_class not in DATA_CLASSES:
        raise _fail("continuity_store_invalid", "Storage query data class is invalid.")
    basis = {
        "format": QUERY_FORMAT,
        "format_version": 1,
        "project_id": _identifier(project_id, "project_id"),
        "exact": _one_line(exact, "exact", 500) if exact else None,
        "text": _one_line(text, "text", 500) if text else None,
        "relation_to": _identifier(relation_to, "relation_to") if relation_to else None,
        "data_class": data_class,
        "cursor": cursor,
        "limit": limit,
        "scan_budget": scan_budget,
        "semantic_requested": semantic_requested,
    }
    return basis | {"query_digest": _value_digest(basis)}


def _local_matches(
    storage_root: Path, state: Mapping[str, Any], query: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    matches = []
    scanned = 0
    for record_id, record in sorted(state["records"].items()):
        if scanned >= _int_value(query["scan_budget"], "scan budget"):
            break
        scanned += 1
        digest = str(record["object_digest"])
        if query["exact"] and query["exact"] not in {record_id, digest, record["source"]}:
            continue
        if query["data_class"] and query["data_class"] != record["data_class"]:
            continue
        if query["relation_to"] and query["relation_to"] not in record["relations"]:
            continue
        confidence = 1.0 if query["exact"] else 0.75
        if query["text"]:
            raw = _verify_blob(_blob_path(storage_root, digest), digest)
            haystack = f"{record['source']}\n{raw.decode('utf-8', errors='replace')}".casefold()
            if str(query["text"]).casefold() not in haystack:
                continue
            confidence = 0.85
        matches.append(dict(record) | {"confidence": confidence})
    return matches, scanned


def _indexed_matches(
    storage_root: Path, state: Mapping[str, Any], query: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    matches: dict[str, dict[str, Any]] = {}
    scanned = 0
    for path in _index_paths(storage_root, str(state["profile"])):
        budget = _int_value(query["scan_budget"], "scan budget")
        remaining = budget - scanned
        if remaining <= 0:
            break
        with closing(
            sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        ) as connection:
            conditions: list[str] = []
            parameters: list[object] = []
            if query["exact"]:
                conditions.append("(record_id = ? OR digest = ? OR source = ?)")
                parameters.extend([query["exact"], query["exact"], query["exact"]])
            if query["data_class"]:
                conditions.append("data_class = ?")
                parameters.append(query["data_class"])
            if query["relation_to"]:
                conditions.append(
                    "EXISTS (SELECT 1 FROM relations rel "
                    "WHERE rel.record_id = records.record_id AND rel.target = ?)"
                )
                parameters.append(query["relation_to"])
            if query["text"]:
                term = str(query["text"])
                fts_ids: set[str] = set()
                try:
                    phrase = '"' + term.replace('"', '""') + '"'
                    fts_ids.update(
                        str(row[0])
                        for row in connection.execute(
                            "SELECT record_id FROM records_fts "
                            "WHERE records_fts MATCH ? LIMIT ?",
                            (phrase, remaining),
                        ).fetchall()
                    )
                except sqlite3.Error:
                    pass
                fts_ids.update(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT record_id FROM records "
                        "WHERE source LIKE ? OR text_content LIKE ? LIMIT ?",
                        (f"%{term}%", f"%{term}%", remaining),
                    ).fetchall()
                )
                if not fts_ids:
                    continue
                placeholders = ",".join("?" for _item in fts_ids)
                conditions.append(f"record_id IN ({placeholders})")
                parameters.extend(sorted(fts_ids))
            sql = (
                "SELECT record_id, digest, data_class, source, freshness, text_content "
                "FROM records"
            )
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += " ORDER BY record_id LIMIT ?"
            parameters.append(remaining)
            rows = connection.execute(sql, parameters).fetchall()
            record_ids = [str(row[0]) for row in rows]
            if record_ids:
                placeholders = ",".join("?" for _item in record_ids)
                relation_rows = connection.execute(
                    f"SELECT record_id, target FROM relations "
                    f"WHERE record_id IN ({placeholders})",
                    record_ids,
                ).fetchall()
            else:
                relation_rows = []
        relations: dict[str, set[str]] = {}
        for record_id, target in relation_rows:
            relations.setdefault(str(record_id), set()).add(str(target))
        for record_id, digest, data_class, source, freshness, content in rows:
            scanned += 1
            confidence = 1.0 if query["exact"] else 0.75
            if query["text"]:
                confidence = 0.85
            matches[str(record_id)] = {
                "record_id": record_id,
                "object_digest": digest,
                "data_class": data_class,
                "source": source,
                "relations": sorted(relations.get(record_id, set())),
                "freshness": freshness,
                "confidence": confidence,
            }
    return [matches[key] for key in sorted(matches)], scanned


def search_adaptive_storage(project_root: Path, query: Mapping[str, object]) -> dict[str, Any]:
    basis = {key: item for key, item in query.items() if key != "query_digest"}
    if query.get("format") != QUERY_FORMAT or query.get("query_digest") != _value_digest(basis):
        raise _fail("continuity_store_invalid", "Storage query is invalid or drifted.")
    state = adaptive_storage_state(project_root, project_id=str(query["project_id"]))
    storage_root = _storage_root(project_root)
    if state["profile"] == "TINY_LOCAL":
        matches, scanned = _local_matches(storage_root, state, query)
        strategy = "MANIFEST_SCAN"
    else:
        matches, scanned = _indexed_matches(storage_root, state, query)
        strategy = "SQLITE_INDEX"
    start = _int_value(query["cursor"], "query cursor")
    stop = start + _int_value(query["limit"], "query limit")
    page = matches[start:stop]
    next_cursor = stop if stop < len(matches) else None
    results = [
        {
            "record_id": item["record_id"],
            "object_digest": item["object_digest"],
            "source": item["source"],
            "data_class": item["data_class"],
            "freshness": item["freshness"],
            "confidence": item["confidence"],
            "provenance": {"project_id": state["project_id"], "profile": state["profile"]},
        }
        for item in page
    ]
    value = {
        "format": RESULT_FORMAT,
        "format_version": 1,
        "project_id": state["project_id"],
        "profile": state["profile"],
        "query_digest": query["query_digest"],
        "strategy": strategy,
        "semantic_status": "DISABLED" if not query["semantic_requested"] else "ADAPTER_REQUIRED",
        "scanned_records": scanned,
        "results": results,
        "next_cursor": next_cursor,
        "state_digest": state["state_digest"],
    }
    return value | {"result_digest": _value_digest(value)}


def validate_team_adapter(adapter: TeamStorageAdapter) -> dict[str, Any]:
    capabilities = dict(adapter.capabilities())
    required = {"identity", "roles", "audit", "compare_and_swap", "distributed_lock"}
    if set(capabilities) != required or not all(capabilities.get(name) is True for name in required):
        raise _fail("continuity_adapter_unavailable", "Team adapter lacks a required safety capability.")
    value = {"profile": "TEAM_SHARED", "capabilities": capabilities, "status": "READY"}
    return value | {"capabilities_digest": _value_digest(value)}


def team_compare_and_swap_event(
    adapter: TeamStorageAdapter,
    *,
    project_id: str,
    actor_id: str,
    role: str,
    expected_revision: int,
    operation_digest: str,
) -> dict[str, Any]:
    """Append one identity-bound audit event through an adapter CAS boundary."""
    validate_team_adapter(adapter)
    if role not in {"WRITER", "ADMIN"}:
        raise _fail("continuity_authority_missing", "Team actor lacks a writer role.")
    selected_project = _identifier(project_id, "project_id")
    current_value = adapter.read_state(selected_project)
    current = dict(current_value) if current_value is not None else {"revision": 0, "audit": []}
    audit = current.get("audit")
    if current.get("revision") != expected_revision or not isinstance(audit, list):
        raise _fail("continuity_write_conflict", "Team state revision changed before write.")
    event = {
        "actor_id": _identifier(actor_id, "actor_id"),
        "role": role,
        "operation_digest": _one_line(operation_digest, "operation_digest", 128),
        "previous_revision": expected_revision,
        "revision": expected_revision + 1,
    }
    event["event_digest"] = _value_digest(event)
    proposed = {"revision": expected_revision + 1, "audit": list(audit) + [event]}
    proposed["state_digest"] = _value_digest(proposed)
    if not adapter.compare_and_swap(selected_project, expected_revision, proposed):
        raise _fail("continuity_write_conflict", "Team compare-and-swap lost the writer race.")
    return {
        "format": "opencntx-team-write-receipt",
        "format_version": 1,
        "project_id": selected_project,
        "status": "COMMITTED",
        "revision": proposed["revision"],
        "actor_id": event["actor_id"],
        "role": role,
        "event_digest": event["event_digest"],
        "state_digest": proposed["state_digest"],
    }
