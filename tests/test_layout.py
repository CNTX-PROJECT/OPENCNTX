from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from opencntx.core import OpenCntxError
from opencntx.layout import SCHEMA_ID, audit_layout, load_order_contract

ROOT = Path(__file__).resolve().parents[1]


def contract_value() -> dict[str, object]:
    return {
        "contract_id": "TEST-ORDER",
        "duplicate_ownership": {
            "allowed_sha256": [],
            "enabled": True,
            "minimum_bytes": 1,
        },
        "folder_roles": [
            {
                "id": "REPOSITORIES",
                "owner": "PROJECT",
                "path": "01-REPOSITORIES",
                "required": True,
                "root": "PROJECT",
            }
        ],
        "format": "opencntx-order-contract",
        "format_version": 1,
        "naming": {
            "directory_pattern": r"[A-Z0-9][A-Z0-9._-]*",
            "exempt": [".git", ".git/**"],
            "file_pattern": r"[A-Za-z0-9][A-Za-z0-9._-]*",
        },
        "path_allowlist": [{"owner": "PROJECT", "pattern": "**", "root": "PROJECT"}],
        "revision": 1,
        "roots": [
            {
                "id": "PROJECT",
                "path": "PROJECT",
                "required": True,
                "role": "PROJECT_CONTAINER",
            }
        ],
        "schema_id": SCHEMA_ID,
        "stop_rule": {
            "acceptance": "ZERO_FINDINGS",
            "maximum_bytes": 1_000_000,
            "maximum_files": 100,
            "maximum_findings": 100,
        },
    }


def write_contract(parent: Path, value: dict[str, object] | None = None) -> Path:
    path = parent / "order-contract.json"
    path.write_text(
        json.dumps(contract_value() if value is None else value, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )
    return path


def snapshot(parent: Path) -> dict[str, bytes]:
    return {
        path.relative_to(parent).as_posix(): path.read_bytes()
        for path in parent.rglob("*")
        if path.is_file()
    }


class LayoutContractTests(unittest.TestCase):
    def test_green_audit_is_deterministic_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            repository = base / "PROJECT" / "01-REPOSITORIES"
            repository.mkdir(parents=True)
            (repository / "README.md").write_text("unique\n", encoding="utf-8")
            contract = write_contract(base)
            before = snapshot(base)

            first = audit_layout(contract, base)
            second = audit_layout(contract, base)

            self.assertTrue(first.ok)
            self.assertEqual("GREEN", first.status)
            self.assertEqual(first, second)
            self.assertEqual(before, snapshot(base))

    def test_disorder_name_ownership_role_and_duplicates_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            project = base / "PROJECT"
            project.mkdir()
            (project / "bad folder").mkdir()
            (project / "bad folder" / "copy one.txt").write_text("same", encoding="utf-8")
            (project / "copy two.txt").write_text("same", encoding="utf-8")
            value = contract_value()
            value["path_allowlist"] = [
                {"owner": "PROJECT", "pattern": "01-REPOSITORIES", "root": "PROJECT"},
                {"owner": "PROJECT", "pattern": "01-REPOSITORIES/**", "root": "PROJECT"},
            ]
            report = audit_layout(write_contract(base, value), base)

            codes = [finding.code for finding in report.findings]
            self.assertEqual("NEEDS_ACTION", report.status)
            self.assertIn("FOLDER_ROLE_MISSING", codes)
            self.assertIn("NAME_POLICY", codes)
            self.assertIn("PATH_NOT_ALLOWED", codes)
            self.assertIn("DUPLICATE_CONTENT", codes)

    def test_scan_bound_stops_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            project = base / "PROJECT" / "01-REPOSITORIES"
            project.mkdir(parents=True)
            (project / "A.txt").write_text("a", encoding="utf-8")
            (project / "B.txt").write_text("b", encoding="utf-8")
            value = contract_value()
            value["stop_rule"]["maximum_files"] = 1  # type: ignore[index]

            report = audit_layout(write_contract(base, value), base)

            self.assertEqual("STOPPED", report.status)
            self.assertIn("SCAN_BOUND_REACHED", {item.code for item in report.findings})

    def test_contract_is_closed_versioned_and_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            unknown = contract_value()
            unknown["surprise"] = True
            with self.assertRaises(OpenCntxError):
                load_order_contract(write_contract(base, unknown))

            duplicate = base / "duplicate.json"
            duplicate.write_text('{"format":1,"format":1}', encoding="utf-8")
            with self.assertRaises(OpenCntxError):
                load_order_contract(duplicate)

    @unittest.skipIf(os.name == "nt", "POSIX symlink creation has different Windows privileges")
    def test_directory_links_are_reported_and_never_followed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            repository = base / "PROJECT" / "01-REPOSITORIES"
            repository.mkdir(parents=True)
            outside = base / "OUTSIDE"
            outside.mkdir()
            (outside / "SECRET.txt").write_text("outside", encoding="utf-8")
            (repository / "LINK").symlink_to(outside, target_is_directory=True)

            report = audit_layout(write_contract(base), base)

            self.assertIn("LINK_NOT_FOLLOWED", {item.code for item in report.findings})
            self.assertEqual(0, report.files)


class LayoutCliTests(unittest.TestCase):
    def _run(self, *arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "opencntx", *arguments],
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_audit_reports_findings_but_verify_requires_green(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            (base / "PROJECT").mkdir()
            contract = write_contract(base)
            before = snapshot(base)

            audit = self._run(
                "layout",
                "audit",
                "--contract",
                str(contract),
                "--base",
                str(base),
                "--json",
                cwd=base,
            )
            verify = self._run(
                "layout",
                "verify",
                "--contract",
                str(contract),
                "--base",
                str(base),
                "--json",
                cwd=base,
            )

            self.assertEqual(0, audit.returncode, audit.stderr)
            self.assertEqual(1, verify.returncode, verify.stderr)
            self.assertTrue(json.loads(audit.stdout)["read_only"])
            self.assertEqual("NEEDS_ACTION", json.loads(verify.stdout)["status"])
            self.assertEqual(before, snapshot(base))


if __name__ == "__main__":
    unittest.main()
