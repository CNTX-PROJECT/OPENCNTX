from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib import resources
from pathlib import Path

from opencntx.continuity import (
    ContinuityError,
    _value_digest,
    execution_state_capsule,
    record_execution_checkpoint,
    start_flow,
)
from opencntx.continuity_version import unwrap_goal_storage, upgrade_goal_storage
from tests.test_session_continuity import roadmap


def bytes_map(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def legacy_writer_code(checkpoint_id: str) -> str:
    """Use the actual writer API available in the immutable historical source."""
    return (
        "from pathlib import Path; import json,sys; import opencntx.continuity as c; "
        "assert Path(c.__file__).resolve().is_relative_to(Path(sys.argv[2])); "
        "root=Path(sys.argv[1]); "
        "has_checkpoint=hasattr(c,'execution_state_capsule') and "
        "hasattr(c,'record_execution_checkpoint'); "
        "s=c.execution_state_capsule(root) if has_checkpoint else None; "
        f"r=c.record_execution_checkpoint(root,checkpoint_id='{checkpoint_id}',"
        "current_internal_task='VERIFY',next_internal_action='Verify legacy',"
        "evidence_paths=['input.txt'],expected_state_digest=s['state_digest']) "
        "if has_checkpoint else c.advance_flow(root,outcome='PASS',evidence_paths=['input.txt']); "
        "print(json.dumps({'api':'checkpoint' if has_checkpoint else 'advance_flow'}))"
    )


class ContinuityVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "legacy-original"
        self.root.mkdir()
        (self.root / "input.txt").write_bytes(b"original")
        start_flow(self.root, roadmap(self.root / "roadmap.json"), "AUTO PILOT")
        self.original = bytes_map(self.root)
        self.staged = self.directory / "isolated-v2"
        shutil.copytree(self.root, self.staged)
        self.state = execution_state_capsule(self.staged)

    def upgrade(self):
        return upgrade_goal_storage(
            self.staged,
            expected_state_digest=self.state["state_digest"],
            approval=f"UPGRADE GOAL STORAGE {self.state['state_digest']}",
        )

    def test_exact_v1_bytes_retained_new_writer_and_idempotent_migration(self) -> None:
        envelope = self.upgrade()
        self.assertEqual(self.upgrade(), envelope)
        self.assertEqual(
            base64.b64decode(envelope["legacy_roadmap_base64"]),
            self.original[".opencntx/continuity/roadmaps/roadmap.json"],
        )
        self.assertEqual(execution_state_capsule(self.staged), self.state)
        record_execution_checkpoint(
            self.staged,
            checkpoint_id="V2-CHECK",
            current_internal_task="VERIFY",
            next_internal_action="Verify migrated state",
            evidence_paths=["input.txt"],
            expected_state_digest=self.state["state_digest"],
        )
        self.assertEqual(execution_state_capsule(self.staged)["checkpoint_number"], 1)
        self.assertEqual(bytes_map(self.root), self.original)

    def test_unapproved_stale_boolean_unknown_and_tampered_versions_refused(self) -> None:
        with self.assertRaises(ContinuityError):
            upgrade_goal_storage(
                self.staged, expected_state_digest=self.state["state_digest"], approval="yes"
            )
        with self.assertRaises(ContinuityError):
            upgrade_goal_storage(
                self.staged,
                expected_state_digest="a" * 64,
                approval=f"UPGRADE GOAL STORAGE {'a' * 64}",
            )
        envelope = self.upgrade()
        for version in (1, 3, True, "2"):
            changed = envelope | {"format_version": version}
            changed["envelope_digest"] = _value_digest(
                {k: v for k, v in changed.items() if k != "envelope_digest"}
            )
            with self.subTest(version=version), self.assertRaises(ContinuityError):
                unwrap_goal_storage(changed)
        with self.assertRaises(ContinuityError):
            unwrap_goal_storage(envelope | {"legacy_sha256": "f" * 64})
        self.assertEqual(bytes_map(self.root), self.original)

    def test_shipped_envelope_schema_and_catalog_match_actual_fields(self) -> None:
        value = self.upgrade()
        schema_root = resources.files("opencntx").joinpath("schemas")
        schema = json.loads(
            schema_root.joinpath("goal-storage-envelope-v2.schema.json").read_text()
        )
        self.assertEqual(set(schema["required"]), set(value))
        self.assertFalse(schema["additionalProperties"])
        catalog = json.loads(schema_root.joinpath("goal-contract-v2.json").read_text())
        self.assertTrue(
            {
                "goal-storage-envelope-v2.schema.json",
                "goal-handoff-evidence-v2.schema.json",
            }.issubset(catalog["schemas"])
        )
        for name in catalog["schemas"]:
            self.assertTrue(schema_root.joinpath(name).is_file())

    def test_faulted_cutover_restores_complete_v1_and_preserves_new_version_evidence(self) -> None:
        from opencntx.transactional_update import apply_update_plan, build_update_preview

        self.upgrade()
        record_execution_checkpoint(
            self.staged,
            checkpoint_id="NEW-VERSION-PROOF",
            current_internal_task="VERIFY",
            next_internal_action="Keep new version evidence",
            evidence_paths=["input.txt"],
            expected_state_digest=self.state["state_digest"],
        )
        new_ledger = (self.staged / ".opencntx/continuity/history/events.jsonl").read_bytes()
        plan = build_update_preview(
            self.directory,
            from_version="1.4.0",
            to_version="R15-LOCAL",
            components=[
                {
                    "name": "PROJECT_STATE",
                    "active_path": str(self.root),
                    "candidate_path": str(self.staged),
                    "from_format": "1",
                    "to_format": "2",
                }
            ],
            target_context_version="2",
            target_companion_version="NONE",
            target_project_format="2",
            compatibility_matrix=[
                {"context_version": "2", "companion_version": "NONE", "project_format": "2"}
            ],
            changelog=["Explicit goal storage envelope"],
            risks=["Injected cutover interruption"],
        )

        def fail(phase: str):
            if phase == "AFTER_ACTIVATE:PROJECT_STATE":
                raise RuntimeError("simulated interrupted cutover")

        with self.assertRaisesRegex(RuntimeError, "interrupted cutover"):
            apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}", fault_hook=fail)
        self.assertEqual(bytes_map(self.root), self.original)
        self.assertEqual(bytes_map(Path(plan["backup_path"]) / "PROJECT_STATE"), self.original)
        preserved = self.directory / ".opencntx-update/preserved-recovery"
        self.assertTrue(
            any(path.read_bytes() == new_ledger for path in preserved.rglob("events.jsonl"))
        )
        self.assertEqual(execution_state_capsule(self.root)["checkpoint_number"], 0)
        self.assertEqual(execution_state_capsule(self.staged)["checkpoint_number"], 1)

    @unittest.skipUnless(
        os.environ.get("R15_LEGACY_SOURCE"), "Actual v1 source path must be supplied"
    )
    def test_actual_legacy_writer_preserves_original_new_store(self) -> None:
        source = Path(os.environ["R15_LEGACY_SOURCE"]).resolve(strict=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(source)
        code = legacy_writer_code("OLD-WRITER")
        legacy_clone = self.directory / "v1-positive-control"
        shutil.copytree(self.root, legacy_clone)
        positive = subprocess.run(
            [sys.executable, "-B", "-c", code, str(legacy_clone), str(source)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(positive.returncode, 0, positive.stderr)
        self.upgrade()
        before = bytes_map(self.staged)
        before_capsule = execution_state_capsule(self.staged)
        rejected = subprocess.run(
            [sys.executable, "-B", "-c", code, str(self.staged), str(source)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if rejected.returncode == 0:
            # Later immutable writers understand the upgraded envelope and may
            # append directly. Require the current reader to authenticate that
            # exact single checkpoint instead of treating success as a failure.
            after_capsule = execution_state_capsule(self.staged)
            self.assertEqual(
                before_capsule["checkpoint_number"] + 1,
                after_capsule["checkpoint_number"],
            )
            self.assertEqual(
                before_capsule["current_assignment"], after_capsule["current_assignment"]
            )
            self.assertNotEqual(bytes_map(self.staged), before)
        else:
            # Earlier readers reject the format or cannot acquire its V2 marker.
            self.assertTrue(
                "Roadmap fields are incomplete or unknown" in rejected.stderr
                or "Another continuity writer is active" in rejected.stderr,
                rejected.stderr,
            )
            self.assertEqual(bytes_map(self.staged), before)
        self.assertEqual(bytes_map(self.root), self.original)


if __name__ == "__main__":
    unittest.main()
