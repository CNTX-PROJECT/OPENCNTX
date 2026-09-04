"""Local-first roadmap continuity, compact context, and portable capsules."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

from .security import CONFIDENCE_HIGH, CONFIDENCE_WARNING, scan_text
from .workspace import WorkspaceError

FORMAT = "opencntx-continuity-roadmap"
FORMAT_VERSION = 1
STORE_FORMAT = "opencntx-continuity-store"
CAPSULE_FORMAT = "opencntx-continuity-capsule"
AUTHORITY = "AUTO PILOT"
ZERO_DIGEST = "0" * 64
EXECUTION_CAPSULE_FORMAT = "opencntx-execution-state-capsule"
FINALIZATION_DECISIONS = frozenset(
    {
        "CONTINUE",
        "REQUEST_OWNER",
        "BLOCKED",
        "COMPLETE_ASSIGNMENT",
        "COMPLETE_ROADMAP",
        "RECONCILE_REQUIRED",
    }
)
CONFLICT_CLASSES = frozenset({"NO_CONFLICT", "EXTEND", "SUPERSEDE", "MIGRATE", "REMOVE"})
ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{0,79}\Z")
SAFE_REMOTE = re.compile(r"^(?:https://|ssh://|git@|file://|[A-Za-z]:[\\/]|/)")
SECRET_TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".md"})
VALIDATION_PARALLEL_THRESHOLD = 16
_VALIDATION_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="opencntx-validation",
)
_LEDGER_SNAPSHOTS: dict[Path, tuple[str, str]] = {}
_EVENT_CACHE: dict[Path, tuple[bytes, list[dict[str, Any]]]] = {}
_JSON_CACHE: dict[Path, tuple[str, dict[str, Any]]] = {}
_ROADMAP_CACHE: dict[Path, tuple[str, dict[str, Any]]] = {}
_STORE_ACCESS_LOCK = threading.RLock()
_Key = TypeVar("_Key")
_Input = TypeVar("_Input")
_Output = TypeVar("_Output")
_Value = TypeVar("_Value")

ROADMAP_FIELDS = {"format", "format_version", "project_id", "roadmap_id", "title", "assignments"}
ASSIGNMENT_FIELDS = {
    "id",
    "title",
    "detail",
    "depends_on",
    "touches",
    "conflict",
    "migration",
    "definition_of_done",
}
HANDOFF_INPUT_FIELDS = {
    "changed_paths",
    "decisions",
    "evidence_explanation",
    "result",
    "risks",
}
HANDOFF_FIELDS = {
    "assignment_id",
    "changed_paths",
    "decisions",
    "dependencies",
    "evidence",
    "evidence_explanation",
    "format",
    "format_version",
    "handoff_digest",
    "next_assignment",
    "outcome",
    "previous_event_head",
    "project_id",
    "receipt_digest",
    "result",
    "risks",
    "roadmap_id",
}
CLAIM_FIELDS = {
    "assignment_id",
    "authority",
    "claim_digest",
    "claimed_event_previous_head",
    "context_digest",
    "delivery_digest",
    "detail_path",
    "detail_sha256",
    "format",
    "format_version",
    "host_id",
    "project_id",
    "roadmap_id",
}
STORE_DIRECTORIES = (
    "roadmaps",
    "details",
    "information",
    "documentation",
    "context",
    "receipts",
    "history",
    "sync",
)


class ContinuityError(WorkspaceError):
    """A bounded continuity operation failed closed."""


@dataclass(frozen=True)
class FlowResult:
    status: str
    current_assignment: str | None
    completed: tuple[str, ...]
    total: int
    next_action: str
    minimum_action: str
    state_digest: str


def _fail(code: str, message: str) -> ContinuityError:
    return ContinuityError(message, code=code)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _pretty(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _value_digest(value: object) -> str:
    return _digest(_canonical(value))


def _remember(cache: dict[_Key, _Value], key: _Key, value: _Value, *, maximum: int) -> None:
    cache[key] = value
    while len(cache) > maximum:
        cache.pop(next(iter(cache)))


def _read_json(path: Path, *, failure_kind: str) -> dict[str, Any]:
    try:
        content = path.read_bytes()
        digest = _digest(content)
        cached = _JSON_CACHE.get(path)
        if cached is not None and cached[0] == digest:
            return cached[1]
        value = json.loads(content)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail(failure_kind, f"Cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise _fail(failure_kind, f"JSON root must be an object: {path}")
    _remember(_JSON_CACHE, path, (digest, value), maximum=8192)
    return value


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 19:
                    raise
                time.sleep(0.005)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise _fail("continuity_write_failed", f"Cannot write continuity state: {path}") from exc


def _one_line(value: object, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise _fail("continuity_roadmap_invalid", f"{field} must be one non-empty line.")
    text = value.strip()
    if len(text) > maximum:
        raise _fail("continuity_roadmap_invalid", f"{field} is too long.")
    return text


def _string_list(value: object, field: str, *, maximum: int = 100) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise _fail("continuity_roadmap_invalid", f"{field} must be a bounded list.")
    result = tuple(_one_line(item, field) for item in value)
    if len(set(result)) != len(result):
        raise _fail("continuity_roadmap_invalid", f"{field} contains duplicates.")
    return result


def _identifier(value: object, field: str) -> str:
    text = _one_line(value, field, 80)
    if ID_PATTERN.fullmatch(text) is None:
        raise _fail("continuity_roadmap_invalid", f"{field} is not a portable identifier.")
    return text


def _safe_relative(value: object, field: str) -> str:
    text = _one_line(value, field, 240).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise _fail("continuity_path_unsafe", f"{field} is not a safe relative path.")
    if path.parts[0] in {".git", ".opencntx"}:
        raise _fail("continuity_path_unsafe", f"{field} targets protected local state.")
    return path.as_posix()


def _validate_graph(assignments: Sequence[dict[str, Any]]) -> None:
    identifiers = {item["id"] for item in assignments}
    graph = {item["id"]: tuple(item["depends_on"]) for item in assignments}
    if any(dependency not in identifiers for values in graph.values() for dependency in values):
        raise _fail("continuity_roadmap_invalid", "An assignment has an unknown dependency.")
    remaining_dependencies = {
        identifier: len(dependencies) for identifier, dependencies in graph.items()
    }
    dependents: dict[str, list[str]] = {identifier: [] for identifier in identifiers}
    for identifier, dependencies in graph.items():
        for dependency in dependencies:
            dependents[dependency].append(identifier)

    ready = [
        identifier
        for identifier in sorted(identifiers, reverse=True)
        if remaining_dependencies[identifier] == 0
    ]
    visited = 0
    while ready:
        identifier = ready.pop()
        visited += 1
        for dependent in dependents[identifier]:
            remaining_dependencies[dependent] -= 1
            if remaining_dependencies[dependent] == 0:
                ready.append(dependent)

    if visited != len(identifiers):
        raise _fail("continuity_roadmap_invalid", "The assignment graph contains a cycle.")


def validate_roadmap(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one portable continuity roadmap."""
    if set(value) != ROADMAP_FIELDS:
        raise _fail("continuity_roadmap_invalid", "Roadmap fields are incomplete or unknown.")
    if value["format"] != FORMAT or value["format_version"] != FORMAT_VERSION:
        raise _fail("continuity_roadmap_invalid", "Roadmap format is unsupported.")
    assignments_value = value["assignments"]
    if not isinstance(assignments_value, list) or not 1 <= len(assignments_value) <= 1000:
        raise _fail("continuity_roadmap_invalid", "Roadmap must contain 1 to 1000 assignments.")
    assignments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in assignments_value:
        if not isinstance(raw, dict) or set(raw) != ASSIGNMENT_FIELDS:
            raise _fail(
                "continuity_roadmap_invalid", "Assignment fields are incomplete or unknown."
            )
        identifier = _identifier(raw["id"], "assignment.id")
        if identifier in seen:
            raise _fail("continuity_roadmap_invalid", "Assignment IDs must be unique.")
        seen.add(identifier)
        conflict = _one_line(raw["conflict"], "assignment.conflict")
        if conflict not in CONFLICT_CLASSES:
            raise _fail("continuity_roadmap_invalid", "Assignment conflict class is unknown.")
        migration = str(raw["migration"]).strip() if isinstance(raw["migration"], str) else ""
        if conflict in {"SUPERSEDE", "MIGRATE", "REMOVE"} and not migration:
            raise _fail("continuity_roadmap_invalid", "Changed contracts require a migration note.")
        assignments.append(
            {
                "id": identifier,
                "title": _one_line(raw["title"], "assignment.title"),
                "detail": _one_line(raw["detail"], "assignment.detail", 2000),
                "depends_on": list(_string_list(raw["depends_on"], "assignment.depends_on")),
                "touches": [
                    _safe_relative(item, "assignment.touches")
                    for item in _string_list(raw["touches"], "assignment.touches")
                ],
                "conflict": conflict,
                "migration": migration,
                "definition_of_done": list(
                    _string_list(raw["definition_of_done"], "assignment.definition_of_done")
                ),
            }
        )
    _validate_graph(assignments)
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": _identifier(value["project_id"], "project_id"),
        "roadmap_id": _identifier(value["roadmap_id"], "roadmap_id"),
        "title": _one_line(value["title"], "title"),
        "assignments": assignments,
    }


