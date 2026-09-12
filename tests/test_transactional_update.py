from __future__ import annotations

import json
import subprocess
import sys
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
    read_update_generation,
    recover_interrupted_update,
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

    def test_completed_update_can_rollback_and_reapply_repeatedly(self) -> None:
        root, components = self.update_fixture()
        plan = self.plan(root, components)
        approval = f"APPLY UPDATE {plan['plan_digest']}"
        for _ in range(3):
            receipt = apply_update_plan(plan, approval=approval)
            self.assertEqual(receipt["status"], "COMPLETED")
            self.assertEqual(apply_update_plan(plan, approval=approval), receipt)
            self.assertEqual(recover_interrupted_update(plan)["status"], "ROLLED_BACK")
            self.assertEqual(recover_interrupted_update(plan)["status"], "ROLLED_BACK")
        self.assertEqual(apply_update_plan(plan, approval=approval)["status"], "COMPLETED")
        self.assertEqual(update_postflight(plan)["status"], "GREEN")

    def test_rollback_archives_completed_receipt_instead_of_erasing_history(self) -> None:
        root, components = self.update_fixture()
        plan = self.plan(root, components)
        receipt = apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        recover_interrupted_update(plan)
        active_receipt = root / ".opencntx-update/receipts" / f"{plan['plan_id']}.json"
        self.assertFalse(active_receipt.exists())
        archived = list((root / ".opencntx-update/receipts/rolled-back").glob("*.json"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(json.loads(archived[0].read_text(encoding="utf-8")), receipt)

    def test_apply_resumes_interrupted_completed_rollback(self) -> None:
        from opencntx import transactional_update as updater

        root, components = self.update_fixture()
        plan = self.plan(root, components)
        approval = f"APPLY UPDATE {plan['plan_digest']}"
        apply_update_plan(plan, approval=approval)
        original = updater._write_journal

        def interrupt(state_root, selected, phase):
            if phase == "ROLLED_BACK":
                raise RuntimeError("rollback interrupted before receipt retirement")
            return original(state_root, selected, phase)

        with (
            mock.patch.object(updater, "_write_journal", side_effect=interrupt),
            self.assertRaisesRegex(RuntimeError, "rollback interrupted"),
        ):
            recover_interrupted_update(plan)
        self.assertEqual(apply_update_plan(plan, approval=approval)["status"], "COMPLETED")

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
        transaction = next((workspace / ".opencntx" / "transactions" / "completed").iterdir())
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
        self.assertEqual(classify_path_capability(self.root / "missing")["status"], "MISSING")
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
            Path(item["active_path"]): sorted(
                path.name for path in Path(item["active_path"]).iterdir()
            )
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
        receipt = apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        self.assertEqual(receipt["status"], "COMPLETED")
        for item in components:
            active = Path(item["active_path"])
            self.assertEqual((active / "version.txt").read_text(encoding="utf-8"), "new\n")
            self.assertFalse((active / "old-only.txt").exists())
            self.assertTrue((active / "new-only.txt").is_file())
        self.assertTrue(Path(str(receipt["backup_path"])).is_dir())
        self.assertEqual(update_postflight(plan)["status"], "GREEN")
        replay = apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        self.assertEqual(replay, receipt)

    def test_managed_reader_observes_one_complete_generation(self) -> None:
        root, components = self.update_fixture("managed-reader")
        plan = self.plan(root, components)
        before = read_update_generation(plan, relative_paths=["version.txt"])
        self.assertEqual("SOURCE", before["generation"])
        self.assertEqual({"SOURCE"}, {item["generation"] for item in before["components"]})
        apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        after = read_update_generation(plan, relative_paths=["version.txt"])
        self.assertEqual("TARGET", after["generation"])
        self.assertEqual({"TARGET"}, {item["generation"] for item in after["components"]})

    def test_managed_subprocess_reader_never_observes_mixed_cutover(self) -> None:
        root, components = self.update_fixture("managed-reader-race")
        plan = self.plan(root, components)
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        program = """
import json
import sys
from pathlib import Path
from opencntx.transactional_update import read_update_generation
plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps(read_update_generation(plan, relative_paths=["version.txt"])))
"""
        readers = []
        first = plan["components"][0]["name"]

        def launch(phase: str) -> None:
            if phase == f"AFTER_ACTIVATE:{first}":
                readers.append(
                    subprocess.Popen(
                        [sys.executable, "-c", program, str(plan_path)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                )

        apply_update_plan(
            plan,
            approval=f"APPLY UPDATE {plan['plan_digest']}",
            fault_hook=launch,
        )
        stdout, stderr = readers[0].communicate(timeout=35)
        self.assertEqual("", stderr)
        observation = json.loads(stdout)
        self.assertEqual("TARGET", observation["generation"])
        self.assertEqual({"TARGET"}, {item["generation"] for item in observation["components"]})

    def test_hard_exit_recovery_needs_no_manual_lock_removal(self) -> None:
        program = """
import json
import os
import sys
from pathlib import Path
from opencntx.transactional_update import apply_update_plan
plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
def crash(phase):
    if phase == sys.argv[2]:
        os._exit(91)
apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}", fault_hook=crash)
"""
        for phase_type, index in (
            ("AFTER_RETIRE", 0),
            ("AFTER_ACTIVATE", 0),
            ("AFTER_ACTIVATE", 1),
        ):
            with self.subTest(phase=phase_type, component=index):
                root, components = self.update_fixture(f"hard-{phase_type}-{index}")
                plan = self.plan(root, components)
                phase = f"{phase_type}:{plan['components'][index]['name']}"
                plan_path = root / "plan.json"
                plan_path.write_text(json.dumps(plan), encoding="utf-8")
                child = subprocess.run(
                    [sys.executable, "-c", program, str(plan_path), phase],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(91, child.returncode)
                self.assertEqual("ROLLED_BACK", recover_interrupted_update(plan)["status"])
                self.assertEqual(
                    {"old"},
                    {
                        (Path(item["active_path"]) / "version.txt")
                        .read_text(encoding="utf-8")
                        .strip()
                        for item in plan["components"]
                    },
                )

    def test_preview_rejects_cross_component_path_overlap(self) -> None:
        root, components = self.update_fixture("overlap")
        components[1]["active_path"] = components[0]["active_path"]
        with self.assertRaisesRegex(WorkspaceError, "overlap"):
            self.plan(root, components)

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

    def test_every_declared_cutover_phase_restores_original_components(self) -> None:
        for component in ("RUNTIME", "PROJECT_STATE"):
            for phase_name in ("BACKUP", "STAGING", "RETIRE", "ACTIVATE"):
                target = f"AFTER_{phase_name}:{component}"
                with self.subTest(phase=target):
                    root, components = self.update_fixture(f"{component}-{phase_name}")
                    plan = self.plan(root, components)
                    before = {
                        item["name"]: {
                            path.name: path.read_bytes()
                            for path in Path(item["active_path"]).iterdir()
                        }
                        for item in components
                    }
                    visited = []

                    def fail(
                        phase: str, *, selected: str = target, seen: list[str] = visited
                    ) -> None:
                        seen.append(phase)
                        if phase == selected:
                            raise RuntimeError("bounded phase failure")

                    with self.assertRaisesRegex(RuntimeError, "bounded phase failure"):
                        apply_update_plan(
                            plan,
                            approval=f"APPLY UPDATE {plan['plan_digest']}",
                            fault_hook=fail,
                        )
                    self.assertEqual(visited[-1], target)
                    for item in components:
                        after = {
                            path.name: path.read_bytes()
                            for path in Path(item["active_path"]).iterdir()
                        }
                        self.assertEqual(after, before[item["name"]])
                    self.assertEqual(recover_interrupted_update(plan)["status"], "ROLLED_BACK")
                    for item in components:
                        after = {
                            path.name: path.read_bytes()
                            for path in Path(item["active_path"]).iterdir()
                        }
                        self.assertEqual(after, before[item["name"]])

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

    def test_rollback_preserves_later_user_work_and_all_recovery_sources(self) -> None:
        root, components = self.update_fixture("later-work")
        plan = self.plan(root, components)
        active = Path(components[0]["active_path"])
        later = active / "later-user-work.txt"
        original_bytes = (active / "version.txt").read_bytes()

        def fail(phase: str) -> None:
            if phase == "AFTER_ACTIVATE:RUNTIME":
                later.write_bytes(b"irreplaceable later work\n")
                raise RuntimeError("injected after later user work")

        with self.assertRaisesRegex(WorkspaceError, "preserved"):
            apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}", fault_hook=fail)
        self.assertTrue(later.is_file(), "Rollback must not erase later user work")
        self.assertEqual(later.read_bytes(), b"irreplaceable later work\n")
        retired = root / ".opencntx-update" / "retired" / str(plan["plan_id"]) / "RUNTIME"
        self.assertEqual((retired / "version.txt").read_bytes(), original_bytes)
        self.assertEqual(
            (Path(str(plan["backup_path"])) / "RUNTIME" / "version.txt").read_bytes(),
            original_bytes,
        )
        with self.assertRaisesRegex(WorkspaceError, "preserved"):
            recover_interrupted_update(plan)
        self.assertEqual(later.read_bytes(), b"irreplaceable later work\n")

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
            (ROOT / "src/opencntx/schemas/continuity-contract-v1.json").read_text(encoding="utf-8")
        )
        self.assertTrue(names.issubset(catalog["schemas"]))
        for name in names:
            schema = json.loads((ROOT / "src/opencntx/schemas" / name).read_text(encoding="utf-8"))
            self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
