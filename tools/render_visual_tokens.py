"""Generate and verify the dependency-free OPENCNTX visual token CSS."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "design-system" / "tokens-v1.json"
TARGET = ROOT / "assets" / "design-system" / "tokens-v1.css"
TOKEN_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
REQUIRED_GROUPS = {
    "component_states",
    "dark",
    "format",
    "format_version",
    "foundation",
    "high_contrast",
    "light",
}


class TokenError(ValueError):
    """A token source or generated artifact is invalid."""


def load_tokens() -> dict[str, object]:
    """Load and validate the closed JSON token source."""
    value = json.loads(SOURCE.read_text(encoding="ascii"))
    if not isinstance(value, dict) or set(value) != REQUIRED_GROUPS:
        raise TokenError("Token source fields differ.")
    if value["format"] != "opencntx-visual-tokens" or value["format_version"] != 1:
        raise TokenError("Token source identity differs.")
    for group in ("foundation", "light", "dark", "high_contrast"):
        entries = value[group]
        if not isinstance(entries, dict) or not entries:
            raise TokenError(f"Token group is invalid: {group}.")
        for name, item in entries.items():
            if TOKEN_NAME.fullmatch(name) is None or not isinstance(item, str) or not item:
                raise TokenError(f"Token is invalid: {group}.{name}.")
    states = value["component_states"]
    if not isinstance(states, list) or states != sorted(set(states)):
        raise TokenError("Component states must be sorted and unique.")
    return value


def _declarations(entries: object) -> str:
    if not isinstance(entries, dict):
        raise TokenError("Token declarations are invalid.")
    return "\n".join(f"  --oc-{name}: {entries[name]};" for name in sorted(entries))


def render_css(tokens: dict[str, object]) -> bytes:
    """Render stable UTF-8 CSS from the canonical token source."""
    root = _declarations(tokens["foundation"])
    light = _declarations(tokens["light"])
    dark = _declarations(tokens["dark"])
    contrast = _declarations(tokens["high_contrast"])
    text = f"""/* Generated from assets/design-system/tokens-v1.json. Do not edit. */
:root {{
{root}
{light}
  color-scheme: light dark;
}}

@media (prefers-color-scheme: dark) {{
  :root {{
{dark}
  }}
}}

@media (prefers-contrast: more) {{
  :root {{
{contrast}
  }}
}}
"""
    return text.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render_css(load_tokens())
    if args.write:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_bytes(expected)
        print(f"VISUAL_TOKENS_WRITTEN path={TARGET.relative_to(ROOT).as_posix()}")
        return 0
    if not TARGET.is_file() or TARGET.read_bytes() != expected:
        print("VISUAL_TOKENS_MISMATCH")
        return 1
    print("VISUAL_TOKENS_OK source=tokens-v1.json target=tokens-v1.css")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
