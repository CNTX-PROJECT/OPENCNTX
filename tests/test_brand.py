from __future__ import annotations

import colorsys
import hashlib
import os
import re
import struct
import subprocess
import sys
import unittest
import zlib
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets" / "brand"
RENDERER = ROOT / "tools" / "render_brand.py"

SVG_DIMENSIONS = {
    "opencntx-avatar.svg": (512, 512),
    "opencntx-social-preview.svg": (1280, 640),
    "opencntx-symbol-dark.svg": (256, 256),
    "opencntx-symbol-light.svg": (256, 256),
    "opencntx-wordmark-dark.svg": (800, 160),
    "opencntx-wordmark-light.svg": (800, 160),
}

PNG_DIMENSIONS = {
    "opencntx-avatar-512.png": (512, 512),
    "opencntx-icon-128.png": (128, 128),
    "opencntx-icon-32.png": (32, 32),
    "opencntx-social-preview-1280x640.png": (1280, 640),
}

PALETTE = {
    "#FFFFFF",
    "#F8FAFC",
    "#0F172A",
    "#0B1020",
    "#111827",
    "#171E32",
    "#DDA0DD",
    "#22D3EE",
    "#94A3B8",
}

ALLOWED_ELEMENTS = {"svg", "g", "title", "desc", "rect", "circle", "text", "tspan"}
ALLOWED_ATTRIBUTES = {
    "svg": {"width", "height", "viewBox", "role", "aria-labelledby"},
    "g": {"id", "fill", "aria-label"},
    "title": {"id"},
    "desc": {"id"},
    "rect": {"id", "x", "y", "width", "height", "fill"},
    "circle": {"cx", "cy", "r", "fill"},
    "text": {
        "id",
        "x",
        "y",
        "fill",
        "font-family",
        "font-size",
        "font-weight",
        "letter-spacing",
        "text-anchor",
        "textLength",
        "lengthAdjust",
    },
    "tspan": {"fill"},
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _shape_left(element: ElementTree.Element) -> float:
    if "x" in element.attrib:
        return float(element.attrib["x"])
    return float(element.attrib["cx"]) - float(element.attrib["r"])


def _png(path: Path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError(f"not a PNG: {path.name}")
    offset = 8
    chunks = []
    payloads: dict[bytes, list[bytes]] = {}
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        name = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        chunks.append(name)
        payloads.setdefault(name, []).append(payload)
        offset += 12 + length
    header = payloads[b"IHDR"][0]
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", header
    )
    raw = zlib.decompress(b"".join(payloads[b"IDAT"]))
    return (
        chunks,
        (width, height),
        (bit_depth, color_type, compression, filtering, interlace),
        raw,
    )


class BrandTests(unittest.TestCase):
    def test_plum_is_the_only_purple_hue_in_every_public_visual(self) -> None:
        visual_roots = (BRAND, ROOT / "assets" / "docs")
        colors = set()
        for visual_root in visual_roots:
            for path in visual_root.glob("*.svg"):
                colors.update(re.findall(r"#[0-9A-F]{6}", path.read_text(encoding="utf-8")))

        purple_hues = set()
        for color in colors:
            red, green, blue = (int(color[index : index + 2], 16) / 255 for index in (1, 3, 5))
            hue, saturation, _ = colorsys.rgb_to_hsv(red, green, blue)
            degrees = hue * 360
            if 270 <= degrees <= 330 and saturation >= 0.15:
                purple_hues.add(color)

        self.assertEqual({"#DDA0DD"}, purple_hues)

    def test_svg_profile_dimensions_and_accessibility_are_exact(self) -> None:
        forbidden = (
            b"<script",
            b"<use",
            b"<image",
            b"<filter",
            b"<mask",
            b"<linearGradient",
            b"<radialGradient",
            b"<animate",
            b"<foreignObject",
            b"href=",
            b"url(",
            b"style=",
        )
        for name, dimensions in SVG_DIMENSIONS.items():
            with self.subTest(name=name):
                path = BRAND / name
                data = path.read_bytes()
                data.decode("utf-8", errors="strict")
                for token in forbidden:
                    self.assertNotIn(token, data)
                root = ElementTree.fromstring(data)
                self.assertEqual(str(dimensions[0]), root.attrib["width"])
                self.assertEqual(str(dimensions[1]), root.attrib["height"])
                self.assertEqual(f"0 0 {dimensions[0]} {dimensions[1]}", root.attrib["viewBox"])
                self.assertEqual("img", root.attrib["role"])
                self.assertEqual("title description", root.attrib["aria-labelledby"])
                self.assertEqual("title", _local_name(root[0].tag))
                self.assertEqual("title", root[0].attrib["id"])
                self.assertEqual("desc", _local_name(root[1].tag))
                self.assertEqual("description", root[1].attrib["id"])
                for element in root.iter():
                    local = _local_name(element.tag)
                    self.assertIn(local, ALLOWED_ELEMENTS)
                    self.assertTrue(
                        set(element.attrib).issubset(ALLOWED_ATTRIBUTES[local]),
                        (name, local, element.attrib),
                    )
                    fill = element.attrib.get("fill")
                    if fill:
                        self.assertIn(fill, PALETTE)

    def test_wordmarks_use_one_rounded_text_run_and_exact_plum(self) -> None:
        expected_open = {
            "opencntx-wordmark-light.svg": "#0F172A",
            "opencntx-wordmark-dark.svg": "#FFFFFF",
        }
        for name, open_fill in expected_open.items():
            root = ElementTree.parse(BRAND / name).getroot()
            groups = {
                element.attrib.get("id"): element
                for element in root
                if _local_name(element.tag) == "g"
            }
            self.assertFalse(
                any(
                    _local_name(element.tag) == "rect"
                    and element.attrib.get("width") == "800"
                    and element.attrib.get("height") == "160"
                    for element in root
                ),
                f"embedded wordmark must have a transparent canvas: {name}",
            )
            self.assertEqual("OPENCNTX", groups["wordmark"].attrib["aria-label"])
            wordmark = next(iter(groups["wordmark"]))
            self.assertEqual("text", _local_name(wordmark.tag))
            self.assertEqual(
                "Trebuchet MS, Trebuchet, Arial, sans-serif",
                wordmark.attrib["font-family"],
            )
            self.assertEqual("-0.015em", wordmark.attrib["letter-spacing"])
            self.assertEqual("spacing", wordmark.attrib["lengthAdjust"])
            spans = list(wordmark)
            self.assertEqual(["open", "cntx"], [span.text for span in spans])
            self.assertEqual(
                [open_fill, "#DDA0DD"],
                [span.attrib["fill"] for span in spans],
            )

    def test_standalone_social_preview_keeps_its_owned_canvas(self) -> None:
        root = ElementTree.parse(BRAND / "opencntx-social-preview.svg").getroot()
        background = next(element for element in root if _local_name(element.tag) == "rect")
        self.assertEqual(
            {"x": "0", "y": "0", "width": "1280", "height": "640", "fill": "#0B1020"},
            background.attrib,
        )

    def test_wordmark_and_social_geometry_is_centered(self) -> None:
        for name in ("opencntx-wordmark-light.svg", "opencntx-wordmark-dark.svg"):
            root = ElementTree.parse(BRAND / name).getroot()
            groups = {element.attrib.get("id"): element for element in root}
            symbol_shapes = list(groups["avatar-tile"])
            left = min(_shape_left(shape) for shape in symbol_shapes)
            wordmark = next(iter(groups["wordmark"]))
            right = float(wordmark.attrib["x"]) + float(wordmark.attrib["textLength"])
            self.assertEqual(132.0, left)
            self.assertEqual(668.0, right)
            self.assertEqual(left, 800.0 - right)
            self.assertEqual(286.0, float(wordmark.attrib["x"]))

        social = ElementTree.parse(BRAND / "opencntx-social-preview.svg").getroot()
        social_wordmark = next(
            element for element in social.iter() if element.attrib.get("id") == "social-wordmark"
        )
        self.assertEqual(
            "Trebuchet MS, Trebuchet, Arial, sans-serif",
            social_wordmark.attrib["font-family"],
        )
        self.assertEqual("-0.015em", social_wordmark.attrib["letter-spacing"])
        self.assertEqual("spacing", social_wordmark.attrib["lengthAdjust"])
        self.assertEqual(
            ["open", "cntx"],
            [span.text for span in social_wordmark],
        )
        self.assertEqual(
            ["#FFFFFF", "#DDA0DD"],
            [span.attrib["fill"] for span in social_wordmark],
        )
        tagline = next(
            element for element in social.iter() if element.attrib.get("id") == "tagline"
        )
        self.assertEqual("116", tagline.attrib["x"])
        self.assertNotIn("text-anchor", tagline.attrib)
        self.assertEqual("Small context. Clear evidence. Any model.", tagline.text)

    def test_avatar_is_theme_neutral_symmetric_and_contains_no_text(self) -> None:
        for name in (
            "opencntx-avatar.svg",
            "opencntx-symbol-light.svg",
            "opencntx-symbol-dark.svg",
        ):
            with self.subTest(name=name):
                root = ElementTree.parse(BRAND / name).getroot()
                self.assertFalse(any(_local_name(element.tag) == "text" for element in root.iter()))
                groups = {element.attrib.get("id"): element for element in root}
                self.assertEqual("#0B1020", groups["avatar-tile"].attrib["fill"])
                self.assertEqual("#FFFFFF", groups["context-primary"].attrib["fill"])
                self.assertEqual("#DDA0DD", groups["context-accent"].attrib["fill"])
                evidence = next(
                    element for element in root if element.attrib.get("id") == "evidence-node"
                )
                self.assertEqual("#FFFFFF", evidence.attrib["fill"])

        light = (BRAND / "opencntx-symbol-light.svg").read_text(encoding="utf-8")
        dark = (BRAND / "opencntx-symbol-dark.svg").read_text(encoding="utf-8")
        for phrase in (
            '<title id="title">OPENCNTX symbol for light screens</title>',
            '<title id="title">OPENCNTX symbol for dark screens</title>',
        ):
            light = light.replace(phrase, '<title id="title">SYMBOL</title>')
            dark = dark.replace(phrase, '<title id="title">SYMBOL</title>')
        self.assertEqual(light, dark)

    def test_text_and_graphic_contrasts_meet_the_contract(self) -> None:
        text_pairs = (
            ("#111827", "#FFFFFF"),
            ("#0F172A", "#F8FAFC"),
            ("#F8FAFC", "#0B1020"),
            ("#94A3B8", "#0B1020"),
        )
        for foreground, background in text_pairs:
            self.assertGreaterEqual(_contrast(foreground, background), 4.5)
        self.assertGreaterEqual(_contrast("#DDA0DD", "#0B1020"), 4.5)
        self.assertGreaterEqual(_contrast("#FFFFFF", "#0B1020"), 4.5)

    def test_png_dimensions_profiles_and_transparency_are_exact(self) -> None:
        for name, dimensions in PNG_DIMENSIONS.items():
            with self.subTest(name=name):
                chunks, actual, profile, raw = _png(BRAND / name)
                self.assertEqual(b"IHDR", chunks[0])
                self.assertEqual(b"IEND", chunks[-1])
                self.assertIn(b"IDAT", chunks)
                self.assertEqual(dimensions, actual)
                self.assertEqual((8, 6, 0, 0, 0), profile)
                stride = dimensions[0] * 4 + 1
                self.assertEqual(stride * dimensions[1], len(raw))
                self.assertTrue(all(raw[row * stride] == 0 for row in range(dimensions[1])))
                alpha = []
                for row in range(dimensions[1]):
                    pixels = raw[row * stride + 1 : (row + 1) * stride]
                    alpha.extend(pixels[3::4])
                if "social-preview" in name:
                    self.assertEqual({255}, set(alpha))
                else:
                    self.assertEqual(0, min(alpha))
                    self.assertEqual(255, max(alpha))

    def test_hash_manifest_is_sorted_complete_and_current(self) -> None:
        manifest = (BRAND / "SHA256SUMS").read_bytes()
        self.assertNotIn(b"\r", manifest)
        self.assertNotIn(b"\n", manifest)
        lines = manifest.decode("ascii").split(" | ")
        parsed = [line.split("  ", 1) for line in lines]
        expected_paths = sorted(
            f"assets/brand/{name}" for name in (*SVG_DIMENSIONS, *PNG_DIMENSIONS)
        )
        self.assertEqual(expected_paths, [item[1] for item in parsed])
        for digest, relative in parsed:
            self.assertEqual(64, len(digest))
            data = (ROOT / relative).read_bytes()
            if relative.endswith(".svg"):
                data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            self.assertEqual(digest, hashlib.sha256(data).hexdigest(), relative)

    def test_standard_library_renderer_checks_all_assets(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONUTF8"] = "1"
        completed = subprocess.run(
            [sys.executable, str(RENDERER), "--check"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("BRAND_ASSETS_OK", completed.stdout.strip())


if __name__ == "__main__":
    unittest.main()
