"""Local single-writer, transaction diagnosis, and recovery primitives."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from .primitives import sha256_bytes as _sha256
from .primitives import timestamp_microseconds as _timestamp

TRANSACTION_FORMAT = "opencntx-transaction"
TRANSACTION_VERSION = 1
PHASE_FORMAT = "opencntx-transaction-phase"
PHASE_VERSION = 1
COMPLETION_FORMAT = "opencntx-transaction-completion"
COMPLETION_VERSION = 1
RECOVERY_FORMAT = "opencntx-recovery-receipt"
RECOVERY_VERSION = 1
LOCK_FORMAT = "opencntx-writer-lock"
LOCK_VERSION = 1

TRANSACTION_ID_PATTERN = re.compile(r"TXN-\d{8}T\d{12}Z-[0-9a-f]{12}\Z")
RECOVERY_ID_PATTERN = re.compile(r"RECOVERY-\d{8}T\d{12}Z-[0-9a-f]{12}\Z")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
TASK_ID_PATTERN = re.compile(r"TASK-\d{8}-\d{4}\Z")
SAFE_COMPONENT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_OS_REPLACE = os.replace


class IntegrityError(Exception):
    """A stable fail-closed error raised by the integrity layer."""

    def __init__(self, message: str, *, code: str = "integrity_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DoctorIssue:
    code: str
    status: str
    message: str
    transaction_id: str | None = None
    intent_sha256: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    root: Path
    status: str
    issues: tuple[DoctorIssue, ...]

    @property
    def ok(self) -> bool:
        return self.status == "HEALTHY"


@dataclass(frozen=True)
class RecoveryPlan:
    root: Path
    transaction_id: str
    intent_sha256: str
    status: str
    action: str
    targets: tuple[dict[str, Any], ...]
    backup_path: Path
    receipt_path: Path | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S%fZ")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
        value = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(
            f"{label} is unreadable or invalid.", code="transaction_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise IntegrityError(f"{label} must be a JSON object.", code="transaction_invalid")
    return value, content


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError as exc:
        raise IntegrityError(
            "Managed path metadata is unavailable.", code="managed_path_unsafe"
        ) from exc
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _relative_parts(relative: str | Path) -> tuple[str, ...]:
    text = relative.as_posix() if isinstance(relative, Path) else relative.replace("\\", "/")
    pure = PurePosixPath(text)
    if (
        not text
        or not pure.parts
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or ":" in pure.parts[0]
    ):
        raise IntegrityError(
            "Managed path must be an exact relative path.", code="managed_path_unsafe"
        )
    return pure.parts


def _path_present(path: Path) -> bool:
    try:
        return path.exists() or path.is_symlink()
    except OSError as exc:
        raise IntegrityError(
            "Managed state path is inaccessible.",
            code="managed_path_unsafe",
        ) from exc


def safe_managed_path(
    root: Path,
    relative: str | Path,
    *,
    must_exist: bool = False,
    kind: str | None = None,
) -> Path:
    """Return one contained path after rejecting links and reparse points."""
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise IntegrityError("Workspace root is unavailable.", code="managed_path_unsafe") from exc
    if resolved_root.is_symlink() or _is_reparse(resolved_root) or not resolved_root.is_dir():
        raise IntegrityError(
            "Workspace root must be a normal local directory.", code="managed_path_unsafe"
        )
    parts = _relative_parts(relative)
    current = resolved_root
    for index, part in enumerate(parts):
        current = current / part
        exists = _path_present(current)
        if not exists:
            if must_exist or index < len(parts) - 1:
                raise IntegrityError("Managed path is missing.", code="managed_path_unsafe")
            break
        if current.is_symlink() or _is_reparse(current):
            raise IntegrityError(
                "Managed path contains a link or reparse point.", code="managed_path_unsafe"
            )
        try:
            resolved = current.resolve(strict=True)
        except OSError as exc:
            raise IntegrityError(
                "Managed path cannot be resolved safely.", code="managed_path_unsafe"
            ) from exc
        if not resolved.is_relative_to(resolved_root):
            raise IntegrityError("Managed path leaves the workspace.", code="managed_path_unsafe")
    if _path_present(current):
        if kind == "file" and not current.is_file():
            raise IntegrityError("Managed path is not a normal file.", code="managed_path_unsafe")
        if kind == "directory" and not current.is_dir():
            raise IntegrityError(
                "Managed path is not a normal directory.", code="managed_path_unsafe"
            )
    return current


def sync_directory(path: Path) -> str:
    """Flush a directory where supported, without overstating durability."""
    if os.name != "nt":
        descriptor: int | None = None
        try:
            descriptor = os.open(path, os.O_RDONLY)
            os.fsync(descriptor)
            return "SYNCED"
        except (AttributeError, NotImplementedError):
            return "UNSUPPORTED"
        except OSError:
            return "FAILED"
        finally:
            if descriptor is not None:
                os.close(descriptor)

    kernel32 = vars(ctypes)["windll"].kernel32
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    flush = kernel32.FlushFileBuffers
    flush.argtypes = [ctypes.c_void_p]
    flush.restype = ctypes.c_int
    close = kernel32.CloseHandle
    close.argtypes = [ctypes.c_void_p]
    close.restype = ctypes.c_int
    handle = create_file(
        str(path),
        0x80000000,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x02000000,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in (None, invalid):
        return "UNSUPPORTED"
    try:
        return "SYNCED" if flush(handle) else "UNSUPPORTED"
    finally:
        close(handle)


def write_new_bytes(
    path: Path,
    content: bytes,
    *,
    mode: int = 0o666,
    private: bool = False,
    sync_parent: bool = False,
) -> str:
    """Write exact bytes to one absent file and optionally flush its parent."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    if private and os.name != "nt":
        os.chmod(path, 0o600)
    return sync_directory(path.parent) if sync_parent else "NOT_REQUESTED"


