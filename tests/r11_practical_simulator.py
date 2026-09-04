"""Bounded R11 practical simulation; not part of default test discovery."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from r10_complex_simulator import run as run_r10

from opencntx.adaptive_storage import build_storage_profile_plan
from opencntx.human_interface import build_intent_contract, intent_readback
from opencntx.optional_integrations import (
    build_companion_plan,
    build_continuity_sync_batch,
    build_continuity_target,
    build_onboarding_profile,
    build_start_authority_choice,
    resolve_start_authority_choice,
)
from opencntx.scale_assurance import build_assurance_plan, build_scale_plan
from opencntx.session_continuity import assess_session_rollover
from opencntx.transactional_update import (
    apply_update_plan,
    build_update_preview,
    update_postflight,
)


def _authority_matrix() -> dict[str, Any]:
    arguments = {
        "roadmap_id": "ROADMAP-A",
        "roadmap_revision": "REV-3",
        "current_assignment": "TASK-3",
        "remaining_assignments": ["TASK-3", "TASK-4", "TASK-5"],
        "roadmap_started": True,
        "language": "en",
    }
    interactive = build_start_authority_choice(
        **arguments, host_capabilities=["INTERACTIVE_CHOICE"]
    )
    command_line = build_start_authority_choice(**arguments, host_capabilities=[])
    interactive_authority = resolve_start_authority_choice(
        interactive,
        expected_choice_digest=interactive["choice_digest"],
        expected_roadmap_revision="REV-3",
        expected_current_assignment="TASK-3",
        submitted_value="REMAINING_ROADMAP",
    )
    command_authority = resolve_start_authority_choice(
        command_line,
        expected_choice_digest=command_line["choice_digest"],
        expected_roadmap_revision="REV-3",
        expected_current_assignment="TASK-3",
        submitted_value="AUTO PILOT ROADMAP-A",
    )
    if interactive_authority != command_authority:
        raise RuntimeError("Provider presentation changed authority semantics")
    if interactive_authority["release_authorized"]:
        raise RuntimeError("Roadmap authority unexpectedly included release")
    return {
        "approved_assignments": len(interactive_authority["approved_assignments"]),
        "authority_digest": interactive_authority["authority_digest"],
        "presentations": 2,
        "release_authorized": False,
    }


def _intent_and_rollover() -> dict[str, Any]:
    intent = build_intent_contract(
        human_intent="Keep the project going and show the next real assignment.",
        language="en",
        goal="Continue the bounded roadmap without losing the next assignment.",
        scope=["CURRENT_APPROVED_ROADMAP"],
        exclusions=["RELEASE", "PUBLICATION"],
        constraints=["HUMAN_SIMPLE_OUTPUT"],
        authority_state="APPROVED",
        risks=["SESSION_ROLLOVER"],
        definition_of_done=["STATE_READBACK_MATCHES"],
        next_internal_action="RUN_CURRENT_CHECK",
    )
    readback = intent_readback(intent)
    if readback["intent_digest"] != intent["intent_digest"]:
        raise RuntimeError("Human intent changed during readback")
    size_signal = assess_session_rollover({"chat_bytes": 31 * 1_048_576})
    provider_signal = assess_session_rollover({"context_percent": 80})
    unknown = assess_session_rollover({})
    if {size_signal["signal"], provider_signal["signal"]} != {"PREPARE_HANDOFF"}:
        raise RuntimeError("Provider rollover signals differ")
    if unknown["signal"] != "METRICS_UNAVAILABLE":
        raise RuntimeError("Missing metrics were guessed")
    return {
        "intent_digest": intent["intent_digest"],
        "known_provider_signals": 2,
        "missing_metrics": "METRICS_UNAVAILABLE",
        "rollover_signal": "PREPARE_HANDOFF",
    }


def _storage_matrix(root: Path) -> dict[str, Any]:
    measurements = {
        "TINY_LOCAL": {
            "object_count": 100,
            "total_bytes": 1_000_000,
            "monthly_change_bytes": 10_000,
            "queries_per_day": 3,
            "concurrent_writers": 1,
        },
        "LOCAL_INDEXED": {
            "object_count": 4_500,
            "total_bytes": 80_000_000,
            "monthly_change_bytes": 2_000_000,
            "queries_per_day": 200,
            "concurrent_writers": 1,
        },
        "LARGE_LOCAL": {
            "object_count": 300_000,
            "total_bytes": 6 * 1024**3,
            "monthly_change_bytes": 2 * 1024**3,
            "queries_per_day": 2_000,
            "concurrent_writers": 1,
        },
        "TEAM_SHARED": {
            "object_count": 20_000,
            "total_bytes": 500_000_000,
            "monthly_change_bytes": 100_000_000,
            "queries_per_day": 1_000,
            "concurrent_writers": 8,
        },
    }
    profiles: dict[str, str] = {}
    for expected, facts in measurements.items():
        project = root / expected.lower()
        project.mkdir()
        plan = build_storage_profile_plan(
            project,
            project_id=f"PROJECT-{expected}",
            current_profile="TINY_LOCAL",
            measurements=facts,
            soft_limit_bytes=10 * 1024**3,
            hard_limit_bytes=20 * 1024**3,
            rollback_reserve_bytes=1024**3,
        )
        profiles[expected] = plan["recommended_profile"]
        if plan["writes_performed"]:
            raise RuntimeError("Read-only storage recommendation wrote data")
    if any(name != value for name, value in profiles.items()):
        raise RuntimeError("Storage profile matrix chose an unsafe profile")
    return {"profiles": profiles, "writes_performed": 0}


def _scale_and_assurance() -> dict[str, Any]:
    request_classes = [
        {
            "name": "BASIC",
            "scope": "BASIC",
            "official_interface": True,
            "endpoint_proven": True,
            "cost_per_request": 1,
            "batch_size": 64,
            "payload_limit_bytes": 2_000_000,
            "ttl_seconds": 86_400,
            "storage_bytes_per_item": 128,
        },
        {
            "name": "DETAIL",
            "scope": "DETAIL",
            "official_interface": True,
            "endpoint_proven": True,
            "cost_per_request": 1,
            "batch_size": 64,
            "payload_limit_bytes": 2_000_000,
            "ttl_seconds": 86_400,
            "storage_bytes_per_item": 512,
        },
    ]
    scale = build_scale_plan(
        project_id="PROJECT-LARGE",
        identity_counts={
            "total_local": 4_509,
            "unique_external": 4_450,
            "missing_external": 20,
            "invalid_external": 10,
            "duplicate_links": 29,
            "fresh_cached": 50,
        },
        pilot_count=5,
        selective_depth_basis_points=500,
        request_classes=request_classes,
        quota_windows=[
            {"name": "DAY", "remaining": 10_000, "reserve": 500, "reset_at": "T+1D"}
        ],
    )
    if scale["status"] != "READY" or scale["pilot_status"] != "PILOT_ONLY":
        raise RuntimeError("Large scale plan hid pilot or quota state")
    tests = [
        {
            "test_id": "TARGETED",
            "covers": ["CORE"],
            "tier": "TARGETED",
            "read_only": True,
            "estimated_ms": 5,
        },
        {
            "test_id": "FULL",
            "covers": ["ALL"],
            "tier": "FULL",
            "read_only": True,
            "estimated_ms": 20,
        },
        {
            "test_id": "ROLLBACK",
            "covers": ["ALL"],
            "tier": "ROLLBACK",
            "read_only": False,
            "estimated_ms": 10,
        },
        {
            "test_id": "SECURITY",
            "covers": ["ALL"],
            "tier": "SECURITY",
            "read_only": True,
            "estimated_ms": 10,
        },
        {
            "test_id": "TERMINAL",
            "covers": ["ALL"],
            "tier": "TERMINAL",
            "read_only": True,
            "estimated_ms": 5,
        },
    ]
    assurance = build_assurance_plan(
        project_id="PROJECT-LARGE",
        changed_components=["CORE"],
        dependency_graph={"CORE": ["ADAPTER"]},
        test_manifest=tests,
        risk_axes={
            "impact": "MEDIUM",
            "newness": "NEW",
            "contract_change": True,
            "migration_change": False,
            "security_change": False,
            "remote_effect": False,
            "rollback": "TESTED",
            "concurrent_writers": 1,
        },
        terminal_boundary=True,
        estimates={"duration_ms": 100, "storage_bytes": 10_000, "model_units": 50},
    )
    if assurance["risk"] != "CRITICAL" or len(assurance["selected_tests"]) != len(tests):
        raise RuntimeError("Terminal assurance did not force the full matrix")
    return {
        "assurance": assurance["risk"],
        "network_requests_performed": scale["network_requests_performed"],
        "pilot_count": scale["pilot_count"],
        "scale_gates": scale["scale_gates"],
        "target_count": scale["target_count"],
    }


def _integration_matrix() -> dict[str, Any]:
    profile = build_onboarding_profile(
        project_id="PROJECT-A",
        project_scope="ALL_REGISTERED_PROJECTS",
        registered_projects=["PROJECT-A", "PROJECT-B"],
        selected_tools=["TOOL-A", "TOOL-B"],
        existing_method_detected=True,
        method_choice="PRESERVE_AND_LINK",
    )
    companion = build_companion_plan(
        onboarding=profile,
        requested=True,
        adapter_id="SPEC-ADAPTER",
        detection={
            "state": "COMPATIBLE",
            "provenance": "managed-runtime",
            "installed_version": "1.0",
            "projects_initialized": True,
        },
        target_version="1.0",
    )
    target = build_continuity_target(
        project_id="PROJECT-A",
        opt_in=True,
        target_id="TARGET-A",
        target_kind="SYNCED_FOLDER",
        allowed_content=["STATUS", "ROADMAP"],
        conflict_policy="CREATE_CONFLICT_COPY",
    )
    change = {
        "change_id": "STATUS-1",
        "content_class": "STATUS",
        "sha256": "a" * 64,
        "bytes": 100,
        "contains_secret": False,
    }
    offline = build_continuity_sync_batch(
        target,
        expected_target_digest=target["target_digest"],
        project_id="PROJECT-A",
        changes=[change],
        online=False,
        conflict=False,
    )
    conflict = build_continuity_sync_batch(
        target,
        expected_target_digest=target["target_digest"],
        project_id="PROJECT-A",
        changes=[change],
        online=True,
        conflict=True,
    )
    if companion["action"] != "VALIDATE":
        raise RuntimeError("Compatible companion was not reused")
    if {offline["status"], conflict["status"]} != {"QUEUED_OFFLINE", "CONFLICT"}:
        raise RuntimeError("Continuity adapter failure mode was unsafe")
    return {
        "companion_action": companion["action"],
        "existing_method": profile["method_choice"],
        "future_projects": profile["future_registered_projects"],
        "sync_states": [offline["status"], conflict["status"]],
        "writes_performed": 0,
    }


def _transactional_update(root: Path) -> dict[str, Any]:
    state = root / "update"
    state.mkdir()
    active = state / "active"
    candidate = state / "candidate"
    active.mkdir()
    candidate.mkdir()
    (active / "version.txt").write_text("old\n", encoding="utf-8")
    (active / "old-only.txt").write_text("retired\n", encoding="utf-8")
    (candidate / "version.txt").write_text("new\n", encoding="utf-8")
    (candidate / "new-only.txt").write_text("active\n", encoding="utf-8")
    plan = build_update_preview(
        state,
        from_version="1.0",
        to_version="2.0",
        components=[
            {
                "name": "RUNTIME",
                "active_path": str(active),
                "candidate_path": str(candidate),
                "from_format": "1",
                "to_format": "2",
            }
        ],
        target_context_version="2.0",
        target_companion_version="1.0",
        target_project_format="2",
        compatibility_matrix=[
            {
                "context_version": "2.0",
                "companion_version": "1.0",
                "project_format": "2",
            }
        ],
        changelog=["Synthetic safe update"],
        risks=["Injected interruption"],
    )
    receipt = apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
    postflight = update_postflight(plan)
    if receipt["status"] != "COMPLETED" or postflight["status"] != "GREEN":
        raise RuntimeError("Transactional update did not reach a green postflight")
    if (active / "old-only.txt").exists() or not (active / "new-only.txt").is_file():
        raise RuntimeError("Old active residue remained after update")
    return {
        "backup_verified": Path(str(receipt["backup_path"])).is_dir(),
        "old_active_residue": 0,
        "postflight": postflight["status"],
        "status": receipt["status"],
    }


def run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="opencntx-r11-practical-") as temporary:
        root = Path(temporary)
        result = {
            "authority": _authority_matrix(),
            "format": "opencntx-r11-practical-simulation",
            "format_version": 1,
            "integrations": _integration_matrix(),
            "intent_and_rollover": _intent_and_rollover(),
            "prior_complex_matrix": run_r10(),
            "scale_and_assurance": _scale_and_assurance(),
            "status": "PASS",
            "storage": _storage_matrix(root),
            "transactional_update": _transactional_update(root),
            "writes_to_real_project_maps": 0,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = run()
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
