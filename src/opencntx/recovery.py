"""Evidence-bound four-stage recovery without provider-specific reasoning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .continuity import _fail, _value_digest

RECOVERY_STAGES = (
    "STANDARD_ATTEMPT_1",
    "STANDARD_RETRY_2",
    "GLOBAL_RECOVERY_1",
    "GLOBAL_RECOVERY_2",
)
DEPENDENCY_CLASSES = frozenset({"CHAIN", "STANDALONE"})
FAILURE_LAYERS = frozenset(
    {
        "PRODUCT",
        "TEST",
        "PLATFORM",
        "DATA",
        "DEPENDENCY",
        "AUTHORITY",
        "EXTERNAL_SERVICE",
        "CONTROL_PLANE",
    }
)


def _text(value: object, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str):
        raise _fail("recovery_record_invalid", f"{field} must be text.")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise _fail("recovery_record_invalid", f"{field} is empty or too long.")
    return normalized


def _digest(value: object, field: str) -> str:
    selected = _text(value, field, 64)
    if len(selected) != 64 or any(character not in "0123456789abcdef" for character in selected):
        raise _fail("recovery_record_invalid", f"{field} must be a lowercase SHA-256 digest.")
    return selected


def _identifiers(values: Sequence[str], field: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not values or len(values) > 100:
        raise _fail("recovery_record_invalid", f"{field} must be a bounded non-empty list.")
    result = [_text(value, field, 80) for value in values]
    if len(result) != len(set(result)):
        raise _fail("recovery_record_invalid", f"{field} contains duplicates.")
    return result


def validate_recovery_history(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate a restart-safe attempt timeline and its hash chain."""
    if isinstance(records, (str, bytes)) or len(records) > len(RECOVERY_STAGES):
        raise _fail("recovery_history_invalid", "Recovery history exceeds four attempts.")
    validated: list[dict[str, Any]] = []
    previous_digest: str | None = None
    assignment_id: str | None = None
    dependency_class: str | None = None
    for index, supplied in enumerate(records):
        record = dict(supplied)
        digest = record.pop("record_digest", None)
        if set(record) != {
            "format",
            "format_version",
            "assignment_id",
            "dependency_class",
            "stage",
            "attempt_number",
            "failure_layer",
            "reason",
            "evidence_digest",
            "scope_fingerprint",
            "approach_fingerprint",
            "chain_coverage",
            "prior_failure_digests",
            "global_analysis_digest",
            "previous_record_digest",
            "authority_changed",
        }:
            raise _fail("recovery_history_invalid", "Recovery record fields differ from v2.")
        if (
            record["format"] != "opencntx-recovery-attempt"
            or record["format_version"] != 2
            or record["stage"] != RECOVERY_STAGES[index]
            or record["attempt_number"] != index + 1
            or record["previous_record_digest"] != previous_digest
            or record["authority_changed"] is not False
            or digest != _value_digest(record)
        ):
            raise _fail("recovery_history_invalid", "Recovery record chain or stage is invalid.")
        current_assignment = _text(record["assignment_id"], "assignment_id", 80)
        current_class = _text(record["dependency_class"], "dependency_class", 20)
        if current_class not in DEPENDENCY_CLASSES:
            raise _fail(
                "recovery_dependency_invalid", "Dependency class must be fixed before attempts."
            )
        if assignment_id not in {None, current_assignment} or dependency_class not in {
            None,
            current_class,
        }:
            raise _fail(
                "recovery_dependency_changed", "Assignment dependency class changed after failure."
            )
        assignment_id, dependency_class = current_assignment, current_class
        _digest(record["evidence_digest"], "evidence_digest")
        _digest(record["scope_fingerprint"], "scope_fingerprint")
        _digest(record["approach_fingerprint"], "approach_fingerprint")
        layer = _text(record["failure_layer"], "failure_layer", 32)
        if layer not in FAILURE_LAYERS:
            raise _fail("recovery_layer_invalid", "Failure layer is not classified.")
        _text(record["reason"], "reason")
        coverage = _identifiers(record["chain_coverage"], "chain_coverage")
        if current_assignment not in coverage:
            raise _fail("recovery_coverage_invalid", "Chain coverage omits the failed assignment.")
        prior = list(record["prior_failure_digests"])
        if prior != [item["record_digest"] for item in validated]:
            raise _fail(
                "recovery_history_invalid", "Prior failure evidence is incomplete or reordered."
            )
        if index < 2 and record["global_analysis_digest"] is not None:
            raise _fail(
                "recovery_analysis_invalid", "Standard attempts cannot claim global analysis."
            )
        if index >= 2:
            _digest(record["global_analysis_digest"], "global_analysis_digest")
            prior_global = validated[2:] if len(validated) > 2 else []
            if any(
                item["approach_fingerprint"] == record["approach_fingerprint"]
                for item in prior_global
            ):
                raise _fail("recovery_approach_repeated", "A global recovery must change approach.")
        if index == 3:
            previous = validated[-1]
            if record["evidence_digest"] == previous["evidence_digest"] or (
                not set(previous["chain_coverage"]) < set(coverage)
                and record["scope_fingerprint"] == previous["scope_fingerprint"]
            ):
                raise _fail(
                    "recovery_scope_not_widened",
                    "The second global recovery needs new evidence and wider coverage or scope.",
                )
        validated_record = record | {"record_digest": str(digest)}
        validated.append(validated_record)
        previous_digest = str(digest)
    return validated


