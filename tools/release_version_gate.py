from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STABLE_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
DOCUMENTATION_SUFFIXES = frozenset(
    {".gif", ".html", ".jpeg", ".jpg", ".md", ".png", ".svg", ".webp"}
)
PUBLIC_SITE_DOCUMENTATION_PATHS = frozenset(
    {"site/README.md", "site/components.html", "site/index.html"}
)
GATE_SUPPORT_PATHS = frozenset(
    {
        "assets/design-system/visual-baseline-v1.json",
        "tests/test_quality.py",
        "tests/test_release_version_gate.py",
        "tools/release_version_gate.py",
    }
)
ALLOWED_POST_RELEASE_STATUSES = frozenset({"A", "M"})
CURRENT_SURFACES = Path("tests/fixtures/quality/current-version-surfaces-v1.json")


class ReleaseVersionError(RuntimeError):
    """Raised when package, Git tag, and source state have drifted."""


@dataclass(frozen=True, order=True)
class StableVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> StableVersion:
        match = STABLE_VERSION.fullmatch(value)
        if match is None:
            raise ReleaseVersionError(f"not a canonical stable version: {value}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def _git(repository: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise ReleaseVersionError("Git is not available")
    try:
        process = subprocess.run(
            [executable, "-C", str(repository), *arguments],
            check=False,
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ReleaseVersionError(f"Git inspection failed: {exc}") from exc
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip() or "unknown Git failure"
        raise ReleaseVersionError(detail)
    return process.stdout.strip()


def _project_version(repository: Path) -> StableVersion:
    project_path = repository / "pyproject.toml"
    try:
        with project_path.open("rb") as project_file:
            value = tomllib.load(project_file)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseVersionError(f"cannot read project version: {exc}") from exc
    if not isinstance(value, str):
        raise ReleaseVersionError("project version is not text")
    return StableVersion.parse(value)


def _stable_tags(repository: Path) -> dict[StableVersion, str]:
    result: dict[StableVersion, str] = {}
    for tag in _git(repository, "tag", "--list", "v*").splitlines():
        value = tag.removeprefix("v")
        if STABLE_VERSION.fullmatch(value) is None:
            continue
        version = StableVersion.parse(value)
        canonical = f"v{version}"
        if tag != canonical:
            raise ReleaseVersionError(f"stable tag is not canonical: {tag}")
        result[version] = tag
    return result


def inspect_current_version_surfaces(
    repository: Path, *, version: StableVersion | None = None
) -> dict[str, Any]:
    """Verify declared current claims while leaving historical versions untouched."""
    selected = _project_version(repository) if version is None else version
    manifest_path = repository / CURRENT_SURFACES
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseVersionError(f"cannot read current-version surface manifest: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != "opencntx-current-version-surfaces"
        or manifest.get("format_version") != 1
        or not isinstance(manifest.get("surfaces"), list)
    ):
        raise ReleaseVersionError("current-version surface manifest is invalid")
    with (repository / "pyproject.toml").open("rb") as stream:
        release = tomllib.load(stream).get("tool", {}).get("opencntx", {}).get("release", {})
    published = StableVersion.parse(release.get("published_version", str(selected)))
    if published > selected or (
        published != selected and release.get("status") != "local-candidate"
    ):
        raise ReleaseVersionError("candidate and published version relationship is invalid")
    checked: list[dict[str, Any]] = []
    for surface in manifest["surfaces"]:
        if not isinstance(surface, dict) or set(surface) not in (
            {"path", "patterns", "purpose"},
            {"path", "patterns", "purpose", "version_source"},
        ):
            raise ReleaseVersionError("current-version surface entry is invalid")
        source = surface.get("version_source", "package")
        if source not in {"package", "published"}:
            raise ReleaseVersionError("unknown version source")
        expected = published if source == "published" else selected
        path = repository / str(surface["path"])
        patterns = surface["patterns"]
        if not isinstance(patterns, list) or not patterns:
            raise ReleaseVersionError(f"current-version surface has no patterns: {surface['path']}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ReleaseVersionError(
                f"cannot read current-version surface {surface['path']}"
            ) from exc
        matches = 0
        for template in patterns:
            if not isinstance(template, str) or template.count("{version}") != 1:
                raise ReleaseVersionError("current-version surface pattern is invalid")
            pattern = template.replace("{version}", r"(?P<version>[0-9]+\.[0-9]+\.[0-9]+)")
            match = re.search(pattern, text, flags=re.MULTILINE)
            if match is None:
                raise ReleaseVersionError(
                    f"declared current-version claim is missing: {surface['path']}"
                )
            found = StableVersion.parse(match.group("version"))
            if found != expected:
                raise ReleaseVersionError(
                    f"stale current version in {surface['path']}: {found} != {expected}"
                )
            matches += 1
        checked.append(
            {
                "path": surface["path"],
                "purpose": surface["purpose"],
                "claim_count": matches,
            }
        )
    return {
        "manifest": CURRENT_SURFACES.as_posix(),
        "project_version": str(selected),
        "surface_count": len(checked),
        "claim_count": sum(int(item["claim_count"]) for item in checked),
        "surfaces": checked,
    }


def _is_documentation_path(path: str) -> bool:
    candidate = Path(path)
    return (
        path == "README.md" or path.startswith("docs/") or path in PUBLIC_SITE_DOCUMENTATION_PATHS
    ) and candidate.suffix.lower() in DOCUMENTATION_SUFFIXES


def _post_release_documentation_paths(
    repository: Path,
    *,
    tag_commit: str,
    head: str,
) -> list[str]:
    try:
        _git(repository, "merge-base", "--is-ancestor", tag_commit, head)
    except ReleaseVersionError as exc:
        raise ReleaseVersionError("latest stable tag commit is not an ancestor of HEAD") from exc

    raw_changes = _git(
        repository,
        "diff",
        "--name-status",
        "--no-renames",
        "-z",
        tag_commit,
        head,
    )
    tokens = raw_changes.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()
    if not tokens or len(tokens) % 2:
        raise ReleaseVersionError("cannot determine post-release changed paths")

    documentation: list[str] = []
    rejected: list[str] = []
    changed_paths: list[str] = []
    for index in range(0, len(tokens), 2):
        status, path = tokens[index : index + 2]
        safe_path = (
            bool(path)
            and "\\" not in path
            and not path.startswith("/")
            and all(part not in {"", ".", ".."} for part in path.split("/"))
        )
        if status not in ALLOWED_POST_RELEASE_STATUSES or not safe_path:
            rejected.append(f"{status}:{path}")
            continue
        changed_paths.append(path)
        if _is_documentation_path(path):
            documentation.append(path)
        elif path not in GATE_SUPPORT_PATHS:
            rejected.append(f"{status}:{path}")

    if rejected:
        raise ReleaseVersionError(
            "post-release changes are not docs-only: " + ", ".join(sorted(rejected))
        )
    if not documentation:
        raise ReleaseVersionError(
            "post-release docs-only maintenance requires a documentation path"
        )
    return sorted(changed_paths)


def inspect_release_version(
    repository: Path,
    *,
    expected_version: str | None = None,
) -> dict[str, Any]:
    repository = repository.resolve()
    version = _project_version(repository)
    if expected_version is not None and version != StableVersion.parse(expected_version):
        raise ReleaseVersionError(
            f"project version {version} differs from expected version {expected_version}"
        )
    surfaces = (
        inspect_current_version_surfaces(repository, version=version)
        if (repository / CURRENT_SURFACES).is_file()
        else None
    )

    tags = _stable_tags(repository)
    head = _git(repository, "rev-parse", "HEAD")
    if not tags:
        return {
            "format": "opencntx-release-version-gate",
            "format_version": 1,
            "head": head,
            "latest_tag": None,
            "project_version": str(version),
            "result": "INITIAL_RELEASE_AHEAD",
            "current_surfaces": surfaces,
        }

    latest = max(tags)
    latest_tag = tags[latest]
    if version < latest:
        raise ReleaseVersionError(
            f"project version {version} is behind latest stable tag {latest_tag}"
        )
    if version == latest:
        tag_commit = _git(repository, "rev-list", "-n", "1", latest_tag)
        if tag_commit == head:
            result = "TAG_ALIGNED"
            post_release_paths: list[str] = []
        else:
            post_release_paths = _post_release_documentation_paths(
                repository,
                tag_commit=tag_commit,
                head=head,
            )
            result = "POST_RELEASE_DOCS_ONLY"
    else:
        result = "UNRELEASED_VERSION_AHEAD"
        post_release_paths = []

    return {
        "format": "opencntx-release-version-gate",
        "format_version": 1,
        "head": head,
        "latest_tag": latest_tag,
        "post_release_paths": post_release_paths,
        "project_version": str(version),
        "result": result,
        "current_surfaces": surfaces,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail when the package version and latest stable Git tag have drifted."
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--expected-version")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = inspect_release_version(
            arguments.repository,
            expected_version=arguments.expected_version,
        )
    except ReleaseVersionError as exc:
        print(f"RELEASE_VERSION_ERROR: {exc}")
        return 1
    if arguments.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "RELEASE_VERSION_OK: "
            f"project={result['project_version']} latest={result['latest_tag']} "
            f"result={result['result']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
