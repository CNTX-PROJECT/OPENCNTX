"""Run mandatory historical writer regressions against one immutable checkout."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    if re.fullmatch(r"[0-9a-f]{40}", args.expected_commit) is None:
        parser.error("--expected-commit must be the immutable full commit identifier")
    git = shutil.which("git")
    if not git or not (source / "src/opencntx/continuity.py").is_file():
        parser.error("an actual historical checkout with continuity.py is required")
    identity = subprocess.run(
        [git, "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    dirty = subprocess.run(
        [git, "-C", str(source), "status", "--porcelain", "--", "src"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    if identity != args.expected_commit or dirty:
        parser.error("historical source differs from the exact clean commit")
    os.environ["R15_LEGACY_SOURCE"] = str(source / "src")
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root / "src"), str(root)]
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        ["tests.test_continuity_version", "tests.test_legacy_recovery"]
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    success = result.wasSuccessful() and not result.skipped and result.testsRun >= 14
    print(
        json.dumps(
            {
                "source_commit": identity,
                "tests": result.testsRun,
                "skipped": len(result.skipped),
                "failures": len(result.failures),
                "errors": len(result.errors),
                "status": "PASS" if success else "FAIL",
                "scope": "historical writer and recovery-copy regression; not installer qualification",
            },
            sort_keys=True,
        )
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
