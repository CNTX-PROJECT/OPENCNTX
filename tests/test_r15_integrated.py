from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from opencntx.goal_followup import compile_goal_context
from opencntx.goal_handoff import prepare_goal_handoff
from opencntx.goal_progress import load_goal_progress
from tests import test_goal_progress as progress_fixture
from tests import test_reference_host as host_fixture
from tests.test_goal_handoff import OPTIONS


@unittest.skipUnless(sys.platform == "win32", "Combined closed Windows physical route")
class IntegratedGoalRouteTests(unittest.TestCase):
    def test_original_question_through_planning_action_and_restarted_handoff(self) -> None:
        fixture = progress_fixture.NativeGoalProgressTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.nodes[2]["status"] = "BLOCKED"
        progress = fixture.prepare()
        goal = fixture.host.expected
        request = goal.payload()
        before = host_fixture.snapshot(fixture.fixture)
        wrong = copy.deepcopy(request)
        wrong["action"]["targets"] = ["parent/child/00.txt"]
        denial = fixture.host.dispatch(wrong)
        self.assertEqual(denial["decision"], "DENY")
        self.assertEqual(host_fixture.snapshot(fixture.fixture), before)
        allowed = fixture.host.dispatch(request)
        self.assertEqual(allowed["decision"], "ALLOW", allowed)
        after = host_fixture.snapshot(fixture.fixture)
        for name in host_fixture.f.NAMES:
            self.assertNotEqual(after[str(Path(name))], before[str(Path(name))])
        for name in host_fixture.f.WATCHED[3:]:
            self.assertEqual(after[str(Path(name))], before[str(Path(name))])
        context = compile_goal_context(fixture.root, goal)
        self.assertEqual(set(context["open_outcome_ids"]), set(request["request"]["outcome_ids"]))
        self.assertEqual(context["goal_status"], "PARTIAL")
        handoff = prepare_goal_handoff(fixture.root, goal, **OPTIONS)
        (fixture.root / "supervisor-goal.json").write_text(goal.canonical_json)
        resumed = subprocess.run(
            [sys.executable, "-B", "-c",
             "from pathlib import Path; import sys; from tests.test_goal_handoff import subprocess_step; subprocess_step(Path(sys.argv[1]), 'ACCEPT')",
             str(fixture.root)], capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        ack = json.loads(resumed.stdout)
        self.assertEqual(ack["status"], "RESUME_AUTOMATICALLY")
        self.assertEqual(ack["execution"], "NOT_PERFORMED")
        self.assertEqual(load_goal_progress(fixture.root, goal), progress)
        self.assertEqual(fixture.host.dispatch(request)["decision"], "DENY")
        self.assertEqual(host_fixture.snapshot(fixture.fixture), after)
        result = {
            "request": request, "progress": progress.payload(), "before": before,
            "wrong_reply": denial, "correct_reply": allowed, "after": after,
            "context": context, "handoff": handoff, "restarted_ack": ack,
            "completion_claim": "PARTIAL_NOT_ALL_OUTCOMES_PROVEN",
        }
        destination = os.environ.get("OPENCNTX_TEST_EVIDENCE_ROOT")
        if destination:
            (Path(destination) / "r15-integrated-route.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    unittest.main()
