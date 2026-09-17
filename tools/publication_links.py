"""Check public relative links, HTML assets and publication identities offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class LinkParser(HTMLParser):
    """Collect navigable links and explicit HTML anchors."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.anchors.add(str(values["id"]))
        for key in ("href", "src"):
            if values.get(key):
                self.links.append(str(values[key]))
        if values.get("srcset"):
            self.links.extend(part.strip().split()[0] for part in str(values["srcset"]).split(","))


def without_code(text: str) -> str:
    """Ignore fenced examples; they are not rendered navigation."""
    return re.sub(r"(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1\s*$", "", text)


def references(text: str) -> list[str]:
    value = without_code(text)
    parser = LinkParser()
    parser.feed(value)
    links = parser.links
    links.extend(re.findall(r"!?\[[^\]\n]*\]\(<?([^\s)>]+)>?(?:\s+[^)]*)?\)", value))
    links.extend(re.findall(r"(?m)^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?", value))
    return links


def anchors(text: str) -> set[str]:
    parser = LinkParser()
    value = without_code(text)
    parser.feed(value)
    found = set(parser.anchors)
    occurrences: dict[str, int] = {}
    for heading in re.findall(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", value):
        heading = re.sub(r"<[^>]*>", "", heading)
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = occurrences.get(slug, 0)
        occurrences[slug] = count + 1
        found.add(slug if count == 0 else f"{slug}-{count}")
    return found


def check_links(root: Path) -> dict[str, object]:
    pages = sorted(
        {
            *root.glob("*.md"),
            *root.glob("docs/**/*.md"),
            *root.glob("site/**/*.md"),
            *root.glob("site/**/*.html"),
        }
    )
    errors = []
    count = 0
    external = set()
    for page in pages:
        for link in references(page.read_text(encoding="utf-8")):
            count += 1
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                external.add(link)
                continue
            target = (page.parent / unquote(parsed.path)).resolve() if parsed.path else page
            if not target.is_relative_to(root) or not target.exists():
                errors.append(f"{page.relative_to(root)}: missing target {link}")
            elif parsed.fragment and target.suffix in {".md", ".html"}:
                if unquote(parsed.fragment) not in anchors(target.read_text(encoding="utf-8")):
                    errors.append(f"{page.relative_to(root)}: missing anchor {link}")
    return {
        "pages": len(pages),
        "links": count,
        "external_urls": sorted(external),
        "errors": errors,
    }


def check_baselines(root: Path) -> None:
    manifest = json.loads((root / "tests/fixtures/release-baselines/manifest.json").read_text())
    for item in manifest["baselines"]:
        path = root / "tests/fixtures/release-baselines" / item["file"]
        if path.parent != root / "tests/fixtures/release-baselines":
            raise ValueError("unsafe fixture path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("baseline fixture checksum differs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    report = check_links(root)
    print(json.dumps(report, indent=2))
    check_baselines(root)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
