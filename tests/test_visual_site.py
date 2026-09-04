from __future__ import annotations

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class SurfaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, {key: value or "" for key, value in attrs}))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        item / 12.92 if item <= 0.04045 else ((item + 0.055) / 1.055) ** 2.4 for item in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class VisualSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (SITE / "components.html").read_text(encoding="utf-8")
        self.css = (SITE / "assets/opencntx.css").read_text(encoding="utf-8")
        self.tokens = json.loads(
            (ROOT / "assets/design-system/tokens-v1.json").read_text(encoding="ascii")
        )
        self.parser = SurfaceParser()
        self.parser.feed(self.html)

    def test_component_reference_is_semantic_and_dependency_free(self) -> None:
        tags = [tag for tag, _ in self.parser.elements]
        self.assertEqual(tags.count("main"), 1)
        self.assertEqual(tags.count("h1"), 1)
        self.assertIn("nav", tags)
        self.assertNotIn("script", tags)
        self.assertNotIn("style", tags)
        for tag, attrs in self.parser.elements:
            if tag == "img":
                self.assertTrue(attrs.get("alt"))
                self.assertTrue(attrs.get("width"))
                self.assertTrue(attrs.get("height"))
            for key in ("href", "src", "srcset"):
                self.assertNotRegex(attrs.get(key, ""), r"^https?://")

    def test_all_declared_states_have_text_or_interaction_evidence(self) -> None:
        rendered = " ".join(self.parser.text).upper()
        evidence = {
            "ACTIVE": ':ACTIVE,\n.BUTTON[DATA-STATE="ACTIVE"]',
            "FOCUS_VISIBLE": ":FOCUS-VISIBLE",
            "HOVER": ":HOVER",
        }
        for state in self.tokens["component_states"]:
            with self.subTest(state=state):
                self.assertTrue(state in rendered or evidence.get(state, "") in self.css.upper())

    def test_site_css_uses_tokens_and_accessible_motion_modes(self) -> None:
        self.assertIn("../../assets/design-system/tokens-v1.css", self.css)
        self.assertNotRegex(self.css, r"#[0-9a-fA-F]{3,8}")
        self.assertIn("prefers-reduced-motion: reduce", self.css)
        self.assertIn("forced-colors: active", self.css)
        self.assertIn("focus-visible", self.css)

    def test_primary_text_and_brand_control_contrast_meet_wcag_aa(self) -> None:
        for mode in ("light", "dark"):
            palette = self.tokens[mode]
            with self.subTest(mode=mode, pair="text"):
                self.assertGreaterEqual(_contrast(palette["text"], palette["canvas"]), 4.5)
            with self.subTest(mode=mode, pair="muted"):
                self.assertGreaterEqual(_contrast(palette["text-muted"], palette["canvas"]), 4.5)
            with self.subTest(mode=mode, pair="brand"):
                self.assertGreaterEqual(_contrast(palette["brand-ink"], palette["brand"]), 4.5)

    def test_no_unclassified_raw_visual_values_outside_token_source(self) -> None:
        raw_lengths = re.findall(r"(?<!var\()(?<![-\w])\d+(?:\.\d+)?(?:rem|px)", self.css)
        allowlisted = {
            "0.01ms",
            "0.05rem",
            "0.0625rem",
            "0.1rem",
            "0.12rem",
            "0.16rem",
            "0.2rem",
            "0.22rem",
            "0.25rem",
            "0.35rem",
            "0.45rem",
            "0.65rem",
            "0.8s",
            "1px",
            "1rem",
            "1.1rem",
            "1.12rem",
            "1.35rem",
            "2rem",
            "2.9rem",
            "4.5rem",
            "10rem",
            "15rem",
            "18rem",
            "28rem",
            "32rem",
            "44rem",
            "999px",
        }
        self.assertEqual(set(raw_lengths) - allowlisted, set())


if __name__ == "__main__":
    unittest.main()
