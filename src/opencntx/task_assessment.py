"""Proportionate semantic assessment; no project creation or second scheduler."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .continuity import _fail, _value_digest
from .goal_binding import BoundGoal, _canonical, _text

KINDS = frozenset(
    {"SINGLE_RESULT", "COUNT_ONLY", "MULTI_PHASE", "MULTI_STREAM", "FULL_COLLECTION_ANALYSIS"}
)


@dataclass(frozen=True)
class TaskFacts:
    """Host-interpreted meaning, not a claim to parse human language automatically."""

    kind: str = "SINGLE_RESULT"
    independent_large_streams: int = 0
    dependent_phases: int = 1
    analysis_dimensions: int = 0
    item_count: int | None = None
    uncertainty: str = "KNOWN"
    risk: str = "LOW"


def classify_task(facts: TaskFacts) -> dict[str, Any]:
    """Pure projectless path: counting 4,001 things does not create a roadmap."""
    if not isinstance(facts, TaskFacts) or _text(facts.kind, "kind") not in KINDS:
        raise _fail("task_assessment_invalid", "Unsupported task kind.")
    for name, value, minimum, maximum in (
        ("streams", facts.independent_large_streams, 0, 50),
        ("phases", facts.dependent_phases, 1, 1000),
        ("dimensions", facts.analysis_dimensions, 0, 50),
    ):
        if type(value) is not int or not minimum <= value <= maximum:
            raise _fail("task_assessment_invalid", f"{name} is outside its integer boundary.")
    if facts.item_count is not None and (
        type(facts.item_count) is not int or not 0 <= facts.item_count < 2**63
    ):
        raise _fail("task_assessment_invalid", "Item count is invalid.")
    if _text(facts.uncertainty, "uncertainty") not in {"KNOWN", "NEEDS_PROBE"}:
        raise _fail("task_assessment_invalid", "Unknown uncertainty state.")
    if _text(facts.risk, "risk") not in {"LOW", "MEDIUM", "HIGH"}:
        raise _fail("task_assessment_invalid", "Unknown risk class.")
    if facts.kind == "COUNT_ONLY" and (
        facts.independent_large_streams or facts.dependent_phases != 1 or facts.analysis_dimensions
    ):
        raise _fail(
            "task_assessment_conflict", "Count-only label contradicts the actual work facts."
        )
    if facts.kind == "MULTI_STREAM" and facts.independent_large_streams < 2:
        raise _fail(
            "task_assessment_conflict", "Multiple streams require at least two large streams."
        )
    if facts.kind == "MULTI_PHASE" and facts.dependent_phases < 2:
        raise _fail("task_assessment_conflict", "Multiple phases require at least two phases.")
    if facts.kind == "FULL_COLLECTION_ANALYSIS" and facts.analysis_dimensions < 2:
        raise _fail(
            "task_assessment_conflict", "Full multidimensional analysis needs its dimensions."
        )
    if facts.independent_large_streams >= 2 or facts.kind == "FULL_COLLECTION_ANALYSIS":
        size, planning = "MEGA", "MAIN_AND_CHILD_ROADMAPS"
    elif (
        facts.independent_large_streams
        or facts.dependent_phases >= 2
        or facts.analysis_dimensions >= 2
    ):
        size, planning = "LARGE", "MAIN_ROADMAP"
    else:
        size, planning = "SHORT", "CHECKLIST"
    return {
        "size_class": size,
        "required_planning": planning,
        "reconnaissance_required": facts.uncertainty == "NEEDS_PROBE",
        "risk": facts.risk,
        "facts": asdict(facts),
        "authority_granted": False,
    }


@dataclass(frozen=True)
class TaskAssessment:
    """Supervisor-retained immutable projection, not execution authority."""

    canonical_json: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def assess_bound_task(
    goal: BoundGoal,
    facts: TaskFacts,
    *,
    reason: str,
    previous: TaskAssessment | None = None,
) -> TaskAssessment:
    """Reassess without losing original outcomes, source history or authority."""
    bound = goal.payload()
    request = bound["request"]
    prior = None if previous is None else previous.payload()
    authority = bound["intent_v1"]["authority_state"]
    if prior is not None and (
        prior["request_id"] != request["id"]
        or prior["request_revision"] > request["revision"]
        or not set(prior["outcome_ids"]).issubset(request["outcome_ids"])
        or prior["authority_state"] != authority
        or prior["classification"]["risk"] != facts.risk
    ):
        raise _fail(
            "task_reassessment_conflict",
            "Reassessment would lose or change the original assignment.",
        )
    value = {
        "format": "opencntx-task-assessment",
        "format_version": 2,
        "assessment_revision": 1 if prior is None else prior["assessment_revision"] + 1,
        "previous_assessment_digest": None if prior is None else prior["assessment_digest"],
        "goal_binding_digest": bound["binding_digest"],
        "request_id": request["id"],
        "request_revision": request["revision"],
        "outcome_ids": request["outcome_ids"],
        "request_source": request["source"],
        "original_source": request["source"] if prior is None else prior["original_source"],
        "authority_state": authority,
        "authority_changed": False,
        "reason": _text(reason, "assessment_reason"),
        "classification": classify_task(facts),
    }
    return TaskAssessment(_canonical(value | {"assessment_digest": _value_digest(value)}))


def validate_task_assessment(assessment: TaskAssessment, goal: BoundGoal) -> dict[str, Any]:
    value = assessment.payload()
    bound = goal.payload()
    request = bound["request"]
    basis = {key: item for key, item in value.items() if key != "assessment_digest"}
    if (
        value.get("format") != "opencntx-task-assessment"
        or type(value.get("format_version")) is not int
        or value.get("format_version") != 2
        or value.get("assessment_digest") != _value_digest(basis)
        or value.get("goal_binding_digest") != bound["binding_digest"]
        or value.get("request_id") != request["id"]
        or value.get("request_revision") != request["revision"]
        or value.get("outcome_ids") != request["outcome_ids"]
        or value.get("request_source") != request["source"]
        or value.get("authority_state") != bound["intent_v1"]["authority_state"]
        or value.get("authority_changed") is not False
    ):
        raise _fail("task_assessment_stale", "Assessment does not bind this current goal.")
    try:
        classification = value["classification"]
        facts = TaskFacts(**classification["facts"])
        if classification != classify_task(facts):
            raise ValueError("Classification contradicts its facts.")
    except (KeyError, TypeError, ValueError) as exc:
        raise _fail("task_assessment_invalid", "Inconsistent assessment facts.") from exc
    return value


def require_assessed_broad_execution(assessment: TaskAssessment, goal: BoundGoal) -> None:
    """No standalone ready flag: uncertainty/planning needs cannot be bypassed."""
    classification = validate_task_assessment(assessment, goal)["classification"]
    if classification["reconnaissance_required"]:
        raise _fail(
            "task_reconnaissance_required", "Bounded source reconnaissance is required first."
        )
    if classification["required_planning"] != "CHECKLIST":
        raise _fail(
            "task_planning_required",
            "Verified main/child planning is required before broad execution.",
        )
