from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opencntx.continuity import ContinuityError, advance_flow, start_flow
from opencntx.continuity_sync import (
    CHECKPOINT_POLICY,
    _load_sync_config,
    _value_digest,
    record_sync_error,
    sync_configured,
    sync_status,
)


def start_project(parent: Path, name: str) -> Path:
    root = parent / name
    root.mkdir()
    roadmap = {
        "format": "opencntx-continuity-roadmap",
        "format_version": 1,
        "project_id": f"SYNC-{name.upper()}",
        "roadmap_id": "SYNC-ROADMAP",
        "title": "Checkpoint sync",
        "assignments": [
            {
                "id": "TASK-1",
                "title": "One task",
                "detail": "Complete one bounded checkpoint task.",
                "depends_on": [],
                "touches": [],
                "conflict": "EXTEND",
                "migration": "",
                "definition_of_done": ["Evidence exists"],
            }
        ],
    }
    roadmap_path = root / "roadmap.json"
    roadmap_path.write_text(json.dumps(roadmap), encoding="utf-8")
    start_flow(root, roadmap_path, "AUTO PILOT")
    return root


def config_value(root: Path, *, legacy: bool) -> dict[str, object]:
    value: dict[str, object] = {
        "format": "opencntx-continuity-sync-config",
        "format_version": 1,
        "repository": str(root / "replica"),
        "remote": "origin",
        "branch": "main",
        "private_repository_confirmed": False,
        "enabled": True,
    }
    if not legacy:
        value["checkpoint_policy"] = CHECKPOINT_POLICY
        value["migration"] = "NONE"
    value["config_digest"] = _value_digest(value)
    return value


class CheckpointSyncTests(unittest.TestCase):
    def test_checkpoint_and_config_schemas_are_closed(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "opencntx" / "schemas"
        checkpoint = json.loads(
            (root / "continuity-checkpoint-v1.schema.json").read_text(encoding="utf-8")
        )
        config = json.loads(
            (root / "continuity-sync-config-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(checkpoint["additionalProperties"])
        self.assertFalse(config["additionalProperties"])
        self.assertEqual(CHECKPOINT_POLICY, checkpoint["properties"]["policy"]["const"])
        self.assertEqual(
            CHECKPOINT_POLICY, config["properties"]["checkpoint_policy"]["const"]
        )

    def test_pass_fail_and_blocked_all_emit_every_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            captured: list[dict[str, object]] = []

            def capture(_root: Path, *, checkpoint: dict[str, object]):
                captured.append(checkpoint)

            with patch("opencntx.continuity_sync.sync_configured", side_effect=capture):
                passed = start_project(parent, "pass")
                (passed / "pass.txt").write_text("pass\n", encoding="utf-8")
                advance_flow(passed, outcome="PASS", evidence_paths=["pass.txt"])

                failed = start_project(parent, "fail")
                (failed / "fail.txt").write_text("fail\n", encoding="utf-8")
                advance_flow(
                    failed,
                    outcome="FAIL",
                    evidence_paths=["fail.txt"],
                    reason="First bounded strategy failed",
                )

                blocked = start_project(parent, "blocked")
                for number in range(1, 4):
                    evidence = blocked / f"blocked-{number}.txt"
                    evidence.write_text(f"failure {number}\n", encoding="utf-8")
                    advance_flow(
                        blocked,
                        outcome="FAIL",
                        evidence_paths=[evidence.name],
                        reason=f"Distinct bounded strategy {number} failed",
                    )

            self.assertEqual(
                ["PASS", "FAIL", "FAIL", "FAIL", "BLOCKED"],
                [item["checkpoint"] for item in captured],
            )
            for item in captured:
                self.assertEqual(CHECKPOINT_POLICY, item["policy"])
                basis = {key: value for key, value in item.items() if key != "checkpoint_digest"}
                self.assertEqual(item["checkpoint_digest"], _value_digest(basis))

    def test_legacy_config_normalizes_read_only_then_migrates_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = start_project(Path(temporary_directory), "legacy")
            path = root / ".opencntx" / "continuity" / "sync" / "config.json"
            path.write_text(json.dumps(config_value(root, legacy=True)), encoding="utf-8")
            legacy_bytes = path.read_bytes()

            preview = _load_sync_config(root, migrate=False)
            self.assertIsNotNone(preview)
            assert preview is not None
            self.assertEqual(CHECKPOINT_POLICY, preview["checkpoint_policy"])
            self.assertEqual("LEGACY_IMPLICIT_EVERY_CHECKPOINT", preview["migration"])
            self.assertEqual(legacy_bytes, path.read_bytes())

            migrated = _load_sync_config(root, migrate=True)
            self.assertEqual(preview, migrated)
            self.assertNotEqual(legacy_bytes, path.read_bytes())
            migrated_bytes = path.read_bytes()
            self.assertEqual(migrated, _load_sync_config(root, migrate=True))
            self.assertEqual(migrated_bytes, path.read_bytes())
            self.assertEqual("LEGACY_IMPLICIT_EVERY_CHECKPOINT", sync_status(root)["config_migration"])

    def test_offline_error_latches_once_and_local_flow_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = start_project(Path(temporary_directory), "offline")
            config_path = root / ".opencntx" / "continuity" / "sync" / "config.json"
            config_path.write_text(json.dumps(config_value(root, legacy=False)), encoding="utf-8")
            (root / "failure.txt").write_text("offline\n", encoding="utf-8")
            unavailable = ContinuityError("Git unavailable", code="continuity_sync_unavailable")

            with patch("opencntx.continuity_sync.sync_configured", side_effect=unavailable):
                result = advance_flow(
                    root,
                    outcome="FAIL",
                    evidence_paths=["failure.txt"],
                    reason="Network-independent local work remains available",
                )

            error_path = root / ".opencntx" / "continuity" / "sync" / "last-error.json"
            first_bytes = error_path.read_bytes()
            first_mtime = error_path.stat().st_mtime_ns
            error = json.loads(first_bytes)
            self.assertEqual("RECOVERY_REQUIRED", result.status)
            self.assertEqual("CONTINUES_OFFLINE", error["local_flow"])
            self.assertEqual(CHECKPOINT_POLICY, error["checkpoint_policy"])
            self.assertEqual("FAIL", error["checkpoint"]["checkpoint"])
            self.assertEqual("NOT_AUTOMATIC", error["retry"])

            self.assertIsNone(sync_configured(root, checkpoint=error["checkpoint"]))
            self.assertEqual(first_bytes, error_path.read_bytes())
            self.assertEqual(first_mtime, error_path.stat().st_mtime_ns)

    def test_blocked_error_record_is_not_rewritten_by_later_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = start_project(Path(temporary_directory), "latched")
            first = {
                "format": "opencntx-continuity-checkpoint",
                "format_version": 1,
                "policy": CHECKPOINT_POLICY,
                "checkpoint": "FAIL",
                "requested_outcome": "FAIL",
                "flow_status": "RECOVERY_REQUIRED",
                "current_assignment": "TASK-1",
                "completed": [],
                "state_digest": "1" * 64,
            }
            first["checkpoint_digest"] = _value_digest(first)
            record_sync_error(
                root,
                ContinuityError("offline", code="continuity_sync_unavailable"),
                checkpoint=first,
            )
            error_path = root / ".opencntx" / "continuity" / "sync" / "last-error.json"
            original = error_path.read_bytes()
            record_sync_error(
                root,
                ContinuityError("still offline", code="continuity_sync_unavailable"),
                checkpoint=first,
            )
            self.assertEqual(original, error_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
