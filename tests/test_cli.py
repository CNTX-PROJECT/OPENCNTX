from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import tempfile
import tomllib
import unittest
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


class CliTests(unittest.TestCase):
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
        self.assertIn("{init,pack,verify,workspace,flow}", result.stdout)
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