def _write_new(path: Path, content: bytes) -> str:
    try:
        result = write_new_bytes(path, content, sync_parent=True)
    except OSError as exc:
        raise IntegrityError(
            "Transaction evidence could not be written.", code="transaction_write_failed"
        ) from exc
    if result == "FAILED":
        raise IntegrityError("Parent directory flush failed.", code="transaction_durability_failed")
    return result


def _create_integrity_directory(path: Path, *, exist_ok: bool = False) -> None:
    """Create one private POSIX or inherited-ACL Windows integrity directory."""
    try:
        if os.name == "nt":
            path.mkdir(exist_ok=exist_ok)
        else:
            path.mkdir(mode=0o700, exist_ok=exist_ok)
        if path.is_symlink() or _is_reparse(path):
            raise IntegrityError(
                "Integrity directory is not a normal directory.",
                code="managed_path_unsafe",
            )
        resolved = path.resolve(strict=True)
        if not resolved.is_dir():
            raise IntegrityError(
                "Integrity directory is not a normal directory.",
                code="managed_path_unsafe",
            )
        with os.scandir(resolved) as entries:
            next(entries, None)
    except IntegrityError:
        raise
    except OSError as exc:
        raise IntegrityError(
            "Integrity directory is inaccessible.",
            code="managed_path_unsafe",
        ) from exc


def _path_digest(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "ABSENT"
    if path.is_symlink() or _is_reparse(path):
        raise IntegrityError("A transaction target is link-like.", code="managed_path_unsafe")
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(b"F\0")
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    if not path.is_dir():
        raise IntegrityError(
            "A transaction target has an unsupported type.", code="managed_path_unsafe"
        )
    digest.update(b"D\0")
    for candidate in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        if candidate.is_symlink() or _is_reparse(candidate):
            raise IntegrityError(
                "A transaction target contains a link.", code="managed_path_unsafe"
            )
        relative = candidate.relative_to(path).as_posix().encode("utf-8")
        if candidate.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif candidate.is_file():
            digest.update(b"F\0" + relative + b"\0")
            with candidate.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
        else:
            raise IntegrityError(
                "A transaction target contains an unsupported entry.", code="managed_path_unsafe"
            )
    return digest.hexdigest()


def state_digest(paths: Sequence[Path]) -> str:
    try:
        value = [{"path": path.as_posix(), "sha256": _path_digest(path)} for path in paths]
    except IntegrityError:
        raise
    except OSError as exc:
        raise IntegrityError(
            "Transaction state path is inaccessible.",
            code="managed_path_unsafe",
        ) from exc
    return _sha256(_json_bytes(value))


class _FileLock:
    def __init__(self, path: Path, handle: Any, metadata: dict[str, Any], *, created: bool) -> None:
        self.path = path
        self.handle = handle
        self.metadata = metadata
        self.created = created
        self.locked = True

    @staticmethod
    def _lock(handle: Any) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                vars(msvcrt)["locking"](handle.fileno(), vars(msvcrt)["LK_NBLCK"], 1)
            except OSError as exc:
                raise IntegrityError(
                    "Another writer is active.", code="transaction_locked"
                ) from exc
        else:
            import fcntl

            try:
                vars(fcntl)["flock"](
                    handle.fileno(), vars(fcntl)["LOCK_EX"] | vars(fcntl)["LOCK_NB"]
                )
            except OSError as exc:
                raise IntegrityError(
                    "Another writer is active.", code="transaction_locked"
                ) from exc

    @staticmethod
    def _unlock(handle: Any) -> None:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            vars(msvcrt)["locking"](handle.fileno(), vars(msvcrt)["LK_UNLCK"], 1)
        else:
            import fcntl

            vars(fcntl)["flock"](handle.fileno(), vars(fcntl)["LOCK_UN"])

    @classmethod
    def create(cls, path: Path, metadata: dict[str, Any]) -> _FileLock:
        try:
            handle = path.open("x+b")
        except FileExistsError:
            try:
                existing = path.read_bytes()
                parsed = json.loads(existing)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                raise IntegrityError(
                    "Another writer is active.", code="transaction_locked"
                ) from None
            if not isinstance(parsed, dict) or parsed.get("format") != LOCK_FORMAT:
                raise IntegrityError(
                    "Another writer is active.", code="transaction_locked"
                ) from None
            active = cls.is_active(path)
            code = "transaction_locked" if active else "transaction_recovery_required"
            message = (
                "Another writer is active." if active else "A stale writer lock requires recovery."
            )
            raise IntegrityError(message, code=code) from None
        try:
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())
            cls._lock(handle)
            content = _json_bytes(metadata)
            handle.seek(0)
            handle.truncate()
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            result = sync_directory(path.parent)
            if result == "FAILED":
                raise IntegrityError(
                    "Lock directory flush failed.", code="transaction_durability_failed"
                )
            return cls(path, handle, metadata, created=True)
        except BaseException:
            try:
                handle.close()
            finally:
                path.unlink(missing_ok=True)
            raise

    @classmethod
    def open_stale(cls, path: Path) -> _FileLock:
        try:
            handle = path.open("r+b")
        except OSError as exc:
            raise IntegrityError("Writer lock is unavailable.", code="transaction_invalid") from exc
        try:
            cls._lock(handle)
            handle.seek(0)
            try:
                metadata = json.loads(handle.read())
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise IntegrityError(
                    "Writer lock is unreadable or invalid.", code="transaction_invalid"
                ) from exc
            if not isinstance(metadata, dict):
                raise IntegrityError("Writer lock is invalid.", code="transaction_invalid")
            return cls(path, handle, metadata, created=False)
        except BaseException:
            handle.close()
            raise

    @classmethod
    def is_active(cls, path: Path) -> bool:
        try:
            handle = path.open("r+b")
        except OSError:
            return False
        try:
            try:
                cls._lock(handle)
            except IntegrityError as exc:
                if exc.code == "transaction_locked":
                    return True
                raise
            cls._unlock(handle)
            return False
        finally:
            handle.close()

    def close(self, *, remove: bool) -> None:
        if not self.locked:
            return
        try:
            self._unlock(self.handle)
        finally:
            self.locked = False
            self.handle.close()
        if remove:
            try:
                self.path.unlink()
                sync_directory(self.path.parent)
            except OSError as exc:
                raise IntegrityError(
                    "Writer lock could not be removed.", code="transaction_recovery_required"
                ) from exc


