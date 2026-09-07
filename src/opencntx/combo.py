"""Bounded local combo-roadmap projections, queries, and comparisons."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .continuity import _fail, _pretty, _value_digest, _writer_lock
from .security import scan_text

FORMAT = "opencntx-combo-roadmap"
FORMAT_VERSION = 1
DEFAULT_QUERY_LIMIT = 10
MAX_QUERY_LIMIT = 20
MAX_MARKDOWN_WORDS = 2_500
MAX_MARKDOWN_BYTES = 20 * 1024
MAX_CURRENT_ITEMS = 12
MAX_DECISIONS = 32
MAX_CONFLICTS = 24
MAX_CAPABILITIES = 24
MAX_RECENT_COMPLETED = 3
MAX_EPOCHS = 12
MAX_SHARD_ROADMAPS = 100
MAX_SHARD_BYTES = 1024 * 1024
ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{0,79}\Z")


def _text(value: object, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str):
        raise _fail("combo_record_invalid", f"{field} must be text.")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise _fail("combo_record_invalid", f"{field} is empty or too long.")
    return normalized


def _identifier(value: object, field: str) -> str:
    selected = _text(value, field, 80)
    if ID_PATTERN.fullmatch(selected) is None:
        raise _fail("combo_record_invalid", f"{field} is not a stable identifier.")
    return selected


def _tags(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)) or len(values) > 20:
        raise _fail("combo_record_invalid", "tags exceed the bounded list.")
    tags = sorted({_text(value, "tag", 40).lower() for value in values})
    if len(tags) != len(values):
        raise _fail("combo_record_invalid", "tags contain duplicates.")
    return tags


def new_combo(project_id: str) -> dict[str, Any]:
    """Create an empty provider-neutral logical combo object."""
    basis = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": _identifier(project_id, "project_id"),
        "revision": 0,
        "active": [],
        "recent_completed": [],
        "epochs": [],
        "decisions": [],
        "conflicts": [],
        "capabilities": [],
        "relations": [],
        "history_index": [],
        "source_roadmap_ids": [],
    }
    return basis | {"combo_digest": _value_digest(basis)}


def validate_combo(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the logical object and its stable source binding."""
    combo = dict(value)
    digest = combo.pop("combo_digest", None)
    required = {
        "format",
        "format_version",
        "project_id",
        "revision",
        "active",
        "recent_completed",
        "epochs",
        "decisions",
        "conflicts",
        "capabilities",
        "relations",
        "history_index",
        "source_roadmap_ids",
    }
    if (
        set(combo) != required
        or combo["format"] != FORMAT
        or combo["format_version"] != FORMAT_VERSION
        or type(combo["revision"]) is not int
        or combo["revision"] < 0
        or digest != _value_digest(combo)
    ):
        raise _fail("combo_record_invalid", "Combo object or digest is invalid.")
    _identifier(combo["project_id"], "project_id")
    limits = {
        "active": MAX_CURRENT_ITEMS,
        "recent_completed": MAX_RECENT_COMPLETED,
        "epochs": MAX_EPOCHS,
        "decisions": MAX_DECISIONS,
        "conflicts": MAX_CONFLICTS,
        "capabilities": MAX_CAPABILITIES,
    }
    for field, maximum in limits.items():
        if not isinstance(combo[field], list) or len(combo[field]) > maximum:
            raise _fail("combo_budget_exceeded", f"{field} exceeds its fixed budget.")
    if any(
        not isinstance(combo[field], list)
        for field in ("relations", "history_index", "source_roadmap_ids")
    ):
        raise _fail("combo_record_invalid", "Combo collections are invalid.")
    return combo | {"combo_digest": str(digest)}


