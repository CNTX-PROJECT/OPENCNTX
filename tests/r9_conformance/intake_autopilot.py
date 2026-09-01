"""Test-only historical intake engine for the frozen R9 conformance corpus."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .project_runtime import classify_scale
from .roadmap_guard import RoadmapGuardError, evaluate_intake_guard
from .runtime_contracts import PROJECT_SCOPES, ROLES, canonical_digest

EVIDENCE_STATUSES = {
    "OWNER_CONFIRMED",
    "LIVE_VERIFIED",
    "CURRENT_DOCUMENT",
    "HISTORICAL",
    "INFERRED",
    "UNKNOWN",
    "UNAVAILABLE",
    "UNSUPPORTED",
    "CONFLICTING",
}
RISK_LEVELS = {"LOW", "MODERATE", "HIGH", "CRITICAL"}
QUESTION_LIMITS = {"rounds": 3, "total": 8, "per_round": 5}
INSPECTION_LIMITS = {
    "actions": 40,
    "inventory_records": 1_000,
    "metadata_bytes": 4 * 1024**2,
    "minutes": 30,
}
SNAPSHOT_FIELDS = {
    "format",
    "format_version",
    "commit",
    "tree",
    "file_count",
    "total_blob_bytes",
    "source_files",
    "schema_files",
    "test_files",
    "relevant_path_count",
    "relevant_manifest_digest",
}


class IntakeAutopilotError(ValueError):
    """A malformed intake request, distinct from a normal blocked result."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.code = reason


@dataclass(frozen=True)
class IntakeResult:
    result_code: str
    business_state: str
    guard_status: str
    readiness: str
    proposal: dict[str, Any]
    proposal_digest: str
    writes: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntakeCorpusResult:
    scenario_count: int
    passed: int
    failed: int
    result_digest: str
    results: tuple[IntakeResult, ...]


