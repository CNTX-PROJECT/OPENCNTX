"""Deterministic, local-only context packaging and verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

from .integrity import Transaction, state_digest, writer_transaction
from .security import (
    POLICY_VERSION,
    SecretAssessment,
    SecretFinding,
    assess_findings,
    finding_record,
    format_finding,
    scan_sources,
)

DEFAULT_EXCLUDE_PATTERNS = (
    ".git/**",
    ".opencntx/**",
    ".env*",
    "**/.env*",
    "**/*.key",
    "**/*.pem",
    "**/.aws/credentials",
    "**/.ssh/id_*",
    "**/.netrc",
    "**/.npmrc",
    "**/.pypirc",
    "**/.docker/config.json",
    "**/application_default_credentials.json",
)
PACKAGE_DIRECTORY = Path(".opencntx") / "latest"
MANIFEST_VERSION = 1


class OpenCntxError(Exception):
    """A short, user-facing OPENCNTX error."""


@dataclass(frozen=True)
class ContextConfig:
    goal: str
    include: tuple[str, ...]
    required: tuple[str, ...]
    exclude: tuple[str, ...]
    max_files: int
    max_bytes: int


@dataclass(frozen=True)
class IncludedPath:
    path: str
    include_pattern: str
    required_by: tuple[str, ...]


@dataclass(frozen=True)
class Selection:
    files: tuple[tuple[str, Path], ...]
    excluded: tuple[dict[str, str], ...]
    ignored: tuple[dict[str, str], ...]
    included: tuple[IncludedPath, ...] = ()


@dataclass(frozen=True)
class Source:
    path: str
    content: bytes
    text: str
    sha256: str

    @property
    def byte_count(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class PackPlan:
    config: ContextConfig
    selection: Selection
    sources: tuple[Source, ...]
    security: SecretAssessment

    @property
    def total_bytes(self) -> int:
        return sum(source.byte_count for source in self.sources)


@dataclass(frozen=True)
class VerifyReport:
    unchanged: tuple[str, ...]
    changed: tuple[str, ...]
    missing: tuple[str, ...]
    unexpected: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (self.changed or self.missing or self.unexpected or self.errors)


def _deduplicate(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _normalize_pattern(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpenCntxError(f"{label} contains an empty or invalid pattern.")
    pattern = value.strip().replace("\\", "/")
    while "//" in pattern:
        pattern = pattern.replace("//", "/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    if not pattern or "\x00" in pattern:
        raise OpenCntxError(f"{label} contains an empty or invalid pattern.")
    if PurePosixPath(pattern).is_absolute() or PureWindowsPath(pattern).is_absolute():
        raise OpenCntxError(f"{label} must not contain an absolute path: {value}")
    if ".." in PurePosixPath(pattern).parts:
        raise OpenCntxError(f"{label} must stay within the project root: {value}")
    return pattern


def _normalize_relative_path(value: object, label: str) -> str:
    path = _normalize_pattern(value, label)
    if any(character in path for character in "*?["):
        raise OpenCntxError(f"{label} is not a literal relative path: {value}")
    return path


def _string_list(
    table: dict[str, Any],
    key: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    value = table.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise OpenCntxError(f"context.{key} must be a list of paths.")
    if not allow_empty and not value:
        raise OpenCntxError(f"context.{key} must not be empty.")
    return tuple(_normalize_pattern(item, f"context.{key}") for item in value)


def _positive_integer(table: dict[str, Any], key: str) -> int:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise OpenCntxError(f"context.{key} must be a positive integer.")
    return value


def _config_from_tables(
    task: dict[str, Any],
    context: dict[str, Any],
    *,
    add_default_excludes: bool,
) -> ContextConfig:
    goal = task.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise OpenCntxError("task.goal must be non-empty text.")

    include = _deduplicate(list(_string_list(context, "include", allow_empty=False)))
    required = _deduplicate(list(_string_list(context, "required", allow_empty=True)))
    configured_exclude = list(_string_list(context, "exclude", allow_empty=True))
    excludes = (
        list(DEFAULT_EXCLUDE_PATTERNS) + configured_exclude
        if add_default_excludes
        else configured_exclude
    )
    exclude = _deduplicate([_normalize_pattern(item, "context.exclude") for item in excludes])
    return ContextConfig(
        goal=goal.strip(),
        include=include,
        required=required,
        exclude=exclude,
        max_files=_positive_integer(context, "max_files"),
        max_bytes=_positive_integer(context, "max_bytes"),
    )


def load_config(project_root: Path) -> ContextConfig:
    """Read and strictly validate ``opencntx.toml`` in a project root."""
    root = project_root.resolve(strict=True)
    config_path = root / "opencntx.toml"
    try:
        resolved_config = config_path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise OpenCntxError("opencntx.toml is missing; run 'opencntx init' first.") from exc
    if not resolved_config.is_relative_to(root):
        raise OpenCntxError("opencntx.toml must stay within the project root.")
    try:
        with resolved_config.open("rb") as config_file:
            data = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise OpenCntxError(f"opencntx.toml contains invalid TOML: {exc}") from exc
    except OSError as exc:
        raise OpenCntxError(f"opencntx.toml cannot be read: {exc}") from exc

    if not isinstance(data, dict):
        raise OpenCntxError("opencntx.toml does not contain a valid table structure.")
    unknown_root = set(data) - {"task", "context"}
    if unknown_root:
        raise OpenCntxError(f"Unknown TOML section or key: {min(unknown_root)}")
    task = data.get("task")
    context = data.get("context")
    if not isinstance(task, dict) or not isinstance(context, dict):
        raise OpenCntxError("opencntx.toml requires the [task] and [context] tables.")
    unknown_task = set(task) - {"goal"}
    unknown_context = set(context) - {
        "include",
        "required",
        "exclude",
        "max_files",
        "max_bytes",
    }
    if unknown_task or unknown_context:
        unknown = min(unknown_task | unknown_context)
        raise OpenCntxError(f"Unknown configuration key: {unknown}")
    return _config_from_tables(task, context, add_default_excludes=True)


def _matches_pattern(relative_path: str, pattern: str) -> bool:
    if fnmatchcase(relative_path, pattern):
        return True
    if pattern.endswith("/**") and relative_path == pattern[:-3].rstrip("/"):
        return True
    if pattern.startswith("**/") and fnmatchcase(relative_path, pattern[3:]):
        return True
    if "/" not in pattern:
        return any(fnmatchcase(part, pattern) for part in PurePosixPath(relative_path).parts)
    return False


def _matching_exclusion(relative_path: str, patterns: tuple[str, ...]) -> str | None:
    return next(
        (pattern for pattern in patterns if _matches_pattern(relative_path, pattern)),
        None,
    )


def _expand(root: Path, pattern: str) -> list[Path]:
    try:
        return sorted(root.glob(pattern), key=lambda path: path.relative_to(root).as_posix())
    except (OSError, ValueError) as exc:
        raise OpenCntxError(f"Include pattern cannot be expanded: {pattern}: {exc}") from exc


def discover_sources(
    project_root: Path,
    config: ContextConfig,
    *,
    enforce_required: bool,
) -> Selection:
    """Expand includes deterministically and exclude paths before reading bytes."""
    root = project_root.resolve(strict=True)
    selected: dict[str, Path] = {}
    include_reasons: dict[str, str] = {}
    excluded: dict[tuple[str, str], dict[str, str]] = {}
    ignored: dict[tuple[str, str], dict[str, str]] = {}

    for pattern in config.include:
        matches = _expand(root, pattern)
        if not matches:
            ignored[(pattern, "no match")] = {
                "pattern": pattern,
                "reason": "include pattern matched no path",
            }
        for candidate in matches:
            try:
                relative_path = candidate.relative_to(root).as_posix()
            except ValueError as exc:
                raise OpenCntxError(f"Path leaves the project root: {candidate}") from exc
            exclusion = _matching_exclusion(relative_path, config.exclude)
            if exclusion is not None:
                if relative_path == ".opencntx" or relative_path.startswith(".opencntx/"):
                    continue
                excluded[(relative_path, exclusion)] = {
                    "path": relative_path,
                    "pattern": exclusion,
                    "reason": "excluded before reading",
                }
                continue
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise OpenCntxError(
                    f"Source path is missing or inaccessible: {relative_path}: {exc}"
                ) from exc
            if not resolved.is_relative_to(root):
                raise OpenCntxError(
                    f"Source path leaves the project root through a symlink: {relative_path}"
                )
            if resolved.is_dir():
                ignored[(relative_path, "directory")] = {
                    "path": relative_path,
                    "reason": "directory is not a text source",
                }
                continue
            if not resolved.is_file():
                ignored[(relative_path, "not a file")] = {
                    "path": relative_path,
                    "reason": "path is not a regular file",
                }
                continue
            selected[relative_path] = resolved
            include_reasons.setdefault(relative_path, pattern)

    ordered_files = tuple(sorted(selected.items()))
    included = tuple(
        IncludedPath(
            path=path,
            include_pattern=include_reasons[path],
            required_by=tuple(
                pattern for pattern in config.required if _matches_pattern(path, pattern)
            ),
        )
        for path, _ in ordered_files
    )
    if enforce_required:
        selected_paths = tuple(path for path, _ in ordered_files)
        for pattern in config.required:
            if not any(_matches_pattern(path, pattern) for path in selected_paths):
                raise OpenCntxError(f"Required pattern produces no included file: {pattern}")
    return Selection(
        files=ordered_files,
        included=included,
        excluded=tuple(excluded[key] for key in sorted(excluded)),
        ignored=tuple(ignored[key] for key in sorted(ignored)),
    )


def _read_source(
    project_root: Path,
    relative_path: str,
    *,
    byte_budget: int | None = None,
    consumed_bytes: int = 0,
) -> Source:
    root = project_root.resolve(strict=True)
    safe_path = _normalize_relative_path(relative_path, "source path")
    logical_path = root.joinpath(*PurePosixPath(safe_path).parts)
    try:
        resolved = logical_path.resolve(strict=True)
    except OSError as exc:
        raise OpenCntxError(f"Source is missing or inaccessible: {safe_path}: {exc}") from exc
    if not resolved.is_relative_to(root):
        raise OpenCntxError(f"Source leaves the project root through a symlink: {safe_path}")
    try:
        declared_size = resolved.stat().st_size
        required_bytes = consumed_bytes + declared_size
        if byte_budget is not None and required_bytes > byte_budget:
            raise OpenCntxError(
                f"Byte budget exceeded before reading: {safe_path} "
                f"(required={required_bytes} bytes; allowed={byte_budget} bytes). "
                "Reduce context.include, exclude the file, or increase max_bytes."
            )
        content = resolved.read_bytes()
        required_bytes = consumed_bytes + len(content)
        if byte_budget is not None and required_bytes > byte_budget:
            raise OpenCntxError(
                f"Byte budget exceeded while reading: {safe_path} "
                f"(required={required_bytes} bytes; allowed={byte_budget} bytes). "
                "Reduce context.include, exclude the file, or increase max_bytes."
            )
    except OpenCntxError:
        raise
    except OSError as exc:
        raise OpenCntxError(f"Source cannot be read: {safe_path}: {exc}") from exc
    if b"\x00" in content or any(byte < 32 and byte not in (9, 10, 13) for byte in content):
        raise OpenCntxError(f"Binary source is rejected: {safe_path}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OpenCntxError(f"Source is not valid UTF-8 text: {safe_path}") from exc
    return Source(
        path=safe_path,
        content=content,
        text=text,
        sha256=hashlib.sha256(content).hexdigest(),
    )


def read_sources(
    project_root: Path,
    selection: Selection,
    config: ContextConfig,
) -> tuple[Source, ...]:
    if not selection.files:
        raise OpenCntxError("No text sources selected; adjust context.include.")
    if len(selection.files) > config.max_files:
        raise OpenCntxError(
            f"File budget exceeded: {len(selection.files)} > {config.max_files}. "
            "Reduce context.include or increase max_files."
        )
    sources: list[Source] = []
    total_bytes = 0
    for relative_path, _ in selection.files:
        source = _read_source(
            project_root,
            relative_path,
            byte_budget=config.max_bytes,
            consumed_bytes=total_bytes,
        )
        total_bytes += source.byte_count
        if total_bytes > config.max_bytes:
            raise OpenCntxError(
                f"Byte budget exceeded: {total_bytes} > {config.max_bytes}. "
                "Reduce context.include, exclude large files, or increase max_bytes."
            )
        sources.append(source)
    return tuple(sources)


def plan_project(
    project_root: Path,
    *,
    allowed_secret_ids: tuple[str, ...] = (),
) -> PackPlan:
    """Build the complete read-only plan shared by preview and pack."""
    root = project_root.resolve(strict=True)
    config = load_config(root)
    selection = discover_sources(root, config, enforce_required=True)
    sources = read_sources(root, selection, config)
    findings = scan_sources((source.path, source.text, source.sha256) for source in sources)
    try:
        security = assess_findings(findings, allowed_secret_ids)
    except ValueError as exc:
        raise OpenCntxError(str(exc)) from exc
    return PackPlan(
        config=config,
        selection=selection,
        sources=sources,
        security=security,
    )


def format_pack_preview(plan: PackPlan) -> str:
    """Render safe deterministic preview metadata without source snippets."""
    lines = ["preview:", f"included ({len(plan.selection.included)}):"]
    for included in plan.selection.included:
        required_by = ",".join(included.required_by) if included.required_by else "-"
        lines.append(
            f"  {included.path} | include={included.include_pattern} | required={required_by}"
        )

    lines.append(f"excluded ({len(plan.selection.excluded)}):")
    for excluded in plan.selection.excluded:
        lines.append(
            f"  {excluded['path']} | pattern={excluded['pattern']} | reason={excluded['reason']}"
        )

    lines.append(f"ignored ({len(plan.selection.ignored)}):")
    for ignored in plan.selection.ignored:
        subject = ignored.get("path", ignored.get("pattern", "-"))
        pattern = ignored.get("pattern")
        pattern_part = f" | pattern={pattern}" if pattern is not None else ""
        lines.append(f"  {subject}{pattern_part} | reason={ignored['reason']}")

    lines.extend(
        (
            "budgets:",
            f"  files={len(plan.sources)}/{plan.config.max_files}",
            f"  bytes={plan.total_bytes}/{plan.config.max_bytes}",
        )
    )
    for label, findings in (
        ("warnings", plan.security.warnings),
        ("blocked", plan.security.blocked),
        ("overrides", plan.security.overrides),
    ):
        lines.append(f"{label} ({len(findings)}):")
        lines.extend(f"  {format_finding(finding)}" for finding in findings)
    lines.append(
        "result: PACK_WOULD_BE_BLOCKED" if plan.security.blocked else "result: PACK_WOULD_SUCCEED"
    )
    return "\n".join(lines)


def _blocked_secret_error(findings: tuple[SecretFinding, ...]) -> OpenCntxError:
    details = "; ".join(format_finding(finding) for finding in findings)
    return OpenCntxError(
        f"Secret policy blocks {len(findings)} high-confidence finding(s): "
        f"{details}. Use 'opencntx pack --preview' and only an exact "
        "--allow-secret finding ID when you deliberately want to include these bytes."
    )


def _markdown_fence(text: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def render_context(goal: str, sources: tuple[Source, ...], *, legacy: bool = False) -> str:
    lines = [
        "# OPENCNTX Context Package",
        "",
        "## Taak" if legacy else "## Task",
        "",
        goal,
        "",
        "## Bronnen" if legacy else "## Sources",
    ]
    for source in sources:
        fence = _markdown_fence(source.text)
        lines.extend(
            [
                "",
                f"### `{source.path}`",
                "",
                f"- Bytes: {source.byte_count}",
                f"- SHA-256: `{source.sha256}`",
                "",
                f"{fence}text",
                source.text,
                fence,
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _security_manifest(security: SecretAssessment) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "warnings": [
            finding_record(finding, disposition="warning") for finding in security.warnings
        ],
        "overrides": [
            finding_record(finding, disposition="overridden") for finding in security.overrides
        ],
    }


def _manifest(
    config: ContextConfig,
    selection: Selection,
    sources: tuple[Source, ...],
    context_bytes: bytes,
    security: SecretAssessment | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "format": "opencntx-manifest",
        "format_version": MANIFEST_VERSION,
        "task": {"goal": config.goal},
        "selection": {
            "include": list(config.include),
            "required": list(config.required),
            "exclude": list(config.exclude),
            "max_files": config.max_files,
            "max_bytes": config.max_bytes,
        },
        "package": {
            "file_count": len(sources),
            "total_bytes": sum(source.byte_count for source in sources),
            "context_sha256": hashlib.sha256(context_bytes).hexdigest(),
        },
        "sources": [
            {
                "path": source.path,
                "bytes": source.byte_count,
                "sha256": source.sha256,
            }
            for source in sources
        ],
        "excluded": list(selection.excluded),
        "ignored": list(selection.ignored),
    }
    if security is not None:
        manifest["security"] = _security_manifest(security)
    return manifest


def _write_file(path: Path, content: bytes) -> None:
    with path.open("xb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def _atomic_package_write(
    project_root: Path,
    context_bytes: bytes,
    manifest_bytes: bytes,
    *,
    _transaction: Transaction | None = None,
) -> Path:
    root = project_root.resolve(strict=True)
    output_parent = root / ".opencntx"
    if output_parent.is_symlink():
        raise OpenCntxError(".opencntx must not be a symlink.")
    try:
        output_parent.mkdir(exist_ok=True)
        resolved_parent = output_parent.resolve(strict=True)
    except OSError as exc:
        raise OpenCntxError(f"Output directory cannot be created: {exc}") from exc
    if not resolved_parent.is_relative_to(root) or not resolved_parent.is_dir():
        raise OpenCntxError("Output directory must be inside the project root.")

    latest = output_parent / "latest"
    if latest.is_symlink():
        raise OpenCntxError(".opencntx/latest must not be a symlink.")
    temporary = Path(tempfile.mkdtemp(prefix=".building-", dir=output_parent))
    backup: Path | None = None
    try:
        _write_file(temporary / "CONTEXT.md", context_bytes)
        _write_file(temporary / "manifest.json", manifest_bytes)
        if _transaction is not None:
            _transaction.track_target(latest)
        if latest.exists():
            if not latest.is_dir():
                raise OpenCntxError(".opencntx/latest is not a package directory.")
            backup = output_parent / f".previous-{uuid4().hex}"
            os.replace(latest, backup)
        try:
            os.replace(temporary, latest)
        except OSError:
            if backup is not None and backup.exists() and not latest.exists():
                os.replace(backup, latest)
            raise
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
        if _transaction is not None:
            _transaction.mark_target_published(latest)
            _transaction.mark_published()
        return latest
    except OpenCntxError:
        raise
    except OSError as exc:
        raise OpenCntxError(f"Package could not be written atomically: {exc}") from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def pack_project(
    project_root: Path,
    *,
    allowed_secret_ids: tuple[str, ...] = (),
) -> tuple[Path, dict[str, Any]]:
    """Build the complete package in memory, then atomically publish it."""
    root = project_root.resolve(strict=True)
    plan = plan_project(root, allowed_secret_ids=allowed_secret_ids)
    if plan.security.blocked:
        raise _blocked_secret_error(plan.security.blocked)
    context_bytes = render_context(plan.config.goal, plan.sources).encode("utf-8")
    manifest = _manifest(
        plan.config,
        plan.selection,
        plan.sources,
        context_bytes,
        plan.security,
    )
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    from .lifecycle import require_disk_capacity

    require_disk_capacity(
        root,
        (len(context_bytes) + len(manifest_bytes)) * 2 + 16 * 1024,
        "core-pack",
    )
    plan_digest = hashlib.sha256(
        json.dumps(
            [{"path": source.path, "sha256": source.sha256} for source in plan.sources],
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    package_state = state_digest((root / ".opencntx" / "latest",))
    expected = hashlib.sha256(f"{plan_digest}:{package_state}".encode("ascii")).hexdigest()

    def current_digest() -> str:
        current = plan_project(root, allowed_secret_ids=allowed_secret_ids)
        current_plan_digest = hashlib.sha256(
            json.dumps(
                [{"path": source.path, "sha256": source.sha256} for source in current.sources],
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        current_package_state = state_digest((root / ".opencntx" / "latest",))
        return hashlib.sha256(
            f"{current_plan_digest}:{current_package_state}".encode("ascii")
        ).hexdigest()

    with writer_transaction(
        root,
        "core-pack",
        expected_digest=expected,
        current_digest=current_digest,
    ) as transaction:
        package_path = _atomic_package_write(
            root,
            context_bytes,
            manifest_bytes,
            _transaction=transaction,
        )
        transaction.mark_receipted(None)
        return package_path, manifest


def _load_manifest(package_path: Path) -> tuple[Path, Path, dict[str, Any], ContextConfig]:
    try:
        package = package_path.resolve(strict=True)
    except OSError as exc:
        raise OpenCntxError(
            f"Package directory is missing or inaccessible: {package_path}"
        ) from exc
    if not package.is_dir() or package.parent.name != ".opencntx":
        raise OpenCntxError("Package directory must be directly below .opencntx.")
    root = package.parent.parent.resolve(strict=True)
    manifest_path = package / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OpenCntxError("manifest.json is missing from the package.") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenCntxError(f"manifest.json is invalid or unreadable: {exc}") from exc
    if not isinstance(manifest, dict):
        raise OpenCntxError("manifest.json does not contain a valid object structure.")
    if (
        manifest.get("format") != "opencntx-manifest"
        or manifest.get("format_version") != MANIFEST_VERSION
    ):
        raise OpenCntxError("manifest.json uses an unknown format or version.")
    task = manifest.get("task")
    selection = manifest.get("selection")
    if not isinstance(task, dict) or not isinstance(selection, dict):
        raise OpenCntxError("manifest.json is missing task or selection data.")
    config = _config_from_tables(task, selection, add_default_excludes=False)
    return root, package, manifest, config


def _expected_sources(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source_list = manifest.get("sources")
    if not isinstance(source_list, list):
        raise OpenCntxError("manifest.json is missing a valid source list.")
    expected: dict[str, dict[str, Any]] = {}
    for item in source_list:
        if not isinstance(item, dict):
            raise OpenCntxError("manifest.json contains an invalid source record.")
        path = _normalize_relative_path(item.get("path"), "manifest source path")
        byte_count = item.get("bytes")
        digest = item.get("sha256")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise OpenCntxError(f"manifest.json contains invalid metadata for: {path}")
        if path in expected:
            raise OpenCntxError(f"manifest.json contains a duplicate source path: {path}")
        expected[path] = item
    return expected


def _manifest_security_errors(
    manifest: dict[str, Any],
    current_sources: dict[str, Source],
) -> tuple[str, ...]:
    if "security" not in manifest:
        return ()
    security = manifest.get("security")
    if not isinstance(security, dict):
        return ("manifest.json contains invalid security metadata",)
    if set(security) != {"policy_version", "warnings", "overrides"}:
        return ("manifest.json contains invalid security metadata",)
    if security.get("policy_version") != POLICY_VERSION:
        return ("manifest.json uses an unknown secret policy version",)
    warnings = security.get("warnings")
    overrides = security.get("overrides")
    if not isinstance(warnings, list) or not isinstance(overrides, list):
        return ("manifest.json contains invalid security metadata",)
    if any(not isinstance(record, dict) for record in warnings + overrides):
        return ("manifest.json contains invalid security metadata",)
    allowed_ids = tuple(record.get("finding_id") for record in overrides)
    if any(not isinstance(finding_id, str) for finding_id in allowed_ids):
        return ("manifest.json contains invalid override data",)

    findings = scan_sources(
        (source.path, source.text, source.sha256) for source in current_sources.values()
    )
    try:
        assessment = assess_findings(findings, allowed_ids)
    except (TypeError, ValueError):
        return ("manifest.json contains invalid override data",)
    if assessment.blocked:
        return ("manifest.json is missing a required secret block or override",)
    if security != _security_manifest(assessment):
        return ("manifest.json security metadata differs from the current sources",)
    return ()


def verify_package(package_path: Path) -> VerifyReport:
    """Compare a package with current sources without writing any file."""
    root, package, manifest, config = _load_manifest(package_path)
    expected = _expected_sources(manifest)
    errors: list[str] = []

    package_info = manifest.get("package")
    if not isinstance(package_info, dict):
        raise OpenCntxError("manifest.json is missing valid package metadata.")
    expected_context_hash = package_info.get("context_sha256")
    if (
        isinstance(package_info.get("file_count"), bool)
        or package_info.get("file_count") != len(expected)
        or isinstance(package_info.get("total_bytes"), bool)
        or package_info.get("total_bytes") != sum(item["bytes"] for item in expected.values())
        or not isinstance(expected_context_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_context_hash) is None
    ):
        errors.append("manifest.json contains internally inconsistent package metadata")
    try:
        context_bytes = (package / "CONTEXT.md").read_bytes()
        actual_context_hash = hashlib.sha256(context_bytes).hexdigest()
        if expected_context_hash != actual_context_hash:
            errors.append("CONTEXT.md differs from the manifest hash")
    except OSError as exc:
        errors.append(f"CONTEXT.md cannot be fully verified: {exc}")

    selection: Selection | None
    try:
        selection = discover_sources(root, config, enforce_required=False)
        current_paths = {path for path, _ in selection.files}
    except OpenCntxError as exc:
        selection = None
        current_paths = {
            path for path in expected if root.joinpath(*PurePosixPath(path).parts).exists()
        }
        errors.append(f"Source selection is incomplete: {exc}")

    expected_paths = set(expected)
    missing = sorted(expected_paths - current_paths)
    unexpected = sorted(current_paths - expected_paths)
    changed: list[str] = []
    unchanged: list[str] = []
    current_sources: dict[str, Source] = {}
    total_bytes = 0
    for path in sorted(current_paths):
        try:
            source = _read_source(
                root,
                path,
                byte_budget=config.max_bytes,
                consumed_bytes=total_bytes,
            )
            current_sources[path] = source
            total_bytes += source.byte_count
        except OpenCntxError as exc:
            errors.append(str(exc))
            if path in expected_paths:
                changed.append(path)

    if len(current_paths) > config.max_files:
        errors.append(f"File budget is now exceeded: {len(current_paths)} > {config.max_files}")
    if total_bytes > config.max_bytes:
        errors.append(f"Byte budget is now exceeded: {total_bytes} > {config.max_bytes}")

    errors.extend(_manifest_security_errors(manifest, current_sources))

    for path in sorted(expected_paths & current_paths):
        current_source = current_sources.get(path)
        if current_source is None:
            continue
        record = expected[path]
        if (
            current_source.byte_count != record["bytes"]
            or current_source.sha256 != record["sha256"]
        ):
            changed.append(path)
        else:
            unchanged.append(path)

    return VerifyReport(
        unchanged=tuple(sorted(set(unchanged))),
        changed=tuple(sorted(set(changed))),
        missing=tuple(missing),
        unexpected=tuple(unexpected),
        errors=tuple(sorted(set(errors))),
    )


def format_verify_report(report: VerifyReport) -> str:
    """Render every required drift category, including empty ones."""
    lines: list[str] = []
    for label, paths in (
        ("unchanged", report.unchanged),
        ("changed", report.changed),
        ("missing", report.missing),
        ("unexpected", report.unexpected),
    ):
        lines.append(f"{label} ({len(paths)}):")
        lines.extend(f"  {path}" for path in paths)
    lines.append(f"errors ({len(report.errors)}):")
    lines.extend(f"  {error}" for error in report.errors)
    lines.append("result: OK" if report.ok else "result: DRIFT OR INCOMPLETE")
    return "\n".join(lines)
