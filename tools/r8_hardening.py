"""Execute the bounded R8-23 contention, crash, and v0.3.0 upgrade proofs."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import queue
import subprocess
import sys
import tempfile
import urllib.request
import venv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from opencntx.integrity import (
    IntegrityError,
    doctor_workspace,
    recover_workspace,
    state_digest,
    sync_directory,
    writer_transaction,
)
from opencntx.workspace import init_workspace

FAMILY_REGISTER = ROOT / "tests" / "fixtures" / "hardening" / "mutation-families-v1.json"
V030_WHEEL_URL = (
    "https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/"
    "v0.3.0/opencntx-0.3.0-py3-none-any.whl"
)
V030_WHEEL_SHA256 = "6dee59d5255c73278400c05217abb298abb50a51f5998c7fb9d1c41e8e027cc6"
CRASH_EXIT = 86
LOCK_FAILURES = {"transaction_locked", "transaction_state_changed"}


class HardeningError(RuntimeError):
    """A bounded hardening proof failed closed."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_manifest(path: Path, value: object) -> str:
    content = _canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    reread = path.read_bytes()
    if reread != content:
        raise HardeningError(f"manifest reread differs: {path}")
    return _sha256(reread)


def _families() -> dict[str, dict[str, Any]]:
    value = json.loads(FAMILY_REGISTER.read_text(encoding="utf-8"))
    families = value.get("families")
    if not isinstance(families, dict) or len(families) != 8:
        raise HardeningError("mutation family register is not the closed eight-family set")
    return families


def _vector(family: str, round_number: int) -> dict[str, object]:
    material = f"opencntx-r8-23-contention-v1|{family}|{round_number:02d}".encode()
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    value: dict[str, object] = {
        "family": family,
        "round": round_number,
        "scenario_version": 1,
        "seed": seed,
    }
    content = _canonical(value)
    return {**value, "input_sha256": _sha256(content)}


def _tree_inventory(root: Path) -> str:
    inventory: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        stat_result = path.lstat()
        if path.is_symlink():
            kind = "link"
            digest = _sha256(os.readlink(path).encode())
        elif path.is_dir():
            kind = "directory"
            digest = None
        elif path.is_file():
            kind = "file"
            digest = _sha256(path.read_bytes())
        else:
            kind = "other"
            digest = None
        inventory.append(
            {
                "kind": kind,
                "mtime_ns": stat_result.st_mtime_ns,
                "path": relative,
                "sha256": digest,
                "size": stat_result.st_size,
            }
        )
    return _sha256(_canonical(inventory))


def _contention_worker(
    root_text: str,
    target_text: str,
    receipt_text: str,
    operation: str,
    expected_digest: str,
    content: bytes,
    receipt_content: bytes,
    start: Any,
    results: Any,
) -> None:
    root = Path(root_text)
    target = Path(target_text)
    receipt = Path(receipt_text)
    start.wait(30)
    try:
        with writer_transaction(
            root,
            operation,
            expected_digest=expected_digest,
            current_digest=lambda: state_digest((target,)),
        ) as transaction:
            record = transaction.track_target(target)
            previous_path = record["previous_path"]
            backup_verified = (
                isinstance(previous_path, str)
                and (transaction.directory / previous_path).read_bytes() == target.read_bytes()
            )
            target.write_bytes(content)
            transaction.mark_target_published(target)
            transaction.mark_published()
            transaction.track_target(receipt)
            receipt.write_bytes(receipt_content)
            transaction.mark_target_published(receipt)
            transaction.mark_receipted(None)
            results.put(
                {
                    "backup_verified": backup_verified,
                    "output_sha256": _sha256(target.read_bytes()),
                    "status": "success",
                    "transaction_id": transaction.transaction_id,
                }
            )
    except IntegrityError as exc:
        results.put({"code": exc.code, "message": str(exc), "status": "error"})
    except Exception as exc:
        results.put(
            {"error_class": type(exc).__name__, "message": str(exc), "status": "unexpected"}
        )


