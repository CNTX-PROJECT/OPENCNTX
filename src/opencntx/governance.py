"""Proportional routing with one invariant safety kernel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .continuity import _fail, _value_digest

PROFILES = ("ANSWER_ONLY", "LIGHT_TASK", "GOVERNED_FLOW")
CHECK_CLASSES = ("HARD_BLOCK", "PROMOTE", "WARN")
HARD_BLOCK_CHECKS = frozenset(
    {
        "AUTHORITY_MISSING",
        "TARGET_UNBOUND",
        "PRIVACY_UNCLEAR",
        "PROTECTED_RESOURCE",
        "INTEGRITY_FAILED",
        "EXTERNAL_WRITE_UNAPPROVED",
        "IRREVERSIBLE_ACTION",
    }
)
PROMOTE_CHECKS = frozenset(
    {
        "AMBIGUOUS_GOAL",
        "MULTIPLE_TARGETS",
        "DEPENDENT_STEPS",
        "WRITER_OVERLAP",
        "MATERIAL_RISK",
        "TWO_FAILED_ATTEMPTS",
        "VERIFICATION_LEASE_INVALID",
    }
)
WARN_CHECKS = frozenset({"STYLE_ONLY", "OPTIONAL_METADATA", "START_HERE_SOFT_BUDGET"})
PROFILE_OVERHEAD = {
    "ANSWER_ONLY": {"safety_checks": 7, "durable_artifacts": 0, "state_writes": 0},
    "LIGHT_TASK": {"safety_checks": 7, "durable_artifacts": 2, "state_writes": 1},
    "GOVERNED_FLOW": {"safety_checks": 7, "durable_artifacts": 8, "state_writes": 4},
}


def profile_overhead(profile: str) -> dict[str, int]:
    """Return the fixed operation budget without reducing the safety kernel."""
    if profile not in PROFILES:
        raise _fail("governance_facts_invalid", "Governance profile is invalid.")
    return dict(PROFILE_OVERHEAD[profile])


def classify_check(check: str) -> str:
    """Classify only the fixed R17 matrix; unknown checks fail closed."""
    if check in HARD_BLOCK_CHECKS:
        return "HARD_BLOCK"
    if check in PROMOTE_CHECKS:
        return "PROMOTE"
    if check in WARN_CHECKS:
        return "WARN"
    raise _fail("governance_check_unknown", "The governance check is not allowlisted.")


def _facts(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "answer_only",
        "writes",
        "reversible",
        "target_count",
        "dependent_steps",
        "external_write",
        "irreversible",
        "protected_resource",
        "privacy_clear",
        "authority_present",
        "integrity_valid",
        "goal_ambiguous",
        "material_risk",
        "failed_attempts",
        "writer_overlap",
        "warnings",
    }
    if set(value) != expected:
        raise _fail("governance_facts_invalid", "Governance facts differ from the fixed contract.")
    facts = dict(value)
    boolean_fields = expected - {"writes", "target_count", "dependent_steps", "failed_attempts", "warnings"}
    if any(not isinstance(facts[field], bool) for field in boolean_fields):
        raise _fail("governance_facts_invalid", "Boolean governance facts are invalid.")
    for field, maximum in (("writes", 1000), ("target_count", 1000), ("dependent_steps", 1000), ("failed_attempts", 1000)):
        if type(facts[field]) is not int or not 0 <= facts[field] <= maximum:
            raise _fail("governance_facts_invalid", f"{field} is outside its boundary.")
    warnings = facts["warnings"]
    if isinstance(warnings, (str, bytes)) or len(warnings) > 20 or len(warnings) != len(set(warnings)):
        raise _fail("governance_facts_invalid", "Warnings are invalid or duplicated.")
    if any(classify_check(item) != "WARN" for item in warnings):
        raise _fail("governance_facts_invalid", "A warning cannot weaken another check class.")
    facts["warnings"] = sorted(warnings)
    return facts


def assess_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    """Select the smallest eligible route and preserve all hard outcomes."""
    facts = _facts(value)
    hard: list[str] = []
    promote: list[str] = []
    if not facts["authority_present"]:
        hard.append("AUTHORITY_MISSING")
    if facts["writes"] and facts["target_count"] != 1:
        hard.append("TARGET_UNBOUND")
    if not facts["privacy_clear"]:
        hard.append("PRIVACY_UNCLEAR")
    if facts["protected_resource"]:
        hard.append("PROTECTED_RESOURCE")
    if not facts["integrity_valid"]:
        hard.append("INTEGRITY_FAILED")
    if facts["external_write"]:
        hard.append("EXTERNAL_WRITE_UNAPPROVED")
    if facts["irreversible"]:
        hard.append("IRREVERSIBLE_ACTION")
    if facts["goal_ambiguous"]:
        promote.append("AMBIGUOUS_GOAL")
    if facts["target_count"] > 1:
        promote.append("MULTIPLE_TARGETS")
    if facts["dependent_steps"] > 1:
        promote.append("DEPENDENT_STEPS")
    if facts["writer_overlap"]:
        promote.append("WRITER_OVERLAP")
    if facts["material_risk"]:
        promote.append("MATERIAL_RISK")
    if facts["failed_attempts"] >= 2:
        promote.append("TWO_FAILED_ATTEMPTS")
    if hard:
        profile, status = "GOVERNED_FLOW", "BLOCKED"
    elif facts["answer_only"] and facts["writes"] == 0 and not promote:
        profile, status = "ANSWER_ONLY", "READY"
    elif (
        facts["writes"] <= 1
        and facts["reversible"]
        and facts["target_count"] <= 1
        and facts["dependent_steps"] <= 1
        and not promote
    ):
        profile, status = "LIGHT_TASK", "READY"
    else:
        profile, status = "GOVERNED_FLOW", "READY"
    result = {
        "format": "opencntx-governance-decision",
        "format_version": 1,
        "profile": profile,
        "status": status,
        "hard_blocks": sorted(hard),
        "promotion_reasons": sorted(promote),
        "warnings": facts["warnings"],
        "authority_changed": False,
        "writes_allowed": status == "READY" and profile != "ANSWER_ONLY",
        "evidence_level": {"ANSWER_ONLY": "NONE", "LIGHT_TASK": "COMPACT", "GOVERNED_FLOW": "FULL"}[profile],
        "facts_digest": _value_digest(facts),
    }
    return result | {"decision_digest": _value_digest(result)}


def create_verification_lease(
    *,
    version: str,
    project_root_digest: str,
    context_digest: str,
    instructions_digest: str,
) -> dict[str, Any]:
    """Bind reusable verification to every fact that can invalidate it."""
    basis = {
        "format": "opencntx-verification-lease",
        "format_version": 1,
        "version": version,
        "project_root_digest": project_root_digest,
        "context_digest": context_digest,
        "instructions_digest": instructions_digest,
    }
    if any(
        not isinstance(item, str) or not item
        for item in (version, project_root_digest, context_digest, instructions_digest)
    ):
        raise _fail("verification_lease_invalid", "Verification lease fields are invalid.")
    return basis | {"lease_digest": _value_digest(basis)}


def validate_verification_lease(lease: Mapping[str, Any], **current: str) -> bool:
    """Return False on any digest/version drift; never silently refresh."""
    basis = {key: value for key, value in lease.items() if key != "lease_digest"}
    expected = {key: value for key, value in current.items() if key in basis}
    return (
        set(lease) == {*basis, "lease_digest"}
        and lease.get("lease_digest") == _value_digest(basis)
        and all(basis.get(key) == value for key, value in expected.items())
        and len(expected) == 4
    )


def assess_profile_with_lease(
    facts: Mapping[str, Any],
    lease: Mapping[str, Any],
    *,
    version: str,
    project_root_digest: str,
    context_digest: str,
    instructions_digest: str,
) -> dict[str, Any]:
    """Promote a stale light lease without weakening a simultaneous hard block."""
    result = assess_profile(facts)
    if validate_verification_lease(
        lease,
        version=version,
        project_root_digest=project_root_digest,
        context_digest=context_digest,
        instructions_digest=instructions_digest,
    ):
        return result
    basis = {key: value for key, value in result.items() if key != "decision_digest"}
    basis["profile"] = "GOVERNED_FLOW"
    basis["promotion_reasons"] = sorted(
        {*basis["promotion_reasons"], "VERIFICATION_LEASE_INVALID"}
    )
    basis["writes_allowed"] = basis["status"] == "READY"
    basis["evidence_level"] = "FULL"
    return basis | {"decision_digest": _value_digest(basis)}


def bind_governance_decision(
    decision: Mapping[str, Any],
    *,
    goal_digest: str,
    authority_digest: str,
    evidence_digest: str,
) -> dict[str, Any]:
    """Bind a profile decision to the goal, authority, and cumulative evidence."""
    decision_basis = {key: value for key, value in decision.items() if key != "decision_digest"}
    if decision.get("decision_digest") != _value_digest(decision_basis):
        raise _fail("governance_decision_invalid", "The profile decision digest is invalid.")
    bindings = {
        "goal_digest": goal_digest,
        "authority_digest": authority_digest,
        "evidence_digest": evidence_digest,
    }
    if any(not isinstance(value, str) or len(value) != 64 for value in bindings.values()):
        raise _fail("governance_binding_invalid", "Governance bindings must be digests.")
    basis = {
        "format": "opencntx-governance-envelope",
        "format_version": 1,
        "decision": dict(decision),
        "bindings": bindings,
        "previous_envelope_digest": None,
        "downgrade_prevented": False,
        "authority_changed": False,
    }
    return basis | {"envelope_digest": _value_digest(basis)}


def promote_governance_decision(
    envelope: Mapping[str, Any], facts: Mapping[str, Any]
) -> dict[str, Any]:
    """Promote automatically while preserving bindings and preventing downgrade."""
    prior_basis = {key: value for key, value in envelope.items() if key != "envelope_digest"}
    if envelope.get("envelope_digest") != _value_digest(prior_basis):
        raise _fail("governance_decision_invalid", "The governance envelope is invalid.")
    prior = dict(envelope["decision"])
    candidate = assess_profile(facts)
    ranks = {"ANSWER_ONLY": 0, "LIGHT_TASK": 1, "GOVERNED_FLOW": 2}
    downgrade = ranks[candidate["profile"]] < ranks[prior["profile"]]
    selected = prior if downgrade else candidate
    basis = {
        "format": "opencntx-governance-envelope",
        "format_version": 1,
        "decision": selected,
        "bindings": dict(envelope["bindings"]),
        "previous_envelope_digest": envelope["envelope_digest"],
        "downgrade_prevented": downgrade,
        "authority_changed": False,
    }
    return basis | {"envelope_digest": _value_digest(basis)}


def sidecar_decision(
    *,
    active_touches: Sequence[str],
    sidecar_touches: Sequence[str],
    advances_roadmap: bool,
) -> dict[str, Any]:
    """Allow parallel side work only when it cannot overlap or advance the writer."""
    active = set(active_touches)
    sidecar = set(sidecar_touches)
    overlap = sorted(active & sidecar)
    status = "BLOCKED" if overlap or advances_roadmap else "ISOLATED"
    return {
        "status": status,
        "overlap": overlap,
        "roadmap_advance_allowed": False,
        "single_writer_preserved": True,
    }