def record_failed_attempt(
    records: Sequence[Mapping[str, Any]],
    *,
    assignment_id: str,
    dependency_class: str,
    failure_layer: str,
    reason: str,
    evidence_digest: str,
    scope_fingerprint: str,
    approach_fingerprint: str,
    chain_coverage: Sequence[str],
    global_analysis_digest: str | None = None,
) -> dict[str, Any]:
    """Append one failure at the only legal next stage."""
    history = validate_recovery_history(records)
    if len(history) >= len(RECOVERY_STAGES):
        raise _fail("recovery_exhausted", "All four recovery attempts are already recorded.")
    identifier = _text(assignment_id, "assignment_id", 80)
    selected_class = _text(dependency_class, "dependency_class", 20)
    selected_layer = _text(failure_layer, "failure_layer", 32)
    if selected_class not in DEPENDENCY_CLASSES or selected_layer not in FAILURE_LAYERS:
        raise _fail("recovery_record_invalid", "Dependency class or failure layer is invalid.")
    coverage = _identifiers(chain_coverage, "chain_coverage")
    if identifier not in coverage:
        raise _fail("recovery_coverage_invalid", "Chain coverage omits the failed assignment.")
    index = len(history)
    if history and (
        history[0]["assignment_id"] != identifier
        or history[0]["dependency_class"] != selected_class
    ):
        raise _fail("recovery_dependency_changed", "Assignment or dependency class changed.")
    record = {
        "format": "opencntx-recovery-attempt",
        "format_version": 2,
        "assignment_id": identifier,
        "dependency_class": selected_class,
        "stage": RECOVERY_STAGES[index],
        "attempt_number": index + 1,
        "failure_layer": selected_layer,
        "reason": _text(reason, "reason"),
        "evidence_digest": _digest(evidence_digest, "evidence_digest"),
        "scope_fingerprint": _digest(scope_fingerprint, "scope_fingerprint"),
        "approach_fingerprint": _digest(approach_fingerprint, "approach_fingerprint"),
        "chain_coverage": coverage,
        "prior_failure_digests": [item["record_digest"] for item in history],
        "global_analysis_digest": (
            None
            if global_analysis_digest is None
            else _digest(global_analysis_digest, "global_analysis_digest")
        ),
        "previous_record_digest": None if not history else history[-1]["record_digest"],
        "authority_changed": False,
    }
    candidate = record | {"record_digest": _value_digest(record)}
    return validate_recovery_history([*history, candidate])[-1]


def recovery_decision(
    records: Sequence[Mapping[str, Any]],
    *,
    next_assignment_independent: bool | None = None,
) -> dict[str, Any]:
    """Return the next attempt or the exact terminal exhaustion route."""
    history = validate_recovery_history(records)
    if not history:
        return {"status": "CONTINUE", "next_stage": RECOVERY_STAGES[0], "attempts": 0}
    if len(history) < len(RECOVERY_STAGES):
        return {
            "status": "CONTINUE",
            "next_stage": RECOVERY_STAGES[len(history)],
            "attempts": len(history),
        }
    dependency_class = history[0]["dependency_class"]
    if dependency_class == "CHAIN":
        return {"status": "BLOCKED_CHAIN", "next_stage": None, "attempts": len(history)}
    if next_assignment_independent is not True:
        raise _fail(
            "recovery_independence_unproven",
            "A standalone skip requires a proven independent next assignment.",
        )
    return {
        "status": "SKIPPED_STANDALONE",
        "next_stage": None,
        "attempts": len(history),
        "roadmap_complete_allowed": False,
    }


def recovery_report(
    records: Sequence[Mapping[str, Any]],
    *,
    rollback: str,
    minimum_continuation: str,
) -> dict[str, Any]:
    """Build the detailed terminal report retained by output and handoff layers."""
    history = validate_recovery_history(records)
    decision = recovery_decision(
        history,
        next_assignment_independent=(history[0]["dependency_class"] == "STANDALONE")
        if history
        else None,
    )
    report = {
        "format": "opencntx-recovery-report",
        "format_version": 2,
        "status": decision["status"],
        "assignment_id": None if not history else history[0]["assignment_id"],
        "dependency_class": None if not history else history[0]["dependency_class"],
        "attempt_timeline": history,
        "failure_layers": sorted({item["failure_layer"] for item in history}),
        "alternative_approaches": [item["approach_fingerprint"] for item in history[2:]],
        "rollback": _text(rollback, "rollback"),
        "minimum_continuation": _text(minimum_continuation, "minimum_continuation"),
        "authority_changed": False,
        "open_required_outcomes": decision["status"] in {"BLOCKED_CHAIN", "SKIPPED_STANDALONE"},
    }
    return report | {"report_digest": _value_digest(report)}


