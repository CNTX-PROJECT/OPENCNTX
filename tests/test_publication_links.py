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


if __name__ == "__main__":
    unittest.main()
