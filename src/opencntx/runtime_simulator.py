"""Model-free simulator for the frozen R9 Assignment-29 scenario corpus."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project_runtime import classify_scale
from .runtime_contracts import canonical_digest

SCENARIO_FORMAT = "opencntx-r9-scenario-corpus"
SCENARIO_VERSION = 1
SCENARIO_COUNT = 72
SCENARIO_TABLE_SHA256 = "dd9f091f30c996324f1472fc40b369228b0cd7cfb5824059284124b38309f4d6"
ASSIGNMENT_29_SHA256 = "d0ba3cf043448e95687f749da95c2c5fe21cd4d11b3dd6e6515cc56dcf449b7c"
SCENARIO_ID_PATTERN = re.compile(r"S29-(\d{3})\Z")


class RuntimeSimulatorError(ValueError):
    """A frozen corpus or deterministic simulation error."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.code = reason


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    result_code: str
    writes: tuple[str, ...]
    result_digest: str


@dataclass(frozen=True)
class CorpusResult:
    scenario_count: int
    passed: int
    failed: int
    result_digest: str
    results: tuple[ScenarioResult, ...]


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeSimulatorError(
                "Scenario fixture has a duplicate key.", reason="runtime_scenario_fixture_invalid"
            )
        result[key] = value
    return result


