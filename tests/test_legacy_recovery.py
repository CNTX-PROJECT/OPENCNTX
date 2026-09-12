from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from opencntx.continuity import (
    ContinuityError,
    _writer_lock,
    execution_state_capsule,
    record_execution_checkpoint,
)
from opencntx.legacy_recovery import stage_legacy_recovery
from tests import test_continuity_version as fixtures

bytes_map = fixtures.bytes_map


class LegacyRecoveryTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ContinuityVersionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        state = execution_state_capsule(self.root)
        record_execution_checkpoint(
            self.root,
            checkpoint_id="CURRENT-WRITER",
            current_internal_task="VERIFY",
            next_internal_action="Verify legacy recovery",
            evidence_paths=["input.txt"],
            expected_state_digest=state["state_digest"],
        )
        self.state = execution_state_capsule(self.root)
        self.before = bytes_map(self.root)
        self.target = fixture.directory / "legacy-recovery"

    def stage(self):
        return stage_legacy_recovery(
            self.root, destination=self.target, expected_state_digest=self.state["state_digest"]
        )

    def test_staging_preserves_source_and_removes_only_copy_markers(self):
        result = self.stage()
        self.assertEqual(bytes_map(self.root), self.before)
        self.assertTrue(result["source_unchanged"])
        self.assertFalse(result["runtime_switched"])
        copied = bytes_map(Path(result["staged_project"]))
        removed = set(result["removed_copy_markers"])
        self.assertEqual(
            copied, {key: value for key, value in self.before.items() if key not in removed}
        )

    def test_active_writer_is_not_unlocked(self):
        with (
            _writer_lock(self.root / ".opencntx/continuity/.operation.lock"),
            self.assertRaises((ContinuityError, PermissionError)),
        ):
            self.stage()
        self.assertFalse(self.target.exists())
        self.assertEqual(bytes_map(self.root), self.before)

    def test_unknown_marker_and_existing_target_are_preserved(self):
        marker = self.root / ".opencntx/continuity/.operation.lock"
        marker.write_bytes(b"old writer")
        with self.assertRaises(ContinuityError):
            self.stage()
        self.assertEqual(marker.read_bytes(), b"old writer")
        self.target.mkdir()
        (self.target / "owner.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(ContinuityError):
            self.stage()
        self.assertEqual((self.target / "owner.txt").read_text(), "keep")

    def test_stale_state_and_nested_destination_do_not_create_copy(self):
        with self.assertRaises(ContinuityError):
            stage_legacy_recovery(
                self.root, destination=self.target, expected_state_digest="0" * 64
            )
        with self.assertRaises(ContinuityError):
            stage_legacy_recovery(
                self.root,
                destination=self.root / "nested",
                expected_state_digest=self.state["state_digest"],
            )
        self.assertFalse(self.target.exists())
        self.assertEqual(bytes_map(self.root), self.before)

    def test_newer_format_restores_retained_snapshot_for_legacy_writer(self):
        self.fixture.upgrade()
        before = bytes_map(self.fixture.staged)
        result = stage_legacy_recovery(
            self.fixture.staged,
            destination=self.target,
            expected_state_digest=self.fixture.state["state_digest"],
        )
        self.assertTrue(result["legacy_roadmap_restored"])
        self.assertEqual(bytes_map(self.fixture.staged), before)
        staged_roadmap = Path(result["staged_project"]) / ".opencntx/continuity/roadmaps/roadmap.json"
        self.assertEqual(
            json.loads(staged_roadmap.read_text(encoding="utf-8"))["format"],
            "opencntx-continuity-roadmap",
        )

    def test_newer_format_without_valid_snapshot_remains_blocked_without_mutation(self):
        self.fixture.upgrade()
        roadmap_path = self.fixture.staged / ".opencntx/continuity/roadmaps/roadmap.json"
        value = json.loads(roadmap_path.read_text(encoding="utf-8"))
        value["legacy_sha256"] = "f" * 64
        roadmap_path.write_text(json.dumps(value), encoding="utf-8")
        before = bytes_map(self.fixture.staged)
        with self.assertRaisesRegex(ContinuityError, "valid retained pre-upgrade snapshot"):
            stage_legacy_recovery(
                self.fixture.staged,
                destination=self.target,
                expected_state_digest=self.fixture.state["state_digest"],
            )
        self.assertEqual(bytes_map(self.fixture.staged), before)

    @unittest.skipUnless(os.environ.get("R15_LEGACY_SOURCE"), "Actual legacy source required")
    def test_actual_legacy_writer_can_continue_on_recovery_copy(self):
        result = self.stage()
        source = Path(os.environ["R15_LEGACY_SOURCE"]).resolve(strict=True)
        code = fixtures.legacy_writer_code("OLD-RESUMED")
        before_state = execution_state_capsule(Path(result["staged_project"]))
        child = subprocess.run(
            [sys.executable, "-B", "-c", code, result["staged_project"], str(source)],
            env=dict(os.environ, PYTHONPATH=str(source)),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        after_state = execution_state_capsule(Path(result["staged_project"]))
        self.assertNotEqual(before_state["state_digest"], after_state["state_digest"])
        self.assertEqual(bytes_map(self.root), self.before)

    @unittest.skipUnless(os.environ.get("R15_LEGACY_SOURCE"), "Actual legacy source required")
    def test_actual_legacy_writer_can_continue_after_v2_upgrade(self):
        self.fixture.upgrade()
        result = stage_legacy_recovery(
            self.fixture.staged,
            destination=self.target,
            expected_state_digest=self.fixture.state["state_digest"],
        )
        source = Path(os.environ["R15_LEGACY_SOURCE"]).resolve(strict=True)
        code = fixtures.legacy_writer_code("OLD-V2-RESUMED")
        before_state = execution_state_capsule(Path(result["staged_project"]))
        child = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                code,
                result["staged_project"],
                str(source),
            ],
            env=dict(os.environ, PYTHONPATH=str(source)),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(child.returncode, 0, child.stderr)
        after_state = execution_state_capsule(Path(result["staged_project"]))
        self.assertNotEqual(before_state["state_digest"], after_state["state_digest"])
        self.assertEqual(
            json.loads(
                (Path(result["staged_project"])
                 / ".opencntx/continuity/roadmaps/roadmap.json").read_text(encoding="utf-8")
            )["format"],
            "opencntx-continuity-roadmap",
        )

    def test_cli_stages_copy_without_switching_runtime(self):
        import contextlib
        import io
        import json

        from opencntx.cli import main

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(
                [
                    "flow",
                    "legacy-stage",
                    "--root",
                    str(self.root),
                    "--destination",
                    str(self.target),
                    "--expected-state",
                    self.state["state_digest"],
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(output.getvalue())["status"], "STAGED_REQUIRES_LEGACY_VALIDATION"
        )
        self.assertEqual(bytes_map(self.root), self.before)
