"""Optional filtered Git/GitHub replica for the canonical local continuity store."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .continuity import ContinuityError, health_report, store_path
from .security import CONFIDENCE_HIGH, CONFIDENCE_WARNING, scan_text

SAFE_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,119}\Z")
CREDENTIAL_URL = re.compile(r"^[a-z][a-z0-9+.-]*://[^/@\s]+:[^/@\s]+@", re.IGNORECASE)
SYNC_SUFFIXES = frozenset({".json", ".jsonl", ".md"})
CHECKPOINT_POLICY = "EVERY_CHECKPOINT"
LEGACY_CONFIG_FIELDS = {
    "branch",
    "config_digest",
    "enabled",
    "format",
    "format_version",
    "private_repository_confirmed",
    "remote",
    "repository",
}
CURRENT_CONFIG_FIELDS = LEGACY_CONFIG_FIELDS | {"checkpoint_policy", "migration"}
CHECKPOINT_FIELDS = {
    "checkpoint",
    "checkpoint_digest",
    "completed",
    "current_assignment",
    "flow_status",
    "format",
    "format_version",
    "policy",
    "requested_outcome",
    "state_digest",
}


@dataclass(frozen=True)
class SyncResult:
    status: str
    preview_digest: str
    commit: str | None
    tree: str | None
    file_count: int
    byte_count: int
    remote_head: str | None
    checks: tuple[str, ...]
    checkpoint_policy: str
    trigger: str


def _fail(code: str, message: str) -> ContinuityError:
    return ContinuityError(message, code=code)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _value_digest(value: object) -> str:
    return _digest(_canonical(value))


def _write_atomic(path: Path, value: object) -> None:
    content = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise _fail("continuity_sync_write_failed", "Cannot write sync state.") from exc


def _clear_sync_error(project_root: Path) -> None:
    try:
        (store_path(project_root) / "sync" / "last-error.json").unlink(missing_ok=True)
    except OSError as exc:
        raise _fail("continuity_sync_write_failed", "Cannot clear blocked sync state.") from exc


def _blocked_sync_error(project_root: Path) -> dict[str, Any] | None:
    path = store_path(project_root) / "sync" / "last-error.json"
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail("continuity_sync_config_invalid", "Blocked sync state is invalid.") from exc
    if not isinstance(value, dict):
        raise _fail("continuity_sync_config_invalid", "Blocked sync state is invalid.")
    basis = {key: item for key, item in value.items() if key != "error_digest"}
    if (
        value.get("error_digest") != _value_digest(basis)
        or basis.get("status") != "SYNC_BLOCKED"
        or basis.get("retry") != "NOT_AUTOMATIC"
    ):
        raise _fail("continuity_sync_config_invalid", "Blocked sync state is invalid.")
    return value


def _load_sync_config(project_root: Path, *, migrate: bool) -> dict[str, Any] | None:
    path = store_path(project_root) / "sync" / "config.json"
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail("continuity_sync_config_invalid", "Sync configuration is invalid.") from exc
    if not isinstance(value, dict) or frozenset(value) not in {
        frozenset(LEGACY_CONFIG_FIELDS),
        frozenset(CURRENT_CONFIG_FIELDS),
    }:
        raise _fail("continuity_sync_config_invalid", "Sync configuration fields are invalid.")
    basis = {key: item for key, item in value.items() if key != "config_digest"}
    if (
        value.get("config_digest") != _value_digest(basis)
        or value.get("format") != "opencntx-continuity-sync-config"
        or value.get("format_version") != 1
        or value.get("enabled") is not True
    ):
        raise _fail("continuity_sync_config_invalid", "Sync configuration is invalid.")
    if set(value) == LEGACY_CONFIG_FIELDS:
        normalized = basis | {
            "checkpoint_policy": CHECKPOINT_POLICY,
            "migration": "LEGACY_IMPLICIT_EVERY_CHECKPOINT",
        }
        normalized["config_digest"] = _value_digest(normalized)
        if migrate:
            _write_atomic(path, normalized)
        return normalized
    if (
        value.get("checkpoint_policy") != CHECKPOINT_POLICY
        or value.get("migration") not in {"NONE", "LEGACY_IMPLICIT_EVERY_CHECKPOINT"}
    ):
        raise _fail("continuity_sync_config_invalid", "Checkpoint sync policy is invalid.")
    return value


def _checkpoint(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    record = dict(value)
    basis = {key: item for key, item in record.items() if key != "checkpoint_digest"}
    if (
        set(record) != CHECKPOINT_FIELDS
        or record.get("checkpoint_digest") != _value_digest(basis)
        or record.get("format") != "opencntx-continuity-checkpoint"
        or record.get("format_version") != 1
        or record.get("policy") != CHECKPOINT_POLICY
        or record.get("checkpoint") not in {"PASS", "FAIL", "BLOCKED"}
    ):
        raise _fail("continuity_sync_config_invalid", "Checkpoint record is invalid.")
    return record


def _git() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise _fail("continuity_sync_unavailable", "Git is unavailable.")
    return executable


def _run(arguments: list[str], *, cwd: Path | None = None, allow_failure: bool = False) -> str:
    result = subprocess.run(arguments, cwd=cwd, check=False, capture_output=True, text=True)
    if result.returncode != 0 and not allow_failure:
        raise _fail("continuity_sync_git_failed", "A bounded Git operation failed.")
    return result.stdout.strip()


def _repository(path: Path) -> Path:
    try:
        repository = path.resolve(strict=True)
    except OSError as exc:
        raise _fail(
            "continuity_sync_repository_invalid", "Sync repository is unavailable."
        ) from exc
    if repository.is_symlink() or not repository.is_dir() or not (repository / ".git").exists():
        raise _fail(
            "continuity_sync_repository_invalid", "Sync repository must be a real Git checkout."
        )
    return repository


def _remote(repository: Path, alias: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", alias):
        raise _fail("continuity_sync_remote_invalid", "Remote alias is unsafe.")
    url = _run([_git(), "-C", str(repository), "remote", "get-url", alias])
    if not url or CREDENTIAL_URL.search(url):
        raise _fail(
            "continuity_sync_remote_invalid", "Remote URL is missing or contains credentials."
        )
    return url


def _branch(value: str) -> str:
    if SAFE_BRANCH.fullmatch(value) is None or ".." in value or value.endswith((".", "/")):
        raise _fail("continuity_sync_branch_invalid", "Sync branch is unsafe.")
    return value


def _remote_head(repository: Path, alias: str, branch: str) -> str | None:
    output = _run(
        [_git(), "-C", str(repository), "ls-remote", "--heads", alias, f"refs/heads/{branch}"]
    )
    if not output:
        return None
    fields = output.split()
    if len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{40}", fields[0]):
        raise _fail("continuity_sync_readback_invalid", "Remote head readback is ambiguous.")
    return fields[0]


def _candidates(project_root: Path) -> tuple[str, list[dict[str, Any]]]:
    store = store_path(project_root)
    health = health_report(project_root)
    if health["status"] != "HEALTHY":
        raise _fail("continuity_sync_store_unhealthy", "Local continuity store is not healthy.")
    state = json.loads((store / "state.json").read_text(encoding="utf-8"))
    project_id = str(state["project_id"])
    candidates = []
    for path in sorted(store.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(store).as_posix()
        if relative.startswith("sync/") or path.suffix.lower() not in SYNC_SUFFIXES:
            continue
        content = path.read_bytes()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _fail(
                "continuity_sync_content_blocked", "Sync candidate is not UTF-8 text."
            ) from exc
        findings = scan_text(path=relative, text=text, source_sha256=_digest(content))
        if any(item.confidence in {CONFIDENCE_HIGH, CONFIDENCE_WARNING} for item in findings):
            raise _fail(
                "continuity_sync_content_blocked", "Sync candidate triggered the secret filter."
            )
        candidates.append(
            {
                "source": path,
                "path": f"opencntx/{project_id}/{relative}",
                "bytes": len(content),
                "sha256": _digest(content),
            }
        )
    if not candidates:
        raise _fail("continuity_sync_content_blocked", "No safe sync candidates were found.")
    return project_id, candidates


def build_sync_preview(
    project_root: Path,
    repository_path: Path,
    *,
    remote: str,
    branch: str,
    private_repository_confirmed: bool,
) -> dict[str, Any]:
    """Build a read-only, filtered, conflict-bound replica preview."""
    repository = _repository(repository_path)
    selected_branch = _branch(branch)
    remote_url = _remote(repository, remote)
    local_remote = remote_url.startswith(("file://", "/")) or bool(
        re.match(r"^[A-Za-z]:[\\/]", remote_url)
    )
    if not local_remote and not private_repository_confirmed:
        raise _fail(
            "continuity_sync_visibility_unconfirmed",
            "Remote sync requires explicit confirmation that the destination is private.",
        )
    if _run([_git(), "-C", str(repository), "status", "--porcelain"]):
        raise _fail("continuity_sync_conflict", "Sync repository has local changes.")
    project_id, candidates = _candidates(project_root)
    head = _remote_head(repository, remote, selected_branch)
    candidate_records = [
        {key: item[key] for key in ("path", "bytes", "sha256")} for item in candidates
    ]
    value = {
        "format": "opencntx-continuity-sync-preview",
        "format_version": 1,
        "project_id": project_id,
        "remote": remote,
        "remote_url_digest": _digest(remote_url.encode("utf-8")),
        "branch": selected_branch,
        "expected_remote_head": head,
        "private_repository_confirmed": private_repository_confirmed or local_remote,
        "candidates": candidate_records,
        "file_count": len(candidates),
        "byte_count": sum(item["bytes"] for item in candidates),
        "checks": [
            "LOCAL_STORE_HEALTHY",
            "SYNC_REPOSITORY_CLEAN",
            "REMOTE_URL_HAS_NO_EMBEDDED_CREDENTIAL",
            "PRIVATE_DESTINATION_CONFIRMED",
            "CONTENT_FILTER_GREEN",
            "NON_FORCE_PUSH_ONLY",
            "REMOTE_READBACK_REQUIRED",
        ],
        "writes": [],
    }
    return value | {"preview_digest": _value_digest(value)}


def _materialize(clone: Path, project_id: str, candidates: list[dict[str, Any]]) -> None:
    target_root = (clone / "opencntx" / project_id).resolve()
    target_root.relative_to(clone.resolve())
    if target_root.exists():
        shutil.rmtree(target_root)
    for item in candidates:
        relative = PurePosixPath(str(item["path"]))
        destination = clone.joinpath(*relative.parts)
        resolved_parent = destination.parent.resolve()
        resolved_parent.relative_to(clone.resolve())
        resolved_parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item["source"], destination)


def apply_sync(
    project_root: Path,
    repository_path: Path,
    *,
    remote: str,
    branch: str,
    private_repository_confirmed: bool,
    expected_preview_digest: str,
    checkpoint: Mapping[str, Any] | None = None,
) -> SyncResult:
    """Apply exactly one non-force replica commit and verify the remote head."""
    checkpoint_record = _checkpoint(checkpoint)
    preview = build_sync_preview(
        project_root,
        repository_path,
        remote=remote,
        branch=branch,
        private_repository_confirmed=private_repository_confirmed,
    )
    if preview["preview_digest"] != expected_preview_digest:
        raise _fail("continuity_sync_preview_drift", "Sync preview changed before apply.")
    repository = _repository(repository_path)
    remote_url = _remote(repository, remote)
    project_id, candidates = _candidates(project_root)
    with tempfile.TemporaryDirectory(prefix="opencntx-sync-") as temporary:
        clone = Path(temporary) / "mirror"
        _run([_git(), "clone", "--quiet", remote_url, str(clone)])
        remote_head = preview["expected_remote_head"]
        if remote_head is None:
            _run([_git(), "-C", str(clone), "checkout", "--orphan", branch])
            for path in clone.iterdir():
                if path.name != ".git":
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
        else:
            _run([_git(), "-C", str(clone), "checkout", "-B", branch, remote_head])
        _materialize(clone, project_id, candidates)
        _run([_git(), "-C", str(clone), "add", "--", f"opencntx/{project_id}"])
        staged = _run([_git(), "-C", str(clone), "diff", "--cached", "--name-only"])
        if not staged:
            commit = str(remote_head)
            tree = _run([_git(), "-C", str(clone), "rev-parse", f"{commit}^{{tree}}"])
            status = "UNCHANGED"
        else:
            _run([_git(), "-C", str(clone), "config", "user.name", "OPENCNTX"])
            _run(
                [
                    _git(),
                    "-C",
                    str(clone),
                    "config",
                    "user.email",
                    "opencntx@users.noreply.github.com",
                ]
            )
            _run([_git(), "-C", str(clone), "commit", "--quiet", "-m", "Sync OPENCNTX continuity"])
            commit = _run([_git(), "-C", str(clone), "rev-parse", "HEAD"])
            tree = _run([_git(), "-C", str(clone), "rev-parse", "HEAD^{tree}"])
            _run(
                [
                    _git(),
                    "-C",
                    str(clone),
                    "push",
                    "--porcelain",
                    "origin",
                    f"HEAD:refs/heads/{branch}",
                ]
            )
            status = "SYNCED"
        readback = _remote_head(repository, remote, branch)
        if readback != commit:
            raise _fail("continuity_sync_readback_mismatch", "Remote head differs after sync.")
    receipt = {
        "format": "opencntx-continuity-sync-receipt",
        "format_version": 1,
        "status": status,
        "preview_digest": expected_preview_digest,
        "commit": commit,
        "tree": tree,
        "readback_head": readback,
        "file_count": preview["file_count"],
        "byte_count": preview["byte_count"],
        "checkpoint_policy": CHECKPOINT_POLICY,
        "trigger": "CHECKPOINT" if checkpoint_record is not None else "MANUAL",
        "checkpoint": checkpoint_record,
    }
    receipt["receipt_digest"] = _value_digest(receipt)
    _write_atomic(store_path(project_root) / "sync" / "last-receipt.json", receipt)
    _clear_sync_error(project_root)
    return SyncResult(
        status=status,
        preview_digest=expected_preview_digest,
        commit=commit,
        tree=tree,
        file_count=int(preview["file_count"]),
        byte_count=int(preview["byte_count"]),
        remote_head=readback,
        checks=tuple(preview["checks"]),
        checkpoint_policy=CHECKPOINT_POLICY,
        trigger="CHECKPOINT" if checkpoint_record is not None else "MANUAL",
    )


def configure_sync(
    project_root: Path,
    repository_path: Path,
    *,
    remote: str,
    branch: str,
    private_repository_confirmed: bool,
) -> dict[str, Any]:
    """Store one explicit optional replica policy after a green preview."""
    preview = build_sync_preview(
        project_root,
        repository_path,
        remote=remote,
        branch=branch,
        private_repository_confirmed=private_repository_confirmed,
    )
    config = {
        "format": "opencntx-continuity-sync-config",
        "format_version": 1,
        "repository": str(_repository(repository_path)),
        "remote": remote,
        "branch": branch,
        "private_repository_confirmed": private_repository_confirmed,
        "enabled": True,
        "checkpoint_policy": CHECKPOINT_POLICY,
        "migration": "NONE",
    }
    config["config_digest"] = _value_digest(config)
    _write_atomic(store_path(project_root) / "sync" / "config.json", config)
    _clear_sync_error(project_root)
    return {"status": "CONFIGURED", "preview_digest": preview["preview_digest"]} | config


def sync_configured(
    project_root: Path, *, checkpoint: Mapping[str, Any] | None = None
) -> SyncResult | None:
    """Apply a configured replica once; never retry an external result automatically."""
    config = _load_sync_config(project_root, migrate=True)
    if config is None:
        return None
    if _blocked_sync_error(project_root) is not None:
        return None
    repository = Path(config["repository"])
    preview = build_sync_preview(
        project_root,
        repository,
        remote=config["remote"],
        branch=config["branch"],
        private_repository_confirmed=config["private_repository_confirmed"],
    )
    return apply_sync(
        project_root,
        repository,
        remote=config["remote"],
        branch=config["branch"],
        private_repository_confirmed=config["private_repository_confirmed"],
        expected_preview_digest=preview["preview_digest"],
        checkpoint=checkpoint,
    )


def sync_status(project_root: Path) -> dict[str, Any]:
    store = store_path(project_root)
    config = store / "sync" / "config.json"
    receipt = store / "sync" / "last-receipt.json"
    error = store / "sync" / "last-error.json"
    loaded_config = _load_sync_config(project_root, migrate=False)
    return {
        "configured": config.exists(),
        "checkpoint_policy": loaded_config["checkpoint_policy"] if loaded_config else None,
        "config_migration": loaded_config["migration"] if loaded_config else None,
        "last_receipt": json.loads(receipt.read_text(encoding="utf-8"))
        if receipt.exists()
        else None,
        "last_error": json.loads(error.read_text(encoding="utf-8")) if error.exists() else None,
        "local_truth": "CANONICAL",
    }


def record_sync_error(
    project_root: Path,
    error: ContinuityError,
    *,
    checkpoint: Mapping[str, Any] | None = None,
) -> None:
    """Record one bounded external stop without automatic retry."""
    try:
        if _blocked_sync_error(project_root) is not None:
            return
    except ContinuityError:
        pass
    value = {
        "status": "SYNC_BLOCKED",
        "code": error.code,
        "retry": "NOT_AUTOMATIC",
        "checkpoint_policy": CHECKPOINT_POLICY,
        "checkpoint": _checkpoint(checkpoint),
        "local_flow": "CONTINUES_OFFLINE",
    }
    value["error_digest"] = _value_digest(value)
    _write_atomic(store_path(project_root) / "sync" / "last-error.json", value)
