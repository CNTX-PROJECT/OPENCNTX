"""Bounded R10 complex flow and layout simulation; not part of default discovery."""

from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from opencntx.continuity import (
    ContinuityError,
    advance_flow,
    export_capsule,
    health_report,
    import_capsule,
    start_flow,
    verify_capsule,
)
from opencntx.continuity_sync import configure_sync, sync_status
from opencntx.host_protocol import claim_host, host_status, resume_host
from opencntx.layout_plan import MANIFEST_SCHEMA_ID, build_layout_plan, verify_layout_plan

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"


def _write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _roadmap(path: Path, count: int, *, project_id: str) -> Path:
    assignments = []
    for index in range(count):
        identifier = f"TASK-{index + 1:03d}"
        assignments.append(
            {
                "id": identifier,
                "title": f"Bounded assignment {index + 1}",
                "detail": f"Complete bounded synthetic assignment {index + 1}.",
                "depends_on": [] if index == 0 else [f"TASK-{index:03d}"],
                "touches": [],
                "conflict": "NO_CONFLICT",
                "migration": "",
                "definition_of_done": ["Bound evidence exists"],
            }
        )
    return _write_json(
        path,
        {
            "format": "opencntx-continuity-roadmap",
            "format_version": 1,
            "project_id": project_id,
            "roadmap_id": f"{project_id}-ROADMAP",
            "title": "Synthetic long-flow validation",
            "assignments": assignments,
        },
    )


def _restart_status(project: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SOURCE)
    result = subprocess.run(
        [sys.executable, "-m", "opencntx", "flow", "status", "--root", str(project), "--json"],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Restart status failed")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise TypeError("Restart status was not an object")
    return value


def _long_flow(parent: Path) -> dict[str, int]:
    project = parent / "long-flow"
    project.mkdir()
    roadmap = _roadmap(project / "roadmap.json", 100, project_id="LONG-FLOW")
    evidence = project / "evidence.txt"
    evidence.write_text("green\n", encoding="utf-8")
    start_flow(project, roadmap, "AUTO PILOT")
    restarts = claims = 0
    for index in range(100):
        for _ in range(2):
            status = _restart_status(project)
            restarts += 1
            if status["current_assignment"] != f"TASK-{index + 1:03d}":
                raise RuntimeError("Restart selected the wrong assignment")
        if index % 10 == 0:
            delivery = host_status(project, "HOST-LONG")
            claim = claim_host(project, "HOST-LONG", delivery["delivery_digest"])
            result = advance_flow(
                project,
                outcome="PASS",
                evidence_paths=[evidence.name],
                host_id="HOST-LONG",
                claim_digest=claim["claim_digest"],
            )
            transition = resume_host(project, "HOST-LONG", claim["claim_digest"])
            expected = "COMPLETE" if index == 99 else "NEXT"
            if transition["phase"] != expected:
                raise RuntimeError("Host resume routed to the wrong phase")
            claims += 1
        else:
            result = advance_flow(project, outcome="PASS", evidence_paths=[evidence.name])
        if index < 99 and result.current_assignment != f"TASK-{index + 2:03d}":
            raise RuntimeError("Automatic trigger selected the wrong next assignment")
    if result.status != "COMPLETE" or len(result.completed) != 100:
        raise RuntimeError("Long flow did not complete")
    capsule = parent / "long-flow.ocx"
    export_capsule(project, capsule)
    if verify_capsule(capsule)["status"] != "VERIFIED":
        raise RuntimeError("Long-flow capsule did not verify")
    restored = parent / "long-flow-restored"
    import_capsule(restored, capsule)
    if health_report(restored)["status"] != "HEALTHY":
        raise RuntimeError("Restored long-flow capsule is unhealthy")
    return {"assignments": 100, "capsules": 1, "host_claims": claims, "process_restarts": restarts}


def _concurrent_writers(parent: Path) -> dict[str, int]:
    project = parent / "writers"
    project.mkdir()
    roadmap = _roadmap(project / "roadmap.json", 1, project_id="WRITER-RACE")
    evidence = project / "evidence.txt"
    evidence.write_text("green\n", encoding="utf-8")
    start_flow(project, roadmap, "AUTO PILOT")

    def advance() -> str:
        try:
            return advance_flow(
                project, outcome="PASS", evidence_paths=[evidence.name]
            ).status
        except ContinuityError:
            return "REJECTED"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lambda _index: advance(), range(8)))
    if outcomes.count("COMPLETE") != 1 or outcomes.count("REJECTED") != 7:
        raise RuntimeError("Concurrent writer result is not exclusive")
    return {"accepted": 1, "rejected": 7, "writers": 8}


