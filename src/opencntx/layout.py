"""Read-only, provider-neutral workspace order auditing."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import schema_identifier
from .core import OpenCntxError

FORMAT = "opencntx-order-contract"
FORMAT_VERSION = 1
SCHEMA_ID = schema_identifier(FORMAT, FORMAT_VERSION)
_TOP_FIELDS = {
    "contract_id",
    "duplicate_ownership",
    "folder_roles",
    "format",
    "format_version",
    "naming",
    "path_allowlist",
    "revision",
    "roots",
    "schema_id",
    "stop_rule",
}
_ID = re.compile(r"[A-Z][A-Z0-9_-]{1,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class LayoutFinding:
    code: str
    root: str
    path: str
    detail: str


@dataclass(frozen=True)
class LayoutReport:
    contract_id: str
    revision: int
    contract_sha256: str
    base: str
    status: str
    files: int
    directories: int
    bytes: int
    findings: tuple[LayoutFinding, ...]

    @property
    def ok(self) -> bool:
        return self.status == "GREEN"


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate key: {key}")
        value[key] = item
    return value


def _closed(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise OpenCntxError(f"Order contract {label} has invalid fields.")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise OpenCntxError(f"Order contract {label} must be an uppercase identifier.")
    return value


def _relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise OpenCntxError(f"Order contract {label} must be a POSIX relative path.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value.startswith("./"):
        raise OpenCntxError(f"Order contract {label} leaves its registered root.")
    return value


def _positive(value: Any, label: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        raise OpenCntxError(f"Order contract {label} is outside its bounded range.")
    return value


def _validate_contract(value: Any) -> dict[str, Any]:
    contract = _closed(value, _TOP_FIELDS, "root")
    if (
        contract["format"] != FORMAT
        or contract["format_version"] != FORMAT_VERSION
        or contract["schema_id"] != SCHEMA_ID
    ):
        raise OpenCntxError("Order contract format or schema identity is unsupported.")
    _identifier(contract["contract_id"], "contract_id")
    _positive(contract["revision"], "revision", 1_000_000)
    _validate_roots(contract)
    _validate_roles(contract)
    _validate_naming(contract)
    _validate_allowlist(contract)
    _validate_duplicates(contract)
    _validate_stop_rule(contract)
    return contract


def _validate_roots(contract: dict[str, Any]) -> None:
    roots = contract["roots"]
    if not isinstance(roots, list) or not roots:
        raise OpenCntxError("Order contract roots must be a non-empty list.")
    seen: set[str] = set()
    for item in roots:
        root = _closed(item, {"id", "path", "required", "role"}, "root entry")
        root_id = _identifier(root["id"], "root id")
        _identifier(root["role"], "root role")
        if root_id in seen or not isinstance(root["path"], str) or not root["path"]:
            raise OpenCntxError("Order contract root registry is invalid.")
        if not isinstance(root["required"], bool):
            raise OpenCntxError("Order contract root required flag must be boolean.")
        seen.add(root_id)


def _validate_roles(contract: dict[str, Any]) -> None:
    root_ids = {item["id"] for item in contract["roots"]}
    roles = contract["folder_roles"]
    if not isinstance(roles, list):
        raise OpenCntxError("Order contract folder_roles must be a list.")
    seen: set[str] = set()
    for item in roles:
        role = _closed(item, {"id", "owner", "path", "required", "root"}, "folder role")
        role_id = _identifier(role["id"], "folder role id")
        _identifier(role["owner"], "folder role owner")
        if role["root"] not in root_ids or not isinstance(role["required"], bool):
            raise OpenCntxError("Order contract folder role has an invalid root or flag.")
        key = f"{role['root']}:{_relative(role['path'], 'folder role path')}"
        if role_id in seen or key in seen:
            raise OpenCntxError("Order contract folder roles must be unique.")
        seen.update((role_id, key))


def _validate_naming(contract: dict[str, Any]) -> None:
    naming = _closed(
        contract["naming"], {"directory_pattern", "exempt", "file_pattern"}, "naming"
    )
    for key in ("directory_pattern", "file_pattern"):
        try:
            if not isinstance(naming[key], str):
                raise TypeError
            re.compile(naming[key], re.ASCII)
        except (TypeError, re.error) as exc:
            raise OpenCntxError(f"Order contract naming.{key} is invalid.") from exc
    if not isinstance(naming["exempt"], list):
        raise OpenCntxError("Order contract naming.exempt must be a list.")
    for pattern in naming["exempt"]:
        _relative(pattern, "naming exempt pattern")


def _validate_allowlist(contract: dict[str, Any]) -> None:
    root_ids = {item["id"] for item in contract["roots"]}
    rules = contract["path_allowlist"]
    if not isinstance(rules, list) or not rules:
        raise OpenCntxError("Order contract path_allowlist must be a non-empty list.")
    covered: set[str] = set()
    for item in rules:
        rule = _closed(item, {"owner", "pattern", "root"}, "path allowlist entry")
        if rule["root"] not in root_ids:
            raise OpenCntxError("Order contract path allowlist references an unknown root.")
        _identifier(rule["owner"], "path owner")
        _relative(rule["pattern"], "path allowlist pattern")
        covered.add(rule["root"])
    if covered != root_ids:
        raise OpenCntxError("Every registered root needs a path allowlist rule.")


def _validate_duplicates(contract: dict[str, Any]) -> None:
    policy = _closed(
        contract["duplicate_ownership"],
        {"allowed_sha256", "enabled", "minimum_bytes"},
        "duplicate ownership",
    )
    if not isinstance(policy["enabled"], bool):
        raise OpenCntxError("Order contract duplicate enabled flag must be boolean.")
    _positive(policy["minimum_bytes"], "duplicate minimum_bytes", 1_073_741_824)
    allowed = policy["allowed_sha256"]
    if not isinstance(allowed, list) or any(
        not isinstance(item, str) or _DIGEST.fullmatch(item) is None for item in allowed
    ):
        raise OpenCntxError("Order contract allowed duplicate digests are invalid.")
    if len(allowed) != len(set(allowed)):
        raise OpenCntxError("Order contract allowed duplicate digests must be unique.")


def _validate_stop_rule(contract: dict[str, Any]) -> None:
    rule = _closed(
        contract["stop_rule"],
        {"acceptance", "maximum_bytes", "maximum_files", "maximum_findings"},
        "stop rule",
    )
    if rule["acceptance"] != "ZERO_FINDINGS":
        raise OpenCntxError("Order contract acceptance must be ZERO_FINDINGS.")
    _positive(rule["maximum_files"], "stop maximum_files", 10_000_000)
    _positive(rule["maximum_bytes"], "stop maximum_bytes", 10_995_116_277_760)
    _positive(rule["maximum_findings"], "stop maximum_findings", 100_000)


def load_order_contract(path: Path) -> tuple[dict[str, Any], str]:
    """Load one strict, versioned order contract without changing it."""
    try:
        content = path.read_bytes()
        if len(content) > 1_048_576:
            raise OpenCntxError("Order contract exceeds the one MiB input boundary.")
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_strict_object)
    except OpenCntxError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise OpenCntxError(f"Order contract cannot be read: {path}") from exc
    return _validate_contract(value), hashlib.sha256(content).hexdigest()


def _resolved_roots(contract: dict[str, Any], base: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for item in contract["roots"]:
        candidate = Path(item["path"])
        result[item["id"]] = (candidate if candidate.is_absolute() else base / candidate).absolute()
    return result


def _finding(code: str, root: str, path: str, detail: str) -> LayoutFinding:
    return LayoutFinding(code=code, root=root, path=path, detail=detail)


def _owners(contract: dict[str, Any], root_id: str, relative: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                item["owner"]
                for item in contract["path_allowlist"]
                if item["root"] == root_id and fnmatchcase(relative, item["pattern"])
            }
        )
    )


def _check_entry(
    contract: dict[str, Any], root_id: str, relative: str, *, directory: bool
) -> tuple[list[LayoutFinding], str]:
    findings: list[LayoutFinding] = []
    naming = contract["naming"]
    exempt = any(fnmatchcase(relative, pattern) for pattern in naming["exempt"])
    pattern = naming["directory_pattern" if directory else "file_pattern"]
    if not exempt and re.fullmatch(pattern, PurePosixPath(relative).name, re.ASCII) is None:
        findings.append(_finding("NAME_POLICY", root_id, relative, "Name violates policy."))
    owners = _owners(contract, root_id, relative)
    if not owners:
        findings.append(_finding("PATH_NOT_ALLOWED", root_id, relative, "No owner rule matches."))
        return findings, "UNOWNED"
    if len(owners) > 1:
        findings.append(
            _finding("MULTIPLE_OWNERS", root_id, relative, f"Owners: {', '.join(owners)}")
        )
    return findings, owners[0]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _audit_root(
    contract: dict[str, Any], root_id: str, root: Path
) -> tuple[list[LayoutFinding], int, int, int, dict[str, list[tuple[str, str]]], bool]:
    findings: list[LayoutFinding] = []
    files = directories = byte_count = 0
    duplicates: dict[str, list[tuple[str, str]]] = {}
    stop = contract["stop_rule"]
    duplicate_policy = contract["duplicate_ownership"]
    for current, child_dirs, child_files in os.walk(root, topdown=True, followlinks=False):
        child_dirs.sort()
        child_files.sort()
        current_path = Path(current)
        safe_dirs: list[str] = []
        for name in child_dirs:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            directories += 1
            entry_findings, _ = _check_entry(contract, root_id, relative, directory=True)
            findings.extend(entry_findings)
            if path.is_symlink():
                findings.append(_finding("LINK_NOT_FOLLOWED", root_id, relative, "Directory link."))
            else:
                safe_dirs.append(name)
        child_dirs[:] = safe_dirs
        for name in child_files:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            files += 1
            entry_findings, owner = _check_entry(contract, root_id, relative, directory=False)
            findings.extend(entry_findings)
            if path.is_symlink():
                findings.append(_finding("LINK_NOT_FOLLOWED", root_id, relative, "File link."))
                continue
            try:
                size = path.stat().st_size
                byte_count += size
                if duplicate_policy["enabled"] and size >= duplicate_policy["minimum_bytes"]:
                    duplicates.setdefault(_hash_file(path), []).append((f"{root_id}:{relative}", owner))
            except OSError:
                findings.append(_finding("FILE_UNREADABLE", root_id, relative, "Cannot read file."))
        if (
            files > stop["maximum_files"]
            or byte_count > stop["maximum_bytes"]
            or len(findings) >= stop["maximum_findings"]
        ):
            findings.append(
                _finding("SCAN_BOUND_REACHED", root_id, ".", "Bounded scan stopped deterministically.")
            )
            return findings, files, directories, byte_count, duplicates, True
    return findings, files, directories, byte_count, duplicates, False


def audit_layout(contract_path: Path, base: Path) -> LayoutReport:
    """Audit registered roots deterministically and without filesystem writes."""
    contract, contract_digest = load_order_contract(contract_path)
    base_path = base.absolute()
    roots = _resolved_roots(contract, base_path)
    findings: list[LayoutFinding] = []
    files = directories = byte_count = 0
    duplicate_files: dict[str, list[tuple[str, str]]] = {}
    stopped = False
    ordered_roots = sorted(contract["roots"], key=lambda item: item["id"])
    for index, left in enumerate(ordered_roots):
        for right in ordered_roots[index + 1 :]:
            left_path, right_path = roots[left["id"]], roots[right["id"]]
            if left_path == right_path or left_path in right_path.parents or right_path in left_path.parents:
                findings.append(
                    _finding("ROOT_OVERLAP", left["id"], str(left_path), f"Overlaps {right['id']}.")
                )
    for item in ordered_roots:
        root_id, root = item["id"], roots[item["id"]]
        if not root.exists():
            if item["required"]:
                findings.append(_finding("ROOT_MISSING", root_id, str(root), "Required root."))
            continue
        if root.is_symlink() or not root.is_dir():
            findings.append(_finding("ROOT_UNSAFE", root_id, str(root), "Root is not a real directory."))
            continue
        for role in sorted(contract["folder_roles"], key=lambda entry: entry["id"]):
            if role["root"] != root_id:
                continue
            role_path = root.joinpath(*PurePosixPath(role["path"]).parts)
            if role["required"] and (not role_path.is_dir() or role_path.is_symlink()):
                findings.append(
                    _finding("FOLDER_ROLE_MISSING", root_id, role["path"], f"Role {role['id']}.")
                )
        result = _audit_root(contract, root_id, root)
        root_findings, root_files, root_dirs, root_bytes, root_duplicates, root_stopped = result
        findings.extend(root_findings)
        files += root_files
        directories += root_dirs
        byte_count += root_bytes
        for digest, entries in root_duplicates.items():
            duplicate_files.setdefault(digest, []).extend(entries)
        if root_stopped:
            stopped = True
            break
    allowed = set(contract["duplicate_ownership"]["allowed_sha256"])
    for digest, entries in sorted(duplicate_files.items()):
        if len(entries) > 1 and digest not in allowed:
            paths = sorted(path for path, _owner in entries)
            owners = sorted({owner for _path, owner in entries})
            findings.append(
                _finding(
                    "DUPLICATE_CONTENT",
                    "MULTI",
                    paths[0],
                    f"Canonical owner {owners[0]}; copies: {', '.join(paths)}",
                )
            )
    ordered = tuple(sorted(findings, key=lambda item: (item.root, item.path, item.code, item.detail)))
    status = "STOPPED" if stopped else ("GREEN" if not ordered else "NEEDS_ACTION")
    return LayoutReport(
        contract_id=contract["contract_id"],
        revision=contract["revision"],
        contract_sha256=contract_digest,
        base=str(base_path),
        status=status,
        files=files,
        directories=directories,
        bytes=byte_count,
        findings=ordered,
    )


def layout_report_record(report: LayoutReport) -> dict[str, Any]:
    """Return stable JSON-ready report data."""
    return {
        "base": report.base,
        "bytes": report.bytes,
        "contract_id": report.contract_id,
        "contract_sha256": report.contract_sha256,
        "directories": report.directories,
        "files": report.files,
        "finding_count": len(report.findings),
        "findings": [
            {"code": item.code, "detail": item.detail, "path": item.path, "root": item.root}
            for item in report.findings
        ],
        "format": "opencntx-layout-report",
        "format_version": 1,
        "read_only": True,
        "revision": report.revision,
        "status": report.status,
        "stop_rule": "ZERO_FINDINGS",
    }


def format_layout_report(report: LayoutReport) -> str:
    """Format one short deterministic text report."""
    lines = [
        f"Layout: {report.status}",
        f"Contract: {report.contract_id} revision {report.revision}",
        f"Contract-SHA-256: {report.contract_sha256}",
        f"Scanned: {report.files} files, {report.directories} directories, {report.bytes} bytes",
        f"Findings: {len(report.findings)}",
    ]
    lines.extend(f"- {item.code} {item.root}:{item.path} — {item.detail}" for item in report.findings)
    lines.append("Read-only audit; no path was created, moved, renamed, or removed.")
    return "\n".join(lines)
