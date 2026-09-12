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


class ProjectRoadmapRoutingTests(unittest.TestCase):
    def test_projectless_information_does_not_create_a_roadmap(self) -> None:
        result = route_project_task(ProjectTaskFacts(project_known=False, relation="INFORMATION"))
        self.assertEqual("ANSWER_ONLY", result["action"])
        self.assertFalse(result["roadmap_required"])

    def test_small_project_task_is_immediately_attached_as_a_step(self) -> None:
        result = route_project_task(
            ProjectTaskFacts(project_known=True, relation="RELATED", size_class="SHORT"),
            master_roadmap_id="MASTER",
            current_child_roadmap_id="CHILD-1",
        )
        self.assertEqual("ATTACH_STEP", result["action"])
        self.assertEqual("CHILD-1", result["target_roadmap_id"])
        self.assertTrue(result["roadmap_required"])

    def test_distinct_large_outcome_creates_a_second_child_roadmap(self) -> None:
        result = route_project_task(
            ProjectTaskFacts(project_known=True, relation="DISTINCT_OUTCOME", size_class="LARGE"),
            master_roadmap_id="MASTER",
            current_child_roadmap_id="CHILD-1",
            existing_child_roadmap_ids=("CHILD-1",),
        )
        self.assertEqual("CREATE_CHILD_ROADMAP", result["action"])
        self.assertEqual("MASTER", result["parent_roadmap_id"])
        self.assertEqual("CHILD-1", result["return_to_roadmap_id"])
        self.assertEqual(2, result["child_ordinal"])

    def test_related_large_extension_reuses_the_current_child_roadmap(self) -> None:
        result = route_project_task(
            ProjectTaskFacts(project_known=True, relation="EXTENSION", size_class="LARGE"),
            master_roadmap_id="MASTER",
            current_child_roadmap_id="CHILD-1",
        )
        self.assertEqual("EXTEND_CHILD_ROADMAP", result["action"])
        self.assertEqual("CHILD-1", result["target_roadmap_id"])

    def test_medium_work_gets_a_built_in_recipe_without_new_master(self) -> None:
        result = route_project_task(
            ProjectTaskFacts(project_known=True, relation="RELATED", size_class="MEDIUM"),
            master_roadmap_id="MASTER",
            current_child_roadmap_id="CHILD-1",
        )
        self.assertEqual("EXTEND_CHILD_ROADMAP", result["action"])
        self.assertEqual("builtin.medium-v1", result["recipe_id"])
        self.assertEqual(["scope", "plan", "change", "verify", "record"], result["method_steps"])

    def test_side_topic_is_parked_with_exact_return_anchor(self) -> None:
        result = route_project_task(
            ProjectTaskFacts(project_known=True, relation="SIDE_TOPIC", size_class="SHORT"),
            master_roadmap_id="MASTER",
            current_child_roadmap_id="CHILD-1",
            current_step_id="STEP-7",
        )
        self.assertEqual("PARK_AND_RETURN", result["action"])
        self.assertEqual("CHILD-1", result["return_to_roadmap_id"])
        self.assertEqual("STEP-7", result["return_to_step_id"])

    def test_known_project_requires_a_master_roadmap(self) -> None:
        with self.assertRaisesRegex(ValueError, "master roadmap"):
            route_project_task(ProjectTaskFacts(project_known=True))


