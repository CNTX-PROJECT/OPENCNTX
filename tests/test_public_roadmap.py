"""Publication checks for the planned roadmap, not runtime feature tests."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicRoadmapTests(unittest.TestCase):
    def test_all_tasks_and_proposals_survive_publication(self) -> None:
        text = (ROOT / "docs/roadmap-plan.nl.md").read_text(encoding="utf-8")
        tasks = re.findall(r"^### (N\d{2}) —", text, flags=re.MULTILINE)
        self.assertEqual([f"N{index:02d}" for index in range(1, 25)], tasks)
        for index in range(1, 13):
            self.assertIn(f"V{index:02d}", text)
        for index in range(1, 17):
            self.assertIn(f"F{index:02d}", text)
        self.assertIn("target_version: 1.7.2", text)
        self.assertIn("planning_revision: 3", text)
        for index in range(1, 11):
            self.assertIn(f"D{index:02d}", text)
        self.assertIn("geen software-release 1.7.2", text)
        self.assertEqual(24, len(re.findall(r"^- \[ \] \*\*Status: Gepland", text, re.MULTILINE)))

    def test_public_plan_has_no_private_note_or_drive_links(self) -> None:
        text = (ROOT / "docs/roadmap-plan.nl.md").read_text(encoding="utf-8")
        self.assertNotIn("[[", text)
        self.assertNotRegex(text, r"(?i)\b[A-Z]:[\\/]")
        self.assertNotIn("analysis-evidence/", text)

    def test_roadmap_markdown_links_resolve_locally(self) -> None:
        for name in ("roadmap.md", "roadmap-plan.nl.md"):
            path = ROOT / "docs" / name
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if target.startswith(("https://", "http://", "#")):
                    continue
                with self.subTest(page=name, target=target):
                    resolved = (path.parent / target.split("#", 1)[0]).resolve()
                    self.assertTrue(resolved.is_relative_to(ROOT))
                    self.assertTrue(resolved.is_file())


if __name__ == "__main__":
    unittest.main()
