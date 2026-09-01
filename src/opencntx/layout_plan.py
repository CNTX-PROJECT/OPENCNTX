"""Deterministic, read-only, digest-bound layout migration planning."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import schema_identifier
from .core import OpenCntxError

MANIFEST_FORMAT = "opencntx-layout-migration"
PLAN_FORMAT = "opencntx-layout-plan"
VERIFY_FORMAT = "opencntx-layout-plan-verification"
FORMAT_VERSION = 1
MANIFEST_SCHEMA_ID = schema_identifier(MANIFEST_FORMAT, FORMAT_VERSION)
PLAN_SCHEMA_ID = schema_identifier(PLAN_FORMAT, FORMAT_VERSION)
_ID = re.compile(r"[A-Z][A-Z0-9_-]{1,79}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_CREDENTIAL_URL = re.compile(r"^[a-z][a-z0-9+.-]*://[^/@\s]+:[^/@\s]+@", re.IGNORECASE)
_MANIFEST_FIELDS = {
    "format",
    "format_version",
    "maximum_bytes",
    "maximum_files",
    "maximum_path_length",
    "minimum_free_bytes",
    "operations",
    "plan_id",
    "protected_paths",
    "schema_id",
}
_OPERATION_FIELDS = {"destination", "id", "source"}
_PLAN_FIELDS = {
    "base",
    "bounds",
    "checks",
    "findings",
    "format",
    "format_version",
    "manifest_sha256",
    "operations",
    "plan_digest",
    "plan_id",
    "read_only",
    "schema_id",
    "status",
}
_PLAN_OPERATION_FIELDS = {
    "destination",
    "destination_state",
    "id",
    "operation_digest",
    "rollback",
    "source",
    "source_state",
}
_SOURCE_STATE_FIELDS = {
    "acl",
    "bytes",
    "directories",
    "files",
    "git",
    "kind",
    "links",
    "longest_projected_path",
    "process_locks",
    "state_digest",
    "tree_sha256",
}


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _value_digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        content = path.read_bytes()
        if len(content) > 1_048_576:
            raise OpenCntxError(f"{label} exceeds the one MiB input boundary.")
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_strict_object)
    except OpenCntxError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise OpenCntxError(f"{label} cannot be read.") from exc
    if not isinstance(value, dict):
        raise OpenCntxError(f"{label} must contain one JSON object.")
    return value, hashlib.sha256(content).hexdigest()


def _identifier(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise OpenCntxError(f"{label} must be one uppercase identifier.")
    return value


def _bounded_int(value: object, *, label: str, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise OpenCntxError(f"{label} is outside its bounded range.")
    return value


def _path_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise OpenCntxError(f"{label} must be one explicit path.")
    if value.startswith("~") or any(token in value for token in ("$", "%", "*", "?", "[", "]")):
        raise OpenCntxError(f"{label} contains an unresolved variable or wildcard.")
    path = Path(value)
    if not path.is_absolute():
        pure = PurePosixPath(value.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts or value.startswith(("./", ".\\")):
            raise OpenCntxError(f"{label} leaves the declared base.")
    return value


def _absolute(value: str, base: Path) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else base / path).absolute()


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    value, digest = _read_json(path, label="Layout migration manifest")
    if set(value) != _MANIFEST_FIELDS:
        raise OpenCntxError("Layout migration manifest fields are invalid.")
    if (
        value["format"] != MANIFEST_FORMAT
        or value["format_version"] != FORMAT_VERSION
        or value["schema_id"] != MANIFEST_SCHEMA_ID
    ):
        raise OpenCntxError("Layout migration manifest identity is unsupported.")
    _identifier(value["plan_id"], label="plan_id")
    _bounded_int(value["maximum_files"], label="maximum_files", minimum=1, maximum=10_000_000)
    _bounded_int(
        value["maximum_bytes"], label="maximum_bytes", minimum=1, maximum=10_995_116_277_760
    )
    _bounded_int(
        value["maximum_path_length"], label="maximum_path_length", minimum=64, maximum=32_767
    )
    _bounded_int(
        value["minimum_free_bytes"],
        label="minimum_free_bytes",
        minimum=0,
        maximum=10_995_116_277_760,
    )
    operations = value["operations"]
    if not isinstance(operations, list) or not operations or len(operations) > 1_000:
        raise OpenCntxError("Layout migration operations must be a bounded non-empty list.")
    identifiers: set[str] = set()
    for item in operations:
        if not isinstance(item, dict) or set(item) != _OPERATION_FIELDS:
            raise OpenCntxError("Layout migration operation fields are invalid.")
        identifier = _identifier(item["id"], label="operation id")
        if identifier in identifiers:
            raise OpenCntxError("Layout migration operation IDs must be unique.")
        identifiers.add(identifier)
        _path_text(item["source"], label="operation source")
        _path_text(item["destination"], label="operation destination")
        if item["source"] == item["destination"]:
            raise OpenCntxError("Layout migration source and destination must differ.")
    protected = value["protected_paths"]
    if not isinstance(protected, list) or len(protected) > 1_000:
        raise OpenCntxError("Layout migration protected_paths must be a bounded list.")
    normalized = [_path_text(item, label="protected path") for item in protected]
    if len(normalized) != len(set(normalized)):
        raise OpenCntxError("Layout migration protected paths must be unique.")
    return value, digest


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _locked(path: Path) -> tuple[bool, str]:
    if os.name != "nt":
        try:
            with path.open("rb"):
                return False, "READ_PROBE"
        except OSError:
            return True, "READ_PROBE"
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
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
    handle = create_file(str(path), 0x80000000, 0, None, 3, 0x80, None)
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        return True, "WINDOWS_EXCLUSIVE_READ"
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return False, "WINDOWS_EXCLUSIVE_READ"


def _git(arguments: list[str], *, cwd: Path) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise OSError("Git is unavailable")
    result = subprocess.run(
        [executable, "-C", str(cwd), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OSError("Git query failed")
    return result.stdout.strip()


def _repository_roots(source: Path) -> tuple[Path, ...]:
    if not source.is_dir():
        return ()
    roots: list[Path] = []
    for current, child_dirs, child_files in os.walk(source, topdown=True, followlinks=False):
        child_dirs.sort()
        child_files.sort()
        current_path = Path(current)
        if ".git" in child_dirs or ".git" in child_files:
            roots.append(current_path)
            child_dirs[:] = [name for name in child_dirs if name != ".git"]
        if len(roots) > 64:
            break
    return tuple(roots)


def _git_identities(source: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    identities: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    roots = _repository_roots(source)
    if len(roots) > 64:
        findings.append(
            {"code": "GIT_BOUND_REACHED", "operation": "", "path": str(source)}
        )
        roots = roots[:64]
    for root in roots:
        relative = root.relative_to(source).as_posix() if root != source else "."
        try:
            head = _git(["rev-parse", "HEAD"], cwd=root)
            if re.fullmatch(r"[0-9a-f]{40,64}", head) is None:
                raise OSError("Invalid Git head")
            branch = _git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=root)
        except OSError:
            try:
                head = _git(["rev-parse", "HEAD"], cwd=root)
                branch = "DETACHED"
            except OSError:
                findings.append(
                    {"code": "GIT_IDENTITY_UNAVAILABLE", "operation": "", "path": relative}
                )
                continue
        try:
            status = _git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=root)
            remote_names = _git(["remote"], cwd=root).splitlines()
            remotes = []
            for name in sorted(item for item in remote_names if item):
                url = _git(["remote", "get-url", name], cwd=root)
                if _CREDENTIAL_URL.search(url):
                    findings.append(
                        {"code": "GIT_REMOTE_CREDENTIAL", "operation": "", "path": relative}
                    )
                    continue
                remotes.append({"name": name, "url_sha256": hashlib.sha256(url.encode()).hexdigest()})
        except OSError:
            findings.append(
                {"code": "GIT_IDENTITY_UNAVAILABLE", "operation": "", "path": relative}
            )
            continue
        identities.append(
            {
                "branch": branch,
                "dirty": bool(status),
                "head": head,
                "path": relative,
                "remote_digests": remotes,
                "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
            }
        )
    return identities, findings


def _snapshot(
    source: Path,
    destination: Path,
    *,
    maximum_files: int,
    maximum_bytes: int,
    maximum_path_length: int,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    findings: list[dict[str, str]] = []
    if not source.exists() and not source.is_symlink():
        return {}, [{"code": "SOURCE_MISSING", "operation": "", "path": str(source)}]
    if source.is_symlink():
        return {}, [{"code": "SOURCE_LINK", "operation": "", "path": str(source)}]
    records: list[str] = []
    acl_records: list[str] = []
    links: list[dict[str, Any]] = []
    locked_paths: list[str] = []
    files = directories = byte_count = 0
    longest_projected = len(str(destination))
    lock_probe = "WINDOWS_EXCLUSIVE_READ" if os.name == "nt" else "READ_PROBE"

    def register(path: Path, relative: str, *, directory: bool) -> None:
        nonlocal files, directories, byte_count, longest_projected, lock_probe
        info = path.lstat()
        mode = stat.S_IMODE(info.st_mode)
        acl_records.append(f"{relative}\0{mode:o}")
        longest_projected = max(
            longest_projected,
            len(str(destination / Path(*PurePosixPath(relative).parts))) if relative != "." else len(str(destination)),
        )
        if path.is_symlink():
            target = os.readlink(path)
            links.append(
                {
                    "directory": path.is_dir(),
                    "path": relative,
                    "target_sha256": hashlib.sha256(os.fsencode(target)).hexdigest(),
                }
            )
            records.append(f"L\0{relative}\0{mode:o}\0{links[-1]['target_sha256']}")
            return
        if directory:
            directories += 1
            records.append(f"D\0{relative}\0{mode:o}")
            return
        files += 1
        size = info.st_size
        byte_count += size
        locked, method = _locked(path)
        lock_probe = method
        if locked:
            locked_paths.append(relative)
        try:
            digest = _hash_file(path)
        except OSError:
            findings.append({"code": "SOURCE_UNREADABLE", "operation": "", "path": relative})
            digest = "UNREADABLE"
        records.append(f"F\0{relative}\0{mode:o}\0{size}\0{digest}")

    try:
        if source.is_file():
            register(source, ".", directory=False)
            kind = "FILE"
        elif source.is_dir():
            kind = "DIRECTORY"
            register(source, ".", directory=True)
            for current, child_dirs, child_files in os.walk(
                source, topdown=True, followlinks=False
            ):
                child_dirs.sort()
                child_files.sort()
                current_path = Path(current)
                safe_dirs: list[str] = []
                for name in child_dirs:
                    path = current_path / name
                    relative = path.relative_to(source).as_posix()
                    register(path, relative, directory=True)
                    if not path.is_symlink() and name != ".git":
                        safe_dirs.append(name)
                child_dirs[:] = safe_dirs
                for name in child_files:
                    path = current_path / name
                    relative = path.relative_to(source).as_posix()
                    register(path, relative, directory=False)
                if files > maximum_files or byte_count > maximum_bytes:
                    findings.append(
                        {"code": "SOURCE_BOUND_REACHED", "operation": "", "path": str(source)}
                    )
                    break
        else:
            return {}, [{"code": "SOURCE_UNSAFE", "operation": "", "path": str(source)}]
    except OSError:
        findings.append({"code": "SOURCE_UNREADABLE", "operation": "", "path": str(source)})
        kind = "UNKNOWN"
    git, git_findings = _git_identities(source)
    findings.extend(git_findings)
    if links:
        findings.append({"code": "LINK_PRESENT", "operation": "", "path": links[0]["path"]})
    if locked_paths:
        findings.append(
            {"code": "PROCESS_LOCK_PRESENT", "operation": "", "path": locked_paths[0]}
        )
    if longest_projected > maximum_path_length:
        findings.append(
            {"code": "PATH_LENGTH_EXCEEDED", "operation": "", "path": str(destination)}
        )
    state = {
        "acl": {
            "digest": hashlib.sha256("\n".join(acl_records).encode("utf-8")).hexdigest(),
            "entries": len(acl_records),
            "method": "PORTABLE_STAT_MODE",
            "platform_acl_readback_required_before_apply": True,
        },
        "bytes": byte_count,
        "directories": directories,
        "files": files,
        "git": git,
        "kind": kind,
        "links": links,
        "longest_projected_path": longest_projected,
        "process_locks": {"method": lock_probe, "paths": locked_paths},
        "tree_sha256": hashlib.sha256("\n".join(records).encode("utf-8")).hexdigest(),
    }
    return state | {"state_digest": _value_digest(state)}, findings


def _overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _nearest_existing(path: Path) -> Path | None:
    candidate = path
    while not candidate.exists():
        if candidate.parent == candidate:
            return None
        candidate = candidate.parent
    return candidate


def _ancestor_link(path: Path) -> str | None:
    candidate = path
    while candidate.parent != candidate:
        if candidate.exists() and candidate.is_symlink():
            return str(candidate)
        candidate = candidate.parent
    return None


def build_layout_plan(manifest_path: Path, base: Path) -> dict[str, Any]:
    """Build a deterministic migration plan without writing to the filesystem."""
    manifest, manifest_digest = _load_manifest(manifest_path)
    base_path = base.absolute()
    protected = tuple(_absolute(item, base_path) for item in manifest["protected_paths"])
    resolved = [
        (
            item,
            _absolute(item["source"], base_path),
            _absolute(item["destination"], base_path),
        )
        for item in manifest["operations"]
    ]
    findings: list[dict[str, str]] = []
    for index, (left, left_source, left_destination) in enumerate(resolved):
        for right, right_source, right_destination in resolved[index + 1 :]:
            if _overlap(left_destination, right_destination):
                findings.append(
                    {
                        "code": "DESTINATION_OVERLAP",
                        "operation": left["id"],
                        "path": right["id"],
                    }
                )
            if _overlap(left_source, right_source):
                findings.append(
                    {"code": "SOURCE_OVERLAP", "operation": left["id"], "path": right["id"]}
                )
    operations: list[dict[str, Any]] = []
    for item, source, destination in resolved:
        operation_findings: list[dict[str, str]] = []
        if _overlap(source, destination):
            operation_findings.append(
                {"code": "SOURCE_DESTINATION_OVERLAP", "operation": item["id"], "path": str(destination)}
            )
        if any(_overlap(source, path) or _overlap(destination, path) for path in protected):
            operation_findings.append(
                {"code": "PROTECTED_PATH", "operation": item["id"], "path": str(destination)}
            )
        if destination.exists() or destination.is_symlink():
            operation_findings.append(
                {"code": "DESTINATION_COLLISION", "operation": item["id"], "path": str(destination)}
            )
        ancestor_link = _ancestor_link(destination.parent)
        if ancestor_link is not None:
            operation_findings.append(
                {"code": "DESTINATION_LINK_ANCESTOR", "operation": item["id"], "path": ancestor_link}
            )
        state, state_findings = _snapshot(
            source,
            destination,
            maximum_files=manifest["maximum_files"],
            maximum_bytes=manifest["maximum_bytes"],
            maximum_path_length=manifest["maximum_path_length"],
        )
        for finding in state_findings:
            finding["operation"] = item["id"]
        operation_findings.extend(state_findings)
        probe = _nearest_existing(destination.parent)
        required_bytes = int(state.get("bytes", 0)) + manifest["minimum_free_bytes"]
        disk_ok = False
        if probe is None:
            operation_findings.append(
                {"code": "DESTINATION_PARENT_UNAVAILABLE", "operation": item["id"], "path": str(destination.parent)}
            )
        else:
            try:
                disk_ok = shutil.disk_usage(probe).free >= required_bytes
            except OSError:
                operation_findings.append(
                    {"code": "DISK_PROBE_FAILED", "operation": item["id"], "path": str(probe)}
                )
            if not disk_ok:
                operation_findings.append(
                    {"code": "DISK_SPACE_INSUFFICIENT", "operation": item["id"], "path": str(probe)}
                )
        operation = {
            "destination": str(destination),
            "destination_state": {
                "collision": destination.exists() or destination.is_symlink(),
                "disk_probe_root": str(probe) if probe is not None else None,
                "required_bytes": required_bytes,
                "space_available": disk_ok,
            },
            "id": item["id"],
            "rollback": {
                "from": str(destination),
                "precondition": "DESTINATION_STATE_DIGEST_MATCH_AND_SOURCE_ABSENT",
                "to": str(source),
            },
            "source": str(source),
            "source_state": state,
        }
        operation["operation_digest"] = _value_digest(operation)
        operations.append(operation)
        findings.extend(operation_findings)
    findings.sort(key=lambda value: (value["operation"], value["path"], value["code"]))
    checks = {
        "acl_capture": "PASS" if all(item["source_state"] for item in operations) else "FAIL",
        "collisions": "FAIL" if any(item["code"] == "DESTINATION_COLLISION" for item in findings) else "PASS",
        "disk_space": "FAIL" if any(item["code"].startswith("DISK_") for item in findings) else "PASS",
        "git_identity": "FAIL" if any(item["code"].startswith("GIT_") for item in findings) else "PASS",
        "links": "FAIL" if any("LINK" in item["code"] for item in findings) else "PASS",
        "path_length": "FAIL" if any(item["code"] == "PATH_LENGTH_EXCEEDED" for item in findings) else "PASS",
        "process_locks": "FAIL" if any(item["code"] == "PROCESS_LOCK_PRESENT" for item in findings) else "PASS",
        "protected_paths": "FAIL" if any(item["code"] == "PROTECTED_PATH" for item in findings) else "PASS",
        "rollback": "PASS",
        "source_state": "FAIL" if any(item["code"].startswith("SOURCE_") for item in findings) else "PASS",
    }
    plan = {
        "base": str(base_path),
        "bounds": {
            "maximum_bytes": manifest["maximum_bytes"],
            "maximum_files": manifest["maximum_files"],
            "maximum_path_length": manifest["maximum_path_length"],
            "minimum_free_bytes": manifest["minimum_free_bytes"],
            "protected_paths": [str(item) for item in protected],
        },
        "checks": checks,
        "findings": findings,
        "format": PLAN_FORMAT,
        "format_version": FORMAT_VERSION,
        "manifest_sha256": manifest_digest,
        "operations": operations,
        "plan_id": manifest["plan_id"],
        "read_only": True,
        "schema_id": PLAN_SCHEMA_ID,
        "status": "READY" if not findings else "BLOCKED",
    }
    return plan | {"plan_digest": _value_digest(plan)}


def _load_plan(path: Path) -> dict[str, Any]:
    value, _digest_value = _read_json(path, label="Layout plan")
    if set(value) != _PLAN_FIELDS:
        raise OpenCntxError("Layout plan fields are invalid.")
    expected = value.get("plan_digest")
    basis = {key: item for key, item in value.items() if key != "plan_digest"}
    if (
        value.get("format") != PLAN_FORMAT
        or value.get("format_version") != FORMAT_VERSION
        or value.get("schema_id") != PLAN_SCHEMA_ID
        or value.get("read_only") is not True
        or not isinstance(expected, str)
        or _DIGEST.fullmatch(expected) is None
        or expected != _value_digest(basis)
    ):
        raise OpenCntxError("Layout plan identity or digest is invalid.")
    if value.get("status") != "READY" or value.get("findings") != []:
        raise OpenCntxError("Only a READY zero-finding layout plan can be verified.")
    bounds = value.get("bounds")
    if not isinstance(bounds, dict) or set(bounds) != {
        "maximum_bytes",
        "maximum_files",
        "maximum_path_length",
        "minimum_free_bytes",
        "protected_paths",
    }:
        raise OpenCntxError("Layout plan bounds are invalid.")
    _bounded_int(bounds["maximum_files"], label="maximum_files", minimum=1, maximum=10_000_000)
    _bounded_int(
        bounds["maximum_bytes"], label="maximum_bytes", minimum=1, maximum=10_995_116_277_760
    )
    _bounded_int(
        bounds["maximum_path_length"], label="maximum_path_length", minimum=64, maximum=32_767
    )
    _bounded_int(
        bounds["minimum_free_bytes"],
        label="minimum_free_bytes",
        minimum=0,
        maximum=10_995_116_277_760,
    )
    if not isinstance(bounds["protected_paths"], list) or any(
        not isinstance(item, str) or not Path(item).is_absolute()
        for item in bounds["protected_paths"]
    ):
        raise OpenCntxError("Layout plan protected paths are invalid.")
    checks = value.get("checks")
    if (
        not isinstance(checks, dict)
        or set(checks)
        != {
            "acl_capture",
            "collisions",
            "disk_space",
            "git_identity",
            "links",
            "path_length",
            "process_locks",
            "protected_paths",
            "rollback",
            "source_state",
        }
        or set(checks.values()) != {"PASS"}
    ):
        raise OpenCntxError("READY layout plan checks are invalid.")
    operations = value.get("operations")
    if not isinstance(operations, list) or not operations or len(operations) > 1_000:
        raise OpenCntxError("Layout plan operations are invalid.")
    seen: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != _PLAN_OPERATION_FIELDS:
            raise OpenCntxError("Layout plan operation fields are invalid.")
        identifier = _identifier(operation["id"], label="operation id")
        if identifier in seen:
            raise OpenCntxError("Layout plan operation IDs must be unique.")
        seen.add(identifier)
        if (
            not isinstance(operation["source"], str)
            or not Path(operation["source"]).is_absolute()
            or not isinstance(operation["destination"], str)
            or not Path(operation["destination"]).is_absolute()
        ):
            raise OpenCntxError("Layout plan operation paths are invalid.")
        operation_digest = operation.get("operation_digest")
        operation_basis = {
            key: item for key, item in operation.items() if key != "operation_digest"
        }
        if (
            not isinstance(operation_digest, str)
            or _DIGEST.fullmatch(operation_digest) is None
            or operation_digest != _value_digest(operation_basis)
        ):
            raise OpenCntxError("Layout plan operation digest is invalid.")
        state = operation.get("source_state")
        if not isinstance(state, dict) or set(state) != _SOURCE_STATE_FIELDS:
            raise OpenCntxError("Layout plan source state is invalid.")
        state_digest = state.get("state_digest")
        state_basis = {key: item for key, item in state.items() if key != "state_digest"}
        if (
            not isinstance(state_digest, str)
            or _DIGEST.fullmatch(state_digest) is None
            or state_digest != _value_digest(state_basis)
        ):
            raise OpenCntxError("Layout plan source state digest is invalid.")
        destination_state = operation.get("destination_state")
        rollback = operation.get("rollback")
        if (
            not isinstance(destination_state, dict)
            or set(destination_state)
            != {"collision", "disk_probe_root", "required_bytes", "space_available"}
            or destination_state["collision"] is not False
            or destination_state["space_available"] is not True
            or not isinstance(destination_state["required_bytes"], int)
            or not isinstance(rollback, dict)
            or set(rollback) != {"from", "precondition", "to"}
            or rollback["from"] != operation["destination"]
            or rollback["to"] != operation["source"]
            or rollback["precondition"]
            != "DESTINATION_STATE_DIGEST_MATCH_AND_SOURCE_ABSENT"
        ):
            raise OpenCntxError("Layout plan destination or rollback state is invalid.")
    return value


def verify_layout_plan(plan_path: Path) -> dict[str, Any]:
    """Verify that a READY plan still matches every read-only preview base."""
    plan = _load_plan(plan_path)
    bounds = plan["bounds"]
    findings: list[dict[str, str]] = []
    for operation in plan["operations"]:
        source = Path(operation["source"])
        destination = Path(operation["destination"])
        state, state_findings = _snapshot(
            source,
            destination,
            maximum_files=bounds["maximum_files"],
            maximum_bytes=bounds["maximum_bytes"],
            maximum_path_length=bounds["maximum_path_length"],
        )
        if state != operation["source_state"]:
            findings.append(
                {"code": "SOURCE_CHANGED", "operation": operation["id"], "path": str(source)}
            )
        for finding in state_findings:
            finding["operation"] = operation["id"]
        findings.extend(state_findings)
        if destination.exists() or destination.is_symlink():
            findings.append(
                {"code": "DESTINATION_CHANGED", "operation": operation["id"], "path": str(destination)}
            )
        ancestor_link = _ancestor_link(destination.parent)
        if ancestor_link is not None:
            findings.append(
                {
                    "code": "DESTINATION_LINK_CHANGED",
                    "operation": operation["id"],
                    "path": ancestor_link,
                }
            )
        if any(
            _overlap(source, Path(path)) or _overlap(destination, Path(path))
            for path in bounds["protected_paths"]
        ):
            findings.append(
                {"code": "PROTECTED_PATH", "operation": operation["id"], "path": str(destination)}
            )
        probe = _nearest_existing(destination.parent)
        required = operation["destination_state"]["required_bytes"]
        try:
            disk_changed = probe is None or shutil.disk_usage(probe).free < required
        except OSError:
            disk_changed = True
        if disk_changed:
            findings.append(
                {"code": "DISK_SPACE_CHANGED", "operation": operation["id"], "path": str(destination.parent)}
            )
    findings.sort(key=lambda value: (value["operation"], value["path"], value["code"]))
    result = {
        "findings": findings,
        "format": VERIFY_FORMAT,
        "format_version": FORMAT_VERSION,
        "plan_digest": plan["plan_digest"],
        "plan_id": plan["plan_id"],
        "read_only": True,
        "status": "VERIFIED" if not findings else "STALE",
    }
    return result | {"verification_digest": _value_digest(result)}
