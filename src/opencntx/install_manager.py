"""Independent, journaled OPENCNTX installation management.

The entry point is intentionally separate from the main CLI.  A candidate can
therefore be run with ``pipx run`` to inspect, update, resume, or repair an
older installation even when that installation cannot import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .installation import InstallationError, file_sha256, inspect_runtime, verify_runtime


class InstallManagerError(RuntimeError):
    """The requested managed installation transition could not be completed."""


_FORMAT = "opencntx-managed-install-v1"
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
_TERMINAL = {"NEW_HEALTHY", "OLD_RESTORED", "RECOVERY_REQUIRED"}
_OWNER_MARKER = "OWNED-BY-OPENCNTX"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _pretty(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def default_state_root() -> Path:
    """Return a per-user state root without importing platform-specific packages."""
    if os.name == "nt":
        parent = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return parent / "OPENCNTX" / "install-manager"
    parent = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return parent / "opencntx" / "install-manager"


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _ensure_state_root(state_root: Path) -> None:
    marker = state_root / _OWNER_MARKER
    if state_root.exists():
        if not state_root.is_dir() or state_root.is_symlink():
            raise InstallManagerError("The installation state root is not a safe directory.")
        if any(state_root.iterdir()) and not marker.is_file():
            raise InstallManagerError("The non-empty installation state root is not product-owned.")
    else:
        state_root.mkdir(parents=True)
    if not marker.exists():
        _write_atomic(marker, b"opencntx-install-manager-v1\n")


def _run(command: Sequence[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallManagerError("The package-manager command could not complete.") from exc


def _pipx_inventory() -> dict[str, Any] | None:
    executable = shutil.which("pipx")
    if executable is None:
        return None
    result = _run([executable, "list", "--json"], timeout=60)
    if result.returncode:
        raise InstallManagerError("pipx inventory failed.")
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise InstallManagerError("pipx returned invalid inventory JSON.") from exc
    return value if isinstance(value, dict) else None


def _pipx_record(inventory: dict[str, Any] | None) -> dict[str, Any] | None:
    if inventory is None:
        return None
    try:
        value = inventory["venvs"]["opencntx"]["metadata"]
        package = value["main_package"]
    except (KeyError, TypeError):
        return None
    paths: list[str] = []
    for item in package.get("app_paths", []):
        if isinstance(item, dict) and isinstance(item.get("__Path__"), str):
            paths.append(item["__Path__"])
    app = next(
        (item for item in paths if Path(item).stem.casefold() == "opencntx"),
        paths[0] if paths else None,
    )
    if not isinstance(app, str):
        return None
    environment = Path(app).parent.parent
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return {
        "owner": "PIPX",
        "version": package.get("package_version"),
        "package_or_url": package.get("package_or_url"),
        "python": str(python),
        "executable": app,
        "source_interpreter": (value.get("source_interpreter") or {}).get("__Path__"),
        "pinned": bool(package.get("pinned")),
    }


def installation_status(*, python: Path | None = None) -> dict[str, Any]:
    """Inspect package ownership and executable identity without writing."""
    # An explicit interpreter is the complete target identity.  Never replace
    # it with an unrelated pipx environment merely because pipx is available.
    pipx = None if python is not None else _pipx_record(_pipx_inventory())
    selected = python or (Path(pipx["python"]) if pipx else None)
    if selected is None:
        # The manager itself can be running from a temporary ``pipx run``
        # environment.  That is bootstrap tooling, not the persistent target.
        runtime: dict[str, Any] = {"owner": "ABSENT", "packages": [], "python": None}
    else:
        try:
            runtime = inspect_runtime(selected)
        except InstallationError as exc:
            runtime = {"python": str(selected), "owner": "UNREADABLE", "error": str(exc)}
    owner = pipx or {
        "owner": runtime.get("owner", "ABSENT"),
        "version": (runtime.get("packages") or [{}])[0].get("version"),
        "python": runtime.get("python") or str(selected or sys.executable),
        "executable": None,
    }
    return {
        "format": _FORMAT,
        "action": "status",
        "owner": owner,
        "runtime": runtime,
        "supported_route": owner["owner"] in {"PIPX", "PIP_VENV", "ABSENT"},
        "writes_performed": False,
    }


def installation_inventory(
    *,
    python: Path | None = None,
    project_roots: Sequence[Path] = (),
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Build a bounded read-only owner, writer, state, and cleanup inventory."""
    status = installation_status(python=python)
    projects: list[dict[str, Any]] = []
    for raw_root in project_roots:
        try:
            root = raw_root.expanduser().resolve(strict=True)
        except OSError as exc:
            raise InstallManagerError(f"Project root cannot be inspected: {raw_root}") from exc
        if not root.is_dir() or root.is_symlink():
            raise InstallManagerError(f"Project root is not a safe local directory: {raw_root}")
        store = root / ".opencntx"
        format_name = "ABSENT"
        format_version: int | None = None
        manifest = store / "manifest.json"
        if manifest.is_file():
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
                format_name = str(value.get("format", "UNKNOWN"))
                raw_version = value.get("format_version")
                format_version = raw_version if isinstance(raw_version, int) else None
            except (OSError, UnicodeError, ValueError):
                format_name = "UNREADABLE"
        locks = []
        if store.is_dir():
            locks = [
                path.relative_to(root).as_posix()
                for path in sorted(store.rglob("*.lock"))
                if path.is_file() and not path.is_symlink()
            ][:100]
        projects.append(
            {
                "root": str(root),
                "state_path": str(store),
                "state_format": format_name,
                "state_format_version": format_version,
                "writer_markers": locks,
                "writer_activity": "UNKNOWN" if locks else "NONE_OBSERVED",
                "rules_and_hooks": "USER_OWNED_UNLESS_PROVEN_GENERATED",
                "cleanup_authority": "NONE_DURING_INVENTORY",
            }
        )
    selected_state = (state_root or default_state_root()).expanduser().absolute()
    pending: list[dict[str, str]] = []
    journals = selected_state / "journals"
    if journals.is_dir():
        for path in sorted(journals.glob("*.json"))[-100:]:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                pending.append({"path": str(path), "phase": "UNREADABLE"})
                continue
            phase = str(value.get("phase", "UNKNOWN"))
            if phase not in _TERMINAL:
                pending.append({"path": str(path), "phase": phase})
    disk_anchor = selected_state
    while not disk_anchor.exists() and disk_anchor.parent != disk_anchor:
        disk_anchor = disk_anchor.parent
    free_bytes = shutil.disk_usage(disk_anchor).free
    owner = str(status["owner"]["owner"])
    route = {
        "PIPX": "DIRECT_MANAGED",
        "PIP_VENV": "DIRECT_MANAGED",
        "ABSENT": "FRESH_MANAGED",
    }.get(owner, "DIAGNOSIS_ONLY")
    result = {
        "format": "opencntx-installation-inventory",
        "format_version": 1,
        "installation": status,
        "projects": projects,
        "pending_journals": pending,
        "state_root": str(selected_state),
        "available_bytes": free_bytes,
        "ownership_classes": {
            "active_product_owned": [
                value
                for value in (status["owner"].get("python"), status["owner"].get("executable"))
                if value
            ],
            "generated_owned": [str(selected_state)],
            "transient_owned": [str(selected_state / "staging")],
            "rollback_owned": [str(selected_state / "rollback")],
            "historical_owned": [str(selected_state / "journals")],
            "user_owned": [str(item["root"]) for item in projects],
        },
        "compatibility_route": route,
        "proposed_write_set": [
            str(selected_state),
            "the exact package-manager-owned OPENCNTX environment",
        ],
        "writes_performed": False,
    }
    return result | {"inventory_digest": _digest(result)}


