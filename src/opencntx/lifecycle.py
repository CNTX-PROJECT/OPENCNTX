"""Local trust, storage, cleanup, schema, and migration lifecycle support."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import uuid4

from .contracts import ContractError, validate_durable_record
from .integrity import (
    safe_managed_path,
    sync_directory,
    write_new_bytes,
    writer_transaction,
)
from .primitives import sha256_bytes as _sha256
from .workspace import (
    PRIVACY_LABELS,
    WorkspaceError,
    _derived_storage_bytes,
    _stored_sources,
    load_workspace_config,
    validate_workspace,
)

LIFECYCLE_STATE_FORMAT = "opencntx-lifecycle-state"
LIFECYCLE_STATE_VERSION = 1
LIFECYCLE_PLAN_FORMAT = "opencntx-lifecycle-plan"
LIFECYCLE_PLAN_VERSION = 1
LIFECYCLE_CHECKPOINT_FORMAT = "opencntx-lifecycle-checkpoint"
LIFECYCLE_CHECKPOINT_VERSION = 1
TRUST_PROFILES = ("single-user-local", "shared-team")
AUDIT_RESULTS = ("SAFE_OBSERVED", "WARNING_BROAD_ACCESS", "UNSUPPORTED", "UNSAFE_PATH")
SCHEMA_FILES = (
    "compatibility-matrix-v1.json",
    "durable-format-contracts-v1.json",
    "durable-records-v1.schema.json",
    "lifecycle-plan-v1.schema.json",
    "lifecycle-state-v1.schema.json",
    "public-contract-v1.json",
)
R9_SCHEMA_FILES = (
    "project-definition-v1.schema.json",
    "actor-binding-v1.schema.json",
    "roadmap-definition-v1.schema.json",
    "workstream-binding-v1.schema.json",
    "resource-claim-v1.schema.json",
    "action-envelope-v1.schema.json",
    "runtime-event-v1.schema.json",
    "evidence-v1.schema.json",
    "storage-policy-v1.schema.json",
    "runtime-pointer-v1.schema.json",
    "context-projection-v1.schema.json",
    "sync-receipt-v1.schema.json",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
TRANSACTION_ID_RE = re.compile(r"TXN-\d{8}T\d{12}Z-[0-9a-f]{12}\Z")
RECOVERY_ID_RE = re.compile(r"RECOVERY-\d{8}T\d{12}Z-[0-9a-f]{12}\Z")
MAX_REQUIRED_BYTES = (1 << 63) - 1
_NOW = lambda: datetime.now(UTC)
_TEST_FAULT_HOOK = None


class LifecycleError(WorkspaceError):
    """A stable, user-facing lifecycle failure."""


@dataclass(frozen=True)
class PermissionAudit:
    result: str
    platform: str
    details: tuple[str, ...]


@dataclass(frozen=True)
class DiskPreflight:
    operation: str
    required_bytes: int
    free_bytes: int
    total_bytes: int
    path: Path


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")


def _pretty(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _is_link_like(path: Path) -> bool:
    return path.is_symlink() or _is_reparse(path)


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    if _is_link_like(path) or not path.is_file():
        raise LifecycleError(f"{label} is not a safe regular file.", code="lifecycle_path_unsafe")
    try:
        content = path.read_bytes()
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise LifecycleError(
            f"{label} is invalid or unreadable.", code="lifecycle_record_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise LifecycleError(
            f"{label} must contain a JSON object.", code="lifecycle_record_invalid"
        )
    return value, content


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _write_new(path: Path, content: bytes, *, private: bool = True) -> str:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(path.parent, 0o700)
        result = write_new_bytes(
            path,
            content,
            mode=0o600 if private else 0o666,
            private=private,
            sync_parent=True,
        )
    except OSError as exc:
        raise LifecycleError(
            "Lifecycle evidence could not be written safely.", code="lifecycle_write_failed"
        ) from exc
    if result == "FAILED":
        raise LifecycleError(
            "Lifecycle directory flush failed.", code="lifecycle_durability_failed"
        )
    return result


def _replace_file(path: Path, content: bytes) -> str:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        _write_new(temporary, content)
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
        result = sync_directory(path.parent)
    except BaseException:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise
    if result == "FAILED":
        raise LifecycleError("Lifecycle state flush failed.", code="lifecycle_durability_failed")
    return result


def _schema_bytes(name: str) -> bytes:
    if name not in SCHEMA_FILES:
        raise LifecycleError("Unknown lifecycle schema asset.", code="lifecycle_schema_unknown")
    try:
        return resources.files("opencntx").joinpath("schemas", name).read_bytes()
    except (FileNotFoundError, OSError) as exc:
        raise LifecycleError(
            "Lifecycle schema asset is unavailable.", code="lifecycle_schema_missing"
        ) from exc


def schema_assets() -> dict[str, bytes]:
    """Return exact packaged lifecycle assets."""
    return {name: _schema_bytes(name) for name in SCHEMA_FILES}


def schema_bundle_digest() -> str:
    records = [
        {"name": name, "sha256": _sha256(content)} for name, content in schema_assets().items()
    ]
    return _sha256(_canonical(records))


def r9_schema_assets() -> dict[str, bytes]:
    """Return the opt-in R9 schema assets without changing the Stable bundle."""
    try:
        return {
            name: resources.files("opencntx").joinpath("schemas", name).read_bytes()
            for name in R9_SCHEMA_FILES
        }
    except (FileNotFoundError, OSError) as exc:
        raise LifecycleError(
            "R9 schema asset is unavailable.", code="lifecycle_schema_missing"
        ) from exc


def r9_schema_bundle_digest() -> str:
    """Return one deterministic digest for the isolated R9 schema family."""
    records = [
        {"name": name, "sha256": _sha256(content)} for name, content in r9_schema_assets().items()
    ]
    return _sha256(_canonical(records))


def _compatibility_matrix() -> dict[str, Any]:
    try:
        value = json.loads(
            _schema_bytes("compatibility-matrix-v1.json").decode("ascii"),
            object_pairs_hook=_strict_object,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise LifecycleError(
            "Compatibility matrix is invalid.", code="lifecycle_schema_invalid"
        ) from exc
    if (
        not isinstance(value, dict)
        or value.get("format") != "opencntx-compatibility-matrix"
        or value.get("format_version") != 1
    ):
        raise LifecycleError(
            "Compatibility matrix uses an unknown format.", code="lifecycle_schema_invalid"
        )
    records = value.get("records")
    if not isinstance(records, list):
        raise LifecycleError(
            "Compatibility matrix records are invalid.", code="lifecycle_schema_invalid"
        )
    return value


def compatibility_matrix_digest() -> str:
    return _sha256(_schema_bytes("compatibility-matrix-v1.json"))


def _known_formats() -> dict[tuple[str, int], str]:
    result: dict[tuple[str, int], str] = {}
    for item in _compatibility_matrix()["records"]:
        if not isinstance(item, dict):
            raise LifecycleError("Compatibility entry is invalid.", code="lifecycle_schema_invalid")
        name = item.get("format")
        version = item.get("format_version")
        status = item.get("status")
        if (
            not isinstance(name, str)
            or not isinstance(version, int)
            or status not in {"CURRENT", "LEGACY_READABLE", "MIGRATABLE", "UNSUPPORTED"}
        ):
            raise LifecycleError("Compatibility entry is invalid.", code="lifecycle_schema_invalid")
        key = (name, version)
        if key in result:
            raise LifecycleError(
                "Compatibility matrix contains a duplicate.", code="lifecycle_schema_invalid"
            )
        result[key] = status
    return result


def require_disk_capacity(path: Path, required_bytes: int, operation: str) -> DiskPreflight:
    """Fail before a write when physical free-space evidence is unavailable or insufficient."""
    if (
        not isinstance(required_bytes, int)
        or isinstance(required_bytes, bool)
        or not 0 <= required_bytes <= MAX_REQUIRED_BYTES
    ):
        raise LifecycleError(
            "Required disk bytes are outside the supported range.", code="disk_space_invalid"
        )
    probe = path
    while not probe.exists():
        parent = probe.parent
        if parent == probe:
            raise LifecycleError(
                "Disk-space probe path is unavailable.", code="disk_space_unavailable"
            )
        probe = parent
    if _is_link_like(probe) or not probe.is_dir():
        raise LifecycleError("Disk-space probe path is unsafe.", code="disk_space_unavailable")
    try:
        usage = shutil.disk_usage(probe)
    except OSError as exc:
        raise LifecycleError(
            "Free disk space could not be measured.", code="disk_space_unavailable"
        ) from exc
    if not (
        all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (usage.free, usage.total)
        )
        and 0 <= usage.free <= usage.total <= MAX_REQUIRED_BYTES
    ):
        raise LifecycleError(
            "Free disk space returned invalid values.", code="disk_space_unavailable"
        )
    if usage.free < required_bytes:
        raise LifecycleError(
            f"Insufficient free disk space for {operation}: {usage.free} < {required_bytes} bytes.",
            code="disk_space_insufficient",
        )
    return DiskPreflight(
        operation, required_bytes, usage.free, usage.total, probe.resolve(strict=True)
    )


class _ACL(ctypes.Structure):
    _fields_ = [
        ("AclRevision", ctypes.c_ubyte),
        ("Sbz1", ctypes.c_ubyte),
        ("AclSize", ctypes.c_ushort),
        ("AceCount", ctypes.c_ushort),
        ("Sbz2", ctypes.c_ushort),
    ]


class _ACE_HEADER(ctypes.Structure):
    _fields_ = [
        ("AceType", ctypes.c_ubyte),
        ("AceFlags", ctypes.c_ubyte),
        ("AceSize", ctypes.c_ushort),
    ]


def _windows_sid(text: str) -> ctypes.c_void_p:
    pointer = ctypes.c_void_p()
    convert = vars(ctypes)["windll"].advapi32.ConvertStringSidToSidW
    convert.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]
    convert.restype = ctypes.c_int
    if not convert(text, ctypes.byref(pointer)):
        raise OSError("ConvertStringSidToSidW failed")
    return pointer


def _audit_windows(path: Path, *, private: bool) -> PermissionAudit:
    descriptor = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    broad: list[tuple[str, ctypes.c_void_p]] = []
    try:
        advapi32 = vars(ctypes)["windll"].advapi32
        get_security = advapi32.GetNamedSecurityInfoW
        get_security.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        get_security.restype = ctypes.c_uint32
        result = get_security(
            str(path), 1, 0x00000004, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor)
        )
        if result != 0 or not dacl.value:
            return PermissionAudit(
                "UNSUPPORTED",
                "windows",
                (f"GetNamedSecurityInfoW={result}", "No reliable DACL result."),
            )
        get_control = advapi32.GetSecurityDescriptorControl
        get_control.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ushort),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        get_control.restype = ctypes.c_int
        descriptor_control = ctypes.c_ushort()
        descriptor_revision = ctypes.c_uint32()
        if not get_control(
            descriptor, ctypes.byref(descriptor_control), ctypes.byref(descriptor_revision)
        ):
            return PermissionAudit(
                "UNSUPPORTED", "windows", ("Security descriptor control flags were unavailable.",)
            )
        protection = "protected" if descriptor_control.value & 0x1000 else "inherits-parent-ACL"
        broad = [
            ("Everyone", _windows_sid("S-1-1-0")),
            ("Authenticated Users", _windows_sid("S-1-5-11")),
            ("Builtin Users", _windows_sid("S-1-5-32-545")),
        ]
        compare = advapi32.EqualSid
        compare.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        compare.restype = ctypes.c_int
        get_ace = advapi32.GetAce
        get_ace.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
        get_ace.restype = ctypes.c_int
        acl = ctypes.cast(dacl, ctypes.POINTER(_ACL)).contents
        findings: list[str] = []
        unknown = False
        inherited_aces = 0
        broad_read = 0x80000000 | 0x10000000 | 0x00120089
        broad_write = 0x40000000 | 0x10000000 | 0x00120116 | 0x00010000 | 0x00040000 | 0x00080000
        for index in range(acl.AceCount):
            ace_pointer = ctypes.c_void_p()
            if not get_ace(dacl, index, ctypes.byref(ace_pointer)):
                unknown = True
                continue
            header = ctypes.cast(ace_pointer, ctypes.POINTER(_ACE_HEADER)).contents
            if header.AceFlags & 0x10:
                inherited_aces += 1
            if header.AceType not in (0x00, 0x05):
                if header.AceType in (0x01, 0x06):
                    unknown = True
                continue
            address = cast(int, ace_pointer.value)
            mask = ctypes.c_uint32.from_address(address + 4).value
            sid = ctypes.c_void_p(address + 8)
            for label, broad_sid in broad:
                if compare(sid, broad_sid):
                    if mask & broad_write:
                        findings.append(f"{label} has a broad write-capable allow ACE.")
                    elif private and mask & broad_read:
                        findings.append(
                            f"{label} has a broad read-capable allow ACE on private data."
                        )
        if findings:
            return PermissionAudit(
                "WARNING_BROAD_ACCESS",
                "windows",
                (
                    f"DACL={protection}; inherited ACEs={inherited_aces}.",
                    *tuple(sorted(set(findings))),
                ),
            )
        if unknown:
            return PermissionAudit(
                "UNSUPPORTED",
                "windows",
                (
                    f"DACL={protection}; inherited ACEs={inherited_aces}.",
                    "Unknown or deny ACEs prevent a complete safe observation.",
                ),
            )
        return PermissionAudit(
            "SAFE_OBSERVED",
            "windows",
            (
                f"DACL={protection}; inherited ACEs={inherited_aces}.",
                "Supported DACL entries showed no broad access in the audited scope.",
                "This is not access-control or confidentiality proof.",
            ),
        )
    except (AttributeError, OSError, ValueError):
        return PermissionAudit(
            "UNSUPPORTED", "windows", ("The local Win32 DACL audit was unavailable.",)
        )
    finally:
        local_free = getattr(getattr(ctypes, "windll", None), "kernel32", None)
        if local_free is not None:
            for _, pointer in broad:
                if pointer.value:
                    local_free.LocalFree(pointer)
            if descriptor.value:
                local_free.LocalFree(descriptor)


def audit_permissions(path: Path, *, private: bool = False) -> PermissionAudit:
    """Observe supported local permission facts without mutating them."""
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return PermissionAudit("UNSAFE_PATH", os.name, ("Path is unavailable.",))
    if _is_link_like(path) or not resolved.is_dir():
        return PermissionAudit("UNSAFE_PATH", os.name, ("Path is link-like or not a directory.",))
    if os.name == "nt":
        return _audit_windows(resolved, private=private)
    try:
        mode = stat.S_IMODE(resolved.stat().st_mode)
    except OSError:
        return PermissionAudit("UNSUPPORTED", "posix", ("POSIX mode bits are unavailable.",))
    broad = mode & (0o077 if private else 0o022)
    if broad:
        return PermissionAudit(
            "WARNING_BROAD_ACCESS",
            "posix",
            (f"Observed mode {mode:04o}; disallowed group/other bits {broad:04o}.",),
        )
    return PermissionAudit(
        "SAFE_OBSERVED",
        "posix",
        (
            f"Observed mode {mode:04o} within the audited scope.",
            "This is not access-control or confidentiality proof.",
        ),
    )


def _safe_files(root: Path) -> list[Path]:
    files: list[Path] = []
    managed = [
        "CONTROL",
        "INBOX",
        "SOURCES",
        "CHAPTERS",
        "TASKS",
        "PLAYBOOKS",
        "ROLES",
        ".opencntx",
    ]
    for name in managed:
        top = root / name
        if not top.exists():
            continue
        if _is_link_like(top) or not top.is_dir():
            raise LifecycleError(
                "Managed storage contains an unsafe top-level path.", code="lifecycle_path_unsafe"
            )
        for current_text, directories, names in os.walk(top, topdown=True, followlinks=False):
            current = Path(current_text)
            safe_directories: list[str] = []
            for directory_name in sorted(directories):
                candidate = current / directory_name
                if _is_link_like(candidate) or not candidate.is_dir():
                    raise LifecycleError(
                        "Managed storage contains a link-like directory.",
                        code="lifecycle_path_unsafe",
                    )
                safe_directories.append(directory_name)
            directories[:] = safe_directories
            for file_name in sorted(names):
                candidate = current / file_name
                if _is_link_like(candidate) or not candidate.is_file():
                    raise LifecycleError(
                        "Managed storage contains an unsafe entry.", code="lifecycle_path_unsafe"
                    )
                files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _storage_category(relative: str) -> str:
    if relative.startswith("SOURCES/"):
        return "source_content"
    if relative.startswith(".opencntx/derived/"):
        return "derived_content"
    if relative == ".opencntx/catalog.sqlite" or relative.startswith(".opencntx/latest/"):
        return "generated_packages_and_catalog"
    if relative.startswith((".opencntx/receipts/", "CONTROL/")):
        return "receipts_and_control"
    if relative.startswith(("TASKS/", "PLAYBOOKS/", "ROLES/", ".opencntx/executors/")):
        return "tasks_definitions_and_executors"
    if relative.startswith((".opencntx/transactions/", ".opencntx/recovery/")):
        return "transactions_and_recovery"
    if relative.startswith(".opencntx/lifecycle/"):
        return "lifecycle_checkpoints_and_state"
    return "other_managed_regular_bytes"


def storage_inventory(project_root: Path) -> dict[str, Any]:
    root = validate_workspace(project_root)
    categories = {
        "source_content": 0,
        "derived_content": 0,
        "generated_packages_and_catalog": 0,
        "receipts_and_control": 0,
        "tasks_definitions_and_executors": 0,
        "transactions_and_recovery": 0,
        "lifecycle_checkpoints_and_state": 0,
        "other_managed_regular_bytes": 0,
    }
    for path in _safe_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise LifecycleError(
                "Managed storage changed during measurement.", code="lifecycle_storage_changed"
            ) from exc
        categories[_storage_category(relative)] += size
    config = load_workspace_config(root)
    usage = require_disk_capacity(root, 0, "lifecycle-status")
    return {
        "budgeted_content_bytes": sum(
            source.byte_count for source in _stored_sources(root).values()
        )
        + _derived_storage_bytes(root),
        "categories": categories,
        "configured_max_storage_bytes": config.max_storage_bytes,
        "free_bytes": usage.free_bytes,
        "observed_total_bytes": sum(categories.values()),
        "total_bytes": usage.total_bytes,
    }


def _record_inventory(root: Path) -> list[dict[str, Any]]:
    known = _known_formats()
    records: list[dict[str, Any]] = []
    for path in _safe_files(root):
        relative = path.relative_to(root).as_posix()
        if not relative.endswith(".json") or relative.startswith(
            (
                ".opencntx/lifecycle/",
                ".opencntx/transactions/locks/",
                ".opencntx/transactions/active/",
            )
        ):
            continue
        value, content = _read_json(path, label=relative)
        if "format" not in value:
            continue
        format_name = value.get("format")
        version = value.get("format_version")
        if not isinstance(format_name, str) or not isinstance(version, int):
            raise LifecycleError(
                "Durable record has an invalid format discriminator.",
                code="lifecycle_record_unsupported",
            )
        status = known.get((format_name, version), "UNSUPPORTED")
        if status == "UNSUPPORTED":
            raise LifecycleError(
                f"Unsupported durable record format: {format_name} v{version}.",
                code="lifecycle_record_unsupported",
            )
        try:
            validate_durable_record(value)
        except ContractError as exc:
            if exc.code == "contract_version_unsupported":
                code = "lifecycle_record_unsupported"
            else:
                code = "lifecycle_record_invalid"
            raise LifecycleError(str(exc), code=code) from exc
        records.append(
            {
                "format": format_name,
                "format_version": version,
                "path": relative,
                "sha256": _sha256(content),
                "status": status,
            }
        )
    return records


def _inventory_digest(records: Sequence[dict[str, Any]]) -> str:
    return _sha256(_canonical(list(records)))


def _validate_current_workspace(root: Path) -> None:
    """Run existing domain readers before registering current durable bytes."""
    load_workspace_config(root)
    sources = _stored_sources(root)
    from .catalog import _load_chapters, _load_sources
    from .integrity import doctor_workspace
    from .media import _load_derivations
    from .playbook import _load_assignment, _load_definition
    from .workflow import _load_chain

    _load_sources(root)
    _load_chapters(root)
    for source_id in sorted(sources):
        _load_derivations(root, source_id)
    tasks = root / "TASKS"
    for path in sorted(tasks.iterdir(), key=lambda item: item.name):
        if _is_link_like(path) or not path.is_dir():
            raise LifecycleError(
                "Task storage contains an unsafe entry.", code="lifecycle_record_invalid"
            )
        _load_chain(root, path.name)
    for definition_type, directory_name in (("PLAYBOOK", "PLAYBOOKS"), ("ROLE", "ROLES")):
        definitions = root / directory_name
        for identifier in sorted(definitions.iterdir(), key=lambda item: item.name):
            if _is_link_like(identifier) or not identifier.is_dir():
                raise LifecycleError(
                    "Definition storage contains an unsafe entry.", code="lifecycle_record_invalid"
                )
            for revision in sorted(identifier.iterdir(), key=lambda item: item.name):
                if (
                    _is_link_like(revision)
                    or not revision.is_dir()
                    or not revision.name.startswith("REV-")
                ):
                    raise LifecycleError(
                        "Definition revision storage is invalid.", code="lifecycle_record_invalid"
                    )
                try:
                    number = int(revision.name.removeprefix("REV-"))
                except ValueError as exc:
                    raise LifecycleError(
                        "Definition revision is invalid.", code="lifecycle_record_invalid"
                    ) from exc
                _load_definition(root, definition_type, identifier.name, number)
    executors = root / ".opencntx" / "executors"
    if executors.exists():
        if _is_link_like(executors) or not executors.is_dir():
            raise LifecycleError("Executor storage is unsafe.", code="lifecycle_record_invalid")
        for task_directory in sorted(executors.iterdir(), key=lambda item: item.name):
            if _is_link_like(task_directory) or not task_directory.is_dir():
                raise LifecycleError(
                    "Executor task storage is unsafe.", code="lifecycle_record_invalid"
                )
            for assignment in sorted(task_directory.iterdir(), key=lambda item: item.name):
                if _is_link_like(assignment) or not assignment.is_dir():
                    raise LifecycleError(
                        "Executor assignment storage is unsafe.", code="lifecycle_record_invalid"
                    )
                _load_assignment(root, task_directory.name, assignment.name)
    report = doctor_workspace(root)
    if not report.ok:
        raise LifecycleError(
            "Transaction diagnosis must be clean before migration.",
            code="lifecycle_migration_blocked",
        )
    latest = root / ".opencntx" / "latest"
    if latest.exists() or latest.is_symlink():
        from .core import verify_package

        package_report = verify_package(latest)
        if not package_report.ok:
            raise LifecycleError(
                "Current context package does not verify.", code="lifecycle_migration_blocked"
            )


def _state_value(root: Path, records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "format": LIFECYCLE_STATE_FORMAT,
        "format_version": LIFECYCLE_STATE_VERSION,
        "inventory_sha256": _inventory_digest(records),
        "record_count": len(records),
        "schema_bundle_sha256": schema_bundle_digest(),
        "trust_statement": "local-observation-not-access-control",
    }


def initialize_lifecycle_state(project_root: Path) -> Path:
    """Create lifecycle-state v1 while an enclosing workspace initialization is still staged."""
    root = validate_workspace(project_root)
    state = root / ".opencntx" / "lifecycle" / "state.json"
    if state.exists() or state.is_symlink():
        raise LifecycleError("Lifecycle state already exists.", code="lifecycle_state_exists")
    records = _record_inventory(root)
    _write_new(state, _pretty(_state_value(root, records)))
    return state


def _load_state(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = root / ".opencntx" / "lifecycle" / "state.json"
    if not path.exists() and not path.is_symlink():
        return None, None
    value, content = _read_json(path, label="lifecycle state")
    required = {
        "format",
        "format_version",
        "inventory_sha256",
        "record_count",
        "schema_bundle_sha256",
        "trust_statement",
    }
    if (
        set(value) != required
        or value.get("format") != LIFECYCLE_STATE_FORMAT
        or value.get("format_version") != 1
    ):
        raise LifecycleError(
            "Lifecycle state uses an unknown contract.", code="lifecycle_state_invalid"
        )
    if not isinstance(value.get("record_count"), int) or not isinstance(
        value.get("inventory_sha256"), str
    ):
        raise LifecycleError("Lifecycle state is invalid.", code="lifecycle_state_invalid")
    return value, _sha256(content)


def lifecycle_status(project_root: Path, trust_profile: str) -> dict[str, Any]:
    root = validate_workspace(project_root)
    if trust_profile not in TRUST_PROFILES:
        raise LifecycleError("Unknown trust profile.", code="lifecycle_trust_profile_invalid")
    before = [(path, path.stat().st_mtime_ns, path.stat().st_size) for path in _safe_files(root)]
    sources = _stored_sources(root)
    privacy = {label: 0 for label in PRIVACY_LABELS}
    source_evidence: list[dict[str, str]] = []
    for source in sources.values():
        privacy[source.privacy] += 1
        source_evidence.append(
            {
                "alias": "SRC-ALIAS-"
                + hashlib.sha256(source.source_id.encode("ascii")).hexdigest()[:12],
                "content_sha256": source.sha256,
                "record_sha256": _sha256(source.record_path.read_bytes()),
            }
        )
    root_audit = audit_permissions(root)
    private_audit = audit_permissions(root / ".opencntx", private=True)
    state, state_digest = _load_state(root)
    storage = storage_inventory(root)
    after = [(path, path.stat().st_mtime_ns, path.stat().st_size) for path in _safe_files(root)]
    if before != after:
        raise LifecycleError(
            "Workspace changed during read-only lifecycle status.", code="lifecycle_status_changed"
        )
    trust_status = (
        "LOCAL_ASSUMPTION_ONLY"
        if trust_profile == "single-user-local"
        else "UNSUPPORTED_FOR_AUTHORIZATION"
    )
    return {
        "sources": sorted(source_evidence, key=lambda item: item["alias"]),
        "permission_audit": {
            "private": {
                "details": list(private_audit.details),
                "platform": private_audit.platform,
                "result": private_audit.result,
            },
            "root": {
                "details": list(root_audit.details),
                "platform": root_audit.platform,
                "result": root_audit.result,
            },
        },
        "privacy_counts": privacy,
        "publication_warning": "Privacy labels do not encrypt, authenticate, authorize, control access, or grant permission to share.",
        "state": "CURRENT"
        if state is not None and state.get("schema_bundle_sha256") == schema_bundle_digest()
        else "LEGACY_UNREGISTERED",
        "state_sha256": state_digest,
        "storage": storage,
        "trust_profile": trust_profile,
        "trust_status": trust_status,
    }


def format_lifecycle_status(report: dict[str, Any]) -> str:
    storage = report["storage"]
    private = report["permission_audit"]["private"]
    lines = [
        f"Lifecycle status: {report['state']}",
        f"Trust profile: {report['trust_profile']} ({report['trust_status']})",
        f"Permission audit: {private['result']} ({private['platform']})",
        f"Observed storage: {storage['observed_total_bytes']} bytes",
        f"Budgeted content: {storage['budgeted_content_bytes']} / {storage['configured_max_storage_bytes']} bytes",
        f"Disk free: {storage['free_bytes']} / {storage['total_bytes']} bytes",
        "Privacy labels: "
        + ", ".join(f"{key}={value}" for key, value in sorted(report["privacy_counts"].items())),
        *[
            f"Source {item['alias']}: content={item['content_sha256']} record={item['record_sha256']}"
            for item in report["sources"]
        ],
        report["publication_warning"],
        "Permission and digest observations are local evidence, not identity, confidentiality, or access-control proof.",
    ]
    return "\n".join(lines)


def _plan_digest(plan: dict[str, Any]) -> str:
    value = dict(plan)
    value.pop("plan_sha256", None)
    return _sha256(_canonical(value))


def _finalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    result = dict(plan)
    result["plan_sha256"] = _plan_digest(result)
    return result


def plan_migration(project_root: Path) -> dict[str, Any]:
    root = validate_workspace(project_root)
    _validate_current_workspace(root)
    state, state_sha = _load_state(root)
    records = _record_inventory(root)
    if state is not None:
        operation = "ALREADY_CURRENT"
        target = state
    else:
        operation = "REGISTER_UNCHANGED_V1"
        target = _state_value(root, records)
    return _finalize_plan(
        {
            "basis_inventory_sha256": _inventory_digest(records),
            "compatibility_matrix_sha256": compatibility_matrix_digest(),
            "format": LIFECYCLE_PLAN_FORMAT,
            "format_version": LIFECYCLE_PLAN_VERSION,
            "operation": operation,
            "record_count": len(records),
            "records": records,
            "schema_bundle_sha256": schema_bundle_digest(),
            "state_before_sha256": state_sha,
            "target_state": target,
        }
    )


def format_migration_plan(plan: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Lifecycle migration: {plan['operation']}",
            f"Records: {plan['record_count']}",
            f"Inventory-SHA-256: {plan['basis_inventory_sha256']}",
            f"Plan-SHA-256: {plan['plan_sha256']}",
            "Dry-run only unless --apply and the exact plan digest are supplied.",
        ]
    )


def write_plan(path: Path, plan: dict[str, Any], *, workspace_root: Path | None = None) -> str:
    if plan.get("plan_sha256") != _plan_digest(plan):
        raise LifecycleError("Plan digest is invalid.", code="lifecycle_plan_invalid")
    requested = path.absolute()
    if requested.exists() or requested.is_symlink():
        raise LifecycleError(
            "Plan destination must be a new regular file.", code="lifecycle_plan_path_invalid"
        )
    if workspace_root is not None:
        root = workspace_root.resolve(strict=True)
        try:
            requested.relative_to(root)
        except ValueError:
            pass
        else:
            raise LifecycleError(
                "Plan file must remain outside the workspace.", code="lifecycle_plan_path_invalid"
            )
    _write_new(requested, _pretty(plan))
    return str(plan["plan_sha256"])


def _load_exact_plan(path: Path, expected_sha256: str) -> dict[str, Any]:
    if SHA256_RE.fullmatch(expected_sha256) is None:
        raise LifecycleError("Plan SHA-256 is invalid.", code="lifecycle_plan_digest_invalid")
    value, _ = _read_json(path.absolute(), label="lifecycle plan")
    actual = _plan_digest(value)
    if actual != expected_sha256 or value.get("plan_sha256") != expected_sha256:
        raise LifecycleError(
            "Lifecycle plan digest does not match.", code="lifecycle_plan_digest_mismatch"
        )
    if value.get("format") != LIFECYCLE_PLAN_FORMAT or value.get("format_version") != 1:
        raise LifecycleError(
            "Lifecycle plan uses an unknown format.", code="lifecycle_plan_invalid"
        )
    return value


def apply_migration(project_root: Path, plan_path: Path, plan_sha256: str) -> dict[str, Any]:
    root = validate_workspace(project_root)
    plan = _load_exact_plan(plan_path, plan_sha256)
    if plan.get("operation") != "REGISTER_UNCHANGED_V1":
        raise LifecycleError(
            "Migration plan has no applicable migration.", code="lifecycle_migration_not_applicable"
        )
    current = plan_migration(root)
    if current.get("plan_sha256") != plan_sha256:
        raise LifecycleError("Migration basis changed.", code="lifecycle_plan_stale")
    require_disk_capacity(
        root,
        len(_pretty(plan["target_state"])) * 2 + 16 * 1024,
        "lifecycle-migrate",
    )
    state_path = root / ".opencntx" / "lifecycle" / "state.json"
    expected = str(plan["basis_inventory_sha256"])

    def current_digest() -> str:
        return _inventory_digest(_record_inventory(root))

    with writer_transaction(
        root, "lifecycle-migrate", expected_digest=expected, current_digest=current_digest
    ) as transaction:
        transaction.track_target(state_path)
        if _TEST_FAULT_HOOK is not None:
            _TEST_FAULT_HOOK("MIGRATION_BEFORE_STATE")
        _write_new(state_path, _pretty(plan["target_state"]))
        transaction.mark_target_published(state_path)
        transaction.mark_published()
        if _TEST_FAULT_HOOK is not None:
            _TEST_FAULT_HOOK("MIGRATION_AFTER_STATE")
        transaction.mark_receipted(None)
    return {"status": "MIGRATED", "plan_sha256": plan_sha256, "state_path": state_path}


def _path_digest(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "ABSENT"
    if _is_link_like(path):
        raise LifecycleError("Lifecycle target is link-like.", code="lifecycle_path_unsafe")
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(b"F\0")
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    if not path.is_dir():
        raise LifecycleError(
            "Lifecycle target has an unsupported type.", code="lifecycle_path_unsafe"
        )
    digest.update(b"D\0")
    for candidate in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        if _is_link_like(candidate):
            raise LifecycleError(
                "Lifecycle target contains a link-like entry.", code="lifecycle_path_unsafe"
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
            raise LifecycleError(
                "Lifecycle target contains an unsupported entry.", code="lifecycle_path_unsafe"
            )
    return digest.hexdigest()


def _path_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for candidate in path.rglob("*"):
        if _is_link_like(candidate):
            raise LifecycleError(
                "Lifecycle target contains a link-like entry.", code="lifecycle_path_unsafe"
            )
        if candidate.is_file():
            total += candidate.stat().st_size
        elif not candidate.is_dir():
            raise LifecycleError(
                "Lifecycle target contains an unsupported entry.", code="lifecycle_path_unsafe"
            )
    return total


def _read_manifest_digest(root: Path) -> str:
    manifest = safe_managed_path(
        root, ".opencntx/latest/manifest.json", must_exist=True, kind="file"
    )
    return _sha256(manifest.read_bytes())


def _latest_is_bound(root: Path, manifest_digest: str) -> bool:
    executor_root = root / ".opencntx" / "executors"
    if not executor_root.exists():
        return False
    if _is_link_like(executor_root) or not executor_root.is_dir():
        raise LifecycleError("Executor storage is unsafe.", code="lifecycle_cleanup_blocked")
    for path in sorted(executor_root.rglob("*.json")):
        value, _ = _read_json(path, label="executor record")
        if value.get("format") == "opencntx-executor-assignment":
            context = value.get("context")
            if isinstance(context, dict) and context.get("manifest_digest") == manifest_digest:
                return True
    manifest, _ = _read_json(
        root / ".opencntx" / "latest" / "manifest.json", label="latest package manifest"
    )
    navigation = manifest.get("navigation")
    task = navigation.get("task") if isinstance(navigation, dict) else None
    task_id = task.get("task_id") if isinstance(task, dict) else None
    if isinstance(task_id, str):
        from .workflow import _load_chain

        chain = _load_chain(root, task_id)
        if chain.status not in {"CLOSED", "CANCELLED", "SUPERSEDED"}:
            return True
    return False


def _cleanup_target(root: Path, target: str) -> tuple[str, Path]:
    if target == "latest-package":
        path = safe_managed_path(root, ".opencntx/latest", must_exist=True, kind="directory")
        from .core import verify_package

        report = verify_package(path)
        if not report.ok:
            raise LifecycleError(
                "Latest package does not fully verify.", code="lifecycle_cleanup_blocked"
            )
        if _latest_is_bound(root, _read_manifest_digest(root)):
            raise LifecycleError(
                "Latest package is bound by an executor record.", code="lifecycle_cleanup_blocked"
            )
        return "latest-package", path
    if target == "catalog-cache":
        from .catalog import _load_chapters, _load_sources

        _load_sources(root)
        _load_chapters(root)
        path = safe_managed_path(root, ".opencntx/catalog.sqlite", must_exist=True, kind="file")
        try:
            header = path.read_bytes()[:16]
        except OSError as exc:
            raise LifecycleError(
                "Catalog cache is unreadable.", code="lifecycle_cleanup_blocked"
            ) from exc
        if header != b"SQLite format 3\x00":
            raise LifecycleError("Catalog cache is invalid.", code="lifecycle_cleanup_blocked")
        return "catalog-cache", path
    if target.startswith("completed-transaction:"):
        transaction_id = target.split(":", 1)[1]
        if TRANSACTION_ID_RE.fullmatch(transaction_id) is None:
            raise LifecycleError(
                "Completed transaction ID is invalid.", code="lifecycle_cleanup_target_invalid"
            )
        path = safe_managed_path(
            root,
            f".opencntx/transactions/completed/{transaction_id}",
            must_exist=True,
            kind="directory",
        )
        intent, _ = _read_json(path / "intent.json", label="completed transaction intent")
        completion, _ = _read_json(
            path / "completion.json", label="completed transaction completion"
        )
        if (
            intent.get("format") != "opencntx-transaction"
            or intent.get("transaction_id") != transaction_id
        ):
            raise LifecycleError(
                "Completed transaction intent is invalid.", code="lifecycle_cleanup_blocked"
            )
        if (
            completion.get("format") != "opencntx-transaction-completion"
            or completion.get("transaction_id") != transaction_id
        ):
            raise LifecycleError(
                "Completed transaction completion is invalid.", code="lifecycle_cleanup_blocked"
            )
        return "completed-transaction", path
    if target.startswith("recovery-backup:"):
        recovery_id = target.split(":", 1)[1]
        if RECOVERY_ID_RE.fullmatch(recovery_id) is None:
            raise LifecycleError(
                "Recovery backup ID is invalid.", code="lifecycle_cleanup_target_invalid"
            )
        path = safe_managed_path(
            root, f".opencntx/recovery/backups/{recovery_id}", must_exist=True, kind="directory"
        )
        manifest, _ = _read_json(path / "manifest.json", label="recovery backup manifest")
        if (
            manifest.get("format") != "opencntx-recovery-backup"
            or manifest.get("backup_id") != recovery_id
        ):
            raise LifecycleError(
                "Recovery backup manifest is invalid.", code="lifecycle_cleanup_blocked"
            )
        recovery_transaction_id = manifest.get("transaction_id")
        intent_sha256 = manifest.get("intent_sha256")
        if (
            not isinstance(recovery_transaction_id, str)
            or TRANSACTION_ID_RE.fullmatch(recovery_transaction_id) is None
            or SHA256_RE.fullmatch(str(intent_sha256)) is None
        ):
            raise LifecycleError(
                "Recovery backup binding is invalid.", code="lifecycle_cleanup_blocked"
            )
        completed = safe_managed_path(
            root,
            f".opencntx/transactions/completed/{recovery_transaction_id}-recovered",
            must_exist=True,
            kind="directory",
        )
        completed_intent, completed_intent_bytes = _read_json(
            completed / "intent.json",
            label="recovered transaction intent",
        )
        if (
            completed_intent.get("transaction_id") != recovery_transaction_id
            or _sha256(completed_intent_bytes) != intent_sha256
        ):
            raise LifecycleError(
                "Recovery backup has no exact completed transaction binding.",
                code="lifecycle_cleanup_blocked",
            )
        bound = False
        receipt_root = root / ".opencntx" / "receipts"
        for receipt in sorted(receipt_root.glob("*.json")):
            value, _ = _read_json(receipt, label="recovery receipt")
            if (
                value.get("format") == "opencntx-recovery-receipt"
                and value.get("backup_path") == path.relative_to(root).as_posix()
                and value.get("transaction_id") == recovery_transaction_id
                and value.get("intent_sha256") == intent_sha256
            ):
                bound = True
                break
        if not bound:
            raise LifecycleError(
                "Recovery backup has no exact recovery receipt.", code="lifecycle_cleanup_blocked"
            )
        return "recovery-backup", path
    raise LifecycleError(
        "Cleanup target is outside the fixed allowlist.", code="lifecycle_cleanup_target_invalid"
    )


def _checkpoint_path(root: Path, checkpoint: Path) -> Path:
    requested = checkpoint.absolute()
    try:
        resolved_root = root.resolve(strict=True)
        compare = requested.resolve(strict=False)
        compare.relative_to(resolved_root)
    except ValueError:
        pass
    except OSError as exc:
        raise LifecycleError(
            "Checkpoint path is unavailable.", code="lifecycle_checkpoint_invalid"
        ) from exc
    else:
        raise LifecycleError(
            "Checkpoint must remain outside the workspace.", code="lifecycle_checkpoint_invalid"
        )
    if requested.is_symlink() or _is_reparse(requested):
        raise LifecycleError("Checkpoint path is link-like.", code="lifecycle_checkpoint_invalid")
    if requested.exists():
        if not requested.is_dir() or any(requested.iterdir()):
            raise LifecycleError(
                "Checkpoint must be new or empty.", code="lifecycle_checkpoint_invalid"
            )
    else:
        parent = requested.parent
        if _is_link_like(parent) or not parent.is_dir():
            raise LifecycleError(
                "Checkpoint parent is unsafe.", code="lifecycle_checkpoint_invalid"
            )
    return requested


def plan_cleanup(project_root: Path, targets: Sequence[str], checkpoint: Path) -> dict[str, Any]:
    root = validate_workspace(project_root)
    if not targets:
        raise LifecycleError(
            "At least one explicit cleanup target is required.",
            code="lifecycle_cleanup_target_invalid",
        )
    if len(set(targets)) != len(targets):
        raise LifecycleError(
            "Cleanup targets must be unique.", code="lifecycle_cleanup_target_invalid"
        )
    checkpoint_path = _checkpoint_path(root, checkpoint)
    records: list[dict[str, Any]] = []
    for target in sorted(targets):
        kind, path = _cleanup_target(root, target)
        records.append(
            {
                "bytes": _path_bytes(path),
                "kind": kind,
                "path": path.relative_to(root).as_posix(),
                "sha256": _path_digest(path),
                "target": target,
            }
        )
    required = sum(int(item["bytes"]) for item in records) + len(_pretty(records)) + 4096
    require_disk_capacity(checkpoint_path.parent, required, "lifecycle-cleanup-checkpoint")
    return _finalize_plan(
        {
            "basis_targets_sha256": _sha256(_canonical(records)),
            "checkpoint": str(checkpoint_path),
            "checkpoint_required_bytes": required,
            "compatibility_matrix_sha256": compatibility_matrix_digest(),
            "format": LIFECYCLE_PLAN_FORMAT,
            "format_version": LIFECYCLE_PLAN_VERSION,
            "operation": "CLEANUP_EXPLICIT_TARGETS",
            "schema_bundle_sha256": schema_bundle_digest(),
            "targets": records,
        }
    )


def format_cleanup_plan(plan: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Lifecycle cleanup: PREVIEW",
            f"Targets: {len(plan['targets'])}",
            f"Checkpoint bytes required: {plan['checkpoint_required_bytes']}",
            f"Plan-SHA-256: {plan['plan_sha256']}",
            "Nothing was removed. Apply requires this exact plan and digest.",
        ]
    )


def _copy_target(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _remove_target(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def apply_cleanup(project_root: Path, plan_path: Path, plan_sha256: str) -> dict[str, Any]:
    root = validate_workspace(project_root)
    plan = _load_exact_plan(plan_path, plan_sha256)
    if plan.get("operation") != "CLEANUP_EXPLICIT_TARGETS" or not isinstance(
        plan.get("targets"), list
    ):
        raise LifecycleError("Cleanup plan operation is invalid.", code="lifecycle_plan_invalid")
    checkpoint = _checkpoint_path(root, Path(str(plan.get("checkpoint"))))
    current_records: list[dict[str, Any]] = []
    for expected in plan["targets"]:
        if not isinstance(expected, dict) or not isinstance(expected.get("target"), str):
            raise LifecycleError("Cleanup target record is invalid.", code="lifecycle_plan_invalid")
        kind, path = _cleanup_target(root, expected["target"])
        current = {
            "bytes": _path_bytes(path),
            "kind": kind,
            "path": path.relative_to(root).as_posix(),
            "sha256": _path_digest(path),
            "target": expected["target"],
        }
        if current != expected:
            raise LifecycleError("Cleanup basis changed.", code="lifecycle_plan_stale")
        current_records.append(current)
    if _sha256(_canonical(current_records)) != plan.get("basis_targets_sha256"):
        raise LifecycleError("Cleanup target basis is invalid.", code="lifecycle_plan_stale")
    require_disk_capacity(
        checkpoint.parent, int(plan["checkpoint_required_bytes"]), "lifecycle-cleanup-checkpoint"
    )

    def current_digest() -> str:
        values = []
        for item in current_records:
            path = safe_managed_path(root, item["path"], must_exist=True)
            values.append({**item, "bytes": _path_bytes(path), "sha256": _path_digest(path)})
        return _sha256(_canonical(values))

    expected_digest = _sha256(_canonical(current_records))
    manifest_path = checkpoint / "manifest.json"
    flush_status = "UNSUPPORTED"
    with writer_transaction(
        root, "lifecycle-cleanup", expected_digest=expected_digest, current_digest=current_digest
    ) as transaction:
        try:
            checkpoint.mkdir(mode=0o700)
            if os.name != "nt":
                os.chmod(checkpoint, 0o700)
            checkpoint_audit = audit_permissions(checkpoint, private=True)
            if checkpoint_audit.result != "SAFE_OBSERVED":
                raise LifecycleError(
                    "Checkpoint permission audit is not safely observed.",
                    code="lifecycle_checkpoint_permissions",
                )
            data = checkpoint / "data"
            data.mkdir(mode=0o700)
            if os.name != "nt":
                os.chmod(data, 0o700)
            copied: list[dict[str, Any]] = []
            for index, item in enumerate(current_records):
                source = safe_managed_path(root, item["path"], must_exist=True)
                destination = data / f"{index:04d}"
                _copy_target(source, destination)
                if _path_digest(destination) != item["sha256"]:
                    raise LifecycleError(
                        "Checkpoint copy digest differs.", code="lifecycle_checkpoint_failed"
                    )
                copied.append({**item, "checkpoint_path": f"data/{index:04d}"})
            if _TEST_FAULT_HOOK is not None:
                _TEST_FAULT_HOOK("CLEANUP_AFTER_COPY")
            manifest = {
                "checkpoint_id": "CHECKPOINT-" + plan_sha256[:24],
                "completed_at": _timestamp(_NOW()),
                "directory_flush": "PENDING",
                "format": LIFECYCLE_CHECKPOINT_FORMAT,
                "format_version": LIFECYCLE_CHECKPOINT_VERSION,
                "plan_sha256": plan_sha256,
                "targets": copied,
            }
            _write_new(manifest_path, _pretty(manifest))
            flush_status = sync_directory(checkpoint)
            if flush_status == "FAILED":
                raise LifecycleError(
                    "Checkpoint directory flush failed.", code="lifecycle_durability_failed"
                )
            manifest["directory_flush"] = flush_status
            _replace_file(manifest_path, _pretty(manifest))
            if _TEST_FAULT_HOOK is not None:
                _TEST_FAULT_HOOK("CLEANUP_BEFORE_REMOVE")
            removed: list[tuple[Path, Path]] = []
            try:
                for index, item in enumerate(current_records):
                    source = safe_managed_path(root, item["path"], must_exist=True)
                    backup = data / f"{index:04d}"
                    _remove_target(source)
                    sync_directory(source.parent)
                    removed.append((source, backup))
                    if _TEST_FAULT_HOOK is not None:
                        _TEST_FAULT_HOOK("CLEANUP_AFTER_REMOVE")
            except BaseException:
                for source, backup in reversed(removed):
                    if not source.exists():
                        _copy_target(backup, source)
                raise
            transaction.mark_published()
            transaction.mark_receipted(None)
        except BaseException:
            if checkpoint.exists() and not manifest_path.exists():
                shutil.rmtree(checkpoint, ignore_errors=True)
            raise
    checkpoint_sha256 = _sha256(manifest_path.read_bytes())
    return {
        "checkpoint": checkpoint,
        "checkpoint_sha256": checkpoint_sha256,
        "directory_flush": flush_status,
        "plan_sha256": plan_sha256,
        "status": "CLEANED_WITH_CHECKPOINT",
    }


def restore_cleanup(project_root: Path, checkpoint: Path, checkpoint_sha256: str) -> dict[str, Any]:
    root = validate_workspace(project_root)
    if SHA256_RE.fullmatch(checkpoint_sha256) is None:
        raise LifecycleError("Checkpoint SHA-256 is invalid.", code="lifecycle_checkpoint_invalid")
    checkpoint_path = checkpoint.resolve(strict=True)
    if _is_link_like(checkpoint_path) or not checkpoint_path.is_dir():
        raise LifecycleError("Checkpoint path is unsafe.", code="lifecycle_checkpoint_invalid")
    checkpoint_audit = audit_permissions(checkpoint_path, private=True)
    if checkpoint_audit.result != "SAFE_OBSERVED":
        raise LifecycleError(
            "Checkpoint permission audit is not safely observed.",
            code="lifecycle_checkpoint_permissions",
        )
    try:
        checkpoint_path.relative_to(root)
    except ValueError:
        pass
    else:
        raise LifecycleError(
            "Checkpoint must remain outside the workspace.", code="lifecycle_checkpoint_invalid"
        )
    manifest_path = checkpoint_path / "manifest.json"
    value, content = _read_json(manifest_path, label="lifecycle checkpoint")
    if _sha256(content) != checkpoint_sha256:
        raise LifecycleError(
            "Checkpoint digest does not match.", code="lifecycle_checkpoint_digest_mismatch"
        )
    if (
        value.get("format") != LIFECYCLE_CHECKPOINT_FORMAT
        or value.get("format_version") != 1
        or not isinstance(value.get("targets"), list)
    ):
        raise LifecycleError("Checkpoint manifest is invalid.", code="lifecycle_checkpoint_invalid")
    restore_bytes = 0
    for item in value["targets"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("checkpoint_path"), str)
        ):
            raise LifecycleError(
                "Checkpoint target record is invalid.", code="lifecycle_checkpoint_invalid"
            )
        target = safe_managed_path(root, item["path"])
        if target.exists() or target.is_symlink():
            raise LifecycleError(
                "Restore target already exists.", code="lifecycle_restore_conflict"
            )
        backup = checkpoint_path / PurePosixPath(item["checkpoint_path"])
        if (
            _is_link_like(backup)
            or not backup.exists()
            or _path_digest(backup) != item.get("sha256")
        ):
            raise LifecycleError(
                "Checkpoint bytes do not verify.", code="lifecycle_checkpoint_invalid"
            )
        restore_bytes += _path_bytes(backup)

    require_disk_capacity(root, restore_bytes * 2 + 16 * 1024, "lifecycle-restore")

    expected = _sha256(
        _canonical([{"path": item["path"], "sha256": "ABSENT"} for item in value["targets"]])
    )

    def current_digest() -> str:
        return _sha256(
            _canonical(
                [
                    {
                        "path": item["path"],
                        "sha256": _path_digest(root / PurePosixPath(item["path"])),
                    }
                    for item in value["targets"]
                ]
            )
        )

    with writer_transaction(
        root, "lifecycle-restore", expected_digest=expected, current_digest=current_digest
    ) as transaction:
        restored: list[Path] = []
        try:
            for item in value["targets"]:
                target = safe_managed_path(root, item["path"])
                backup = checkpoint_path / PurePosixPath(item["checkpoint_path"])
                _copy_target(backup, target)
                if _path_digest(target) != item["sha256"]:
                    raise LifecycleError(
                        "Restored bytes do not verify.", code="lifecycle_restore_failed"
                    )
                sync_directory(target.parent)
                restored.append(target)
                if _TEST_FAULT_HOOK is not None:
                    _TEST_FAULT_HOOK("RESTORE_AFTER_COPY")
            transaction.mark_published()
            transaction.mark_receipted(None)
        except BaseException:
            for target in reversed(restored):
                if target.exists():
                    _remove_target(target)
            raise
    return {
        "status": "RESTORED",
        "checkpoint_sha256": checkpoint_sha256,
        "target_count": len(value["targets"]),
    }
