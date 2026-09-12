"""Deterministic project-roadmap routing and bounded continuation decisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

_RELATIONS = frozenset({"INFORMATION", "RELATED", "EXTENSION", "DISTINCT_OUTCOME", "SIDE_TOPIC"})
_SIZES = frozenset({"SHORT", "MEDIUM", "LARGE", "MEGA"})
_CONTEXT_ROLES = frozenset({"CURRENT_STEP", "RETURN_ANCHOR", "DECISION", "SUPPORTING"})
_ROLE_PRIORITY = {"CURRENT_STEP": 0, "RETURN_ANCHOR": 1, "DECISION": 2, "SUPPORTING": 3}
_REQUIRED_ROLES = frozenset({"CURRENT_STEP", "RETURN_ANCHOR"})


def _identifier(value: str | None, name: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{name} must be a non-empty bounded string")
    return value.strip()


@dataclass(frozen=True)
class ProjectTaskFacts:
    """Host-supplied project relationship; no human-language inference is claimed."""

    project_known: bool
    relation: str = "RELATED"
    size_class: str = "SHORT"


def route_project_task(
    facts: ProjectTaskFacts,
    *,
    master_roadmap_id: str | None = None,
    current_child_roadmap_id: str | None = None,
    current_step_id: str | None = None,
    existing_child_roadmap_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Route one task into the existing hierarchy without creating a second master."""
    if not isinstance(facts, ProjectTaskFacts) or type(facts.project_known) is not bool:
        raise ValueError("facts must be ProjectTaskFacts with a boolean project flag")
    if facts.relation not in _RELATIONS:
        raise ValueError("unsupported task relation")
    if facts.size_class not in _SIZES:
        raise ValueError("unsupported task size")
    master = _identifier(master_roadmap_id, "master roadmap")
    current_child = _identifier(current_child_roadmap_id, "current child roadmap")
    current_step = _identifier(current_step_id, "current step")
    children = tuple(
        _identifier(item, "child roadmap", required=True) for item in existing_child_roadmap_ids
    )
    if len(children) != len(set(children)):
        raise ValueError("child roadmap identifiers must be unique")

    recipe_id = {
        "SHORT": "builtin.short-v1",
        "MEDIUM": "builtin.medium-v1",
        "LARGE": "builtin.large-v1",
        "MEGA": "builtin.mega-v1",
    }[facts.size_class]
    base: dict[str, Any] = {
        "roadmap_required": facts.project_known,
        "project_known": facts.project_known,
        "relation": facts.relation,
        "size_class": facts.size_class,
        "master_roadmap_id": master,
        "target_roadmap_id": None,
        "parent_roadmap_id": None,
        "return_to_roadmap_id": current_child,
        "return_to_step_id": current_step,
        "child_ordinal": None,
        "recipe_id": recipe_id,
        "method_steps": {
            "SHORT": ["scope", "change", "verify", "record"],
            "MEDIUM": ["scope", "plan", "change", "verify", "record"],
            "LARGE": ["scope", "child-roadmap", "implement", "verify", "handoff"],
            "MEGA": [
                "master-roadmap",
                "children",
                "dependencies",
                "milestones",
                "verify",
                "release",
            ],
        }[facts.size_class],
    }
    if not facts.project_known:
        return base | {"action": "ANSWER_ONLY", "recipe_id": None, "method_steps": []}
    if master is None:
        raise ValueError("a known project requires its master roadmap")
    if facts.relation == "SIDE_TOPIC":
        return base | {"action": "PARK_AND_RETURN", "target_roadmap_id": current_child or master}
    if facts.relation == "DISTINCT_OUTCOME" and facts.size_class in {"LARGE", "MEGA"}:
        return base | {
            "action": "CREATE_CHILD_ROADMAP",
            "parent_roadmap_id": master,
            "child_ordinal": len(children) + 1,
        }
    if facts.size_class == "SHORT":
        return base | {"action": "ATTACH_STEP", "target_roadmap_id": current_child or master}
    return base | {"action": "EXTEND_CHILD_ROADMAP", "target_roadmap_id": current_child or master}


@dataclass(frozen=True)
class ContextSource:
    """One bounded source known to a host before content is loaded."""

    source_id: str
    revision: int
    sha256: str
    byte_count: int
    role: str = "SUPPORTING"


def _validated_source(source: ContextSource) -> ContextSource:
    if not isinstance(source, ContextSource):
        raise TypeError("context sources must be ContextSource values")
    _identifier(source.source_id, "source id", required=True)
    if type(source.revision) is not int or source.revision < 1:
        raise ValueError("source revision must be a positive integer")
    if (
        not isinstance(source.sha256, str)
        or len(source.sha256) != 64
        or any(character not in "0123456789abcdef" for character in source.sha256)
    ):
        raise ValueError("source digest must be lowercase SHA-256")
    if type(source.byte_count) is not int or not 0 <= source.byte_count <= 100_000_000:
        raise ValueError("source byte count is outside its boundary")
    if source.role not in _CONTEXT_ROLES:
        raise ValueError("unsupported context role")
    return source


