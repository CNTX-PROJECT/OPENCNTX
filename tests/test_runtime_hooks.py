from __future__ import annotations

import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from tests.r9_conformance.project_runtime import RuntimeState
from tests.r9_conformance.runtime_contracts import canonical_digest, validate_runtime_record
from tests.r9_conformance.runtime_hooks import (
    ASSIGNMENT_33_PROPOSAL_SHA256,
    CASE_RESULT_CODES,
    CONTINUITY_EVENTS,
    SCENARIO_COUNT,
    SCENARIO_TABLE_SHA256,
    RuntimeHookError,
    build_current_assignment_package,
    evaluate_parking_lot_request,
    evaluate_runtime_hook,
    load_runtime_hook_corpus,
    restore_runtime_hook_context,
    run_runtime_hook_corpus,
    validate_runtime_hook_corpus,
    validate_runtime_hook_trace,
)
from tests.test_roadmap_runtime import runtime_records
from tests.test_runtime_contracts import DIGEST, samples

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "r9" / "assignment-33-runtime-hook-scenarios-v1.json"
SNAPSHOT = ROOT / "tests" / "fixtures" / "r9" / "assignment-33-opencntx-public-snapshot-v1.json"
ASSIGNMENT_29 = ROOT / "tests" / "fixtures" / "r9" / "assignment-29-scenarios-v1.json"
ASSIGNMENT_31 = ROOT / "tests" / "fixtures" / "r9" / "assignment-31-intake-scenarios-v1.json"
ASSIGNMENT_31_SNAPSHOT = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-31-opencntx-public-snapshot-v1.json"
)
ASSIGNMENT_32 = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-32-roadmap-runtime-scenarios-v1.json"
)
ASSIGNMENT_32_SNAPSHOT = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-32-opencntx-public-snapshot-v1.json"
)


def _git_blob_id(content: bytes) -> str:
    canonical = content.replace(b"\r\n", b"\n")
    header = f"blob {len(canonical)}\0".encode()
    return hashlib.sha1(header + canonical, usedforsecurity=False).hexdigest()


def governed_inputs() -> dict[str, object]:
    records = runtime_records()
    project = copy.deepcopy(records["project"])
    project["scale"] = "MEDIUM_PROJECT"
    pointer = copy.deepcopy(records["pointer"])
    actor = copy.deepcopy(records["actors"][1])
    workstream = copy.deepcopy(records["workstream"])
    state_value = {
        "actors": [
            {
                "actor_id": actor["actor_id"],
                "availability": actor["availability"],
                "role": actor["role"],
            }
        ],
        "conflicts": [],
        "current_leaf_id": pointer["current_leaf_id"],
        "event_count": 1,
        "event_head": pointer["event_head"],
        "facts": [],
        "mode": pointer["mode"],
        "project_id": project["project_id"],
        "roadmap_stack": pointer["roadmap_stack"],
        "status": "ACTIVE",
        "workstreams": [
            {
                "actor_id": actor["actor_id"],
                "current_leaf_id": pointer["current_leaf_id"],
                "workstream_id": workstream["workstream_id"],
            }
        ],
    }
    state = RuntimeState(
        project_id=project["project_id"],
        status="ACTIVE",
        mode=pointer["mode"],
        current_leaf_id=pointer["current_leaf_id"],
        roadmap_stack=tuple(copy.deepcopy(pointer["roadmap_stack"])),
        event_head=pointer["event_head"],
        event_count=1,
        actors=((actor["actor_id"], actor["role"], actor["availability"]),),
        workstreams=(
            (
                workstream["workstream_id"],
                actor["actor_id"],
                pointer["current_leaf_id"],
            ),
        ),
        conflicts=(),
        facts=(),
        state_digest=canonical_digest(state_value),
    )
    pointer["projected_state_digest"] = state.state_digest
    envelope = samples()["opencntx-action-envelope"]
    envelope.update(
        {
            "actor_id": actor["actor_id"],
            "allowed_actions": ["read-file", "write-file"],
            "allowed_paths": ["src/opencntx/runtime_hooks.py"],
            "budgets": {
                "max_actions": 10,
                "max_attempts": 3,
                "max_bytes": 262_144,
                "max_files": 40,
                "max_minutes": 150,
            },
            "current_leaf_id": pointer["current_leaf_id"],
            "evidence_requirements": ["FULL_TESTS", "TARGETED_TESTS"],
            "exact_stop": "R9_ASSIGNMENT_33_CANDIDATE_PROVEN",
            "input_digests": [DIGEST],
            "project_id": project["project_id"],
            "proposal_digest": ASSIGNMENT_33_PROPOSAL_SHA256,
            "protected_paths": ["src/opencntx/core.py"],
            "roadmap_stack_digest": canonical_digest(pointer["roadmap_stack"]),
            "rollback_boundary": "STOP_WITHOUT_CANONICAL_WRITE",
            "workstream_id": workstream["workstream_id"],
        }
    )
    leaf_contract = {
        "acceptance_criteria": ["All exact scenarios are green."],
        "allowed_tools": ["apply_patch", "python"],
        "assignment_id": pointer["current_leaf_id"],
        "assignment_revision": 1,
        "blockers": [],
        "definition_of_done": ["Pure runtime-hook facade proven."],
        "evidence": ["MAIN_CI_33242602782"],
        "goal": "Enforce runtime hooks and leaf-only context.",
        "interface_contracts": ["ROADMAP_GUARD", "RUNTIME_POINTER"],
    }
    selection = {
        "blocked": ["secrets"],
        "detail_markers": [],
        "excluded": ["src/opencntx/core.py"],
        "included": ["src/opencntx/runtime_hooks.py"],
        "total_bytes": 1024,
        "total_files": 1,
        "unread": ["docs/future.md"],
    }
    storage = samples()["opencntx-storage-policy"]
    storage.update(
        {
            "default_storage": "PRIVATE_GIT_SYNC",
            "private_branch": "mirror",
            "private_git_sync_enabled": True,
            "private_remote": "origin",
            "sync_types": ["json"],
        }
    )
    return {
        "actor": actor,
        "envelope": envelope,
        "leaf_contract": leaf_contract,
        "pointer": pointer,
        "project": project,
        "roadmaps": records["roadmaps"],
        "selection": selection,
        "state": state,
        "storage": storage,
        "workstream": workstream,
    }


