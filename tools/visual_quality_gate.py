from __future__ import annotations

import hashlib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
BASELINE = ROOT / "assets" / "design-system" / "visual-baseline-v1.json"


class _AuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, {name: value or "" for name, value in attrs}))


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        item / 12.92 if item <= 0.04045 else ((item + 0.055) / 1.055) ** 2.4 for item in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _local_reference(value: str) -> str:
    return value.split(",", 1)[0].strip().split(" ", 1)[0].split("#", 1)[0]


def _audit_html(path: Path) -> tuple[_AuditParser, set[Path]]:
    source = path.read_text(encoding="utf-8")
    parser = _AuditParser()
    parser.feed(source)
    tags = [tag for tag, _ in parser.elements]
    _require(tags.count("main") == 1, f"{path.name}: expected one main")
    _require(tags.count("h1") == 1, f"{path.name}: expected one h1")
    _require("nav" in tags, f"{path.name}: navigation missing")
    _require("script" not in tags, f"{path.name}: JavaScript is forbidden")
    ids = [attrs["id"] for _, attrs in parser.elements if attrs.get("id")]
    _require(len(ids) == len(set(ids)), f"{path.name}: duplicate id")
    resources: set[Path] = set()
    for tag, attrs in parser.elements:
        if tag == "img":
            _require(bool(attrs.get("alt")), f"{path.name}: image alt missing")
            _require(bool(attrs.get("width")), f"{path.name}: image width missing")
            _require(bool(attrs.get("height")), f"{path.name}: image height missing")
        for key in ("src", "srcset"):
            target = attrs.get(key, "")
            _require(not target.startswith(("http://", "https://")), f"{path.name}: remote asset")
            if target:
                resolved = (path.parent / _local_reference(target)).resolve()
                _require(resolved.is_relative_to(ROOT), f"{path.name}: asset escapes repository")
                _require(resolved.is_file(), f"{path.name}: missing asset {target}")
                resources.add(resolved)
        href = attrs.get("href", "")
        if not href or href.startswith(("#", "http://", "https://", "mailto:")):
            continue
        resolved = (path.parent / _local_reference(href)).resolve()
        _require(resolved.is_relative_to(ROOT), f"{path.name}: link escapes repository")
        _require(resolved.exists(), f"{path.name}: missing link {href}")
        if tag == "link":
            resources.add(resolved)
    return parser, resources


def run_checks() -> list[str]:
    checks: list[str] = []
    tokens = _load(ROOT / "assets/design-system/tokens-v1.json")
    _require(tokens["format"] == "opencntx-visual-tokens", "token format")
    for mode in ("light", "dark"):
        palette = tokens[mode]
        _require(_contrast(palette["text"], palette["canvas"]) >= 4.5, f"{mode} text contrast")
        _require(
            _contrast(palette["text-muted"], palette["canvas"]) >= 4.5,
            f"{mode} muted contrast",
        )
    checks.extend(("TOKENS", "CONTRAST"))

    inventory = _load(ROOT / "assets/design-system/surface-inventory-v1.json")
    allowed = set(inventory["required_statuses"])
    _require("UNKNOWN" not in allowed, "unknown inventory status")
    _require(all(item["status"] in allowed for item in inventory["surfaces"]), "surface status")
    checks.append("SURFACES")

    _, landing_resources = _audit_html(SITE / "index.html")
    _audit_html(SITE / "components.html")
    checks.extend(("SEMANTICS", "LINKS", "ASSETS"))

    css = (SITE / "assets/opencntx.css").read_text(encoding="utf-8")
    token_css = (ROOT / "assets/design-system/tokens-v1.css").read_text(encoding="utf-8")
    for marker in (
        "prefers-color-scheme: dark",
        "prefers-reduced-motion: reduce",
        "forced-colors: active",
        "focus-visible",
        "@media (max-width:",
    ):
        _require(marker in css + token_css, f"CSS mode missing: {marker}")
    checks.extend(("VIEWPORT", "REDUCED_MOTION", "FORCED_COLORS"))

    budget = _load(SITE / "performance-budget-v1.json")
    entrypoint = SITE / "index.html"
    _require(entrypoint.stat().st_size <= budget["local_entrypoint_max_bytes"], "entrypoint budget")
    resource_bytes = entrypoint.stat().st_size + sum(
        path.stat().st_size for path in landing_resources
    )
    _require(
        resource_bytes <= budget["local_initial_resources_max_bytes"], "initial resources budget"
    )
    _require(budget["javascript_max_bytes"] == 0, "JavaScript budget")
    _require(budget["remote_runtime_requests_max"] == 0, "remote request budget")
    _require(
        budget["field_metrics"]["status"] == "NOT_AVAILABLE_UNPUBLISHED",
        "field metrics must remain unclaimed before publication",
    )
    checks.append("PERFORMANCE_BUDGET")

    baseline = _load(BASELINE)
    _require(baseline["review_policy"] == "HUMAN_REVIEW_REQUIRED_ON_DIFF", "review policy")
    for relative, expected in baseline["files"].items():
        path = ROOT / relative
        _require(path.is_file(), f"baseline file missing: {relative}")
        _require(_sha256(path) == expected, f"visual baseline differs: {relative}")
    checks.append("VISUAL_BASELINE")
    return checks


def main() -> int:
    try:
        checks = run_checks()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"VISUAL_QUALITY_FAIL {error}", file=sys.stderr)
        return 1
    print(f"VISUAL_QUALITY_OK checks={len(checks)} baseline={_sha256(BASELINE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