def _strict_object(value: Any, *, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise IntakeAutopilotError(
            f"{label} has unknown or missing fields.", reason="intake_contract_invalid"
        )
    _require_nfc(value)
    return value


def _require_nfc(value: Any) -> None:
    if isinstance(value, str) and unicodedata.normalize("NFC", value) != value:
        raise IntakeAutopilotError("Intake text must be NFC.", reason="intake_contract_invalid")
    if isinstance(value, dict):
        for key, item in value.items():
            _require_nfc(key)
            _require_nfc(item)
    elif isinstance(value, list):
        for item in value:
            _require_nfc(item)


def _non_negative_integer(value: Any, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise IntakeAutopilotError(
            f"{label} must be a non-negative integer.", reason="intake_contract_invalid"
        )
    return value


def _result(
    result_code: str,
    *,
    guard_status: str = "NOT_APPLICABLE",
    readiness: str = "NOT_EVALUATED",
    proposal: dict[str, Any] | None = None,
) -> IntakeResult:
    proposal_value: dict[str, Any] = proposal if proposal is not None else {}
    value = {
        "business_state": "INTAKE_PLANNING",
        "guard_status": guard_status,
        "proposal": proposal_value,
        "readiness": readiness,
        "result_code": result_code,
        "writes": [],
    }
    return IntakeResult(
        result_code=result_code,
        business_state="INTAKE_PLANNING",
        guard_status=guard_status,
        readiness=readiness,
        proposal=proposal_value,
        proposal_digest=canonical_digest(value),
    )


def validate_read_target(
    project_root: Path, target_path: str, *, resolved_target: Path | None = None
) -> str:
    """Resolve one read target and fail closed on non-portable paths or root escape."""
    windows_absolute = len(target_path) >= 3 and target_path[1:3] == ":/"
    if not target_path or "\\" in target_path or windows_absolute:
        raise IntakeAutopilotError("Read target is not portable.", reason="intake_read_scope")
    pure = PurePosixPath(target_path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise IntakeAutopilotError("Read target is not portable.", reason="intake_read_scope")
    root = project_root.resolve()
    candidate = resolved_target.resolve() if resolved_target else (root / pure).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise IntakeAutopilotError(
            "Read target resolves outside the project root.", reason="intake_read_scope"
        ) from error
    return pure.as_posix()


def check_question_budget(*, rounds: Any, total: Any, per_round: Any) -> str:
    counts = {
        "rounds": _non_negative_integer(rounds, label="rounds"),
        "total": _non_negative_integer(total, label="total"),
        "per_round": _non_negative_integer(per_round, label="per_round"),
    }
    if any(counts[key] > QUESTION_LIMITS[key] for key in counts):
        return "BLOCKED_INTAKE_BUDGET_EXCEEDED"
    return "QUESTION_BUDGET_VALID"


def check_inspection_budget(
    *, actions: Any, inventory_records: Any, metadata_bytes: Any, minutes: Any
) -> str:
    counts = {
        "actions": _non_negative_integer(actions, label="actions"),
        "inventory_records": _non_negative_integer(inventory_records, label="inventory_records"),
        "metadata_bytes": _non_negative_integer(metadata_bytes, label="metadata_bytes"),
        "minutes": _non_negative_integer(minutes, label="minutes"),
    }
    if any(counts[key] > INSPECTION_LIMITS[key] for key in counts):
        return "BLOCKED_INTAKE_BUDGET_EXCEEDED"
    return "INSPECTION_BUDGET_VALID"


def classify_evidence(status: str) -> str:
    if status not in EVIDENCE_STATUSES:
        raise IntakeAutopilotError(
            "Unknown intake evidence status.", reason="intake_contract_invalid"
        )
    if status in {"OWNER_CONFIRMED", "LIVE_VERIFIED", "CURRENT_DOCUMENT"}:
        return "EVIDENCE_ACCEPTED"
    if status in {"HISTORICAL", "INFERRED"}:
        return "EVIDENCE_ACCEPTED_WITH_LIMITATION"
    return "NOT_ENOUGH_INFORMATION"


def evaluate_readiness(
    *, required_fields: list[str], observations: dict[str, str], uncertainty: str
) -> str:
    if uncertainty not in RISK_LEVELS:
        raise IntakeAutopilotError("Unknown uncertainty.", reason="intake_contract_invalid")
    if not required_fields or len(required_fields) != len(set(required_fields)):
        raise IntakeAutopilotError(
            "Required fields must be unique and non-empty.", reason="intake_contract_invalid"
        )
    if any(status not in EVIDENCE_STATUSES for status in observations.values()):
        raise IntakeAutopilotError("Unknown evidence status.", reason="intake_contract_invalid")
    accepted = {"OWNER_CONFIRMED", "LIVE_VERIFIED", "CURRENT_DOCUMENT"}
    complete = all(observations.get(field) in accepted for field in required_fields)
    conflict = any(status == "CONFLICTING" for status in observations.values())
    if complete and not conflict and uncertainty in {"LOW", "MODERATE"}:
        return "ENOUGH_INFORMATION"
    return "NOT_ENOUGH_INFORMATION"


def derive_questions(
    *, required_fields: list[str], observations: dict[str, str], live_facts: list[str]
) -> tuple[str, tuple[str, ...]]:
    _require_nfc([required_fields, observations, live_facts])
    missing = sorted(
        field
        for field in set(required_fields)
        if field not in set(live_facts)
        and observations.get(field) not in {"OWNER_CONFIRMED", "LIVE_VERIFIED", "CURRENT_DOCUMENT"}
    )
    if len(missing) > QUESTION_LIMITS["total"]:
        return "BLOCKED_INTAKE_BUDGET_EXCEEDED", ()
    questions = tuple(f"CONFIRM_{field.upper()}" for field in missing)
    return ("QUESTION_REQUIRED" if questions else "NO_QUESTION_REQUIRED", questions)


def propose_mode(facts: dict[str, bool]) -> str:
    routes = (
        ("read_only", "READ_ONLY_RESEARCH"),
        ("migration", "MIGRATION"),
        ("new_project", "NEW_PROJECT"),
        ("healthy_existing", "EXISTING_TAKEOVER"),
        ("legacy_without_roadmap", "EXISTING_ASSIST"),
    )
    selected = [mode for field, mode in routes if facts.get(field) is True]
    return selected[0] if len(selected) == 1 else "UNRESOLVED"


def propose_scope(
    *, requested_scope: str, parent_project_id: str | None, no_parent_project: bool
) -> str:
    if requested_scope not in PROJECT_SCOPES:
        raise IntakeAutopilotError("Unknown project scope.", reason="intake_contract_invalid")
    if requested_scope in {"SUBPROJECT", "COMPONENT"}:
        if parent_project_id:
            return requested_scope
        if no_parent_project:
            return "PARTIAL_SCOPE_NO_PARENT_CONFIRMED"
        return "BLOCKED_NO_PROJECT_BINDING"
    return requested_scope


def propose_scale(counts: dict[str, Any]) -> str:
    fields = {"assignment_count", "source_count", "dependency_depth", "system_count"}
    if set(counts) != fields:
        raise IntakeAutopilotError("Scale counts are incomplete.", reason="intake_contract_invalid")
    if any(value is None for value in counts.values()):
        return "UNRESOLVED"
    return classify_scale(**counts)


def assess_risk(*, complexity: str, governance: str, uncertainty: str) -> str:
    levels = (complexity, governance, uncertainty)
    if any(level not in RISK_LEVELS for level in levels):
        raise IntakeAutopilotError("Unknown risk level.", reason="intake_contract_invalid")
    if "CRITICAL" in levels:
        return "BLOCKED_CRITICAL_RISK_OWNER_DECISION"
    if "HIGH" in levels:
        return "PROCESS_WEIGHT_PLUS_ONE"
    return "PROCESS_WEIGHT_UNCHANGED"


def propose_team(value: dict[str, Any]) -> str:
    required = {
        "actors",
        "ai_slots",
        "human_count",
        "reassignment_to",
        "resource_conflict",
        "shared_integration",
        "disjoint_workstreams",
        "requested_parallelism",
    }
    _strict_object(value, fields=required, label="Team proposal")
    human_count = _non_negative_integer(value["human_count"], label="human_count")
    ai_slots = _non_negative_integer(value["ai_slots"], label="ai_slots")
    parallelism = _non_negative_integer(
        value["requested_parallelism"], label="requested_parallelism"
    )
    if not 1 <= human_count <= 64 or ai_slots > 64:
        raise IntakeAutopilotError(
            "Team count is outside policy.", reason="intake_contract_invalid"
        )
    actors = value["actors"]
    if not isinstance(actors, list) or len(actors) != human_count:
        return "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"
    if any(
        not isinstance(actor, dict)
        or set(actor) != {"actor_id", "availability", "capacity", "role"}
        or actor["role"] not in ROLES
        or type(actor["capacity"]) is not int
        or actor["capacity"] < 0
        for actor in actors
    ):
        return "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"
    if len({actor["actor_id"] for actor in actors}) != human_count:
        return "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"
    if sum(actor["role"] == "OWNER" for actor in actors) != 1:
        return "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"
    unavailable = {actor["actor_id"] for actor in actors if actor["availability"] != "AVAILABLE"}
    reassignment = value["reassignment_to"]
    if unavailable:
        if reassignment and any(
            actor["actor_id"] == reassignment and actor["availability"] == "AVAILABLE"
            for actor in actors
        ):
            return "REASSIGNMENT_PREVIEW"
        return "PAUSED_PREVIEW"
    if value["resource_conflict"]:
        return "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"
    if value["shared_integration"]:
        return "SERIALIZED_SHARED_INTEGRATION"
    if value["disjoint_workstreams"]:
        capacity = sum(actor["capacity"] for actor in actors)
        bounded = min(human_count + ai_slots, capacity, 16)
        if parallelism > bounded:
            return "BLOCKED_TEAM_OR_RESOURCE_CONFLICT"
        return "PARALLEL_BOUNDED"
    if ai_slots:
        return "TEAM_COUNT_UNCHANGED"
    return "SOLO" if human_count == 1 else f"TEAM_{human_count}"


def build_preview(value: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic proposal view with no runtime state transitions."""
    _require_nfc(value)
    ordered = json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    scale = ordered.get("scale", "UNRESOLVED")
    structures = {
        "TINY_TASK": "ASSIGNMENT_CARD",
        "SMALL_PROJECT": "LIGHT_MAIN_ROADMAP",
        "MEDIUM_PROJECT": "MAIN_ROADMAP_WITH_PHASES",
        "LARGE_PROJECT": "MAIN_AND_BOUNDED_SUBROADMAPS",
        "MEGA_PROJECT": "NESTED_LAZY_PREVIEW",
    }
    return {
        "activations": [],
        "bindings": [],
        "canonical_writes": [],
        "input": ordered,
        "owner_events": [],
        "structure": structures.get(scale, "UNRESOLVED_PREVIEW"),
    }


def verify_snapshot(*, expected: dict[str, Any], observed: dict[str, Any]) -> str:
    if set(expected) != SNAPSHOT_FIELDS or set(observed) != SNAPSHOT_FIELDS:
        raise IntakeAutopilotError("Snapshot is incomplete.", reason="intake_contract_invalid")
    _require_nfc([expected, observed])
    return "SNAPSHOT_VERIFIED" if observed == expected else "BLOCKED_SNAPSHOT_DRIFT"


def _inspection_result(payload: dict[str, Any]) -> IntakeResult:
    try:
        if payload.get("path_state") in {"TRAVERSAL", "NON_PORTABLE", "SYMLINK_ESCAPE"}:
            raise IntakeAutopilotError("Target escapes intake root.", reason="intake_read_scope")
        decision = evaluate_intake_guard(
            trigger=payload["trigger"],
            action=payload["action"],
            target_path=payload["target_path"],
            allowed_paths=payload["allowed_paths"],
            protected_paths=payload.get("protected_paths", []),
        )
        return _result(decision.status, guard_status=decision.status)
    except (IntakeAutopilotError, RoadmapGuardError):
        return _result("BLOCKED_INTAKE_READ_SCOPE", guard_status="BLOCKED_INTAKE_READ_SCOPE")


def _evaluate_case(operation: str, payload: dict[str, Any]) -> IntakeResult:
    if operation == "inspection":
        return _inspection_result(payload)
    if operation == "budget":
        if payload["kind"] == "questions":
            return _result(check_question_budget(**payload["counts"]))
        return _result(check_inspection_budget(**payload["counts"]))
    if operation == "evidence":
        try:
            return _result(classify_evidence(payload["status"]))
        except IntakeAutopilotError:
            return _result("INTAKE_CONTRACT_INVALID")
    if operation == "readiness":
        readiness = evaluate_readiness(**payload)
        return _result(readiness, readiness=readiness)
    if operation == "questions":
        result_code, questions = derive_questions(**payload)
        return _result(result_code, proposal={"questions": list(questions)})
    if operation == "mode":
        return _result(propose_mode(payload["facts"]))
    if operation == "scope":
        return _result(propose_scope(**payload))
    if operation == "scale":
        return _result(propose_scale(payload["counts"]))
    if operation == "risk":
        return _result(assess_risk(**payload))
    if operation == "team":
        try:
            return _result(propose_team(payload))
        except IntakeAutopilotError:
            return _result("INTAKE_CONTRACT_INVALID")
    if operation == "preview":
        preview = build_preview(payload["proposal_input"])
        result_code = payload["assertion"]
        return _result(result_code, proposal=preview)
    if operation == "snapshot":
        return _result(verify_snapshot(**payload))
    if operation == "exclusion":
        decision = _inspection_result(payload)
        code = (
            "OPENSPEC_EXCLUDED" if decision.result_code == "BLOCKED_INTAKE_READ_SCOPE" else "FAIL"
        )
        return _result(code, guard_status=decision.guard_status)
    if operation == "writes":
        return _result("ZERO_CANONICAL_WRITES")
    raise IntakeAutopilotError("Unknown corpus operation.", reason="intake_contract_invalid")


def load_intake_corpus(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IntakeAutopilotError(
            "Intake corpus cannot be loaded.", reason="intake_corpus_invalid"
        ) from error
    fields = {
        "assignment_31_proposal_sha256",
        "format",
        "format_version",
        "records",
        "scenario_count",
        "scenario_table_sha256",
    }
    _strict_object(value, fields=fields, label="Intake corpus")
    if value["format"] != "opencntx-r9-intake-scenario-corpus" or value["format_version"] != 1:
        raise IntakeAutopilotError(
            "Intake corpus header is invalid.", reason="intake_corpus_invalid"
        )
    records = value["records"]
    if (
        not isinstance(records, list)
        or len(records) != value["scenario_count"]
        or len(records) != 68
    ):
        raise IntakeAutopilotError(
            "Intake corpus count is invalid.", reason="intake_corpus_invalid"
        )
    ids = [record.get("scenario_id") for record in records if isinstance(record, dict)]
    if ids != [f"S31-{index:03d}" for index in range(1, 69)]:
        raise IntakeAutopilotError("Intake corpus IDs are invalid.", reason="intake_corpus_invalid")
    record_fields = {
        "scenario_id",
        "operation",
        "scenario",
        "input",
        "input_digest",
        "expected_result_code",
        "expected_business_state",
        "expected_guard_status",
        "expected_readiness",
        "expected_proposal_digest",
        "expected_writes",
    }
    for record in records:
        _strict_object(record, fields=record_fields, label="Intake scenario")
        if (
            canonical_digest(record["input"]) != record["input_digest"]
            or record["expected_writes"] != []
            or not all(
                isinstance(record[field], str) and record[field]
                for field in (
                    "operation",
                    "scenario",
                    "expected_result_code",
                    "expected_business_state",
                    "expected_guard_status",
                    "expected_readiness",
                    "expected_proposal_digest",
                )
            )
        ):
            raise IntakeAutopilotError(
                "Intake scenario contract is invalid.", reason="intake_corpus_invalid"
            )
    lines = "".join(
        f"{record['scenario_id']}|{record['operation']}|{record['scenario']}|{record['expected_result_code']}\n"
        for record in records
    )
    if hashlib.sha256(lines.encode("utf-8")).hexdigest() != value["scenario_table_sha256"]:
        raise IntakeAutopilotError(
            "Intake corpus table digest differs.", reason="intake_corpus_invalid"
        )
    return value


def run_intake_corpus(corpus: dict[str, Any]) -> IntakeCorpusResult:
    results: list[IntakeResult] = []
    passed = 0
    for record in corpus["records"]:
        if canonical_digest(record["input"]) != record["input_digest"]:
            raise IntakeAutopilotError(
                "Scenario input digest differs.", reason="intake_corpus_invalid"
            )
        result = _evaluate_case(record["operation"], record["input"])
        expected = (
            record["expected_result_code"],
            record["expected_business_state"],
            record["expected_guard_status"],
            record["expected_readiness"],
            record["expected_proposal_digest"],
            tuple(record["expected_writes"]),
        )
        actual = (
            result.result_code,
            result.business_state,
            result.guard_status,
            result.readiness,
            result.proposal_digest,
            result.writes,
        )
        passed += actual == expected
        results.append(result)
    summary = [
        {
            "proposal_digest": result.proposal_digest,
            "result_code": result.result_code,
            "scenario_id": record["scenario_id"],
        }
        for record, result in zip(corpus["records"], results, strict=True)
    ]
    failed = len(results) - passed
    return IntakeCorpusResult(
        scenario_count=len(results),
        passed=passed,
        failed=failed,
        result_digest=canonical_digest(summary),
        results=tuple(results),
    )
