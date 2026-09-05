"""Goal-relevant continuation, durable STOP and bounded changed-fact recovery."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .continuity import (
    ContinuityError,
    _digest,
    _fail,
    _resolve_input,
    _safe_relative,
    _value_digest,
    decide_finalization,
)
from .goal_binding import BoundGoal, _sha, _text
from .goal_progress import load_goal_progress, progress_readiness


def recovery_observation(goal: BoundGoal, *, error_class: str) -> dict[str, Any]:
    """Relevant facts exclude ledger digests: recording failure is not a changed capability."""
    bound = goal.payload()
    action = bound["action"]
    identity = {
        "request_id": bound["request"]["id"],
        "revision": bound["request"]["revision"],
        "outcome_id": action["outcome_id"],
        "capability": action["capability_ref"],
        "operation": action["operation"],
        "targets": action["targets"],
    }
    return identity | {
        "action_fingerprint": _value_digest(identity),
        "fingerprint": _value_digest(identity | {"error_class": error_class}),
        "error_class": _text(error_class, "error_class"),
        "capabilities_digest": _value_digest(
            {"capability": action["capability_ref"], "platform": sys.platform}
        ),
        "relevant_evidence_digest": _value_digest(action["preconditions"]),
    }


def build_followup_evidence(
    goal: BoundGoal, *, attempts: Sequence[Mapping[str, object]] = (), stopped: bool = False
) -> dict[str, Any]:
    if type(stopped) is not bool or not isinstance(attempts, (list, tuple)) or len(attempts) > 150:
        raise _fail("goal_followup_invalid", "Followup evidence is not bounded.")
    request = goal.payload()["request"]
    fields = {
        "request_id",
        "revision",
        "outcome_id",
        "capability",
        "operation",
        "targets",
        "fingerprint",
        "action_fingerprint",
        "error_class",
        "capabilities_digest",
        "relevant_evidence_digest",
    }
    records = []
    for attempt in attempts:
        if (
            set(attempt) != fields
            or attempt["request_id"] != request["id"]
            or attempt["revision"] != request["revision"]
            or attempt["outcome_id"] not in request["outcome_ids"]
        ):
            raise _fail("goal_followup_invalid", "Attempt belongs to another original outcome.")
        identity = {
            key: attempt[key]
            for key in (
                "request_id",
                "revision",
                "outcome_id",
                "capability",
                "operation",
                "targets",
            )
        }
        if attempt["action_fingerprint"] != _value_digest(identity) or attempt[
            "fingerprint"
        ] != _value_digest(identity | {"error_class": attempt["error_class"]}):
            raise _fail("goal_followup_invalid", "Attempt fingerprint differs from its facts.")
        for key in (
            "fingerprint",
            "action_fingerprint",
            "capabilities_digest",
            "relevant_evidence_digest",
        ):
            _sha(attempt[key], key)
        _text(attempt["error_class"], "error_class")
        records.append(dict(attempt))
    value = {
        "format": "opencntx-goal-followup",
        "format_version": 2,
        "request": request,
        "stopped": stopped,
        "attempts": records,
    }
    return value | {"followup_digest": _value_digest(value)}


def load_followup_evidence(root: Path, goal: BoundGoal) -> dict[str, Any]:
    try:
        progress = load_goal_progress(root, goal).payload()
    except ContinuityError as exc:
        if exc.code != "goal_progress_missing":
            raise
        return build_followup_evidence(goal)
    found = {}
    for node in progress["nodes"]:
        for ref in node["evidence"]:
            path = _resolve_input(root, _safe_relative(ref["reference"], "followup_evidence"))
            if path.suffix != ".json":
                continue
            content = path.read_bytes()
            if _digest(content) != ref["sha256"]:
                raise _fail("goal_followup_stale", "Followup evidence bytes changed.")
            value = json.loads(content)
            if isinstance(value, dict) and value.get("format") == "opencntx-goal-followup":
                expected = build_followup_evidence(
                    goal, attempts=value["attempts"], stopped=value["stopped"]
                )
                if value != expected:
                    raise _fail(
                        "goal_followup_stale", "Followup evidence belongs to another request."
                    )
                found[ref["reference"]] = value
    if len(found) > 1:
        raise _fail("goal_followup_invalid", "Multiple active followup records are ambiguous.")
    return next(iter(found.values())) if found else build_followup_evidence(goal)


def recovery_decision(goal: BoundGoal, evidence: Mapping[str, Any]) -> str:
    if dict(evidence) != build_followup_evidence(
        goal, attempts=evidence["attempts"], stopped=evidence["stopped"]
    ):
        raise _fail("goal_followup_stale", "Recovery evidence is not bound to this request.")
    if evidence["stopped"]:
        return "OWNER_STOP"
    current = recovery_observation(goal, error_class="CHECK")
    attempts = [
        item
        for item in evidence["attempts"]
        if item["action_fingerprint"] == current["action_fingerprint"]
    ]
    if len(attempts) >= 3:
        return "RECOVERY_EXHAUSTED"
    if attempts and all(
        attempts[-1][key] == current[key]
        for key in ("capabilities_digest", "relevant_evidence_digest")
    ):
        return "SUPPRESS_UNCHANGED"
    return "CONTINUE"


def enforce_goal_followup(root: Path, goal: BoundGoal) -> None:
    decision = recovery_decision(goal, load_followup_evidence(root, goal))
    if decision != "CONTINUE":
        raise _fail("goal_followup_blocked", decision)


def compile_goal_context(
    root: Path,
    goal: BoundGoal,
    *,
    synthesis_reference: str | None = None,
    proposed_outcome: str | None = None,
    future_idea: bool = False,
) -> dict[str, Any]:
    """Compile status; does not replace OWNER authority or native terminal routing."""
    from .continuity import validate_current_goal_binding
    from .outcome_coverage import compile_current_outcomes, integrate_outcomes

    bound = validate_current_goal_binding(root, goal.payload(), expected=goal)
    try:
        matrix = compile_current_outcomes(root, goal, synthesis_reference=synthesis_reference)
    except ContinuityError as exc:
        if exc.code != "goal_progress_missing":
            raise
        matrix = integrate_outcomes(goal, [])
    if matrix.get("request") != bound["request"] or matrix.get("matrix_digest") != _value_digest(
        {k: v for k, v in matrix.items() if k != "matrix_digest"}
    ):
        raise _fail("goal_output_stale", "Outcome matrix belongs to another current request.")
    if set(matrix["outcomes"]) != set(bound["request"]["outcome_ids"]):
        raise _fail("goal_output_invalid", "Output loses an original outcome.")
    opened = [key for key, status in matrix["outcomes"].items() if status != "DELIVERED"]
    if future_idea or proposed_outcome is not None and proposed_outcome not in opened:
        raise _fail(
            "goal_followup_unrelated", "Suggestion does not serve an open original outcome."
        )
    if proposed_outcome is not None and proposed_outcome != bound["action"]["outcome_id"]:
        raise _fail(
            "goal_followup_unrelated", "Suggestion does not match the currently bound action."
        )
    base = decide_finalization(bound["execution_capsule_v1"])
    followup = load_followup_evidence(root, goal)
    recovery = recovery_decision(goal, followup)
    next_outcome = bound["action"]["outcome_id"]
    decision, reason = base["decision"], base["reason"]
    if recovery == "OWNER_STOP":
        decision, reason = "BLOCKED", "OWNER_STOP"
    elif decision.startswith("COMPLETE") and matrix["status"] != "TECHNICALLY_COMPLETE":
        decision, reason = "BLOCKED", "OPEN_ORIGINAL_OUTCOMES"
    elif decision == "CONTINUE":
        if recovery != "CONTINUE":
            decision, reason = "BLOCKED", recovery
        else:
            try:
                progress = load_goal_progress(root, goal)
            except ContinuityError as exc:
                if exc.code != "goal_progress_missing":
                    raise
            else:
                ready = progress_readiness(progress, goal)["ready_nodes"]
                if not ready and matrix["status"] != "TECHNICALLY_COMPLETE":
                    decision, reason = "BLOCKED", "NO_READY_ORIGINAL_OUTCOME"
    if base["decision"] == "CONTINUE" and recovery in {"SUPPRESS_UNCHANGED", "RECOVERY_EXHAUSTED"}:
        progress = load_goal_progress(root, goal)
        ready = progress_readiness(progress, goal)["ready_nodes"]
        attempted = {item["outcome_id"] for item in followup["attempts"]}
        alternatives = sorted(
            {
                outcome
                for node in progress.payload()["nodes"]
                if node["id"] in ready
                for outcome in node["outcome_ids"]
                if outcome in opened and outcome not in attempted
            }
        )
        if alternatives:
            decision, reason = "CONTINUE", "REBIND_INDEPENDENT_OUTCOME"
            next_outcome = alternatives[0]
    value = {
        "format": "opencntx-goal-output-context",
        "format_version": 2,
        "request": bound["request"],
        "capsule_digest": bound["execution_capsule_v1"]["capsule_digest"],
        "matrix_digest": matrix["matrix_digest"],
        "open_outcome_ids": opened,
        "goal_status": matrix["status"],
        "decision": decision,
        "reason": reason,
        "proposed_outcome": proposed_outcome,
        "next_outcome_id": next_outcome if decision == "CONTINUE" else None,
        "authority_changed": False,
    }
    return value | {"context_digest": _value_digest(value)}


def plan_request_replacement(
    previous: BoundGoal, replacement: BoundGoal, old_outcomes: Mapping[str, str]
) -> dict[str, Any]:
    old, new = previous.payload()["request"], replacement.payload()["request"]
    if set(old_outcomes) != set(old["outcome_ids"]):
        raise _fail("goal_replacement_invalid", "Previous outcomes must all remain visible.")
    if any(
        status not in {"DELIVERED", "PARTIAL", "BLOCKED", "NOT_ASSESSED"}
        for status in old_outcomes.values()
    ):
        raise _fail("goal_replacement_invalid", "Prior outcome status is unsupported.")
    explicit = (
        new["source"]["role"] == "OWNER"
        and new["source"]["reference"] != old["source"]["reference"]
        and (
            (new["id"] == old["id"] and new["revision"] > old["revision"])
            or (new["id"] != old["id"] and new["revision"] == 1)
        )
        and replacement.payload()["intent_v1"]["authority_state"] == "APPROVED"
    )
    value = {
        "format": "opencntx-request-replacement",
        "format_version": 2,
        "previous_request": old,
        "replacement_request": new,
        "previous_outcomes": dict(old_outcomes),
        "status": "EXPLICIT_REPLACEMENT" if explicit else "PROPOSAL_ONLY",
        "previous_outcome_disposition": "SUPERSEDED_VISIBLE" if explicit else "UNCHANGED",
        "authority_granted": False,
        "execution": "NOT_PERFORMED",
    }
    return value | {"replacement_digest": _value_digest(value)}