def _recovery(parent: Path) -> dict[str, int]:
    recovered = parent / "recovered"
    recovered.mkdir()
    roadmap = _roadmap(recovered / "roadmap.json", 1, project_id="RECOVERY-SUCCESS")
    evidence = recovered / "evidence.txt"
    evidence.write_text("basis-1\n", encoding="utf-8")
    start_flow(recovered, roadmap, "AUTO PILOT")
    for round_number in (1, 2):
        evidence.write_text(f"basis-{round_number}\n", encoding="utf-8")
        state = advance_flow(
            recovered,
            outcome="FAIL",
            evidence_paths=[evidence.name],
            reason=f"distinct bounded failure {round_number}",
        )
        if state.status != "RECOVERY_REQUIRED":
            raise RuntimeError("A bounded recovery did not remain available")
    evidence.write_text("recovered\n", encoding="utf-8")
    if advance_flow(recovered, outcome="PASS", evidence_paths=[evidence.name]).status != "COMPLETE":
        raise RuntimeError("Recovery flow did not complete")

    blocked = parent / "blocked"
    blocked.mkdir()
    roadmap = _roadmap(blocked / "roadmap.json", 1, project_id="RECOVERY-BLOCK")
    evidence = blocked / "evidence.txt"
    evidence.write_text("basis\n", encoding="utf-8")
    start_flow(blocked, roadmap, "AUTO PILOT")
    for round_number in (1, 2, 3):
        evidence.write_text(f"blocked-basis-{round_number}\n", encoding="utf-8")
        state = advance_flow(
            blocked,
            outcome="FAIL",
            evidence_paths=[evidence.name],
            reason=f"distinct terminal failure {round_number}",
        )
    if state.status != "BLOCKED":
        raise RuntimeError("Three recovery rounds did not block")
    return {"blocked_after": 3, "recovered_after": 2, "rounds_exercised": 5}


