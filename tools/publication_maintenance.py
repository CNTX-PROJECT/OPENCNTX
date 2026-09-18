"""Verify a maintenance checkout against unchanged published runtime bytes."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

from release_version_gate import (
    ReleaseVersionError,
    StableVersion,
    _git,
    _project_version,
    _stable_tags,
)

MAINTENANCE_FILES = {
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    ".github/workflows/ci.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    "site/index.html",
    "site/README.md",
    "assets/design-system/visual-baseline-v1.json",
    "tests/fixtures/quality/current-version-surfaces-v1.json",
    "tests/test_quality.py",
    "tests/test_cli.py",
    "tests/test_contracts.py",
    "tests/r12_install_simulator.py",
    "tests/test_refactor_contract.py",
    "tests/fixtures/quality/cli-contract-1.8.5.json",
    "tests/test_public_roadmap.py",
    "tests/test_publication_maintenance.py",
    "tests/test_publication_links.py",
    "tools/release_version_gate.py",
    "tools/publication_maintenance.py",
    "tools/publication_links.py",
    "tools/r8_hardening.py",
}
RETIRED_HELPERS = {
    ".github/workflows/owner-preview-185.yml",
    ".github/workflows/release-185.yml",
    "tools/build_owner_preview_185.py",
    "tools/build_release_185.py",
}


def allowed_change(status: str, path: str) -> bool:
    """Permit documentation and named verification maintenance, never runtime."""
    parts = PurePosixPath(path).parts
    if not parts or "\\" in path or path.startswith("/") or ".." in parts:
        return False
    if path in RETIRED_HELPERS:
        return status == "D"
    if status not in {"A", "M"}:
        return False
    if path in MAINTENANCE_FILES:
        return True
    if path.startswith("docs/") and path.endswith((".md", ".json")):
        return True
    return path in {
        "tests/fixtures/release-baselines/manifest.json",
        "tests/fixtures/release-baselines/opencntx-0.3.0-py3-none-any.whl",
        "tests/fixtures/release-baselines/opencntx-1.7.6-py3-none-any.whl",
    }


def _validate_release_metadata_transition(
    source_text: str,
    current_text: str,
    *,
    version: str,
) -> None:
    """Allow only candidate-to-published state after the tagged build."""
    try:
        source_project = tomllib.loads(source_text)
        current_project = tomllib.loads(current_text)
    except tomllib.TOMLDecodeError as exc:
        raise ReleaseVersionError("release metadata TOML is invalid") from exc

    def release_table(project: dict[str, Any]) -> dict[str, Any]:
        tool = project.get("tool")
        opencntx = tool.get("opencntx") if isinstance(tool, dict) else None
        if not isinstance(opencntx, dict) or not isinstance(opencntx.get("release"), dict):
            raise ReleaseVersionError("release metadata table is missing")
        return opencntx["release"]

    def without_release_state(project: dict[str, Any]) -> dict[str, Any]:
        tool = project["tool"]
        opencntx = tool["opencntx"]
        del opencntx["release"]
        return project

    source_release = release_table(source_project)
    current_release = release_table(current_project)
    if without_release_state(source_project) != without_release_state(current_project):
        raise ReleaseVersionError("post-release pyproject changes packaging metadata")
    if source_release.get("status") != "local-candidate":
        raise ReleaseVersionError("tagged pyproject is not a local release candidate")
    if current_release != {"published_version": version, "status": "published"}:
        raise ReleaseVersionError("pyproject release state is not the exact published version")
    if StableVersion.parse(str(source_release.get("published_version"))) >= StableVersion.parse(
        version
    ):
        raise ReleaseVersionError("pyproject release state did not advance")


def inspect_maintenance(repository: Path) -> dict[str, Any]:
    """Report content alignment; do not claim ancestry or artifact equivalence."""
    root = repository.resolve()
    if _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ReleaseVersionError("maintenance checkout must be clean")
    record = json.loads((root / "docs/publication.json").read_text(encoding="utf-8"))
    version = str(_project_version(root))
    if record.get("format") != "opencntx-publication-v1" or record.get("version") != version:
        raise ReleaseVersionError("publication and package version differ")
    tags = _stable_tags(root)
    if not tags or str(max(tags)) != version:
        raise ReleaseVersionError("maintenance version differs from the latest stable tag")
    tag = f"v{version}"
    if record.get("tag") != tag:
        raise ReleaseVersionError("publication tag differs")
    source = _git(root, "rev-list", "-n", "1", tag)
    if record.get("source_commit") != source:
        raise ReleaseVersionError("publication source does not match the immutable tag")
    # Includes all source/schema bytes, build metadata, dependencies and legal identity.
    protected = [
        "src",
        "MANIFEST.in",
        "LICENSE",
        "requirements-quality.txt",
        "requirements-security.txt",
    ]
    if _git(root, "diff", "--name-only", source, "HEAD", "--", *protected):
        raise ReleaseVersionError("runtime or packaging changed; a new package version is required")
    raw = _git(root, "diff", "--name-status", "--no-renames", source, "HEAD")
    changes = []
    for line in raw.splitlines():
        status, separator, path = line.partition("\t")
        release_state_update = path == "pyproject.toml" and status == "M"
        if not separator or not (allowed_change(status, path) or release_state_update):
            raise ReleaseVersionError(f"unapproved maintenance path: {line}")
        if path == "pyproject.toml":
            if status != "M":
                raise ReleaseVersionError("pyproject release state must be updated in place")
            source_text = _git(root, "show", f"{source}:pyproject.toml")
            try:
                current_text = (root / "pyproject.toml").read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ReleaseVersionError("cannot read current pyproject metadata") from exc
            _validate_release_metadata_transition(source_text, current_text, version=version)
        changes.append({"status": status, "path": path})
    if not changes:
        result = "TAG_CONTENT_ALIGNED"
    else:
        result = "RELEASE_RUNTIME_ALIGNED_MAINTENANCE"
    return {
        "format": "opencntx-publication-maintenance-v1",
        "result": result,
        "project_version": version,
        "latest_tag": tag,
        "release_commit": source,
        "head": _git(root, "rev-parse", "HEAD"),
        "changes": changes,
        "artifact_equivalence_claimed": False,
        "ancestry_claimed": False,
    }
