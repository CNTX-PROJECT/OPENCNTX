from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from opencntx.contracts import validate_durable_record
from opencntx.control import refresh_control_snapshot
from opencntx.integrity import UNBOUND_EXPECTED_DIGEST, writer_transaction
from opencntx.transactional_update import (
    apply_update_plan,
    build_update_preview,
    classify_path_capability,
    export_legacy_transaction_history,
    migration_readiness,
    update_postflight,
)
from opencntx.workspace import WorkspaceError, init_workspace

ROOT = Path(__file__).resolve().parents[1]
MATRIX = [
    {
        "context_version": "2.0",
        "companion_version": "1.10",
        "project_format": "2",
    },
    {
        "context_version": "2.0",
        "companion_version": "NONE",
        "project_format": "2",
    },
]


class TransactionalUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def update_fixture(self, name: str = "update") -> tuple[Path, list[dict[str, str]]]:
        root = self.root / name
        root.mkdir()
        components = []
        for component in ("RUNTIME", "PROJECT_STATE"):
            active = root / f"active-{component.lower()}"
            candidate = root / f"candidate-{component.lower()}"
            active.mkdir()
            candidate.mkdir()
            (active / "version.txt").write_text("old\n", encoding="utf-8")
            (active / "old-only.txt").write_text("remove from active\n", encoding="utf-8")
            (candidate / "version.txt").write_text("new\n", encoding="utf-8")
            (candidate / "new-only.txt").write_text("target only\n", encoding="utf-8")
            components.append(
                {
                    "name": component,
                    "active_path": str(active),
                    "candidate_path": str(candidate),
                    "from_format": "1",
                    "to_format": "2",
                }
            )
        return root, components

    def plan(self, root: Path, components: list[dict[str, str]]) -> dict[str, object]:
        return build_update_preview(
            root,
            from_version="1.0",
            to_version="2.0",
            components=components,
            target_context_version="2.0",
            target_companion_version="1.10",
            target_project_format="2",
            compatibility_matrix=MATRIX,
            changelog=["Transaction records are validated before publication."],
            risks=["Cutover interruption"],
        )

    def test_writer_without_digest_publishes_contract_valid_string(self) -> None:
        workspace = self.root / "workspace"
        init_workspace(workspace)
        with writer_transaction(workspace, "contract-proof"):
            pass
        completed = workspace / ".opencntx" / "transactions" / "completed"
        transaction = next(completed.iterdir())
        intent = json.loads((transaction / "intent.json").read_text(encoding="utf-8"))
        self.assertEqual(intent["expected_digest"], UNBOUND_EXPECTED_DIGEST)
        validate_durable_record(intent)

    def test_control_refresh_route_never_writes_null_expected_digest(self) -> None:
        workspace = self.root / "control"
        init_workspace(workspace)
        refresh_control_snapshot(workspace)
        completed = workspace / ".opencntx" / "transactions" / "completed"
        intents = [
            json.loads((directory / "intent.json").read_text(encoding="utf-8"))
            for directory in completed.iterdir()
        ]
        self.assertTrue(intents)
        self.assertTrue(all(item["expected_digest"] == UNBOUND_EXPECTED_DIGEST for item in intents))
        for intent in intents:
            validate_durable_record(intent)

    def test_health_and_legacy_migration_readiness_are_separate(self) -> None:
        workspace = self.root / "legacy"
        init_workspace(workspace)
        with writer_transaction(workspace, "legacy-source"):
            pass
        transaction = next(
            (workspace / ".opencntx" / "transactions" / "completed").iterdir()
        )
        intent_path = transaction / "intent.json"
        value = json.loads(intent_path.read_text(encoding="utf-8"))
        value["expected_digest"] = None
        intent_path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        before = intent_path.read_bytes()
        readiness = migration_readiness(workspace)
        self.assertEqual(readiness["operational_health"], "HEALTHY")
        self.assertEqual(readiness["migration_readiness"], "COMPATIBILITY_REQUIRED")
        destination = self.root / "sealed-legacy-export"
        manifest = export_legacy_transaction_history(
            workspace,
            destination=destination,
            expected_readiness_digest=str(readiness["readiness_digest"]),
        )
        copied = destination / manifest["entries"][0]["export_path"] / "intent.json"
        self.assertEqual(copied.read_bytes(), before)
        self.assertEqual(intent_path.read_bytes(), before)
        self.assertFalse(manifest["source_rewritten"])

    def test_path_capabilities_distinguish_missing_sandbox_acl_and_reparse(self) -> None:
        readable = self.root / "readable.txt"
        readable.write_text("safe\n", encoding="utf-8")
        self.assertEqual(classify_path_capability(readable)["status"], "READABLE")
        self.assertEqual(
            classify_path_capability(self.root / "missing")["status"], "MISSING"
        )
        self.assertEqual(
            classify_path_capability(readable, declared_sandbox_denied=True)["status"],
            "SANDBOX_DENIED",
        )
        with mock.patch.object(Path, "lstat", side_effect=PermissionError):
            self.assertEqual(classify_path_capability(readable)["status"], "ACL_DENIED")
        link = self.root / "link"
        try:
            link.symlink_to(readable)
        except OSError:
            pass
        else:
            self.assertEqual(classify_path_capability(link)["status"], "REPARSE_UNSAFE")

    def test_preview_is_read_only_and_requires_compatible_tuple_and_space(self) -> None:
        root, components = self.update_fixture()
        before = {
            Path(item["active_path"]): sorted(path.name for path in Path(item["active_path"]).iterdir())
            for item in components
        }
        plan = self.plan(root, components)
        self.assertFalse(plan["writes_performed"])
        self.assertFalse((root / ".opencntx-update").exists())
        for path, names in before.items():
            self.assertEqual(sorted(item.name for item in path.iterdir()), names)
        with self.assertRaisesRegex(WorkspaceError, "unsupported"):
            build_update_preview(
                root,
                from_version="1.0",
                to_version="2.0",
                components=components,
                target_context_version="9.0",
                target_companion_version="1.10",
                target_project_format="2",
                compatibility_matrix=MATRIX,
                changelog=[],
                risks=[],
            )
        with self.assertRaisesRegex(WorkspaceError, "space"):
            build_update_preview(
                root,
                from_version="1.0",
                to_version="2.0",
                components=components,
                target_context_version="2.0",
                target_companion_version="1.10",
                target_project_format="2",
                compatibility_matrix=MATRIX,
                changelog=[],
                risks=[],
                available_bytes=0,
            )

    def test_multi_component_cutover_has_backup_no_active_old_residue_and_replay(self) -> None:
        root, components = self.update_fixture()
        plan = self.plan(root, components)
        with self.assertRaisesRegex(WorkspaceError, "approval"):
            apply_update_plan(plan, approval="yes")
        receipt = apply_update_plan(
            plan, approval=f"APPLY UPDATE {plan['plan_digest']}"
        )
        self.assertEqual(receipt["status"], "COMPLETED")
        for item in components:
            active = Path(item["active_path"])
            self.assertEqual((active / "version.txt").read_text(encoding="utf-8"), "new\n")
            self.assertFalse((active / "old-only.txt").exists())
            self.assertTrue((active / "new-only.txt").is_file())
        self.assertTrue(Path(str(receipt["backup_path"])).is_dir())
        self.assertEqual(update_postflight(plan)["status"], "GREEN")
        replay = apply_update_plan(
            plan, approval=f"APPLY UPDATE {plan['plan_digest']}"
        )
        self.assertEqual(replay, receipt)

    def test_failure_during_second_component_restores_every_active_component(self) -> None:
        root, components = self.update_fixture("failure")
        plan = self.plan(root, components)

        def fail(phase: str) -> None:
            if phase == "AFTER_RETIRE:PROJECT_STATE":
                raise RuntimeError("injected second component failure")

        with self.assertRaisesRegex(RuntimeError, "second component"):
            apply_update_plan(
                plan,
                approval=f"APPLY UPDATE {plan['plan_digest']}",
                fault_hook=fail,
            )
        for item in components:
            active = Path(item["active_path"])
            self.assertEqual((active / "version.txt").read_text(encoding="utf-8"), "old\n")
            self.assertTrue((active / "old-only.txt").is_file())
            self.assertFalse((active / "new-only.txt").exists())
        self.assertTrue(Path(str(plan["backup_path"])).is_dir())
        self.assertFalse((root / ".opencntx-update" / "staging" / str(plan["plan_id"])).exists())
        self.assertFalse((root / ".opencntx-update" / "retired" / str(plan["plan_id"])).exists())

    def test_source_or_candidate_drift_stops_before_cutover(self) -> None:
        root, components = self.update_fixture("drift")
        plan = self.plan(root, components)
        candidate = Path(components[0]["candidate_path"])
        (candidate / "version.txt").write_text("changed after preview\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "changed after preview"):
            apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        self.assertEqual(
            (Path(components[0]["active_path"]) / "version.txt").read_text(encoding="utf-8"),
            "old\n",
        )

    def test_completed_receipt_never_hides_later_active_drift(self) -> None:
        root, components = self.update_fixture("postflight-drift")
        plan = self.plan(root, components)
        apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        active = Path(components[0]["active_path"])
        (active / "version.txt").write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceError, "active state drifted"):
            apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        self.assertEqual(update_postflight(plan)["status"], "REPAIR_REQUIRED")

    def test_contract_catalog_lists_r11_04_schemas(self) -> None:
        names = {
            "path-capability-v1.schema.json",
            "migration-readiness-v1.schema.json",
            "transactional-update-plan-v1.schema.json",
            "transactional-update-receipt-v1.schema.json",
            "legacy-transaction-export-v1.schema.json",
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
