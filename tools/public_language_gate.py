"""Fail closed when tracked public text contains known Dutch product wording."""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import zlib
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_TERM_DATA = "eNpVVW3apDgI/M9d5lDRYEwbgw8mum9fag+xF9uC2NMzf5R8CFRRYGRauRFzpR3vK1S6RJRqxirZ9ju/Kt2skW7R2HCdl0a74HzD7a3XiluhnBSxFNmoSqI9BKUpv6jnRtUWcpDUyErR/L+H3fp52tf4sjHJTm8uS2SK/BjIo9/jifMe/YF09cT9djP7ZcUzcYk54bx+rYk3rvZNbZP+ZfMGDPkEYria11y+VkFCH5vC3DKf40WXhmSHGkKiic9i4J439lt+RS75tRG+1fxaJieBLz5bTpEyMsNJ2JAfU+FkD050tlAjrkazgtMOhu/8QnoT/F3wbW9sIhB8FLFwK2sBTZWOjlOgw4eT9rwh90nFyzKHKtXPonABClBvtBi4zdOTAVVBJKKwRUUWqItxcJQ8ryA6K877nCcuTDMYzLX/929jwE8qloLKi+emIkgZsaceEwSyiizxbH0zZMeBi2eTwwR2G97fERGKUQysLZ2oAVEtfqjtxuXB6uopqhQQ3bg4IkrCceOu4JaUE5xoQKmsFC7kFEA6NMdLrtlqGGXuO9emPMOxJ/uYcpwlpCfziaFzdbkgjzs4DYYc8dmEK1JN5Nsnqm3+yStsL+b8MxeQWWQLAen6DQOST+fEFIBTryMCbRYUQsERdKjelWUgOR0zXNeAVL8cXVKS9eeG0u/WFEgKsdTFcomB0ANb/OeGhSrBWQO5UKL+rgV9tGPvB4b1zccyQYenOvDklrUy8iiMvjMjeadxtm5pAve3AwTv1u0AUoZ+HdPzbnZzkx2ij32C0uiQ45HQ6L+LHW8oUXk/cOH8qfMh0OgPyvTLVlNQJrVZccAranQmREcDnWSKA/n9NtBAKD4j4HCX3ToPDBgN6LtqLTjZgKowwMkb3ctfk6bR7wAKDY6Z8rXBERgSQ4jxeWFcgZNiUrBxhX6xZILJchIXNJ+9uFSc/7cH/YoqYhXmmY/2LDZBI5kmWCfo23WTi/FuG550leZaNw19hgKUscKlaAYJFNRkuNBLMF03QRWTzeAiRrmJCRo0qfg0daWtkngIHIyNcYuetD4zGhMk7VNtLiHvQ0tecjA1agosEdrijEtWCvs3vCUCNujH8y32C8H/x2aq0zMcTHygcYxj4AOWwj4O8wsdKuqMo6ny3svo14ydfxbp8Lssec5Ia5TnEefTY4zpj/9aH8NxhZR3zA0ggQgBPJlI/gc/Kqhn"
_EXTRA_TERM_DATA = "eJxVU1uy7CAI/HeXJCGGiUpKMVN1N3UWcTZ2G5N5nB9tLYGmaSd+yqPFyqWFk+vClX2nAvQGy+eOyxtKicF4bxZ2PYQDrZETCx5vXHcuEyHXJIWkBr+38GSukU/k6GKnXim2LotED9+o7JzksX/jDZFBj8ht3lTLH8zhAqEI92czDlVz5pSp7uY80ZvT/0CUNmVwwLI4dIBLxQvkqvI4v06D6pMIArz2kIhsVEJc8sQT22gET6Q0o5TIoEbk+8RDv8i/P99nryCvrY2KhTNyUDfNyNAG2a+Ta4XOUR/Ms7TU0WPr88zt1ISbWEfhVZKNWAd1ID1MMqU751H1wbMNvqvWfNMdg2lh1mJVE4dC88Yz5hhihdYSA9eT7k71SNqaU3oj3Po0ymsomWiHSo3NSxGVg66ID7zMFK+Zv5G/mTUf4DVJEmOxcPQpyTzow2wHfFbuWQearTN2DHPX3My9NDGkhlfuHY8zIQpGURNzwRdM81StcDBouPxhwlr0CHpZHilv5MUwNRg9k+ux6Fi0RrQCAYb7Qj8WsqsjWYWv7wM0D30NTJwzt55svFu121h4+NdacHO08M9D0e3lxD5+ZORrqkv4/INCO8Tygoo4n89KzhRvidIS4BQX2Ocppf/+uI7/AV8Sfvs="


