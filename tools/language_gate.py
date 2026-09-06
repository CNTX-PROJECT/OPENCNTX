"""Enforce English source text while preserving intentional Unicode uses."""

from __future__ import annotations

import ast
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "opencntx"


class LanguageGateError(RuntimeError):
    """Raised when current product or developer text contains Unicode letters."""


def _references_legacy(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Name) and child.id == "legacy" for child in ast.walk(node))


def _legacy_branch(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    child = node
    while child in parents:
        parent = parents[child]
        if isinstance(parent, ast.IfExp) and parent.body is child and _references_legacy(parent.test):
            return True
        child = parent
    return False


def inspect_language(paths: Iterable[Path] | None = None) -> dict[str, Any]:
    """Inventory non-ASCII literals and reject unmarked product-language letters."""
    selected = tuple(sorted(SOURCE.glob("*.py"))) if paths is None else tuple(paths)
    records: list[dict[str, Any]] = []
    for path in selected:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            characters = [character for character in node.value if ord(character) > 127]
            if not characters:
                continue
            has_letters = any(unicodedata.category(character).startswith("L") for character in characters)
            purpose = "legacy_i18n" if has_letters and _legacy_branch(node, parents) else "unicode_symbol"
            records.append(
                {
                    "path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix(),
                    "line": node.lineno,
                    "character_count": len(characters),
                    "purpose": purpose,
                    "violation": has_letters and purpose != "legacy_i18n",
                }
            )
    violations = [record for record in records if record["violation"]]
    return {
        "files_scanned": len(selected),
        "literal_count": len(records),
        "character_count": sum(int(record["character_count"]) for record in records),
        "purposes": sorted({str(record["purpose"]) for record in records}),
        "violations": violations,
        "records": records,
    }


def check_language(paths: Iterable[Path] | None = None) -> dict[str, Any]:
    """Fail closed on accidental non-English Unicode letters in shipped source."""
    result = inspect_language(paths)
    if result["violations"]:
        locations = [f"{item['path']}:{item['line']}" for item in result["violations"]]
        raise LanguageGateError(f"Unmarked Unicode product text: {locations}")
    print(
        "QUALITY_LANGUAGE_OK "
        f"files={result['files_scanned']} literals={result['literal_count']} "
        f"characters={result['character_count']}"
    )
    return result