def _entry(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "id",
        "roadmap_id",
        "kind",
        "status",
        "statement",
        "subject_key",
        "scope_key",
        "tags",
        "sequence",
        "year",
        "source_digest",
        "supersedes",
    }
    if set(value) != expected:
        raise _fail("combo_record_invalid", "Combo entry fields differ from v1.")
    entry = dict(value)
    entry["id"] = _identifier(entry["id"], "id")
    entry["roadmap_id"] = _identifier(entry["roadmap_id"], "roadmap_id")
    entry["kind"] = _text(entry["kind"], "kind", 32)
    entry["status"] = _text(entry["status"], "status", 32)
    if entry["kind"] not in {"ROADMAP", "DECISION", "CONFLICT", "CAPABILITY"}:
        raise _fail("combo_record_invalid", "Combo entry kind is invalid.")
    if entry["status"] not in {"ACTIVE", "COMPLETED", "SUPERSEDED", "BLOCKED"}:
        raise _fail("combo_record_invalid", "Combo entry status is invalid.")
    for field in ("statement", "subject_key", "scope_key"):
        entry[field] = _text(entry[field], field)
    entry["tags"] = _tags(entry["tags"])
    if type(entry["sequence"]) is not int or entry["sequence"] < 0:
        raise _fail("combo_record_invalid", "sequence is invalid.")
    if type(entry["year"]) is not int or not 2000 <= entry["year"] <= 9999:
        raise _fail("combo_record_invalid", "year is invalid.")
    source_digest = _text(entry["source_digest"], "source_digest", 64)
    if len(source_digest) != 64 or any(
        character not in "0123456789abcdef" for character in source_digest
    ):
        raise _fail("combo_record_invalid", "source_digest is invalid.")
    entry["supersedes"] = [_identifier(item, "supersedes") for item in entry["supersedes"]]
    if len(entry["supersedes"]) != len(set(entry["supersedes"])):
        raise _fail("combo_record_invalid", "supersedes contains duplicates.")
    privacy_text = "\n".join([entry["statement"], *entry["tags"]])
    if scan_text(
        path=f"combo/{entry['id']}",
        text=privacy_text,
        source_sha256=source_digest,
    ):
        raise _fail("combo_secret", "Combo entry contains a credential signal.")
    return entry


def _dedup_key(entry: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(entry["subject_key"]), str(entry["scope_key"]), str(entry["statement"]))