_LOCAL = threading.local()
_TEST_FAULT_HOOK: Callable[[str, str], None] | None = None


def _held() -> dict[str, tuple[_FileLock, int]]:
    value = getattr(_LOCAL, "held", None)
    if value is None:
        value = {}
        _LOCAL.held = value
    return value


def _layout(root: Path, *, create: bool) -> dict[str, Path]:
    resolved = root.resolve(strict=True)
    candidate = resolved / ".opencntx"
    if not _path_present(candidate) and create:
        _create_integrity_directory(candidate, exist_ok=True)
        result = sync_directory(resolved)
        if result == "FAILED":
            raise IntegrityError(
                "Integrity root flush failed.", code="transaction_durability_failed"
            )
    opencntx = safe_managed_path(resolved, ".opencntx", must_exist=True, kind="directory")
    paths = {
        "transactions": opencntx / "transactions",
        "locks": opencntx / "transactions" / "locks",
        "task_locks": opencntx / "transactions" / "locks" / "tasks",
        "active": opencntx / "transactions" / "active",
        "completed": opencntx / "transactions" / "completed",
        "recovery": opencntx / "recovery",
        "backups": opencntx / "recovery" / "backups",
        "receipts": opencntx / "receipts",
    }
    if create:
        for key in (
            "transactions",
            "locks",
            "task_locks",
            "active",
            "completed",
            "recovery",
            "backups",
        ):
            path = paths[key]
            if _path_present(path):
                if path.is_symlink() or _is_reparse(path) or not path.is_dir():
                    raise IntegrityError("Integrity path is unsafe.", code="managed_path_unsafe")
            else:
                _create_integrity_directory(path, exist_ok=True)
                result = sync_directory(path.parent)
                if result == "FAILED":
                    raise IntegrityError(
                        "Integrity directory flush failed.", code="transaction_durability_failed"
                    )
    return paths


def _lock_relative(task_id: str | None) -> str:
    if task_id is None:
        return ".opencntx/transactions/locks/workspace.lock"
    if TASK_ID_PATTERN.fullmatch(task_id) is None:
        raise IntegrityError("Task lock target is invalid.", code="transaction_target_invalid")
    return f".opencntx/transactions/locks/tasks/{task_id}.lock"


@contextmanager
def _locks(
    root: Path, operation: str, *, workspace: bool, task_id: str | None
) -> Iterator[list[_FileLock]]:
    requests: list[str] = []
    if workspace:
        requests.append(_lock_relative(None))
    if task_id is not None:
        requests.append(_lock_relative(task_id))
    acquired: list[_FileLock] = []
    local = _held()
    try:
        for relative in requests:
            if relative in local:
                lock, count = local[relative]
                local[relative] = (lock, count + 1)
                acquired.append(lock)
                continue
            path = safe_managed_path(root, relative)
            metadata = {
                "created_at": _timestamp(_now()),
                "format": LOCK_FORMAT,
                "format_version": LOCK_VERSION,
                "host": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "local",
                "lock_id": f"LOCK-{uuid4().hex}",
                "operation": operation,
                "pid": os.getpid(),
                "scope": "workspace" if relative.endswith("workspace.lock") else "task",
                "target": relative,
            }
            lock = _FileLock.create(path, metadata)
            local[relative] = (lock, 1)
            acquired.append(lock)
        yield acquired
    finally:
        for relative in reversed(requests):
            entry = local.get(relative)
            if entry is None:
                continue
            lock, count = entry
            if count > 1:
                local[relative] = (lock, count - 1)
            else:
                del local[relative]
                lock.close(remove=True)


