"""Offline documentation regression checks, including deliberately broken fixtures."""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
_module = importlib.import_module("publication_links")
anchors = _module.anchors
check_links = _module.check_links
references = _module.references


class PublicationLinkTests(unittest.TestCase):
    def test_duplicate_heading_anchors(self) -> None:
        self.assertEqual(anchors("# Hello\n## Hello\n## Hello\n"), {"hello", "hello-1", "hello-2"})

    def test_fenced_examples_do_not_create_navigation(self) -> None:
        self.assertEqual(references("```text\n[bad](missing.md)\n```\n[ok](real.md)"), ["real.md"])

    def test_missing_paths_and_anchors_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "README.md").write_text("# Home\n[bad](absent.md)\n[wrong](other.md#absent)\n")
            (root / "other.md").write_text("# Present\n")
            self.assertEqual(len(check_links(root)["errors"]), 2)

    def test_html_assets_and_markdown_reference_links(self) -> None:
        value = '<img src="image.svg"><source srcset="dark.svg">\n[guide]: notes.md\n'
        self.assertEqual(references(value), ["image.svg", "dark.svg", "notes.md"])

    def test_current_repository_navigation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        report = check_links(root)
        self.assertEqual(report["errors"], [])

    def test_original_visual_documentation_is_preserved(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / 'README.md').read_text(encoding="utf-8")
        self.assertIn(
            '<picture><source media="(prefers-color-scheme: dar'
            'k)" srcset="assets/brand/opencntx-wordmark-dark.sv'
            'g"><img src="assets/brand/opencntx-wordmark-light.'
            'svg" width="640" alt="OPENCNTX"></picture>',
            text,
        )
        self.assertIn(
            '![Your local workspace holds project knowledge; Gi'
            'tHub is an optional remote copy; a notes app is a '
            'readable view.](assets/docs/knowledge-ecosystem.sv'
            'g)',
            text,
        )
        self.assertIn(
            '![Choose a task, load relevant context, work and v'
            'erify, save evidence, then continue.](assets/docs/'
            'task-journey.svg)',
            text,
        )
        self.assertIn(
            '```mermaid\nflowchart TD\n    M["Project master"] --'
            '> A["Child A: current outcome"]\n    M --> B["Child'
            ' B: independent outcome"]\n    A --> C["Current ste'
            'p + relevant context"]\n    C --> D["Work → verify '
            '→ save evidence"]\n    D --> E["Next step or comple'
            'ted outcome"]\n    C -. "Side question" .-> P["Reme'
            'mber return step"]\n    P -. "Resume" .-> C\n```',
            text,
        )
        text = (root / 'docs/README.md').read_text(encoding="utf-8")
        self.assertIn(
            '<picture>\n  <source media="(prefers-color-scheme: '
            'dark)" srcset="../assets/docs/opencntx-overview-da'
            'rk.svg">\n  <img src="../assets/docs/opencntx-overv'
            'iew.svg" alt="Select local files, review a small c'
            'ontext package, verify exact bytes and choose whet'
            'her to share">\n</picture>',
            text,
        )
        text = (root / 'docs/releases.md').read_text(encoding="utf-8")
        self.assertIn(
            '<picture>\n  <source media="(prefers-color-scheme: '
            'dark)" srcset="../assets/docs/roadmap-dark.svg">\n '
            ' <img src="../assets/docs/roadmap.svg" alt="Histor'
            'ical foundation milestones through version 1.0.0, '
            'not completion of the current roadmap">\n</picture>',
            text,
        )


if __name__ == "__main__":
    unittest.main()
