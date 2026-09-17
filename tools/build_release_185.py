"""Finalize the owner-authorized regular 1.8.5 release with truthful evidence.

Reuse, rather than weaken, the targeted product and managed-install checks
already used by the preceding build. Regular publication is not a claim that
the full roadmap or comprehensive release qualification has been completed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import build_owner_preview_185 as checked_builder

ROOT = Path(__file__).resolve().parents[1]
TESTED_CODE_COMMIT = "112112c5e0fd400e501ce81b61c82bf9cb272fe7"
ALLOWED_CHANGES = {
    "pyproject.toml",
    "docs/release-1.8.5.md",
    "tools/build_release_185.py",
    ".github/workflows/release-185.yml",
}


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> int:
    if os.environ.get("GITHUB_REF") != "refs/heads/release/1.8.5":
        raise RuntimeError("This publication is bound to release/1.8.5")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if project["project"]["version"] != "1.8.5":
        raise RuntimeError("Unexpected package version")
    delta = subprocess.run(
        ["git", "diff", "--name-only", "-z", TESTED_CODE_COMMIT, "HEAD"],
        cwd=ROOT, check=True, capture_output=True, timeout=30,
    ).stdout.decode("utf-8").split("\0")
    changed = {name for name in delta if name}
    if not changed <= ALLOWED_CHANGES:
        raise RuntimeError("Unexpected changes outside publication scope")
    # Every prior product check must pass on the newly built final artifact.
    if checked_builder.main() != 0:
        raise RuntimeError("Required product checks failed")
    directory = ROOT / "dist"
    record_path = directory / "BUILD-RECORD.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record.update({
        "format": "opencntx-owner-authorized-release-build-v1",
        "release_tag": "v1.8.5",
        "publication_channel": "REGULAR_RELEASE_LATEST",
        "qualification": "TARGETED_PRODUCT_CHECKS_ONLY_FULL_ROADMAP_NOT_COMPLETE",
        "publication_authority": "Explicit owner instruction for regular permanent publication",
        "code_baseline": TESTED_CODE_COMMIT,
        "runtime_code_unchanged_from_tested_preview": True,
        "publication_changed_paths": sorted(changed),
        "check_runner": "tools/build_owner_preview_185.py (retained targeted check implementation)",
    })
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    files = [directory / "opencntx-1.8.5-py3-none-any.whl", directory / "opencntx-1.8.5.tar.gz", record_path]
    (directory / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files), encoding="utf-8"
    )
    print("REGULAR_RELEASE_READY: targeted checks passed; full qualification is not claimed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
