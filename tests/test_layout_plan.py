from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from opencntx.core import OpenCntxError
from opencntx.layout_plan import (
    MANIFEST_SCHEMA_ID,
    PLAN_SCHEMA_ID,
    build_layout_plan,
    verify_layout_plan,
)

ROOT = Path(__file__).resolve().parents[1]


def manifest_value() -> dict[str, object]:
    return {
        "format": "opencntx-layout-migration",
        "format_version": 1,
        "maximum_bytes": 1_000_000,
        "maximum_files": 100,
        "maximum_path_length": 240,
        "minimum_free_bytes": 1_000,
        "operations": [
            {"destination": "TARGET/PROJECT", "id": "MOVE-PROJECT", "source": "SOURCE"}
        ],
        "plan_id": "LAYOUT-TEST",
        "protected_paths": ["PROTECTED"],
        "schema_id": MANIFEST_SCHEMA_ID,
    }


def write_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


class LayoutPlanTests(unittest.TestCase):
    def _ready_project(self, base: Path) -> Path:
        source = base / "SOURCE"
        (source / "DOCS").mkdir(parents=True)
        (source / "README.md").write_text("bounded\n", encoding="utf-8")
        (source / "DOCS" / "GUIDE.md").write_text("guide\n", encoding="utf-8")
        return write_json(base / "migration.json", manifest_value())

    def test_equal_inputs_produce_equal_read_only_rollbackable_plans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            manifest = self._ready_project(base)
            before = snapshot(base)

            first = build_layout_plan(manifest, base)
            second = build_layout_plan(manifest, base)

            self.assertEqual(first, second)
            self.assertEqual("READY", first["status"])
            self.assertTrue(first["read_only"])
            self.assertEqual([], first["findings"])
            self.assertEqual(PLAN_SCHEMA_ID, first["schema_id"])
            operation = first["operations"][0]
            self.assertEqual(operation["source"], operation["rollback"]["to"])
            self.assertEqual(operation["destination"], operation["rollback"]["from"])
            self.assertRegex(operation["source_state"]["tree_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(operation["source_state"]["acl"]["digest"], r"^[0-9a-f]{64}$")
            self.assertIn("process_locks", operation["source_state"])
            self.assertEqual(before, snapshot(base))

    def test_saved_plan_verifies_then_source_change_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            manifest = self._ready_project(base)
            plan_path = write_json(base / "plan.json", build_layout_plan(manifest, base))

            verified = verify_layout_plan(plan_path)
            (base / "SOURCE" / "README.md").write_text("changed\n", encoding="utf-8")
            stale = verify_layout_plan(plan_path)

            self.assertEqual("VERIFIED", verified["status"])
            self.assertEqual("STALE", stale["status"])
            self.assertIn("SOURCE_CHANGED", {item["code"] for item in stale["findings"]})
            self.assertTrue(verified["read_only"])

    def test_collision_path_length_protection_and_overlap_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            manifest = self._ready_project(base)
            value = json.loads(manifest.read_text(encoding="utf-8"))
            (base / "TARGET" / "PROJECT").mkdir(parents=True)
            value["maximum_path_length"] = 64
            value["protected_paths"] = ["SOURCE/DOCS"]
            value["operations"].append(
                {"destination": "TARGET/PROJECT/CHILD", "id": "MOVE-CHILD", "source": "SOURCE/DOCS"}
            )

            plan = build_layout_plan(write_json(manifest, value), base)
            codes = {item["code"] for item in plan["findings"]}

            self.assertEqual("BLOCKED", plan["status"])
            self.assertIn("DESTINATION_COLLISION", codes)
            self.assertIn("DESTINATION_OVERLAP", codes)
            self.assertIn("PATH_LENGTH_EXCEEDED", codes)
            self.assertIn("PROTECTED_PATH", codes)

    def test_unresolved_paths_and_changed_plan_digest_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            manifest = self._ready_project(base)
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["operations"][0]["destination"] = "%UNRESOLVED%/PROJECT"
            with self.assertRaisesRegex(OpenCntxError, "unresolved variable or wildcard"):
                build_layout_plan(write_json(manifest, value), base)

            value = manifest_value()
            write_json(manifest, value)
            plan = build_layout_plan(manifest, base)
            plan["plan_id"] = "CHANGED"
            with self.assertRaisesRegex(OpenCntxError, "identity or digest"):
                verify_layout_plan(write_json(base / "changed-plan.json", plan))

    @unittest.skipIf(os.name == "nt", "POSIX symlink creation differs from Windows")
    def test_source_link_is_recorded_but_never_followed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            manifest = self._ready_project(base)
            outside = base / "OUTSIDE"
            outside.mkdir()
            (outside / "PRIVATE.md").write_text("outside\n", encoding="utf-8")
            (base / "SOURCE" / "LINK").symlink_to(outside, target_is_directory=True)

            plan = build_layout_plan(manifest, base)

            self.assertEqual("BLOCKED", plan["status"])
            self.assertIn("LINK_PRESENT", {item["code"] for item in plan["findings"]})
            self.assertEqual(2, plan["operations"][0]["source_state"]["files"])

    def test_git_identity_is_bound_without_remote_url_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            manifest = self._ready_project(base)
            source = base / "SOURCE"
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.name", "Example"], check=True)
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "example@example.invalid"],
                check=True,
            )
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-qm", "initial"], check=True)
            subprocess.run(
                ["git", "-C", str(source), "remote", "add", "origin", "https://example.invalid/repository.git"],
                check=True,
            )

            plan = build_layout_plan(manifest, base)
            identity = plan["operations"][0]["source_state"]["git"][0]

            self.assertEqual("READY", plan["status"])
            self.assertRegex(identity["head"], r"^[0-9a-f]{40}$")
            self.assertFalse(identity["dirty"])
            self.assertNotIn("example.invalid", json.dumps(plan))
            self.assertRegex(identity["remote_digests"][0]["url_sha256"], r"^[0-9a-f]{64}$")

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "remote",
                    "set-url",
                    "origin",
                    "https://user:synthetic-password@example.invalid/repository.git",
                ],
                check=True,
            )
            blocked = build_layout_plan(manifest, base)
            rendered = json.dumps(blocked)
            self.assertEqual("BLOCKED", blocked["status"])
            self.assertIn("GIT_REMOTE_CREDENTIAL", {item["code"] for item in blocked["findings"]})
            self.assertNotIn("synthetic-password", rendered)

    @unittest.skipUnless(os.name == "nt", "Windows exclusive handles define this lock proof")
    def test_windows_process_lock_blocks_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            manifest = self._ready_project(base)
            locked_path = base / "SOURCE" / "README.md"
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            create_file = kernel32.CreateFileW
            create_file.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.c_void_p,
            ]
            create_file.restype = ctypes.c_void_p
            handle = create_file(str(locked_path), 0x80000000, 0, None, 3, 0x80, None)
            self.assertNotEqual(ctypes.c_void_p(-1).value, handle)
            try:
                plan = build_layout_plan(manifest, base)
            finally:
                kernel32.CloseHandle(ctypes.c_void_p(handle))

            codes = {item["code"] for item in plan["findings"]}
            self.assertEqual("BLOCKED", plan["status"])
            self.assertIn("PROCESS_LOCK_PRESENT", codes)

    def test_schemas_are_closed_and_packaged(self) -> None:
        for name, schema_id in (
            ("layout-migration-v1.schema.json", MANIFEST_SCHEMA_ID),
            ("layout-plan-v1.schema.json", PLAN_SCHEMA_ID),
        ):
            schema = json.loads(
                (ROOT / "src" / "opencntx" / "schemas" / name).read_text(encoding="utf-8")
            )
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema_id, schema["properties"]["schema_id"]["const"])


class LayoutPlanCliTests(unittest.TestCase):
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

    def test_cli_preview_and_verify_are_digest_bound_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            manifest = LayoutPlanTests()._ready_project(base)
            before = snapshot(base)
            preview = self._run(
                "layout",
                "plan",
                "preview",
                "--manifest",
                str(manifest),
                "--base",
                str(base),
                cwd=base,
            )
            self.assertEqual(0, preview.returncode, preview.stderr)
            plan = json.loads(preview.stdout)
            self.assertEqual(before, snapshot(base))
            plan_path = write_json(base / "plan.json", plan)
            verify = self._run(
                "layout", "plan", "verify", "--plan", str(plan_path), cwd=base
            )
            self.assertEqual(0, verify.returncode, verify.stderr)
            self.assertEqual("VERIFIED", json.loads(verify.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
