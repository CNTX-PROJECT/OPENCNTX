from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib import resources
from pathlib import Path
from unittest.mock import patch

from opencntx.continuity import (
    ContinuityError,
    _digest,
    execution_state_capsule,
    record_execution_checkpoint,
    start_flow,
)
from opencntx.goal_binding import BoundGoal, build_goal_binding
from opencntx.goal_followup import build_followup_evidence, recovery_observation
from opencntx.goal_handoff import accept_goal_handoff, prepare_goal_handoff
from opencntx.goal_progress import build_goal_progress, load_goal_progress, persist_goal_progress
from opencntx.session_continuity import session_handoff_status
from tests import test_goal_binding as binding_fixture
from tests.test_goal_progress import nodes
from tests.test_session_continuity import CAPABILITIES, roadmap

OPTIONS = {
    "handoff_id": "R15-HANDOFF",
    "source_part": "13 - source",
    "target_part": "14 - target",
    "provider_capabilities": CAPABILITIES,
    "rollback_boundary": "Retain the original question and all open outcomes.",
}


def subprocess_step(root: Path, operation: str) -> None:
    expected = BoundGoal((root / "supervisor-goal.json").read_text())
    if operation == "PREPARE_CRASH":
        prepare_goal_handoff(root, expected, **OPTIONS)
        os._exit(73)
    else:
        result = accept_goal_handoff(
            root, expected, handoff_id=OPTIONS["handoff_id"], target_part=OPTIONS["target_part"]
        )
        print(json.dumps(result))


class GoalHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "input.txt").write_bytes(b"original source")
        start_flow(self.root, roadmap(self.root / "roadmap.json"), "AUTO PILOT")
        fixture = binding_fixture.GoalBindingTests()
        fixture.setUp()
        self.args = fixture.args
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        (self.root / "probe.txt").write_bytes(b"immutable source snapshot")
        self.nodes = nodes()
        for node in self.nodes:
            node["source_snapshot"][0]["sha256"] = _digest((self.root / "probe.txt").read_bytes())
        self.goal = self.current_goal()

    def current_goal(self, **changes) -> BoundGoal:
        return build_goal_binding(
            **(self.args | {"execution_capsule": execution_state_capsule(self.root)} | changes)
        )

    def persist(self, *, stopped: bool = False, failed: bool = False) -> None:
        if stopped or failed:
            value = build_followup_evidence(
                self.goal,
                stopped=stopped,
                attempts=[recovery_observation(self.goal, error_class="UNAVAILABLE")] if failed else [],
            )
            content = json.dumps(value).encode()
            (self.evidence / "recovery.json").write_bytes(content)
            self.nodes[1]["evidence"] = [{"reference": "evidence/recovery.json", "sha256": _digest(content)}]
        self.progress = build_goal_progress(self.goal, root_id="MAIN", nodes=self.nodes)
        persist_goal_progress(self.root, self.goal, self.progress, evidence_directory=self.evidence)
        self.goal = self.current_goal()

    def accept(self, goal=None):
        return accept_goal_handoff(
            self.root, goal or self.goal,
            handoff_id=OPTIONS["handoff_id"], target_part=OPTIONS["target_part"],
        )

    def snapshot(self, record):
        digest = record["evidence_objects"][0]["sha256"]
        return json.loads(gzip.decompress(
            (self.root / ".opencntx/continuity/evidence-objects" / f"{digest}.gz").read_bytes()
        ))

    def child(self, operation):
        (self.root / "supervisor-goal.json").write_text(self.goal.canonical_json)
        return subprocess.run(
            [sys.executable, "-B", "-c",
             "from pathlib import Path; import sys; from tests.test_goal_handoff import subprocess_step; subprocess_step(Path(sys.argv[1]), sys.argv[2])",
             str(self.root), operation], capture_output=True, text=True, timeout=30, check=False,
        )

    def test_compact_handoff_preserves_original_request_and_blocked_child(self) -> None:
        self.nodes[2]["status"] = "BLOCKED"
        self.persist()
        state = execution_state_capsule(self.root)
        record = prepare_goal_handoff(self.root, self.goal, **OPTIONS)
        self.assertEqual(record, prepare_goal_handoff(self.root, self.goal, **OPTIONS))
        snapshot = self.snapshot(record)
        self.assertEqual(snapshot["goal"]["request"], self.goal.payload()["request"])
        self.assertEqual(set(snapshot["context"]["open_outcome_ids"]), set(self.args["outcome_ids"]))
        self.assertEqual(
            next(node for node in snapshot["positions"] if node["id"] == "PRESERVE")["status"],
            "BLOCKED",
        )
        self.assertLess(record["evidence_objects"][0]["bytes"], 65536)
        ack = self.accept()
        self.assertEqual(ack["status"], "RESUME_AUTOMATICALLY")
        self.assertEqual(ack["execution"], "NOT_PERFORMED")
        self.assertEqual(self.accept(), ack)
        self.assertEqual(execution_state_capsule(self.root), state)
        self.assertEqual(load_goal_progress(self.root, self.goal), self.progress)

    def test_actual_process_crash_after_prepare_lost_ack_and_replayed_ack(self) -> None:
        self.persist()
        result = self.child("PREPARE_CRASH")
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertFalse(session_handoff_status(self.root, OPTIONS["handoff_id"])["source_may_idle"])
        first = self.child("ACCEPT")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.child("ACCEPT")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))
        self.assertEqual(load_goal_progress(self.root, self.goal), self.progress)
        self.assertTrue(session_handoff_status(self.root, OPTIONS["handoff_id"])["source_may_idle"])

    def test_shipped_snapshot_schema_matches_actual_bound_fields(self) -> None:
        self.persist()
        value = self.snapshot(prepare_goal_handoff(self.root, self.goal, **OPTIONS))
        schema = json.loads(resources.files("opencntx").joinpath("schemas/goal-handoff-evidence-v2.schema.json").read_text())
        self.assertEqual(set(schema["required"]), set(value))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]["positions"]["items"]["required"]), set(value["positions"][0]))

    def test_changed_question_or_state_cannot_receive_old_handoff(self) -> None:
        self.persist()
        prepare_goal_handoff(self.root, self.goal, **OPTIONS)
        with self.assertRaises(ContinuityError):
            self.accept(self.current_goal(revision=2))
        record_execution_checkpoint(
            self.root, checkpoint_id="STATE-DRIFT", current_internal_task="VERIFY",
            next_internal_action="Continue exact verification", evidence_paths=["probe.txt"],
            expected_state_digest=execution_state_capsule(self.root)["state_digest"],
        )
        with self.assertRaises(ContinuityError):
            self.accept()
        with self.assertRaises(ContinuityError):
            self.accept(self.current_goal())
        self.assertFalse((self.root / ".opencntx/continuity/session-acks/R15-HANDOFF.json").exists())

    def test_state_change_between_snapshot_and_native_prepare_is_refused(self) -> None:
        self.persist()
        from opencntx import goal_handoff as module
        original = module.store_evidence_object

        def drift(*args, **kwargs):
            result = original(*args, **kwargs)
            record_execution_checkpoint(
                self.root, checkpoint_id="PREPARE-DRIFT", current_internal_task="VERIFY",
                next_internal_action="Verify source", evidence_paths=["probe.txt"],
                expected_state_digest=execution_state_capsule(self.root)["state_digest"],
            )
            return result

        with patch.object(module, "store_evidence_object", side_effect=drift), self.assertRaises(ContinuityError):
            prepare_goal_handoff(self.root, self.goal, **OPTIONS)
        self.assertFalse((self.root / ".opencntx/continuity/session-handoffs/R15-HANDOFF.json").exists())

    def test_stop_and_recovery_fingerprint_survive_handoff(self) -> None:
        self.persist(stopped=True, failed=True)
        record = prepare_goal_handoff(self.root, self.goal, **OPTIONS)
        snapshot = self.snapshot(record)
        self.assertTrue(snapshot["followup"]["stopped"])
        self.assertEqual(len(snapshot["followup"]["attempts"]), 1)
        with self.assertRaisesRegex(ContinuityError, "blocked"):
            self.accept()

    def test_actual_competing_process_cannot_ack_while_native_writer_is_active(self) -> None:
        self.persist()
        prepare_goal_handoff(self.root, self.goal, **OPTIONS)
        code = (
            "from pathlib import Path; import sys; from opencntx.continuity import _writer_lock; "
            "lock=_writer_lock(Path(sys.argv[1])/'.opencntx/continuity/.operation.lock'); "
            "lock.__enter__(); print('LOCKED',flush=True); sys.stdin.readline(); lock.__exit__(None,None,None)"
        )
        with subprocess.Popen(
            [sys.executable, "-B", "-c", code, str(self.root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ) as child:
            try:
                self.assertEqual(child.stdout.readline().strip(), "LOCKED")
                with self.assertRaises(ContinuityError) as error:
                    self.accept()
                self.assertEqual(error.exception.code, "continuity_write_conflict")
            finally:
                child.communicate("release\n", timeout=30)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(self.accept()["status"], "RESUME_AUTOMATICALLY")

    def test_state_change_between_snapshot_and_native_accept_is_refused(self) -> None:
        self.persist()
        prepare_goal_handoff(self.root, self.goal, **OPTIONS)
        from opencntx import goal_handoff as module
        original = module.accept_session_handoff

        def drift(*args, **kwargs):
            record_execution_checkpoint(
                self.root, checkpoint_id="ACK-DRIFT", current_internal_task="VERIFY",
                next_internal_action="Verify source", evidence_paths=["probe.txt"],
                expected_state_digest=execution_state_capsule(self.root)["state_digest"],
            )
            return original(*args, **kwargs)

        with patch.object(module, "accept_session_handoff", side_effect=drift), self.assertRaises(ContinuityError):
            self.accept()
        self.assertFalse((self.root / ".opencntx/continuity/session-acks/R15-HANDOFF.json").exists())


@unittest.skipUnless(sys.platform == "win32", "Closed Windows physical writer")
class PhysicalGoalHandoffTests(unittest.TestCase):
    def test_replayed_ack_and_restart_do_not_repeat_physical_mutation(self) -> None:
        from tests import test_goal_progress as progress_fixture
        from tests import test_reference_host as host_fixture
        fixture = progress_fixture.NativeGoalProgressTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare()
        goal = fixture.host.expected
        prepare_goal_handoff(fixture.root, goal, **OPTIONS)
        values = {key: OPTIONS[key] for key in ("handoff_id", "target_part")}
        first = accept_goal_handoff(fixture.root, goal, **values)
        self.assertEqual(accept_goal_handoff(fixture.root, goal, **values), first)
        self.assertEqual(fixture.host.dispatch(goal.payload())["decision"], "ALLOW")
        after = host_fixture.snapshot(fixture.fixture)
        self.assertEqual(fixture.host.dispatch(goal.payload())["decision"], "DENY")
        with self.assertRaises(host_fixture.f.Refused):
            host_fixture.host(fixture.root)
        self.assertEqual(host_fixture.snapshot(fixture.fixture), after)


if __name__ == "__main__":
    unittest.main()
