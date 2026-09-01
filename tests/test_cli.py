from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing_pythonpath) if part
    )
    return subprocess.run(
        [sys.executable, "-m", "opencntx", *arguments],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def run_main(arguments: list[str], *, cwd: Path) -> tuple[int, str, str]:
    from opencntx.cli import main

    stdout = StringIO()
    stderr = StringIO()
    with chdir(cwd), redirect_stdout(stdout), redirect_stderr(stderr):
        result = main(arguments)
    return result, stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
    def test_in_process_core_route_covers_preview_pack_verify_and_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "README.md").write_text("# Core CLI\n", encoding="utf-8")

            initialized = run_main(["init"], cwd=root)
            preview = run_main(["pack", "--preview"], cwd=root)
            packed = run_main(["pack"], cwd=root)
            verified = run_main(["verify"], cwd=root)
            invalid_override = run_main(
                ["pack", "--preview", "--allow-secret", "invalid"], cwd=root
            )
            (root / "README.md").write_text("# Drift\n", encoding="utf-8")
            drift = run_main(["verify", ".opencntx\\latest"], cwd=root)

            self.assertEqual(initialized[0], 0, initialized[2])
            self.assertIn("Created:", initialized[1])
            self.assertEqual(preview[0], 0, preview[2])
            self.assertIn("PACK_WOULD_SUCCEED", preview[1])
            self.assertEqual(packed[0], 0, packed[2])
            self.assertIn("Built locally", packed[1])
            self.assertEqual(verified[0], 0, verified[2])
            self.assertIn("result: OK", verified[1])
            self.assertEqual(invalid_override[0], 2)
            self.assertIn("Invalid secret finding ID", invalid_override[2])
            self.assertEqual(drift[0], 1)
            self.assertIn("result: DRIFT OR INCOMPLETE", drift[1])

    def test_in_process_flow_route_covers_complete_restart_safe_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            restored = root / "restored"
            restored.mkdir()
            (root / "input.txt").write_text("input\n", encoding="utf-8")
            (root / "evidence.txt").write_text("green\n", encoding="utf-8")
            roadmap = {
                "format": "opencntx-continuity-roadmap",
                "format_version": 1,
                "project_id": "CLI-PROJECT",
                "roadmap_id": "CLI-ROADMAP",
                "title": "CLI flow",
                "assignments": [
                    {
                        "id": "TASK-1",
                        "title": "Task",
                        "detail": "Complete the task.",
                        "depends_on": [],
                        "touches": ["input.txt"],
                        "conflict": "NO_CONFLICT",
                        "migration": "",
                        "definition_of_done": ["Evidence is green"],
                    }
                ],
            }
            (root / "roadmap.json").write_text(json.dumps(roadmap), encoding="utf-8")

            preview = run_main(
                ["flow", "preview", "roadmap.json", "--root", str(root), "--json"],
                cwd=root,
            )
            started = run_main(
                [
                    "flow",
                    "start",
                    "roadmap.json",
                    "--approval",
                    "AUTO PILOT",
                    "--root",
                    str(root),
                    "--json",
                ],
                cwd=root,
            )
            status = run_main(["flow", "status", "--root", str(root)], cwd=root)
            capabilities = run_main(
                ["flow", "capabilities", "--root", str(root), "--json"], cwd=root
            )
            inspected_file = run_main(
                ["flow", "inspect", "file", "input.txt", "--root", str(root), "--json"],
                cwd=root,
            )
            inspected_json = run_main(
                ["flow", "inspect", "json", "roadmap.json", "--root", str(root), "--json"],
                cwd=root,
            )
            sync = run_main(["flow", "sync", "status", "--root", str(root)], cwd=root)
            delivery = run_main(
                ["flow", "host", "status", "--host", "HOST-A", "--root", str(root)],
                cwd=root,
            )
            delivery_value = json.loads(delivery[1])
            claimed = run_main(
                [
                    "flow",
                    "host",
                    "claim",
                    "--host",
                    "HOST-A",
                    "--delivery-digest",
                    delivery_value["delivery_digest"],
                    "--root",
                    str(root),
                ],
                cwd=root,
            )
            claim_value = json.loads(claimed[1])
            resumed = run_main(
                [
                    "flow",
                    "host",
                    "resume",
                    "--host",
                    "HOST-A",
                    "--claim-digest",
                    claim_value["claim_digest"],
                    "--root",
                    str(root),
                ],
                cwd=root,
            )
            advanced = run_main(
                [
                    "flow",
                    "advance",
                    "--outcome",
                    "PASS",
                    "--evidence",
                    "evidence.txt",
                    "--host",
                    "HOST-A",
                    "--claim-digest",
                    claim_value["claim_digest"],
                    "--root",
                    str(root),
                    "--json",
                ],
                cwd=root,
            )
            health = run_main(["flow", "health", "--root", str(root), "--json"], cwd=root)
            capsule = root / "flow.ocx"
            exported = run_main(
                ["flow", "capsule", "export", str(capsule), "--root", str(root)], cwd=root
            )
            verified = run_main(["flow", "capsule", "verify", str(capsule)], cwd=root)
            imported = run_main(
                ["flow", "capsule", "import", str(capsule), "--root", str(restored)],
                cwd=root,
            )

            for result in (
                preview,
                started,
                status,
                capabilities,
                inspected_file,
                inspected_json,
                sync,
                delivery,
                claimed,
                resumed,
                advanced,
                health,
                exported,
                verified,
                imported,
            ):
                self.assertEqual(result[0], 0, result[2])
            self.assertEqual(json.loads(started[1])["current_assignment"], "TASK-1")
            self.assertIn("Current assignment: TASK-1", status[1])
            self.assertEqual(json.loads(advanced[1])["status"], "COMPLETE")
            self.assertEqual(json.loads(health[1])["status"], "HEALTHY")
            self.assertEqual(json.loads(imported[1])["status"], "IMPORTED")

    def test_workspace_lifecycle_help_status_and_dry_run_are_bounded(self) -> None:
        from opencntx.workspace import init_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            help_result = run_cli("workspace", "lifecycle", "--help", cwd=workspace)
            status = run_cli(
                "workspace",
                "lifecycle",
                "status",
                "--json",
                "--trust-profile",
                "shared-team",
                "--root",
                str(workspace),
                cwd=workspace,
            )
            before = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            migration = run_cli(
                "workspace",
                "lifecycle",
                "migrate",
                "--dry-run",
                "--json",
                "--root",
                str(workspace),
                cwd=workspace,
            )
            after = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }

            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("{status,migrate,cleanup,restore}", help_result.stdout)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(
                json.loads(status.stdout)["trust_status"], "UNSUPPORTED_FOR_AUTHORIZATION"
            )
            self.assertEqual(migration.returncode, 0, migration.stderr)
            self.assertEqual(json.loads(migration.stdout)["operation"], "ALREADY_CURRENT")
            self.assertEqual(before, after)

    def test_package_versions_match(self) -> None:
        with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as project_file:
            project_version = tomllib.load(project_file)["project"]["version"]

        package_globals = runpy.run_path(SOURCE_ROOT / "opencntx" / "__init__.py")

        self.assertEqual(package_globals["__version__"], project_version)

    def test_help_works(self) -> None:
        result = run_cli("--help", cwd=REPOSITORY_ROOT)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("{init,pack,verify,workspace,flow,layout}", result.stdout)
        self.assertIn("explicit, and verifiable context package", result.stdout)
        self.assertLess(result.stdout.index("init"), result.stdout.index("workspace"))
        self.assertIn("Stable workspace", result.stdout)
        self.assertNotIn("Advanced / Alpha", result.stdout)

    def test_init_creates_expected_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)

            result = run_cli("init", cwd=project_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            config = (project_root / "opencntx.toml").read_text(encoding="utf-8")
            self.assertIn('[task]\ngoal = "Describe the one concrete task"', config)
            self.assertIn("max_files = 25", config)
            self.assertIn("max_bytes = 100000", config)

    def test_init_never_overwrites_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            config_path = project_root / "opencntx.toml"
            config_path.write_text("bewaar mij\n", encoding="utf-8")

            result = run_cli("init", cwd=project_root)

            self.assertEqual(result.returncode, 2)
            self.assertIn("nothing was overwritten", result.stderr)
            self.assertEqual(config_path.read_text(encoding="utf-8"), "bewaar mij\n")

    def test_workspace_doctor_is_read_only_on_a_new_workspace(self) -> None:
        from opencntx.workspace import init_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            before = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            result = run_cli("workspace", "doctor", "--root", str(workspace), cwd=workspace)
            after = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Workspace doctor: HEALTHY", result.stdout)
            self.assertIn("Read-only inspection", result.stdout)
            self.assertEqual(before, after)

    def test_workspace_doctor_exit_codes_distinguish_findings_and_invalid_input(self) -> None:
        from opencntx.workspace import init_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            active = workspace / ".opencntx" / "transactions" / "active"
            active.mkdir(parents=True)
            (active / "unknown-entry").mkdir()
            finding = run_cli("workspace", "doctor", "--root", str(workspace), cwd=workspace)
            invalid = run_cli(
                "workspace",
                "doctor",
                "--root",
                str(workspace / "missing"),
                cwd=workspace,
            )
            self.assertEqual(finding.returncode, 1, finding.stderr)
            self.assertIn("UNSAFE_UNKNOWN_STATE", finding.stdout)
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("doctor_failed", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
