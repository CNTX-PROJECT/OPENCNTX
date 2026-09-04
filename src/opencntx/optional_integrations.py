"""Provider-neutral start choices and optional integration contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .continuity import _fail, _one_line, _value_digest

INTERACTION_CAPABILITIES = frozenset({"INTERACTIVE_CHOICE"})
PROJECT_SCOPES = frozenset({"CURRENT_PROJECT", "ALL_REGISTERED_PROJECTS"})
METHOD_CHOICES = frozenset({"NONE", "PRESERVE_AND_LINK", "USE_RECOMMENDED"})
COMPANION_STATES = frozenset({"ABSENT", "COMPATIBLE", "OUTDATED", "DAMAGED", "AMBIGUOUS"})
TARGET_KINDS = frozenset({"LOCAL_FOLDER", "SYNCED_FOLDER", "API_ADAPTER"})
DIRECTIONS = frozenset({"PUSH_DERIVED", "BIDIRECTIONAL_REVIEW"})
CADENCES = frozenset({"MANUAL", "VERIFIED_CHANGE", "CHECKPOINT"})
CONFLICT_POLICIES = frozenset({"FAIL_CLOSED", "CREATE_CONFLICT_COPY"})

_START_LABELS = {
    "nl": {
        "question": "Wil je alleen de huidige opdracht starten, of de volledige roadmap?",
        "question_remaining": "Wil je alleen de huidige opdracht starten, of de resterende roadmap?",
        "current": "Enkel huidige opdracht",
        "roadmap": "Volledige roadmap",
        "remaining": "Resterende roadmap",
    },
    "en": {
        "question": "Start only the current assignment, or the complete roadmap?",
        "question_remaining": "Start only the current assignment, or the remaining roadmap?",
        "current": "Current assignment only",
        "roadmap": "Complete roadmap",
        "remaining": "Remaining roadmap",
    },
}


def _bounded_unique(values: Sequence[str], field: str, *, maximum: int = 100) -> list[str]:
    if isinstance(values, (str, bytes)) or not values or len(values) > maximum:
        raise _fail("integration_contract_invalid", f"{field} must be a bounded list.")
    result = [_one_line(value, field, 200) for value in values]
    if len(result) != len(set(result)):
        raise _fail("integration_contract_invalid", f"{field} contains duplicates.")
    return result


def _validate_digest(value: Mapping[str, object], field: str, code: str) -> dict[str, Any]:
    record = dict(value)
    digest = record.pop(field, None)
    if digest != _value_digest(record):
        raise _fail(code, "Contract digest differs.")
    return dict(value)


def build_start_authority_choice(
    *,
    roadmap_id: str,
    roadmap_revision: str,
    current_assignment: str,
    remaining_assignments: Sequence[str],
    roadmap_started: bool,
    host_capabilities: Sequence[str] = (),
    language: str = "en",
) -> dict[str, Any]:
    """Build exactly two choices without granting execution authority."""
    roadmap = _one_line(roadmap_id, "roadmap_id", 120)
    revision = _one_line(roadmap_revision, "roadmap_revision", 120)
    current = _one_line(current_assignment, "current_assignment", 120)
    remaining = _bounded_unique(remaining_assignments, "remaining_assignment")
    if remaining[0] != current:
        raise _fail(
            "start_authority_invalid",
            "Current assignment must be the first remaining assignment.",
        )
    capabilities = set(host_capabilities)
    if not capabilities.issubset(INTERACTION_CAPABILITIES):
        raise _fail("start_authority_invalid", "Host capability is unsupported.")
    selected_language = language.lower()
    labels = _START_LABELS.get(selected_language)
    if labels is None:
        raise _fail("start_authority_invalid", "Start-choice language is unsupported.")
    roadmap_label = labels["remaining"] if roadmap_started else labels["roadmap"]
    question = labels["question_remaining"] if roadmap_started else labels["question"]
    value = {
        "format": "opencntx-start-authority-choice",
        "format_version": 1,
        "language": selected_language,
        "roadmap_id": roadmap,
        "roadmap_revision": revision,
        "current_assignment": current,
        "remaining_assignments": remaining,
        "roadmap_started": roadmap_started,
        "presentation": (
            "INTERACTIVE_CHOICE"
            if "INTERACTIVE_CHOICE" in capabilities
            else "COPY_COMMANDS"
        ),
        "question": question,
        "choices": [
            {
                "choice_id": "CURRENT_ASSIGNMENT",
                "label": labels["current"],
                "submit_value": f"START {current}",
            },
            {
                "choice_id": "REMAINING_ROADMAP",
                "label": roadmap_label,
                "submit_value": f"AUTO PILOT {roadmap}",
            },
        ],
        "authority_granted": False,
    }
    return value | {"choice_digest": _value_digest(value)}


def resolve_start_authority_choice(
    choice: Mapping[str, object],
    *,
    expected_choice_digest: str,
    expected_roadmap_revision: str,
    expected_current_assignment: str,
    submitted_value: str,
) -> dict[str, Any]:
    """Resolve one exact button id or fallback command against live bindings."""
    record = _validate_digest(choice, "choice_digest", "start_authority_stale")
    if record.get("format") != "opencntx-start-authority-choice":
        raise _fail("start_authority_invalid", "Start choice format is invalid.")
    if expected_choice_digest != record["choice_digest"]:
        raise _fail("start_authority_stale", "Start choice changed.")
    if (
        record.get("roadmap_revision") != expected_roadmap_revision
        or record.get("current_assignment") != expected_current_assignment
    ):
        raise _fail("start_authority_stale", "Roadmap binding changed.")
    choices = record.get("choices")
    if not isinstance(choices, list) or len(choices) != 2:
        raise _fail("start_authority_invalid", "Exactly two start choices are required.")
    submitted = _one_line(submitted_value, "submitted_value", 240)
    matches = [
        item
        for item in choices
        if isinstance(item, Mapping)
        and submitted in {item.get("choice_id"), item.get("submit_value")}
    ]
    if len(matches) != 1:
        raise _fail("start_authority_invalid", "Start selection is not exact.")
    selected = matches[0]
    scope = str(selected["choice_id"])
    remaining = record.get("remaining_assignments")
    if not isinstance(remaining, list):
        raise _fail("start_authority_invalid", "Remaining assignments are invalid.")
    approved = [record["current_assignment"]] if scope == "CURRENT_ASSIGNMENT" else remaining
    value = {
        "format": "opencntx-start-authority",
        "format_version": 1,
        "roadmap_id": record["roadmap_id"],
        "roadmap_revision": record["roadmap_revision"],
        "current_assignment": record["current_assignment"],
        "scope": scope,
        "approved_assignments": approved,
        "release_authorized": False,
        "publication_authorized": False,
        "authority_granted": True,
    }
    return value | {"authority_digest": _value_digest(value)}


def build_onboarding_profile(
    *,
    project_id: str,
    project_scope: str,
    registered_projects: Sequence[str],
    selected_tools: Sequence[str],
    existing_method_detected: bool,
    method_choice: str,
) -> dict[str, Any]:
    """Record project reach and existing-method handling without scanning."""
    project = _one_line(project_id, "project_id", 120)
    scope = project_scope.upper()
    if scope not in PROJECT_SCOPES:
        raise _fail("integration_onboarding_invalid", "Project scope is invalid.")
    projects = _bounded_unique(registered_projects, "registered_project")
    if project not in projects:
        raise _fail("integration_onboarding_invalid", "Current project is not registered.")
    tools = _bounded_unique(selected_tools, "selected_tool", maximum=50)
    method = method_choice.upper()
    if method not in METHOD_CHOICES:
        raise _fail("integration_onboarding_invalid", "Method choice is invalid.")
    if existing_method_detected != (method != "NONE"):
        raise _fail("integration_onboarding_invalid", "Existing-method choice is incomplete.")
    selected_projects = [project] if scope == "CURRENT_PROJECT" else projects
    value = {
        "format": "opencntx-integration-onboarding",
        "format_version": 1,
        "project_id": project,
        "project_scope": scope,
        "selected_projects": selected_projects,
        "future_registered_projects": scope == "ALL_REGISTERED_PROJECTS",
        "selected_tools": tools,
        "existing_method_detected": existing_method_detected,
        "method_choice": method,
        "inventory_only": True,
        "writes": [],
        "authority_granted": False,
    }
    return value | {"profile_digest": _value_digest(value)}


def build_companion_plan(
    *,
    onboarding: Mapping[str, object],
    requested: bool,
    adapter_id: str,
    detection: Mapping[str, object],
    target_version: str,
) -> dict[str, Any]:
    """Compile read-only detection facts into an approval-bound companion plan."""
    profile = _validate_digest(onboarding, "profile_digest", "integration_onboarding_invalid")
    if profile.get("format") != "opencntx-integration-onboarding":
        raise _fail("integration_onboarding_invalid", "Onboarding format is invalid.")
    adapter = _one_line(adapter_id, "adapter_id", 120)
    version = _one_line(target_version, "target_version", 80)
    state = str(detection.get("state", "")).upper()
    if state not in COMPANION_STATES:
        raise _fail("companion_detection_invalid", "Companion state is invalid.")
    provenance = detection.get("provenance")
    if not isinstance(provenance, str) or not provenance:
        raise _fail("companion_detection_invalid", "Companion provenance is missing.")
    installed_version = detection.get("installed_version")
    if installed_version is not None and not isinstance(installed_version, str):
        raise _fail("companion_detection_invalid", "Installed version is invalid.")
    if not requested:
        action, status, approval = "NONE", "DECLINED", False
    elif state == "AMBIGUOUS":
        action, status, approval = "BLOCKED", "AMBIGUOUS", False
    elif state == "COMPATIBLE":
        action = "VALIDATE" if detection.get("projects_initialized") is True else "INITIALIZE"
        status, approval = "READY", action == "INITIALIZE"
    elif state == "ABSENT":
        action, status, approval = "INSTALL_AND_INITIALIZE", "READY", True
    elif state == "OUTDATED":
        action, status, approval = "UPDATE_AND_VALIDATE", "READY", True
    else:
        action, status, approval = "REPAIR_AND_VALIDATE", "READY", True
    proposed_writes: list[str] = []
    if action not in {"NONE", "BLOCKED", "VALIDATE"}:
        proposed_writes = ["COMPANION_RUNTIME", "SELECTED_PROJECT_INTEGRATIONS"]
    value = {
        "format": "opencntx-specification-companion-plan",
        "format_version": 1,
        "adapter_id": adapter,
        "requested": requested,
        "status": status,
        "action": action,
        "detected_state": state,
        "installed_version": installed_version,
        "target_version": version,
        "provenance_digest": _value_digest(provenance),
        "selected_projects": profile["selected_projects"],
        "selected_tools": profile["selected_tools"],
        "approval_required": approval,
        "proposed_writes": proposed_writes,
        "network_actions_performed": 0,
        "writes_performed": 0,
        "onboarding_digest": profile["profile_digest"],
    }
    return value | {"plan_digest": _value_digest(value)}


def approve_companion_plan(
    plan: Mapping[str, object], *, expected_plan_digest: str, approved: bool
) -> dict[str, Any]:
    """Record approval only; an adapter must execute and prove any action later."""
    record = _validate_digest(plan, "plan_digest", "companion_plan_stale")
    if record.get("format") != "opencntx-specification-companion-plan":
        raise _fail("companion_plan_invalid", "Companion plan format is invalid.")
    if record["plan_digest"] != expected_plan_digest:
        raise _fail("companion_plan_stale", "Companion plan changed.")
    if record["status"] == "AMBIGUOUS" and approved:
        raise _fail("companion_plan_blocked", "Ambiguous installation cannot be approved.")
    if record["status"] == "DECLINED" or (
        record["approval_required"] is True and not approved
    ):
        status = "DECLINED"
    elif record["approval_required"] is False:
        status = "NO_MUTATION_REQUIRED"
    else:
        status = "APPROVED_FOR_ADAPTER"
    value = {
        "format": "opencntx-integration-approval",
        "format_version": 1,
        "plan_digest": record["plan_digest"],
        "status": status,
        "adapter_execution_performed": False,
        "writes_performed": 0,
    }
    return value | {"approval_digest": _value_digest(value)}


def build_continuity_target(
    *,
    project_id: str,
    opt_in: bool,
    target_id: str | None = None,
    target_kind: str | None = None,
    allowed_content: Sequence[str] = (),
    direction: str = "PUSH_DERIVED",
    cadence: str = "VERIFIED_CHANGE",
    conflict_policy: str = "FAIL_CLOSED",
) -> dict[str, Any]:
    """Build an isolated target contract; actual destination access is adapter-owned."""
    project = _one_line(project_id, "project_id", 120)
    if not opt_in:
        value = {
            "format": "opencntx-continuity-target",
            "format_version": 1,
            "project_id": project,
            "enabled": False,
            "target_id": None,
            "target_kind": None,
            "allowed_content": [],
            "direction": None,
            "cadence": None,
            "conflict_policy": None,
            "local_canonical": True,
            "credentials_stored": False,
        }
        return value | {"target_digest": _value_digest(value)}
    target = _one_line(target_id, "target_id", 160) if target_id is not None else None
    kind = target_kind.upper() if target_kind is not None else ""
    if target is None or kind not in TARGET_KINDS:
        raise _fail("continuity_target_invalid", "Target identity or kind is invalid.")
    content = _bounded_unique(allowed_content, "allowed_content", maximum=30)
    selected_direction = direction.upper()
    selected_cadence = cadence.upper()
    selected_conflict = conflict_policy.upper()
    if (
        selected_direction not in DIRECTIONS
        or selected_cadence not in CADENCES
        or selected_conflict not in CONFLICT_POLICIES
    ):
        raise _fail("continuity_target_invalid", "Target policy is invalid.")
    value = {
        "format": "opencntx-continuity-target",
        "format_version": 1,
        "project_id": project,
        "enabled": True,
        "target_id": target,
        "target_kind": kind,
        "allowed_content": content,
        "direction": selected_direction,
        "cadence": selected_cadence,
        "conflict_policy": selected_conflict,
        "local_canonical": True,
        "credentials_stored": False,
    }
    return value | {"target_digest": _value_digest(value)}


def build_continuity_sync_batch(
    target: Mapping[str, object],
    *,
    expected_target_digest: str,
    project_id: str,
    changes: Sequence[Mapping[str, object]],
    online: bool,
    conflict: bool,
    max_records: int = 500,
) -> dict[str, Any]:
    """Filter a compact adapter batch while keeping local state authoritative."""
    record = _validate_digest(target, "target_digest", "continuity_target_stale")
    if record.get("format") != "opencntx-continuity-target":
        raise _fail("continuity_target_invalid", "Target format is invalid.")
    if record["target_digest"] != expected_target_digest:
        raise _fail("continuity_target_stale", "Target changed.")
    if record["project_id"] != project_id:
        raise _fail("continuity_target_isolation", "Target belongs to another project.")
    if not record["enabled"]:
        raise _fail("continuity_target_disabled", "Target is not enabled.")
    if isinstance(changes, (str, bytes)) or len(changes) > max_records:
        raise _fail("continuity_batch_invalid", "Sync batch exceeds its record budget.")
    allowed = set(record["allowed_content"])
    included: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    seen: set[str] = set()
    for change in changes:
        change_id = _one_line(change.get("change_id"), "change_id", 160)
        content_class = _one_line(change.get("content_class"), "content_class", 100)
        digest = _one_line(change.get("sha256"), "sha256", 64)
        byte_count = change.get("bytes")
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
            or change_id in seen
        ):
            raise _fail("continuity_batch_invalid", "Sync change is invalid or duplicate.")
        seen.add(change_id)
        if change.get("contains_secret") is True:
            excluded.append({"change_id": change_id, "reason": "SECRET_FILTERED"})
        elif content_class not in allowed:
            excluded.append({"change_id": change_id, "reason": "CONTENT_CLASS_BLOCKED"})
        else:
            included.append(
                {
                    "change_id": change_id,
                    "content_class": content_class,
                    "sha256": digest,
                    "bytes": byte_count,
                }
            )
    if conflict:
        status = "CONFLICT"
    elif not online:
        status = "QUEUED_OFFLINE"
    else:
        status = "READY_FOR_ADAPTER"
    value = {
        "format": "opencntx-continuity-sync-batch",
        "format_version": 1,
        "project_id": project_id,
        "target_digest": record["target_digest"],
        "status": status,
        "included": included,
        "excluded": excluded,
        "external_writes_performed": 0,
        "local_canonical": True,
    }
    return value | {"batch_digest": _value_digest(value)}