class ContextEconomyTests(unittest.TestCase):
    def test_unchanged_context_is_referenced_instead_of_reloaded(self) -> None:
        sources = (
            ContextSource("current-step", 3, "a" * 64, 1000, "CURRENT_STEP"),
            ContextSource("return-anchor", 2, "b" * 64, 800, "RETURN_ANCHOR"),
            ContextSource("old-analysis", 5, "c" * 64, 6000, "SUPPORTING"),
            ContextSource("changed-decision", 2, "d" * 64, 1200, "DECISION"),
        )
        result = plan_context_load(
            sources,
            previous_digests={"old-analysis": "c" * 64, "changed-decision": "e" * 64},
            available_source_ids=("old-analysis",),
            max_bytes=4000,
        )
        self.assertEqual(
            ["current-step", "return-anchor", "changed-decision"], result["load_source_ids"]
        )
        self.assertEqual(["old-analysis"], result["reference_source_ids"])
        self.assertEqual(
            ["current-step", "return-anchor", "changed-decision"], result["required_source_ids"]
        )
        self.assertEqual(0, result["omitted_bytes"])
        self.assertEqual(6000, result["referenced_bytes"])
        self.assertEqual(0.0, result["omission_percent"])
        self.assertGreaterEqual(result["reduction_percent"], 30)
        self.assertLessEqual(result["loaded_bytes"], 4000)

    def test_context_plan_is_deterministic_for_unordered_input(self) -> None:
        sources = (
            ContextSource("b", 1, "b" * 64, 100, "SUPPORTING"),
            ContextSource("a", 1, "a" * 64, 100, "CURRENT_STEP"),
        )
        self.assertEqual(
            plan_context_load(sources, max_bytes=1000),
            plan_context_load(tuple(reversed(sources)), max_bytes=1000),
        )

    def test_required_context_cannot_silently_overflow_the_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "required context"):
            plan_context_load(
                (ContextSource("current", 1, "a" * 64, 1001, "CURRENT_STEP"),),
                max_bytes=1000,
            )

    def test_new_session_does_not_count_unavailable_digest_as_loaded_context(self) -> None:
        sources = (
            ContextSource("current", 1, "a" * 64, 1000, "CURRENT_STEP"),
            ContextSource("supporting", 1, "b" * 64, 9000, "SUPPORTING"),
        )
        result = plan_context_load(
            sources,
            previous_digests={"supporting": "b" * 64},
            available_source_ids=(),
            max_bytes=3000,
        )
        self.assertEqual(["current"], result["load_source_ids"])
        self.assertEqual(["supporting"], result["skipped_source_ids"])
        self.assertEqual(0, result["referenced_bytes"])
        self.assertTrue(result["availability_checked"])


class ExecutionDecisionTests(unittest.TestCase):
    def test_safe_open_work_continues_without_premature_stop(self) -> None:
        result = decide_execution(ExecutionFacts(authority_granted=True, safe_action_ready=True))
        self.assertEqual("CONTINUE", result["decision"])

    def test_not_ready_does_not_authorize_a_mutation_or_claim_safe_work(self) -> None:
        result = decide_execution(ExecutionFacts(authority_granted=True, safe_action_ready=False))
        self.assertEqual("WAIT_FOR_SAFE_ACTION", result["decision"])
        self.assertEqual("NO_SAFE_ACTION_READY", result["reason"])
        self.assertFalse(result["technical_mutation_allowed"])

    def test_only_material_choice_requests_owner(self) -> None:
        result = decide_execution(
            ExecutionFacts(
                authority_granted=True,
                safe_action_ready=True,
                material_choice_required=True,
            )
        )
        self.assertEqual("ASK_OWNER", result["decision"])

    def test_rollover_hands_off_without_losing_return_anchor(self) -> None:
        result = decide_execution(
            ExecutionFacts(
                authority_granted=True,
                safe_action_ready=True,
                rollover_required=True,
                return_to_roadmap_id="CHILD-1",
                return_to_step_id="STEP-7",
            )
        )
        self.assertEqual("HANDOFF", result["decision"])
        self.assertEqual("CHILD-1", result["return_to_roadmap_id"])
        self.assertEqual("STEP-7", result["return_to_step_id"])

    def test_completion_requires_closed_work_and_evidence(self) -> None:
        self.assertEqual(
            "COMPLETE",
            decide_execution(
                ExecutionFacts(
                    authority_granted=True,
                    safe_action_ready=False,
                    open_steps=False,
                    evidence_complete=True,
                )
            )["decision"],
        )
        self.assertEqual(
            "WAIT_FOR_SAFE_ACTION",
            decide_execution(
                ExecutionFacts(
                    authority_granted=True,
                    safe_action_ready=False,
                    open_steps=False,
                    evidence_complete=False,
                )
            )["decision"],
        )

    def test_feedback_is_parked_and_returns_without_technical_mutation(self) -> None:
        result = decide_execution(
            ExecutionFacts(
                authority_granted=True,
                safe_action_ready=True,
                feedback_only=True,
                return_to_roadmap_id="CHILD-1",
                return_to_step_id="STEP-7",
            )
        )
        self.assertEqual("PARK_AND_RETURN", result["decision"])
        self.assertFalse(result["technical_mutation_allowed"])


if __name__ == "__main__":
    unittest.main()
