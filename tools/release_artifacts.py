"""Build and verify local OPENCNTX release candidates without publishing them."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

PROJECT_NAME = "opencntx"
CHECKSUMS_NAME = "SHA256SUMS"
RECORD_NAME = "BUILD-RECORD.json"
RECORD_SCHEMA = "opencntx-build-record-v1"
BUILD_FRONTEND = "build==1.3.0"
BUILD_BACKEND = "setuptools==83.0.0"
MAX_ARCHIVE_MEMBER_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 100 * 1024 * 1024


class ReleaseArtifactError(Exception):
    """A bounded release-candidate validation failure."""


def _validate_build_toolchain() -> None:
    for distribution, expected_version in (
        ("build", "1.3.0"),
        ("setuptools", "83.0.0"),
    ):
        try:
            actual_version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ReleaseArtifactError(
                f"required build tool is not installed: {distribution}"
            ) from exc
        if actual_version != expected_version:
            raise ReleaseArtifactError(
                f"installed {distribution} version differs: "
                f"expected {expected_version}, found {actual_version}"
            )


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=capture,
    )


def _git(repository: Path, *arguments: str) -> str:
    result = _run(
        ["git", "-C", str(repository), *arguments],
        capture=True,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _project_version(repository: Path) -> str:
    with (repository / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)["project"]
    if project.get("name") != PROJECT_NAME:
        raise ReleaseArtifactError("pyproject.toml contains an unexpected project name")
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise ReleaseArtifactError("pyproject.toml contains no valid project version")
    return version


def _safe_member_path(name: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise ReleaseArtifactError(f"unsafe archive member path: {name!r}")
    if any(part in ("", ".", "..") for part in name.split("/")):
        raise ReleaseArtifactError(f"unsafe archive member path: {name!r}")
    path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ReleaseArtifactError(f"unsafe archive member path: {name!r}")
    if any(part in ("", ".", "..") for part in path.parts):
        raise ReleaseArtifactError(f"unsafe archive member path: {name!r}")
    return path


def _zip_inventory(path: Path) -> dict[str, bytes]:
    inventory: dict[str, bytes] = {}
    total_size = 0
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            safe_path = _safe_member_path(member.filename.rstrip("/"))
            normalized = safe_path.as_posix()
            if normalized in inventory:
                raise ReleaseArtifactError(f"duplicate wheel member: {normalized}")
            mode = (member.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            if member.is_dir():
                continue
            if file_type not in (0, stat.S_IFREG):
                raise ReleaseArtifactError(f"non-regular wheel member: {normalized}")
            if member.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                raise ReleaseArtifactError(f"oversized wheel member: {normalized}")
            total_size += member.file_size
            if total_size > MAX_ARCHIVE_TOTAL_BYTES:
                raise ReleaseArtifactError("wheel exceeds the inspection byte limit")
            inventory[normalized] = archive.read(member)
    if not inventory:
        raise ReleaseArtifactError("wheel contains no files")
    return inventory


def _tar_inventory(path: Path) -> dict[str, bytes]:
    inventory: dict[str, bytes] = {}
    total_size = 0
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive.getmembers():
            safe_path = _safe_member_path(member.name.rstrip("/"))
            normalized = safe_path.as_posix()
            if normalized in inventory:
                raise ReleaseArtifactError(f"duplicate sdist member: {normalized}")
            if member.isdir():
                continue
            if not member.isfile():
                raise ReleaseArtifactError(f"non-regular sdist member: {normalized}")
            if member.size > MAX_ARCHIVE_MEMBER_BYTES:
                raise ReleaseArtifactError(f"oversized sdist member: {normalized}")
            total_size += member.size
            if total_size > MAX_ARCHIVE_TOTAL_BYTES:
                raise ReleaseArtifactError("sdist exceeds the inspection byte limit")
            source = archive.extractfile(member)
            if source is None:
                raise ReleaseArtifactError(f"unreadable sdist member: {normalized}")
            inventory[normalized] = source.read()
    if not inventory:
        raise ReleaseArtifactError("sdist contains no files")
    return inventory


def _metadata_value(content: bytes, field: str) -> str:
    message = BytesParser(policy=email_policy).parsebytes(content)
    value = message.get(field)
    if not isinstance(value, str) or not value:
        raise ReleaseArtifactError(f"artifact metadata has no {field}")
    return value


def _artifact_metadata(path: Path) -> tuple[str, str, dict[str, bytes]]:
    if path.name.endswith(".whl"):
        inventory = _zip_inventory(path)
        candidates = [
            content for name, content in inventory.items() if name.endswith(".dist-info/METADATA")
        ]
    elif path.name.endswith(".tar.gz"):
        inventory = _tar_inventory(path)
        candidates = [
            content
            for name, content in inventory.items()
            if len(PurePosixPath(name).parts) == 2 and name.endswith("/PKG-INFO")
        ]
    else:
        raise ReleaseArtifactError(f"unsupported artifact type: {path.name}")
    if len(candidates) != 1:
        raise ReleaseArtifactError(f"expected exactly one primary metadata file in {path.name}")
    return (
        _metadata_value(candidates[0], "Name"),
        _metadata_value(candidates[0], "Version"),
        inventory,
    )


def _artifact_pair(directory: Path) -> tuple[Path, Path]:
    wheels = sorted(directory.glob(f"{PROJECT_NAME}-*.whl"))
    sdists = sorted(directory.glob(f"{PROJECT_NAME}-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseArtifactError("expected exactly one opencntx wheel and one opencntx sdist")
    return wheels[0], sdists[0]


def _inspect_pair(directory: Path, expected_version: str) -> tuple[Path, Path]:
    wheel, sdist = _artifact_pair(directory)
    expected_stem = f"{PROJECT_NAME}-{expected_version}"
    if not wheel.name.startswith(f"{expected_stem}-"):
        raise ReleaseArtifactError(f"unexpected wheel filename: {wheel.name}")
    if sdist.name != f"{expected_stem}.tar.gz":
        raise ReleaseArtifactError(f"unexpected sdist filename: {sdist.name}")

    wheel_name, wheel_version, wheel_inventory = _artifact_metadata(wheel)
    sdist_name, sdist_version, sdist_inventory = _artifact_metadata(sdist)
    if (wheel_name, wheel_version) != (PROJECT_NAME, expected_version):
        raise ReleaseArtifactError("wheel metadata does not match the project")
    if (sdist_name, sdist_version) != (PROJECT_NAME, expected_version):
        raise ReleaseArtifactError("sdist metadata does not match the project")
    if not any(name.startswith("opencntx/") for name in wheel_inventory):
        raise ReleaseArtifactError("wheel contains no opencntx package")

    root = f"{expected_stem}/"
    required_sdist = {
        f"{root}LICENSE",
        f"{root}MANIFEST.in",
        f"{root}README.md",
        f"{root}docs/release-artifacts.md",
        f"{root}pyproject.toml",
        f"{root}src/opencntx/__init__.py",
        f"{root}tests/test_release_artifacts.py",
        f"{root}tools/release_artifacts.py",
    }
    missing = sorted(required_sdist - set(sdist_inventory))
    if missing:
        raise ReleaseArtifactError(f"sdist is missing required files: {missing}")
    for name in sdist_inventory:
        parts = PurePosixPath(name).parts
        if any(part in {".git", ".opencntx", "__pycache__", "build", "dist"} for part in parts):
            raise ReleaseArtifactError(f"sdist contains a forbidden path: {name}")
        if name.endswith((".pyc", ".pyo")):
            raise ReleaseArtifactError(f"sdist contains bytecode: {name}")
    return wheel, sdist


def _extract_git_archive(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive_path, mode="r:") as archive:
        seen: set[str] = set()
        for member in archive.getmembers():
            safe_path = _safe_member_path(member.name.rstrip("/"))
            normalized = safe_path.as_posix()
            if normalized in seen:
                raise ReleaseArtifactError(f"duplicate Git archive member: {normalized}")
            seen.add(normalized)
            target = destination.joinpath(*safe_path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ReleaseArtifactError(f"non-regular Git archive member: {normalized}")
            source = archive.extractfile(member)
            if source is None:
                raise ReleaseArtifactError(f"unreadable Git archive member: {normalized}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())


def _export_source(repository: Path, commit: str, destination: Path) -> None:
    archive_path = destination.parent / f"{destination.name}.tar"
    _run(
        [
            "git",
            "-C",
            str(repository),
            "archive",
            "--format=tar",
            f"--output={archive_path}",
            commit,
        ]
    )
    try:
        _extract_git_archive(archive_path, destination)
    finally:
        archive_path.unlink(missing_ok=True)


def _build_source(source: Path, output: Path, source_date_epoch: str) -> None:
    output.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "SOURCE_DATE_EPOCH": source_date_epoch,
        }
    )
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--sdist",
            "--wheel",
            "--outdir",
            str(output),
            str(source),
        ],
        cwd=source,
        env=environment,
    )


def _write_checksums(output: Path, artifacts: tuple[Path, Path]) -> None:
    lines = [
        f"{_sha256(path)}  {path.name}"
        for path in sorted(artifacts, key=lambda candidate: candidate.name)
    ]
    (output / CHECKSUMS_NAME).write_text("\n".join(lines) + "\n", encoding="ascii")


def _record(
    *,
    artifacts: tuple[Path, Path],
    version: str,
    commit: str,
    tree: str,
    source_date_epoch: int,
    sdist_byte_reproducible: bool,
) -> dict[str, Any]:
    return {
        "artifacts": [
            {
                "filename": path.name,
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            }
            for path in sorted(artifacts, key=lambda candidate: candidate.name)
        ],
        "build_frontend": BUILD_FRONTEND,
        "build_backend": BUILD_BACKEND,
        "project": PROJECT_NAME,
        "provenance": {
            "attestation": False,
            "signed": False,
            "statement": "Unsigned local build record; not publisher identity.",
        },
        "python": {
            "implementation": sys.implementation.name,
            "version": ".".join(str(part) for part in sys.version_info[:3]),
        },
        "reproducibility": {
            "sdist_bytes": sdist_byte_reproducible,
            "sdist_content": True,
            "wheel_bytes": True,
        },
        "schema": RECORD_SCHEMA,
        "source": {
            "commit": commit,
            "source_date_epoch": source_date_epoch,
            "tree": tree,
        },
        "version": version,
    }


def verify_candidate(
    directory: Path,
    *,
    expected_version: str,
    expected_commit: str,
    expected_tree: str,
) -> dict[str, Any]:
    directory = directory.resolve()
    wheel, sdist = _inspect_pair(directory, expected_version)
    expected_names = {wheel.name, sdist.name, CHECKSUMS_NAME, RECORD_NAME}
    actual_names = {path.name for path in directory.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise ReleaseArtifactError(
            f"candidate directory differs: expected {sorted(expected_names)}, "
            f"found {sorted(actual_names)}"
        )

    expected_checksum_text = (
        "\n".join(
            f"{_sha256(path)}  {path.name}"
            for path in sorted((wheel, sdist), key=lambda candidate: candidate.name)
        )
        + "\n"
    )
    checksum_text = (directory / CHECKSUMS_NAME).read_text(encoding="ascii")
    if checksum_text != expected_checksum_text:
        raise ReleaseArtifactError("SHA256SUMS does not match the exact artifacts")

    record_path = directory / RECORD_NAME
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseArtifactError("BUILD-RECORD.json is not valid UTF-8 JSON") from exc
    if record_path.read_bytes() != _canonical_json(record):
        raise ReleaseArtifactError("BUILD-RECORD.json is not canonical")
    if record.get("schema") != RECORD_SCHEMA:
        raise ReleaseArtifactError("build record schema is not supported")
    if record.get("project") != PROJECT_NAME or record.get("version") != expected_version:
        raise ReleaseArtifactError("build record project or version differs")
    if record.get("build_frontend") != BUILD_FRONTEND:
        raise ReleaseArtifactError("build record frontend differs from the approved pin")
    if record.get("build_backend") != BUILD_BACKEND:
        raise ReleaseArtifactError("build record backend differs from the approved pin")
    source = record.get("source")
    if (
        not isinstance(source, dict)
        or source.get("commit") != expected_commit
        or source.get("tree") != expected_tree
    ):
        raise ReleaseArtifactError("build record source binding differs")
    provenance = record.get("provenance")
    if (
        provenance is None
        or provenance.get("signed") is not False
        or provenance.get("attestation") is not False
    ):
        raise ReleaseArtifactError("build record must remain explicitly unsigned")
    expected_artifacts = [
        {"filename": path.name, "sha256": _sha256(path), "size": path.stat().st_size}
        for path in sorted((wheel, sdist), key=lambda candidate: candidate.name)
    ]
    if record.get("artifacts") != expected_artifacts:
        raise ReleaseArtifactError("build record artifact inventory differs")
    reproducibility = record.get("reproducibility")
    if not isinstance(reproducibility, dict):
        raise ReleaseArtifactError("build record has no reproducibility result")
    if (
        reproducibility.get("wheel_bytes") is not True
        or reproducibility.get("sdist_content") is not True
    ):
        raise ReleaseArtifactError("required reproducibility evidence is absent")
    return record


def build_candidate(
    repository: Path,
    output: Path,
    *,
    expected_commit: str,
    expected_tree: str,
) -> dict[str, Any]:
    repository = repository.resolve()
    output = output.resolve()
    _validate_build_toolchain()
    if output.exists() and any(output.iterdir()):
        raise ReleaseArtifactError(f"output directory is not empty: {output}")
    if _git(repository, "status", "--porcelain=v1"):
        raise ReleaseArtifactError("repository worktree is not clean")
    commit = _git(repository, "rev-parse", "HEAD")
    tree = _git(repository, "rev-parse", "HEAD^{tree}")
    if commit != expected_commit or tree != expected_tree:
        raise ReleaseArtifactError("repository HEAD or tree differs from the expected source")
    version = _project_version(repository)
    source_date_epoch_text = _git(repository, "show", "-s", "--format=%ct", commit)
    source_date_epoch = int(source_date_epoch_text)

    with tempfile.TemporaryDirectory(prefix="opencntx-release-build-") as temp_name:
        temp_root = Path(temp_name)
        source_one = temp_root / "source-one"
        source_two = temp_root / "source-two"
        build_one = temp_root / "build-one"
        build_two = temp_root / "build-two"
        _export_source(repository, commit, source_one)
        _export_source(repository, commit, source_two)
        _build_source(source_one, build_one, source_date_epoch_text)
        _build_source(source_two, build_two, source_date_epoch_text)
        wheel_one, sdist_one = _inspect_pair(build_one, version)
        wheel_two, sdist_two = _inspect_pair(build_two, version)
        if wheel_one.read_bytes() != wheel_two.read_bytes():
            raise ReleaseArtifactError("independent wheel builds are not byte-identical")
        sdist_one_inventory = _tar_inventory(sdist_one)
        sdist_two_inventory = _tar_inventory(sdist_two)
        if sdist_one_inventory != sdist_two_inventory:
            raise ReleaseArtifactError("independent sdist contents differ")
        sdist_byte_reproducible = sdist_one.read_bytes() == sdist_two.read_bytes()

        output.mkdir(parents=True, exist_ok=True)
        copied = (
            Path(shutil.copy2(wheel_one, output / wheel_one.name)),
            Path(shutil.copy2(sdist_one, output / sdist_one.name)),
        )
        _write_checksums(output, copied)
        record = _record(
            artifacts=copied,
            version=version,
            commit=commit,
            tree=tree,
            source_date_epoch=source_date_epoch,
            sdist_byte_reproducible=sdist_byte_reproducible,
        )
        (output / RECORD_NAME).write_bytes(_canonical_json(record))

    verify_candidate(
        output,
        expected_version=version,
        expected_commit=commit,
        expected_tree=tree,
    )
    return record


def _venv_paths(environment: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        return (
            environment / "Scripts" / "python.exe",
            environment / "Scripts" / "opencntx.exe",
        )
    return environment / "bin" / "python", environment / "bin" / "opencntx"


def smoke_artifact(artifact: Path, *, expected_version: str) -> None:
    artifact = artifact.resolve()
    name, version, _ = _artifact_metadata(artifact)
    if (name, version) != (PROJECT_NAME, expected_version):
        raise ReleaseArtifactError("smoke artifact metadata differs")
    with tempfile.TemporaryDirectory(prefix="opencntx-install-smoke-") as temp_name:
        root = Path(temp_name)
        environment = root / "venv"
        project = root / "project"
        project.mkdir()
        (project / "README.md").write_text("# Installation smoke\n", encoding="utf-8")
        venv.EnvBuilder(with_pip=True).create(environment)
        python, command = _venv_paths(environment)
        clean_environment = os.environ.copy()
        clean_environment.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-deps",
                str(artifact),
            ],
            cwd=project,
            env=clean_environment,
        )
        version_result = _run(
            [str(command), "--version"],
            cwd=project,
            env=clean_environment,
            capture=True,
        )
        if version_result.stdout.strip() != f"{PROJECT_NAME} {expected_version}":
            raise ReleaseArtifactError("installed --version output differs")
        for arguments in (
            ["--help"],
            ["init"],
            ["pack", "--preview"],
            ["pack"],
            ["verify"],
        ):
            _run([str(command), *arguments], cwd=project, env=clean_environment)
        _run(
            [
                str(python),
                "-c",
                (
                    "import importlib.metadata as m; "
                    f"assert m.version('{PROJECT_NAME}') == '{expected_version}'"
                ),
            ],
            cwd=project,
            env=clean_environment,
        )
        _run(
            [str(python), "-m", "pip", "uninstall", "--yes", PROJECT_NAME],
            cwd=project,
            env=clean_environment,
        )
        _run(
            [
                str(python),
                "-c",
                (
                    "import importlib.metadata as m; "
                    "\ntry: m.version('opencntx')"
                    "\nexcept m.PackageNotFoundError: raise SystemExit(0)"
                    "\nraise SystemExit('opencntx metadata remains after uninstall')"
                ),
            ],
            cwd=project,
            env=clean_environment,
        )
        if command.exists():
            raise ReleaseArtifactError("opencntx entrypoint remains after uninstall")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and verify unpublished OPENCNTX release candidates."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build twice and emit one candidate set")
    build.add_argument("--repository", type=Path, default=Path.cwd())
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--expected-commit", required=True)
    build.add_argument("--expected-tree", required=True)

    verify = subparsers.add_parser("verify", help="verify one candidate set")
    verify.add_argument("--directory", type=Path, required=True)
    verify.add_argument("--expected-version", required=True)
    verify.add_argument("--expected-commit", required=True)
    verify.add_argument("--expected-tree", required=True)

    smoke = subparsers.add_parser("smoke", help="install, exercise, and uninstall one artifact")
    smoke.add_argument("--artifact", type=Path, required=True)
    smoke.add_argument("--expected-version", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "build":
            record = build_candidate(
                arguments.repository,
                arguments.output,
                expected_commit=arguments.expected_commit,
                expected_tree=arguments.expected_tree,
            )
            print(
                "CANDIDATE_VERIFIED: "
                f"{record['project']} {record['version']} / "
                f"wheel-bytes={record['reproducibility']['wheel_bytes']} / "
                f"sdist-content={record['reproducibility']['sdist_content']} / "
                f"sdist-bytes={record['reproducibility']['sdist_bytes']}"
            )
        elif arguments.command == "verify":
            verify_candidate(
                arguments.directory,
                expected_version=arguments.expected_version,
                expected_commit=arguments.expected_commit,
                expected_tree=arguments.expected_tree,
            )
            print("CANDIDATE_VERIFIED")
        else:
            smoke_artifact(
                arguments.artifact,
                expected_version=arguments.expected_version,
            )
            print(f"INSTALL_SMOKE_VERIFIED: {arguments.artifact.name}")
    except (OSError, ReleaseArtifactError, subprocess.CalledProcessError) as exc:
        print(f"RELEASE_ARTIFACT_ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
