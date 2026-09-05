"""Portable continuation proof without invoking the Windows physical writer."""

from __future__ import annotations

import copy
import json
import unittest

from opencntx.continuity import ContinuityError, _digest, execution_state_capsule
from opencntx.goal_followup import (
    build_followup_evidence,
    compile_goal_context,
    enforce_goal_followup,
    load_followup_evidence,
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
from tests import test_goal_handoff as fixture


class PortableFollowupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixture.GoalHandoffTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def save(self, *values: dict, text_evidence: bool = False) -> None:
        refs = []
        for index, value in enumerate(values):
            path = f"evidence/followup-{index}.json"
            content = json.dumps(value).encode()
            (self.root / path).write_bytes(content)
            refs.append({"reference": path, "sha256": _digest(content)})
        if text_evidence:
            (self.root / "evidence/note.txt").write_bytes(b"Preserved ordinary evidence")
            refs.append(
                {
                    "reference": "evidence/note.txt",
                    "sha256": _digest(b"Preserved ordinary evidence"),
                }
            )
        self.fixture.nodes[1]["evidence"] = refs
        goal = self.fixture.current_goal()
        progress = build_goal_progress(goal, root_id="MAIN", nodes=self.fixture.nodes)
        persist_goal_progress(self.root, goal, progress, evidence_directory=self.fixture.evidence)
        self.fixture.goal = self.fixture.current_goal()

    def output(self, context: dict, language: str = "nl", **kwargs) -> dict:
        return build_output_contract(
            execution_capsule=execution_state_capsule(self.root),
            roadmap_label="Portable continuation",
            summary="Unverified completion must not be shown",
            language=language,
            metrics=extract_bound_session_metrics(
                session_id="portable", source_session_id="portable", chat_bytes=0, records=[]
            ),
            required_capability="TEST",
            reasoning_level="LOW",
            goal_context=context,
            **kwargs,
        )

    def test_missing_progress_preserves_open_outcomes(self) -> None:
        goal = self.fixture.goal
        self.assertEqual(load_followup_evidence(self.root, goal), build_followup_evidence(goal))
        context = compile_goal_context(self.root, goal)
        self.assertEqual(context["decision"], "CONTINUE")
        self.assertEqual(set(context["open_outcome_ids"]), {"PARENT-RESULT", "CHILD-PRESERVATION"})
        enforce_goal_followup(self.root, goal)

    def test_unrelated_evidence_does_not_become_recovery_authority(self) -> None:
        self.save({"ordinary": "source note"}, text_evidence=True)
        self.assertEqual(load_followup_evidence(self.root, self.fixture.goal)["attempts"], [])
        enforce_goal_followup(self.root, self.fixture.goal)

    def test_stop_survives_reopen_and_controls_both_output_languages(self) -> None:
        self.save(build_followup_evidence(self.fixture.goal, stopped=True))
        goal = self.fixture.current_goal()
        with self.assertRaisesRegex(ContinuityError, "OWNER_STOP"):
            enforce_goal_followup(self.root, goal)
        context = compile_goal_context(self.root, goal)
        self.assertEqual((context["decision"], context["reason"]), ("BLOCKED", "OWNER_STOP"))
        for language, message in (
            ("nl", "Gestopt op jouw verzoek"),
            ("en", "Stopped at your request"),
        ):
            output = self.output(context, language)
            self.assertEqual(output["next_action_state"], "BLOCKED")
            self.assertIn(message, render_output(output))
            self.assertNotIn("```", render_output(output))

    def test_failed_action_rebinds_only_unattempted_independent_outcome(self) -> None:
        observation = recovery_observation(self.fixture.goal, error_class="UNAVAILABLE")
        for count in (1, 3):
            self.save(build_followup_evidence(self.fixture.goal, attempts=[observation] * count))
            context = compile_goal_context(self.root, self.fixture.goal)
            self.assertEqual(context["reason"], "REBIND_INDEPENDENT_OUTCOME")
            self.assertEqual(context["next_outcome_id"], "CHILD-PRESERVATION")
            for language in ("nl", "en"):
                output = self.output(context, language)
                self.assertEqual(output["next_action_state"], "CONTINUE_AUTOMATICALLY")
                self.assertIn("CHILD-PRESERVATION", output["thereafter"])
                self.assertNotIn("```", render_output(output))
        self.fixture.nodes[2]["status"] = "BLOCKED"
        self.save(build_followup_evidence(self.fixture.goal, attempts=[observation] * 3))
        context = compile_goal_context(self.root, self.fixture.goal)
        self.assertEqual(
            (context["decision"], context["reason"]), ("BLOCKED", "RECOVERY_EXHAUSTED")
        )
        self.assertIsNone(context["next_outcome_id"])

    def test_all_blocked_nodes_cannot_appear_ready(self) -> None:
        self.fixture.nodes[1]["status"] = "BLOCKED"
        self.fixture.nodes[2]["status"] = "BLOCKED"
        self.save()
        context = compile_goal_context(self.root, self.fixture.goal)
        self.assertEqual(context["reason"], "NO_READY_ORIGINAL_OUTCOME")
        self.assertEqual(self.output(context)["next_action_state"], "BLOCKED")

    def test_open_partial_output_rejects_detours_and_external_override(self) -> None:
        self.save()
        goal = self.fixture.goal
        context = compile_goal_context(self.root, goal, proposed_outcome="PARENT-RESULT")
        self.assertIn("Nog niet volledig afgerond", render_output(self.output(context)))
        self.assertIn("Not fully complete", render_output(self.output(context, "en")))
        for kwargs in (
            {"proposed_outcome": "OTHER"},
            {"proposed_outcome": "CHILD-PRESERVATION"},
            {"future_idea": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ContinuityError):
                compile_goal_context(self.root, goal, **kwargs)
        with self.assertRaises(ContinuityError):
            self.output(context, external_action=True, exact_human_action="Unrelated action")
        self.save(build_followup_evidence(goal, stopped=True))
        with self.assertRaises(ContinuityError):
            self.output(context)

    def test_ambiguous_or_rehashed_foreign_followup_is_refused(self) -> None:
        value = build_followup_evidence(self.fixture.goal)
        self.save(value, value)
        with self.assertRaisesRegex(ContinuityError, "Multiple active"):
            load_followup_evidence(self.root, self.fixture.goal)
        self.save(value | {"followup_digest": "f" * 64})
        with self.assertRaisesRegex(ContinuityError, "another request"):
            load_followup_evidence(self.root, self.fixture.goal)

    def test_attempt_bounds_identity_and_fingerprints_are_checked(self) -> None:
        goal = self.fixture.goal
        observation = recovery_observation(goal, error_class="UNAVAILABLE")
        for kwargs in ({"stopped": 1}, {"attempts": {}}, {"attempts": [observation] * 151}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ContinuityError):
                build_followup_evidence(goal, **kwargs)
        for changes in (
            {"extra": True},
            {"request_id": "FOREIGN"},
            {"revision": 2},
            {"outcome_id": "FOREIGN"},
            {"fingerprint": "f" * 64},
            {"action_fingerprint": "f" * 64},
            {"capabilities_digest": "invalid"},
            {"relevant_evidence_digest": "invalid"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ContinuityError):
                build_followup_evidence(goal, attempts=[observation | changes])
        evidence = build_followup_evidence(goal)
        with self.assertRaises(ContinuityError):
            recovery_decision(goal, evidence | {"followup_digest": "f" * 64})
        for outcomes in (
            {"PARENT-RESULT": "PARTIAL"},
            {"PARENT-RESULT": "UNKNOWN", "CHILD-PRESERVATION": "BLOCKED"},
        ):
            with self.subTest(outcomes=outcomes), self.assertRaises(ContinuityError):
                plan_request_replacement(goal, goal, outcomes)

    def test_output_rejects_forged_context_even_with_valid_digest(self) -> None:
        from opencntx.continuity import _value_digest

        context = compile_goal_context(self.root, self.fixture.goal)
        for changes in (
            {"format_version": True},
            {"authority_changed": True},
            {"decision": "COMPLETE_ROADMAP"},
        ):
            forged = copy.deepcopy(context) | changes
            forged["context_digest"] = _value_digest(
                {k: v for k, v in forged.items() if k != "context_digest"}
            )
            with self.subTest(changes=changes), self.assertRaises(ContinuityError):
                self.output(forged)