def _wheel_version(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise InstallManagerError("The wheel has no unique primary metadata record.")
            metadata = archive.read(names[0]).decode("utf-8", errors="strict")
    except (OSError, UnicodeError, zipfile.BadZipFile) as exc:
        raise InstallManagerError("The candidate is not a readable wheel.") from exc
    versions = [line[9:].strip() for line in metadata.splitlines() if line.startswith("Version: ")]
    names = [
        line[6:].strip().lower() for line in metadata.splitlines() if line.startswith("Name: ")
    ]
    if names != ["opencntx"] or len(versions) != 1:
        raise InstallManagerError("The wheel metadata does not identify one OPENCNTX version.")
    return versions[0]


def _copy_artifact(source: str, destination: Path) -> None:
    parsed = urllib.parse.urlparse(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if parsed.scheme in {"http", "https"}:
        if parsed.scheme != "https" or parsed.hostname not in {
            "github.com",
            "objects.githubusercontent.com",
        }:
            raise InstallManagerError("Remote artifacts must use an approved GitHub HTTPS host.")
        request = urllib.request.Request(source, headers={"User-Agent": "opencntx-install/1"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                final = urllib.parse.urlparse(response.geturl())
                if final.scheme != "https" or final.hostname not in {
                    "github.com",
                    "objects.githubusercontent.com",
                    "release-assets.githubusercontent.com",
                }:
                    raise InstallManagerError(
                        "The artifact redirect left the approved GitHub hosts."
                    )
                with destination.open("xb") as target:
                    remaining = _MAX_DOWNLOAD_BYTES + 1
                    while remaining:
                        chunk = response.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        target.write(chunk)
                        remaining -= len(chunk)
                    if remaining == 0 and response.read(1):
                        raise InstallManagerError("The artifact exceeds the download byte limit.")
        except (InstallManagerError, OSError, urllib.error.URLError) as exc:
            destination.unlink(missing_ok=True)
            if isinstance(exc, InstallManagerError):
                raise
            raise InstallManagerError("The candidate artifact could not be downloaded.") from exc
        return
    local = Path(source).expanduser().resolve(strict=True)
    if not local.is_file():
        raise InstallManagerError("The candidate artifact is not a regular file.")
    shutil.copyfile(local, destination)


def _stage_artifact(source: str, destination: Path, expected_sha256: str, version: str) -> str:
    if len(expected_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_sha256
    ):
        raise InstallManagerError("Expected SHA-256 must be 64 lowercase hexadecimal characters.")
    _copy_artifact(source, destination)
    actual = file_sha256(destination)
    if actual != expected_sha256:
        destination.unlink(missing_ok=True)
        raise InstallManagerError("The candidate artifact SHA-256 does not match.")
    if _wheel_version(destination) != version:
        destination.unlink(missing_ok=True)
        raise InstallManagerError(
            "The candidate wheel version does not match the requested version."
        )
    return actual


def _latest_journal(state_root: Path, plan_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    journals = state_root / "journals"
    candidates = [journals / f"{plan_id}.json"] if plan_id else list(journals.glob("*.json"))
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise InstallManagerError("The managed installation journal is unreadable.") from exc
        if value.get("format") != _FORMAT or value.get("plan_digest") != _digest(
            {
                key: item
                for key, item in value.items()
                if key not in {"plan_digest", "phase", "result"}
            }
        ):
            raise InstallManagerError("The managed installation journal identity is invalid.")
        loaded.append((path, value))
    if loaded:
        return max(loaded, key=lambda item: int(item[1].get("created_ns", -1)))
    raise InstallManagerError("No matching managed installation journal exists.")


def _save_journal(
    path: Path, journal: dict[str, Any], *, phase: str, result: dict[str, Any] | None = None
) -> None:
    value = dict(journal)
    value["phase"] = phase
    value["result"] = result
    _write_atomic(path, _pretty(value))


def _manager_command(owner: str, python: Path, wheel: Path) -> list[str]:
    if owner == "PIPX":
        executable = shutil.which("pipx")
        if executable is None:
            raise InstallManagerError("The recorded pipx owner is no longer available.")
        return [executable, "install", "--force", str(wheel)]
    if owner in {"PIP_VENV", "ABSENT"}:
        if owner == "ABSENT":
            executable = shutil.which("pipx")
            if executable is None:
                raise InstallManagerError("Fresh managed installation requires pipx.")
            return [executable, "install", str(wheel)]
        return [str(python), "-I", "-B", "-m", "pip", "install", "--upgrade", str(wheel)]
    raise InstallManagerError(f"Installation owner {owner!r} is diagnosis-only.")


def _restore_command(journal: dict[str, Any]) -> list[str]:
    return _manager_command(
        str(journal["owner"]),
        Path(str(journal["python"])),
        Path(str(journal["rollback_artifact"])),
    )


def _execute(command: list[str], message: str) -> None:
    result = _run(command)
    if result.returncode:
        raise InstallManagerError(f"{message} exited {result.returncode}.")


def _resolved_python() -> Path:
    current = _pipx_record(_pipx_inventory())
    if current:
        return Path(current["python"])
    return Path(sys.executable)


def _verification_python(journal: dict[str, Any]) -> Path:
    """Resolve the activated target without confusing a bootstrap runner for it."""
    if journal.get("owner") == "PIP_VENV":
        return Path(str(journal["python"]))
    return _resolved_python()


def _restore(journal_path: Path, journal: dict[str, Any], cause: str) -> dict[str, Any]:
    result: dict[str, Any]
    rollback = Path(str(journal.get("rollback_artifact", "")))
    previous = str(journal.get("from_version") or "")
    if not previous and journal.get("owner") == "ABSENT":
        executable = shutil.which("pipx")
        if executable is None:
            result = {"status": "RECOVERY_REQUIRED", "cause": cause, "rollback_artifact": None}
            _save_journal(journal_path, journal, phase="RECOVERY_REQUIRED", result=result)
            return result
        removal = _run([executable, "uninstall", "opencntx"])
        if removal.returncode not in {0, 1}:
            result = {"status": "RECOVERY_REQUIRED", "cause": cause, "rollback_artifact": None}
            _save_journal(journal_path, journal, phase="RECOVERY_REQUIRED", result=result)
            return result
        result = {"status": "OLD_RESTORED", "cause": cause, "previous_state": "ABSENT"}
        _save_journal(journal_path, journal, phase="OLD_RESTORED", result=result)
        return result
    if not previous or not rollback.is_file():
        result = {"status": "RECOVERY_REQUIRED", "cause": cause, "rollback_artifact": str(rollback)}
        _save_journal(journal_path, journal, phase="RECOVERY_REQUIRED", result=result)
        return result
    try:
        _execute(_restore_command(journal), "Offline rollback")
        health = verify_runtime(_verification_python(journal), expected_version=previous)
    except (InstallManagerError, InstallationError) as exc:
        result = {
            "status": "RECOVERY_REQUIRED",
            "cause": cause,
            "rollback_error": str(exc),
            "rollback_artifact": str(rollback),
        }
        _save_journal(journal_path, journal, phase="RECOVERY_REQUIRED", result=result)
        return result
    result = {"status": "OLD_RESTORED", "cause": cause, "health": health}
    _save_journal(journal_path, journal, phase="OLD_RESTORED", result=result)
    candidate = Path(str(journal.get("candidate_artifact", "")))
    artifacts = journal_path.parent.parent / "artifacts"
    try:
        candidate.relative_to(artifacts)
    except ValueError:
        pass
    else:
        if candidate.is_file() and file_sha256(candidate) == journal.get("candidate_sha256"):
            candidate.unlink()
            marker = candidate.parent / _OWNER_MARKER
            if marker.is_file():
                marker.unlink()
                candidate.parent.rmdir()
    return result


def _cleanup_owned(
    state_root: Path, *, keep_plan_id: str, keep_artifact: Path | None = None
) -> dict[str, Any]:
    removed: list[str] = []
    staging = state_root / "staging"
    if staging.is_dir():
        for path in staging.iterdir():
            if path.is_dir() and (path / "OWNED-BY-OPENCNTX").is_file():
                shutil.rmtree(path)
                removed.append(path.relative_to(state_root).as_posix())
    journals = sorted(
        (state_root / "journals").glob("*.json"), key=lambda item: item.stat().st_mtime
    )
    terminal = []
    for path in journals:
        try:
            phase = json.loads(path.read_text(encoding="utf-8")).get("phase")
        except (OSError, ValueError):
            continue
        if phase in _TERMINAL and path.stem != keep_plan_id:
            terminal.append(path)
    # The active plan becomes the newest terminal journal immediately after
    # cleanup, so retain at most nine other completed cycles.
    for path in terminal[:-9]:
        path.unlink()
        removed.append(path.relative_to(state_root).as_posix())
    artifacts = state_root / "artifacts"
    if artifacts.is_dir() and keep_artifact is not None:
        for path in artifacts.iterdir():
            if path.is_dir() and path != keep_artifact.parent and (path / _OWNER_MARKER).is_file():
                shutil.rmtree(path)
                removed.append(path.relative_to(state_root).as_posix())
    return {"removed_owned_paths": removed, "retained_terminal_journals": min(len(terminal), 9) + 1}


def managed_update(
    *,
    artifact: str,
    sha256: str,
    version: str,
    rollback_artifact: str | None,
    rollback_sha256: str | None,
    state_root: Path,
    python: Path | None = None,
) -> dict[str, Any]:
    """Stage, activate, verify, and if necessary independently restore one installation."""
    state_root = state_root.expanduser().absolute()
    status = installation_status(python=python)
    owner = str(status["owner"]["owner"])
    if not status["supported_route"]:
        raise InstallManagerError(f"Installation owner {owner!r} is diagnosis-only.")
    selected_python = Path(str(status["owner"]["python"]))
    from_version = status["owner"].get("version")
    if from_version == version:
        health = verify_runtime(selected_python, expected_version=version)
        return {"status": "NEW_HEALTHY", "reused": True, "health": health}
    if from_version and (not rollback_artifact or not rollback_sha256):
        raise InstallManagerError(
            "An existing installation requires an offline rollback wheel and SHA-256."
        )
    _ensure_state_root(state_root)
    created_ns = time.time_ns()
    seed = {
        "from_version": from_version,
        "to_version": version,
        "artifact_sha256": sha256,
        "created_ns": created_ns,
    }
    plan_id = _digest(seed)[:24]
    plan_root = state_root / "staging" / plan_id
    plan_root.mkdir(parents=True, exist_ok=False)
    _write_atomic(plan_root / _OWNER_MARKER, b"opencntx-install-manager-v1\n")
    staged_candidate = plan_root / f"opencntx-{version}-py3-none-any.whl"
    try:
        _stage_artifact(artifact, staged_candidate, sha256, version)
    except Exception:
        shutil.rmtree(plan_root)
        raise
    rollback = state_root / "rollback" / f"opencntx-{from_version}-py3-none-any.whl"
    staged_rollback: Path | None = None
    if from_version and (not rollback.is_file() or file_sha256(rollback) != rollback_sha256):
        staged_rollback = plan_root / f"rollback-opencntx-{from_version}.whl"
        try:
            _stage_artifact(
                str(rollback_artifact), staged_rollback, str(rollback_sha256), str(from_version)
            )
        except Exception:
            shutil.rmtree(plan_root)
            raise
    candidate_directory = state_root / "artifacts" / f"{version}-{sha256[:12]}"
    candidate = candidate_directory / f"opencntx-{version}-py3-none-any.whl"
    if candidate_directory.exists() and not (candidate_directory / _OWNER_MARKER).is_file():
        shutil.rmtree(plan_root)
        raise InstallManagerError("The managed candidate cache directory is not product-owned.")
    if not candidate_directory.exists():
        candidate_directory.mkdir(parents=True)
        _write_atomic(candidate_directory / _OWNER_MARKER, b"opencntx-install-manager-v1\n")
    candidate_created = False
    try:
        if candidate.is_file():
            if file_sha256(candidate) != sha256:
                raise InstallManagerError("The managed candidate cache has conflicting content.")
            staged_candidate.unlink()
        else:
            os.replace(staged_candidate, candidate)
            candidate_created = True
        if staged_rollback is not None:
            rollback.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_rollback, rollback)
    except Exception:
        if candidate_created:
            candidate.unlink(missing_ok=True)
            (candidate_directory / _OWNER_MARKER).unlink(missing_ok=True)
            candidate_directory.rmdir()
        shutil.rmtree(plan_root)
        raise
    journal_base = {
        "format": _FORMAT,
        "plan_id": plan_id,
        "created_ns": created_ns,
        "owner": owner,
        "python": str(selected_python),
        "executable": status["owner"].get("executable"),
        "from_version": from_version,
        "to_version": version,
        "candidate_artifact": str(candidate),
        "candidate_sha256": sha256,
        "rollback_artifact": str(rollback) if from_version else None,
        "rollback_sha256": rollback_sha256 if from_version else None,
    }
    journal_base["plan_digest"] = _digest(journal_base)
    journal_path = state_root / "journals" / f"{plan_id}.json"
    _save_journal(journal_path, journal_base, phase="STAGED")
    try:
        _save_journal(journal_path, journal_base, phase="ACTIVATING")
        _execute(_manager_command(owner, selected_python, candidate), "Candidate activation")
        _save_journal(journal_path, journal_base, phase="VERIFYING")
        health = verify_runtime(_verification_python(journal_base), expected_version=version)
    except (InstallManagerError, InstallationError) as exc:
        return _restore(journal_path, journal_base, str(exc))
    cleanup = _cleanup_owned(state_root, keep_plan_id=plan_id, keep_artifact=candidate)
    result = {"status": "NEW_HEALTHY", "reused": False, "health": health, "cleanup": cleanup}
    _save_journal(journal_path, journal_base, phase="NEW_HEALTHY", result=result)
    return result


def resume_update(*, state_root: Path, plan_id: str | None = None) -> dict[str, Any]:
    """Resolve an interrupted update from a fresh process using its durable journal."""
    state_root = state_root.expanduser().absolute()
    path, journal = _latest_journal(state_root, plan_id)
    phase = str(journal.get("phase"))
    result = journal.get("result")
    if phase in _TERMINAL and isinstance(result, dict):
        return result
    try:
        health = verify_runtime(
            _verification_python(journal), expected_version=str(journal["to_version"])
        )
    except (InstallationError, InstallManagerError) as exc:
        return _restore(path, journal, f"Interrupted update recovery: {exc}")
    cleanup = _cleanup_owned(
        state_root,
        keep_plan_id=str(journal["plan_id"]),
        keep_artifact=Path(str(journal["candidate_artifact"])),
    )
    result = {"status": "NEW_HEALTHY", "reused": True, "health": health, "cleanup": cleanup}
    _save_journal(path, journal, phase="NEW_HEALTHY", result=result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opencntx-install",
        description="Inspect and manage one OPENCNTX installation with verified rollback.",
    )
    parser.add_argument("--state-root", type=Path, default=default_state_root())
    parser.add_argument("--python", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    status = commands.add_parser(
        "status", help="read-only installation owner and runtime inventory"
    )
    status.add_argument("--project", action="append", type=Path, default=[])
    for name in ("install", "update"):
        command = commands.add_parser(name, help=f"stage, activate, and verify a managed {name}")
        command.add_argument("--artifact", required=True)
        command.add_argument("--sha256", required=True)
        command.add_argument("--version", required=True)
        command.add_argument("--rollback-artifact")
        command.add_argument("--rollback-sha256")
    for name in ("resume", "repair"):
        command = commands.add_parser(name, help=f"{name} from a durable installation journal")
        command.add_argument("--plan-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "status":
            result = installation_inventory(
                python=args.python,
                project_roots=args.project,
                state_root=args.state_root,
            )
        elif args.action in {"install", "update"}:
            result = managed_update(
                artifact=args.artifact,
                sha256=args.sha256,
                version=args.version,
                rollback_artifact=args.rollback_artifact,
                rollback_sha256=args.rollback_sha256,
                state_root=args.state_root,
                python=args.python,
            )
        else:
            result = resume_update(state_root=args.state_root, plan_id=args.plan_id)
    except (InstallManagerError, InstallationError, OSError, ValueError) as exc:
        print(f"Managed installation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") != "RECOVERY_REQUIRED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