def run_contention(evidence: Path) -> dict[str, object]:
    families = _families()
    vectors = [
        _vector(family, round_number) for family in families for round_number in range(1, 26)
    ]
    if len(vectors) != 200 or len({item["input_sha256"] for item in vectors}) != 200:
        raise HardeningError("contention vector set is not exactly 200 unique vectors")
    manifest = {
        "format": "opencntx-r8-23-contention-vectors",
        "format_version": 1,
        "rounds_per_family": 25,
        "vectors": vectors,
    }
    manifest_sha256 = _write_manifest(evidence / "contention-vectors.json", manifest)
    context = multiprocessing.get_context("spawn")
    results_log: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="opencntx-r8-23-contention-") as temp_name:
        root = Path(temp_name) / "workspace"
        init_workspace(root)
        targets = root / ".opencntx" / "hardening"
        targets.mkdir()
        for vector in vectors:
            family = str(vector["family"])
            round_number = int(vector["round"])
            operation = str(families[family]["representative"])
            stem = f"{family.lower()}-{round_number:02d}"
            target = targets / f"{stem}.json"
            receipt = root / ".opencntx" / "receipts" / f"hardening-{stem}.json"
            base = _canonical({"family": family, "round": round_number, "state": "base"})
            target.write_bytes(base)
            content = _canonical(
                {
                    "family": family,
                    "input_sha256": vector["input_sha256"],
                    "round": round_number,
                    "seed": vector["seed"],
                    "state": "published",
                }
            )
            receipt_content = _canonical(
                {
                    "family": family,
                    "input_sha256": vector["input_sha256"],
                    "round": round_number,
                    "status": "COMPLETED",
                }
            )
            expected = state_digest((target,))
            start = context.Event()
            result_queue = context.Queue()
            processes = [
                context.Process(
                    target=_contention_worker,
                    args=(
                        str(root),
                        str(target),
                        str(receipt),
                        operation,
                        expected,
                        content,
                        receipt_content,
                        start,
                        result_queue,
                    ),
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(60)
                if process.is_alive():
                    process.kill()
                    process.join()
                    raise HardeningError(f"contention process timed out: {family} {round_number}")
            outcomes: list[dict[str, object]] = []
            while True:
                try:
                    outcomes.append(result_queue.get_nowait())
                except queue.Empty:
                    break
            result_queue.close()
            success = [item for item in outcomes if item.get("status") == "success"]
            errors = [item for item in outcomes if item.get("status") == "error"]
            if (
                len(outcomes) != 2
                or len(success) != 1
                or len(errors) != 1
                or errors[0].get("code") not in LOCK_FAILURES
                or success[0].get("backup_verified") is not True
                or target.read_bytes() != content
                or receipt.read_bytes() != receipt_content
                or any(process.exitcode != 0 for process in processes)
            ):
                raise HardeningError(
                    f"contention acceptance failed: {family} {round_number}: {outcomes}"
                )
            before_doctor = _tree_inventory(root)
            report = doctor_workspace(root)
            after_doctor = _tree_inventory(root)
            if report.status != "HEALTHY" or before_doctor != after_doctor:
                raise HardeningError(
                    f"doctor was not healthy and read-only: {family} {round_number}"
                )
            results_log.append(
                {
                    "family": family,
                    "input_sha256": vector["input_sha256"],
                    "loser_code": errors[0]["code"],
                    "output_sha256": success[0]["output_sha256"],
                    "round": round_number,
                    "winner_count": 1,
                }
            )
    result_value = {
        "format": "opencntx-r8-23-contention-results",
        "format_version": 1,
        "platform": "windows" if os.name == "nt" else "posix",
        "rounds": results_log,
        "vector_manifest_sha256": manifest_sha256,
    }
    result_sha256 = _write_manifest(evidence / "contention-results.json", result_value)
    return {"result_sha256": result_sha256, "rounds": len(results_log)}


def _successful_phases(root: Path, operation: str, family: str) -> list[str]:
    from opencntx import integrity

    phases: list[str] = []
    target = root / ".opencntx" / "hardening" / f"dry-{family.lower()}.txt"
    receipt = root / ".opencntx" / "receipts" / f"dry-{family.lower()}.json"
    target.write_bytes(b"previous\n")

    def record(_transaction_id: str, phase: str) -> None:
        phases.append(phase)

    integrity._TEST_FAULT_HOOK = record
    try:
        with writer_transaction(root, operation) as transaction:
            transaction.track_target(target)
            target.write_bytes(b"published\n")
            transaction.mark_target_published(target)
            transaction.mark_published()
            transaction.track_target(receipt)
            receipt.write_bytes(_canonical({"family": family, "status": "dry"}))
            transaction.mark_target_published(receipt)
            transaction.mark_receipted(None)
    finally:
        integrity._TEST_FAULT_HOOK = None
    return phases


def _crash_worker(
    root_text: str,
    target_text: str,
    receipt_text: str,
    operation: str,
    phase_index: int,
    content: bytes,
) -> None:
    from opencntx import integrity

    observed_index = 0

    def crash(_transaction_id: str, _phase: str) -> None:
        nonlocal observed_index
        observed_index += 1
        if observed_index == phase_index:
            os._exit(CRASH_EXIT)

    integrity._TEST_FAULT_HOOK = crash
    root = Path(root_text)
    target = Path(target_text)
    receipt = Path(receipt_text)
    with writer_transaction(root, operation) as transaction:
        transaction.track_target(target)
        target.write_bytes(content)
        transaction.mark_target_published(target)
        transaction.mark_published()
        transaction.track_target(receipt)
        receipt.write_bytes(_canonical({"operation": operation, "status": "crash-fixture"}))
        transaction.mark_target_published(receipt)
        transaction.mark_receipted(None)


def run_crash_matrix(evidence: Path) -> dict[str, object]:
    families = _families()
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="opencntx-r8-23-crash-") as temp_name:
        root = Path(temp_name) / "workspace"
        init_workspace(root)
        hardening = root / ".opencntx" / "hardening"
        hardening.mkdir()
        cases: list[dict[str, object]] = []
        for family, value in families.items():
            operation = str(value["representative"])
            phases = _successful_phases(root, operation, family)
            expected = [
                "INTENT_DURABLE",
                "TARGET_TRACKED",
                "TARGET_PUBLISHED",
                "PUBLISHED",
                "TARGET_TRACKED",
                "TARGET_PUBLISHED",
                "RECEIPTED",
                "COMPLETED",
            ]
            if phases != expected:
                raise HardeningError(f"unexpected phase sequence for {family}: {phases}")
            for phase_index, phase in enumerate(phases, start=1):
                input_value = {
                    "family": family,
                    "fault_code": CRASH_EXIT,
                    "operation": operation,
                    "phase": phase,
                    "phase_index": phase_index,
                    "target": f".opencntx/hardening/crash-{family.lower()}-{phase_index:02d}.txt",
                    "expected_recovery": "PREVIOUS_VALID_STATE",
                }
                cases.append({**input_value, "input_sha256": _sha256(_canonical(input_value))})
        manifest = {
            "cases": cases,
            "format": "opencntx-r8-23-crash-matrix",
            "format_version": 1,
            "platform": "windows" if os.name == "nt" else "posix",
        }
        manifest_sha256 = _write_manifest(evidence / "crash-matrix.json", manifest)
        results: list[dict[str, object]] = []
        for case in cases:
            target = root / str(case["target"])
            receipt = (
                root
                / ".opencntx"
                / "receipts"
                / f"crash-{str(case['family']).lower()}-{int(case['phase_index']):02d}.json"
            )
            base = _canonical(
                {"family": case["family"], "phase_index": case["phase_index"], "state": "base"}
            )
            target.write_bytes(base)
            receipt.unlink(missing_ok=True)
            process = context.Process(
                target=_crash_worker,
                args=(
                    str(root),
                    str(target),
                    str(receipt),
                    str(case["operation"]),
                    int(case["phase_index"]),
                    _canonical({"input_sha256": case["input_sha256"], "state": "published"}),
                ),
            )
            process.start()
            process.join(60)
            if process.is_alive():
                process.kill()
                process.join()
                raise HardeningError(f"crash process timed out: {case}")
            if process.exitcode != CRASH_EXIT:
                raise HardeningError(f"fault injection did not stop at the bound phase: {case}")
            report = doctor_workspace(root)
            issues = [item for item in report.issues if item.transaction_id is not None]
            if report.status != "RECOVERY_REQUIRED" or len(issues) != 1:
                raise HardeningError(f"crash was not exactly recoverable: {case}: {report}")
            issue = issues[0]
            if issue.transaction_id is None or issue.intent_sha256 is None:
                raise HardeningError(f"recovery identity missing: {case}")
            preview = recover_workspace(
                root, issue.transaction_id, issue.intent_sha256, apply=False
            )
            applied = recover_workspace(root, issue.transaction_id, issue.intent_sha256, apply=True)
            if (
                preview.transaction_id != applied.transaction_id
                or target.read_bytes() != base
                or receipt.exists()
                or doctor_workspace(root).status != "HEALTHY"
            ):
                raise HardeningError(f"exact rollback failed: {case}")
            results.append(
                {
                    "family": case["family"],
                    "input_sha256": case["input_sha256"],
                    "phase": case["phase"],
                    "phase_index": case["phase_index"],
                    "recovered": True,
                }
            )
    result_value = {
        "cases": results,
        "format": "opencntx-r8-23-crash-results",
        "format_version": 1,
        "manifest_sha256": manifest_sha256,
        "platform": "windows" if os.name == "nt" else "posix",
    }
    result_sha256 = _write_manifest(evidence / "crash-results.json", result_value)
    return {"cases": len(results), "result_sha256": result_sha256}


def _run(
    command: list[str], *, cwd: Path, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=capture,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
    )
    if completed.returncode:
        raise HardeningError(
            f"command failed ({completed.returncode}): {command}\n"
            f"{completed.stdout if capture else ''}{completed.stderr if capture else ''}"
        )
    return completed


def _venv_paths(environment: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe", environment / "Scripts" / "opencntx.exe"
    return environment / "bin" / "python", environment / "bin" / "opencntx"


def _user_inventory(root: Path) -> str:
    value: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            value.append({"kind": "directory", "path": relative})
        elif path.is_file():
            value.append({"kind": "file", "path": relative, "sha256": _sha256(path.read_bytes())})
        else:
            raise HardeningError(f"unexpected user-data path type: {path}")
    return _sha256(_canonical(value))


def run_upgrade(candidate: Path, evidence: Path) -> dict[str, object]:
    candidate = candidate.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="opencntx-r8-23-upgrade-") as temp_name:
        root = Path(temp_name)
        official = root / "opencntx-0.3.0-py3-none-any.whl"
        with urllib.request.urlopen(V030_WHEEL_URL, timeout=60) as response:
            official.write_bytes(response.read())
        if _sha256(official.read_bytes()) != V030_WHEEL_SHA256:
            raise HardeningError("official v0.3.0 wheel hash differs")
        environment = root / "venv"
        user_data = root / "user-data"
        core = user_data / "core"
        workspace = user_data / "workspace"
        core.mkdir(parents=True)
        (core / "README.md").write_text("# R8 upgrade fixture\n", encoding="utf-8")
        venv.EnvBuilder(with_pip=True).create(environment)
        python, command = _venv_paths(environment)
        _run(
            [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(official)],
            cwd=core,
        )
        version = _run([str(command), "--version"], cwd=core, capture=True).stdout.strip()
        if version != "opencntx 0.3.0":
            raise HardeningError(f"official version differs: {version}")
        for arguments in (["init"], ["pack"], ["verify"]):
            _run([str(command), *arguments], cwd=core)
        _run([str(command), "workspace", "init", str(workspace)], cwd=user_data)
        _run([str(command), "workspace", "doctor", "--root", str(workspace)], cwd=user_data)
        before_upgrade = _user_inventory(user_data)
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                str(candidate),
            ],
            cwd=core,
        )
        _run([str(python), "-m", "pip", "check"], cwd=core)
        _run([str(command), "verify"], cwd=core)
        _run([str(command), "workspace", "doctor", "--root", str(workspace)], cwd=user_data)
        after_upgrade = _user_inventory(user_data)
        if after_upgrade != before_upgrade:
            raise HardeningError("candidate upgrade changed existing user data")
        _run([str(python), "-m", "pip", "uninstall", "--yes", "opencntx"], cwd=core)
        metadata_check = _run(
            [
                str(python),
                "-c",
                (
                    "import importlib.metadata as m\n"
                    "try: m.version('opencntx')\n"
                    "except m.PackageNotFoundError: raise SystemExit(0)\n"
                    "raise SystemExit('metadata remains')"
                ),
            ],
            cwd=core,
        )
        if (
            metadata_check.returncode
            or command.exists()
            or _user_inventory(user_data) != before_upgrade
        ):
            raise HardeningError(
                "uninstall did not remove package cleanly while preserving user data"
            )
    result = {
        "candidate_sha256": _sha256(candidate.read_bytes()),
        "format": "opencntx-r8-23-upgrade-result",
        "format_version": 1,
        "official_v030_sha256": V030_WHEEL_SHA256,
        "platform": "windows" if os.name == "nt" else "posix",
        "user_data_preserved": True,
    }
    result_sha256 = _write_manifest(evidence / "upgrade-result.json", result)
    return {"result_sha256": result_sha256, "user_data_preserved": True}


