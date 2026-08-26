from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from opencntx.catalog import rebuild_catalog
from opencntx.core import pack_project, verify_package
from opencntx.lifecycle import (
    AUDIT_RESULTS,
    LifecycleError,
    _plan_digest,
    apply_cleanup,
    apply_migration,
    audit_permissions,
    lifecycle_status,
    plan_cleanup,
    plan_migration,
    require_disk_capacity,
    restore_cleanup,
    schema_assets,
    schema_bundle_digest,
    storage_inventory,
    write_plan,
)
from opencntx.workspace import capture_source, init_workspace

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "lifecycle"


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def byte_tree(path: Path) -> dict[str, bytes]:
    if path.is_file():
        return {".": path.read_bytes()}
    return {
        candidate.relative_to(path).as_posix(): candidate.read_bytes()
        for candidate in sorted(path.rglob("*"))
        if candidate.is_file()
    }


def write_core_config(root: Path) -> None:
    (root / "opencntx.toml").write_text(
        """[task]
goal = "Lifecycle test"

[context]
include = ["README.md"]
required = ["README.md"]
exclude = []
max_files = 5
max_bytes = 10000
""",
        encoding="utf-8",
        newline="\n",
    )


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")


def cleanup_worker(
    root: str,
    plan_path: str,
    plan_sha256: str,
    barrier: object,
    queue: object,
) -> None:
    try:
        barrier.wait(timeout=15)
        result = apply_cleanup(Path(root), Path(plan_path), plan_sha256)
        queue.put(("success", result["status"]))
    except BaseException as exc:  # subprocess proof reports stable class/code only
        queue.put(("error", getattr(exc, "code", type(exc).__name__)))