class PublicLanguageGateError(RuntimeError):
    """Raised when a tracked public file contains blocked product wording."""


def _terms() -> tuple[str, ...]:
    ignored = {
        base64.b64decode("bWV0").decode("ascii"),
        # These entries are English technical vocabulary or product names in
        # the supplementary compatibility list, not blocked Dutch wording.
        "backup",
        "back-up",
        "buggy",
        "computer",
        "footer",
        "map",
        "obsidian",
        "pc",
        "recent",
        "release",
        "research",
        "roadmap",
        "test",
        "update",
        "zip",
    }
    terms: list[str] = []
    for encoded in (_TERM_DATA, _EXTRA_TERM_DATA):
        content = zlib.decompress(base64.b64decode(encoded)).decode("utf-8")
        terms.extend(term for term in content.splitlines() if term and term not in ignored)
    return tuple(dict.fromkeys(terms))


@lru_cache(maxsize=1)
def _term_pattern() -> tuple[re.Pattern[str], dict[str, str]]:
    terms = _terms()
    alternatives = "|".join(
        re.escape(term) for term in sorted(terms, key=lambda value: (-len(value), value))
    )
    pattern = re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])", re.IGNORECASE)
    return pattern, {term.casefold(): term for term in terms}


def findings(text: str) -> list[dict[str, Any]]:
    """Return deterministic line/token findings for one public text value."""
    pattern, canonical_terms = _term_pattern()
    result: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        result.append(
            {
                "line": text.count("\n", 0, match.start()) + 1,
                "term": canonical_terms[match.group(0).casefold()],
            }
        )
    return sorted(result, key=lambda item: (int(item["line"]), str(item["term"])))


def _tracked_paths() -> tuple[Path, ...]:
    executable = shutil.which("git")
    if executable is None:
        raise OSError("Git is required to enumerate public files")
    # The executable is resolved from the trusted PATH and the arguments are fixed.
    completed = subprocess.run(  # noqa: S603, RUF100
        [executable, "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    paths: list[Path] = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8"))
        if relative.suffix.lower() in {".gz", ".ico", ".jpg", ".jpeg", ".png", ".pyc"}:
            continue
        paths.append(ROOT / relative)
    return tuple(paths)


def check_public_english(paths: Iterable[Path] | None = None) -> dict[str, Any]:
    """Scan tracked public text and fail closed on known Dutch wording."""
    selected = tuple(paths) if paths is not None else _tracked_paths()
    all_findings: list[dict[str, Any]] = []
    for path in selected:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for item in findings(text):
            all_findings.append(
                {
                    "path": path.relative_to(ROOT).as_posix()
                    if path.is_relative_to(ROOT)
                    else path.as_posix(),
                    **item,
                }
            )
    if all_findings:
        preview = ", ".join(
            f"{item['path']}:{item['line']}:{item['term']}" for item in all_findings[:20]
        )
        raise PublicLanguageGateError(f"Blocked non-English product text: {preview}")
    print(f"QUALITY_PUBLIC_ENGLISH_OK files={len(selected)} findings=0")
    return {"files_scanned": len(selected), "findings": []}


if __name__ == "__main__":
    check_public_english()