def run_platform(candidate: Path, evidence: Path) -> None:
    if sys.version_info[:2] != (3, 14):
        raise HardeningError("platform hardening is bound to Python 3.14")
    evidence.mkdir(parents=True, exist_ok=True)
    contention = run_contention(evidence)
    crashes = run_crash_matrix(evidence)
    sync_status = sync_directory(evidence)
    if sync_status == "FAILED":
        raise HardeningError("platform evidence directory flush failed")
    upgrade = run_upgrade(candidate, evidence)
    summary = {
        "contention": contention,
        "crash_matrix": crashes,
        "directory_flush": sync_status,
        "format": "opencntx-r8-23-platform-result",
        "format_version": 1,
        "platform": "windows" if os.name == "nt" else "posix",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "upgrade": upgrade,
    }
    digest = _write_manifest(evidence / "platform-result.json", summary)
    print(
        "R8_23_PLATFORM_HARDENING_OK "
        f"rounds={contention['rounds']} crash_cases={crashes['cases']} "
        f"directory_flush={sync_status} result_sha256={digest}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    platform = subparsers.add_parser("platform")
    platform.add_argument("--candidate", type=Path, required=True)
    platform.add_argument("--evidence", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        run_platform(arguments.candidate, arguments.evidence)
    except (HardeningError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"R8_23_HARDENING_ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
