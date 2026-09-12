from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from opencntx import install_manager as manager


class InstallManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def wheel(self, version: str, name: str | None = None) -> tuple[Path, str]:
        path = self.root / (name or f"opencntx-{version}-py3-none-any.whl")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                f"opencntx-{version}.dist-info/METADATA",
                f"Metadata-Version: 2.1\nName: opencntx\nVersion: {version}\n",
            )
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def pipx(self, version: str = "1.7.5") -> dict[str, object]:
        return {
            "venvs": {
                "opencntx": {
                    "metadata": {
                        "main_package": {
                            "app_paths": [
                                {"__Path__": str(self.root / "venv/Scripts/opencntx.exe")}
                            ],
                            "package_version": version,
                            "package_or_url": f"opencntx=={version}",
                            "pinned": True,
                        },
                        "source_interpreter": {"__Path__": "python"},
                    }
                }
            }
        }

    def test_bootstrap_runner_is_not_mistaken_for_persistent_installation(self) -> None:
        with mock.patch.object(manager, "_pipx_inventory", return_value={"venvs": {}}):
            status = manager.installation_status()
        self.assertEqual("ABSENT", status["owner"]["owner"])
        self.assertEqual([], status["runtime"]["packages"])
        self.assertFalse(status["writes_performed"])

    def test_inventory_is_read_only_and_classifies_project_and_route(self) -> None:
        project = self.root / "project"
        store = project / ".opencntx"
        store.mkdir(parents=True)
        (store / "manifest.json").write_text(
            '{"format":"opencntx-workspace","format_version":1}', encoding="utf-8"
        )
        (store / "writer.lock").write_text("retained marker\n", encoding="utf-8")
        before = {
            path.relative_to(project): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file()
        }
        with mock.patch.object(manager, "_pipx_inventory", return_value={"venvs": {}}):
            inventory = manager.installation_inventory(
                project_roots=(project,), state_root=self.root / "state"
            )
        self.assertEqual("FRESH_MANAGED", inventory["compatibility_route"])
        self.assertEqual("opencntx-workspace", inventory["projects"][0]["state_format"])
        self.assertEqual("UNKNOWN", inventory["projects"][0]["writer_activity"])
        self.assertFalse(inventory["writes_performed"])
        self.assertEqual(
            before,
            {
                path.relative_to(project): path.read_bytes()
                for path in project.rglob("*")
                if path.is_file()
            },
        )

    def test_explicit_python_cannot_be_replaced_by_unrelated_pipx(self) -> None:
        selected = self.root / "target/Scripts/python.exe"
        runtime = {
            "owner": "PIP_VENV",
            "python": str(selected),
            "packages": [{"version": "1.7.5"}],
        }
        with (
            mock.patch.object(manager, "_pipx_inventory") as pipx_inventory,
            mock.patch.object(manager, "inspect_runtime", return_value=runtime),
        ):
            status = manager.installation_status(python=selected)
        pipx_inventory.assert_not_called()
        self.assertEqual("PIP_VENV", status["owner"]["owner"])
        self.assertEqual(str(selected), status["owner"]["python"])

    def test_update_binds_artifacts_verifies_runtime_and_removes_owned_staging(self) -> None:
        candidate, candidate_hash = self.wheel("1.7.6")
        rollback, rollback_hash = self.wheel("1.7.5", "rollback.whl")
        health = {"status": "RUNTIME_HEALTHY", "version": "1.7.6"}
        with (
            mock.patch.object(manager, "_pipx_inventory", return_value=self.pipx()),
            mock.patch.object(manager, "inspect_runtime", return_value={"owner": "PIPX"}),
            mock.patch.object(manager, "_manager_command", return_value=["manager"]),
            mock.patch.object(manager, "_execute") as execute,
            mock.patch.object(manager, "_resolved_python", return_value=Path("python")),
            mock.patch.object(manager, "verify_runtime", return_value=health),
        ):
            result = manager.managed_update(
                artifact=str(candidate),
                sha256=candidate_hash,
                version="1.7.6",
                rollback_artifact=str(rollback),
                rollback_sha256=rollback_hash,
                state_root=self.root / "state",
            )
        self.assertEqual("NEW_HEALTHY", result["status"])
        execute.assert_called_once()
        self.assertEqual([], list((self.root / "state/staging").iterdir()))
        journal = json.loads(next((self.root / "state/journals").iterdir()).read_text())
        self.assertEqual("NEW_HEALTHY", journal["phase"])
        self.assertEqual(candidate_hash, journal["candidate_sha256"])
        self.assertEqual(rollback_hash, journal["rollback_sha256"])
        self.assertTrue(Path(journal["candidate_artifact"]).is_file())

    def test_failed_candidate_uses_cached_offline_rollback(self) -> None:
        candidate, candidate_hash = self.wheel("1.7.6")
        rollback, rollback_hash = self.wheel("1.7.5", "rollback.whl")
        health_calls = [manager.InstallationError("candidate crashed"), {"version": "1.7.5"}]
        with (
            mock.patch.object(manager, "_pipx_inventory", return_value=self.pipx()),
            mock.patch.object(manager, "inspect_runtime", return_value={"owner": "PIPX"}),
            mock.patch.object(manager, "_manager_command", return_value=["manager"]),
            mock.patch.object(manager, "_execute") as execute,
            mock.patch.object(manager, "_resolved_python", return_value=Path("python")),
            mock.patch.object(manager, "verify_runtime", side_effect=health_calls),
        ):
            result = manager.managed_update(
                artifact=str(candidate),
                sha256=candidate_hash,
                version="1.7.6",
                rollback_artifact=str(rollback),
                rollback_sha256=rollback_hash,
                state_root=self.root / "state",
            )
        self.assertEqual("OLD_RESTORED", result["status"])
        self.assertEqual(2, execute.call_count)

    def test_bad_candidate_hash_stops_before_journal_or_activation(self) -> None:
        candidate, _candidate_hash = self.wheel("1.7.6")
        with (
            mock.patch.object(manager, "_pipx_inventory", return_value={"venvs": {}}),
            self.assertRaisesRegex(manager.InstallManagerError, "SHA-256"),
        ):
            manager.managed_update(
                artifact=str(candidate),
                sha256="0" * 64,
                version="1.7.6",
                rollback_artifact=None,
                rollback_sha256=None,
                state_root=self.root / "state",
            )
        self.assertFalse((self.root / "state/journals").exists())
        self.assertEqual([], list((self.root / "state/staging").iterdir()))

    def test_non_owned_nonempty_state_root_fails_closed(self) -> None:
        candidate, candidate_hash = self.wheel("1.7.6")
        state = self.root / "state"
        state.mkdir()
        sentinel = state / "user.txt"
        sentinel.write_text("keep\n", encoding="utf-8")
        with (
            mock.patch.object(manager, "_pipx_inventory", return_value={"venvs": {}}),
            self.assertRaisesRegex(manager.InstallManagerError, "not product-owned"),
        ):
            manager.managed_update(
                artifact=str(candidate),
                sha256=candidate_hash,
                version="1.7.6",
                rollback_artifact=None,
                rollback_sha256=None,
                state_root=state,
            )
        self.assertEqual("keep\n", sentinel.read_text(encoding="utf-8"))

    def test_resume_rejects_tampered_journal_identity(self) -> None:
        directory = self.root / "state/journals"
        directory.mkdir(parents=True)
        (directory / "plan.json").write_text(
            json.dumps({"format": manager._FORMAT, "plan_digest": "0" * 64}), encoding="utf-8"
        )
        with self.assertRaisesRegex(manager.InstallManagerError, "identity"):
            manager.resume_update(state_root=self.root / "state")

    def test_resume_selects_newest_created_journal_not_filename_order(self) -> None:
        journals = self.root / "state/journals"
        journals.mkdir(parents=True)
        for name, created, status in (("zz", 1, "OLD_RESTORED"), ("aa", 2, "NEW_HEALTHY")):
            basis = {
                "format": manager._FORMAT,
                "plan_id": name,
                "created_ns": created,
                "owner": "PIPX",
                "python": "python",
                "executable": "opencntx",
                "from_version": "1.7.5",
                "to_version": "1.7.6",
                "candidate_artifact": "candidate.whl",
                "candidate_sha256": "a" * 64,
                "rollback_artifact": "rollback.whl",
                "rollback_sha256": "b" * 64,
            }
            basis["plan_digest"] = manager._digest(basis)
            manager._save_journal(
                journals / f"{name}.json", basis, phase=status, result={"status": status}
            )
        self.assertEqual(
            "NEW_HEALTHY", manager.resume_update(state_root=self.root / "state")["status"]
        )

    def test_cleanup_retains_ten_terminal_journals_and_unknown_paths(self) -> None:
        state = self.root / "state"
        journals = state / "journals"
        journals.mkdir(parents=True)
        for number in range(12):
            (journals / f"{number:02}.json").write_text('{"phase":"NEW_HEALTHY"}', encoding="utf-8")
        unknown = state / "staging/unknown"
        unknown.mkdir(parents=True)
        result = manager._cleanup_owned(state, keep_plan_id="11")
        self.assertEqual(10, len(list(journals.iterdir())))
        self.assertTrue(unknown.is_dir())
        self.assertEqual(10, result["retained_terminal_journals"])

    def test_virtual_environment_verification_never_uses_bootstrap_python(self) -> None:
        selected = self.root / "target/Scripts/python.exe"
        self.assertEqual(
            selected,
            manager._verification_python({"owner": "PIP_VENV", "python": str(selected)}),
        )


if __name__ == "__main__":
    unittest.main()
