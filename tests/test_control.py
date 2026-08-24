from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.control import (
    CONTROL_BLOCK_MAX_BYTES,
    CONTROL_END,
    CONTROL_SNAPSHOT_HEADER,
    CONTROL_START,
    ControlError,
    _render_snapshot,
    inspect_control,
    refresh_control_snapshot,
)
from opencntx.workspace import init_workspace


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing_pythonpath) if part
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "opencntx", *arguments],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


class ControlTests(unittest.TestCase):
    def make_workspace(self, parent: Path) -> Path:
        workspace = parent / "project"
        init_workspace(workspace)
        return workspace

    def roadmap(self, workspace: Path) -> Path:
        return workspace / "CONTROL" / "ROADMAP.md"

    def snapshot(self, workspace: Path) -> Path:
        return workspace / ".opencntx" / "control-snapshot.md"

    def receipts(self, workspace: Path) -> set[str]:
        return {
            item.name for item in (workspace / ".opencntx" / "receipts").iterdir() if item.is_file()
        }

    def test_new_workspace_has_one_marker_pair_and_deterministic_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            roadmap = self.roadmap(workspace).read_bytes()
            self.assertEqual(roadmap.count(CONTROL_START), 1)
            self.assertEqual(roadmap.count(CONTROL_END), 1)

            first = refresh_control_snapshot(workspace)
            first_bytes = self.snapshot(workspace).read_bytes()
            second = refresh_control_snapshot(workspace)
            second_bytes = self.snapshot(workspace).read_bytes()

            self.assertEqual(first.status, "CONTROL_SNAPSHOT_REFRESHED")
            self.assertEqual(first.mode, "COMPACT_MARKED")
            self.assertEqual(first.snapshot_sha256, second.snapshot_sha256)
            self.assertEqual(first_bytes, second_bytes)
            self.assertTrue(first_bytes.startswith(CONTROL_SNAPSHOT_HEADER))
            self.assertIn(CONTROL_START, first_bytes)
            self.assertIn(CONTROL_END, first_bytes)
            self.assertIn(b"grants no OWNER authority", first_bytes)

    def test_exact_legacy_snapshot_is_accepted_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            owner = (workspace / "CONTROL" / "OWNER.md").read_bytes()
            roadmap = self.roadmap(workspace).read_bytes()
            current = (workspace / "CONTROL" / "CURRENT.md").read_bytes()
            start = roadmap.index(CONTROL_START)
            end = roadmap.index(CONTROL_END) + len(CONTROL_END)
            legacy = _render_snapshot(
                owner=owner,
                roadmap=roadmap,
                current=current,
                block=roadmap[start:end],
                legacy=True,
            )
            self.snapshot(workspace).write_bytes(legacy)
            before = self.snapshot(workspace).read_bytes()

            state = inspect_control(workspace, require_snapshot=True)

            self.assertEqual(state.snapshot_bytes, legacy)
            self.assertEqual(self.snapshot(workspace).read_bytes(), before)

    def test_inspection_is_read_only_and_refresh_receipt_has_no_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            before = self.receipts(workspace)
            state = inspect_control(workspace)
            self.assertEqual(state.mode, "COMPACT_MARKED")
            self.assertEqual(self.receipts(workspace), before)
            self.assertFalse(self.snapshot(workspace).exists())

            result = refresh_control_snapshot(workspace)
            receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "CONTROL_SNAPSHOT_REFRESHED")
            self.assertEqual(receipt["mode"], "COMPACT_MARKED")
            self.assertEqual(receipt["snapshot_path"], ".opencntx/control-snapshot.md")
            self.assertNotIn(str(workspace), result.receipt_path.read_text(encoding="utf-8"))
            completed = workspace / ".opencntx" / "transactions" / "completed"
            self.assertEqual(len(list(completed.iterdir())), 1)
            self.assertEqual(
                list((workspace / ".opencntx" / "transactions" / "locks").rglob("*.lock")), []
            )

    def test_exact_block_byte_limit_is_accepted_and_one_more_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            overhead = len(CONTROL_START) + 1 + len(CONTROL_END)
            exact = (
                CONTROL_START + b"\n" + b"x" * (CONTROL_BLOCK_MAX_BYTES - overhead) + CONTROL_END
            )
            self.assertEqual(len(exact), CONTROL_BLOCK_MAX_BYTES)
            self.roadmap(workspace).write_bytes(exact)
            state = inspect_control(workspace)
            self.assertEqual(state.block_bytes, CONTROL_BLOCK_MAX_BYTES)

            self.roadmap(workspace).write_bytes(
                CONTROL_START
                + b"\n"
                + b"x" * (CONTROL_BLOCK_MAX_BYTES - overhead + 1)
                + CONTROL_END
            )
            with self.assertRaisesRegex(ControlError, "te groot") as context:
                inspect_control(workspace)
            self.assertEqual(context.exception.code, "control_block_too_large")

    def test_no_markers_is_legacy_and_refresh_does_not_create_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            self.roadmap(workspace).write_text(
                "# ROADMAP\n\n## Actuele opdracht\n\nGeen.\n",
                encoding="utf-8",
                newline="\n",
            )
            result = refresh_control_snapshot(workspace)
            self.assertEqual(result.status, "CONTROL_LEGACY_CONFIRMED")
            self.assertEqual(result.mode, "LEGACY_FULL_ROADMAP")
            self.assertIsNone(result.snapshot_path)
            self.assertFalse(self.snapshot(workspace).exists())

    def test_partial_duplicate_reversed_and_nested_markers_fail_closed(self) -> None:
        invalid = (
            CONTROL_START + b"\nzonder eind",
            CONTROL_END + b"\nzonder start",
            CONTROL_START + b"\na" + CONTROL_START + b"\nb" + CONTROL_END,
            CONTROL_START + b"\na" + CONTROL_END + b"\n" + CONTROL_END,
            CONTROL_END + b"\nomgekeerd\n" + CONTROL_START,
        )
        for number, content in enumerate(invalid):
            with self.subTest(case=number), tempfile.TemporaryDirectory() as temporary:
                workspace = self.make_workspace(Path(temporary))
                self.roadmap(workspace).write_bytes(content)
                with self.assertRaises(ControlError) as context:
                    inspect_control(workspace)
                self.assertEqual(context.exception.code, "control_markers_invalid")

    def test_invalid_utf8_nul_and_control_character_are_rejected(self) -> None:
        invalid = (b"\xff", b"ok\x00no", b"ok\x01no")
        for content in invalid:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temporary:
                workspace = self.make_workspace(Path(temporary))
                self.roadmap(workspace).write_bytes(content)
                with self.assertRaises(ControlError) as context:
                    inspect_control(workspace)
                self.assertEqual(context.exception.code, "control_file_invalid")

    def test_unknown_snapshot_bytes_are_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            path = self.snapshot(workspace)
            path.write_bytes(b"OWNER DATA\n")
            with self.assertRaises(ControlError) as context:
                refresh_control_snapshot(workspace)
            self.assertEqual(context.exception.code, "control_snapshot_unmanaged")
            self.assertEqual(path.read_bytes(), b"OWNER DATA\n")

    def test_atomic_publish_failure_preserves_previous_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            refresh_control_snapshot(workspace)
            previous = self.snapshot(workspace).read_bytes()
            current = workspace / "CONTROL" / "CURRENT.md"
            current.write_text(
                current.read_text(encoding="utf-8") + "\n- Opmerking: gewijzigd\n",
                encoding="utf-8",
                newline="\n",
            )
            with (
                mock.patch("opencntx.control.os.replace", side_effect=OSError("test")),
                self.assertRaises(ControlError) as context,
            ):
                refresh_control_snapshot(workspace)
            self.assertEqual(context.exception.code, "control_snapshot_write_failed")
            self.assertEqual(self.snapshot(workspace).read_bytes(), previous)
            leftovers = list((workspace / ".opencntx").glob(".control-snapshot.md.*.tmp"))
            self.assertEqual(leftovers, [])

    def test_snapshot_drift_is_reported_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            refresh_control_snapshot(workspace)
            path = self.snapshot(workspace)
            path.write_bytes(path.read_bytes() + b"drift\n")
            before = path.read_bytes()
            with self.assertRaises(ControlError) as context:
                inspect_control(workspace, require_snapshot=True)
            self.assertEqual(context.exception.code, "control_snapshot_stale")
            self.assertEqual(path.read_bytes(), before)

    def test_snapshot_symlink_is_rejected_when_platform_allows_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.make_workspace(Path(temporary_directory))
            target = workspace / "outside.md"
            target.write_text("outside", encoding="utf-8")
            try:
                self.snapshot(workspace).symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks zijn niet beschikbaar op dit platform.")
            with self.assertRaises(ControlError) as context:
                refresh_control_snapshot(workspace)
            self.assertEqual(context.exception.code, "control_snapshot_unmanaged")
            self.assertEqual(target.read_text(encoding="utf-8"), "outside")

    def test_cli_refresh_is_explicit_for_compact_and_legacy_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace = self.make_workspace(parent)
            compact = run_cli(
                "workspace", "control", "refresh", "--root", str(workspace), cwd=parent
            )
            self.assertEqual(compact.returncode, 0, compact.stderr)
            self.assertIn("CONTROL_SNAPSHOT_REFRESHED: COMPACT_MARKED", compact.stdout)
            self.assertIn("Derived evidence", compact.stdout)

            self.roadmap(workspace).write_text(
                "# ROADMAP\n\nGeen actieve opdracht.\n",
                encoding="utf-8",
                newline="\n",
            )
            legacy = run_cli(
                "workspace", "control", "refresh", "--root", str(workspace), cwd=parent
            )
            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            self.assertIn("CONTROL_LEGACY_CONFIRMED: LEGACY_FULL_ROADMAP", legacy.stdout)


if __name__ == "__main__":
    unittest.main()
