"""Source-derived outcome reports and explicit cross-outcome synthesis.

This closed read-only query supports exact equality over bounded JSON records.
Semantic query/claim selection belongs to the trusted supervisor, not the client.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .continuity import (
    _digest,
    _fail,
    _resolve_input,
    _safe_relative,
    _value_digest,
    decide_finalization,
    validate_current_goal_binding,
)
from .goal_binding import BoundGoal, _canonical, _path, _sha, _text, _unique
from .goal_progress import load_goal_progress

MAX_SOURCE_BYTES = 1_048_576
MAX_RECORDS = 10_000


@dataclass(frozen=True)
class SourceQuery:
    outcome_id: str
    source_path: str
    source_sha256: str
    required_fields: tuple[str, ...]
    match_field: str
    match_value: str
    claim_key: str | None = None
    match_conclusion: str | None = None
    zero_conclusion: str | None = None

    def payload(self) -> dict[str, Any]:
        result = asdict(self)
        _text(self.outcome_id, "outcome_id")
        _path(self.source_path)
        _sha(self.source_sha256, "source_sha256")
        fields = _unique(self.required_fields, "required_fields")
        if not fields or _text(self.match_field, "match_field") not in fields:
            raise _fail("outcome_query_invalid", "Match field must be a required source field.")
        _text(self.match_value, "match_value")
        for value in (self.claim_key, self.match_conclusion, self.zero_conclusion):
            if value is not None:
                _text(value, "semantic_claim")
        if (self.claim_key is None) != (
            self.match_conclusion is None and self.zero_conclusion is None
        ):
            raise _fail(
                "outcome_query_invalid", "Claim key and conclusion must be specified together."
            )
        result["required_fields"] = fields
        return result


@dataclass(frozen=True)
class OutcomeReport:
    canonical_json: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def _records(content: bytes) -> list[dict[str, Any]]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    try:
        records = json.loads(content, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise _fail("outcome_source_invalid", "Source is not unambiguous JSON.") from exc
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise _fail("outcome_source_invalid", "Source must be a bounded record collection.")
    identities = []
    for record in records:
        if not isinstance(record, dict):
            raise _fail("outcome_source_invalid", "Each record must be an object.")
        identities.append(_text(record.get("id"), "record_id", 80))
    if len(set(identities)) != len(identities):
        raise _fail("outcome_source_invalid", "Record identity repeats.")
    return records


def run_source_query(
    root: Path,
    *,
    message: Mapping[str, object],
    expected: BoundGoal,
    query: SourceQuery,
    inspect_limit: int | None = None,
) -> OutcomeReport:
    """Actual read route: no caller completeness/count flags and no writes."""
    bound = validate_current_goal_binding(root, message, expected=expected)
    query.payload()
    action = bound["action"]
    if (
        action["operation"] != "READ_EXACT"
        or action["outcome_id"] != query.outcome_id
        or action["targets"] != [query.source_path]
        or action["preconditions"][0]["sha256"] != query.source_sha256
        or bound["intent_v1"]["authority_state"] != "APPROVED"
        or bound["request"]["source"]["role"] != "OWNER"
        or decide_finalization(bound["execution_capsule_v1"])["decision"] != "CONTINUE"
    ):
        raise _fail("outcome_query_unbound", "Query does not match this approved read action.")
    if inspect_limit is not None and (
        type(inspect_limit) is not int or not 0 <= inspect_limit <= MAX_RECORDS
    ):
        raise _fail("outcome_query_invalid", "Inspection limit is invalid.")
    path = _resolve_input(root, _safe_relative(query.source_path, "source"))
    with path.open("rb") as stream:
        content = stream.read(MAX_SOURCE_BYTES + 1)
    return _derive_report(bound["request"], query, content, inspect_limit)


def _derive_report(
    request: dict[str, Any], query: SourceQuery, content: bytes, inspect_limit: int | None
) -> OutcomeReport:
    specification = query.payload()
    if len(content) > MAX_SOURCE_BYTES or _digest(content) != query.source_sha256:
        raise _fail("outcome_source_stale", "Source bytes changed or exceed the fixed boundary.")
    records = _records(content)
    inspected = records if inspect_limit is None else records[:inspect_limit]
    missing = {
        record["id"]: [
            field
            for field in query.required_fields
            if not isinstance(record.get(field), str) or not record[field].strip()
        ]
        for record in inspected
    }
    missing = {key: fields for key, fields in missing.items() if fields}
    findings = [
        record["id"]
        for record in inspected
        if record["id"] not in missing and record[query.match_field] == query.match_value
    ]
    status = "BLOCKED" if missing else "PARTIAL" if len(inspected) != len(records) else "DELIVERED"
    conclusion = query.match_conclusion if findings else query.zero_conclusion
    claims = (
        []
        if status != "DELIVERED" or conclusion is None
        else [{"key": query.claim_key, "value": conclusion}]
    )
    result = {
        "format": "opencntx-outcome-report",
        "format_version": 2,
        "request": request,
        "outcome_id": query.outcome_id,
        "query": specification,
        "source_bytes": len(content),
        "denominator": len(records),
        "inspected_ids": [record["id"] for record in inspected],
        "missing_fields": missing,
        "finding_ids": findings,
        "status": status,
        "safety": "SAFE_READ_ONLY",
        "usability": "USABLE" if status == "DELIVERED" else "INSUFFICIENT",
        "acceptance": "UNKNOWN",
        "claims": claims,
    }
    return OutcomeReport(_canonical(result | {"report_digest": _value_digest(result)}))


def verify_outcome_source(root: Path, report: OutcomeReport, goal: BoundGoal) -> None:
    """Recompute source facts: a self-rehashed report is not source proof."""
    value = validate_outcome_report(report, goal)
    query_value = value["query"] | {"required_fields": tuple(value["query"]["required_fields"])}
    try:
        query = SourceQuery(**query_value)
    except TypeError as exc:
        raise _fail("outcome_report_invalid", "Report query fields differ.") from exc
    path = _resolve_input(root, _safe_relative(query.source_path, "source"))
    with path.open("rb") as stream:
        content = stream.read(MAX_SOURCE_BYTES + 1)
    recomputed = _derive_report(value["request"], query, content, len(value["inspected_ids"]))
    if recomputed.payload() != value:
        raise _fail("outcome_report_invalid", "Reported findings differ from the actual source.")


def validate_outcome_report(report: OutcomeReport, goal: BoundGoal) -> dict[str, Any]:
    value = report.payload()
    if (
        value.get("format") != "opencntx-outcome-report"
        or type(value.get("format_version")) is not int
        or value.get("format_version") != 2
        or value.get("report_digest")
        != _value_digest({k: v for k, v in value.items() if k != "report_digest"})
        or value.get("request") != goal.payload()["request"]
        or value.get("outcome_id") not in goal.payload()["request"]["outcome_ids"]
    ):
        raise _fail("outcome_report_stale", "Report does not bind the current original request.")
    inspected = value["inspected_ids"]
    denominator = value["denominator"]
    if (
        type(denominator) is not int
        or not 0 <= denominator <= MAX_RECORDS
        or len(set(inspected)) != len(inspected)
        or len(inspected) > denominator
        or not set(value["finding_ids"]).issubset(inspected)
        or not set(value["missing_fields"]).issubset(inspected)
    ):
        raise _fail("outcome_report_invalid", "Coverage facts are inconsistent.")
    status = (
        "BLOCKED"
        if value["missing_fields"]
        else "PARTIAL"
        if len(inspected) != denominator
        else "DELIVERED"
    )
    if (
        value["status"] != status
        or value["usability"] != ("USABLE" if status == "DELIVERED" else "INSUFFICIENT")
        or value["acceptance"] != "UNKNOWN"
    ):
        raise _fail("outcome_report_invalid", "Report claim contradicts its coverage facts.")
    return value


def integrate_outcomes(
    goal: BoundGoal,
    reports: Sequence[OutcomeReport],
    *,
    synthesis_proof: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """No missing outcome, duplicate credit or contradictory child can close parent."""
    if not isinstance(reports, (list, tuple)) or len(reports) > 50:
        raise _fail("outcome_report_invalid", "Reports must be bounded.")
    values = [validate_outcome_report(report, goal) for report in reports]
    by_outcome = {value["outcome_id"]: value for value in values}
    if len(by_outcome) != len(values):
        raise _fail("outcome_report_duplicate", "One outcome has duplicated evidence credit.")
    matrix = {
        outcome: by_outcome[outcome]["status"] if outcome in by_outcome else "NOT_ASSESSED"
        for outcome in goal.payload()["request"]["outcome_ids"]
    }
    claims: dict[str, set[str]] = {}
    for report in values:
        for claim in report["claims"]:
            claims.setdefault(claim["key"], set()).add(claim["value"])
    conflicts = sorted(key for key, choices in claims.items() if len(choices) > 1)
    report_digests = sorted(report["report_digest"] for report in values)
    proof = None
    if synthesis_proof is not None:
        if set(synthesis_proof) != {
            "reports_digest",
            "reference",
            "sha256",
            "conclusion",
        } or synthesis_proof["reports_digest"] != _value_digest(report_digests):
            raise _fail("outcome_synthesis_stale", "Synthesis does not bind these exact reports.")
        proof = dict(synthesis_proof)
        _path(proof["reference"])
        _sha(proof["sha256"], "synthesis_proof")
        _text(proof["conclusion"], "conclusion")
    complete = (
        all(status == "DELIVERED" for status in matrix.values())
        and not conflicts
        and proof is not None
    )
    value = {
        "format": "opencntx-outcome-matrix",
        "format_version": 2,
        "request": goal.payload()["request"],
        "outcomes": matrix,
        "report_digests": report_digests,
        "conflicting_claim_keys": conflicts,
        "synthesis_proof": proof,
        "status": "TECHNICALLY_COMPLETE" if complete else "PARTIAL",
        "acceptance": "UNKNOWN",
        "authority_granted": False,
    }
    return value | {"matrix_digest": _value_digest(value)}


def compile_current_outcomes(
    root: Path, goal: BoundGoal, *, synthesis_reference: str | None = None
) -> dict[str, Any]:
    """Live native evidence route; arbitrary client reports/proofs are not inputs."""
    validate_current_goal_binding(root, goal.payload(), expected=goal)
    progress = load_goal_progress(root, goal).payload()
    reports: dict[str, OutcomeReport] = {}
    refs: dict[str, str] = {}
    for node in progress["nodes"]:
        sources = {(ref["reference"], ref["sha256"]) for ref in node["source_snapshot"]}
        for ref in node["evidence"]:
            refs[ref["reference"]] = ref["sha256"]
            path = _resolve_input(root, _safe_relative(ref["reference"], "evidence"))
            content = path.read_bytes()
            if _digest(content) != ref["sha256"]:
                raise _fail("outcome_report_stale", "Evidence changed after native binding.")
            if path.suffix != ".json":
                continue
            try:
                value = json.loads(content)
            except (ValueError, UnicodeError) as exc:
                raise _fail("outcome_report_invalid", "Bound JSON evidence is invalid.") from exc
            if not isinstance(value, dict) or value.get("format") != "opencntx-outcome-report":
                continue
            query = value["query"]
            if (
                value["outcome_id"] not in node["outcome_ids"]
                or (query["source_path"], query["source_sha256"]) not in sources
            ):
                raise _fail(
                    "outcome_report_unbound", "Report belongs to another node/source snapshot."
                )
            report = OutcomeReport(_canonical(value))
            validate_outcome_report(report, goal)
            verify_outcome_source(root, report, goal)
            reports[ref["reference"]] = report
    proof = None
    if synthesis_reference is not None:
        if synthesis_reference not in refs:
            raise _fail(
                "outcome_synthesis_unbound", "Synthesis is not part of native-bound evidence."
            )
        content = _resolve_input(
            root, _safe_relative(synthesis_reference, "synthesis")
        ).read_bytes()
        raw = json.loads(content)
        if (
            not isinstance(raw, dict)
            or set(raw) != {"reports_digest", "conclusion"}
            or _digest(content) != refs[synthesis_reference]
        ):
            raise _fail("outcome_synthesis_invalid", "Synthesis proof fields or bytes differ.")
        proof = raw | {"reference": synthesis_reference, "sha256": refs[synthesis_reference]}
    return integrate_outcomes(goal, list(reports.values()), synthesis_proof=proof)