def _epoch(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    years = [int(item["year"]) for item in entries]
    ids = sorted(str(item["id"]) for item in entries)
    basis = {
        "id": f"EPOCH_{min(years)}_{max(years)}_{len(ids)}",
        "year_start": min(years),
        "year_end": max(years),
        "meta_epoch": f"META_{min(years) // 5 * 5}_{min(years) // 5 * 5 + 4}",
        "roadmap_count": len(ids),
        "source_ids": ids,
        "source_digest": _value_digest(ids),
    }
    return basis | {"epoch_digest": _value_digest(basis)}


def _bounded_append(
    values: list[dict[str, Any]], item: dict[str, Any], maximum: int
) -> list[dict[str, Any]]:
    combined = [entry for entry in values if _dedup_key(entry) != _dedup_key(item)]
    combined.append(item)
    return sorted(combined, key=lambda entry: (-int(entry["sequence"]), str(entry["id"])))[:maximum]


def set_active_roadmaps(
    combo: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Replace the bounded current view without adding incomplete work to history."""
    current = validate_combo(combo)
    normalized = [_entry(item) for item in entries]
    if any(item["kind"] != "ROADMAP" or item["status"] != "ACTIVE" for item in normalized):
        raise _fail("combo_record_invalid", "Current view accepts only active roadmaps.")
    if len(normalized) > MAX_CURRENT_ITEMS:
        raise _fail("combo_budget_exceeded", "Current roadmap view exceeds twelve items.")
    result = {key: value for key, value in current.items() if key != "combo_digest"}
    result["revision"] += 1
    result["active"] = sorted(normalized, key=_rank)
    updated = result | {"combo_digest": _value_digest(result)}
    render_combo_markdown(updated)
    return updated


def _mark_superseded(result: dict[str, Any], identifiers: set[str]) -> None:
    for field in ("active", "recent_completed", "decisions", "conflicts", "capabilities"):
        result[field] = [
            item | {"status": "SUPERSEDED"} if item["id"] in identifiers else item
            for item in result[field]
        ]


def update_combo(combo: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply completed roadmap knowledge with exact dedup and explicit supersession."""
    current = validate_combo(combo)
    if isinstance(entries, (str, bytes)) or not entries:
        raise _fail("combo_record_invalid", "At least one combo entry is required.")
    normalized = [_entry(item) for item in entries]
    roadmap_ids = {item["roadmap_id"] for item in normalized}
    completed_ids = {
        item["roadmap_id"]
        for item in normalized
        if item["kind"] == "ROADMAP" and item["status"] == "COMPLETED"
    }
    if completed_ids != roadmap_ids:
        raise _fail(
            "combo_roadmap_incomplete", "Only a fully completed roadmap may update history."
        )
    result = {key: value for key, value in current.items() if key != "combo_digest"}
    result["revision"] += 1
    existing_ids = {
        item["id"]
        for field in ("active", "recent_completed", "decisions", "conflicts", "capabilities")
        for item in result[field]
    }
    relations = list(result["relations"])
    for item in normalized:
        missing = set(item["supersedes"]) - existing_ids
        if missing:
            raise _fail("combo_supersession_unknown", "Supersession references unknown IDs.")
        for superseded in item["supersedes"]:
            relations.append({"from": item["id"], "type": "SUPERSEDES", "to": superseded})
        _mark_superseded(result, set(item["supersedes"]))
        field = {
            "ROADMAP": "recent_completed",
            "DECISION": "decisions",
            "CONFLICT": "conflicts",
            "CAPABILITY": "capabilities",
        }[item["kind"]]
        maximum = {
            "recent_completed": MAX_RECENT_COMPLETED,
            "decisions": MAX_DECISIONS,
            "conflicts": MAX_CONFLICTS,
            "capabilities": MAX_CAPABILITIES,
        }[field]
        before = list(result[field])
        result[field] = _bounded_append(before, item, maximum)
        if field == "recent_completed" and len(before) >= maximum:
            displaced = sorted(
                [*before, item], key=lambda entry: (-int(entry["sequence"]), str(entry["id"]))
            )[maximum:]
            if displaced:
                for archived in displaced:
                    compact = {
                        "id": archived["id"],
                        "roadmap_id": archived["roadmap_id"],
                        "kind": archived["kind"],
                        "status": archived["status"],
                        "statement": archived["statement"],
                        "tags": archived["tags"],
                        "sequence": archived["sequence"],
                        "year": archived["year"],
                    }
                    result["history_index"] = [
                        prior for prior in result["history_index"] if prior["id"] != compact["id"]
                    ]
                    result["history_index"].append(compact)
                result["epochs"].append(_epoch(displaced))
    while len(result["epochs"]) > MAX_EPOCHS:
        first, second, *tail = result["epochs"]
        merged_ids = [*first["source_ids"], *second["source_ids"]]
        merged = {
            "id": f"EPOCH_{first['year_start']}_{second['year_end']}_{len(merged_ids)}",
            "year_start": first["year_start"],
            "year_end": second["year_end"],
            "meta_epoch": f"META_{first['year_start'] // 5 * 5}_{second['year_end'] // 5 * 5 + 4}",
            "roadmap_count": len(merged_ids),
            "source_ids": sorted(merged_ids),
            "source_digest": _value_digest(sorted(merged_ids)),
        }
        result["epochs"] = [merged | {"epoch_digest": _value_digest(merged)}, *tail]
    result["relations"] = sorted(
        {json.dumps(item, sort_keys=True): item for item in relations}.values(),
        key=lambda item: (item["from"], item["type"], item["to"]),
    )
    result["source_roadmap_ids"] = sorted(set(result["source_roadmap_ids"]) | roadmap_ids)
    updated = result | {"combo_digest": _value_digest(result)}
    validate_combo(updated)
    render_combo_markdown(updated)
    return updated


def _rank(entry: Mapping[str, Any]) -> tuple[int, int, str]:
    score = {"ACTIVE": 400, "BLOCKED": 300, "COMPLETED": 200, "SUPERSEDED": 100}[
        str(entry["status"])
    ]
    score += {"CONFLICT": 40, "DECISION": 30, "CAPABILITY": 20, "ROADMAP": 10}[str(entry["kind"])]
    return (-score, -int(entry["sequence"]), str(entry["id"]))


def query_combo(
    combo: Mapping[str, Any],
    *,
    identifiers: Sequence[str] = (),
    tags: Sequence[str] = (),
    text: str = "",
    limit: int = DEFAULT_QUERY_LIMIT,
) -> dict[str, Any]:
    """Run a bounded deterministic query across current human-useful knowledge."""
    current = validate_combo(combo)
    if type(limit) is not int or not 1 <= limit <= MAX_QUERY_LIMIT:
        raise _fail("combo_query_limit", "Query limit must be between 1 and 20.")
    selected_ids = {_identifier(item, "identifier") for item in identifiers}
    selected_tags = set(_tags(tags))
    needle = " ".join(text.lower().split())
    entries = [
        item
        for field in ("active", "recent_completed", "decisions", "conflicts", "capabilities")
        for item in current[field]
    ]
    entries.extend(current["history_index"])
    matches = []
    for item in entries:
        haystack = " ".join(
            [item["id"], item["roadmap_id"], item["statement"], *item["tags"]]
        ).lower()
        if (
            selected_ids
            and item["id"] not in selected_ids
            and item["roadmap_id"] not in selected_ids
        ):
            continue
        if selected_tags and not selected_tags.issubset(set(item["tags"])):
            continue
        if needle and needle not in haystack:
            continue
        matches.append(item)
    ranked = sorted(matches, key=_rank)[:limit]
    result = {
        "format": "opencntx-combo-query",
        "format_version": 1,
        "combo_digest": current["combo_digest"],
        "limit": limit,
        "match_count": len(matches),
        "results": ranked,
        "ranking": "status-kind-sequence-id",
    }
    return result | {"query_digest": _value_digest(result)}


def compare_roadmap(combo: Mapping[str, Any], proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Compare before start and never mutate or grant start authority."""
    current = validate_combo(combo)
    required = {"roadmap_id", "references", "tags", "touches", "supersedes"}
    if set(proposal) != required:
        raise _fail("combo_compare_invalid", "Roadmap comparison fields differ from v1.")
    roadmap_id = _identifier(proposal["roadmap_id"], "roadmap_id")
    references = {_identifier(item, "reference") for item in proposal["references"]}
    supersedes = {_identifier(item, "supersedes") for item in proposal["supersedes"]}
    known = set(current["source_roadmap_ids"]) | {
        item["id"]
        for field in ("active", "recent_completed", "decisions", "conflicts", "capabilities")
        for item in current[field]
    }
    missing = sorted(references - known)
    unresolved = sorted(
        item["id"]
        for item in current["conflicts"]
        if item["status"] in {"ACTIVE", "BLOCKED"}
        and set(item["tags"]) & set(_tags(proposal["tags"]))
        and item["id"] not in supersedes
    )
    if unresolved:
        status = "BLOCKED"
    elif missing:
        status = "RECONCILE_REQUIRED"
    else:
        status = "CLEAR"
    result = {
        "format": "opencntx-combo-comparison",
        "format_version": 1,
        "roadmap_id": roadmap_id,
        "combo_digest": current["combo_digest"],
        "status": status,
        "missing_references": missing,
        "unresolved_conflicts": unresolved,
        "authority_granted": False,
        "flow_started": False,
    }
    return result | {"comparison_digest": _value_digest(result)}


def render_combo_markdown(combo: Mapping[str, Any]) -> str:
    """Render a compact human projection and enforce both accepted budgets."""
    current = validate_combo(combo)
    lines = [
        "# Combo roadmap",
        "",
        f"Revision: `{current['revision']}`  ",
        f"Source digest: `{current['combo_digest']}`",
        "",
    ]
    for title, field in (
        ("Current", "active"),
        ("Recent completed", "recent_completed"),
        ("Decisions", "decisions"),
        ("Conflicts", "conflicts"),
        ("Capabilities", "capabilities"),
    ):
        lines.extend([f"## {title}", ""])
        if not current[field]:
            lines.append("- None.")
        else:
            for item in sorted(current[field], key=_rank):
                lines.append(
                    f"- `{item['id']}` [{item['status']}] {item['statement']} "
                    f"(source `{item['roadmap_id']}`)"
                )
        lines.append("")
    lines.extend(["## Epochs", ""])
    for epoch in current["epochs"]:
        lines.append(
            f"- `{epoch['id']}`: {epoch['roadmap_count']} roadmaps, "
            f"{epoch['year_start']}-{epoch['year_end']}."
        )
    if not current["epochs"]:
        lines.append("- None.")
    rendered = "\n".join(lines).rstrip() + "\n"
    word_count = len(re.findall(r"\b[\w-]+\b", rendered, flags=re.UNICODE))
    if word_count > MAX_MARKDOWN_WORDS or len(rendered.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise _fail("combo_budget_exceeded", "Markdown projection exceeds its fixed budget.")
    return rendered


def _combo_root(project_root: Path) -> Path:
    return project_root.resolve() / ".opencntx" / "combo"


_UNSPECIFIED = object()


def write_combo(
    project_root: Path, combo: Mapping[str, Any], *, expected_digest: object = _UNSPECIFIED
) -> dict[str, Any]:
    """Serialize publication; optional CAS protects read-modify-write callers."""
    root = _combo_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    with _writer_lock(root / ".writer.lock"):
        if expected_digest is not _UNSPECIFIED:
            current = (
                load_combo(project_root)["combo_digest"] if (root / "CURRENT").exists() else None
            )
            if current != expected_digest:
                raise _fail("combo_write_conflict", "Combo changed after preparation.")
        return _write_combo_unlocked(project_root, combo)


def _write_combo_unlocked(project_root: Path, combo: Mapping[str, Any]) -> dict[str, Any]:
    """Publish JSON, Markdown, and receipt through one atomic generation pointer."""
    current = validate_combo(combo)
    markdown = render_combo_markdown(current).encode("utf-8")
    json_bytes = _pretty(current)
    root = _combo_root(project_root)
    generations = root / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    generation = current["combo_digest"]
    final = generations / generation
    if not final.exists():
        staging = Path(tempfile.mkdtemp(prefix="combo-", dir=generations))
        try:
            (staging / "combo.json").write_bytes(json_bytes)
            (staging / "COMBO.md").write_bytes(markdown)
            receipt = {
                "format": "opencntx-combo-optimization-receipt",
                "format_version": 1,
                "combo_digest": generation,
                "json_digest": _value_digest(json.loads(json_bytes)),
                "markdown_digest": _value_digest(markdown.decode("utf-8")),
                "markdown_words": len(re.findall(r"\b[\w-]+\b", markdown.decode("utf-8"))),
                "markdown_bytes": len(markdown),
                "query_default": DEFAULT_QUERY_LIMIT,
                "query_maximum": MAX_QUERY_LIMIT,
                "epoch_count": len(current["epochs"]),
                "history_index_count": len(current["history_index"]),
                "history_shard_count": (len(current["history_index"]) + MAX_SHARD_ROADMAPS - 1)
                // MAX_SHARD_ROADMAPS,
            }
            receipt["receipt_digest"] = _value_digest(receipt)
            (staging / "receipt.json").write_bytes(_pretty(receipt))
            os.replace(staging, final)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    pointer_tmp = root / "CURRENT.tmp"
    pointer_tmp.write_text(generation + "\n", encoding="ascii", newline="\n")
    os.replace(pointer_tmp, root / "CURRENT")
    return json.loads((final / "receipt.json").read_text(encoding="utf-8"))


def load_combo(project_root: Path) -> dict[str, Any]:
    """Read the generation selected by the atomic pointer."""
    root = _combo_root(project_root)
    try:
        generation = (root / "CURRENT").read_text(encoding="ascii").strip()
        value = json.loads(
            (root / "generations" / generation / "combo.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail("combo_store_invalid", "Combo store cannot be read.") from exc
    combo = validate_combo(value)
    if combo["combo_digest"] != generation:
        raise _fail("combo_store_invalid", "Combo pointer and generation differ.")
    return combo


def build_history_shards(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Split immutable history at 100 roadmaps or 1 MiB, whichever comes first."""
    shards: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_bytes = 2
    for supplied in entries:
        item = _entry(supplied)
        encoded = len(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")) + 1
        if current and (
            len(current) >= MAX_SHARD_ROADMAPS or current_bytes + encoded > MAX_SHARD_BYTES
        ):
            shards.append(_shard(len(shards) + 1, current))
            current, current_bytes = [], 2
        current.append(item)
        current_bytes += encoded
    if current:
        shards.append(_shard(len(shards) + 1, current))
    return shards


def _shard(number: int, entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    basis = {
        "id": f"SHARD_{number:04d}",
        "entry_count": len(entries),
        "first_sequence": min(int(item["sequence"]) for item in entries),
        "last_sequence": max(int(item["sequence"]) for item in entries),
        "entry_ids": [str(item["id"]) for item in entries],
        "entries_digest": _value_digest(list(entries)),
    }
    return basis | {"shard_digest": _value_digest(basis)}