class Transaction:
    def __init__(
        self,
        root: Path,
        directory: Path,
        transaction_id: str,
        intent: dict[str, Any],
        locks: Sequence[_FileLock],
    ) -> None:
        self.root = root
        self.directory = directory
        self.transaction_id = transaction_id
        self.intent = intent
        self.intent_sha256 = _sha256(_json_bytes(intent))
        self.locks = tuple(locks)
        self.targets: list[dict[str, Any]] = []
        self.phase_number = 0

    def checkpoint(self, name: str, details: dict[str, Any] | None = None) -> None:
        self.phase_number += 1
        phases = self.directory / "phases"
        directory_sync = sync_directory(phases)
        if directory_sync == "FAILED":
            raise IntegrityError(
                "Transaction phase directory flush failed.", code="transaction_durability_failed"
            )
        value = {
            "details": details or {},
            "directory_sync": directory_sync,
            "format": PHASE_FORMAT,
            "format_version": PHASE_VERSION,
            "phase": name,
            "phase_number": self.phase_number,
            "recorded_at": _timestamp(_now()),
            "transaction_id": self.transaction_id,
        }
        _write_new(phases / f"{self.phase_number:04d}-{name.lower()}.json", _json_bytes(value))
        if _TEST_FAULT_HOOK is not None:
            _TEST_FAULT_HOOK(self.transaction_id, name)

    def track_target(self, target: Path) -> dict[str, Any]:
        try:
            relative = target.resolve(strict=False).relative_to(self.root).as_posix()
        except (OSError, ValueError) as exc:
            raise IntegrityError(
                "Transaction target leaves the workspace.", code="transaction_target_invalid"
            ) from exc
        target = safe_managed_path(self.root, relative)
        index = len(self.targets) + 1
        digest = _path_digest(target)
        previous_relative: str | None = None
        if digest != "ABSENT":
            previous = self.directory / "previous" / f"{index:04d}"
            previous.parent.mkdir(exist_ok=True)
            if target.is_dir():
                shutil.copytree(target, previous)
            else:
                shutil.copy2(target, previous)
            if _path_digest(previous) != digest:
                raise IntegrityError(
                    "Transaction backup verification failed.", code="transaction_backup_failed"
                )
            previous_relative = previous.relative_to(self.directory).as_posix()
            sync_directory(previous.parent)
        record = {
            "index": index,
            "path": relative,
            "previous_path": previous_relative,
            "previous_sha256": digest,
        }
        self.targets.append(record)
        _write_new(self.directory / f"target-{index:04d}.json", _json_bytes(record))
        self.checkpoint("TARGET_TRACKED", {"path": relative, "previous_sha256": digest})
        return record

    def mark_target_published(self, target: Path) -> None:
        relative = target.resolve(strict=False).relative_to(self.root).as_posix()
        if relative not in {item["path"] for item in self.targets}:
            raise IntegrityError(
                "Published target was not tracked.", code="transaction_target_invalid"
            )
        self.checkpoint(
            "TARGET_PUBLISHED",
            {"path": relative, "sha256": _path_digest(self.root / relative)},
        )

    def _track_published_new_target(self, target: Path) -> None:
        relative = target.resolve(strict=False).relative_to(self.root).as_posix()
        if relative in {item["path"] for item in self.targets}:
            return
        target = safe_managed_path(self.root, relative, must_exist=True)
        index = len(self.targets) + 1
        record = {
            "index": index,
            "path": relative,
            "previous_path": None,
            "previous_sha256": "ABSENT",
        }
        self.targets.append(record)
        _write_new(self.directory / f"target-{index:04d}.json", _json_bytes(record))
        self.checkpoint("TARGET_TRACKED", {"path": relative, "previous_sha256": "ABSENT"})
        self.mark_target_published(target)

    def mark_published(self) -> None:
        current = [
            {"path": item["path"], "sha256": _path_digest(self.root / item["path"])}
            for item in self.targets
        ]
        self.checkpoint("PUBLISHED", {"targets": current})

    def mark_receipted(self, receipt: Path | None) -> None:
        details: dict[str, Any] = {}
        if receipt is not None:
            self._track_published_new_target(receipt)
            details = {
                "receipt": receipt.relative_to(self.root).as_posix(),
                "receipt_sha256": _path_digest(receipt),
            }
        self.checkpoint("RECEIPTED", details)

    def _restore(self) -> None:
        after = self.directory / "current-after-error"
        for item in reversed(self.targets):
            target = self.root / item["path"]
            if target.exists() or target.is_symlink():
                after_target = after / f"{item['index']:04d}"
                after_target.parent.mkdir(exist_ok=True)
                _OS_REPLACE(target, after_target)
            previous_path = item["previous_path"]
            if previous_path is not None:
                previous = self.directory / previous_path
                if previous.is_dir():
                    shutil.copytree(previous, target)
                else:
                    shutil.copy2(previous, target)
            if _path_digest(target) != item["previous_sha256"]:
                raise IntegrityError(
                    "Automatic rollback could not restore the previous state.",
                    code="transaction_recovery_required",
                )
            sync_directory(target.parent)

    def abort(self, error: BaseException) -> None:
        self._restore()
        self.checkpoint("ABORTED_ROLLED_BACK", {"error_class": type(error).__name__})
        self._archive("ABORTED_ROLLED_BACK")

    def complete(self) -> None:
        self.checkpoint("COMPLETED", {})
        for transient_name in ("previous", "current-after-error"):
            transient = self.directory / transient_name
            if transient.exists():
                shutil.rmtree(transient)
        self._archive("COMPLETED")

    def _archive(self, status: str) -> None:
        completion = {
            "completed_at": _timestamp(_now()),
            "format": COMPLETION_FORMAT,
            "format_version": COMPLETION_VERSION,
            "intent_sha256": self.intent_sha256,
            "status": status,
            "transaction_id": self.transaction_id,
        }
        _write_new(self.directory / "completion.json", _json_bytes(completion))
        destination = self.directory.parent.parent / "completed" / self.transaction_id
        _OS_REPLACE(self.directory, destination)
        result = sync_directory(destination.parent)
        if result == "FAILED":
            raise IntegrityError(
                "Transaction archive flush failed.", code="transaction_durability_failed"
            )
        self.directory = destination


