from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opencntx.knowledge import KnowledgeError
from opencntx.visual_design import build_visual_review
from opencntx.visual_integration import (
    apply_visual_integration,
    preview_visual_integration,
    rollback_visual_integration,
)
from tests.test_visual_design import intent


class VisualIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ocx-visual-integration-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "10 - Parent.md"
        self.before = b"# Parent\r\n\r\n[Child](child.md#anchor)\r\n"
        self.source.write_bytes(self.before)
        (self.root / "child.md").write_text("# Anchor\n", encoding="utf-8")
        self.brief = intent()
        self.plan = preview_visual_integration(self.root, self.source.name, self.brief)
        # Simulated approval is confined to this disposable test fixture.
        self.review = build_visual_review(self.brief, human_review_status="APPROVED")

    def test_apply_second_run_and_exact_rollback_preserve_original_structure(self) -> None:
        result = apply_visual_integration(self.root, self.plan, self.brief, self.review)
        self.assertEqual(result["writes"], 3)
        self.assertTrue(self.source.read_bytes().startswith(self.before))
        self.assertEqual((self.root / "child.md").read_text(encoding="utf-8"), "# Anchor\n")
        snapshot = {
            str(path): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
            if path.is_file()
        }
        again = apply_visual_integration(self.root, self.plan, self.brief, self.review)
        self.assertEqual(again["writes"], 0)
        self.assertEqual(
            snapshot,
            {
                str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*")
                if path.is_file()
            },
        )
        self.assertEqual(rollback_visual_integration(self.root, self.plan)["status"], "RESTORED")
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertEqual(rollback_visual_integration(self.root, self.plan)["writes"], 0)

    def test_pending_review_and_source_drift_do_not_write(self) -> None:
        with self.assertRaises(KnowledgeError):
            apply_visual_integration(
                self.root, self.plan, self.brief, build_visual_review(self.brief)
            )
        self.assertEqual(self.source.read_bytes(), self.before)
        self.source.write_bytes(self.before + b"new work")
        with self.assertRaises(KnowledgeError):
            apply_visual_integration(self.root, self.plan, self.brief, self.review)
        self.assertTrue(self.source.read_bytes().endswith(b"new work"))

    def test_rollback_never_overwrites_new_user_work(self) -> None:
        apply_visual_integration(self.root, self.plan, self.brief, self.review)
        self.source.write_bytes(self.source.read_bytes() + b"new user work")
        with self.assertRaises(KnowledgeError):
            rollback_visual_integration(self.root, self.plan)
        self.assertTrue(self.source.read_bytes().endswith(b"new user work"))

    def test_receipt_write_failure_restores_original_document(self) -> None:
        with (
            patch(
                "opencntx.visual_integration._atomic_json", side_effect=OSError("fixture disk full")
            ),
            self.assertRaises(KnowledgeError),
        ):
            apply_visual_integration(self.root, self.plan, self.brief, self.review)
        self.assertEqual(self.source.read_bytes(), self.before)

    def test_malformed_plan_types_and_receipt_fail_without_source_changes(self) -> None:
        from opencntx.knowledge import _canonical_json, _digest

        for field, value in (("format_version", True), ("path", []), ("mode", "UNKNOWN")):
            plan = self.plan | {field: value}
            plan["plan_digest"] = _digest(
                _canonical_json({key: item for key, item in plan.items() if key != "plan_digest"})
            )
            with self.subTest(field=field), self.assertRaises(KnowledgeError):
                apply_visual_integration(self.root, plan, self.brief, self.review)
            self.assertEqual(self.source.read_bytes(), self.before)
        apply_visual_integration(self.root, self.plan, self.brief, self.review)
        integrated = self.source.read_bytes()
        receipt = self.root / ".opencntx/visual-integrations" / (self.plan["plan_digest"] + ".json")
        receipt.write_bytes(b"[]")
        with self.assertRaises(KnowledgeError):
            apply_visual_integration(self.root, self.plan, self.brief, self.review)
        self.assertEqual(self.source.read_bytes(), integrated)
        rollback_visual_integration(self.root, self.plan)
        self.assertEqual(self.source.read_bytes(), self.before)


if __name__ == "__main__":
    unittest.main()
