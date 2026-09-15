"""Long 1.8.1 clean-install and 1.8.0-to-1.8.1 transition simulation.

This is an opt-in integration simulator. It creates disposable virtual
environments and disposable projects only; it never touches a registered
project or a persistent OPENCNTX installation.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from opencntx.install_manager import InstallManagerError, managed_update

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=300,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().replace("\n", " ")
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}: {detail}")
    return result.stdout


def _python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _create_venv(parent: Path, name: str, package: Path) -> Path:
    venv = parent / name
    _run([sys.executable, "-I", "-B", "-m", "venv", str(venv)], cwd=parent)
    python = _python(venv)
    _run([str(python), "-I", "-B", "-m", "pip", "install", "--no-deps", str(package)], cwd=parent)
    return python


def _prepare_project(parent: Path, name: str) -> Path:
    project = parent / name
    project.mkdir()
    return project


def _snapshot_sources(project: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(project.rglob("*")):
        if not path.is_file() or ".opencntx" in path.parts or ".git" in path.parts:
            continue
        snapshot[path.relative_to(project).as_posix()] = _sha256(path)
    return snapshot


def _init_and_seed(python: Path, project: Path) -> None:
    _run([str(python), "-I", "-B", "-m", "opencntx", "workspace", "init"], cwd=project)
    _run([str(python), "-I", "-B", "-m", "opencntx", "init"], cwd=project)
    control = project / "CONTROL"
    (control / "10 - ROADMAP.md").write_text(
        "# 10 - ROADMAP\n\nCurrent clean-install transition fixture.\n", encoding="utf-8"
    )
    (control / "ARCHIVE").mkdir()
    (control / "ARCHIVE" / "old-note.md").write_text(
        "# Historical note\n\nRetained outside the active route.\n", encoding="utf-8"
    )
    (project / "README.md").write_text(
        "# Transition fixture\n\nHuman-owned content must remain unchanged.\n", encoding="utf-8"
    )


def _exercise_project(python: Path, project: Path, *, expected_version: str) -> dict[str, Any]:
    version = _run([str(python), "-I", "-B", "-m", "opencntx", "--version"], cwd=project).strip()
    if version != f"opencntx {expected_version}":
        raise RuntimeError(f"Unexpected runtime version: {version}")
    _run([str(python), "-I", "-B", "-m", "opencntx", "pack", "--preview"], cwd=project)
    _run([str(python), "-I", "-B", "-m", "opencntx", "pack"], cwd=project)
    _run([str(python), "-I", "-B", "-m", "opencntx", "verify"], cwd=project)
    _run(
        [
            str(python),
            "-I",
            "-B",
            "-m",
            "opencntx",
            "knowledge",
            "index",
            "build",
            "--root",
            ".",
        ],
        cwd=project,
    )
    preview_text = _run(
        [str(python), "-I", "-B", "-m", "opencntx", "knowledge", "adopt", "--root", "."],
        cwd=project,
    )
    preview = json.loads(preview_text)
    manifest = preview["manifest"]
    written_text = _run(
        [
            str(python),
            "-I",
            "-B",
            "-m",
            "opencntx",
            "knowledge",
            "adopt",
            "--root",
            ".",
            "--write",
            "--expected-manifest-digest",
            manifest["manifest_digest"],
        ],
        cwd=project,
    )
    written = json.loads(written_text)
    if written["manifest"]["manifest_digest"] != manifest["manifest_digest"]:
        raise RuntimeError("Reviewed adoption digest changed during the write")
    footer = _run(
        [
            str(python),
            "-I",
            "-B",
            "-m",
            "opencntx",
            "knowledge",
            "footer",
            "--task-note",
            "transition-test",
            "--status",
            "PASS",
            "--now",
            "SIMULATED",
            "--thereafter",
            "STOP",
        ],
        cwd=project,
    )
    if not footer.endswith("\n") or "**Daarna:** STOP" not in footer:
        raise RuntimeError("Footer contract did not render its final field")
    return {
        "adoption_audit": manifest["audit"]["status"],
        "adoption_findings": len(manifest["audit"]["findings"]),
        "footer_has_final_field": True,
        "version": version,
    }


def _make_broken_candidate(candidate: Path, destination: Path) -> Path:
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(candidate) as source:
        record_name = next(name for name in source.namelist() if name.endswith(".dist-info/RECORD"))
        for name in source.namelist():
            if name != record_name:
                files[name] = source.read(name)
    files["opencntx/__init__.py"] = b"raise RuntimeError('simulated broken activation')\n"
    rows = []
    for name in sorted(files):
        digest = base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest()).decode().rstrip("=")
        rows.append(f"{name},sha256={digest},{len(files[name])}")
    files[record_name] = ("\n".join(rows) + f"\n{record_name},,\n").encode()
    with zipfile.ZipFile(destination, "w") as target:
        for name in sorted(files):
            target.writestr(name, files[name])
    return destination


def _rollback_probe(parent: Path, baseline: Path, candidate: Path) -> dict[str, Any]:
    python = _create_venv(parent, "rollback-venv", baseline)
    broken = _make_broken_candidate(candidate, parent / "broken-1.8.1.whl")
    broken_hash = _sha256(broken)
    baseline_hash = _sha256(baseline)
    result = managed_update(
        artifact=str(broken),
        sha256=broken_hash,
        version="1.8.1",
        rollback_artifact=str(baseline),
        rollback_sha256=baseline_hash,
        state_root=parent / "rollback-state",
        python=python,
    )
    version = _run([str(python), "-I", "-B", "-m", "opencntx", "--version"], cwd=parent).strip()
    if result["status"] != "OLD_RESTORED" or version != "opencntx 1.8.0":
        raise RuntimeError(f"Real candidate rollback did not restore 1.8.0: {result}, {version}")
    return {"status": result["status"], "restored_version": version}


def _blocked_adoption_probe(python: Path, parent: Path) -> dict[str, Any]:
    project = _prepare_project(parent, "blocked-adoption-project")
    _init_and_seed(python, project)
    control = project / "CONTROL"
    (control / "10 - SECOND.md").write_text("# Duplicate ordinal\n", encoding="utf-8")
    with (control / "10 - ROADMAP.md").open("a", encoding="utf-8") as stream:
        stream.write("\n[Missing](missing.md)\n")
    preview = json.loads(
        _run(
            [str(python), "-I", "-B", "-m", "opencntx", "knowledge", "adopt", "--root", "."],
            cwd=project,
        )
    )["manifest"]
    codes = {item["code"] for item in preview["audit"]["findings"]}
    required = {"DUPLICATE_ORDINAL", "UNRESOLVED_LINK"}
    if preview["audit"]["status"] != "BLOCKED" or not required.issubset(codes):
        raise RuntimeError(f"Ambiguous adoption was not blocked: {preview['audit']}")
    return {"status": preview["audit"]["status"], "finding_codes": sorted(codes)}


def _clean_install(parent: Path, candidate: Path) -> dict[str, Any]:
    python = _create_venv(parent, "clean-venv", candidate)
    project = _prepare_project(parent, "clean-project")
    _init_and_seed(python, project)
    before = _snapshot_sources(project)
    exercised = _exercise_project(python, project, expected_version="1.8.1")
    after = _snapshot_sources(project)
    if before != after:
        raise RuntimeError("Clean installation changed human-owned project files")
    return {"human_source_unchanged": True, "runtime": exercised}


def _upgrade_from_180(
    parent: Path,
    baseline: Path,
    candidate: Path,
    cycles: int,
) -> dict[str, Any]:
    python = _create_venv(parent, "upgrade-venv", baseline)
    project = _prepare_project(parent, "upgrade-project")
    _init_and_seed(python, project)
    before = _snapshot_sources(project)
    _run([str(python), "-I", "-B", "-m", "opencntx", "pack"], cwd=project)
    baseline_hash = _sha256(baseline)
    candidate_hash = _sha256(candidate)
    first = managed_update(
        artifact=str(candidate),
        sha256=candidate_hash,
        version="1.8.1",
        rollback_artifact=str(baseline),
        rollback_sha256=baseline_hash,
        state_root=parent / "managed-state",
        python=python,
    )
    if first["status"] != "NEW_HEALTHY":
        raise RuntimeError(f"1.8.0-to-1.8.1 update failed: {first}")
    reapply_statuses = []
    for _ in range(cycles):
        result = managed_update(
            artifact=str(candidate),
            sha256=candidate_hash,
            version="1.8.1",
            rollback_artifact=str(baseline),
            rollback_sha256=baseline_hash,
            state_root=parent / "managed-state",
            python=python,
        )
        reapply_statuses.append((result["status"], bool(result.get("reused"))))
    exercised = _exercise_project(python, project, expected_version="1.8.1")
    blocked = _blocked_adoption_probe(python, parent)
    after = _snapshot_sources(project)
    if before != after:
        raise RuntimeError("Upgrade changed human-owned project files")
    return {
        "human_source_unchanged": True,
        "initial_update": first["status"],
        "reapply_statuses": reapply_statuses,
        "runtime": exercised,
        "blocked_visual_adoption": blocked,
    }


def _lock_probe(parent: Path) -> dict[str, Any]:
    state = parent / "lock-state"
    state.mkdir()
    script = (
        "from pathlib import Path\n"
        "import sys\n"
        "import time\n"
        "from opencntx.install_manager import _operation_lock\n"
        "with _operation_lock(Path(sys.argv[1])):\n"
        "    print('LOCKED', flush=True)\n"
        "    time.sleep(2)\n"
    )
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"}
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(state)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if child.stdout is not None and child.stdout.readline().strip() == "LOCKED":
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("Lock probe child did not acquire its lock")
        try:
            from opencntx.install_manager import _operation_lock

            with _operation_lock(state):
                raise RuntimeError("The second writer acquired an active lock")
        except InstallManagerError:
            blocked = True
        else:
            blocked = False
    finally:
        child.wait(timeout=20)
    if child.returncode != 0:
        raise RuntimeError("Lock probe child failed")
    return {"second_writer_blocked": blocked, "lock_released_after_process": True}


def run(candidate: Path, baseline: Path, *, cycles: int) -> dict[str, Any]:
    if cycles < 4:
        raise ValueError("At least four same-version reapply cycles are required.")
    with tempfile.TemporaryDirectory(prefix="opencntx-r12-install-") as temporary:
        parent = Path(temporary)
        result = {
            "clean_install": _clean_install(parent, candidate),
            "format": "opencntx-r12-install-simulation",
            "format_version": 1,
            "lock_probe": _lock_probe(parent),
            "status": "PASS",
            "rollback_probe": _rollback_probe(parent, baseline, candidate),
            "upgrade_1_8_0_to_1_8_1": _upgrade_from_180(parent, baseline, candidate, cycles),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=8)
    arguments = parser.parse_args()
    result = run(arguments.candidate.resolve(strict=True), arguments.baseline.resolve(strict=True), cycles=arguments.cycles)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