@contextmanager
def writer_transaction(
    root: Path,
    operation: str,
    *,
    workspace: bool = True,
    task_id: str | None = None,
    expected_digest: str | None = None,
    current_digest: Callable[[], str] | None = None,
) -> Iterator[Transaction]:
    """Hold exact writer locks and durable evidence for one mutation."""
    resolved = root.resolve(strict=True)
    layout = _layout(resolved, create=True)
    with _locks(resolved, operation, workspace=workspace, task_id=task_id) as locks:
        if expected_digest is not None and (
            current_digest is None or current_digest() != expected_digest
        ):
            raise IntegrityError(
                "Transaction basis changed before publication.",
                code="transaction_state_changed",
            )
        now = _now()
        transaction_id = f"TXN-{_stamp(now)}-{uuid4().hex[:12]}"
        directory = layout["active"] / transaction_id
        _create_integrity_directory(directory)
        _create_integrity_directory(directory / "phases")
        intent = {
            "created_at": _timestamp(now),
            "expected_digest": expected_digest,
            "format": TRANSACTION_FORMAT,
            "format_version": TRANSACTION_VERSION,
            "locks": [
                {
                    "path": lock.path.relative_to(resolved).as_posix(),
                    "sha256": _sha256(_json_bytes(lock.metadata)),
                }
                for lock in locks
            ],
            "operation": operation,
            "task_id": task_id,
            "transaction_id": transaction_id,
        }
        _write_new(directory / "intent.json", _json_bytes(intent))
        transaction = Transaction(resolved, directory, transaction_id, intent, locks)
        transaction.checkpoint("INTENT_DURABLE", {})
        try:
            yield transaction
        except (Exception, GeneratorExit, KeyboardInterrupt, SystemExit) as exc:
            try:
                transaction.abort(exc)
            except (Exception, GeneratorExit, KeyboardInterrupt, SystemExit):
                raise IntegrityError(
                    "Mutation failed and exact recovery is required.",
                    code="transaction_recovery_required",
                ) from exc
            raise
        else:
            transaction.complete()


def _transaction_directories(root: Path) -> tuple[Path | None, Path | None]:
    opencntx = safe_managed_path(root, ".opencntx", must_exist=True, kind="directory")
    transactions = opencntx / "transactions"
    if not transactions.exists():
        return None, None
    if transactions.is_symlink() or _is_reparse(transactions) or not transactions.is_dir():
        raise IntegrityError("Transaction root is unsafe.", code="managed_path_unsafe")
    active = transactions / "active"
    locks = transactions / "locks"
    return active if active.exists() else None, locks if locks.exists() else None


