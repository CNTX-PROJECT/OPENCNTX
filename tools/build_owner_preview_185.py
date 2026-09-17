"""Build an explicitly unqualified owner preview and run bounded product checks.

This does not replace the stable release gate. It operates only in a disposable
CI checkout, uses the unchanged managed installer, and records its limited scope.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
import venv
from pathlib import Path

BASELINE = "6fc196b5ec90370c93c204a115ac58c73fd2bb32"
BASELINE_WHEEL_SHA256 = "b3fe658c5071b17e1835be65cc10df3c025dd03677c1be45c9b8aeb977d011d9"
ROOT = Path(__file__).resolve().parents[1]
CHECKS: list[dict[str, object]] = []


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(label: str, command: list[str], *, env: dict[str, str], timeout: int = 300) -> str:
    started = time.perf_counter()
    process = subprocess.run(
        command, cwd=ROOT, env=env, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=timeout, check=False,
    )
    print(f"\n=== {label} ===", flush=True)
    print(process.stdout, end="", flush=True)
    print(process.stderr, end="", file=sys.stderr, flush=True)
    CHECKS.append({
        "label": label, "exit_code": process.returncode,
        "duration_seconds": round(time.perf_counter() - started, 4),
        "stdout_tail": process.stdout[-4000:], "stderr_tail": process.stderr[-2000:],
    })
    if process.returncode:
        raise RuntimeError(f"Preview check failed: {label}")
    return process.stdout


def main() -> int:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    source_env = {**env, "PYTHONPATH": str(ROOT / "src")}
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if version != "1.8.5":
        raise RuntimeError("Refusing to build a different package version")
    head = run("source_commit", ["git", "rev-parse", "HEAD"], env=env).strip()
    tree = run("source_tree", ["git", "rev-parse", "HEAD^{tree}"], env=env).strip()
    if os.environ.get("GITHUB_SHA", head) != head:
        raise RuntimeError("Checkout differs from the requested workflow commit")
    run("baseline_ancestry", ["git", "merge-base", "--is-ancestor", BASELINE, head], env=env)
    if run("clean_checkout", ["git", "status", "--porcelain"], env=env).strip():
        raise RuntimeError("Preview source checkout is not clean")
    for filename in (
        "test_owner_preview_185.py", "test_release_184_regressions.py",
        "test_search_index_v2.py", "test_presentation.py", "test_visual_integration.py",
    ):
        if not (ROOT / "tests" / filename).is_file():
            raise RuntimeError(f"Required test file missing: {filename}")
        program = (
            "import unittest,sys; "
            f"suite=unittest.defaultTestLoader.discover('tests',pattern={filename!r}); "
            "count=suite.countTestCases(); "
            "print('TEST_COUNT',count); "
            "result=unittest.TextTestRunner(verbosity=1).run(suite); "
            "sys.exit(0 if count and result.wasSuccessful() else 1)"
        )
        run(filename, [sys.executable, "-c", program], env=source_env)
    destination = ROOT / "dist"
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError("Refusing to mix preview artifacts with existing dist files")
    run("standard_preview_build", [sys.executable, "-m", "build", "--no-isolation"], env=source_env)
    wheel = destination / "opencntx-1.8.5-py3-none-any.whl"
    sdist = destination / "opencntx-1.8.5.tar.gz"
    if not wheel.is_file() or not sdist.is_file():
        raise RuntimeError("Preview wheel or source distribution is missing")
    with tempfile.TemporaryDirectory(prefix="ocx-preview-artifacts-") as temporary:
        work = Path(temporary)
        installed = work / "installed"
        venv.EnvBuilder(with_pip=True).create(installed)
        executable = installed / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        isolated = {key: value for key, value in env.items() if key != "PYTHONPATH"}
        isolated["PIP_NO_INDEX"] = "1"
        run("wheel_install", [str(executable), "-I", "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], env=isolated)
        output = run("installed_version", [str(executable), "-I", "-m", "opencntx", "--version"], env=isolated)
        if output.strip() != "opencntx 1.8.5":
            raise RuntimeError("Installed wheel reports the wrong version")
        run("installed_preview_tests", [str(executable), "-I", str(ROOT / "tests/test_owner_preview_185.py")], env=isolated)
        baseline = work / "opencntx-1.8.4-py3-none-any.whl"
        url = "https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v1.8.4/opencntx-1.8.4-py3-none-any.whl"
        with urllib.request.urlopen(url, timeout=45) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != BASELINE_WHEEL_SHA256:
            raise RuntimeError("Published 1.8.4 rollback wheel failed the pinned hash check")
        baseline.write_bytes(data)
        run(
            "managed_1.8.4_upgrade_rollback_reapply_resume",
            [sys.executable, str(ROOT / "tools/managed_install_acceptance.py"),
             "--candidate", str(wheel), "--baseline", str(baseline),
             "--expected-candidate", "1.8.5", "--expected-baseline", "1.8.4",
             "--expected-baseline-sha256", BASELINE_WHEEL_SHA256],
            env={**source_env, "PIP_NO_INDEX": "1"}, timeout=480,
        )
    record = {
        "format": "opencntx-owner-preview-build-v1", "format_version": 1,
        "version": "1.8.5", "release_tag": "v1.8.5-preview.1",
        "qualification": "EXPERIMENTAL_NOT_STABLE_NOT_FULL_ROADMAP",
        "baseline_commit": BASELINE, "commit": head, "tree": tree,
        "python": platform.python_version(), "platform": platform.platform(),
        "artifacts": [{"name": path.name, "sha256": digest(path), "bytes": path.stat().st_size} for path in (wheel, sdist)],
        "checks": CHECKS,
        "not_tested": ["full_suite", "coverage", "Windows", "ARM64", "real_user_installation", "provider_tokens", "native_hosts", "full_1.8.5_roadmap"],
        "stable_reproducibility_gate": "NOT_RUN_STANDARD_BUILD_ONLY",
    }
    record_path = destination / "BUILD-RECORD.json"
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (destination / "SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in (wheel, sdist, record_path)), encoding="utf-8",
    )
    print("OWNER_PREVIEW_READY: checks passed within the declared limited scope", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
