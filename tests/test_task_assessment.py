from __future__ import annotations

import json
import unittest
from importlib import resources
from unittest.mock import patch

from opencntx.continuity import ContinuityError, _value_digest
from opencntx.goal_binding import build_goal_binding
from opencntx.human_interface import assess_task_size
from opencntx.task_assessment import (
    TaskAssessment,
    TaskFacts,
    assess_bound_task,
    classify_task,
    require_assessed_broad_execution,
    validate_task_assessment,
)
from tests import test_goal_binding as fixture


class AssessmentTests(unittest.TestCase):
    def setUp(self) -> None:
        source = fixture.GoalBindingTests()
        source.setUp()
        self.goal = source.bound
        self.args = source.args

    def assess(self, facts: TaskFacts | None = None, **kwargs) -> TaskAssessment:
        return assess_bound_task(
            self.goal, facts or TaskFacts(), reason="Controlled fixture facts", **kwargs
        )

    def test_counting_is_projectless_and_proportionate(self) -> None:
        with (
            patch("pathlib.Path.mkdir", side_effect=AssertionError("No project creation")),
            patch("builtins.open", side_effect=AssertionError("No file I/O")),
        ):
            for count in (10, 100, 1000, 4000, 4001):
                result = assess_task_size(TaskFacts(kind="COUNT_ONLY", item_count=count))
                self.assertEqual(result["size_class"], "SHORT")
                self.assertEqual(result["required_planning"], "CHECKLIST")
                self.assertFalse(result["authority_granted"])

    def test_shipped_versioned_schema_matches_projection(self) -> None:
        schema = json.loads(
            resources.files("opencntx")
            .joinpath("schemas/task-assessment-v2.schema.json")
            .read_text(encoding="utf-8")
        )
        value = self.assess().payload()
        self.assertEqual(set(schema["required"]), set(value))
        self.assertEqual(set(schema["properties"]), set(value))
        self.assertIs(schema["additionalProperties"], False)
        for part in ("classification",):
            self.assertEqual(set(schema["properties"][part]["required"]), set(value[part]))

    def test_risk_remains_separate(self) -> None:
        result = classify_task(TaskFacts(risk="HIGH"))
        self.assertEqual(result["size_class"], "SHORT")
        self.assertEqual(result["risk"], "HIGH")
        self.assertFalse(result["authority_granted"])

    def test_semantic_complexity_not_item_count(self) -> None:
        cases = (
            (TaskFacts(kind="MULTI_PHASE", dependent_phases=3), "LARGE", "MAIN_ROADMAP"),
            (
                TaskFacts(kind="MULTI_STREAM", independent_large_streams=2),
                "MEGA",
                "MAIN_AND_CHILD_ROADMAPS",
            ),
            (
                TaskFacts(kind="FULL_COLLECTION_ANALYSIS", analysis_dimensions=4, item_count=10),
                "MEGA",
                "MAIN_AND_CHILD_ROADMAPS",
            ),
        )
        for facts, size, planning in cases:
            with self.subTest(facts=facts):
                result = classify_task(facts)
                self.assertEqual(
                    (result["size_class"], result["required_planning"]), (size, planning)
                )
                with self.assertRaises(ContinuityError):
                    require_assessed_broad_execution(self.assess(facts), self.goal)

    def test_conflicting_or_invalid_facts_fail_closed(self) -> None:
        for facts in (
            TaskFacts(kind="COUNT_ONLY", dependent_phases=2),
            TaskFacts(kind="COUNT_ONLY", analysis_dimensions=1),
            TaskFacts(kind="MULTI_STREAM"),
            TaskFacts(kind="MULTI_PHASE"),
            TaskFacts(kind="FULL_COLLECTION_ANALYSIS"),
            TaskFacts(kind="OTHER"),
            TaskFacts(item_count=True),
            TaskFacts(item_count=-1),
            TaskFacts(dependent_phases=True),
            TaskFacts(independent_large_streams=51),
            TaskFacts(uncertainty="UNKNOWN"),
            TaskFacts(risk="NONE"),
        ):
            with self.subTest(facts=facts), self.assertRaises(ContinuityError):
                classify_task(facts)

    def test_source_probe_required_then_broad_short_action_allowed(self) -> None:
        probe = self.assess(TaskFacts(uncertainty="NEEDS_PROBE"))
        with self.assertRaises(ContinuityError):
            require_assessed_broad_execution(probe, self.goal)
        resolved = self.assess(previous=probe)
        require_assessed_broad_execution(resolved, self.goal)
        self.assertEqual(
            resolved.payload()["previous_assessment_digest"], probe.payload()["assessment_digest"]
        )

    def test_grow_and_shrink_preserves_original_obligations(self) -> None:
        first = self.assess()
        bigger = self.assess(
            TaskFacts(kind="MULTI_STREAM", independent_large_streams=2), previous=first
        )
        smaller = self.assess(previous=bigger)
        for key in ("request_id", "outcome_ids", "original_source", "authority_state"):
            self.assertEqual(first.payload()[key], smaller.payload()[key])
        self.assertEqual(smaller.payload()["assessment_revision"], 3)
        self.assertFalse(smaller.payload()["authority_changed"])
        self.assertEqual(validate_task_assessment(smaller, self.goal), smaller.payload())

    def test_new_revision_keeps_history_and_all_outcomes(self) -> None:
        first = self.assess()
        new_goal = build_goal_binding(
            **(
                self.args
                | {"revision": 2, "outcome_ids": self.args["outcome_ids"] + ["ADDITIONAL"]}
            )
        )
        newer = assess_bound_task(
            new_goal, TaskFacts(), reason="Additional internal result", previous=first
        )
        self.assertEqual(newer.payload()["request_revision"], 2)
        self.assertEqual(newer.payload()["original_source"], first.payload()["original_source"])
        with self.assertRaises(ContinuityError):
            validate_task_assessment(first, new_goal)
        with self.assertRaises(ContinuityError):
            assess_bound_task(self.goal, TaskFacts(), reason="Stale", previous=newer)

    def test_reassessment_cannot_drop_outcomes_or_change_request_authority(self) -> None:
        first = self.assess()
        intent = self.args["intent"] | {"authority_state": "NOT_AUTHORIZED"}
        intent["intent_digest"] = _value_digest(
            {k: v for k, v in intent.items() if k != "intent_digest"}
        )
        for change in (
            {"request_id": "OTHER"},
            {"outcome_ids": ["PARENT-RESULT"]},
            {"intent": intent},
        ):
            with self.subTest(change=change):
                new_goal = build_goal_binding(**(self.args | change))
                with self.assertRaises(ContinuityError) as error:
                    assess_bound_task(new_goal, TaskFacts(), reason="Must refuse", previous=first)
                self.assertIn("original assignment", str(error.exception))

    def test_risk_change_is_not_ordinary_internal_replanning(self) -> None:
        with self.assertRaises(ContinuityError):
            self.assess(TaskFacts(risk="HIGH"), previous=self.assess())

    def test_rehashed_inconsistent_projection_refused(self) -> None:
        original = self.assess().payload()
        for key, value in (
            ("classification", original["classification"] | {"size_class": "MEGA"}),
            ("request_id", "OTHER"),
            ("authority_changed", True),
        ):
            altered = original | {key: value}
            altered["assessment_digest"] = _value_digest(
                {k: v for k, v in altered.items() if k != "assessment_digest"}
            )
            with self.subTest(key=key), self.assertRaises(ContinuityError):
                validate_task_assessment(TaskAssessment(json.dumps(altered)), self.goal)


if __name__ == "__main__":
    unittest.main()
