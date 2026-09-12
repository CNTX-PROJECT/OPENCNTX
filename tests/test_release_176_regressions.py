"""Regression cases reproduced by the post-1.7.5 audit, not release claims."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import release_176_efficiency

from opencntx.project_planning import (
    ContextSource,
    ExecutionFacts,
    ProjectTaskFacts,
    decide_execution,
    plan_context_load,
    route_project_task,
)


class Release176Regressions(unittest.TestCase):
    def test_acceptance_corpus_has_immutable_baseline_and_unique_case_ids(self) -> None:
        path = Path(__file__).resolve().parent / "fixtures/release-1.7.6/acceptance-corpus-v1.json"
        corpus = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("opencntx-1.7.6-acceptance-corpus", corpus["format"])
        self.assertEqual(
            "685d3738782c1e0ef2ebc7398d1f76593fae54b8",
            corpus["baseline"]["commit"],
        )
        self.assertEqual(4, len(corpus["baseline"]["assets"]))
        identifiers = [
            item["id"]
            for collection in ("failure_cases", "golden_tasks")
            for item in corpus[collection]
        ]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(10, len(corpus["failure_cases"]))
        self.assertEqual(8, len(corpus["golden_tasks"]))
        self.assertTrue(all(item.get("expected") for item in corpus["failure_cases"]))

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

    def test_efficiency_evidence_covers_all_frozen_scales(self) -> None:
        result = release_176_efficiency.measure(repeats=3)
        self.assertEqual("PASS", result["status"])
        cases = result["cases"]
        self.assertEqual([0, 100, 1000, 10000], [item["checkpoints"] for item in cases])
        self.assertTrue(all(item["read_bytes"] == 8192 for item in cases))
        self.assertTrue(all(item["reduction_percent"] >= 30 for item in cases[1:]))

    def test_release_176_schemas_are_closed_and_purpose_registered(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema_root = root / "src/opencntx/schemas"
        names = {
            "host-input-anchor-v1.schema.json",
            "host-input-ack-v1.schema.json",
            "installation-inventory-v1.schema.json",
            "managed-install-journal-v1.schema.json",
        }
        for name in names:
            with self.subTest(schema=name):
                schema = json.loads((schema_root / name).read_text(encoding="utf-8"))
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
        purposes = json.loads(
            (root / "tests/fixtures/quality/schema-purpose-v1.json").read_text(encoding="utf-8")
        )["new_schemas"]
        self.assertTrue(names.issubset(purposes))


if __name__ == "__main__":
    unittest.main()
