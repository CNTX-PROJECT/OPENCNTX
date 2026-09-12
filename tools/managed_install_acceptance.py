"""Exercise real managed update, rollback, reapply, and fresh-process resume cycles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from opencntx.install_manager import managed_update, resume_update


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _run(command: list[str]) -> None:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode:
        raise RuntimeError(f"acceptance command exited {result.returncode}: {command[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--expected-candidate", default="1.7.6")
    parser.add_argument("--expected-baseline", default="1.7.5")
    parser.add_argument(
        "--expected-baseline-sha256",
        default="8494439d1b3422d8a3afcb0fb385f1e499253d4932232338fada8fd04713fca0",
    )
    parser.add_argument("--transitions", type=int, default=10)
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    baseline = args.baseline.resolve(strict=True)
    candidate_hash = _sha256(candidate)
    baseline_hash = _sha256(baseline)
    if baseline_hash != args.expected_baseline_sha256:
        raise ValueError("the acquired baseline differs from its frozen release SHA-256")
    with tempfile.TemporaryDirectory(prefix="opencntx-managed-acceptance-") as temporary:
        root = Path(temporary)
        target = root / "target"
        state = root / "state"
        _run([sys.executable, "-I", "-B", "-m", "venv", str(target)])
        python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run([str(python), "-I", "-B", "-m", "pip", "install", str(baseline)])
        if args.transitions < 10:
            raise ValueError("at least ten managed transitions are required")
        phases: list[str] = []
        for number in range(args.transitions):
            to_candidate = number % 2 == 0
            result = managed_update(
                artifact=str(candidate if to_candidate else baseline),
                sha256=candidate_hash if to_candidate else baseline_hash,
                version=args.expected_candidate if to_candidate else args.expected_baseline,
                rollback_artifact=str(baseline if to_candidate else candidate),
                rollback_sha256=baseline_hash if to_candidate else candidate_hash,
                state_root=state,
                python=python,
            )
            phases.append(str(result["status"]))
        if args.transitions % 2 == 0:
            result = managed_update(
                artifact=str(candidate),
                sha256=candidate_hash,
                version=args.expected_candidate,
                rollback_artifact=str(baseline),
                rollback_sha256=baseline_hash,
                state_root=state,
                python=python,
            )
            phases.append(str(result["status"]))
        resumed = resume_update(state_root=state)
        if phases != ["NEW_HEALTHY"] * len(phases) or resumed["status"] != "NEW_HEALTHY":
            raise RuntimeError(f"managed acceptance phases differ: {phases}")
        journals = sorted((state / "journals").glob("*.json"))
        staging = list((state / "staging").iterdir())
        if len(journals) != 10 or staging:
            raise RuntimeError("managed acceptance provenance cleanup differs")
        evidence = {
            "format": "opencntx-managed-install-acceptance",
            "format_version": 1,
            "status": "PASS",
            "candidate_version": args.expected_candidate,
            "candidate_sha256": candidate_hash,
            "baseline_version": args.expected_baseline,
            "baseline_sha256": baseline_hash,
            "cycles": ["update", "rollback", "reapply", "fresh-process-resume"],
            "successful_transitions": len(phases),
            "terminal_journals": len(journals),
            "remaining_staging_entries": len(staging),
            "platform": sys.platform,
            "python": list(sys.version_info[:3]),
        }
        print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