def doctor_workspace(project_root: Path) -> DoctorReport:
    """Inspect transaction state without creating, locking, or repairing anything."""
    try:
        root = project_root.resolve(strict=True)
        if root.is_symlink() or _is_reparse(root) or not root.is_dir():
            raise IntegrityError("Workspace root is unsafe.", code="managed_path_unsafe")
        safe_managed_path(root, ".opencntx", must_exist=True, kind="directory")
        active_root, locks_root = _transaction_directories(root)
        issues: list[DoctorIssue] = []
        if locks_root is not None:
            if locks_root.is_symlink() or _is_reparse(locks_root) or not locks_root.is_dir():
                raise IntegrityError("Lock root is unsafe.", code="managed_path_unsafe")
            for lock in sorted(locks_root.rglob("*.lock")):
                if lock.is_symlink() or _is_reparse(lock) or not lock.is_file():
                    issues.append(
                        DoctorIssue(
                            "managed_path_unsafe", "UNSAFE_UNKNOWN_STATE", "Lock path is unsafe."
                        )
                    )
                    continue
                active = _FileLock.is_active(lock)
                status = "ACTIVE" if active else "RECOVERY_REQUIRED"
                issues.append(
                    DoctorIssue(
                        "transaction_locked" if active else "transaction_recovery_required",
                        status,
                        "A writer is active."
                        if active
                        else "A stale writer lock requires exact recovery.",
                    )
                )
        if active_root is not None:
            if active_root.is_symlink() or _is_reparse(active_root) or not active_root.is_dir():
                raise IntegrityError(
                    "Active transaction root is unsafe.", code="managed_path_unsafe"
                )
            for directory in sorted(active_root.iterdir()):
                if (
                    directory.is_symlink()
                    or _is_reparse(directory)
                    or not directory.is_dir()
                    or TRANSACTION_ID_PATTERN.fullmatch(directory.name) is None
                ):
                    issues.append(
                        DoctorIssue(
                            "transaction_unknown",
                            "UNSAFE_UNKNOWN_STATE",
                            "Unknown transaction entry.",
                        )
                    )
                    continue
                try:
                    intent, content = _read_json(
                        directory / "intent.json", label="Transaction intent"
                    )
                    transaction_id = intent.get("transaction_id")
                    if (
                        transaction_id != directory.name
                        or intent.get("format") != TRANSACTION_FORMAT
                        or intent.get("format_version") != TRANSACTION_VERSION
                    ):
                        raise IntegrityError(
                            "Transaction intent does not match its directory.",
                            code="transaction_invalid",
                        )
                    targets = _load_targets(directory)
                    phases = _phase_records(directory)
                    published = _published_digests(phases)
                    for item in targets:
                        expected = published.get(item["path"], item["previous_sha256"])
                        if _path_digest(safe_managed_path(root, item["path"])) != expected:
                            raise IntegrityError(
                                "Transaction target differs from its phase proof.",
                                code="recovery_target_mismatch",
                            )
                    digest = _sha256(content)
                    issues.append(
                        DoctorIssue(
                            "transaction_recovery_required",
                            "RECOVERY_REQUIRED",
                            f"Incomplete transaction at phase {phases[-1]['phase']} requires exact rollback.",
                            transaction_id=directory.name,
                            intent_sha256=digest,
                        )
                    )
                except IntegrityError as exc:
                    issues.append(
                        DoctorIssue(
                            exc.code,
                            "UNSAFE_UNKNOWN_STATE",
                            str(exc),
                            transaction_id=directory.name,
                        )
                    )
        statuses = {issue.status for issue in issues}
        if "UNSAFE_UNKNOWN_STATE" in statuses:
            status = "UNSAFE_UNKNOWN_STATE"
        elif "ACTIVE" in statuses:
            status = "ACTIVE"
        elif "RECOVERY_REQUIRED" in statuses:
            status = "RECOVERY_REQUIRED"
        else:
            status = "HEALTHY"
        return DoctorReport(root, status, tuple(issues))
    except IntegrityError:
        raise
    except OSError as exc:
        raise IntegrityError(
            "Workspace diagnosis could not be completed.", code="doctor_failed"
        ) from exc


def format_doctor_report(report: DoctorReport) -> str:
    lines = [f"Workspace doctor: {report.status}"]
    for issue in report.issues:
        detail = f"- {issue.status}: {issue.code}: {issue.message}"
        if issue.transaction_id is not None:
            detail += (
                f" Transaction: {issue.transaction_id}. Intent-SHA-256: {issue.intent_sha256}."
            )
        lines.append(detail)
    if not report.issues:
        lines.append("No active or incomplete transaction state found.")
    lines.append("Read-only inspection; no workspace data was changed.")
    return "\n".join(lines)


def _load_targets(directory: Path) -> list[dict[str, Any]]:
    allowed = {"intent.json", "phases", "previous", "current-after-error", "completion.json"}
    target_files = sorted(directory.glob("target-*.json"))
    allowed.update(path.name for path in target_files)
    unknown = {path.name for path in directory.iterdir()} - allowed
    if unknown:
        raise IntegrityError("Transaction contains unknown data.", code="transaction_unknown")
    targets: list[dict[str, Any]] = []
    for expected, path in enumerate(target_files, start=1):
        value, _ = _read_json(path, label="Transaction target")
        previous_sha256 = value.get("previous_sha256")
        previous_path = value.get("previous_path")
        if (
            value.get("index") != expected
            or not isinstance(value.get("path"), str)
            or previous_sha256 != "ABSENT"
            and (
                not isinstance(previous_sha256, str)
                or DIGEST_PATTERN.fullmatch(previous_sha256) is None
            )
            or previous_path not in {None, f"previous/{expected:04d}"}
        ):
            raise IntegrityError(
                "Transaction target record is invalid.", code="transaction_invalid"
            )
        _relative_parts(value["path"])
        if previous_path is not None:
            previous = directory / previous_path
            if not previous.exists() or _path_digest(previous) != previous_sha256:
                raise IntegrityError(
                    "Transaction previous-state proof is invalid.", code="transaction_invalid"
                )
        targets.append(value)
    return targets