def trace_for(trigger: str) -> list[str]:
    if trigger == "SESSION_OPEN":
        return ["SESSION_OPEN"]
    trace = ["SESSION_OPEN", "MESSAGE_RECEIVED"]
    if trigger == "MESSAGE_RECEIVED":
        return trace
    if trigger == "DRIFT_DETECTED":
        return trace + [trigger]
    trace.append("BEFORE_CONTEXT_BUILD")
    if trigger == "BEFORE_CONTEXT_BUILD":
        return trace
    trace.append("BEFORE_ACTION")
    if trigger == "BEFORE_ACTION":
        return trace
    if trigger == "AFTER_ACTION":
        return trace + [trigger]
    if trigger == "AFTER_SYNC":
        return trace + ["BEFORE_SYNC", trigger]
    if trigger == "RETURN_TO_PARENT":
        return trace + ["SUBROADMAP_CLOSED", trigger]
    return trace + [trigger]


class RuntimeHookTests(unittest.TestCase):
    def test_trace_is_ordered_bounded_and_deterministic(self) -> None:
        trace = trace_for("AFTER_ACTION")
        first = validate_runtime_hook_trace(trace)
        second = validate_runtime_hook_trace(tuple(trace))
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_trace_bypass_cases_fail_closed(self) -> None:
        cases = (
            [],
            ["UNKNOWN"],
            ["MESSAGE_RECEIVED"],
            ["SESSION_OPEN", "BEFORE_CONTEXT_BUILD"],
            ["SESSION_OPEN", "MESSAGE_RECEIVED", "BEFORE_ACTION"],
            ["SESSION_OPEN", "MESSAGE_RECEIVED", "AFTER_ACTION"],
            ["SESSION_OPEN", "MESSAGE_RECEIVED", "BEFORE_STORAGE_WRITE"],
            ["SESSION_OPEN", "MESSAGE_RECEIVED", "BEFORE_SYNC"],
            ["SESSION_OPEN", "MESSAGE_RECEIVED", "AFTER_SYNC"],
            ["SESSION_OPEN", "MESSAGE_RECEIVED", "RETURN_TO_PARENT"],
            ["SESSION_OPEN", "MESSAGE_RECEIVED", "DRIFT_DETECTED", "BEFORE_CONTEXT_BUILD"],
            trace_for("BEFORE_ACTION") + ["BEFORE_ACTION"],
            ["SESSION_OPEN"] * 257,
        )
        for trace in cases:
            with self.subTest(trace=trace), self.assertRaises(RuntimeHookError):
                validate_runtime_hook_trace(trace)

    def test_all_fourteen_hooks_are_guarded_and_write_free(self) -> None:
        data = governed_inputs()
        statuses = {}
        for trigger in sorted(
            {
                "SESSION_OPEN",
                "MESSAGE_RECEIVED",
                "BEFORE_CONTEXT_BUILD",
                "BEFORE_ACTION",
                "AFTER_ACTION",
                "BEFORE_STORAGE_WRITE",
                "BEFORE_SYNC",
                "AFTER_SYNC",
                "DONE_CANDIDATE",
                "OWNER_ACCEPTED",
                "NODE_CLOSED",
                "SUBROADMAP_CLOSED",
                "RETURN_TO_PARENT",
                "DRIFT_DETECTED",
            }
        ):
            state = data["state"]
            if trigger == "RETURN_TO_PARENT":
                state = replace(state, mode="RETURN_TO_PARENT")
            read_only = trigger in {
                "SESSION_OPEN",
                "MESSAGE_RECEIVED",
                "BEFORE_CONTEXT_BUILD",
            }
            decision = evaluate_runtime_hook(
                state=state,
                envelope=data["envelope"],
                trigger=trigger,
                action="read-file" if read_only else "write-file",
                actor_id=data["actor"]["actor_id"],
                trace=trace_for(trigger),
                target_path="src/opencntx/runtime_hooks.py",
                storage_policy=(
                    data["storage"] if trigger in {"BEFORE_SYNC", "AFTER_SYNC"} else None
                ),
            )
            statuses[trigger] = decision.status
            self.assertEqual(decision.writes, ())
            self.assertIn("HOOK_TRACE_VALID", decision.checks)
            self.assertRegex(decision.decision_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(statuses["SESSION_OPEN"], "READ_ONLY_ONLY")
        self.assertEqual(statuses["BEFORE_ACTION"], "ALLOW_EXACT_ACTION")
        self.assertEqual(statuses["DRIFT_DETECTED"], "BLOCKED_ROADMAP_DRIFT")

    def test_hook_trace_head_and_guard_blocks_remain_fail_closed(self) -> None:
        data = governed_inputs()
        with self.assertRaises(RuntimeHookError):
            evaluate_runtime_hook(
                state=data["state"],
                envelope=data["envelope"],
                trigger="BEFORE_ACTION",
                action="write-file",
                actor_id=data["actor"]["actor_id"],
                trace=trace_for("AFTER_ACTION"),
            )
        blocked = evaluate_runtime_hook(
            state=data["state"],
            envelope=data["envelope"],
            trigger="BEFORE_ACTION",
            action="delete-file",
            actor_id=data["actor"]["actor_id"],
            trace=trace_for("BEFORE_ACTION"),
        )
        self.assertEqual(blocked.status, "BLOCKED_ACTION_OUTSIDE_CURRENT_ASSIGNMENT")

    def test_current_assignment_package_is_complete_deterministic_and_valid(self) -> None:
        data = governed_inputs()
        arguments = {
            "state": data["state"],
            "project": data["project"],
            "pointer": data["pointer"],
            "actor": data["actor"],
            "workstream": data["workstream"],
            "envelope": data["envelope"],
            "leaf_contract": data["leaf_contract"],
            "context_selection": data["selection"],
        }
        first = build_current_assignment_package(**arguments)
        second = build_current_assignment_package(**copy.deepcopy(arguments))
        self.assertEqual(first, second)
        self.assertEqual(first.status, "CURRENT_ASSIGNMENT_PACKAGE_VALID")
        self.assertEqual(first.writes, ())
        self.assertEqual(first.package_digest, second.package_digest)
        self.assertEqual(first.projection_digest, second.projection_digest)
        self.assertEqual(first.leaf_package["assignment_id"], data["state"].current_leaf_id)
        self.assertNotIn("goal", json.loads(first.breadcrumb))
        validate_runtime_record(first.context_projection)

    def test_all_scale_boundaries_are_exact(self) -> None:
        data = governed_inputs()
        boundaries = {
            "TINY_TASK": (15, 65_536),
            "SMALL_PROJECT": (25, 131_072),
            "MEDIUM_PROJECT": (40, 262_144),
            "LARGE_PROJECT": (60, 524_288),
            "MEGA_PROJECT": (80, 1_048_576),
        }
        for scale, (files, size) in boundaries.items():
            project = copy.deepcopy(data["project"])
            project["scale"] = scale
            selection = copy.deepcopy(data["selection"])
            selection["total_files"] = files
            selection["total_bytes"] = size
            result = build_current_assignment_package(
                state=data["state"],
                project=project,
                pointer=data["pointer"],
                actor=data["actor"],
                workstream=data["workstream"],
                envelope=data["envelope"],
                leaf_contract=data["leaf_contract"],
                context_selection=selection,
            )
            self.assertEqual(result.context_projection["max_files"], files)
            self.assertEqual(result.context_projection["max_bytes"], size)

    def test_parent_fragment_is_single_bounded_digest_bound_and_temporary(self) -> None:
        data = governed_inputs()
        fragment = {
            "bytes": 32_768,
            "expires_at": "9999",
            "path": "parent/phase.md",
            "reason": "Required interface contract.",
            "sha256": DIGEST,
        }
        result = build_current_assignment_package(
            state=data["state"],
            project=data["project"],
            pointer=data["pointer"],
            actor=data["actor"],
            workstream=data["workstream"],
            envelope=data["envelope"],
            leaf_contract=data["leaf_contract"],
            context_selection=data["selection"],
            parent_fragments=[fragment],
            allowed_parent_paths=["parent/phase.md"],
            current_marker="2026",
        )
        self.assertEqual(result.context_projection["justified_parent_fragment"], fragment)
        cases = (
            {"parent_fragments": [fragment, fragment]},
            {"parent_fragments": [fragment | {"bytes": 32_769}]},
            {"parent_fragments": [fragment | {"path": "sibling/phase.md"}]},
            {"parent_fragments": [fragment | {"expires_at": "2025"}]},
            {"parent_fragments": [fragment | {"sha256": "bad"}]},
            {"parent_fragments": [fragment | {"reason": ""}]},
        )
        base = {
            "state": data["state"],
            "project": data["project"],
            "pointer": data["pointer"],
            "actor": data["actor"],
            "workstream": data["workstream"],
            "envelope": data["envelope"],
            "leaf_contract": data["leaf_contract"],
            "context_selection": data["selection"],
            "allowed_parent_paths": ["parent/phase.md"],
            "current_marker": "2026",
        }
        for override in cases:
            with self.subTest(override=override), self.assertRaises(RuntimeHookError):
                build_current_assignment_package(**(base | override))

    def test_binding_leaf_selection_and_budget_mismatches_block(self) -> None:
        data = governed_inputs()
        base = {
            "state": data["state"],
            "project": data["project"],
            "pointer": data["pointer"],
            "actor": data["actor"],
            "workstream": data["workstream"],
            "envelope": data["envelope"],
            "leaf_contract": data["leaf_contract"],
            "context_selection": data["selection"],
        }
        overrides = []
        project = copy.deepcopy(data["project"])
        project["project_id"] = "OTHER_PROJECT"
        overrides.append({"project": project})
        pointer = copy.deepcopy(data["pointer"])
        pointer["projected_state_digest"] = "9" * 64
        overrides.append({"pointer": pointer})
        actor = copy.deepcopy(data["actor"])
        actor["availability"] = "UNAVAILABLE"
        overrides.append({"actor": actor})
        leaf = copy.deepcopy(data["leaf_contract"])
        leaf["assignment_id"] = "OTHER_ASSIGNMENT"
        overrides.append({"leaf_contract": leaf})
        leaf = copy.deepcopy(data["leaf_contract"])
        leaf.pop("goal")
        overrides.append({"leaf_contract": leaf})
        envelope = copy.deepcopy(data["envelope"])
        envelope["protected_paths"] = list(envelope["allowed_paths"])
        overrides.append({"envelope": envelope})
        project = copy.deepcopy(data["project"])
        project["scale"] = "UNRESOLVED"
        overrides.append({"project": project})
        selection = copy.deepcopy(data["selection"])
        selection["total_files"] = 41
        overrides.append({"context_selection": selection})
        selection = copy.deepcopy(data["selection"])
        selection["total_bytes"] = 262_145
        overrides.append({"context_selection": selection})
        selection = copy.deepcopy(data["selection"])
        selection["detail_markers"] = ["SIBLING_DETAIL"]
        overrides.append({"context_selection": selection})
        for override in overrides:
            with self.subTest(keys=tuple(override)), self.assertRaises(RuntimeHookError):
                build_current_assignment_package(**(base | override))

    def test_every_forbidden_detail_marker_blocks(self) -> None:
        data = governed_inputs()
        markers = {
            "FULL_MAIN_ROADMAP",
            "SIBLING_DETAIL",
            "FUTURE_DETAIL",
            "OTHER_TEAM_LEAF",
            "OLD_CHAT",
            "BROAD_EVIDENCE",
            "FULL_MEM_DIRECTORY",
            "FULL_OBSIDIAN_DIRECTORY",
            "UNAUTHORIZED_PARKING_ITEM",
        }
        for marker in markers:
            selection = copy.deepcopy(data["selection"])
            selection["detail_markers"] = [marker]
            with self.subTest(marker=marker), self.assertRaises(RuntimeHookError):
                build_current_assignment_package(
                    state=data["state"],
                    project=data["project"],
                    pointer=data["pointer"],
                    actor=data["actor"],
                    workstream=data["workstream"],
                    envelope=data["envelope"],
                    leaf_contract=data["leaf_contract"],
                    context_selection=selection,
                )

    def test_parking_lot_is_owner_only_in_memory_and_state_preserving(self) -> None:
        data = governed_inputs()
        owner = evaluate_parking_lot_request(
            state=data["state"],
            actor_role="OWNER",
            item="Consider a later documentation improvement.",
            owner_instruction_digest=DIGEST,
        )
        self.assertEqual(owner.status, "PARKING_LOT_OWNER_AUTHORIZED")
        self.assertEqual(owner.writes, ())
        self.assertEqual(owner.source_state_digest, owner.resulting_state_digest)
        for role, digest in (("ARCHITECT", DIGEST), ("OWNER", None), ("EXECUTOR", None)):
            blocked = evaluate_parking_lot_request(
                state=data["state"],
                actor_role=role,
                item="Not owner authorized.",
                owner_instruction_digest=digest,
            )
            self.assertEqual(blocked.status, "BLOCKED_OWNER_ONLY_PARKING_LOT")
            self.assertEqual(blocked.writes, ())
        with self.assertRaises(RuntimeHookError):
            evaluate_parking_lot_request(
                state=data["state"],
                actor_role="OWNER",
                item="",
                owner_instruction_digest=DIGEST,
            )

    def test_restart_model_compaction_and_team_handoff_restore_sticky_leaf(self) -> None:
        data = governed_inputs()
        for event in sorted(CONTINUITY_EVENTS):
            result = restore_runtime_hook_context(
                state=data["state"],
                pointer=data["pointer"],
                roadmaps=data["roadmaps"],
                target_actor=data["actor"],
                target_workstream=data["workstream"],
                continuity_event=event,
            )
            expected = (
                "TEAM_HANDOFF_CONTEXT_RESTORED"
                if event == "TEAM_HANDOFF"
                else "STICKY_LEAF_RESTORED"
            )
            self.assertEqual(result["status"], expected)
            self.assertEqual(result["current_leaf_id"], data["state"].current_leaf_id)
            self.assertEqual(result["writes"], [])
        unavailable = copy.deepcopy(data["actor"])
        unavailable["availability"] = "UNAVAILABLE"
        with self.assertRaises(RuntimeHookError):
            restore_runtime_hook_context(
                state=data["state"],
                pointer=data["pointer"],
                roadmaps=data["roadmaps"],
                target_actor=unavailable,
                target_workstream=data["workstream"],
                continuity_event="TEAM_HANDOFF",
            )
        with self.assertRaises(RuntimeHookError):
            restore_runtime_hook_context(
                state=data["state"],
                pointer=data["pointer"],
                roadmaps=data["roadmaps"],
                target_actor=data["actor"],
                target_workstream=data["workstream"],
                continuity_event="UNKNOWN",
            )

    def test_exact_96_case_corpus_is_model_free_and_write_free(self) -> None:
        corpus = load_runtime_hook_corpus(FIXTURE.read_bytes())
        result = run_runtime_hook_corpus(corpus)
        self.assertEqual(len(CASE_RESULT_CODES), SCENARIO_COUNT)
        self.assertEqual(result.scenario_count, 96)
        self.assertEqual(result.passed, 96)
        self.assertEqual(result.failed, 0)
        self.assertTrue(all(item.writes == () for item in result.results))
        self.assertRegex(result.result_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(corpus["table_digest"], SCENARIO_TABLE_SHA256)

    def test_corpus_rejects_count_ids_expected_values_writes_and_metadata_drift(self) -> None:
        corpus = load_runtime_hook_corpus(FIXTURE.read_bytes())
        mutations = []
        missing = copy.deepcopy(corpus)
        missing["records"].pop()
        mutations.append(missing)
        duplicate = copy.deepcopy(corpus)
        duplicate["records"][1]["scenario_id"] = "S33-001"
        mutations.append(duplicate)
        expected = copy.deepcopy(corpus)
        expected["records"][0]["expected_result_code"] = "WRONG"
        mutations.append(expected)
        writes = copy.deepcopy(corpus)
        writes["records"][0]["expected_writes"] = ["write"]
        mutations.append(writes)
        metadata = copy.deepcopy(corpus)
        metadata["table_digest"] = "0" * 64
        mutations.append(metadata)
        extra = copy.deepcopy(corpus)
        extra["unknown"] = True
        mutations.append(extra)
        binding = copy.deepcopy(corpus)
        binding["records"][0]["input"]["bindings_digest"] = "0" * 64
        mutations.append(binding)
        for mutation in mutations:
            with self.subTest(keys=tuple(mutation)), self.assertRaises(RuntimeHookError):
                validate_runtime_hook_corpus(mutation)

    def test_strict_json_rejects_duplicate_non_nfc_constant_utf8_and_non_object(self) -> None:
        cases = (
            b'{"format":"x","format":"y"}',
            '{"value":"e\u0301"}'.encode(),
            b'{"value":NaN}',
            b"\xff",
            b"[]",
        )
        for content in cases:
            with self.subTest(content=content), self.assertRaises(RuntimeHookError):
                load_runtime_hook_corpus(content)

    def test_snapshot_and_all_previous_r9_bytes_are_frozen(self) -> None:
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["commit"], "02e14a23d28c1a9b0795f48e3056962f2f094f85")
        self.assertEqual(snapshot["tree"], "e61c5de10ad38e4a9a1df5775687cedce7a83a38")
        self.assertEqual(snapshot["file_count"], 201)
        self.assertEqual(snapshot["total_blob_bytes"], 4_003_027)
        self.assertEqual(snapshot["relevant_path_count"], 25)
        frozen = {
            ASSIGNMENT_29: "220d6ea7f3c0fbd0d84ee054e2f904bbfa0f21dc",
            ASSIGNMENT_31: "e25c3ccec031e3ff938d0dcaa1eb7ec0bcb3991b",
            ASSIGNMENT_31_SNAPSHOT: "9bf13af2caf13697a5549f9c8a34391f8f20a03c",
            ASSIGNMENT_32: "c6474f90cb0b1869d83130469417e4287ddf57eb",
            ASSIGNMENT_32_SNAPSHOT: "53fe93ac779f6573572f8d53b99c9591e05c39ee",
        }
        for path, expected_blob in frozen.items():
            self.assertEqual(_git_blob_id(path.read_bytes()), expected_blob)

    def test_runtime_hook_module_has_no_external_integration_or_openspec_route(self) -> None:
        source = (ROOT / "tests" / "r9_conformance" / "runtime_hooks.py").read_text(
            encoding="utf-8"
        )
        lowered = source.lower()
        for marker in (
            "from pathlib",
            "import os",
            "import socket",
            "import subprocess",
            "import urllib",
            "import requests",
            "import openspec",
            ".openspec-store",
        ):
            self.assertNotIn(marker, lowered)
        self.assertNotIn("open(", source)
        self.assertNotIn("Path(", source)


if __name__ == "__main__":
    unittest.main()
