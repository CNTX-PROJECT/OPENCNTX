from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opencntx.cli import main
from opencntx.combo import load_combo, new_combo, write_combo
from opencntx.connected_state import connected_status, export_status, publish_connected_state
from opencntx.continuity import (
    ContinuityError,
    advance_flow,
    flow_status,
    record_execution_checkpoint,
    start_flow,
)
from opencntx.goal_progress import (
    begin_recovery,
    finish_recovery,
    persist_goal_progress,
    progress_readiness,
)
from tests import test_goal_progress as progress_fixture
from tests import test_reference_host as host_fixture


def roadmap() -> dict:
    return {
        "format": "opencntx-continuity-roadmap",
        "format_version": 1,
        "project_id": "DEMO",
        "roadmap_id": "ANALYSIS",
        "title": "Analysis to recommendation",
        "assignments": [
            {
                "id": name,
                "title": title,
                "detail": title,
                "depends_on": deps,
                "touches": [],
                "conflict": "NO_CONFLICT",
                "migration": "",
                "definition_of_done": [title],
            }
            for name, title, deps in [
                ("PRODUCER", "Collect verified records", []),
                ("RECOMMENDATION", "Deliver evidence-backed recommendation", ["PRODUCER"]),
            ]
        ],
    }


class ConnectedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "roadmap.json"
        self.path.write_text(json.dumps(roadmap()), encoding="utf-8")

    def start(self):
        return start_flow(self.root, self.path, "AUTO PILOT")

    def publish(self):
        return publish_connected_state(
            self.root, expected_state_digest=flow_status(self.root).state_digest
        )

    def test_missing_store_is_read_only_and_not_enforced(self):
        before = list(self.root.iterdir())
        self.assertEqual(connected_status(self.root)["status"], "CONFIGURED_ONLY")
        self.assertEqual(before, list(self.root.iterdir()))

    def test_producer_completion_retains_recommendation_and_restart(self):
        self.start()
        self.publish()
        (self.root / "proof.txt").write_text("Verified producer result", encoding="utf-8")
        advance_flow(self.root, outcome="PASS", evidence_paths=["proof.txt"])
        self.assertEqual(connected_status(self.root)["status"], "STALE")
        value = self.publish()
        self.assertEqual(value["capsule"]["current_assignment"], "RECOMMENDATION")
        self.assertFalse(connected_status(self.root)["completion_allowed"])
        result = subprocess.run(
            [sys.executable, "-m", "opencntx", "flow", "current", "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["status"], "CURRENT")

    def test_stale_writer_and_combo_update_invalidate_view(self):
        first = self.start()
        self.publish()
        (self.root / "proof.txt").write_text("Verified result", encoding="utf-8")
        advance_flow(self.root, outcome="PASS", evidence_paths=["proof.txt"])
        with self.assertRaises(ContinuityError):
            publish_connected_state(self.root, expected_state_digest=first.state_digest)
        self.publish()
        combo = load_combo(self.root)
        write_combo(self.root, new_combo("DEMO"), expected_digest=combo["combo_digest"])
        self.assertEqual(connected_status(self.root)["status"], "STALE")
        with self.assertRaises(ContinuityError):
            write_combo(self.root, combo, expected_digest=combo["combo_digest"])

    def test_repeat_publish_is_idempotent(self):
        self.start()
        first = self.publish()
        self.assertEqual(self.publish(), first)

    def test_compaction_preserves_history_and_open_work(self):
        self.start()
        first = self.publish()
        ledger = self.root / ".opencntx/continuity/history/events.jsonl"
        original = ledger.read_bytes()
        (self.root / "proof.txt").write_text("Checkpoint evidence")
        for index in range(100):
            record_execution_checkpoint(
                self.root,
                checkpoint_id=f"STEP-{index}",
                current_internal_task="COLLECT",
                next_internal_action="Return to recommendation",
                evidence_paths=["proof.txt"],
                expected_state_digest=flow_status(self.root).state_digest,
            )
        value = self.publish()
        self.assertEqual(value["assignments"], first["assignments"])
        self.assertTrue(ledger.read_bytes().startswith(original))
        from opencntx.connected_state import render_current

        self.assertLess(len(render_current(value)), 2500)
        with (
            patch("opencntx.connected_state.MAX_VIEW_BYTES", 20),
            self.assertRaises(ContinuityError),
        ):
            self.publish()
        self.assertEqual(connected_status(self.root)["status"], "CURRENT")

    def test_export_missing_and_stale_never_changes_native_status(self):
        self.start()
        value = self.publish()
        destination = self.root / "export.md"
        self.assertEqual(export_status(self.root, destination)["status"], "SYNC_PENDING")
        source = (
            self.root
            / ".opencntx/continuity/views/generations"
            / value["view_digest"]
            / "ROADMAP.md"
        )
        destination.write_bytes(source.read_bytes())
        first = export_status(self.root, destination)
        self.assertEqual(first["status"], "CURRENT")
        self.assertEqual(export_status(self.root, destination), first)
        destination.write_text("Old export")
        self.assertEqual(export_status(self.root, destination)["status"], "SYNC_PENDING")
        self.assertEqual(connected_status(self.root)["status"], "CURRENT")

        (self.root / "proof.txt").write_text("Verified producer")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "flow",
                        "advance",
                        "--outcome",
                        "PASS",
                        "--evidence",
                        "proof.txt",
                        "--root",
                        str(self.root),
                        "--json",
                    ]
                ),
                0,
            )
        current = connected_status(self.root)
        self.assertEqual(current["status"], "CURRENT")
        self.assertEqual(current["view"]["capsule"]["current_assignment"], "RECOMMENDATION")

    def test_interrupted_publish_and_modified_markdown_do_not_claim_current(self):
        self.start()
        first = self.publish()
        (self.root / "proof.txt").write_text("Progress", encoding="utf-8")
        state = flow_status(self.root)
        record_execution_checkpoint(
            self.root,
            checkpoint_id="CHECK-1",
            current_internal_task="REPAIR",
            next_internal_action="Resume goal",
            evidence_paths=["proof.txt"],
            expected_state_digest=state.state_digest,
        )
        from opencntx import connected_state as module

        original = module._write_atomic

        def fail_pointer(path, content):
            if path.name == "CURRENT":
                raise OSError("simulated interruption")
            return original(path, content)

        with (
            patch.object(module, "_write_atomic", side_effect=fail_pointer),
            self.assertRaises(OSError),
        ):
            self.publish()
        self.assertEqual(connected_status(self.root)["status"], "STALE")
        self.publish()
        current = self.root / ".opencntx/continuity/views"
        generation = (current / "CURRENT").read_text().strip()
        (current / "generations" / generation / "ROADMAP.md").write_text("False complete")
        with self.assertRaises(ContinuityError):
            connected_status(self.root)
        self.assertTrue((current / "generations" / first["view_digest"]).exists())

    def test_export_delivery_is_durable_pending_then_read_back(self):
        from opencntx.connected_state import record_export_delivery

        self.start()
        value = self.publish()
        destination = self.root / "export.md"
        pending = record_export_delivery(self.root, destination)
        self.assertEqual(pending["status"], "SYNC_PENDING")
        views = self.root / ".opencntx/continuity/views"
        receipt = views / "deliveries" / (pending["delivery_key"] + ".json")
        self.assertEqual(json.loads(receipt.read_bytes()), pending)
        destination.write_bytes(
            (views / "generations" / value["view_digest"] / "ROADMAP.md").read_bytes()
        )
        delivered = record_export_delivery(self.root, destination)
        self.assertEqual(delivered["status"], "CURRENT")
        self.assertEqual(delivered["delivery_key"], pending["delivery_key"])
        self.assertEqual(json.loads(receipt.read_bytes()), delivered)
        self.assertEqual(record_export_delivery(self.root, destination), delivered)

    def test_reparse_view_is_rejected_before_read_or_write(self):
        from opencntx import connected_state as module

        self.start()
        self.publish()
        with patch.object(module, "_is_reparse", side_effect=lambda p: p.name == "views"):
            with self.assertRaisesRegex(ContinuityError, "aliases"):
                connected_status(self.root)
            with self.assertRaisesRegex(ContinuityError, "aliases"):
                self.publish()

    def test_cli_reports_inaccessible_view_without_traceback(self):
        self.start()
        self.publish()
        output = io.StringIO()
        with (
            patch.object(Path, "is_symlink", side_effect=PermissionError("denied")),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(main(["flow", "current", "--root", str(self.root)]), 2)
        self.assertIn("connected_path_inaccessible", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_real_directory_link_cannot_redirect_views(self):
        self.start()
        self.publish()
        views = self.root / ".opencntx/continuity/views"
        retained = self.root / "retained-views"
        views.rename(retained)
        if sys.platform == "win32":
            subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(views), str(retained)],
                check=True,
                capture_output=True,
            )
            self.addCleanup(views.rmdir)
        else:
            views.symlink_to(retained, target_is_directory=True)
            self.addCleanup(views.unlink)
        before = {
            str(p.relative_to(retained)): p.read_bytes() for p in retained.rglob("*") if p.is_file()
        }
        with self.assertRaisesRegex(ContinuityError, "aliases"):
            self.publish()
        self.assertEqual(
            before,
            {
                str(p.relative_to(retained)): p.read_bytes()
                for p in retained.rglob("*")
                if p.is_file()
            },
        )

    def test_invalid_pointer_cannot_escape_store(self):
        self.start()
        self.publish()
        pointer = self.root / ".opencntx/continuity/views/CURRENT"
        for text in ("../../outside", "z" * 64, "[]"):
            pointer.write_text(text)
            with self.assertRaises(ContinuityError):
                connected_status(self.root)

    def test_cli_connected_start_and_bound_publish(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(
                main(
                    [
                        "flow",
                        "start",
                        str(self.path),
                        "--root",
                        str(self.root),
                        "--approval",
                        "AUTO PILOT",
                        "--connected",
                        "--json",
                    ]
                ),
                0,
            )
        self.assertEqual(connected_status(self.root)["status"], "CURRENT")


class RecoveryTests(unittest.TestCase):
    def test_repair_resumes_original_goal_and_preserves_authority(self):
        fixture = progress_fixture.GoalProgressTests()
        fixture.setUp()
        first = fixture.build()
        repair = begin_recovery(
            fixture.goal,
            first,
            node_id="WRITE",
            recovery_id="REPAIR",
            resume_id="RESUME",
            reason="Producer failed",
        )
        self.assertNotIn("RESUME", progress_readiness(repair, fixture.goal)["ready_nodes"])
        finished = finish_recovery(
            fixture.goal,
            repair,
            recovery_id="REPAIR",
            evidence=[{"reference": "proof.json", "sha256": "a" * 64}],
        )
        result = progress_readiness(finished, fixture.goal)
        self.assertIn("RESUME", result["ready_nodes"])
        self.assertIn("PARENT-RESULT", result["open_outcome_ids"])
        self.assertEqual(finished.payload()["intent_digest"], first.payload()["intent_digest"])
        self.assertEqual(finished.payload()["request"], first.payload()["request"])
        self.assertEqual(result["parent_status"], "PARTIAL")

    def test_test_only_repair_blocks_execution_and_retains_original_intent(self):
        fixture = progress_fixture.GoalProgressTests()
        fixture.setUp()
        first = fixture.build()
        repair = begin_recovery(
            fixture.goal,
            first,
            node_id="WRITE",
            recovery_id="REPAIR",
            resume_id="RESUME",
            reason="Run tests first",
            test_only=True,
        )
        ready = progress_readiness(repair, fixture.goal)
        self.assertNotIn("REPAIR", ready["ready_nodes"])
        self.assertNotIn("RESUME", ready["ready_nodes"])
        self.assertEqual(first.payload()["intent_digest"], repair.payload()["intent_digest"])
        finished = finish_recovery(
            fixture.goal,
            repair,
            recovery_id="REPAIR",
            evidence=[{"reference": "tests.json", "sha256": "a" * 64}],
        )
        self.assertIn("RESUME", progress_readiness(finished, fixture.goal)["ready_nodes"])

    def test_replan_cannot_erase_repair_budget(self):
        fixture = progress_fixture.GoalProgressTests()
        fixture.setUp()
        first = fixture.build()
        repair = begin_recovery(
            fixture.goal,
            first,
            node_id="WRITE",
            recovery_id="REPAIR",
            resume_id="RESUME",
            reason="Retained failure",
        )
        with self.assertRaisesRegex(ContinuityError, "erase retained"):
            fixture.build(previous=repair)

    def test_repeated_repair_splits_cannot_exceed_three(self):
        fixture = progress_fixture.GoalProgressTests()
        fixture.setUp()
        progress = fixture.build()
        node = "WRITE"
        for index in range(3):
            progress = begin_recovery(
                fixture.goal,
                progress,
                node_id=node,
                recovery_id=f"REPAIR{index}",
                resume_id=f"RESUME{index}",
                reason="Same bounded failure",
            )
            node = f"RESUME{index}"
        with self.assertRaisesRegex(ContinuityError, "budget"):
            begin_recovery(
                fixture.goal,
                progress,
                node_id=node,
                recovery_id="EXTRA",
                resume_id="EXTRA-RESUME",
                reason="Fourth repair",
            )


@unittest.skipUnless(sys.platform == "win32", "Closed Windows reference host")
class ConnectedHostTests(unittest.TestCase):
    def setUp(self):
        progress_fixture.NativeGoalProgressTests.setUp(self)

    def test_real_host_repair_persistence_resume_and_source_drift(self):
        first = progress_fixture.NativeGoalProgressTests.prepare(self)
        repair = begin_recovery(
            self.host.expected,
            first,
            node_id="WRITE",
            recovery_id="REPAIR",
            resume_id="RESUME",
            reason="Collection must be repaired",
            test_only=True,
        )
        persist_goal_progress(
            self.root, self.host.expected, repair, evidence_directory=self.evidence_directory
        )
        self.host = host_fixture.host(self.root, progress_node_id="REPAIR")
        value = self.host.publish_current()
        self.assertNotIn("REPAIR", value["ready_nodes"])
        self.assertEqual(self.host.dispatch(self.host.expected.payload())["decision"], "DENY")
        self.assertEqual(value["binding"], "GOAL_CONNECTED")
        with self.assertRaises(ContinuityError):
            publish_connected_state(self.root, expected_state_digest=value["source_digest"])
        self.assertIn("PARENT-RESULT", value["goal_context"]["open_outcome_ids"])
        proof = self.root / "repair.txt"
        proof.write_bytes(b"Repair evidence fixture")
        finished = finish_recovery(
            self.host.expected,
            repair,
            recovery_id="REPAIR",
            evidence=[
                {"reference": "repair.txt", "sha256": host_fixture._digest(proof.read_bytes())}
            ],
        )
        persist_goal_progress(
            self.root, self.host.expected, finished, evidence_directory=self.evidence_directory
        )
        self.host = host_fixture.host(self.root, progress_node_id="RESUME")
        self.assertIn("RESUME", self.host.publish_current()["ready_nodes"])
        reply = self.host.dispatch(self.host.expected.payload())
        self.assertEqual(reply["decision"], "ALLOW", reply)
        self.assertFalse(connected_status(self.root)["completion_allowed"])
        record_execution_checkpoint(
            self.root,
            checkpoint_id="HOST-READBACK",
            current_internal_task="VERIFY-OUTCOMES",
            next_internal_action="Verify original outcomes",
            evidence_paths=["repair.txt"],
            expected_state_digest=flow_status(self.root).state_digest,
        )
        self.assertEqual(connected_status(self.root)["status"], "STALE")

    def test_delivered_labels_without_semantic_evidence_do_not_complete(self):
        for node in self.nodes:
            node["status"] = "DELIVERED"
        progress_fixture.NativeGoalProgressTests.prepare(self)
        value = self.host.publish_current()
        self.assertNotEqual(value["goal_context"]["goal_status"], "TECHNICALLY_COMPLETE")
        self.assertFalse(connected_status(self.root)["completion_allowed"])


if __name__ == "__main__":
    unittest.main()
