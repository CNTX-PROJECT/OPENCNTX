from __future__ import annotations

import json
import sys
import unittest
from importlib import resources
from unittest.mock import patch

from opencntx.continuity import (
    ContinuityError,
    _digest,
    _value_digest,
    advance_flow,
    execution_state_capsule,
)
from opencntx.goal_binding import HostSource, build_goal_binding
from opencntx.goal_followup import (
    build_followup_evidence,
    compile_goal_context,
    plan_request_replacement,
    recovery_decision,
    recovery_observation,
)
from opencntx.goal_progress import build_goal_progress, persist_goal_progress
from opencntx.output_contract import (
    build_output_contract,
    extract_bound_session_metrics,
    render_output,
)
from tests import test_goal_binding as pure_fixture
from tests import test_goal_progress as native_fixture
from tests import test_reference_host as host_fixture


class FollowupTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = pure_fixture.GoalBindingTests()
        fixture.setUp()
        self.goal, self.args = fixture.bound, fixture.args

    def test_same_changed_and_exhausted_recovery(self) -> None:
        observed = recovery_observation(self.goal, error_class="UNAVAILABLE")
        changed = observed | {"capabilities_digest": "f" * 64}
        for attempts, expected in (
            ([observed], "SUPPRESS_UNCHANGED"),
            ([changed], "CONTINUE"),
            ([changed] * 3, "RECOVERY_EXHAUSTED"),
        ):
            self.assertEqual(
                recovery_decision(self.goal, build_followup_evidence(self.goal, attempts=attempts)),
                expected,
            )
        self.assertEqual(
            recovery_decision(self.goal, build_followup_evidence(self.goal, stopped=True)),
            "OWNER_STOP",
        )

    def test_followup_schema_binds_both_action_and_error_identity(self) -> None:
        value = build_followup_evidence(
            self.goal, attempts=[recovery_observation(self.goal, error_class="ERROR")]
        )
        schema = json.loads(
            resources.files("opencntx")
            .joinpath("schemas/goal-followup-v2.schema.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(set(schema["required"]), set(value))
        self.assertEqual(
            set(schema["properties"]["attempts"]["items"]["required"]), set(value["attempts"][0])
        )

    def test_proposal_and_owner_replacement_preserve_open_history(self) -> None:
        for role, expected in (("AI_PROPOSAL", "PROPOSAL_ONLY"), ("OWNER", "EXPLICIT_REPLACEMENT")):
            source = HostSource(
                role,
                "new-message",
                self.args["source"].content_sha256,
                "original-proposal" if role == "AI_PROPOSAL" else None,
            )
            newer = build_goal_binding(
                **(self.args | {"revision": 2, "source": source, "outcome_ids": ["PARENT-RESULT"]})
            )
            result = plan_request_replacement(
                self.goal, newer, {"PARENT-RESULT": "PARTIAL", "CHILD-PRESERVATION": "BLOCKED"}
            )
            self.assertEqual(result["status"], expected)
            self.assertEqual(result["previous_outcomes"]["CHILD-PRESERVATION"], "BLOCKED")
            self.assertEqual(result["replacement_request"]["source"]["role"], role)
            self.assertFalse(result["authority_granted"])
            self.assertEqual(result["execution"], "NOT_PERFORMED")


@unittest.skipUnless(sys.platform == "win32", "Closed Windows reference route")
class NativeFollowupTests(unittest.TestCase):
    def setUp(self) -> None:
        native_fixture.NativeGoalProgressTests.setUp(self)
        self.sequence = 0

    def save(self, evidence: dict) -> None:
        self.sequence += 1
        path = f"evidence/followup-{self.sequence}.json"
        content = json.dumps(evidence).encode()
        (self.root / path).write_bytes(content)
        self.nodes[0]["evidence"] = [{"reference": path, "sha256": _digest(content)}]
        progress = build_goal_progress(self.host.expected, root_id="MAIN", nodes=self.nodes)
        persist_goal_progress(
            self.root, self.host.expected, progress, evidence_directory=self.evidence_directory
        )
        self.host = host_fixture.host(self.root, progress_node_id="WRITE")

    def output(self, context: dict, **kwargs):
        return build_output_contract(
            execution_capsule=execution_state_capsule(self.root),
            roadmap_label="Fixture",
            summary="Do not claim full completion",
            language="nl",
            metrics=extract_bound_session_metrics(
                session_id="fixture", source_session_id="fixture", chat_bytes=0, records=[]
            ),
            required_capability="TEST",
            reasoning_level="LOW",
            goal_context=context,
            **kwargs,
        )

    def test_actual_failure_checkpoint_does_not_repeat_operation(self) -> None:
        old_digest = execution_state_capsule(self.root)["state_digest"]
        with patch.object(
            host_fixture.f, "execute", side_effect=host_fixture.f.Refused("fixture_unavailable")
        ) as operation:
            self.assertEqual(self.host.dispatch(self.host.expected.payload())["decision"], "DENY")
            self.save(
                build_followup_evidence(
                    self.host.expected,
                    attempts=[
                        recovery_observation(self.host.expected, error_class="fixture_unavailable")
                    ],
                )
            )
            self.assertNotEqual(execution_state_capsule(self.root)["state_digest"], old_digest)
            for _ in range(2):
                reply = self.host.dispatch(self.host.expected.payload())
                self.assertEqual(reply["decision"], "DENY")
                self.assertIn("SUPPRESS_UNCHANGED", reply["reason"])
            self.assertEqual(operation.call_count, 1)

    def test_changed_real_source_allows_bounded_rebound_action(self) -> None:
        observed = recovery_observation(self.host.expected, error_class="old_source_failure")
        (self.fixture / "parent/00.txt").write_bytes(b"New controlled fixture source")
        (self.fixture / "backup/parent/00.txt").write_bytes(b"New controlled fixture source")
        self.save(build_followup_evidence(self.host.expected, attempts=[observed]))
        reply = self.host.dispatch(self.host.expected.payload())
        self.assertEqual(reply["decision"], "ALLOW", reply)

    def test_blocker_rebinds_independent_outcome_but_does_not_retry_failed_write(self) -> None:
        self.save(
            build_followup_evidence(
                self.host.expected,
                attempts=[recovery_observation(self.host.expected, error_class="unavailable")],
            )
        )
        context = compile_goal_context(self.root, self.host.expected)
        self.assertEqual(context["decision"], "CONTINUE")
        self.assertEqual(context["next_outcome_id"], "CHILD-PRESERVATION")
        self.assertEqual(context["reason"], "REBIND_INDEPENDENT_OUTCOME")
        with patch.object(host_fixture.f, "execute") as operation:
            self.assertEqual(self.host.dispatch(self.host.expected.payload())["decision"], "DENY")
            operation.assert_not_called()

    def test_stop_blocks_actual_write_and_detour_box(self) -> None:
        self.save(build_followup_evidence(self.host.expected, stopped=True))
        before = host_fixture.snapshot(self.fixture)
        reply = self.host.dispatch(self.host.expected.payload())
        self.assertEqual(reply["decision"], "DENY")
        self.assertIn("OWNER_STOP", reply["reason"])
        self.assertEqual(host_fixture.snapshot(self.fixture), before)
        output = self.output(compile_goal_context(self.root, self.host.expected))
        self.assertEqual(output["next_action_state"], "BLOCKED")
        self.assertIn("Gestopt op jouw verzoek", render_output(output))
        self.assertNotIn("```", render_output(output))

    def test_partial_output_continues_without_external_override(self) -> None:
        self.nodes[2]["status"] = "BLOCKED"
        self.save(build_followup_evidence(self.host.expected))
        context = compile_goal_context(
            self.root, self.host.expected, proposed_outcome="PARENT-RESULT"
        )
        output = self.output(context)
        self.assertEqual(output["format_version"], 2)
        schema = json.loads(
            resources.files("opencntx")
            .joinpath("schemas/human-output-v2.schema.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(set(schema["required"]), set(output))
        self.assertEqual(output["next_action_state"], "CONTINUE_AUTOMATICALLY")
        self.assertIn("CHILD-PRESERVATION", render_output(output))
        self.assertNotIn("```", render_output(output))
        for kwargs in ({"proposed_outcome": "OTHER"}, {"future_idea": True}):
            with self.assertRaises(ContinuityError):
                compile_goal_context(self.root, self.host.expected, **kwargs)
        with self.assertRaises(ContinuityError):
            self.output(context, external_action=True, exact_human_action="Unrelated action")

    def test_stale_context_and_forged_completion_refused(self) -> None:
        context = compile_goal_context(self.root, self.host.expected)
        forged = context | {"decision": "COMPLETE_ROADMAP"}
        forged["context_digest"] = _value_digest(
            {k: v for k, v in forged.items() if k != "context_digest"}
        )
        with self.assertRaises(ContinuityError):
            self.output(forged)
        self.save(build_followup_evidence(self.host.expected))
        with self.assertRaises(ContinuityError):
            self.output(context)

    def test_old_complete_roadmap_cannot_close_new_question(self) -> None:
        (self.root / "old-proof.txt").write_text("Old fixture complete", encoding="utf-8")
        advance_flow(self.root, outcome="PASS", evidence_paths=["old-proof.txt"])
        self.host = host_fixture.host(self.root)
        old = self.host.expected.payload()
        goal = build_goal_binding(
            intent=old["intent_v1"],
            execution_capsule=old["execution_capsule_v1"],
            request_id="NEW-QUESTION",
            revision=1,
            parent_request_id=None,
            outcome_ids=old["request"]["outcome_ids"],
            action=old["action"],
            source=HostSource("OWNER", "new-question", old["request"]["source"]["content_sha256"]),
        )
        context = compile_goal_context(self.root, goal)
        self.assertEqual(context["reason"], "OPEN_ORIGINAL_OUTCOMES")
        self.assertEqual(context["decision"], "BLOCKED")
        self.assertEqual(context["request"]["id"], "NEW-QUESTION")


if __name__ == "__main__":
    unittest.main()
