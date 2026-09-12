"""Regression cases reproduced by the post-1.7.5 audit, not release claims."""

from __future__ import annotations

import unittest

from opencntx.project_planning import (
    ContextSource,
    ExecutionFacts,
    ProjectTaskFacts,
    decide_execution,
    plan_context_load,
    route_project_task,
)


class Release176Regressions(unittest.TestCase):
    def test_owner_decision_cannot_be_omitted_to_meet_budget(self) -> None:
        sources = (
            ContextSource("step", 1, "a" * 64, 1000, "CURRENT_STEP"),
            ContextSource("anchor", 1, "b" * 64, 1000, "RETURN_ANCHOR"),
            ContextSource("decision", 1, "c" * 64, 9000, "DECISION"),
        )
        with self.assertRaisesRegex(ValueError, "required context"):
            plan_context_load(sources, max_bytes=2000)

    def test_digest_without_current_availability_requires_loading(self) -> None:
        result = plan_context_load(
            (ContextSource("reference", 1, "a" * 64, 1000),),
            previous_digests={"reference": "a" * 64},
        )
        self.assertEqual(["reference"], result["load_source_ids"])
        self.assertEqual([], result["reference_source_ids"])

    def test_side_topic_without_step_does_not_claim_a_return_anchor(self) -> None:
        with self.assertRaisesRegex(ValueError, "current step"):
            route_project_task(ProjectTaskFacts(True, "SIDE_TOPIC"), master_roadmap_id="MASTER")

    def test_feedback_without_anchor_does_not_claim_resumability(self) -> None:
        with self.assertRaisesRegex(ValueError, "return"):
            decide_execution(ExecutionFacts(feedback_only=True))

    def test_information_recipe_has_no_change_or_release_step(self) -> None:
        for size in ("SHORT", "MEDIUM", "LARGE", "MEGA"):
            with self.subTest(size=size):
                result = route_project_task(
                    ProjectTaskFacts(True, "INFORMATION", size), master_roadmap_id="MASTER"
                )
                self.assertFalse(
                    {"change", "implement", "release"}.intersection(result["method_steps"])
                )

    def test_gap_in_identifiers_does_not_reuse_a_reserved_number(self) -> None:
        result = route_project_task(
            ProjectTaskFacts(True, "DISTINCT_OUTCOME", "LARGE"),
            master_roadmap_id="MASTER",
            existing_child_roadmap_ids=("CHILD-1", "CHILD-3"),
        )
        self.assertEqual(4, result["child_ordinal"])

    def test_new_project_build_has_a_bootstrap_recipe(self) -> None:
        result = route_project_task(ProjectTaskFacts(False, "DISTINCT_OUTCOME", "MEGA"))
        self.assertEqual("BOOTSTRAP_PROJECT", result["action"])
        self.assertTrue(result["roadmap_required"])
        self.assertIn("master-roadmap", result["method_steps"])


if __name__ == "__main__":
    unittest.main()