def load_roadmap(path: Path) -> dict[str, Any]:
    return validate_roadmap(
        _read_json(path.resolve(strict=True), failure_kind="continuity_roadmap_invalid")
    )


def _load_bound_roadmap(path: Path) -> dict[str, Any]:
    try:
        resolved = path.resolve(strict=True)
        content = resolved.read_bytes()
        digest = _digest(content)
        cached = _ROADMAP_CACHE.get(resolved)
        if cached is not None and cached[0] == digest:
            return cached[1]
        value = json.loads(content)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail("continuity_store_invalid", f"Cannot read valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise _fail("continuity_store_invalid", f"JSON root must be an object: {resolved}")
    roadmap = validate_roadmap(value)
    _remember(_ROADMAP_CACHE, resolved, (digest, roadmap), maximum=128)
    return roadmap


def _root(project_root: Path, *, create: bool = False) -> Path:
    try:
        root = project_root.resolve(strict=not create)
        if create:
            root.mkdir(parents=True, exist_ok=True)
            root = root.resolve(strict=True)
    except OSError as exc:
        raise _fail("continuity_root_invalid", "Project root is unavailable.") from exc
    if root.is_symlink() or not root.is_dir():
        raise _fail("continuity_root_invalid", "Project root must be a real directory.")
    return root


def store_path(project_root: Path) -> Path:
    return _root(project_root) / ".opencntx" / "continuity"


def _resolve_input(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _fail(
            "continuity_path_unsafe", f"Input is missing or outside the project: {relative}"
        ) from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise _fail("continuity_path_unsafe", f"Input is not a regular file: {relative}")
    return resolved


def discover_capabilities(project_root: Path) -> dict[str, Any]:
    """Return local-only capability facts without changing project state."""
    root = _root(project_root)
    git = shutil.which("git")
    is_git = (root / ".git").exists()
    remotes: list[str] = []
    if git and is_git:
        result = subprocess.run(
            [git, "-C", str(root), "remote"], check=False, capture_output=True, text=True
        )
        if result.returncode == 0:
            remotes = sorted(line for line in result.stdout.splitlines() if line)
    return {
        "format": "opencntx-continuity-capabilities",
        "format_version": 1,
        "python": platform.python_version(),
        "platform": platform.system(),
        "local_store": "AVAILABLE",
        "git": "AVAILABLE" if git else "UNAVAILABLE",
        "git_repository": is_git,
        "git_remotes": remotes,
        "github_sync": "AVAILABLE_WITH_EXPLICIT_PRIVATE_REMOTE" if git else "UNAVAILABLE",
        "network_required_for_local_flow": False,
        "runtime_dependencies": 0,
    }


def _expand_touches(root: Path, touches: Sequence[str]) -> dict[str, Any]:
    included: dict[str, dict[str, Any]] = {}
    unread: list[str] = []
    blocked: list[str] = []
    matched_patterns: set[str] = set()
    for pattern in touches:
        try:
            matches = sorted(root.glob(pattern))
        except (OSError, ValueError):
            unread.append(pattern)
            continue
        for path in matches:
            try:
                resolved = path.resolve(strict=True)
                relative = resolved.relative_to(root).as_posix()
            except (OSError, ValueError):
                blocked.append(pattern)
                continue
            if relative.startswith((".git/", ".opencntx/")) or resolved.is_symlink():
                blocked.append(relative)
                continue
            if not resolved.is_file():
                continue
            matched_patterns.add(pattern)
            if len(included) >= 200:
                blocked.append("BUDGET:more-than-200-files")
                break
            try:
                content = resolved.read_bytes()
            except OSError:
                unread.append(relative)
                continue
            included[relative] = {"bytes": len(content), "sha256": _digest(content)}
    return {
        "included": [{"path": path} | included[path] for path in sorted(included)],
        "excluded": sorted(set(touches) - matched_patterns),
        "unread": sorted(set(unread)),
        "blocked": sorted(set(blocked)),
        "file_count": len(included),
        "byte_count": sum(item["bytes"] for item in included.values()),
    }


def preview_roadmap(project_root: Path, roadmap_path: Path) -> dict[str, Any]:
    """Read and inspect only the existing paths relevant to one roadmap."""
    root = _root(project_root)
    roadmap = load_roadmap(roadmap_path)
    assignments = []
    for assignment in roadmap["assignments"]:
        check = _expand_touches(root, assignment["touches"])
        assignments.append(
            {
                "id": assignment["id"],
                "conflict": assignment["conflict"],
                "depends_on": assignment["depends_on"],
                "existing_check": check,
            }
        )
    result = {
        "format": "opencntx-continuity-preview",
        "format_version": 1,
        "roadmap_digest": _value_digest(roadmap),
        "project_id": roadmap["project_id"],
        "assignment_count": len(assignments),
        "assignments": assignments,
        "writes": [],
    }
    return result | {"preview_digest": _value_digest(result)}


def _store_files(store: Path) -> list[Path]:
    return sorted(
        path
        for path in store.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and ".tmp" not in path.name
        and path.name != ".operation.lock"
        and path.relative_to(store).as_posix() not in {"sync/config.json", "sync/last-error.json"}
    )


def _read_events(store: Path) -> list[dict[str, Any]]:
    ledger = store / "history" / "events.jsonl"
    try:
        content = ledger.read_bytes()
    except OSError as exc:
        raise _fail("continuity_store_invalid", "Continuity event ledger is unavailable.") from exc
    cached = _EVENT_CACHE.get(ledger)
    if cached is not None and content == cached[0]:
        return list(cached[1])
    if cached is not None and content.startswith(cached[0]) and cached[0].endswith(b"\n"):
        events = list(cached[1])
        previous = str(events[-1]["event_digest"])
        remainder = content[len(cached[0]) :]
    else:
        events = []
        previous = ZERO_DIGEST
        remainder = content
    try:
        lines = remainder.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise _fail("continuity_store_invalid", "Continuity event ledger is invalid.") from exc
    for number, line in enumerate(lines, start=len(events) + 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _fail("continuity_store_invalid", "Continuity event ledger is invalid.") from exc
        if not isinstance(event, dict) or event.get("sequence") != number:
            raise _fail("continuity_store_invalid", "Continuity event sequence is invalid.")
        digest = event.get("event_digest")
        payload = {key: value for key, value in event.items() if key != "event_digest"}
        if payload.get("previous_digest") != previous or digest != _value_digest(payload):
            raise _fail("continuity_store_invalid", "Continuity event chain is invalid.")
        previous = str(digest)
        events.append(event)
    if not events:
        raise _fail("continuity_store_invalid", "Continuity event ledger is empty.")
    _remember(
        _LEDGER_SNAPSHOTS,
        ledger,
        (str(events[-1]["event_digest"]), _digest(content)),
        maximum=256,
    )
    _remember(_EVENT_CACHE, ledger, (content, list(events)), maximum=256)
    return events


def _bounded_parallel_map(
    function: Callable[[_Input], _Output], values: Sequence[_Input]
) -> list[_Output]:
    if len(values) < VALIDATION_PARALLEL_THRESHOLD:
        return [function(value) for value in values]
    worker_count = min(4, len(values))
    chunk_size = (len(values) + worker_count - 1) // worker_count
    futures = [
        _VALIDATION_EXECUTOR.submit(_function_batch, function, values[offset : offset + chunk_size])
        for offset in range(0, len(values), chunk_size)
    ]
    return [item for future in futures for item in future.result()]


def _function_batch(
    function: Callable[[_Input], _Output], values: Sequence[_Input]
) -> list[_Output]:
    return [function(value) for value in values]


def _selection_artifacts(
    value: tuple[Path, dict[str, Any], str],
) -> tuple[dict[str, Any], bytes, bytes]:
    store, assignment, identifier = value
    check = _read_json(
        store / "receipts" / f"{identifier}-existing-check.json",
        failure_kind="continuity_store_invalid",
    )
    try:
        expected_detail = _detail_bytes(assignment, check["result"])
        actual_detail = (store / "details" / f"{identifier}.md").read_bytes()
    except (KeyError, OSError, TypeError) as exc:
        raise _fail(
            "continuity_store_invalid",
            "Bound assignment detail is unavailable or invalid.",
        ) from exc
    return check, expected_detail, actual_detail


def _handoff_artifacts(
    value: tuple[Path, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    store, identifier = value
    return (
        _read_json(
            store / "handoffs" / f"{identifier}.json", failure_kind="continuity_store_invalid"
        ),
        _read_json(
            store / "receipts" / f"{identifier}-complete.json",
            failure_kind="continuity_store_invalid",
        ),
    )


def _reduce(
    store: Path, roadmap: dict[str, Any], events: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    completed: list[str] = []
    current: str | None = None
    status = "READY"
    failures: list[str] = []
    for event in events:
        event_type = event["type"]
        payload = event["payload"]
        if event_type == "FLOW_STARTED":
            status = "RUNNING"
        elif event_type == "ASSIGNMENT_SELECTED":
            current = payload["assignment_id"]
            failures = []
            status = "RUNNING"
        elif event_type == "ASSIGNMENT_FAILED":
            if payload.get("assignment_id") != current:
                raise _fail(
                    "continuity_store_invalid",
                    "Continuity failure is not bound to the active assignment.",
                )
            failures.append(payload["fingerprint"])
            status = "RECOVERY_REQUIRED"
        elif event_type == "ASSIGNMENT_COMPLETED":
            if payload.get("assignment_id") != current:
                raise _fail(
                    "continuity_store_invalid",
                    "Continuity completion is not bound to the active assignment.",
                )
            completed.append(payload["assignment_id"])
            current = None
            failures = []
            status = "RUNNING"
        elif event_type == "FLOW_BLOCKED":
            status = "BLOCKED"
        elif event_type == "FLOW_COMPLETED":
            status = "COMPLETE"
            current = None
    state = {
        "format": STORE_FORMAT,
        "format_version": 1,
        "project_id": roadmap["project_id"],
        "roadmap_id": roadmap["roadmap_id"],
        "roadmap_digest": _value_digest(roadmap),
        "status": status,
        "current_assignment": current,
        "completed": completed,
        "recovery_rounds": len(failures),
        "failure_fingerprints": failures,
        "event_count": len(events),
        "event_head": events[-1]["event_digest"],
    }
    return state | {"state_digest": _value_digest(state)}


def _validate_store_bindings(
    store: Path,
    roadmap: dict[str, Any],
    events: Sequence[dict[str, Any]],
    state: Mapping[str, Any],
) -> None:
    """Bind roadmap, generated details and current context to the event ledger."""
    first = events[0]
    roadmap_digest = _value_digest(roadmap)
    if (
        first.get("type") != "FLOW_STARTED"
        or first.get("payload", {}).get("authority") != AUTHORITY
        or first.get("payload", {}).get("roadmap_digest") != roadmap_digest
        or first.get("payload", {}).get("roadmap_id") != roadmap["roadmap_id"]
    ):
        raise _fail(
            "continuity_store_invalid",
            "Stored roadmap differs from the roadmap bound when the flow started.",
        )

    assignments = {item["id"]: item for item in roadmap["assignments"]}
    selections: dict[str, Mapping[str, Any]] = {}
    selection_inputs: list[tuple[Path, dict[str, Any], str]] = []
    selection_payloads: list[Mapping[str, Any]] = []
    for event in events:
        if event["type"] != "ASSIGNMENT_SELECTED":
            continue
        payload = event["payload"]
        identifier = payload.get("assignment_id")
        assignment = assignments.get(identifier)
        if assignment is None:
            raise _fail(
                "continuity_store_invalid",
                "Selected assignment is absent from the bound roadmap.",
            )
        selection_inputs.append((store, assignment, str(identifier)))
        selection_payloads.append(payload)

    selection_files = _bounded_parallel_map(_selection_artifacts, selection_inputs)
    for selection_input, payload, artifacts in zip(
        selection_inputs, selection_payloads, selection_files, strict=True
    ):
        _, _, identifier = selection_input
        check, expected_detail, actual_detail = artifacts
        check_digest = check.get("check_digest")
        check_basis = {key: value for key, value in check.items() if key != "check_digest"}
        if (
            check_digest != _value_digest(check_basis)
            or payload.get("existing_check_digest") != check_digest
            or check_basis.get("assignment_id") != identifier
        ):
            raise _fail(
                "continuity_store_invalid",
                "Existing-check receipt differs from its selected assignment binding.",
            )
        if actual_detail != expected_detail:
            raise _fail(
                "continuity_store_invalid",
                "Assignment detail differs from its bound roadmap and existing check.",
            )
        selections[str(identifier)] = payload

    _validate_handoffs(store, roadmap, events)
    _validate_claims(store, roadmap, events)
    _validate_execution_checkpoints(store, roadmap, events)
    current = state["current_assignment"]
    current_path = store / "context" / "current.json"
    if current is None:
        if current_path.exists():
            raise _fail(
                "continuity_store_invalid",
                "Current context exists without an active assignment.",
            )
        return
    selection = selections.get(str(current))
    if selection is None:
        raise _fail(
            "continuity_store_invalid",
            "Active assignment has no bound selection event.",
        )
    context = _read_json(current_path, failure_kind="continuity_store_invalid")
    context_digest = context.get("context_digest")
    context_basis = {key: value for key, value in context.items() if key != "context_digest"}
    expected_context = {
        "format": "opencntx-current-assignment",
        "format_version": 1,
        "assignment": assignments[str(current)],
        "detail_path": f"details/{current}.md",
        "existing_check_digest": selection.get("existing_check_digest"),
    }
    if (
        context_digest != _value_digest(context_basis)
        or context_digest != selection.get("context_digest")
        or context_basis != expected_context
    ):
        raise _fail(
            "continuity_store_invalid",
            "Current context differs from its bound assignment selection.",
        )


def _validate_execution_checkpoints(
    store: Path, roadmap: dict[str, Any], events: Sequence[dict[str, Any]]
) -> None:
    """Validate progressive checkpoint bindings without making them mandatory."""
    current: str | None = None
    seen: set[str] = set()
    checkpoint_number = 0
    for index, event in enumerate(events):
        event_type = event["type"]
        payload = event["payload"]
        if event_type == "ASSIGNMENT_SELECTED":
            current = str(payload["assignment_id"])
        elif event_type == "ASSIGNMENT_COMPLETED":
            current = None
        if event_type != "EXECUTION_CHECKPOINT":
            continue

        checkpoint_number += 1
        checkpoint_id = payload.get("checkpoint_id")
        evidence = payload.get("evidence")
        if (
            not isinstance(checkpoint_id, str)
            or ID_PATTERN.fullmatch(checkpoint_id) is None
            or checkpoint_id in seen
            or payload.get("checkpoint_number") != checkpoint_number
            or payload.get("assignment_id") != current
            or not isinstance(evidence, list)
            or payload.get("evidence_digest") != _value_digest(evidence)
            or payload.get("prior_state_digest")
            != _reduce(store, roadmap, events[:index])["state_digest"]
        ):
            raise _fail(
                "continuity_store_invalid",
                "Execution checkpoint differs from its event binding.",
            )
        for field in ("current_internal_task", "next_internal_action"):
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
                raise _fail("continuity_store_invalid", "Execution checkpoint text is invalid.")
        seen.add(checkpoint_id)


def _next_trigger(events: Sequence[dict[str, Any]], start: int) -> str | None:
    for event in events[start:]:
        if event["type"] == "NEXT_ASSIGNMENT_TRIGGERED":
            return str(event["payload"]["assignment_id"])
        if event["type"] == "FLOW_COMPLETED":
            return None
    raise _fail("continuity_store_invalid", "Completed assignment has no next-flow event.")


def _bound_inventory(store: Path, directory: str, label: str) -> set[str]:
    root = store / directory
    if not root.exists():
        return set()
    if root.is_symlink() or not root.is_dir():
        raise _fail("continuity_store_invalid", f"{label} directory is unsafe.")
    files: set[str] = set()
    try:
        for path in root.rglob("*"):
            mode = path.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode):
                raise _fail("continuity_store_invalid", f"{label} inventory contains a link.")
            if stat.S_ISREG(mode):
                files.add(path.relative_to(store).as_posix())
    except OSError as exc:
        raise _fail("continuity_store_invalid", f"{label} inventory is unavailable.") from exc
    return files


def _validate_handoffs(
    store: Path, roadmap: dict[str, Any], events: Sequence[dict[str, Any]]
) -> None:
    assignments = {item["id"]: item for item in roadmap["assignments"]}
    bound_paths: set[str] = set()
    completed_events = [
        (index, event)
        for index, event in enumerate(events)
        if event["type"] == "ASSIGNMENT_COMPLETED"
        and (
            event["payload"].get("handoff_digest") is not None
            or event["payload"].get("handoff_path") is not None
        )
    ]
    handoff_inputs = [
        (store, str(event["payload"].get("assignment_id"))) for _, event in completed_events
    ]
    handoff_files = _bounded_parallel_map(_handoff_artifacts, handoff_inputs)
    for (index, event), artifacts in zip(completed_events, handoff_files, strict=True):
        payload = event["payload"]
        handoff_digest = payload.get("handoff_digest")
        handoff_path = payload.get("handoff_path")
        if handoff_digest is None and handoff_path is None:
            continue
        identifier = str(payload.get("assignment_id"))
        expected_path = f"handoffs/{identifier}.json"
        if handoff_path != expected_path or not isinstance(handoff_digest, str):
            raise _fail("continuity_store_invalid", "Handoff event binding is invalid.")
        record, receipt = artifacts
        if set(record) != HANDOFF_FIELDS:
            raise _fail("continuity_store_invalid", "Handoff record fields are invalid.")
        basis = {key: value for key, value in record.items() if key != "handoff_digest"}
        assignment = assignments.get(identifier)
        if (
            assignment is None
            or record["format"] != "opencntx-continuity-handoff"
            or record["format_version"] != 1
            or record["project_id"] != roadmap["project_id"]
            or record["roadmap_id"] != roadmap["roadmap_id"]
            or record["assignment_id"] != identifier
            or record["outcome"] != "PASS"
            or record["dependencies"] != assignment["depends_on"]
            or record["evidence"] != receipt.get("evidence")
            or record["receipt_digest"] != payload.get("receipt_digest")
            or record["previous_event_head"] != event["previous_digest"]
            or record["next_assignment"] != _next_trigger(events, index + 1)
            or record["handoff_digest"] != _value_digest(basis)
            or record["handoff_digest"] != handoff_digest
        ):
            raise _fail("continuity_store_invalid", "Handoff differs from its event binding.")
        bound_paths.add(expected_path)
    actual_paths = _bound_inventory(store, "handoffs", "Handoff")
    if actual_paths != bound_paths:
        raise _fail("continuity_store_invalid", "Handoff inventory differs from event history.")


def _reject_secret_content(*, relative: str, content: bytes, context: str) -> None:
    if PurePosixPath(relative).suffix.lower() not in SECRET_TEXT_SUFFIXES:
        return
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _fail(
            f"continuity_{context}_secret", f"{context.title()} text is not valid UTF-8."
        ) from exc
    findings = scan_text(path=relative, text=text, source_sha256=_digest(content))
    if any(item.confidence in {CONFIDENCE_HIGH, CONFIDENCE_WARNING} for item in findings):
        raise _fail(
            f"continuity_{context}_secret",
            f"{context.title()} content triggered the secret filter.",
        )


def _selection_for(events: Sequence[dict[str, Any]], identifier: str) -> Mapping[str, Any]:
    for event in events:
        if (
            event["type"] == "ASSIGNMENT_SELECTED"
            and event["payload"].get("assignment_id") == identifier
        ):
            return event["payload"]
    raise _fail("continuity_store_invalid", "Claim has no assignment selection binding.")


def _claim_for_assignment(
    store: Path, events: Sequence[dict[str, Any]], identifier: str
) -> dict[str, Any] | None:
    matches = [
        event
        for event in events
        if event["type"] == "ASSIGNMENT_CLAIMED"
        and event["payload"].get("assignment_id") == identifier
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise _fail("continuity_store_invalid", "Assignment has duplicate host claims.")
    path = store / "claims" / f"{identifier}.json"
    return _read_json(path, failure_kind="continuity_store_invalid")


def _validate_claims(
    store: Path, roadmap: dict[str, Any], events: Sequence[dict[str, Any]]
) -> None:
    assignments = {item["id"] for item in roadmap["assignments"]}
    bound_paths: set[str] = set()
    seen: set[str] = set()
    for index, event in enumerate(events):
        if event["type"] != "ASSIGNMENT_CLAIMED":
            continue
        payload = event["payload"]
        identifier = str(payload.get("assignment_id"))
        expected_path = f"claims/{identifier}.json"
        if (
            identifier in seen
            or identifier not in assignments
            or payload.get("claim_path") != expected_path
        ):
            raise _fail("continuity_store_invalid", "Host claim event binding is invalid.")
        record = _read_json(store / expected_path, failure_kind="continuity_store_invalid")
        if set(record) != CLAIM_FIELDS:
            raise _fail("continuity_store_invalid", "Host claim fields are invalid.")
        basis = {key: value for key, value in record.items() if key != "claim_digest"}
        selection = _selection_for(events, identifier)
        try:
            detail = (store / record["detail_path"]).read_bytes()
        except (OSError, TypeError) as exc:
            raise _fail("continuity_store_invalid", "Claimed detail is unavailable.") from exc
        if (
            record["format"] != "opencntx-host-claim"
            or record["format_version"] != 1
            or record["project_id"] != roadmap["project_id"]
            or record["roadmap_id"] != roadmap["roadmap_id"]
            or record["assignment_id"] != identifier
            or record["authority"] != AUTHORITY
            or record["detail_path"] != f"details/{identifier}.md"
            or record["detail_sha256"] != _digest(detail)
            or record["context_digest"] != selection.get("context_digest")
            or record["claimed_event_previous_head"] != event["previous_digest"]
            or record["claim_digest"] != _value_digest(basis)
            or payload.get("claim_digest") != record["claim_digest"]
            or payload.get("delivery_digest") != record["delivery_digest"]
            or payload.get("host_id") != record["host_id"]
        ):
            raise _fail("continuity_store_invalid", "Host claim differs from its event binding.")
        for later in events[index + 1 :]:
            if (
                later["type"] == "ASSIGNMENT_COMPLETED"
                and later["payload"].get("assignment_id") == identifier
            ):
                if (
                    later["payload"].get("claim_digest") != record["claim_digest"]
                    or later["payload"].get("host_id") != record["host_id"]
                ):
                    raise _fail(
                        "continuity_store_invalid", "Completion is not bound to its host claim."
                    )
                break
        seen.add(identifier)
        bound_paths.add(expected_path)
    actual_paths = _bound_inventory(store, "claims", "Host claim")
    if actual_paths != bound_paths:
        raise _fail("continuity_store_invalid", "Host claim inventory differs from event history.")


def _load_store(
    project_root: Path,
) -> tuple[Path, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    with _STORE_ACCESS_LOCK:
        store = store_path(project_root)
        if not store.is_dir() or store.is_symlink():
            raise _fail("continuity_store_missing", "Continuity store is not initialized.")
        roadmap = _load_bound_roadmap(store / "roadmaps" / "roadmap.json")
        events = _read_events(store)
        state = _reduce(store, roadmap, events)
        _validate_store_bindings(store, roadmap, events, state)
        return store, roadmap, events, state


@contextmanager
def _writer_lock(path: Path):
    with _STORE_ACCESS_LOCK:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError as exc:
            raise _fail(
                "continuity_write_conflict", "Another continuity writer is active."
            ) from exc
        except OSError as exc:
            raise _fail(
                "continuity_write_failed", "Cannot acquire the continuity writer lock."
            ) from exc
        try:
            yield
        finally:
            path.unlink(missing_ok=True)


def _append_events(
    store: Path,
    entries: Sequence[tuple[str, Mapping[str, Any]]],
    *,
    expected_head: str | None = None,
    existing_events: Sequence[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    ledger = store / "history" / "events.jsonl"
    if existing_events is None:
        events = _read_events(store) if ledger.exists() and ledger.stat().st_size else []
        existing_content = b"".join(_canonical(event) for event in events)
    else:
        events = list(existing_events)
        try:
            existing_content = ledger.read_bytes()
            head = str(events[-1]["event_digest"]) if events else ZERO_DIGEST
            snapshot = _LEDGER_SNAPSHOTS.get(ledger)
            if snapshot is None:
                expected_content = b"".join(_canonical(event) for event in events)
                unchanged = existing_content == expected_content
            else:
                unchanged = snapshot == (head, _digest(existing_content))
            if not unchanged:
                raise _fail("continuity_write_conflict", "Continuity state changed before commit.")
        except OSError as exc:
            raise _fail(
                "continuity_write_conflict", "Continuity state changed before commit."
            ) from exc
    head = events[-1]["event_digest"] if events else ZERO_DIGEST
    if expected_head is not None and expected_head != head:
        raise _fail("continuity_write_conflict", "Continuity state changed before commit.")
    appended: list[dict[str, Any]] = []
    for event_type, payload in entries:
        event = {
            "sequence": len(events) + len(appended) + 1,
            "previous_digest": appended[-1]["event_digest"] if appended else head,
            "type": event_type,
            "payload": dict(payload),
        }
        event["event_digest"] = _value_digest(event)
        appended.append(event)
    content = existing_content + b"".join(_canonical(event) for event in appended)
    _write_atomic(ledger, content)
    _remember(
        _LEDGER_SNAPSHOTS,
        ledger,
        (str(appended[-1]["event_digest"]), _digest(content)),
        maximum=256,
    )
    _remember(_EVENT_CACHE, ledger, (content, [*events, *appended]), maximum=256)
    return appended


def _append_event(store: Path, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return _append_events(store, ((event_type, payload),))[0]


def _assignment(roadmap: dict[str, Any], identifier: str) -> dict[str, Any]:
    for assignment in roadmap["assignments"]:
        if assignment["id"] == identifier:
            return assignment
    raise _fail("continuity_store_invalid", "Current assignment is absent from the roadmap.")


def _next_assignment(roadmap: dict[str, Any], completed: Sequence[str]) -> dict[str, Any] | None:
    done = set(completed)
    for assignment in roadmap["assignments"]:
        if assignment["id"] not in done and all(
            dependency in done for dependency in assignment["depends_on"]
        ):
            return assignment
    return None


def _detail_bytes(assignment: dict[str, Any], check: dict[str, Any]) -> bytes:
    paths = (
        "\n".join(
            f"- `{item['path']}` — {item['bytes']} bytes — `{item['sha256']}`"
            for item in check["included"]
        )
        or "- No existing touched file was found."
    )
    done = "\n".join(f"- [ ] {item}" for item in assignment["definition_of_done"])
    migration = assignment["migration"] or "Not required."
    text = f"""# {assignment["id"]} — {assignment["title"]}

## Detail

{assignment["detail"]}

## Short existing check

- Conflict class: `{assignment["conflict"]}`
- Rev4 result: the objective in this detail wins within the bound scope.
- Migration/compatibility: {migration}
- Files: {check["file_count"]}
- Bytes: {check["byte_count"]}

{paths}

## Definition of Done

{done}
"""
    return text.encode("utf-8")


def _prepare_selection(
    store: Path, root: Path, roadmap: dict[str, Any], assignment: dict[str, Any]
) -> dict[str, Any]:
    check = _expand_touches(root, assignment["touches"])
    check_value = {
        "format": "opencntx-existing-check",
        "format_version": 1,
        "assignment_id": assignment["id"],
        "conflict": assignment["conflict"],
        "migration": assignment["migration"],
        "result": check,
    }
    check_value["check_digest"] = _value_digest(check_value)
    _write_atomic(
        store / "receipts" / f"{assignment['id']}-existing-check.json", _pretty(check_value)
    )
    detail_path = store / "details" / f"{assignment['id']}.md"
    _write_atomic(detail_path, _detail_bytes(assignment, check))
    context = {
        "format": "opencntx-current-assignment",
        "format_version": 1,
        "assignment": assignment,
        "detail_path": f"details/{assignment['id']}.md",
        "existing_check_digest": check_value["check_digest"],
    }
    context["context_digest"] = _value_digest(context)
    _write_atomic(store / "context" / "current.json", _pretty(context))
    return {
        "assignment_id": assignment["id"],
        "conflict": assignment["conflict"],
        "existing_check_digest": check_value["check_digest"],
        "context_digest": context["context_digest"],
    }


def _cache_state(
    store: Path,
    roadmap: dict[str, Any],
    events: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state = _reduce(store, roadmap, _read_events(store) if events is None else events)
    _write_atomic(store / "state.json", _pretty(state))
    return state


def start_flow(project_root: Path, roadmap_path: Path, approval: str) -> FlowResult:
    """Start an entire bounded roadmap with one explicit AUTO PILOT approval."""
    if approval != AUTHORITY:
        raise _fail("continuity_authority_missing", 'Exact approval "AUTO PILOT" is required.')
    root = _root(project_root)
    roadmap = load_roadmap(roadmap_path)
    control = root / ".opencntx"
    control.mkdir(exist_ok=True)
    store = control / "continuity"
    with _writer_lock(control / "continuity.lock"):
        if store.exists():
            raise _fail(
                "continuity_store_exists", "Continuity is already initialized; nothing changed."
            )
        staging = Path(tempfile.mkdtemp(prefix="continuity-start-", dir=control))
        try:
            for directory in STORE_DIRECTORIES:
                (staging / directory).mkdir(parents=True, exist_ok=False)
            _write_atomic(staging / "roadmaps" / "roadmap.json", _pretty(roadmap))
            _write_atomic(
                staging / "information" / "capabilities.json",
                _pretty(discover_capabilities(root)),
            )
            _write_atomic(
                staging / "documentation" / "README.md",
                (
                    b"# OPENCNTX continuity store\n\n"
                    b"Local canonical roadmap, current detail, context, receipts and history.\n"
                    b"Git/GitHub synchronization is optional and never the only truth.\n"
                ),
            )
            first = _next_assignment(roadmap, ())
            if first is None:
                raise _fail(
                    "continuity_roadmap_invalid", "Roadmap has no dependency-ready assignment."
                )
            selection = _prepare_selection(staging, root, roadmap, first)
            started_events = _append_events(
                staging,
                (
                    (
                        "FLOW_STARTED",
                        {
                            "authority": AUTHORITY,
                            "roadmap_digest": _value_digest(roadmap),
                            "roadmap_id": roadmap["roadmap_id"],
                        },
                    ),
                    ("ASSIGNMENT_SELECTED", selection),
                ),
                expected_head=ZERO_DIGEST,
            )
            state = _cache_state(staging, roadmap, started_events)
            os.replace(staging, store)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    return _flow_result(roadmap, state)


def _evidence(root: Path, paths: Sequence[str]) -> list[dict[str, Any]]:
    if not paths:
        raise _fail("continuity_evidence_missing", "At least one evidence file is required.")
    result = []
    for value in paths:
        relative = _safe_relative(value, "evidence")
        path = _resolve_input(root, relative)
        content = path.read_bytes()
        result.append({"path": relative, "bytes": len(content), "sha256": _digest(content)})
    return result


def _handoff_lines(value: object, field: str, maximum: int = 20) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise _fail("continuity_handoff_invalid", f"handoff.{field} must be a bounded list.")
    lines = [_one_line(item, f"handoff.{field}", 500) for item in value]
    if len(lines) != len(set(lines)):
        raise _fail("continuity_handoff_invalid", f"handoff.{field} contains duplicates.")
    return lines


def _handoff_input(root: Path, relative_path: str | None) -> dict[str, Any]:
    if relative_path is None:
        return {
            "changed_paths": [],
            "decisions": [],
            "evidence_explanation": (
                "The assignment receipt binds every evidence path, byte count, and SHA-256 digest."
            ),
            "result": "The assignment met its declared Definition of Done with bound evidence.",
            "risks": [],
        }
    relative = _safe_relative(relative_path, "handoff")
    path = _resolve_input(root, relative)
    try:
        content = path.read_bytes()
        if len(content) > 65_536:
            raise _fail("continuity_handoff_invalid", "Handoff input exceeds 64 KiB.")
        text = content.decode("utf-8")
        value = json.loads(text)
    except ContinuityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail("continuity_handoff_invalid", "Handoff input is not valid UTF-8 JSON.") from exc
    findings = scan_text(path=relative, text=text, source_sha256=_digest(content))
    if any(item.confidence in {CONFIDENCE_HIGH, CONFIDENCE_WARNING} for item in findings):
        raise _fail("continuity_handoff_secret", "Handoff input triggered the secret filter.")
    if not isinstance(value, dict) or set(value) != HANDOFF_INPUT_FIELDS:
        raise _fail("continuity_handoff_invalid", "Handoff input fields are invalid.")
    if not isinstance(value["changed_paths"], list):
        raise _fail("continuity_handoff_invalid", "Handoff changed_paths must be a list.")
    changed = [_safe_relative(item, "handoff.changed_paths") for item in value["changed_paths"]]
    if len(changed) > 100 or len(changed) != len(set(changed)):
        raise _fail("continuity_handoff_invalid", "Handoff changed_paths are invalid.")
    return {
        "changed_paths": changed,
        "decisions": _handoff_lines(value["decisions"], "decisions"),
        "evidence_explanation": _one_line(
            value["evidence_explanation"], "handoff.evidence_explanation", 2000
        ),
        "result": _one_line(value["result"], "handoff.result", 2000),
        "risks": _handoff_lines(value["risks"], "risks"),
    }


def _write_handoff(
    store: Path,
    roadmap: dict[str, Any],
    assignment: dict[str, Any],
    evidence: list[dict[str, Any]],
    receipt_digest: str,
    next_assignment: str | None,
    previous_event_head: str,
    supplied: dict[str, Any],
) -> dict[str, str]:
    record = {
        "format": "opencntx-continuity-handoff",
        "format_version": 1,
        "project_id": roadmap["project_id"],
        "roadmap_id": roadmap["roadmap_id"],
        "assignment_id": assignment["id"],
        "outcome": "PASS",
        "decisions": supplied["decisions"],
        "result": supplied["result"],
        "changed_paths": supplied["changed_paths"],
        "evidence": evidence,
        "evidence_explanation": supplied["evidence_explanation"],
        "risks": supplied["risks"],
        "dependencies": assignment["depends_on"],
        "next_assignment": next_assignment,
        "receipt_digest": receipt_digest,
        "previous_event_head": previous_event_head,
    }
    record["handoff_digest"] = _value_digest(record)
    content = _pretty(record)
    findings = scan_text(
        path=f"handoffs/{assignment['id']}.json",
        text=content.decode("utf-8"),
        source_sha256=_digest(content),
    )
    if any(item.confidence in {CONFIDENCE_HIGH, CONFIDENCE_WARNING} for item in findings):
        raise _fail("continuity_handoff_secret", "Generated handoff triggered the secret filter.")
    relative = f"handoffs/{assignment['id']}.json"
    _write_atomic(store / relative, content)
    return {"handoff_digest": record["handoff_digest"], "handoff_path": relative}


def _advance_claim_binding(
    store: Path,
    events: Sequence[dict[str, Any]],
    identifier: str,
    host_id: str | None,
    claim_digest: str | None,
) -> dict[str, str]:
    record = _claim_for_assignment(store, events, identifier)
    if record is None:
        if host_id is not None or claim_digest is not None:
            raise _fail("continuity_claim_invalid", "No host claim exists for this assignment.")
        return {}
    if (
        not isinstance(host_id, str)
        or not isinstance(claim_digest, str)
        or host_id != record["host_id"]
        or claim_digest != record["claim_digest"]
    ):
        raise _fail("continuity_claim_required", "The active host claim must bind advance.")
    return {"host_id": host_id, "claim_digest": claim_digest}


def _advance_local(
    project_root: Path,
    *,
    outcome: str,
    evidence_paths: Sequence[str],
    reason: str = "",
    handoff_path: str | None = None,
    host_id: str | None = None,
    claim_digest: str | None = None,
) -> FlowResult:
    """Record one bounded result and trigger the next dependency-ready detail."""
    root = _root(project_root)
    store, roadmap, events, state = _load_store(root)
    if state["status"] in {"COMPLETE", "BLOCKED"} or state["current_assignment"] is None:
        raise _fail("continuity_not_active", "Continuity has no active assignment.")
    identifier = str(state["current_assignment"])
    claim_binding = _advance_claim_binding(store, events, identifier, host_id, claim_digest)
    evidence = _evidence(root, evidence_paths)
    normalized = outcome.strip().upper()
    if normalized == "FAIL":
        explanation = _one_line(reason, "reason", 500)
        fingerprint = _value_digest(
            {"assignment_id": identifier, "evidence": evidence, "reason": explanation}
        )
        repetitions = state["failure_fingerprints"].count(fingerprint)
        if repetitions >= 2:
            appended = _append_events(
                store,
                (
                    (
                        "FLOW_BLOCKED",
                        {"assignment_id": identifier, "reason": "REPEATED_FAILED_STRATEGY"},
                    ),
                ),
                expected_head=state["event_head"],
                existing_events=events,
            )
            state = _cache_state(store, roadmap, [*events, *appended])
            return _flow_result(roadmap, state)
        round_number = state["recovery_rounds"] + 1
        entries: list[tuple[str, Mapping[str, Any]]] = [
            (
                "ASSIGNMENT_FAILED",
                {
                    "assignment_id": identifier,
                    "evidence": evidence,
                    "fingerprint": fingerprint,
                    "reason": explanation,
                    "recovery_round": round_number,
                    **claim_binding,
                },
            )
        ]
        if round_number >= 3:
            entries.append(
                (
                    "FLOW_BLOCKED",
                    {"assignment_id": identifier, "reason": "THREE_FAILED_RECOVERY_ROUNDS"},
                )
            )
        appended = _append_events(
            store,
            entries,
            expected_head=state["event_head"],
            existing_events=events,
        )
        state = _cache_state(store, roadmap, [*events, *appended])
        return _flow_result(roadmap, state)
    if normalized != "PASS":
        raise _fail("continuity_outcome_invalid", "Outcome must be PASS or FAIL.")
    assignment = _assignment(roadmap, identifier)
    supplied_handoff = _handoff_input(root, handoff_path)
    receipt = {
        "format": "opencntx-assignment-receipt",
        "format_version": 1,
        "assignment_id": identifier,
        "definition_of_done": assignment["definition_of_done"],
        "evidence": evidence,
        "authority": AUTHORITY,
        "result": "TECHNICALLY_COMPLETE",
    }
    receipt["receipt_digest"] = _value_digest(receipt)
    _write_atomic(store / "receipts" / f"{identifier}-complete.json", _pretty(receipt))
    interim_completed = [*state["completed"], identifier]
    next_assignment = _next_assignment(roadmap, interim_completed)
    handoff = _write_handoff(
        store,
        roadmap,
        assignment,
        evidence,
        receipt["receipt_digest"],
        None if next_assignment is None else next_assignment["id"],
        state["event_head"],
        supplied_handoff,
    )
    entries = [
        (
            "ASSIGNMENT_COMPLETED",
            {
                "assignment_id": identifier,
                "receipt_digest": receipt["receipt_digest"],
                **handoff,
                **claim_binding,
            },
        ),
        ("ROADMAP_RETURNED", {"completed_assignment_id": identifier}),
    ]
    if next_assignment is None:
        if len(interim_completed) != len(roadmap["assignments"]):
            raise _fail(
                "continuity_dependency_blocked", "No remaining assignment is dependency-ready."
            )
        entries.append(
            (
                "FLOW_COMPLETED",
                {"assignment_count": len(interim_completed), "roadmap_id": roadmap["roadmap_id"]},
            )
        )
    else:
        selection = _prepare_selection(store, root, roadmap, next_assignment)
        entries.extend(
            (
                ("NEXT_ASSIGNMENT_TRIGGERED", {"assignment_id": next_assignment["id"]}),
                ("ASSIGNMENT_SELECTED", selection),
            )
        )
    appended = _append_events(
        store,
        entries,
        expected_head=state["event_head"],
        existing_events=events,
    )
    if next_assignment is None:
        (store / "context" / "current.json").unlink(missing_ok=True)
    state = _cache_state(store, roadmap, [*events, *appended])
    return _flow_result(roadmap, state)


def advance_flow(
    project_root: Path,
    *,
    outcome: str,
    evidence_paths: Sequence[str],
    reason: str = "",
    handoff_path: str | None = None,
    host_id: str | None = None,
    claim_digest: str | None = None,
) -> FlowResult:
    """Record one result atomically and trigger the next dependency-ready detail."""
    root = _root(project_root)
    store = store_path(root)
    with _writer_lock(store / ".operation.lock"):
        result = _advance_local(
            root,
            outcome=outcome,
            evidence_paths=evidence_paths,
            reason=reason,
            handoff_path=handoff_path,
            host_id=host_id,
            claim_digest=claim_digest,
        )
    checkpoint_kind = "BLOCKED" if result.status == "BLOCKED" else outcome.strip().upper()
    checkpoint = {
        "format": "opencntx-continuity-checkpoint",
        "format_version": 1,
        "policy": "EVERY_CHECKPOINT",
        "checkpoint": checkpoint_kind,
        "requested_outcome": outcome.strip().upper(),
        "flow_status": result.status,
        "current_assignment": result.current_assignment,
        "completed": list(result.completed),
        "state_digest": result.state_digest,
    }
    checkpoint["checkpoint_digest"] = _value_digest(checkpoint)
    try:
        from .continuity_sync import sync_configured

        sync_configured(root, checkpoint=checkpoint)
    except ContinuityError as exc:
        from .continuity_sync import record_sync_error

        record_sync_error(root, exc, checkpoint=checkpoint)
    return result


def _flow_result(roadmap: dict[str, Any], state: dict[str, Any]) -> FlowResult:
    current = state["current_assignment"]
    if state["status"] == "COMPLETE":
        next_action = "ROADMAP_COMPLETE"
        minimum = "NONE"
    elif state["status"] == "BLOCKED":
        next_action = "STOP_FAIL_CLOSED"
        minimum = "Review the three distinct failure receipts and define a changed bounded route."
    elif state["status"] == "RECOVERY_REQUIRED":
        next_action = f"RECOVER {current}"
        minimum = "Change relevant input or evidence before one bounded retry."
    else:
        next_action = f"EXECUTE {current}"
        if state["completed"]:
            previous = state["completed"][-1]
            minimum = (
                f"Read .opencntx/continuity/handoffs/{previous}.json, then "
                f".opencntx/continuity/details/{current}.md"
            )
        else:
            minimum = f"Read .opencntx/continuity/details/{current}.md"
    return FlowResult(
        status=state["status"],
        current_assignment=current,
        completed=tuple(state["completed"]),
        total=len(roadmap["assignments"]),
        next_action=next_action,
        minimum_action=minimum,
        state_digest=state["state_digest"],
    )


def flow_status(project_root: Path) -> FlowResult:
    """Return the restart-safe state rebuilt from the hash-chained ledger."""
    _, roadmap, _, state = _load_store(project_root)
    return _flow_result(roadmap, state)


def _capsule_from_loaded(
    roadmap: dict[str, Any], events: Sequence[dict[str, Any]], state: dict[str, Any]
) -> dict[str, Any]:
    current = state["current_assignment"]
    latest_checkpoint = next(
        (
            event["payload"]
            for event in reversed(events)
            if event["type"] == "EXECUTION_CHECKPOINT"
            and event["payload"].get("assignment_id") == current
        ),
        None,
    )
    latest_selection = next(
        (
            event["payload"]
            for event in reversed(events)
            if event["type"] == "ASSIGNMENT_SELECTED"
            and event["payload"].get("assignment_id") == current
        ),
        None,
    )
    flow = _flow_result(roadmap, state)
    if state["status"] == "COMPLETE":
        assignment_status = "COMPLETED"
        continuation_mode = "STOP_COMPLETE"
    elif state["status"] == "BLOCKED":
        assignment_status = "BLOCKED"
        continuation_mode = "STOP_FAIL_CLOSED"
    elif state["status"] == "RECOVERY_REQUIRED":
        assignment_status = "RECOVERY_REQUIRED"
        continuation_mode = "CONTINUE_AUTOMATICALLY"
    else:
        assignment_status = "ACTIVE"
        continuation_mode = "CONTINUE_AUTOMATICALLY"

    next_assignment = None
    if current is not None:
        candidate = _next_assignment(roadmap, [*state["completed"], str(current)])
        next_assignment = None if candidate is None else candidate["id"]

    if latest_checkpoint is not None:
        internal_task = latest_checkpoint["current_internal_task"]
        internal_action = latest_checkpoint["next_internal_action"]
        evidence_digest = latest_checkpoint["evidence_digest"]
    elif current is not None:
        internal_task = "READ_BOUND_DETAIL"
        internal_action = flow.minimum_action
        evidence_digest = (
            ZERO_DIGEST
            if latest_selection is None
            else str(latest_selection["existing_check_digest"])
        )
    else:
        internal_task = None
        internal_action = None
        last_receipt = next(
            (
                event["payload"].get("receipt_digest")
                for event in reversed(events)
                if event["type"] == "ASSIGNMENT_COMPLETED"
            ),
            ZERO_DIGEST,
        )
        evidence_digest = str(last_receipt)

    capsule = {
        "format": EXECUTION_CAPSULE_FORMAT,
        "format_version": 1,
        "roadmap_revision": state["roadmap_digest"],
        "current_assignment": current,
        "current_internal_task": internal_task,
        "assignment_status": assignment_status,
        "next_internal_action": internal_action,
        "next_assignment_after_completion": next_assignment,
        "authority_state": "APPROVED_AUTO_PILOT",
        "continuation_mode": continuation_mode,
        "recovery_round": state["recovery_rounds"],
        "checkpoint_number": sum(event["type"] == "EXECUTION_CHECKPOINT" for event in events),
        "evidence_digest": evidence_digest,
        "state_digest": state["state_digest"],
    }
    return capsule | {"capsule_digest": _value_digest(capsule)}


def execution_state_capsule(project_root: Path) -> dict[str, Any]:
    """Compile a fresh execution projection from validated durable state."""
    _, roadmap, events, state = _load_store(project_root)
    return _capsule_from_loaded(roadmap, events, state)


def decide_finalization(
    capsule: Mapping[str, Any], *, projection_digest: str | None = None
) -> dict[str, Any]:
    """Return the one legal host decision for a validated execution capsule."""
    basis = {key: value for key, value in capsule.items() if key != "capsule_digest"}
    capsule_digest = capsule.get("capsule_digest")
    decision = "RECONCILE_REQUIRED"
    reason = "CAPSULE_INVALID"
    next_action = "Reread durable roadmap, events, authority and evidence."
    recovery_round = capsule.get("recovery_round")
    recovery_exhausted = (
        isinstance(recovery_round, int)
        and not isinstance(recovery_round, bool)
        and recovery_round >= 3
    )
    valid_core = (
        capsule.get("format") == EXECUTION_CAPSULE_FORMAT
        and capsule.get("format_version") == 1
        and isinstance(recovery_round, int)
        and not isinstance(recovery_round, bool)
        and 0 <= recovery_round <= 3
        and capsule.get("assignment_status")
        in {"ACTIVE", "RECOVERY_REQUIRED", "BLOCKED", "COMPLETED"}
    )
    if capsule_digest == _value_digest(basis) and valid_core:
        if projection_digest is not None and projection_digest != capsule_digest:
            reason = "PROJECTION_STALE"
        elif capsule.get("authority_state") != "APPROVED_AUTO_PILOT":
            decision = "REQUEST_OWNER"
            reason = "AUTHORITY_REQUIRED"
            next_action = "Request exactly the missing OWNER decision."
        elif capsule.get("assignment_status") == "BLOCKED" or recovery_exhausted:
            decision = "BLOCKED"
            reason = "RECOVERY_BOUND_REACHED"
            next_action = "Review the failed evidence and define one changed bounded route."
        elif capsule.get("assignment_status") == "COMPLETED":
            if capsule.get("next_assignment_after_completion") is None:
                decision = "COMPLETE_ROADMAP"
                reason = "ROADMAP_TERMINAL_PROOF"
                next_action = "NONE"
            else:
                decision = "COMPLETE_ASSIGNMENT"
                reason = "ASSIGNMENT_TERMINAL_PROOF"
                next_action = "Request authority for the next roadmap assignment."
        elif (
            capsule.get("assignment_status") in {"ACTIVE", "RECOVERY_REQUIRED"}
            and capsule.get("current_assignment")
            and capsule.get("next_internal_action")
        ):
            decision = "CONTINUE"
            reason = "APPROVED_SAFE_ACTION_OPEN"
            next_action = str(capsule["next_internal_action"])
    result = {
        "format": "opencntx-finalization-decision",
        "format_version": 1,
        "decision": decision,
        "reason": reason,
        "next_action": next_action,
        "capsule_digest": capsule_digest,
    }
    return result | {"decision_digest": _value_digest(result)}


def finalization_guard(
    project_root: Path, *, projection_digest: str | None = None
) -> dict[str, Any]:
    """Compile current state and decide whether the caller may finalize."""
    return decide_finalization(
        execution_state_capsule(project_root), projection_digest=projection_digest
    )


def record_execution_checkpoint(
    project_root: Path,
    *,
    checkpoint_id: str,
    current_internal_task: str,
    next_internal_action: str,
    evidence_paths: Sequence[str],
    expected_state_digest: str,
) -> dict[str, Any]:
    """Append one idempotent, state-bound progress checkpoint."""
    root = _root(project_root)
    normalized_id = _identifier(checkpoint_id, "checkpoint_id")
    normalized_task = _one_line(current_internal_task, "current_internal_task", 240)
    normalized_action = _one_line(next_internal_action, "next_internal_action", 500)
    store = store_path(root)
    with _writer_lock(store / ".operation.lock"):
        store, roadmap, events, state = _load_store(root)
        if state["status"] in {"COMPLETE", "BLOCKED"} or state["current_assignment"] is None:
            raise _fail("continuity_not_active", "Continuity has no active assignment.")
        evidence = _evidence(root, evidence_paths)
        evidence_digest = _value_digest(evidence)
        requested = {
            "assignment_id": state["current_assignment"],
            "checkpoint_id": normalized_id,
            "current_internal_task": normalized_task,
            "next_internal_action": normalized_action,
            "evidence": evidence,
            "evidence_digest": evidence_digest,
        }
        existing = next(
            (
                event["payload"]
                for event in events
                if event["type"] == "EXECUTION_CHECKPOINT"
                and event["payload"].get("checkpoint_id") == normalized_id
            ),
            None,
        )
        if existing is not None:
            comparable = {key: existing.get(key) for key in requested}
            if comparable != requested:
                raise _fail(
                    "continuity_checkpoint_conflict",
                    "Checkpoint ID already exists with different content.",
                )
            return _capsule_from_loaded(roadmap, events, state)
        if expected_state_digest != state["state_digest"]:
            raise _fail("continuity_write_conflict", "Continuity state changed before checkpoint.")
        payload = requested | {
            "checkpoint_number": 1
            + sum(event["type"] == "EXECUTION_CHECKPOINT" for event in events),
            "prior_state_digest": state["state_digest"],
        }
        appended = _append_events(
            store,
            (("EXECUTION_CHECKPOINT", payload),),
            expected_head=state["event_head"],
            existing_events=events,
        )
        state = _cache_state(store, roadmap, [*events, *appended])
        return _capsule_from_loaded(roadmap, [*events, *appended], state)


def health_report(project_root: Path) -> dict[str, Any]:
    """Verify local store structure, immutable roadmap, state cache, and current detail."""
    store, roadmap, events, state = _load_store(project_root)
    issues: list[str] = []
    for directory in STORE_DIRECTORIES:
        path = store / directory
        if not path.is_dir() or path.is_symlink():
            issues.append(f"DIRECTORY_INVALID:{directory}")
    cache_path = store / "state.json"
    if (
        not cache_path.is_file()
        or _read_json(cache_path, failure_kind="continuity_store_invalid") != state
    ):
        issues.append("STATE_CACHE_DRIFT")
    current = state["current_assignment"]
    if current and not (store / "details" / f"{current}.md").is_file():
        issues.append("CURRENT_DETAIL_MISSING")
    result = {
        "format": "opencntx-continuity-health",
        "format_version": 1,
        "status": "HEALTHY" if not issues else "REPAIR_REQUIRED",
        "issues": issues,
        "roadmap_digest": _value_digest(roadmap),
        "state_digest": state["state_digest"],
        "event_count": len(events),
        "current_assignment": current,
        "minimum_action": "NONE"
        if not issues
        else "Restore from a verified capsule or rebuild derived state.",
    }
    return result | {"health_digest": _value_digest(result)}


def inspect_adapter(project_root: Path, adapter: str, target: str = ".") -> dict[str, Any]:
    """Inspect one local file, Markdown tree, JSON file, or Git checkout without writes."""
    root = _root(project_root)
    kind = adapter.lower()
    if kind == "git":
        git = shutil.which("git")
        if git is None or not (root / ".git").exists():
            raise _fail("continuity_adapter_unavailable", "Git adapter is unavailable.")
        commands = {
            "head": [git, "-C", str(root), "rev-parse", "HEAD"],
            "branch": [git, "-C", str(root), "branch", "--show-current"],
            "status": [git, "-C", str(root), "status", "--porcelain"],
            "tracked": [git, "-C", str(root), "ls-files"],
        }
        values: dict[str, str] = {}
        for name, command in commands.items():
            command_result = subprocess.run(command, check=False, capture_output=True, text=True)
            if command_result.returncode != 0:
                raise _fail("continuity_adapter_failed", "Git inspection failed.")
            values[name] = command_result.stdout.strip()
        payload: dict[str, Any] = {
            "head": values["head"],
            "branch": values["branch"],
            "clean": not values["status"],
            "tracked_count": len(values["tracked"].splitlines()),
        }
    else:
        relative = "." if kind == "markdown" and target == "." else _safe_relative(target, "target")
        path = _resolve_input(root, relative) if kind in {"file", "json"} else root / relative
        if kind == "file":
            content = path.read_bytes()
            payload = {"path": relative, "bytes": len(content), "sha256": _digest(content)}
        elif kind == "json":
            value = _read_json(path, failure_kind="continuity_adapter_failed")
            payload = {"path": relative, "keys": sorted(value), "sha256": _value_digest(value)}
        elif kind == "markdown":
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, ValueError) as exc:
                raise _fail("continuity_adapter_failed", "Markdown target is unavailable.") from exc
            candidates = [resolved] if resolved.is_file() else sorted(resolved.rglob("*.md"))
            records = []
            for candidate in candidates[:200]:
                content = candidate.read_bytes()
                records.append(
                    {
                        "path": candidate.relative_to(root).as_posix(),
                        "bytes": len(content),
                        "sha256": _digest(content),
                    }
                )
            payload = {"files": records, "file_count": len(records)}
        else:
            raise _fail(
                "continuity_adapter_unknown", "Adapter must be file, git, markdown, or json."
            )
    adapter_result = {
        "format": "opencntx-read-only-adapter-result",
        "format_version": 1,
        "adapter": kind,
        "result": payload,
        "writes": [],
    }
    return adapter_result | {"result_digest": _value_digest(adapter_result)}


def export_capsule(project_root: Path, destination: Path) -> dict[str, Any]:
    """Export a deterministic, independently verifiable continuity capsule."""
    store, _, _, state = _load_store(project_root)
    target = destination.resolve()
    if target.exists():
        raise _fail("continuity_capsule_exists", "Capsule destination already exists.")
    entries: list[dict[str, Any]] = []
    for path in _store_files(store):
        relative = path.relative_to(store).as_posix()
        content = path.read_bytes()
        _reject_secret_content(relative=relative, content=content, context="capsule")
        entries.append({"path": relative, "bytes": len(content), "sha256": _digest(content)})
    manifest = {
        "format": CAPSULE_FORMAT,
        "format_version": 1,
        "project_id": state["project_id"],
        "roadmap_digest": state["roadmap_digest"],
        "state_digest": state["state_digest"],
        "files": entries,
    }
    manifest["capsule_digest"] = _value_digest(manifest)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(
            target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            payloads = [("manifest.json", _pretty(manifest))]
            payloads.extend(
                (f"continuity/{item['path']}", (store / item["path"]).read_bytes())
                for item in entries
            )
            for name, content in payloads:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, content)
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise _fail("continuity_capsule_write_failed", "Cannot create capsule.") from exc
    return {
        "status": "EXPORTED",
        "path": str(target),
        "bytes": target.stat().st_size,
        "sha256": _digest(target.read_bytes()),
        "capsule_digest": manifest["capsule_digest"],
    }


def verify_capsule(path: Path) -> dict[str, Any]:
    """Verify a capsule without trusting its filenames or extraction behavior."""
    source = path.resolve(strict=True)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise _fail(
                    "continuity_capsule_invalid", "Capsule names are incomplete or duplicate."
                )
            for name in names:
                pure = PurePosixPath(name)
                if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
                    raise _fail("continuity_capsule_invalid", "Capsule contains an unsafe path.")
            manifest_value = json.loads(archive.read("manifest.json").decode("utf-8"))
            if not isinstance(manifest_value, dict):
                raise _fail("continuity_capsule_invalid", "Capsule manifest is invalid.")
            expected_digest = manifest_value.get("capsule_digest")
            basis = {key: value for key, value in manifest_value.items() if key != "capsule_digest"}
            if (
                basis.get("format") != CAPSULE_FORMAT
                or basis.get("format_version") != 1
                or expected_digest != _value_digest(basis)
            ):
                raise _fail("continuity_capsule_invalid", "Capsule manifest digest differs.")
            files = basis.get("files")
            if not isinstance(files, list):
                raise _fail("continuity_capsule_invalid", "Capsule file inventory is invalid.")
            expected_names = {"manifest.json"}
            for item in files:
                if not isinstance(item, dict) or set(item) != {"path", "bytes", "sha256"}:
                    raise _fail("continuity_capsule_invalid", "Capsule file record is invalid.")
                name = f"continuity/{_safe_relative(item['path'], 'capsule.path')}"
                content = archive.read(name)
                if len(content) != item["bytes"] or _digest(content) != item["sha256"]:
                    raise _fail("continuity_capsule_invalid", "Capsule file digest differs.")
                _reject_secret_content(
                    relative=str(item["path"]), content=content, context="capsule"
                )
                expected_names.add(name)
            if set(names) != expected_names:
                raise _fail("continuity_capsule_invalid", "Capsule contains unexpected files.")
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        if isinstance(exc, WorkspaceError):
            raise
        raise _fail("continuity_capsule_invalid", "Capsule cannot be verified.") from exc
    return {
        "status": "VERIFIED",
        "path": str(source),
        "bytes": source.stat().st_size,
        "sha256": _digest(source.read_bytes()),
        "capsule_digest": expected_digest,
        "file_count": len(files),
    }


def import_capsule(project_root: Path, capsule: Path) -> dict[str, Any]:
    """Restore a verified capsule into a new, empty continuity store."""
    verification = verify_capsule(capsule)
    root = _root(project_root, create=True)
    store = root / ".opencntx" / "continuity"
    if store.exists():
        raise _fail("continuity_store_exists", "Continuity store already exists; nothing changed.")
    parent = store.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="continuity-import-", dir=parent))
    try:
        with zipfile.ZipFile(capsule.resolve(strict=True), "r") as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            for item in manifest["files"]:
                relative = _safe_relative(item["path"], "capsule.path")
                destination = temporary.joinpath(*PurePosixPath(relative).parts)
                _write_atomic(destination, archive.read(f"continuity/{relative}"))
        os.replace(temporary, store)
        for directory in STORE_DIRECTORIES:
            (store / directory).mkdir(exist_ok=True)
        health = health_report(root)
        if health["status"] != "HEALTHY":
            raise _fail("continuity_capsule_invalid", "Restored capsule is not healthy.")
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        if store.exists():
            shutil.rmtree(store)
        raise
    return verification | {"status": "IMPORTED", "store": str(store)}


def format_flow(result: FlowResult) -> str:
    current = result.current_assignment or "NONE"
    return "\n".join(
        (
            f"Status: {result.status}",
            f"Current assignment: {current}",
            f"Progress: {len(result.completed)}/{result.total}",
            f"Next action: {result.next_action}",
            f"Minimum action: {result.minimum_action}",
            f"State-SHA-256: {result.state_digest}",
        )
    )