def build_global_analysis(
    *,
    round_number: int,
    assignment_id: str,
    chain_coverage: Sequence[str],
    failure_layers: Sequence[str],
    prior_failure_digests: Sequence[str],
    evidence_digest: str,
    conflicts: Sequence[Mapping[str, Any]],
    rules: Sequence[Mapping[str, Any]],
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind a whole-chain recovery analysis without calling an AI provider."""
    if round_number not in {1, 2}:
        raise _fail("recovery_analysis_invalid", "Global analysis round must be one or two.")
    identifier = _text(assignment_id, "assignment_id", 80)
    coverage = _identifiers(chain_coverage, "chain_coverage")
    if identifier not in coverage:
        raise _fail("recovery_coverage_invalid", "Global analysis omits the failed assignment.")
    layers = sorted({_text(item, "failure_layer", 32) for item in failure_layers})
    if not layers or any(item not in FAILURE_LAYERS for item in layers):
        raise _fail("recovery_layer_invalid", "Global analysis has unclassified failure layers.")
    prior = [_digest(item, "prior_failure_digest") for item in prior_failure_digests]
    if not prior:
        raise _fail("recovery_analysis_invalid", "Global analysis must retain prior failures.")
    normalized_conflicts = []
    for item in conflicts:
        if set(item) != {"id", "status", "source_digest"}:
            raise _fail("recovery_analysis_invalid", "Conflict fields differ from the contract.")
        normalized_conflicts.append(
            {
                "id": _text(item["id"], "conflict.id", 80),
                "status": _text(item["status"], "conflict.status", 32),
                "source_digest": _digest(item["source_digest"], "conflict.source_digest"),
            }
        )
    normalized_rules = []
    for item in rules:
        if set(item) != {"id", "status", "approved", "source_digest"}:
            raise _fail("recovery_analysis_invalid", "Rule fields differ from the contract.")
        status = _text(item["status"], "rule.status", 32)
        approved = item["approved"]
        if status not in {"CURRENT", "SUPERSEDED"} or not isinstance(approved, bool):
            raise _fail("recovery_analysis_invalid", "Rule status or approval is invalid.")
        normalized_rules.append(
            {
                "id": _text(item["id"], "rule.id", 80),
                "status": status,
                "approved": approved,
                "source_digest": _digest(item["source_digest"], "rule.source_digest"),
            }
        )
    effective = sorted(
        str(item["id"])
        for item in normalized_rules
        if item["status"] == "CURRENT" and item["approved"]
    )
    if not effective:
        raise _fail("recovery_analysis_invalid", "No current approved rule is available.")
    prior_analysis_digest = None
    if round_number == 2:
        if previous is None:
            raise _fail("recovery_analysis_invalid", "Round two requires the first analysis.")
        previous_basis = {key: value for key, value in previous.items() if key != "analysis_digest"}
        if previous.get("analysis_digest") != _value_digest(previous_basis):
            raise _fail("recovery_analysis_invalid", "The first global analysis is invalid.")
        # New evidence can invalidate the prior diagnosis even when the first
        # analysis already covered the complete dependency chain. Requiring a
        # fictitious extra target in that case made a legitimate second global
        # approach impossible. The immutable prior digest still proves lineage.
        scope_widened = set(previous.get("chain_coverage", [])) <= set(coverage)
        if (
            previous.get("round_number") != 1
            or not scope_widened
            or previous.get("evidence_digest") == evidence_digest
        ):
            raise _fail(
                "recovery_scope_not_widened",
                "Round two needs new evidence without narrowing chain coverage.",
            )
        prior_analysis_digest = previous["analysis_digest"]
    elif previous is not None:
        raise _fail("recovery_analysis_invalid", "Round one cannot inherit a later analysis.")
    basis = {
        "format": "opencntx-global-recovery-analysis",
        "format_version": 1,
        "round_number": round_number,
        "assignment_id": identifier,
        "chain_coverage": coverage,
        "failure_layers": layers,
        "prior_failure_digests": prior,
        "evidence_digest": _digest(evidence_digest, "evidence_digest"),
        "connected_conflicts": sorted(normalized_conflicts, key=lambda item: str(item["id"])),
        "rules": sorted(normalized_rules, key=lambda item: str(item["id"])),
        "effective_rule_ids": effective,
        "superseded_rule_ids": sorted(
            str(item["id"]) for item in normalized_rules if item["status"] == "SUPERSEDED"
        ),
        "previous_analysis_digest": prior_analysis_digest,
        "provider_call_required": False,
        "authority_changed": False,
    }
    return basis | {"analysis_digest": _value_digest(basis)}
