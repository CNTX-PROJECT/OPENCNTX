from __future__ import annotations

import copy
import unittest

from opencntx.lifecycle import r9_schema_assets, r9_schema_bundle_digest, schema_assets
from opencntx.runtime_contracts import (
    FORMAT_TO_SCHEMA,
    RuntimeContractError,
    canonical_digest,
    canonical_json_bytes,
    load_json_record,
    runtime_schema_bundle_digest,
    runtime_schema_catalog,
    schema_identifier,
    validate_runtime_record,
)

DIGEST = "a" * 64
ZERO = "0" * 64


def _base(format_name: str, record_id: str) -> dict[str, object]:
    return {
        "format": format_name,
        "format_version": 1,
        "schema_id": schema_identifier(format_name),
        "record_id": record_id,
        "project_id": "PROJECT_R9",
        "revision": 1,
    }


def samples() -> dict[str, dict[str, object]]:
    project = _base("opencntx-project-definition", "PROJECT_DEFINITION_R1") | {
        "project_mode": "EXISTING_ASSIST",
        "project_scope": "FULL_PROJECT",
        "scale": "MEDIUM_PROJECT",
        "collaboration_mode": "SOLO",
        "declared_human_count": 1,
        "declared_ai_worker_slots": 1,
        "owner_actor_id": "ACTOR_OWNER",
        "parent_project_id": None,
        "goal": "Build the isolated runtime foundation.",
        "non_goals": ["activate-runtime"],
        "source_count": 26,
        "assignment_count": 9,
        "dependency_depth": 3,
        "system_count": 3,
    }
    actor = _base("opencntx-actor-binding", "ACTOR_BINDING_OWNER_R1") | {
        "actor_id": "ACTOR_OWNER",
        "role": "OWNER",
        "workstream_id": None,
        "capacity": 100,
        "availability": "AVAILABLE",
    }
    roadmap = _base("opencntx-roadmap-definition", "ROADMAP_DEFINITION_MAIN_R1") | {
        "roadmap_id": "ROADMAP_MAIN",
        "roadmap_type": "MAIN_ROADMAP",
        "parent_roadmap_id": None,
        "parent_node_id": None,
        "return_node_id": None,
        "nodes": [
            {
                "node_id": "ASSIGNMENT_30",
                "node_type": "ASSIGNMENT",
                "status": "ACTIVE",
                "title": "Runtime foundation",
            },
            {
                "node_id": "PHASE_A",
                "node_type": "PHASE",
                "status": "ACTIVE",
                "title": "Foundation",
            },
        ],
        "relations": [{"from": "PHASE_A", "to": "ASSIGNMENT_30", "type": "PARENT_OF"}],
        "definition_of_done": ["all-scenarios-pass"],
        "event_head": ZERO,
    }
    workstream = _base("opencntx-workstream-binding", "WORKSTREAM_BINDING_MAIN_R1") | {
        "workstream_id": "WORKSTREAM_MAIN",
        "actor_id": "ACTOR_ARCHITECT",
        "roadmap_id": "ROADMAP_MAIN",
        "current_leaf_id": "ASSIGNMENT_30",
        "max_parallelism": 1,
        "resource_claim_ids": ["CLAIM_SOURCE"],
    }
    resource = _base("opencntx-resource-claim", "RESOURCE_CLAIM_SOURCE_R1") | {
        "claim_id": "CLAIM_SOURCE",
        "resource_ids": ["RESOURCE_SOURCE"],
        "conflict_set_ids": ["CONFLICT_SOURCE"],
        "exclusive": True,
    }
    envelope = _base("opencntx-action-envelope", "ACTION_ENVELOPE_30_R1") | {
        "envelope_id": "ENVELOPE_30",
        "actor_id": "ACTOR_ARCHITECT",
        "workstream_id": "WORKSTREAM_MAIN",
        "current_leaf_id": "ASSIGNMENT_30",
        "roadmap_stack_digest": DIGEST,
        "proposal_digest": DIGEST,
        "input_digests": [DIGEST],
        "allowed_actions": ["write-file"],
        "allowed_paths": ["src/opencntx/runtime_contracts.py"],
        "protected_paths": ["src/opencntx/core.py"],
        "evidence_requirements": ["tests-green"],
        "budgets": {
            "max_actions": 60,
            "max_attempts": 2,
            "max_bytes": 1_048_576,
            "max_files": 21,
            "max_minutes": 90,
        },
        "exact_stop": "AWAITING_OWNER_DECISION",
        "rollback_boundary": "candidate-worktree-only",
    }
    event = _base("opencntx-runtime-event", "RUNTIME_EVENT_0001") | {
        "event_id": "EVENT_0001",
        "event_number": 1,
        "event_type": "PROJECT_PROPOSED",
        "actor_id": "ACTOR_ARCHITECT",
        "actor_role": "ARCHITECT",
        "created_at": "2026-08-28T00:00:00Z",
        "previous_record_digest": ZERO,
        "to_status": "UNBOUND",
        "payload": {"project_definition_digest": canonical_digest(project)},
    }
    evidence = _base("opencntx-evidence", "EVIDENCE_TEST_R1") | {
        "evidence_id": "EVIDENCE_TEST",
        "evidence_type": "TEST_RESULT",
        "source_class": "LOCAL_VALIDATOR",
        "locator": "tests/test_runtime_contracts.py",
        "bytes": 10,
        "sha256": DIGEST,
        "captured_at": "2026-08-28T00:00:00Z",
        "freshness": "CURRENT",
        "validator": "unittest",
        "validator_version": "1",
        "result": "PASS",
        "limitations": ["local-only"],
        "state_digest": DIGEST,
        "input_digests": [DIGEST],
    }
    policy = _base("opencntx-storage-policy", "STORAGE_POLICY_LOCAL_R1") | {
        "policy_id": "POLICY_LOCAL",
        "default_storage": "LOCAL_CANONICAL",
        "private_git_sync_enabled": False,
        "private_remote": None,
        "private_branch": None,
        "sync_types": ["JSON"],
        "max_file_bytes": 10 * 1024**2,
        "max_batch_files": 100,
        "max_batch_bytes": 50 * 1024**2,
        "max_repository_bytes": 1024**3,
        "local_only_media": ["BINARY"],
        "excluded_classes": ["SECRET"],
    }
    frame = {
        "active_node_id": "ASSIGNMENT_30",
        "event_head": DIGEST,
        "policy_digest": DIGEST,
        "projection_digest": DIGEST,
        "return_node_id": None,
        "roadmap_id": "ROADMAP_MAIN",
        "roadmap_revision": 1,
        "schema_digest": DIGEST,
    }
    pointer = _base("opencntx-runtime-pointer", "RUNTIME_POINTER_R1") | {
        "pointer_id": "POINTER_MAIN",
        "mode": "LOCKED_EXECUTION",
        "main_roadmap_id": "ROADMAP_MAIN",
        "roadmap_stack": [frame],
        "current_leaf_id": "ASSIGNMENT_30",
        "event_head": DIGEST,
        "schema_digest": DIGEST,
        "policy_digest": DIGEST,
        "projected_state_digest": DIGEST,
        "expected_previous_digest": ZERO,
    }
    projection = _base("opencntx-context-projection", "CONTEXT_PROJECTION_R1") | {
        "projection_id": "PROJECTION_CURRENT",
        "current_leaf_id": "ASSIGNMENT_30",
        "roadmap_stack_digest": DIGEST,
        "included": ["CONTROL/CURRENT.md"],
        "excluded": ["CONTROL/ROADMAP.md"],
        "unread": ["CHAPTERS/history.md"],
        "blocked": [],
        "max_files": 40,
        "max_bytes": 262_144,
        "total_files": 1,
        "total_bytes": 100,
        "breadcrumb": "Project: PROJECT_R9",
        "justified_parent_fragment": None,
        "source_state_digest": DIGEST,
        "projection_digest": DIGEST,
    }
    receipt = _base("opencntx-sync-receipt", "SYNC_RECEIPT_R1") | {
        "sync_id": "SYNC_0001",
        "policy_digest": DIGEST,
        "preview_digest": DIGEST,
        "base_commit": None,
        "result": "POLICY_BLOCKED",
        "file_count": 0,
        "byte_count": 0,
        "commit": None,
        "remote_readback_digest": None,
        "conflicts": ["sync-disabled"],
    }
    return {
        record["format"]: record
        for record in (
            project,
            actor,
            roadmap,
            workstream,
            resource,
            envelope,
            event,
            evidence,
            policy,
            pointer,
            projection,
            receipt,
        )
    }