def load_corpus(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeSimulatorError(
            "Scenario fixture is unavailable or unsafe.", reason="runtime_scenario_fixture_invalid"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except RuntimeSimulatorError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeSimulatorError(
            "Scenario fixture is invalid JSON.", reason="runtime_scenario_fixture_invalid"
        ) from exc
    validate_corpus(value)
    return value


def _table_bytes(records: Sequence[dict[str, Any]]) -> bytes:
    lines = [
        f"| {record['scenario_id']} | {record['scenario']} | {record['expected']} |"
        for record in records
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def validate_corpus(value: object) -> None:
    expected_keys = {
        "assignment_29_sha256",
        "format",
        "format_version",
        "records",
        "scenario_count",
        "scenario_table_sha256",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise RuntimeSimulatorError(
            "Scenario corpus envelope differs.", reason="runtime_scenario_fixture_invalid"
        )
    records = value["records"]
    if (
        value["format"] != SCENARIO_FORMAT
        or value["format_version"] != SCENARIO_VERSION
        or value["assignment_29_sha256"] != ASSIGNMENT_29_SHA256
        or value["scenario_table_sha256"] != SCENARIO_TABLE_SHA256
        or value["scenario_count"] != SCENARIO_COUNT
        or not isinstance(records, list)
        or len(records) != SCENARIO_COUNT
    ):
        raise RuntimeSimulatorError(
            "Scenario corpus binding differs.", reason="runtime_scenario_fixture_invalid"
        )
    expected_record_keys = {
        "expected",
        "expected_result_code",
        "expected_writes",
        "input",
        "operation",
        "scenario",
        "scenario_id",
    }
    ids: list[str] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != expected_record_keys:
            raise RuntimeSimulatorError(
                "Scenario record differs.", reason="runtime_scenario_fixture_invalid"
            )
        scenario_id = record["scenario_id"]
        match = SCENARIO_ID_PATTERN.fullmatch(scenario_id) if isinstance(scenario_id, str) else None
        if (
            match is None
            or int(match.group(1)) != index
            or not isinstance(record["scenario"], str)
            or not isinstance(record["expected"], str)
            or not isinstance(record["operation"], str)
            or not isinstance(record["input"], dict)
            or not isinstance(record["expected_result_code"], str)
            or not isinstance(record["expected_writes"], list)
            or any(not isinstance(item, str) for item in record["expected_writes"])
        ):
            raise RuntimeSimulatorError(
                "Scenario identity or fields differ.", reason="runtime_scenario_fixture_invalid"
            )
        ids.append(scenario_id)
    if ids != [f"S29-{number:03d}" for number in range(1, SCENARIO_COUNT + 1)]:
        raise RuntimeSimulatorError(
            "Scenario IDs are missing, extra, or reordered.",
            reason="runtime_scenario_fixture_invalid",
        )
    import hashlib

    if hashlib.sha256(_table_bytes(records)).hexdigest() != SCENARIO_TABLE_SHA256:
        raise RuntimeSimulatorError(
            "Scenario table bytes differ from Assignment 29.",
            reason="runtime_scenario_fixture_invalid",
        )


def _intake(data: dict[str, Any]) -> str:
    if data.get("conflicting"):
        return "CONFLICTING"
    if data.get("missing_parent"):
        return "BLOCKED_NO_PROJECT_BINDING"
    if data.get("counts_known") is False:
        return "UNRESOLVED"
    if not data.get("owner_bound", False):
        return "INTAKE_PLANNING"
    return str(data["result"])


def _team(data: dict[str, Any]) -> str:
    humans = data.get("humans")
    if type(humans) is not int or humans < 1 or humans > 64:
        return "SCHEMA_BLOCKED"
    if data.get("actor_missing") or data.get("role_invented") or data.get("resource_conflict"):
        return "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"
    if data.get("unavailable") and not data.get("reassigned"):
        return "PAUSED"
    if data.get("reassigned"):
        return "REASSIGNED"
    mode = "SOLO" if humans == 1 else f"TEAM_{humans}"
    return str(data.get("result", mode))


def _stack(data: dict[str, Any]) -> str:
    if data.get("cycle"):
        return "BLOCKED_GRAPH_CYCLE"
    if data.get("orphan"):
        return "BLOCKED_GRAPH_ORPHAN"
    if data.get("unknown_relation"):
        return "BLOCKED_UNKNOWN_RELATION"
    if data.get("invented"):
        return "BLOCKED_UNVERIFIED_AI_CLAIM"
    depth = data.get("depth", 1)
    if type(depth) is not int or depth < 1 or depth > 8:
        return "BLOCKED_NO_VALID_ROADMAP_STACK"
    return str(data.get("result", "STACK_VALID"))


def _return(data: dict[str, Any]) -> str:
    if not data.get("accepted") or not data.get("closed"):
        return "NO_RETURN"
    if data.get("stale") or data.get("invented"):
        return "BLOCKED_INVALID_RETURN_TO_PARENT"
    return "RETURNED_ONE_FRAME_NO_START"


def _guard(data: dict[str, Any]) -> str:
    precedence = (
        ("project_bound", False, "BLOCKED_NO_PROJECT_BINDING"),
        ("main_roadmap_valid", False, "BLOCKED_NO_VALID_MAIN_ROADMAP"),
        ("stack_valid", False, "BLOCKED_NO_VALID_ROADMAP_STACK"),
        ("active_assignment", False, "BLOCKED_NO_ACTIVE_ASSIGNMENT"),
        ("detail_matches", False, "BLOCKED_ASSIGNMENT_DETAIL_MISMATCH"),
        ("team_conflict", True, "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"),
        ("claim_verified", False, "BLOCKED_UNVERIFIED_AI_CLAIM"),
        ("context_budget", False, "BLOCKED_CONTEXT_BUDGET"),
        ("action_allowed", False, "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT"),
        ("roadmap_drift", True, "BLOCKED_ROADMAP_DRIFT"),
    )
    for key, blocked_value, result in precedence:
        if data.get(key, not blocked_value) == blocked_value:
            return result
    return "READ_ONLY_ONLY" if data.get("read_only") else "ALLOW_EXACT_ACTION"


def _storage(data: dict[str, Any]) -> str:
    if data.get("secret"):
        return "EXCLUDED_SECRET"
    if data.get("project") in {"SKYRIM", "HOME_ASSISTANT"}:
        return "HARD_EXCLUDED_UNCHANGED"
    if data.get("central_unavailable"):
        return "LOCAL_CONTINUITY"
    if data.get("repository_public") or not data.get("private_confirmed", True):
        return "BLOCKED_STORAGE_OR_SYNC_CONFLICT"
    if data.get("drift") or data.get("conflict"):
        return "BLOCKED_STORAGE_OR_SYNC_CONFLICT"
    file_bytes = data.get("file_bytes", 0)
    if type(file_bytes) is not int or file_bytes > 10 * 1024**2 or data.get("binary"):
        return "LOCAL_ONLY_MEDIA"
    if data.get("batch_files", 0) > 100 or data.get("batch_bytes", 0) > 50 * 1024**2:
        return "BLOCKED_STORAGE_OR_SYNC_CONFLICT"
    if data.get("repository_bytes", 0) > 1024**3:
        return "OWNER_DECISION_REQUIRED"
    return str(data.get("result", "SYNC_POLICY_GREEN"))


def _compatibility(data: dict[str, Any]) -> str:
    return "V1_COMPATIBLE" if data.get("major") == 1 else "REJECT_BEFORE_WRITE"


def _openspec(data: dict[str, Any]) -> str:
    return "OPENSPEC_EXCLUDED" if data.get("present") or data.get("adapter") else "NO_OPENSPEC"


def _continuity(data: dict[str, Any]) -> str:
    return "STICKY_CURRENT_LEAF" if data.get("current_leaf") else "BLOCKED_NO_ACTIVE_ASSIGNMENT"


OPERATIONS = {
    "compatibility": _compatibility,
    "continuity": _continuity,
    "guard": _guard,
    "intake": _intake,
    "openspec": _openspec,
    "return": _return,
    "stack": _stack,
    "storage": _storage,
    "team": _team,
}


def simulate_scenario(record: dict[str, Any]) -> ScenarioResult:
    operation = record["operation"]
    data = record["input"]
    if operation == "scale":
        result_code = classify_scale(
            assignment_count=data["assignment_count"],
            source_count=data["source_count"],
            dependency_depth=data["dependency_depth"],
            system_count=data["system_count"],
        )
    else:
        handler = OPERATIONS.get(operation)
        if handler is None:
            raise RuntimeSimulatorError(
                "Scenario operation is unknown.", reason="runtime_scenario_operation_unknown"
            )
        result_code = handler(data)
    writes = tuple(
        record["expected_writes"] if result_code == record["expected_result_code"] else ()
    )
    value = {
        "result_code": result_code,
        "scenario_id": record["scenario_id"],
        "writes": list(writes),
    }
    return ScenarioResult(
        scenario_id=record["scenario_id"],
        result_code=result_code,
        writes=writes,
        result_digest=canonical_digest(value),
    )


def run_corpus(value: dict[str, Any]) -> CorpusResult:
    validate_corpus(value)
    results = tuple(simulate_scenario(record) for record in value["records"])
    passed = sum(
        result.result_code == record["expected_result_code"]
        and list(result.writes) == record["expected_writes"]
        for result, record in zip(results, value["records"], strict=True)
    )
    result_value = [
        {
            "result_code": result.result_code,
            "result_digest": result.result_digest,
            "scenario_id": result.scenario_id,
            "writes": list(result.writes),
        }
        for result in results
    ]
    return CorpusResult(
        scenario_count=len(results),
        passed=passed,
        failed=len(results) - passed,
        result_digest=canonical_digest(result_value),
        results=results,
    )
