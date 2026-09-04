from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from opencntx.continuity import ContinuityError
from opencntx.visual_design import (
    MAX_REFINEMENT_ROUNDS,
    ROLE_ID,
    ROLE_LABELS,
    build_visual_intent,
    build_visual_review,
    validate_visual_intent,
    validate_visual_review,
)

ROOT = Path(__file__).resolve().parents[1]


def intent(*, refinement_round: int = 0) -> dict[str, object]:
    return build_visual_intent(
        surface_id="SITE-HOME",
        medium="WEB",
        user_task="Understand OPENCNTX and start safely.",
        primary_message="Keep context small, explicit, and verifiable.",
        content_priority=["Value", "How it works", "Safe start"],
        required_states=["DEFAULT", "FOCUS_VISIBLE", "ERROR", "SUCCESS"],
        constraints=["No remote font", "No tracker", "Semantic text fallback"],
        accessibility_targets=["WCAG_2_2_AA", "KEYBOARD", "REDUCED_MOTION"],
        refinement_round=refinement_round,
    )


class VisualDesignTests(unittest.TestCase):
    def test_role_identity_and_deterministic_intent(self) -> None:
        first = intent()
        second = intent()
        self.assertEqual(ROLE_ID, "VISUAL_ARTIST")
        self.assertEqual(ROLE_LABELS["nl"], "VISUEEL ARTIST")
        self.assertEqual(first, second)
        self.assertEqual(validate_visual_intent(first), first)
        self.assertRegex(str(first["intent_digest"]), r"^[0-9a-f]{64}$")

    def test_intent_rejects_tampering_unknown_fields_and_round_four(self) -> None:
        altered = copy.deepcopy(intent())
        altered["primary_message"] = "Changed without digest"
        with self.assertRaises(ContinuityError):
            validate_visual_intent(altered)
        altered = copy.deepcopy(intent())
        altered["unknown"] = True
        with self.assertRaises(ContinuityError):
            validate_visual_intent(altered)
        with self.assertRaises(ContinuityError):
            intent(refinement_round=MAX_REFINEMENT_ROUNDS + 1)

    def test_joint_gate_needs_both_roles_and_human_review(self) -> None:
        brief = intent()
        pending = build_visual_review(brief)
        self.assertEqual(pending["decision"], "AWAITING_HUMAN_REVIEW")
        refined = build_visual_review(brief, visual_findings=["Hierarchy is unclear"])
        self.assertEqual(refined["decision"], "REFINE")
        complete = build_visual_review(brief, human_review_status="APPROVED")
        self.assertEqual(complete["decision"], "COMPLETE")
        self.assertEqual(validate_visual_review(complete), complete)

    def test_third_failed_refinement_stops(self) -> None:
        review = build_visual_review(
            intent(refinement_round=3),
            perfection_findings=["Contrast gate failed"],
        )
        self.assertEqual(review["decision"], "BLOCKED")
        self.assertEqual(review["stop_reason"], "REFINEMENT_LIMIT_REACHED")

    def test_schemas_are_closed_packaged_and_catalogued(self) -> None:
        names = {"visual-intent-v1.schema.json", "visual-review-v1.schema.json"}
        catalog = json.loads(
            (ROOT / "src/opencntx/schemas/continuity-contract-v1.json").read_text(encoding="utf-8")
        )
        self.assertTrue(names.issubset(catalog["schemas"]))
        for name in names:
            schema = json.loads((ROOT / "src/opencntx/schemas" / name).read_text(encoding="utf-8"))
            self.assertFalse(schema["additionalProperties"])

    def test_tokens_are_closed_complete_and_reproducible(self) -> None:
        source = ROOT / "assets/design-system/tokens-v1.json"
        tokens = json.loads(source.read_text(encoding="ascii"))
        self.assertEqual(tokens["format"], "opencntx-visual-tokens")
        self.assertEqual(tokens["light"]["brand"], "#DDA0DD")
        self.assertEqual(tokens["dark"]["brand"], "#DDA0DD")
        self.assertEqual(
            tokens["component_states"],
            sorted(
                {
                    "ACTIVE",
                    "BLOCKED",
                    "DEFAULT",
                    "DISABLED",
                    "EMPTY",
                    "ERROR",
                    "FOCUS_VISIBLE",
                    "HOVER",
                    "LOADING",
                    "SUCCESS",
                    "WARNING",
                }
            ),
        )
        completed = subprocess.run(
            [sys.executable, "tools/render_visual_tokens.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)


if __name__ == "__main__":
    unittest.main()
