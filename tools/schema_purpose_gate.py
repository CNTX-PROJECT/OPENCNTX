"""Require a unique declared need for every schema added after the baseline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "src" / "opencntx" / "schemas"
REGISTRY = ROOT / "tests" / "fixtures" / "quality" / "schema-purpose-v1.json"


class SchemaPurposeError(RuntimeError):
    """Raised when the schema-purpose registry and shipped schemas differ."""


def _names_digest(names: list[str]) -> str:
    encoded = (json.dumps(sorted(names), separators=(",", ":")) + "\n").encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def check_schema_purposes(
    *, schema_root: Path = SCHEMAS, registry_path: Path = REGISTRY
) -> dict[str, Any]:
    """Verify the frozen baseline and every post-baseline purpose declaration."""
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    purposes = registry.get("new_schemas")
    if not isinstance(purposes, dict) or not purposes:
        raise SchemaPurposeError("Schema-purpose registry has no new schema declarations.")
    if any(
        not isinstance(name, str)
        or not isinstance(purpose, str)
        or len(purpose.split()) < 6
        for name, purpose in purposes.items()
    ):
        raise SchemaPurposeError("Each new schema needs one specific bounded purpose.")
    normalized = {" ".join(purpose.lower().split()) for purpose in purposes.values()}
    if len(normalized) != len(purposes):
        raise SchemaPurposeError("New schema purposes must be unique.")
    current = sorted(path.name for path in schema_root.iterdir() if path.is_file())
    declared = sorted(purposes)
    undeclared = sorted(set(current) - set(declared))
    if len(undeclared) != registry.get("baseline_count"):
        raise SchemaPurposeError("Baseline schema count changed.")
    if _names_digest(undeclared) != registry.get("baseline_names_sha256"):
        raise SchemaPurposeError("Baseline schema names changed.")
    missing = sorted(set(declared) - set(current))
    if missing:
        raise SchemaPurposeError(f"Declared schemas are missing: {missing}")
    result = {
        "schema_count": len(current),
        "baseline_count": len(undeclared),
        "new_schema_count": len(declared),
        "undeclared_new": [],
        "unique_purposes": len(normalized),
    }
    print(
        "QUALITY_SCHEMA_PURPOSE_OK "
        f"schemas={len(current)} baseline={len(undeclared)} new={len(declared)}"
    )
    return result