def _phase_records(directory: Path) -> list[dict[str, Any]]:
    phases = directory / "phases"
    if not phases.is_dir() or phases.is_symlink() or _is_reparse(phases):
        raise IntegrityError("Transaction phase directory is invalid.", code="transaction_invalid")
    records: list[dict[str, Any]] = []
    for expected, path in enumerate(sorted(phases.iterdir()), start=1):
        if path.is_symlink() or _is_reparse(path) or not path.is_file():
            raise IntegrityError("Transaction phase entry is unsafe.", code="transaction_unknown")
        value, _ = _read_json(path, label="Transaction phase")
        phase = value.get("phase")
        if (
            value.get("format") != PHASE_FORMAT
            or value.get("format_version") != PHASE_VERSION
            or value.get("phase_number") != expected
            or not isinstance(phase, str)
            or path.name != f"{expected:04d}-{phase.lower()}.json"
            or value.get("directory_sync") not in {"SYNCED", "UNSUPPORTED"}
        ):
            raise IntegrityError("Transaction phase record is invalid.", code="transaction_invalid")
        records.append(value)
    if not records or records[0].get("phase") != "INTENT_DURABLE":
        raise IntegrityError("Transaction has no durable intent phase.", code="transaction_invalid")
    return records


def _published_digests(phases: Sequence[dict[str, Any]]) -> dict[str, str]:
    published: dict[str, str] = {}
    for phase in phases:
        details = phase.get("details")
        if not isinstance(details, dict):
            raise IntegrityError(
                "Transaction phase details are invalid.", code="transaction_invalid"
            )
        if phase.get("phase") == "TARGET_PUBLISHED":
            path = details.get("path")
            digest = details.get("sha256")
            if not isinstance(path, str) or not isinstance(digest, str):
                raise IntegrityError(
                    "Published target proof is invalid.", code="transaction_invalid"
                )
            published[path] = digest
        if phase.get("phase") == "PUBLISHED":
            targets = details.get("targets")
            if not isinstance(targets, list):
                raise IntegrityError(
                    "Published bundle proof is invalid.", code="transaction_invalid"
                )
            for item in targets:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("path"), str)
                    or not isinstance(item.get("sha256"), str)
                ):
                    raise IntegrityError(
                        "Published bundle target is invalid.", code="transaction_invalid"
                    )
                published[item["path"]] = item["sha256"]
    return published


def _recovery_paths(
    root: Path, transaction_id: str
) -> tuple[Path, dict[str, Any], bytes, list[dict[str, Any]], list[dict[str, Any]]]:
    if TRANSACTION_ID_PATTERN.fullmatch(transaction_id) is None:
        raise IntegrityError("Transaction ID is invalid.", code="recovery_target_mismatch")
    active = safe_managed_path(
        root,
        f".opencntx/transactions/active/{transaction_id}",
        must_exist=True,
        kind="directory",
    )
    intent, content = _read_json(active / "intent.json", label="Transaction intent")
    if intent.get("transaction_id") != transaction_id:
        raise IntegrityError(
            "Transaction ID does not match the intent.", code="recovery_target_mismatch"
        )
    targets = _load_targets(active)
    phases = _phase_records(active)
    return active, intent, content, targets, phases


