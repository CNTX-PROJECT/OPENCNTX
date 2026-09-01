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
        }

    latest = max(tags)
    latest_tag = tags[latest]
    if version < latest:
        raise ReleaseVersionError(
            f"project version {version} is behind latest stable tag {latest_tag}"
        )
    if version == latest:
        tag_commit = _git(repository, "rev-list", "-n", "1", latest_tag)
        if tag_commit != head:
            raise ReleaseVersionError(
                f"project version {version} equals {latest_tag}, but HEAD is not that release commit"
            )
        result = "TAG_ALIGNED"
    else:
        result = "UNRELEASED_VERSION_AHEAD"

    return {
        "format": "opencntx-release-version-gate",
        "format_version": 1,
        "head": head,
        "latest_tag": latest_tag,
        "project_version": str(version),
        "result": result,
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
