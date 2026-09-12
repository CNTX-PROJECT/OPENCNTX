"""Inspect installation identity without importing or modifying the target package.

This module deliberately uses only the standard library. It can be invoked by
an independent Python interpreter while an installed OPENCNTX cannot import.
Inspection is not an installation or a claim of supported upgrade compatibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class InstallationError(RuntimeError):
    """An exact runtime could not be inspected or verified."""


_INVENTORY_PROGRAM = r"""
import importlib.metadata as metadata
import json
import pathlib
import sys
import sysconfig

prefix = pathlib.Path(sys.prefix)
distributions = list(metadata.distributions(name="opencntx"))
packages = []
for dist in distributions:
    files = dist.files or []
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    packages.append({
        "version": dist.version,
        "location": str(pathlib.Path(dist.locate_file("")).absolute()),
        "installer": (dist.read_text("INSTALLER") or "unknown").strip(),
        "editable": direct.get("dir_info", {}).get("editable", False),
        "record_available": dist.read_text("RECORD") is not None,
        "record_entries": len(files),
        "source_commit": direct.get("vcs_info", {}).get("commit_id"),
    })
pipx_metadata = prefix / "pipx_metadata.json"
result = {
    "python": sys.executable,
    "python_version": list(sys.version_info[:3]),
    "prefix": str(prefix),
    "base_prefix": sys.base_prefix,
    "scripts": sysconfig.get_path("scripts"),
    "isolated_environment": sys.prefix != sys.base_prefix,
    "pipx_metadata_present": pipx_metadata.is_file(),
    "packages": packages,
}
print(json.dumps(result))
"""


def _run_python(python: Path, arguments: list[str], *, cwd: Path) -> str:
    command = python.absolute()
    if not command.is_file():
        raise InstallationError("The selected Python executable is missing.")
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    try:
        process = subprocess.run(
            [str(command), "-I", "-B", *arguments],
            cwd=cwd,
            env=environment,
            capture_output=True,
            encoding="utf-8",
            errors="strict",
            timeout=60,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise InstallationError("The selected runtime did not complete its probe.") from exc
    if process.returncode:
        # A failing package may print private state. Retain only the exit status.
        raise InstallationError(f"The selected runtime probe exited {process.returncode}.")
    if len(process.stdout) > 1_000_000:
        raise InstallationError("The selected runtime probe output exceeds its bound.")
    return process.stdout


def inspect_runtime(python: Path) -> dict[str, Any]:
    """Identify one exact interpreter, distribution and package-manager owner."""
    with tempfile.TemporaryDirectory(prefix="opencntx-inventory-") as temporary:
        output = _run_python(python, ["-c", _INVENTORY_PROGRAM], cwd=Path(temporary))
    try:
        result = json.loads(output)
        packages = result["packages"]
    except (ValueError, KeyError, TypeError) as exc:
        raise InstallationError("The selected runtime returned an invalid inventory.") from exc
    if len(packages) != 1:
        owner = "ABSENT" if not packages else "AMBIGUOUS"
    elif packages[0]["editable"]:
        owner = "EDITABLE"
    elif result["pipx_metadata_present"]:
        owner = "PIPX"
    elif result["isolated_environment"] and packages[0]["installer"] == "pip":
        owner = "PIP_VENV"
    else:
        owner = "SHARED_OR_UNKNOWN"
    return result | {"owner": owner, "writes_performed": False}


_CONTINUITY_PROGRAM = r"""
import json
from pathlib import Path
from opencntx.continuity import execution_state_capsule, record_execution_checkpoint, start_flow

root = Path.cwd()
(root / "input.txt").write_text("installation sentinel\n", encoding="utf-8")
roadmap = {
    "format": "opencntx-continuity-roadmap", "format_version": 1,
    "project_id": "INSTALL-PROBE", "roadmap_id": "INSTALL-ROADMAP",
    "title": "Installation continuity probe", "assignments": [{
        "id": "PROBE-1", "title": "Verify runtime", "detail": "Retain the active task.",
        "depends_on": [], "touches": ["input.txt"], "conflict": "EXTEND",
        "migration": "Preserve the input.", "definition_of_done": ["Resume verified"]
    }]
}
path = root / "roadmap.json"
path.write_text(json.dumps(roadmap), encoding="utf-8")
start_flow(root, path, "AUTO PILOT")
before = execution_state_capsule(root)
record_execution_checkpoint(
    root, checkpoint_id="INSTALL-CHECK", current_internal_task="VERIFY",
    next_internal_action="Resume the installation probe", evidence_paths=["input.txt"],
    expected_state_digest=before["state_digest"]
)
after = execution_state_capsule(root)
assert after["current_assignment"] == before["current_assignment"]
assert after["checkpoint_number"] == before["checkpoint_number"] + 1
assert (root / "input.txt").read_text(encoding="utf-8") == "installation sentinel\n"
print(json.dumps({"state_digest": after["state_digest"], "checkpoint": after["checkpoint_number"]}))
"""

_RESUME_PROGRAM = r"""
import json
from pathlib import Path
from opencntx.continuity import execution_state_capsule
state = execution_state_capsule(Path.cwd())
print(json.dumps({"state_digest": state["state_digest"], "checkpoint": state["checkpoint_number"]}))
"""


def verify_runtime(python: Path, *, expected_version: str) -> dict[str, Any]:
    """Require import, CLI and a real checkpoint reopened by a second process.

    Only disposable project state is written. No existing user project is changed.
    This does not certify that an existing project has migrated successfully.
    """
    inventory = inspect_runtime(python)
    if len(inventory["packages"]) != 1 or inventory["packages"][0]["version"] != expected_version:
        raise InstallationError("Installed package metadata differs from the expected version.")
    with tempfile.TemporaryDirectory(prefix="opencntx-health-") as temporary:
        root = Path(temporary)
        version = _run_python(python, ["-m", "opencntx", "--version"], cwd=root).strip()
        if version != f"opencntx {expected_version}":
            raise InstallationError("The actual executable version differs from its metadata.")
        help_text = _run_python(python, ["-m", "opencntx", "--help"], cwd=root)
        if "usage:" not in help_text or "opencntx" not in help_text:
            raise InstallationError("The installed CLI did not return its expected help.")
        first = json.loads(_run_python(python, ["-c", _CONTINUITY_PROGRAM], cwd=root))
        resumed = json.loads(_run_python(python, ["-c", _RESUME_PROGRAM], cwd=root))
        if first != resumed or first["checkpoint"] != 1:
            raise InstallationError("A fresh process could not resume the actual checkpoint.")
    return {
        "status": "RUNTIME_HEALTHY",
        "version": expected_version,
        "python": inventory["python"],
        "owner": inventory["owner"],
        "checks": ["metadata", "import-version", "help", "checkpoint", "fresh-process-resume"],
        "existing_projects_verified": False,
    }


def file_sha256(path: Path) -> str:
    """Hash a package without loading the whole artifact into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect an exact OPENCNTX installation.")
    parser.add_argument("action", choices=("inventory", "verify"))
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--expected-version")
    args = parser.parse_args(argv)
    try:
        if args.action == "verify":
            if not args.expected_version:
                parser.error("verify requires --expected-version")
            result = verify_runtime(args.python, expected_version=args.expected_version)
        else:
            result = inspect_runtime(args.python)
    except (InstallationError, ValueError) as exc:
        print(f"Installation check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
