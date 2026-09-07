from __future__ import annotations

import json
import unittest
from pathlib import Path

from opencntx.connected_state import publish_connected_state
from opencntx.continuity import advance_flow, flow_status, record_execution_checkpoint, start_flow
from opencntx.transactional_update import apply_update_plan, build_update_preview
from tests import test_transactional_update as baseline
from tests.test_connected_state import roadmap


class ProjectUpdateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = baseline.TransactionalUpdateTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.components = self.fixture.update_fixture()
        self.project = self.root / "project"
        self.project.mkdir()
        self.profile = self.root / "candidate-profile.json"
        self.profile.write_text(json.dumps({"runtime_version": "2.0"}))

    def plan(self, *, require_connected=False):
        return build_update_preview(
            self.root,
            from_version="1.0",
            to_version="2.0",
            components=self.components,
            target_context_version="2.0",
            target_companion_version="1.10",
            target_project_format="2",
            compatibility_matrix=baseline.MATRIX,
            changelog=["Fixture"],
            risks=["Interruption"],
            project_checks=[
                {
                    "project_path": str(self.project),
                    "profile_path": str(self.profile),
                    "require_connected": require_connected,
                }
            ],
        )

    def test_missing_binding_and_stale_pin_are_explicit(self):
        with self.assertRaisesRegex(Exception, "absent or stale"):
            self.plan(require_connected=True)
        self.profile.write_text(json.dumps({"runtime_version": "1.0"}))
        with self.assertRaisesRegex(Exception, "stale version pin"):
            self.plan()

    def test_profile_drift_before_apply_preserves_components(self):
        plan = self.plan()
        self.profile.write_text(json.dumps({"runtime_version": "2.0", "note": "New user edit"}))
        with self.assertRaisesRegex(Exception, "profile changed"):
            apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        self.assertEqual(
            (Path(self.components[0]["active_path"]) / "version.txt").read_text(), "old\n"
        )

    def test_active_flow_requires_checkpoint_then_update_is_replayable(self):
        path = self.project / "roadmap.json"
        path.write_text(json.dumps(roadmap()))
        state = start_flow(self.project, path, "AUTO PILOT")
        with self.assertRaisesRegex(Exception, "checkpoint"):
            self.plan()
        proof = self.project / "checkpoint.txt"
        proof.write_text("Host paused at a bounded checkpoint")
        capsule = record_execution_checkpoint(
            self.project,
            checkpoint_id="UPDATE-READY",
            current_internal_task="UPDATE_CHECKPOINT",
            next_internal_action="Resume original recommendation after update",
            evidence_paths=["checkpoint.txt"],
            expected_state_digest=state.state_digest,
        )
        publish_connected_state(self.project, expected_state_digest=capsule["state_digest"])
        plan = self.plan(require_connected=True)
        self.assertEqual(plan["format_version"], 2)
        first = apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}")
        self.assertEqual(
            apply_update_plan(plan, approval=f"APPLY UPDATE {plan['plan_digest']}"), first
        )
        advance_flow(self.project, outcome="PASS", evidence_paths=["checkpoint.txt"])
        self.assertEqual(flow_status(self.project).current_assignment, "RECOMMENDATION")

    def test_malformed_profile_and_active_writer_are_rejected(self):
        self.profile.write_text("{")
        with self.assertRaisesRegex(Exception, "cannot be read"):
            self.plan()
        self.profile.write_text(json.dumps({"runtime_version": "2.0"}))
        lock = self.project / ".opencntx/continuity/.operation.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("active writer")
        with self.assertRaisesRegex(Exception, "writer"):
            self.plan()

    def test_v2_schema_and_legacy_reader_refusal(self):
        schemas = Path(__file__).resolve().parents[1] / "src/opencntx/schemas"
        plan = self.plan()
        modern = json.loads((schemas / "transactional-update-plan-v2.schema.json").read_bytes())
        legacy = json.loads((schemas / "transactional-update-plan-v1.schema.json").read_bytes())
        self.assertEqual(set(plan), set(modern["required"]))
        self.assertEqual(plan["format_version"], modern["properties"]["format_version"]["const"])
        self.assertNotEqual(plan["format_version"], legacy["properties"]["format_version"]["const"])
        self.assertNotIn("project_checks", legacy["properties"])
        self.assertFalse(legacy["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
