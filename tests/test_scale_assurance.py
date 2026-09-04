from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from opencntx.scale_assurance import (
    acquisition_queue_status,
    assurance_receipt_reusable,
    build_assurance_plan,
    build_assurance_receipt,
    build_scale_plan,
    claim_acquisition_batch,
    classify_assurance_risk,
    complete_acquisition_batch,
    initialize_acquisition_queue,
)
from opencntx.workspace import WorkspaceError

ROOT = Path(__file__).resolve().parents[1]


def request_classes(*, proven: bool = True) -> list[dict[str, object]]:
    return [
        {
            "name": "BASIC-CARD",
            "scope": "BASIC",
            "official_interface": True,
            "endpoint_proven": proven,
            "cost_per_request": 1,
            "batch_size": 64,
            "payload_limit_bytes": 2_000_000,
            "ttl_seconds": 86_400,
            "storage_bytes_per_item": 128,
        },
        {
            "name": "DETAIL-CARD",
            "scope": "DETAIL",
            "official_interface": True,
            "endpoint_proven": proven,
            "cost_per_request": 1,
            "batch_size": 64,
            "payload_limit_bytes": 2_000_000,
            "ttl_seconds": 86_400,
            "storage_bytes_per_item": 512,
        },
    ]


def scale_plan(
    total: int,
    *,
    pilot: int = 5,
    missing: int = 0,
    invalid: int = 0,
    duplicates: int = 0,
    fresh: int = 0,
    proven: bool = True,
    quota: int = 100_000,
) -> dict[str, object]:
    unique = total - missing - invalid - duplicates
    return build_scale_plan(
        project_id="PROJECT-A",
        identity_counts={
            "total_local": total,
            "unique_external": unique,
            "missing_external": missing,
            "invalid_external": invalid,
            "duplicate_links": duplicates,
            "fresh_cached": fresh,
        },
        pilot_count=min(pilot, unique),
        selective_depth_basis_points=500,
        request_classes=request_classes(proven=proven),
        quota_windows=[
            {"name": "HOUR", "remaining": quota, "reserve": 10, "reset_at": "T+1H"},
            {"name": "DAY", "remaining": quota, "reserve": 10, "reset_at": "T+1D"},
        ],
    )


def risk_axes(**overrides: object) -> dict[str, object]:
    return {
        "impact": "LOW",
        "newness": "KNOWN",
        "contract_change": False,
        "migration_change": False,
        "security_change": False,
        "remote_effect": False,
        "rollback": "TRIVIAL",
        "concurrent_writers": 1,
    } | overrides


def assurance_manifest() -> list[dict[str, object]]:
    return [
        {"test_id": "T-CORE", "covers": ["CORE"], "tier": "TARGETED", "read_only": True, "estimated_ms": 5},
        {"test_id": "T-API", "covers": ["API"], "tier": "TARGETED", "read_only": True, "estimated_ms": 5},
        {"test_id": "T-FULL", "covers": ["ALL"], "tier": "FULL", "read_only": True, "estimated_ms": 20},
        {"test_id": "T-ROLLBACK", "covers": ["ALL"], "tier": "ROLLBACK", "read_only": False, "estimated_ms": 10},
        {"test_id": "T-SECURITY", "covers": ["ALL"], "tier": "SECURITY", "read_only": True, "estimated_ms": 10},
        {"test_id": "T-TERMINAL", "covers": ["ALL"], "tier": "TERMINAL", "read_only": True, "estimated_ms": 5},
    ]


class ScaleAssuranceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def assurance(self, axes: dict[str, object], terminal: bool = False) -> dict[str, object]:
        return build_assurance_plan(
            project_id="PROJECT-A",
            changed_components=["CORE"],
            dependency_graph={"CORE": ["API"], "API": ["DOCS"]},
            test_manifest=assurance_manifest(),
            risk_axes=axes,
            terminal_boundary=terminal,
            estimates={"duration_ms": 100, "storage_bytes": 2_000, "model_units": 50},
        )

    def test_scale_gates_cover_zero_ten_hundred_thousand_and_large_target(self) -> None:
        for target in (0, 10, 100, 1_000, 4_509):
            with self.subTest(target=target):
                plan = scale_plan(target, pilot=0 if target == 0 else 5)
                self.assertEqual(plan["target_count"], target)
                self.assertEqual(plan["scale_gates"][-1], target)
                self.assertEqual(plan["network_requests_performed"], 0)
        large = scale_plan(4_509, missing=20, invalid=10, duplicates=37, fresh=5)
        self.assertEqual(large["pilot_ratio"], {"numerator": 5, "denominator": 4_509})
        self.assertEqual(large["pilot_status"], "PILOT_ONLY")
        self.assertEqual(large["review_required_count"], 30)
        self.assertGreater(large["worst_case_requests"], 0)

    def test_unproven_interface_and_quota_reserve_block_before_network(self) -> None:
        unproven = scale_plan(4_000, proven=False)
        self.assertEqual(unproven["status"], "BLOCKED")
        self.assertIn("OFFICIAL_INTERFACE_PROOF_REQUIRED", unproven["blockers"])
        quota = scale_plan(4_000, quota=20)
        self.assertEqual(quota["status"], "BLOCKED")
        self.assertIn("QUOTA_RESERVE_WOULD_BE_CROSSED", quota["blockers"])
        self.assertEqual(quota["network_requests_performed"], 0)

    def test_queue_rejects_duplicate_external_identity_before_write(self) -> None:
        root = self.root / "duplicate"
        root.mkdir()
        plan = scale_plan(2)
        identities = [
            {"local_id": "LOCAL-1", "external_id": "EXT-1", "fingerprint": "a", "fresh": False},
            {"local_id": "LOCAL-2", "external_id": "EXT-1", "fingerprint": "b", "fresh": False},
        ]
        with self.assertRaisesRegex(WorkspaceError, "Duplicate"):
            initialize_acquisition_queue(root, plan=plan, identities=identities)
        self.assertEqual(list(root.iterdir()), [])

    def test_queue_accounts_fresh_missing_pending_and_is_idempotent(self) -> None:
        root = self.root / "queue"
        root.mkdir()
        plan = scale_plan(4, missing=1, fresh=1)
        identities = [
            {"local_id": "LOCAL-1", "external_id": "EXT-1", "fingerprint": "a", "fresh": True},
            {"local_id": "LOCAL-2", "external_id": "EXT-2", "fingerprint": "b", "fresh": False},
            {"local_id": "LOCAL-3", "external_id": "EXT-3", "fingerprint": "c", "fresh": False},
            {"local_id": "LOCAL-4", "external_id": None, "fingerprint": "d", "fresh": False},
        ]
        first = initialize_acquisition_queue(root, plan=plan, identities=identities)
        second = initialize_acquisition_queue(root, plan=plan, identities=identities)
        self.assertEqual(first, second)
        self.assertEqual(first["counts"]["FETCHED"], 1)
        self.assertEqual(first["counts"]["PENDING"], 2)
        self.assertEqual(first["counts"]["REVIEW_REQUIRED"], 1)

    def test_quota_reserve_stops_claim_without_state_change(self) -> None:
        root = self.root / "quota"
        root.mkdir()
        plan = scale_plan(1)
        initialize_acquisition_queue(
            root,
            plan=plan,
            identities=[
                {"local_id": "LOCAL-1", "external_id": "EXT-1", "fingerprint": "a", "fresh": False}
            ],
        )
        claim = claim_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=0,
            batch_size=64,
            quota_remaining=10,
            quota_reserve=10,
            now_epoch=100,
        )
        self.assertEqual(claim["status"], "QUOTA_RESERVED")
        self.assertEqual(acquisition_queue_status(root, plan_digest=str(plan["plan_digest"]))["revision"], 0)

    def test_expired_batch_resumes_and_committed_items_are_not_selected_again(self) -> None:
        root = self.root / "resume"
        root.mkdir()
        plan = scale_plan(3)
        identities = [
            {"local_id": f"LOCAL-{index}", "external_id": f"EXT-{index}", "fingerprint": str(index), "fresh": False}
            for index in range(3)
        ]
        initialize_acquisition_queue(root, plan=plan, identities=identities)
        first = claim_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=0,
            batch_size=2,
            quota_remaining=100,
            quota_reserve=10,
            now_epoch=100,
            lease_seconds=1,
        )
        resumed = claim_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=1,
            batch_size=2,
            quota_remaining=99,
            quota_reserve=10,
            now_epoch=102,
        )
        self.assertEqual(
            {item["local_id"] for item in first["items"]},
            {item["local_id"] for item in resumed["items"]},
        )
        outcomes = [
            {"local_id": item["local_id"], "status": "FETCHED", "response_hash": f"hash-{item['local_id']}", "retry_at": None}
            for item in resumed["items"]
        ]
        committed = complete_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=int(resumed["revision"]),
            batch_id=str(resumed["batch_id"]),
            outcomes=outcomes,
        )
        next_batch = claim_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=int(committed["revision"]),
            batch_size=2,
            quota_remaining=98,
            quota_reserve=10,
            now_epoch=103,
        )
        self.assertEqual([item["local_id"] for item in next_batch["items"]], ["LOCAL-2"])

    def test_retry_after_waits_until_due(self) -> None:
        root = self.root / "retry"
        root.mkdir()
        plan = scale_plan(1)
        initialize_acquisition_queue(
            root,
            plan=plan,
            identities=[
                {"local_id": "LOCAL-1", "external_id": "EXT-1", "fingerprint": "a", "fresh": False}
            ],
        )
        claim = claim_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=0,
            batch_size=1,
            quota_remaining=100,
            quota_reserve=10,
            now_epoch=100,
        )
        result = complete_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=1,
            batch_id=str(claim["batch_id"]),
            outcomes=[
                {"local_id": "LOCAL-1", "status": "RETRY_AFTER", "response_hash": None, "retry_at": 200}
            ],
        )
        early = claim_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=int(result["revision"]),
            batch_size=1,
            quota_remaining=99,
            quota_reserve=10,
            now_epoch=199,
        )
        self.assertEqual(early["status"], "EMPTY")
        due = claim_acquisition_batch(
            root,
            plan_digest=str(plan["plan_digest"]),
            expected_revision=int(result["revision"]),
            batch_size=1,
            quota_remaining=99,
            quota_reserve=10,
            now_epoch=200,
        )
        self.assertEqual(due["status"], "LEASED")

    def test_four_thousand_plus_queue_finishes_in_bounded_batches_without_duplicates(self) -> None:
        root = self.root / "large-queue"
        root.mkdir()
        plan = scale_plan(4_509, fresh=5)
        identities = [
            {
                "local_id": f"LOCAL-{index:05d}",
                "external_id": f"EXT-{index:05d}",
                "fingerprint": f"fp-{index:05d}",
                "fresh": index < 5,
            }
            for index in range(4_509)
        ]
        status = initialize_acquisition_queue(root, plan=plan, identities=identities)
        revision = int(status["revision"])
        fetched: set[str] = set()
        batches = 0
        while True:
            claim = claim_acquisition_batch(
                root,
                plan_digest=str(plan["plan_digest"]),
                expected_revision=revision,
                batch_size=64,
                quota_remaining=100_000 - batches,
                quota_reserve=100,
                now_epoch=1_000 + batches,
            )
            if claim["status"] == "EMPTY":
                break
            batch_ids = {str(item["local_id"]) for item in claim["items"]}
            self.assertTrue(fetched.isdisjoint(batch_ids))
            fetched.update(batch_ids)
            result = complete_acquisition_batch(
                root,
                plan_digest=str(plan["plan_digest"]),
                expected_revision=int(claim["revision"]),
                batch_id=str(claim["batch_id"]),
                outcomes=[
                    {
                        "local_id": item["local_id"],
                        "status": "FETCHED",
                        "response_hash": f"hash-{item['local_id']}",
                        "retry_at": None,
                    }
                    for item in claim["items"]
                ],
            )
            revision = int(result["revision"])
            batches += 1
        final = acquisition_queue_status(root, plan_digest=str(plan["plan_digest"]))
        self.assertEqual(batches, 71)
        self.assertEqual(len(fetched), 4_504)
        self.assertEqual(final["counts"]["FETCHED"], 4_509)
        database = next((root / ".opencntx" / "scale").glob("queue-*.sqlite"))
        self.assertLess(database.stat().st_size, 2 * 1024 * 1024)

    def test_risk_classification_does_not_use_project_size(self) -> None:
        self.assertEqual(classify_assurance_risk(**risk_axes()), "LIGHT")
        self.assertEqual(classify_assurance_risk(**risk_axes(newness="NEW")), "STANDARD")
        for axis in ("contract_change", "migration_change", "security_change", "remote_effect"):
            self.assertEqual(classify_assurance_risk(**risk_axes(**{axis: True})), "CRITICAL")
        self.assertEqual(classify_assurance_risk(**risk_axes(concurrent_writers=2)), "CRITICAL")

    def test_light_plan_uses_dependency_selection_and_compact_specification(self) -> None:
        plan = self.assurance(risk_axes())
        selected = {item["test_id"] for item in plan["selected_tests"]}
        self.assertEqual(plan["risk"], "LIGHT")
        self.assertEqual(plan["specification_profile"], "COMPACT")
        self.assertIn("T-CORE", selected)
        self.assertIn("T-API", selected)
        self.assertIn("T-TERMINAL", selected)
        self.assertNotIn("T-FULL", selected)
        self.assertTrue(plan["single_writer_preserved"])

    def test_migration_or_terminal_boundary_forces_every_test(self) -> None:
        migration = self.assurance(risk_axes(migration_change=True))
        terminal = self.assurance(risk_axes(), terminal=True)
        expected = {item["test_id"] for item in assurance_manifest()}
        self.assertEqual({item["test_id"] for item in migration["selected_tests"]}, expected)
        self.assertEqual({item["test_id"] for item in terminal["selected_tests"]}, expected)
        self.assertEqual(migration["risk"], "CRITICAL")
        self.assertEqual(terminal["risk"], "CRITICAL")

    def test_receipt_reuse_requires_every_binding_and_records_estimate_delta(self) -> None:
        plan = self.assurance(risk_axes())
        bindings = {
            "code_tree_digest": "tree-a",
            "environment_digest": "env-a",
            "dependencies_digest": "deps-a",
            "test_manifest_digest": plan["test_manifest_digest"],
            "input_digests": ["input-a"],
        }
        results = {item["test_id"]: "PASS" for item in plan["selected_tests"]}
        receipt = build_assurance_receipt(
            plan,
            bindings=bindings,
            test_results=results,
            actuals={"duration_ms": 80, "storage_bytes": 2_500, "model_units": 40},
        )
        self.assertTrue(assurance_receipt_reusable(receipt, current_bindings=bindings)["reusable"])
        drifted = bindings | {"environment_digest": "env-b"}
        decision = assurance_receipt_reusable(receipt, current_bindings=drifted)
        self.assertFalse(decision["reusable"])
        self.assertEqual(decision["differences"], ["environment_digest"])
        self.assertEqual(receipt["estimate_comparison"]["duration_ms"]["delta"], -20)

    def test_incomplete_green_receipt_is_rejected(self) -> None:
        plan = self.assurance(risk_axes())
        bindings = {
            "code_tree_digest": "tree-a",
            "environment_digest": "env-a",
            "dependencies_digest": "deps-a",
            "test_manifest_digest": plan["test_manifest_digest"],
            "input_digests": [],
        }
        with self.assertRaisesRegex(WorkspaceError, "incomplete"):
            build_assurance_receipt(
                plan,
                bindings=bindings,
                test_results={},
                actuals={"duration_ms": 0, "storage_bytes": 0, "model_units": 0},
            )

    def test_r11_06_schemas_are_closed_and_catalogued(self) -> None:
        names = {
            "scale-plan-v1.schema.json",
            "acquisition-queue-status-v1.schema.json",
            "assurance-plan-v1.schema.json",
            "assurance-receipt-v1.schema.json",
        }
        catalog = json.loads(
            (ROOT / "src/opencntx/schemas/continuity-contract-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(names.issubset(catalog["schemas"]))
        for name in names:
            schema = json.loads(
                (ROOT / "src/opencntx/schemas" / name).read_text(encoding="utf-8")
            )
            self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