def recover_workspace(
    project_root: Path,
    transaction_id: str,
    intent_sha256: str,
    *,
    apply: bool = False,
) -> RecoveryPlan:
    """Preview or apply exact rollback of one incomplete transaction."""
    root = project_root.resolve(strict=True)
    if DIGEST_PATTERN.fullmatch(intent_sha256) is None:
        raise IntegrityError("Intent SHA-256 is invalid.", code="recovery_target_mismatch")
    active, intent, content, targets, phases = _recovery_paths(root, transaction_id)
    actual_digest = _sha256(content)
    if actual_digest != intent_sha256:
        raise IntegrityError("Intent SHA-256 does not match.", code="recovery_target_mismatch")
    published = _published_digests(phases)
    before_digests: list[dict[str, str]] = []
    for item in targets:
        target = safe_managed_path(root, item["path"])
        current = _path_digest(target)
        expected = published.get(item["path"], item["previous_sha256"])
        if current != expected:
            raise IntegrityError(
                "Current target differs from the exact transaction phase.",
                code="recovery_target_mismatch",
            )
        before_digests.append({"path": item["path"], "sha256": current})
    recovery_id = transaction_id.replace("TXN-", "RECOVERY-", 1)
    backup = root / ".opencntx" / "recovery" / "backups" / recovery_id
    plan = RecoveryPlan(
        root=root,
        transaction_id=transaction_id,
        intent_sha256=intent_sha256,
        status="RECOVERY_PREVIEW",
        action="ROLL_BACK_TO_PREVIOUS",
        targets=tuple(targets),
        backup_path=backup,
    )
    if not apply:
        return plan

    layout = _layout(root, create=True)
    stale_locks: list[_FileLock] = []
    try:
        for lock_record in intent.get("locks", []):
            if not isinstance(lock_record, dict) or not isinstance(lock_record.get("path"), str):
                raise IntegrityError(
                    "Transaction lock record is invalid.", code="transaction_invalid"
                )
            lock_path = safe_managed_path(root, lock_record["path"], must_exist=True, kind="file")
            if _FileLock.is_active(lock_path):
                raise IntegrityError("Another writer is active.", code="transaction_locked")
            try:
                lock_digest = _sha256(lock_path.read_bytes())
            except PermissionError as exc:
                raise IntegrityError(
                    "Another writer is active.", code="transaction_locked"
                ) from exc
            except OSError as exc:
                raise IntegrityError(
                    "Writer lock cannot be read.", code="transaction_invalid"
                ) from exc
            if lock_digest != lock_record.get("sha256"):
                raise IntegrityError("Writer lock digest changed.", code="recovery_target_mismatch")
            stale_locks.append(_FileLock.open_stale(lock_path))

        _create_integrity_directory(backup)
        shutil.copytree(active, backup / "transaction")
        current_root = backup / "current"
        _create_integrity_directory(current_root)
        for item in targets:
            target = safe_managed_path(root, item["path"])
            current_backup = current_root / f"{item['index']:04d}"
            if target.exists():
                if target.is_dir():
                    shutil.copytree(target, current_backup)
                else:
                    shutil.copy2(target, current_backup)
                if _path_digest(current_backup) != _path_digest(target):
                    raise IntegrityError(
                        "Recovery backup verification failed.", code="transaction_backup_failed"
                    )
        manifest = {
            "backup_id": recovery_id,
            "current_targets": before_digests,
            "format": "opencntx-recovery-backup",
            "format_version": 1,
            "intent_sha256": intent_sha256,
            "transaction_id": transaction_id,
        }
        _write_new(backup / "manifest.json", _json_bytes(manifest))
        if sync_directory(backup) == "FAILED":
            raise IntegrityError(
                "Recovery backup flush failed.", code="transaction_durability_failed"
            )

        for item in reversed(targets):
            target = root / item["path"]
            if target.exists() or target.is_symlink():
                moved = backup / "replaced" / f"{item['index']:04d}"
                moved.parent.mkdir(exist_ok=True)
                _OS_REPLACE(target, moved)
            previous_path = item.get("previous_path")
            if previous_path is not None:
                previous = active / previous_path
                if previous.is_dir():
                    shutil.copytree(previous, target)
                else:
                    shutil.copy2(previous, target)
            if _path_digest(target) != item.get("previous_sha256"):
                raise IntegrityError(
                    "Recovered target does not match previous digest.", code="recovery_failed"
                )
            sync_directory(target.parent)

        recovered = layout["completed"] / f"{transaction_id}-recovered"
        _OS_REPLACE(active, recovered)
        sync_directory(recovered.parent)
        after_digests = [
            {"path": item["path"], "sha256": _path_digest(root / item["path"])} for item in targets
        ]
        now = _now()
        receipt_id = f"RECOVERY-{_stamp(now)}-{uuid4().hex[:12]}"
        receipt = layout["receipts"] / f"{receipt_id}.json"
        value = {
            "action": "ROLL_BACK_TO_PREVIOUS",
            "backup_path": backup.relative_to(root).as_posix(),
            "before_targets": before_digests,
            "completed_at": _timestamp(now),
            "format": RECOVERY_FORMAT,
            "format_version": RECOVERY_VERSION,
            "intent_sha256": intent_sha256,
            "receipt_id": receipt_id,
            "status": "RECOVERED",
            "transaction_id": transaction_id,
            "after_targets": after_digests,
        }
        _write_new(receipt, _json_bytes(value))
    finally:
        for lock in reversed(stale_locks):
            lock.close(remove=True)
    return RecoveryPlan(
        root=root,
        transaction_id=transaction_id,
        intent_sha256=intent_sha256,
        status="RECOVERED",
        action="ROLL_BACK_TO_PREVIOUS",
        targets=tuple(targets),
        backup_path=backup,
        receipt_path=receipt,
    )


def format_recovery_plan(plan: RecoveryPlan, *, applied: bool) -> str:
    lines = [
        f"Workspace recovery: {plan.status}",
        f"Transaction: {plan.transaction_id}",
        f"Intent-SHA-256: {plan.intent_sha256}",
        f"Action: {plan.action}",
        f"Backup: {plan.backup_path.relative_to(plan.root).as_posix()}",
    ]
    for target in plan.targets:
        lines.append(f"- Target: {target['path']} (previous {target['previous_sha256']})")
    if applied:
        if plan.receipt_path is not None:
            lines.append(f"Receipt: {plan.receipt_path.relative_to(plan.root).as_posix()}")
        lines.append("Recovery applied; backup and receipt were retained.")
    else:
        lines.append("Preview only; no workspace data was changed. Add --apply to execute.")
    return "\n".join(lines)
