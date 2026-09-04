from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.visual_quality_gate import run_checks

ROOT = Path(__file__).resolve().parents[1]


class VisualQualityGateTests(unittest.TestCase):
    def test_all_visual_quality_checks_pass(self) -> None:
        self.assertEqual(
            run_checks(),
            [
                "TOKENS",
                "CONTRAST",
                "SURFACES",
                "SEMANTICS",
                "LINKS",
                "ASSETS",
                "VIEWPORT",
                "REDUCED_MOTION",
                "FORCED_COLORS",
                "PERFORMANCE_BUDGET",
                "VISUAL_BASELINE",
            ],
        )

    def test_performance_field_metrics_are_not_claimed(self) -> None:
        budget = json.loads((ROOT / "site/performance-budget-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(budget["field_metrics"]["status"], "NOT_AVAILABLE_UNPUBLISHED")
        self.assertEqual(budget["javascript_max_bytes"], 0)
        self.assertEqual(budget["remote_runtime_requests_max"], 0)

    def test_baseline_requires_human_review_on_difference(self) -> None:
        baseline = json.loads(
            (ROOT / "assets/design-system/visual-baseline-v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(baseline["review_policy"], "HUMAN_REVIEW_REQUIRED_ON_DIFF")
        self.assertEqual(len(baseline["files"]), 8)


if __name__ == "__main__":
    unittest.main()
