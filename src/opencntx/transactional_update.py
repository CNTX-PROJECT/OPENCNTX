"""Read-only update planning and backup-first multi-component cutover."""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .continuity import (
    _digest,
    _fail,
    _identifier,
    _one_line,
    _value_digest,
    _write_atomic,
    _writer_lock,
)
from .contracts import ContractError, validate_durable_record
from .integrity import UNBOUND_EXPECTED_DIGEST, doctor_workspace

CAPABILITY_STATES = frozenset(
    {"READABLE", "MISSING", "ACL_DENIED", "SANDBOX_DENIED", "REPARSE_UNSAFE", "LOCKED"}
)
PLAN_FORMAT = "opencntx-transactional-update-plan"
RECEIPT_FORMAT = "opencntx-transactional-update-receipt"


def _pretty(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _tree_digest(root: Path) -> str:
    if not root.is_dir() or root.is_symlink():
        raise _fail("update_path_invalid", "Update component must be a real directory.")
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        mode = path.stat(follow_symlinks=False).st_mode
        if stat.S_ISLNK(mode) or getattr(path.lstat(), "st_file_attributes", 0) & 0x0400:
            raise _fail("update_path_invalid", "Update component contains a link or reparse point.")
        if stat.S_ISDIR(mode):
            records.append({"path": relative, "type": "directory"})
        elif stat.S_ISREG(mode):
            content = path.read_bytes()
            records.append(
                {"path": relative, "type": "file", "bytes": len(content), "sha256": _digest(content)}
            )
        else:
            raise _fail("update_path_invalid", "Update component contains a special entry.")
    return _value_digest(records)


def _tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def classify_path_capability(
    path: Path,
    *,
    declared_sandbox_denied: bool = False,
) -> dict[str, Any]:
    """Classify one required path without changing it."""
    requested = path.absolute()
    try:
        metadata = requested.lstat()
    except FileNotFoundError:
        status = "MISSING"
        exists = False
    except PermissionError:
        status = "SANDBOX_DENIED" if declared_sandbox_denied else "ACL_DENIED"
        exists = True
    except OSError as exc:
        status = "LOCKED" if getattr(exc, "winerror", None) in {32, 33} else "ACL_DENIED"
        exists = True
    else:
        exists = True
        if declared_sandbox_denied:
            status = "SANDBOX_DENIED"
        elif stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x0400:
            status = "REPARSE_UNSAFE"
        else:
            try:
                if requested.is_file():
                    with requested.open("rb") as stream:
                        stream.read(1)
                elif requested.is_dir():
                    next(requested.iterdir(), None)
                else:
                    raise OSError("special path")
            except PermissionError:
                status = "ACL_DENIED"
            except OSError as exc:
                status = "LOCKED" if getattr(exc, "winerror", None) in {32, 33} else "ACL_DENIED"
            else:
                status = "READABLE"
    next_action = {
        "READABLE": "NONE",
        "MISSING": "Restore the exact missing path from verified source evidence.",
        "ACL_DENIED": "Request minimal read access; do not reinitialize or delete content.",
        "SANDBOX_DENIED": "Use the exact bounded read capability or a digest-bound read-only capsule.",
        "REPARSE_UNSAFE": "Resolve the approved real path before continuing.",
        "LOCKED": "Wait for or identify the exact active owner of the path lock.",
    }[status]
    result = {
        "format": "opencntx-path-capability",
        "format_version": 1,
        "path": str(requested),
        "exists": exists,
        "status": status,
        "next_action": next_action,
        "state_changed": False,
    }
    return result | {"capability_digest": _value_digest(result)}


def migration_readiness(project_root: Path) -> dict[str, Any]:
    """Report operational health separately from durable-record migration readiness."""
    root = project_root.resolve(strict=True)
    operational = doctor_workspace(root)
    completed = root / ".opencntx" / "transactions" / "completed"
    valid = 0
    legacy_null: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    if completed.exists():
        for directory in sorted(completed.iterdir()):
            intent_path = directory / "intent.json"
            try:
                content = intent_path.read_bytes()
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise TypeError
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
                invalid.append({"transaction_id": directory.name, "reason": "INTENT_UNREADABLE"})
                continue
            try:
                validate_durable_record(value)
            except ContractError:
                repaired = dict(value)
                if value.get("expected_digest") is None:
                    repaired["expected_digest"] = UNBOUND_EXPECTED_DIGEST
                    try:
                        validate_durable_record(repaired)
                    except ContractError:
                        invalid.append(
                            {"transaction_id": directory.name, "reason": "CONTRACT_INVALID"}
                        )
                    else:
                        legacy_null.append(
                            {
                                "transaction_id": directory.name,
                                "path": intent_path.relative_to(root).as_posix(),
                                "sha256": _digest(content),
                            }
                        )
                else:
                    invalid.append({"transaction_id": directory.name, "reason": "CONTRACT_INVALID"})
            else:
                valid += 1
    if invalid:
        readiness = "BLOCKED"
    elif legacy_null:
        readiness = "COMPATIBILITY_REQUIRED"
    else:
        readiness = "READY"
    value = {
        "format": "opencntx-migration-readiness",
        "format_version": 1,
        "operational_health": operational.status,
        "migration_readiness": readiness,
        "valid_transaction_count": valid,
        "legacy_null_transactions": legacy_null,
        "invalid_transactions": invalid,
        "source_changed": False,
    }
    return value | {"readiness_digest": _value_digest(value)}


def export_legacy_transaction_history(
    project_root: Path,
    *,
    destination: Path,
    expected_readiness_digest: str,
) -> dict[str, Any]:
    """Export exact legacy completed transaction bytes without rewriting their source."""
    root = project_root.resolve(strict=True)
    before = migration_readiness(root)
    if before["readiness_digest"] != expected_readiness_digest:
        raise _fail("update_source_drift", "Migration readiness changed before export.")
    if before["migration_readiness"] != "COMPATIBILITY_REQUIRED":
        raise _fail("update_legacy_export_unavailable", "No exact legacy compatibility set exists.")
    target = destination.absolute()
    if target.exists():
        raise _fail("update_legacy_export_exists", "Legacy export destination already exists.")
    try:
        target.relative_to(root / ".opencntx" / "transactions")
    except ValueError:
        pass
    else:
        raise _fail("update_path_invalid", "Legacy export must be outside active transactions.")
    source_digest_before = _tree_digest(root / ".opencntx" / "transactions" / "completed")
    target.mkdir(parents=True)
    entries: list[dict[str, Any]] = []
    try:
        raw = target / "raw"
        raw.mkdir()
        for item in before["legacy_null_transactions"]:
            identifier = item["transaction_id"]
            source = root / ".opencntx" / "transactions" / "completed" / identifier
            copied = raw / identifier
            shutil.copytree(source, copied)
            source_digest = _tree_digest(source)
            if _tree_digest(copied) != source_digest:
                raise _fail("update_backup_invalid", "Legacy export is not byte-equal.")
            entries.append(
                {
                    "transaction_id": identifier,
                    "source_path": source.relative_to(root).as_posix(),
                    "export_path": copied.relative_to(target).as_posix(),
                    "tree_digest": source_digest,
                }
            )
        manifest = {
            "format": "opencntx-legacy-transaction-export",
            "format_version": 1,
            "source_root": str(root),
            "readiness_digest": expected_readiness_digest,
            "entries": entries,
            "source_completed_tree_digest": source_digest_before,
            "source_rewritten": False,
        }
        manifest["manifest_digest"] = _value_digest(manifest)
        _write_atomic(target / "manifest.json", _pretty(manifest))
        if _tree_digest(root / ".opencntx" / "transactions" / "completed") != source_digest_before:
            raise _fail("update_source_drift", "Source transaction history changed during export.")
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return manifest


def _inside(root: Path, raw: object, field: str) -> Path:
    text = _one_line(raw, field, 1_000)
    path = Path(text).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise _fail("update_path_invalid", f"{field} must stay inside update_root.") from exc
    return path


def _bounded_lines(values: Sequence[str], field: str) -> list[str]:
    if isinstance(values, (str, bytes)) or len(values) > 100:
        raise _fail("update_plan_invalid", f"{field} must be a bounded list.")
    lines = [_one_line(value, field, 500) for value in values]
    if len(lines) != len(set(lines)):
        raise _fail("update_plan_invalid", f"{field} contains duplicates.")
    return lines


def build_update_preview(
    update_root: Path,
    *,
    from_version: str,
    to_version: str,
    components: Sequence[Mapping[str, object]],
    target_context_version: str,
    target_companion_version: str | None,
    target_project_format: str,
    compatibility_matrix: Sequence[Mapping[str, str]],
    changelog: Sequence[str],
    risks: Sequence[str],
    available_bytes: int | None = None,
) -> dict[str, Any]:
    """Build a complete read-only plan; no runtime or project byte is changed."""
    root = update_root.resolve(strict=True)
    if not components or len(components) > 100:
        raise _fail("update_plan_invalid", "Update components must be a bounded non-empty list.")
    version_from = _one_line(from_version, "from_version", 120)
    version_to = _one_line(to_version, "to_version", 120)
    if version_from == version_to:
        raise _fail("update_plan_invalid", "Update versions must differ.")
    companion = "NONE" if target_companion_version is None else _one_line(
        target_companion_version, "target_companion_version", 120
    )
    target_tuple = {
        "context_version": _one_line(target_context_version, "target_context_version", 120),
        "companion_version": companion,
        "project_format": _one_line(target_project_format, "target_project_format", 120),
    }
    matrix = []
    for item in compatibility_matrix:
        if set(item) != {"context_version", "companion_version", "project_format"}:
            raise _fail("update_plan_invalid", "Compatibility matrix fields differ.")
        matrix.append(
            {
                "companion_version": _one_line(
                    item["companion_version"], "matrix.companion_version", 120
                ),
                "context_version": _one_line(
                    item["context_version"], "matrix.context_version", 120
                ),
                "project_format": _one_line(
                    item["project_format"], "matrix.project_format", 120
                ),
            }
        )
    if target_tuple not in matrix:
        raise _fail("update_compatibility_unsupported", "Target version tuple is unsupported.")
    component_records: list[dict[str, Any]] = []
    total_active = 0
    total_candidate = 0
    names: set[str] = set()
    for component in components:
        if set(component) != {"name", "active_path", "candidate_path", "from_format", "to_format"}:
            raise _fail("update_plan_invalid", "Update component fields differ.")
        name = _identifier(component["name"], "component.name")
        if name in names:
            raise _fail("update_plan_invalid", "Update component names must be unique.")
        names.add(name)
        active = _inside(root, component["active_path"], "active_path")
        candidate = _inside(root, component["candidate_path"], "candidate_path")
        if active == candidate or active in candidate.parents or candidate in active.parents:
            raise _fail("update_path_invalid", "Active and candidate components must be separate.")
        active_capability = classify_path_capability(active)
        candidate_capability = classify_path_capability(candidate)
        if active_capability["status"] != "READABLE" or candidate_capability["status"] != "READABLE":
            raise _fail("update_preflight_failed", "A component path is not safely readable.")
        active_bytes = _tree_bytes(active)
        candidate_bytes = _tree_bytes(candidate)
        total_active += active_bytes
        total_candidate += candidate_bytes
        component_records.append(
            {
                "name": name,
                "active_path": str(active),
                "candidate_path": str(candidate),
                "from_format": _one_line(component["from_format"], "from_format", 120),
                "to_format": _one_line(component["to_format"], "to_format", 120),
                "active_bytes": active_bytes,
                "candidate_bytes": candidate_bytes,
                "active_digest": _tree_digest(active),
                "candidate_digest": _tree_digest(candidate),
            }
        )
    required = total_active + total_candidate + max(16 * 1_048_576, (total_active + total_candidate) // 10)
    available = shutil.disk_usage(root).free if available_bytes is None else available_bytes
    if isinstance(available, bool) or not isinstance(available, int) or available < 0:
        raise _fail("update_plan_invalid", "available_bytes is invalid.")
    if available < required:
        raise _fail("update_disk_space_insufficient", "Backup and staging space is insufficient.")
    core = {
        "format": PLAN_FORMAT,
        "format_version": 1,
        "update_root": str(root),
        "from_version": version_from,
        "to_version": version_to,
        "components": component_records,
        "compatibility_target": target_tuple,
        "compatibility_matrix_digest": _value_digest(matrix),
        "changelog": _bounded_lines(changelog, "changelog"),
        "risks": _bounded_lines(risks, "risks"),
        "required_bytes": required,
        "available_bytes": available,
        "writes_performed": False,
    }
    plan_id = f"UPDATE-{_value_digest(core)[:24].upper()}"
    value = core | {
        "plan_id": plan_id,
        "backup_path": str(root / ".opencntx-update" / "backups" / plan_id),
        "rollback_boundary": "Keep verified backup until explicit acceptance and retention cleanup.",
    }
    return value | {"plan_digest": _value_digest(value)}


def _validate_plan(plan: Mapping[str, object]) -> dict[str, Any]:
    basis = {key: item for key, item in plan.items() if key != "plan_digest"}
    required = {
        "format",
        "format_version",
        "update_root",
        "from_version",
        "to_version",
        "components",
        "compatibility_target",
        "compatibility_matrix_digest",
        "changelog",
        "risks",
        "required_bytes",
        "available_bytes",
        "writes_performed",
        "plan_id",
        "backup_path",
        "rollback_boundary",
        "plan_digest",
    }
    if (
        set(plan) != required
        or plan.get("format") != PLAN_FORMAT
        or plan.get("format_version") != 1
        or plan.get("writes_performed") is not False
        or plan.get("plan_digest") != _value_digest(basis)
        or not isinstance(plan.get("components"), list)
    ):
        raise _fail("update_plan_invalid", "Update plan is invalid.")
    return dict(plan)


def _copy_or_verify(source: Path, target: Path, expected_digest: str) -> None:
    if target.exists():
        if _tree_digest(target) != expected_digest:
            raise _fail("update_backup_invalid", "Existing update copy differs.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    if _tree_digest(target) != expected_digest:
        raise _fail("update_backup_invalid", "Update copy is not byte-equal.")


def _write_journal(state_root: Path, plan: Mapping[str, object], phase: str) -> None:
    value = {
        "format": "opencntx-update-journal",
        "format_version": 1,
        "plan_id": plan["plan_id"],
        "plan_digest": plan["plan_digest"],
        "phase": phase,
    }
    value["journal_digest"] = _value_digest(value)
    _write_atomic(state_root / "journal.json", _pretty(value))


def _recover_unlocked(plan: Mapping[str, object], state_root: Path) -> dict[str, Any]:
    backup = Path(str(plan["backup_path"]))
    retired_root = state_root / "retired" / str(plan["plan_id"])
    staging_root = state_root / "staging" / str(plan["plan_id"])
    restored: list[str] = []
    components = plan.get("components")
    if not isinstance(components, list) or not all(isinstance(item, dict) for item in components):
        raise _fail("update_plan_invalid", "Update components are invalid.")
    for item in reversed(components):
        name = item["name"]
        active = Path(item["active_path"])
        retired = retired_root / name
        original = backup / name
        if retired.exists():
            if active.exists():
                shutil.rmtree(active)
            os.replace(retired, active)
            restored.append(name)
        elif active.exists() and _tree_digest(active) == item["candidate_digest"] and original.exists():
            shutil.rmtree(active)
            shutil.copytree(original, active)
            restored.append(name)
        if active.exists() and original.exists() and _tree_digest(active) != item["active_digest"]:
            raise _fail("update_rollback_failed", "Active component could not be restored.")
    shutil.rmtree(staging_root, ignore_errors=True)
    shutil.rmtree(retired_root, ignore_errors=True)
    _write_journal(state_root, plan, "ROLLED_BACK")
    result = {
        "format": "opencntx-update-recovery",
        "format_version": 1,
        "plan_id": plan["plan_id"],
        "status": "ROLLED_BACK",
        "restored_components": sorted(restored),
        "backup_path": str(backup),
    }
    return result | {"recovery_digest": _value_digest(result)}


def recover_interrupted_update(plan: Mapping[str, object]) -> dict[str, Any]:
    """Restore a plan left between staging and completion."""
    selected = _validate_plan(plan)
    root = Path(str(selected["update_root"])).resolve(strict=True)
    state_root = root / ".opencntx-update"
    state_root.mkdir(exist_ok=True)
    with _writer_lock(state_root / "writer.lock"):
        return _recover_unlocked(selected, state_root)


def apply_update_plan(
    plan: Mapping[str, object],
    *,
    approval: str,
    fault_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Apply one exact approved plan with verified backup, rollback, and replay."""
    selected = _validate_plan(plan)
    expected_approval = f"APPLY UPDATE {selected['plan_digest']}"
    if approval != expected_approval:
        raise _fail("update_approval_missing", "Exact update-plan approval is required.")
    root = Path(str(selected["update_root"])).resolve(strict=True)
    state_root = root / ".opencntx-update"
    state_root.mkdir(exist_ok=True)
    receipt_path = state_root / "receipts" / f"{selected['plan_id']}.json"
    with _writer_lock(state_root / "writer.lock"):
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt_basis = {key: value for key, value in receipt.items() if key != "receipt_digest"}
            if (
                receipt.get("format") != RECEIPT_FORMAT
                or receipt.get("plan_digest") != selected["plan_digest"]
                or receipt.get("receipt_digest") != _value_digest(receipt_basis)
            ):
                raise _fail("update_receipt_invalid", "Existing update receipt differs.")
            if any(
                _tree_digest(Path(item["active_path"])) != item["candidate_digest"]
                for item in selected["components"]
            ):
                raise _fail("update_postflight_failed", "Completed update active state drifted.")
            return receipt
        journal_path = state_root / "journal.json"
        retired_root = state_root / "retired" / str(selected["plan_id"])
        staging_root = state_root / "staging" / str(selected["plan_id"])
        if journal_path.exists() and (retired_root.exists() or staging_root.exists()):
            _recover_unlocked(selected, state_root)
        for item in selected["components"]:
            active = Path(item["active_path"])
            candidate = Path(item["candidate_path"])
            if _tree_digest(active) != item["active_digest"] or _tree_digest(candidate) != item["candidate_digest"]:
                raise _fail("update_source_drift", "Active or candidate component changed after preview.")
        if shutil.disk_usage(root).free < selected["required_bytes"]:
            raise _fail("update_disk_space_insufficient", "Current free space is below the plan bound.")
        backup = Path(str(selected["backup_path"]))
        switched: list[dict[str, Any]] = []
        try:
            for item in selected["components"]:
                name = item["name"]
                active = Path(item["active_path"])
                candidate = Path(item["candidate_path"])
                _copy_or_verify(active, backup / name, item["active_digest"])
                if fault_hook is not None:
                    fault_hook(f"AFTER_BACKUP:{name}")
                _copy_or_verify(candidate, staging_root / name, item["candidate_digest"])
                if fault_hook is not None:
                    fault_hook(f"AFTER_STAGING:{name}")
            _write_journal(state_root, selected, "STAGED_VERIFIED")
            for item in selected["components"]:
                name = item["name"]
                active = Path(item["active_path"])
                retired = retired_root / name
                retired.parent.mkdir(parents=True, exist_ok=True)
                os.replace(active, retired)
                switched.append(item)
                _write_journal(state_root, selected, f"RETIRED:{name}")
                if fault_hook is not None:
                    fault_hook(f"AFTER_RETIRE:{name}")
                os.replace(staging_root / name, active)
                _write_journal(state_root, selected, f"ACTIVATED:{name}")
                if fault_hook is not None:
                    fault_hook(f"AFTER_ACTIVATE:{name}")
            for item in selected["components"]:
                if _tree_digest(Path(item["active_path"])) != item["candidate_digest"]:
                    raise _fail("update_postflight_failed", "Active target digest differs after cutover.")
            shutil.rmtree(staging_root, ignore_errors=True)
            shutil.rmtree(retired_root, ignore_errors=True)
            receipt = {
                "format": RECEIPT_FORMAT,
                "format_version": 1,
                "plan_id": selected["plan_id"],
                "plan_digest": selected["plan_digest"],
                "from_version": selected["from_version"],
                "to_version": selected["to_version"],
                "backup_path": str(backup),
                "backup_digest": _tree_digest(backup),
                "component_results": [
                    {
                        "name": item["name"],
                        "active_digest": _tree_digest(Path(item["active_path"])),
                        "expected_target_digest": item["candidate_digest"],
                    }
                    for item in selected["components"]
                ],
                "staging_residue": False,
                "retired_residue": False,
                "status": "COMPLETED",
                "rollback_boundary": selected["rollback_boundary"],
            }
            receipt["receipt_digest"] = _value_digest(receipt)
            _write_atomic(receipt_path, _pretty(receipt))
            _write_journal(state_root, selected, "COMPLETED")
            return receipt
        except BaseException:
            for item in reversed(switched):
                name = item["name"]
                active = Path(item["active_path"])
                retired = retired_root / name
                original = backup / name
                if active.exists():
                    shutil.rmtree(active)
                if retired.exists():
                    os.replace(retired, active)
                elif original.exists():
                    shutil.copytree(original, active)
            shutil.rmtree(staging_root, ignore_errors=True)
            shutil.rmtree(retired_root, ignore_errors=True)
            _write_journal(state_root, selected, "ROLLED_BACK")
            raise


def update_postflight(plan: Mapping[str, object]) -> dict[str, Any]:
    """Prove one target combination is active with no transient old/new mixture."""
    selected = _validate_plan(plan)
    root = Path(str(selected["update_root"])).resolve(strict=True)
    state_root = root / ".opencntx-update"
    receipt_path = state_root / "receipts" / f"{selected['plan_id']}.json"
    receipt_exists = receipt_path.is_file()
    active = [
        {
            "name": item["name"],
            "digest": _tree_digest(Path(item["active_path"])),
            "expected": item["candidate_digest"],
        }
        for item in selected["components"]
    ]
    staging = state_root / "staging" / str(selected["plan_id"])
    retired = state_root / "retired" / str(selected["plan_id"])
    backup = Path(str(selected["backup_path"]))
    status = (
        "GREEN"
        if receipt_exists
        and backup.is_dir()
        and all(item["digest"] == item["expected"] for item in active)
        and not staging.exists()
        and not retired.exists()
        else "REPAIR_REQUIRED"
    )
    value = {
        "format": "opencntx-update-postflight",
        "format_version": 1,
        "plan_id": selected["plan_id"],
        "status": status,
        "active_components": active,
        "backup_isolated": backup.is_dir(),
        "receipt_exists": receipt_exists,
        "staging_residue": staging.exists(),
        "retired_residue": retired.exists(),
    }
    return value | {"postflight_digest": _value_digest(value)}
