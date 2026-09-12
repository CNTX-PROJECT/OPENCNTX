"""Publication checks for the release-aware continuing roadmap."""

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PAGES = (
    "README.md",
    "docs/README.md",
    "docs/roadmap.md",
    "docs/roadmap-plan.md",
    "docs/releases.md",
    "site/index.html",
)


class PublicRoadmapTests(unittest.TestCase):
    def test_primary_routes_point_to_the_roadmap_home(self) -> None:
        self.assertFalse((ROOT / "docs/roadmap-plan.nl.md").exists())
        with (ROOT / "pyproject.toml").open("rb") as project_file:
            metadata = tomllib.load(project_file)
        published = metadata["tool"]["opencntx"]["release"]["published_version"]
        for name in ("README.md", "docs/README.md", "site/index.html"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertIn("roadmap.md", text)
                self.assertIn("releases.md", text)
                self.assertIn(str(published), text)
        overview = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        self.assertIn("roadmap-plan.md", overview)
        self.assertIn("Fixed historical English snapshot", overview)
        self.assertIn(
            "/blob/f6edbbf6d9d81310c37a55036f7d9794e38e109b/docs/roadmap-plan.md",
            overview,
        )

    def test_all_tasks_and_findings_survive_publication(self) -> None:
        text = (ROOT / "docs/roadmap-plan.md").read_text(encoding="utf-8")
        tasks = re.findall(r"^### (N\d{2}) —", text, flags=re.MULTILINE)
        self.assertEqual([f"N{index:02d}" for index in range(1, 25)], tasks)
        for prefix, count in (("V", 12), ("F", 16), ("D", 10), ("T", 12)):
            for index in range(1, count + 1):
                self.assertIn(f"{prefix}{index:02d}", text)
        self.assertIn("S01", text)
        self.assertIn("target_version: 1.7.3", text)
        self.assertIn("planning_revision: 4", text)
        self.assertIn("Reliability set shipped in v1.7.3", text)
        self.assertNotIn("- [x]", text.lower())

    def test_only_explicit_extensions_are_deferred(self) -> None:
        text = (ROOT / "docs/roadmap-plan.md").read_text(encoding="utf-8")
        tasks = re.findall(
            r"^### (N\d{2}) — [^\n]+\n\n- \[ \] \*\*Status: ([^\n]+)",
            text,
            flags=re.MULTILINE,
        )
        self.assertEqual(24, len(tasks))
        deferred = {task for task, status in tasks if status.startswith("Deferred")}
        self.assertEqual({"N18", "N19", "N21"}, deferred)
        self.assertEqual(21, sum(status == "Planned**" for _, status in tasks))
        self.assertIn("N06A — early", text)
        self.assertIn("N06B — later", text)

    def test_release_scope_and_continuing_plan_are_distinct(self) -> None:
        plan = (ROOT / "docs/roadmap-plan.md").read_text(encoding="utf-8")
        overview = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        releases = (ROOT / "docs/releases.md").read_text(encoding="utf-8")
        self.assertIn("published_baseline: 1.7.3", plan)
        self.assertIn("Published software — v1.7.5 Stable", releases)
        self.assertIn("release scope", releases)
        self.assertIn("remaining work", releases.lower())
        self.assertIn("twelve failed tasks out of one hundred", overview)
        self.assertIn("two long routes of 100 tasks each", overview)

    def test_public_pages_exclude_private_material_and_old_language(self) -> None:
        for name in PUBLIC_PAGES:
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertNotIn("[[", text)
                self.assertNotRegex(text, r"(?i)\b[A-Z]:[\\/]")
                self.assertNotIn("analysis-evidence/", text)
                for old_label in ("Volledige", "Nederlands", "full Dutch plan", 'lang="nl"'):
                    self.assertNotIn(old_label, text)

    def test_public_markdown_links_and_local_anchors_resolve(self) -> None:
        for name in PUBLIC_PAGES:
            if not name.endswith(".md"):
                continue
            path = ROOT / name
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if target.startswith(("https://", "http://")):
                    continue
                file_part, _, anchor = target.partition("#")
                resolved = (path.parent / file_part).resolve() if file_part else path
                with self.subTest(page=name, target=target):
                    self.assertTrue(resolved.is_relative_to(ROOT))
                    self.assertTrue(resolved.is_file())
                    if anchor:
                        headings = re.findall(
                            r"^#{1,6} (.+)$",
                            resolved.read_text(encoding="utf-8"),
                            flags=re.MULTILINE,
                        )
                        slugs = {
                            re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
                            for heading in headings
                        }
                        self.assertIn(anchor, slugs)


if __name__ == "__main__":
    unittest.main()