def plan_context_load(
    sources: Sequence[ContextSource],
    *,
    previous_digests: Mapping[str, str] | None = None,
    available_source_ids: Sequence[str] | None = None,
    max_bytes: int = 250_000,
) -> dict[str, Any]:
    """Load anchors and changed sources, while referencing unchanged material by digest."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= 100_000_000:
        raise ValueError("context byte budget is outside its boundary")
    previous = {} if previous_digests is None else dict(previous_digests)
    available = None if available_source_ids is None else set(available_source_ids)
    validated = tuple(_validated_source(source) for source in sources)
    if len(validated) != len({source.source_id for source in validated}):
        raise ValueError("context source identifiers must be unique")
    ordered = sorted(validated, key=lambda item: (_ROLE_PRIORITY[item.role], item.source_id))
    naive_bytes = sum(item.byte_count for item in ordered)
    load: list[str] = []
    reference: list[str] = []
    skipped: list[str] = []
    required_ids: list[str] = []
    loaded_bytes = 0
    referenced_bytes = 0
    for source in ordered:
        unchanged = previous.get(source.source_id) == source.sha256
        required = source.role in _REQUIRED_ROLES
        if required:
            required_ids.append(source.source_id)
        reference_available = available is None or source.source_id in available
        if unchanged and not required and reference_available:
            reference.append(source.source_id)
            referenced_bytes += source.byte_count
            continue
        if loaded_bytes + source.byte_count <= max_bytes:
            load.append(source.source_id)
            loaded_bytes += source.byte_count
            continue
        if required:
            raise ValueError("required context exceeds the byte budget")
        skipped.append(source.source_id)
    omitted_bytes = naive_bytes - loaded_bytes - referenced_bytes
    # Keep reduction as the amount not loaded into this request for compatibility
    # with existing hosts. Omission is reported separately: references may be
    # available through a verified cache, while skipped bytes are genuinely absent.
    reduction = (
        0.0 if naive_bytes == 0 else round((naive_bytes - loaded_bytes) * 100 / naive_bytes, 1)
    )
    omission_percent = 0.0 if naive_bytes == 0 else round(omitted_bytes * 100 / naive_bytes, 1)
    return {
        "format": "opencntx-context-load-plan",
        "format_version": 1,
        "max_bytes": max_bytes,
        "naive_bytes": naive_bytes,
        "loaded_bytes": loaded_bytes,
        "referenced_bytes": referenced_bytes,
        "omitted_bytes": omitted_bytes,
        "effective_bytes": loaded_bytes + referenced_bytes,
        "omission_percent": omission_percent,
        "reduction_percent": reduction,
        "load_source_ids": load,
        "reference_source_ids": reference,
        "skipped_source_ids": skipped,
        "required_source_ids": required_ids,
        "omitted_source_ids": list(skipped),
        "availability_checked": available is not None,
    }


@dataclass(frozen=True)
class ExecutionFacts:
    """Explicit host state used to select one terminal or continuing action."""

    authority_granted: bool = False
    safe_action_ready: bool = False
    open_steps: bool = True
    material_choice_required: bool = False
    blocker_present: bool = False
    recovery_exhausted: bool = False
    rollover_required: bool = False
    evidence_complete: bool = False
    feedback_only: bool = False
    return_to_roadmap_id: str | None = None
    return_to_step_id: str | None = None


def decide_execution(facts: ExecutionFacts) -> dict[str, Any]:
    """Continue safe work by default and stop only for an explicit bounded reason."""
    if not isinstance(facts, ExecutionFacts):
        raise TypeError("facts must be ExecutionFacts")
    for name, value in asdict(facts).items():
        if name not in {"return_to_roadmap_id", "return_to_step_id"} and type(value) is not bool:
            raise ValueError(f"{name} must be boolean")
    roadmap = _identifier(facts.return_to_roadmap_id, "return roadmap")
    step = _identifier(facts.return_to_step_id, "return step")
    decision = "CONTINUE"
    technical_mutation_allowed = False
    reason = "OPEN_SAFE_WORK"
    if facts.feedback_only:
        decision, reason, technical_mutation_allowed = "PARK_AND_RETURN", "FEEDBACK_ONLY", False
    elif not facts.authority_granted:
        decision, reason, technical_mutation_allowed = "ASK_OWNER", "AUTHORITY_REQUIRED", False
    elif facts.material_choice_required:
        decision, reason, technical_mutation_allowed = (
            "ASK_OWNER",
            "MATERIAL_CHOICE_REQUIRED",
            False,
        )
    elif facts.blocker_present and facts.recovery_exhausted:
        decision, reason, technical_mutation_allowed = "BLOCKED", "RECOVERY_EXHAUSTED", False
    elif facts.rollover_required:
        decision, reason = "HANDOFF", "ROLLOVER_REQUIRED"
    elif not facts.open_steps and facts.evidence_complete:
        decision, reason = "COMPLETE", "VERIFIED_OUTCOMES_COMPLETE"
    elif not facts.safe_action_ready:
        decision, reason = "WAIT_FOR_SAFE_ACTION", "NO_SAFE_ACTION_READY"
    else:
        technical_mutation_allowed = True
    return {
        "decision": decision,
        "reason": reason,
        "technical_mutation_allowed": technical_mutation_allowed,
        "return_to_roadmap_id": roadmap,
        "return_to_step_id": step,
    }