def _git(*arguments: str, cwd: Path | None = None) -> None:
    subprocess.run(["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True)


def _sync_failure(parent: Path) -> dict[str, int]:
    bare = parent / "remote.git"
    mirror = parent / "mirror"
    _git("init", "--bare", "-q", str(bare))
    mirror.mkdir()
    _git("init", "-q", cwd=mirror)
    _git("config", "user.name", "Example", cwd=mirror)
    _git("config", "user.email", "example@example.invalid", cwd=mirror)
    (mirror / "README.md").write_text("private replica\n", encoding="utf-8")
    _git("add", ".", cwd=mirror)
    _git("commit", "-qm", "initial", cwd=mirror)
    _git("branch", "-M", "main", cwd=mirror)
    _git("remote", "add", "origin", str(bare), cwd=mirror)
    _git("push", "-q", "-u", "origin", "main", cwd=mirror)

    project = parent / "sync-project"
    project.mkdir()
    roadmap = _roadmap(project / "roadmap.json", 2, project_id="SYNC-FAILURE")
    evidence = project / "evidence.txt"
    evidence.write_text("green\n", encoding="utf-8")
    start_flow(project, roadmap, "AUTO PILOT")
    configure_sync(
        project,
        mirror,
        remote="origin",
        branch="main",
        private_repository_confirmed=False,
    )
    bare.rename(parent / "remote-unavailable.git")
    state = advance_flow(project, outcome="PASS", evidence_paths=[evidence.name])
    status = sync_status(project)
    if state.status != "RUNNING" or status["last_error"] is None:
        raise RuntimeError("Offline sync failure did not preserve local flow and latch the error")
    if status["last_error"]["retry"] != "NOT_AUTOMATIC":
        raise RuntimeError("Sync failure retry policy changed")
    return {"latched_errors": 1, "local_checkpoints_preserved": 1}


def _manifest(base: Path, operations: list[dict[str, str]] | None = None) -> Path:
    return _write_json(
        base / "manifest.json",
        {
            "format": "opencntx-layout-migration",
            "format_version": 1,
            "maximum_bytes": 1_000_000,
            "maximum_files": 100,
            "maximum_path_length": 240,
            "minimum_free_bytes": 0,
            "operations": operations
            or [{"destination": "TARGET/PROJECT", "id": "MOVE-PROJECT", "source": "SOURCE"}],
            "plan_id": "CHAOS-PLAN",
            "protected_paths": ["PROTECTED"],
            "schema_id": MANIFEST_SCHEMA_ID,
        },
    )


def _init_source(base: Path) -> None:
    source = base / "SOURCE"
    (source / "DOCS").mkdir(parents=True)
    (source / "README.md").write_text("source\n", encoding="utf-8")
    (source / "DOCS" / "GUIDE.md").write_text("guide\n", encoding="utf-8")


def _exclusive_handle(path: Path) -> tuple[Any, int]:
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
    if handle == ctypes.c_void_p(-1).value:
        raise RuntimeError("Cannot establish synthetic exclusive handle")
    return kernel32, handle


def _layout_case(parent: Path, number: int, category: str) -> None:
    base = parent / f"case-{number:03d}"
    base.mkdir()
    _init_source(base)
    operations: list[dict[str, str]] | None = None
    manifest = _manifest(base)
    expected_code: str | None = None
    handle: tuple[Any, int] | None = None
    if category == "casing":
        (base / "TARGET" / "PROJECT").mkdir(parents=True)
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["operations"][0]["destination"] = (
            "target/project" if os.name == "nt" else "TARGET/PROJECT"
        )
        _write_json(manifest, value)
        expected_code = "DESTINATION_COLLISION"
    elif category == "duplicate_destination":
        operations = [
            {"destination": "TARGET/PROJECT", "id": "MOVE-ONE", "source": "SOURCE"},
            {"destination": "TARGET/PROJECT", "id": "MOVE-TWO", "source": "SOURCE/DOCS"},
        ]
        manifest = _manifest(base, operations)
        expected_code = "DESTINATION_OVERLAP"
    elif category == "link_or_lock":
        if os.name == "nt":
            handle = _exclusive_handle(base / "SOURCE" / "README.md")
            expected_code = "PROCESS_LOCK_PRESENT"
        else:
            outside = base / "OUTSIDE"
            outside.mkdir()
            (base / "SOURCE" / "LINK").symlink_to(outside, target_is_directory=True)
            expected_code = "LINK_PRESENT"
    elif category == "long_path":
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["maximum_path_length"] = 64
        _write_json(manifest, value)
        expected_code = "PATH_LENGTH_EXCEEDED"
    elif category == "protected":
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["protected_paths"] = ["SOURCE/DOCS"]
        _write_json(manifest, value)
        expected_code = "PROTECTED_PATH"
    elif category == "source_overlap":
        operations = [
            {"destination": "TARGET/ONE", "id": "MOVE-ONE", "source": "SOURCE"},
            {"destination": "TARGET/TWO", "id": "MOVE-TWO", "source": "SOURCE/DOCS"},
        ]
        manifest = _manifest(base, operations)
        expected_code = "SOURCE_OVERLAP"
    elif category == "partial_move":
        destination = base / "TARGET" / "PROJECT"
        destination.mkdir(parents=True)
        (destination / "README.md").write_text("partial\n", encoding="utf-8")
        expected_code = "DESTINATION_COLLISION"
    elif category == "missing_source":
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["operations"][0]["source"] = "MISSING"
        _write_json(manifest, value)
        expected_code = "SOURCE_MISSING"
    elif category == "stale_git":
        source = base / "SOURCE"
        _git("init", "-q", cwd=source)
        _git("config", "user.name", "Example", cwd=source)
        _git("config", "user.email", "example@example.invalid", cwd=source)
        _git("add", ".", cwd=source)
        _git("commit", "-qm", "initial", cwd=source)
        plan = build_layout_plan(manifest, base)
        if plan["status"] != "READY":
            raise RuntimeError("Stale Git basis was not initially ready")
        plan_path = _write_json(base / "plan.json", plan)
        (source / "CHANGE.md").write_text("changed\n", encoding="utf-8")
        _git("add", ".", cwd=source)
        _git("commit", "-qm", "change", cwd=source)
        result = verify_layout_plan(plan_path)
        if result["status"] != "STALE":
            raise RuntimeError("Changed Git basis did not become stale")
        return
    try:
        plan = build_layout_plan(manifest, base)
    finally:
        if handle is not None:
            handle[0].CloseHandle(ctypes.c_void_p(handle[1]))
    if category == "ready":
        if plan["status"] != "READY":
            raise RuntimeError("Clean layout case was not ready")
        return
    codes = {item["code"] for item in plan["findings"]}
    if expected_code not in codes or plan["status"] != "BLOCKED":
        raise RuntimeError(f"Layout chaos case {category} did not fail closed")


def _layout_chaos(parent: Path) -> dict[str, Any]:
    parent.mkdir()
    categories = (
        "ready",
        "casing",
        "duplicate_destination",
        "link_or_lock",
        "long_path",
        "protected",
        "source_overlap",
        "stale_git",
        "partial_move",
        "missing_source",
    )
    counts = {category: 0 for category in categories}
    for number in range(120):
        category = categories[number % len(categories)]
        _layout_case(parent, number, category)
        counts[category] += 1
    return {"categories": counts, "scenarios": sum(counts.values())}


def run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="opencntx-r10-complex-") as temporary_directory:
        root = Path(temporary_directory)
        result = {
            "concurrent_writers": _concurrent_writers(root),
            "format": "opencntx-r10-complex-simulation",
            "format_version": 1,
            "layout": _layout_chaos(root / "layout"),
            "long_flow": _long_flow(root),
            "recovery": _recovery(root),
            "status": "PASS",
            "sync_failure": _sync_failure(root),
            "writes_to_real_project_maps": 0,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = run()
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