class RuntimeContractTests(unittest.TestCase):
    def test_exact_twelve_schemas_are_unique_packaged_and_separate(self) -> None:
        catalog = runtime_schema_catalog()
        self.assertEqual(set(catalog), set(FORMAT_TO_SCHEMA))
        self.assertEqual(len(catalog), 12)
        self.assertEqual(len({schema.schema_id for schema in catalog.values()}), 12)
        self.assertEqual(set(r9_schema_assets()), set(FORMAT_TO_SCHEMA.values()))
        self.assertEqual(len(schema_assets()), 6)
        self.assertRegex(runtime_schema_bundle_digest(), r"^[0-9a-f]{64}$")
        self.assertRegex(r9_schema_bundle_digest(), r"^[0-9a-f]{64}$")

    def test_one_positive_record_for_every_runtime_family(self) -> None:
        records = samples()
        self.assertEqual(len(records), 12)
        for format_name, record in records.items():
            with self.subTest(format_name=format_name):
                self.assertIs(validate_runtime_record(record), record)
                self.assertRegex(canonical_digest(record), r"^[0-9a-f]{64}$")

    def test_canonical_bytes_are_deterministic_and_key_order_independent(self) -> None:
        record = samples()["opencntx-project-definition"]
        reversed_record = dict(reversed(list(record.items())))
        self.assertEqual(canonical_json_bytes(record), canonical_json_bytes(reversed_record))
        self.assertEqual(canonical_digest(record), canonical_digest(reversed_record))

    def test_unknown_field_unknown_major_and_wrong_schema_fail_closed(self) -> None:
        record = samples()["opencntx-project-definition"]
        for field, value, code in (
            ("unexpected", True, "runtime_contract_fields_invalid"),
            ("format_version", 2, "runtime_contract_version_unsupported"),
            (
                "schema_id",
                "urn:uuid:00000000-0000-0000-0000-000000000000",
                "runtime_contract_schema_invalid",
            ),
        ):
            candidate = copy.deepcopy(record)
            candidate[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeContractError) as raised:
                validate_runtime_record(candidate)
            self.assertEqual(raised.exception.code, code)

    def test_duplicate_json_key_non_finite_and_non_nfc_fail_closed(self) -> None:
        with self.assertRaises(RuntimeContractError) as duplicate:
            load_json_record(b'{"format":"x","format":"y"}')
        self.assertEqual(duplicate.exception.code, "runtime_contract_duplicate_key")
        with self.assertRaises(RuntimeContractError) as constant:
            load_json_record(b'{"value":NaN}')
        self.assertEqual(constant.exception.code, "runtime_contract_json_invalid")
        record = samples()["opencntx-project-definition"]
        record["goal"] = "Cafe\u0301"
        with self.assertRaises(RuntimeContractError) as nfc:
            validate_runtime_record(record)
        self.assertEqual(nfc.exception.code, "runtime_contract_text_invalid")

    def test_sorted_unique_fields_and_storage_limits_are_enforced(self) -> None:
        project = samples()["opencntx-project-definition"]
        project["non_goals"] = ["z", "a"]
        with self.assertRaises(RuntimeContractError) as ordering:
            validate_runtime_record(project)
        self.assertEqual(ordering.exception.code, "runtime_contract_order_invalid")
        policy = samples()["opencntx-storage-policy"]
        policy["max_file_bytes"] = 10 * 1024**2 + 1
        with self.assertRaises(RuntimeContractError) as budget:
            validate_runtime_record(policy)
        self.assertEqual(budget.exception.code, "runtime_contract_field_invalid")

    def test_partial_scope_and_collaboration_mismatch_fail_closed(self) -> None:
        project = samples()["opencntx-project-definition"]
        project["project_scope"] = "SUBPROJECT"
        with self.assertRaises(RuntimeContractError) as parent:
            validate_runtime_record(project)
        self.assertEqual(parent.exception.code, "runtime_contract_binding_invalid")
        project = samples()["opencntx-project-definition"]
        project["collaboration_mode"] = "TEAM"
        with self.assertRaises(RuntimeContractError) as team:
            validate_runtime_record(project)
        self.assertEqual(team.exception.code, "runtime_contract_binding_invalid")


if __name__ == "__main__":
    unittest.main()