class LifecycleTests(unittest.TestCase):
    def private_checkpoint(self, name: str = "checkpoint") -> Path:
        temporary = tempfile.TemporaryDirectory(
            prefix="opencntx-private-checkpoint-",
            dir=Path.home(),
        )
        self.addCleanup(temporary.cleanup)
        parent = Path(temporary.name)
        audit = audit_permissions(parent, private=True)
        self.assertEqual(
            audit.result,
            "SAFE_OBSERVED",
            f"private checkpoint test parent is unavailable: {audit.details}",
        )
        return parent / name

    def test_new_workspace_has_current_private_lifecycle_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)

            state_path = root / ".opencntx" / "lifecycle" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(state["format"], "opencntx-lifecycle-state")
            self.assertEqual(state["format_version"], 1)
            self.assertEqual(state["record_count"], 0)
            self.assertEqual(state["schema_bundle_sha256"], schema_bundle_digest())
            if os.name != "nt":
                self.assertEqual(state_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(state_path.parent.stat().st_mode & 0o777, 0o700)

    def test_status_is_read_only_private_and_distinguishes_trust_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            private = parent / "private-client-name.txt"
            private.write_text("sensitive fixture words\n", encoding="utf-8")
            capture_source(root, private, privacy="PRIVATE", origin="TEST")
            before = snapshot(root)

            local = lifecycle_status(root, "single-user-local")
            shared = lifecycle_status(root, "shared-team")
            after = snapshot(root)
            rendered = json.dumps(local, ensure_ascii=True, sort_keys=True)

            self.assertEqual(before, after)
            self.assertEqual(local["trust_status"], "LOCAL_ASSUMPTION_ONLY")
            self.assertEqual(shared["trust_status"], "UNSUPPORTED_FOR_AUTHORIZATION")
            self.assertEqual(local["privacy_counts"]["PRIVATE"], 1)
            self.assertEqual(
                local["sources"][0]["content_sha256"],
                hashlib.sha256(private.read_bytes()).hexdigest(),
            )
            self.assertRegex(local["sources"][0]["alias"], r"^SRC-ALIAS-[0-9a-f]{12}$")
            self.assertNotIn(private.name, rendered)
            self.assertNotIn("sensitive fixture words", rendered)
            self.assertIn("do not encrypt", local["publication_warning"])

    def test_permission_audit_is_observational_and_platform_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            path = root / ".opencntx"
            before = path.stat().st_mode

            result = audit_permissions(path, private=True)

            self.assertIn(result.result, AUDIT_RESULTS)
            self.assertEqual(path.stat().st_mode, before)
            if os.name != "nt":
                os.chmod(path, 0o777)
                self.assertEqual(
                    audit_permissions(path, private=True).result, "WARNING_BROAD_ACCESS"
                )

    def test_storage_categories_sum_exactly_and_keep_budget_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            source = parent / "source.bin"
            source.write_bytes(b"source-bytes")
            capture_source(root, source)

            report = storage_inventory(root)

            self.assertEqual(sum(report["categories"].values()), report["observed_total_bytes"])
            self.assertEqual(
                report["categories"]["source_content"],
                len(b"source-bytes") + next((root / "SOURCES").rglob("record.json")).stat().st_size,
            )
            self.assertEqual(report["budgeted_content_bytes"], len(b"source-bytes"))
            self.assertEqual(report["configured_max_storage_bytes"], 20 * 1024**3)

    def test_disk_preflight_rejects_integer_and_volume_evidence_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory)
            with self.assertRaises(LifecycleError) as invalid:
                require_disk_capacity(path, 1 << 63, "test")
            self.assertEqual(invalid.exception.code, "disk_space_invalid")
            with (
                mock.patch(
                    "opencntx.lifecycle.shutil.disk_usage", side_effect=OSError("unavailable")
                ),
                self.assertRaises(LifecycleError) as unavailable,
            ):
                require_disk_capacity(path, 1, "test")
            self.assertEqual(unavailable.exception.code, "disk_space_unavailable")
            invalid_usage = mock.Mock(total=10, used=0, free=11)
            with (
                mock.patch("opencntx.lifecycle.shutil.disk_usage", return_value=invalid_usage),
                self.assertRaises(LifecycleError) as inconsistent,
            ):
                require_disk_capacity(path, 1, "test")
            self.assertEqual(inconsistent.exception.code, "disk_space_unavailable")

    def test_schema_assets_are_unique_packaged_and_matrix_aligned(self) -> None:
        assets = schema_assets()
        self.assertEqual(
            set(assets),
            {
                "compatibility-matrix-v1.json",
                "durable-format-contracts-v1.json",
                "durable-records-v1.schema.json",
                "lifecycle-plan-v1.schema.json",
                "lifecycle-state-v1.schema.json",
                "public-contract-v1.json",
            },
        )
        values = {name: json.loads(content.decode("ascii")) for name, content in assets.items()}
        ids = {value["$id"] for value in values.values()}
        self.assertEqual(len(ids), 6)
        matrix_formats = {
            item["format"] for item in values["compatibility-matrix-v1.json"]["records"]
        }
        schema_formats = set(
            values["durable-records-v1.schema.json"]["$defs"]["currentRecord"]["properties"][
                "format"
            ]["enum"]
        )
        self.assertEqual(matrix_formats, schema_formats)
        self.assertRegex(schema_bundle_digest(), r"^[0-9a-f]{64}$")

    def test_migration_dry_run_is_deterministic_and_apply_rewrites_no_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            (root / ".opencntx" / "lifecycle" / "state.json").unlink()
            source = parent / "fixture.txt"
            source.write_bytes(b"fixture\n")
            capture_source(root, source, origin="TEST-FIXTURE")
            before = snapshot(root)

            first = plan_migration(root)
            second = plan_migration(root)
            plan_path = parent / "migration-plan.json"
            write_plan(plan_path, first, workspace_root=root)
            result = apply_migration(root, plan_path, first["plan_sha256"])
            after = snapshot(root)

            self.assertEqual(first, second)
            self.assertEqual(first["operation"], "REGISTER_UNCHANGED_V1")
            self.assertEqual(first["plan_sha256"], _plan_digest(first))
            self.assertEqual(result["status"], "MIGRATED")
            for relative, value in before.items():
                self.assertEqual(after[relative], value, relative)
            self.assertTrue((root / ".opencntx" / "lifecycle" / "state.json").is_file())

    def test_current_pack_manifest_security_is_migration_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            (root / "README.md").write_text("# Lifecycle\n", encoding="utf-8")
            write_core_config(root)
            latest, _ = pack_project(root)
            manifest = json.loads((latest / "manifest.json").read_text(encoding="utf-8"))

            self.assertIsInstance(manifest["security"], dict)
            plan = plan_migration(root)
            self.assertEqual("ALREADY_CURRENT", plan["operation"])
            self.assertEqual(plan["plan_sha256"], _plan_digest(plan))

    def test_migration_fault_rolls_back_to_absent_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            state_path = root / ".opencntx" / "lifecycle" / "state.json"
            state_path.unlink()
            plan = plan_migration(root)
            plan_path = parent / "migration-plan.json"
            write_plan(plan_path, plan, workspace_root=root)

            no_space = mock.Mock(total=100, used=100, free=0)
            with (
                mock.patch("opencntx.lifecycle.shutil.disk_usage", return_value=no_space),
                self.assertRaises(LifecycleError) as no_space_error,
            ):
                apply_migration(root, plan_path, plan["plan_sha256"])
            self.assertEqual(no_space_error.exception.code, "disk_space_insufficient")
            self.assertFalse(state_path.exists())

            def fail(phase: str) -> None:
                if phase == "MIGRATION_AFTER_STATE":
                    raise RuntimeError("injected migration failure")

            with (
                mock.patch("opencntx.lifecycle._TEST_FAULT_HOOK", fail),
                self.assertRaisesRegex(RuntimeError, "injected migration failure"),
            ):
                apply_migration(root, plan_path, plan["plan_sha256"])

            self.assertFalse(state_path.exists())

    def test_all_lifecycle_fault_hooks_restore_exact_state(self) -> None:
        for phase in ("MIGRATION_BEFORE_STATE", "MIGRATION_AFTER_STATE"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary_directory:
                parent = Path(temporary_directory)
                root = parent / "workspace"
                init_workspace(root)
                state_path = root / ".opencntx" / "lifecycle" / "state.json"
                state_path.unlink()
                plan = plan_migration(root)
                plan_path = parent / "migration-plan.json"
                write_plan(plan_path, plan, workspace_root=root)

                def fail_migration(observed: str, expected_phase: str = phase) -> None:
                    if observed == expected_phase:
                        raise RuntimeError(f"injected {expected_phase}")

                with (
                    mock.patch("opencntx.lifecycle._TEST_FAULT_HOOK", fail_migration),
                    self.assertRaisesRegex(RuntimeError, f"injected {phase}"),
                ):
                    apply_migration(root, plan_path, plan["plan_sha256"])
                self.assertFalse(state_path.exists())

        for phase in ("CLEANUP_AFTER_COPY", "CLEANUP_BEFORE_REMOVE", "CLEANUP_AFTER_REMOVE"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary_directory:
                parent = Path(temporary_directory)
                root = parent / "workspace"
                init_workspace(root)
                (root / "README.md").write_text("# Lifecycle\n", encoding="utf-8")
                write_core_config(root)
                latest, _ = pack_project(root)
                before = byte_tree(latest)
                plan = plan_cleanup(root, ["latest-package"], self.private_checkpoint())
                plan_path = parent / "cleanup-plan.json"
                write_plan(plan_path, plan, workspace_root=root)

                def fail_cleanup(observed: str, expected_phase: str = phase) -> None:
                    if observed == expected_phase:
                        raise RuntimeError(f"injected {expected_phase}")

                with (
                    mock.patch("opencntx.lifecycle._TEST_FAULT_HOOK", fail_cleanup),
                    self.assertRaisesRegex(RuntimeError, f"injected {phase}"),
                ):
                    apply_cleanup(root, plan_path, plan["plan_sha256"])
                self.assertEqual(before, byte_tree(latest))

        with (
            self.subTest(phase="RESTORE_AFTER_COPY"),
            tempfile.TemporaryDirectory() as temporary_directory,
        ):
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            (root / "README.md").write_text("# Lifecycle\n", encoding="utf-8")
            write_core_config(root)
            latest, _ = pack_project(root)
            checkpoint = self.private_checkpoint()
            plan = plan_cleanup(root, ["latest-package"], checkpoint)
            plan_path = parent / "cleanup-plan.json"
            write_plan(plan_path, plan, workspace_root=root)
            applied = apply_cleanup(root, plan_path, plan["plan_sha256"])
            before_restore = snapshot(root)

            def fail_restore(observed: str) -> None:
                if observed == "RESTORE_AFTER_COPY":
                    raise RuntimeError("injected RESTORE_AFTER_COPY")

            with (
                mock.patch("opencntx.lifecycle._TEST_FAULT_HOOK", fail_restore),
                self.assertRaisesRegex(RuntimeError, "injected RESTORE_AFTER_COPY"),
            ):
                restore_cleanup(root, checkpoint, applied["checkpoint_sha256"])
            self.assertFalse(latest.exists())
            after_restore = snapshot(root)
            for relative, value in before_restore.items():
                self.assertEqual(value, after_restore[relative], relative)
            transaction_evidence = set(after_restore) - set(before_restore)
            self.assertTrue(transaction_evidence)
            self.assertTrue(
                all(
                    relative.startswith(".opencntx/transactions/completed/")
                    for relative in transaction_evidence
                )
            )

    def test_unknown_fixture_fails_closed_and_rollback_fixture_is_structural(self) -> None:
        unknown = json.loads((FIXTURES / "unknown-v99-record.json").read_text(encoding="utf-8"))
        rollback = json.loads((FIXTURES / "rollback-state-v1.json").read_text(encoding="utf-8"))
        legacy = json.loads(
            (FIXTURES / "legacy-unregistered-v1-record.json").read_text(encoding="utf-8")
        )
        self.assertEqual(legacy["format_version"], 1)
        self.assertEqual(rollback["format"], "opencntx-lifecycle-state")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            (root / ".opencntx" / "lifecycle" / "state.json").unlink()
            (root / ".opencntx" / "receipts" / "unknown.json").write_text(
                json.dumps(unknown), encoding="utf-8"
            )
            with self.assertRaises(LifecycleError) as context:
                plan_migration(root)
            self.assertEqual(context.exception.code, "lifecycle_record_unsupported")

            (root / ".opencntx" / "receipts" / "unknown.json").write_text(
                json.dumps(
                    {
                        "format": "opencntx-manifest",
                        "format_version": 1,
                        "unexpected": True,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(LifecycleError) as invalid_context:
                plan_migration(root)
            self.assertEqual(invalid_context.exception.code, "lifecycle_record_invalid")

    def test_cleanup_plan_apply_and_restore_are_digest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            (root / "README.md").write_text("# Lifecycle\n", encoding="utf-8")
            write_core_config(root)
            latest, _ = pack_project(root)
            before_digest = hashlib.sha256((latest / "manifest.json").read_bytes()).hexdigest()
            checkpoint = self.private_checkpoint()

            first = plan_cleanup(root, ["latest-package"], checkpoint)
            second = plan_cleanup(root, ["latest-package"], checkpoint)
            plan_path = parent / "cleanup-plan.json"
            write_plan(plan_path, first, workspace_root=root)
            with self.assertRaises(LifecycleError):
                apply_cleanup(root, plan_path, "0" * 64)
            self.assertTrue(latest.exists())
            applied = apply_cleanup(root, plan_path, first["plan_sha256"])

            self.assertEqual(first, second)
            self.assertFalse(latest.exists())
            self.assertTrue((checkpoint / "manifest.json").is_file())
            self.assertIn(applied["directory_flush"], {"SYNCED", "UNSUPPORTED"})
            restored = restore_cleanup(root, checkpoint, applied["checkpoint_sha256"])
            self.assertEqual(restored["status"], "RESTORED")
            self.assertEqual(
                hashlib.sha256((latest / "manifest.json").read_bytes()).hexdigest(),
                before_digest,
            )
            self.assertTrue(verify_package(latest).ok)
            with self.assertRaises(LifecycleError) as conflict:
                restore_cleanup(root, checkpoint, applied["checkpoint_sha256"])
            self.assertEqual(conflict.exception.code, "lifecycle_restore_conflict")

    def test_active_executor_binding_blocks_latest_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            (root / "README.md").write_text("# Lifecycle\n", encoding="utf-8")
            write_core_config(root)
            latest, _ = pack_project(root)
            manifest_digest = hashlib.sha256((latest / "manifest.json").read_bytes()).hexdigest()
            executors = root / ".opencntx" / "executors"
            executors.mkdir()
            (executors / "active.json").write_text(
                json.dumps(
                    {
                        "format": "opencntx-executor-assignment",
                        "format_version": 1,
                        "context": {"manifest_digest": manifest_digest},
                    }
                ),
                encoding="utf-8",
            )

            checkpoint = self.private_checkpoint()
            with self.assertRaises(LifecycleError) as blocked:
                plan_cleanup(root, ["latest-package"], checkpoint)

            self.assertEqual(blocked.exception.code, "lifecycle_cleanup_blocked")
            self.assertTrue(latest.is_dir())
            self.assertFalse(checkpoint.exists())

    def test_other_allowlisted_cleanup_classes_round_trip_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            rebuild_catalog(root)

            completed_id = "TXN-20260820T010203000004Z-111111111111"
            completed = root / ".opencntx" / "transactions" / "completed" / completed_id
            completed.mkdir(parents=True)
            (completed / "intent.json").write_bytes(
                json_bytes(
                    {
                        "format": "opencntx-transaction",
                        "format_version": 1,
                        "transaction_id": completed_id,
                    }
                )
            )
            (completed / "completion.json").write_bytes(
                json_bytes(
                    {
                        "format": "opencntx-transaction-completion",
                        "format_version": 1,
                        "transaction_id": completed_id,
                    }
                )
            )

            recovered_id = "TXN-20260820T010203000005Z-222222222222"
            recovered = (
                root / ".opencntx" / "transactions" / "completed" / f"{recovered_id}-recovered"
            )
            recovered.mkdir(parents=True)
            recovered_intent = json_bytes(
                {
                    "format": "opencntx-transaction",
                    "format_version": 1,
                    "transaction_id": recovered_id,
                }
            )
            (recovered / "intent.json").write_bytes(recovered_intent)
            intent_digest = hashlib.sha256(recovered_intent).hexdigest()
            recovery_id = "RECOVERY-20260820T010203000006Z-333333333333"
            backup = root / ".opencntx" / "recovery" / "backups" / recovery_id
            backup.mkdir(parents=True)
            (backup / "manifest.json").write_bytes(
                json_bytes(
                    {
                        "backup_id": recovery_id,
                        "format": "opencntx-recovery-backup",
                        "format_version": 1,
                        "intent_sha256": intent_digest,
                        "transaction_id": recovered_id,
                    }
                )
            )
            (root / ".opencntx" / "receipts" / "recovery-test.json").write_bytes(
                json_bytes(
                    {
                        "backup_path": backup.relative_to(root).as_posix(),
                        "format": "opencntx-recovery-receipt",
                        "format_version": 1,
                        "intent_sha256": intent_digest,
                        "transaction_id": recovered_id,
                    }
                )
            )
            targets = [
                "catalog-cache",
                f"completed-transaction:{completed_id}",
                f"recovery-backup:{recovery_id}",
            ]
            expected = {
                path.relative_to(root).as_posix(): byte_tree(path)
                for path in (root / ".opencntx" / "catalog.sqlite", completed, backup)
            }
            checkpoint = self.private_checkpoint()
            plan = plan_cleanup(root, targets, checkpoint)
            plan_path = parent / "cleanup-plan.json"
            write_plan(plan_path, plan, workspace_root=root)

            applied = apply_cleanup(root, plan_path, plan["plan_sha256"])
            self.assertFalse((root / ".opencntx" / "catalog.sqlite").exists())
            self.assertFalse(completed.exists())
            self.assertFalse(backup.exists())
            restore_cleanup(root, checkpoint, applied["checkpoint_sha256"])

            self.assertEqual(
                byte_tree(root / ".opencntx" / "catalog.sqlite"),
                expected[".opencntx/catalog.sqlite"],
            )
            self.assertEqual(byte_tree(completed), expected[completed.relative_to(root).as_posix()])
            self.assertEqual(byte_tree(backup), expected[backup.relative_to(root).as_posix()])

    def test_cleanup_rejects_arbitrary_targets_and_restores_after_fault(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            (root / "README.md").write_text("# Lifecycle\n", encoding="utf-8")
            write_core_config(root)
            latest, _ = pack_project(root)
            with self.assertRaises(LifecycleError) as context:
                plan_cleanup(root, ["SOURCES"], parent / "bad-checkpoint")
            self.assertEqual(context.exception.code, "lifecycle_cleanup_target_invalid")

            plan = plan_cleanup(root, ["latest-package"], self.private_checkpoint())
            plan_path = parent / "cleanup-plan.json"
            write_plan(plan_path, plan, workspace_root=root)

            def fail(phase: str) -> None:
                if phase == "CLEANUP_AFTER_REMOVE":
                    raise RuntimeError("injected cleanup failure")

            with (
                mock.patch("opencntx.lifecycle._TEST_FAULT_HOOK", fail),
                self.assertRaisesRegex(RuntimeError, "injected cleanup failure"),
            ):
                apply_cleanup(root, plan_path, plan["plan_sha256"])

            self.assertTrue(latest.is_dir())
            self.assertTrue(verify_package(latest).ok)

    def test_two_cleanup_writers_cannot_apply_the_same_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "workspace"
            init_workspace(root)
            (root / "README.md").write_text("# Lifecycle\n", encoding="utf-8")
            write_core_config(root)
            pack_project(root)
            plan = plan_cleanup(root, ["latest-package"], self.private_checkpoint())
            plan_path = parent / "cleanup-plan.json"
            write_plan(plan_path, plan, workspace_root=root)
            context = multiprocessing.get_context("spawn")
            barrier = context.Barrier(2)
            queue = context.Queue()
            processes = [
                context.Process(
                    target=cleanup_worker,
                    args=(str(root), str(plan_path), plan["plan_sha256"], barrier, queue),
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=30)
                self.assertFalse(process.is_alive(), "cleanup writer hung")
                self.assertEqual(process.exitcode, 0)
            outcomes = sorted(queue.get(timeout=5) for _ in processes)
            self.assertEqual([item[0] for item in outcomes], ["error", "success"])
            self.assertFalse((root / ".opencntx" / "latest").exists())


if __name__ == "__main__":
    unittest.main()
