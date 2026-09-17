"""Digest-bound, reversible visual text integration into one existing document."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .knowledge import KnowledgeError, _atomic_json, _canonical_json, _digest, _root
from .knowledge_io import bounded_read, safe_path
from .presentation import visual_projection
from .visual_design import validate_visual_intent, validate_visual_review

START = "<!-- OPENCNTX:VISUAL_ARTIST:START -->"
END = "<!-- OPENCNTX:VISUAL_ARTIST:END -->"


def preview_visual_integration(
    root: Path, relative: str, intent: Mapping[str, object], *, maximum_bytes: int = 1_000_000
) -> dict[str, Any]:
    """Preserve the existing bytes and append a visible, owned text projection."""
    selected = _root(root)
    if not relative.endswith(".md") or relative.startswith(".opencntx/"):
        raise KnowledgeError("Visual integration requires an existing Markdown source.")
    source = safe_path(selected, relative)
    if source.stat().st_nlink != 1:
        raise KnowledgeError("Visual integration refuses multiply linked source files.")
    before = bounded_read(selected, relative, maximum_bytes)
    try:
        text = before.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeError("Visual document must be UTF-8 without source conversion.") from exc
    if START in text or END in text:
        raise KnowledgeError("An existing visual section requires its integration receipt.")
    projection = visual_projection(intent)
    if START in projection["text"] or END in projection["text"]:
        raise KnowledgeError("Visual content cannot contain integration boundaries.")
    append = f"\n\n{START}\n\n{projection['text']}\n\n{END}\n".encode()
    basis = {
        "format": "ocx-visual-integration-plan-v1",
        "format_version": 1,
        "path": relative,
        "root_digest": _digest(str(selected).encode("utf-8")),
        "source_digest": _digest(before),
        "result_digest": _digest(before + append),
        "intent_digest": projection["intent_digest"],
        "append_text": append.decode("utf-8"),
        "maximum_bytes": maximum_bytes,
        "mode": "TEXT_FALLBACK",
    }
    if len(before) + len(append) > maximum_bytes:
        raise KnowledgeError("Visual integration exceeds its byte budget.")
    return basis | {"plan_digest": _digest(_canonical_json(basis))}


def _validate_plan(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "format",
        "format_version",
        "path",
        "root_digest",
        "source_digest",
        "result_digest",
        "intent_digest",
        "append_text",
        "maximum_bytes",
        "mode",
        "plan_digest",
    }
    if (
        set(plan) != fields
        or plan["format"] != "ocx-visual-integration-plan-v1"
        or plan["format_version"] != 1
    ):
        raise KnowledgeError("Visual integration plan fields or version differ.")
    basis = {key: value for key, value in plan.items() if key != "plan_digest"}
    if plan["plan_digest"] != _digest(_canonical_json(basis)) or plan["root_digest"] != _digest(
        str(root).encode("utf-8")
    ):
        raise KnowledgeError("Visual integration plan digest or root differs.")
    if type(plan["maximum_bytes"]) is not int or not 0 < plan["maximum_bytes"] <= 25_000_000:
        raise KnowledgeError("Visual integration budget is invalid.")
    return dict(plan)


def apply_visual_integration(
    root: Path, plan: Mapping[str, Any], intent: Mapping[str, object], review: Mapping[str, object]
) -> dict[str, Any]:
    """Apply only the exact reviewed intent; a second identical call writes nothing."""
    from .integrity import IntegrityError, writer_transaction

    selected = _root(root)
    valid = _validate_plan(selected, plan)
    brief = validate_visual_intent(intent)
    approved = validate_visual_review(review)
    from .visual_design import build_visual_review

    if approved != build_visual_review(
        brief,
        visual_findings=approved["visual_findings"],
        perfection_findings=approved["perfection_findings"],
        human_review_status=approved["human_review_status"],
    ):
        raise KnowledgeError("Visual review does not match its declared findings.")
    if (
        approved["decision"] != "COMPLETE"
        or approved["human_review_status"] != "APPROVED"
        or approved["intent_digest"] != brief["intent_digest"]
        or valid["intent_digest"] != brief["intent_digest"]
    ):
        raise KnowledgeError("Visual integration requires the exact approved visual review.")
    relative = valid["path"]
    receipt_relative = f".opencntx/visual-integrations/{valid['plan_digest']}.json"
    current = bounded_read(selected, relative, valid["maximum_bytes"])
    if _digest(current) == valid["result_digest"]:
        receipt = json.loads(bounded_read(selected, receipt_relative, 100_000))
        if receipt.get("plan_digest") != valid["plan_digest"] or receipt.get(
            "result_digest"
        ) != _digest(current):
            raise KnowledgeError("Visual integration receipt differs.")
        return receipt | {"writes": 0}
    if (
        preview_visual_integration(selected, relative, brief, maximum_bytes=valid["maximum_bytes"])
        != valid
    ):
        raise KnowledgeError("Visual source changed after the reviewed preview.")
    receipt = {
        "format": "ocx-visual-integration-receipt-v1",
        "format_version": 1,
        "plan_digest": valid["plan_digest"],
        "source_digest": valid["source_digest"],
        "result_digest": valid["result_digest"],
        "review_digest": approved["review_digest"],
        "path": relative,
        "mode": "TEXT_FALLBACK",
    }
    try:
        with writer_transaction(selected, "visual-integration") as transaction:
            if (
                _digest(bounded_read(selected, relative, valid["maximum_bytes"]))
                != valid["source_digest"]
            ):
                raise KnowledgeError("Visual source changed before publication.")
            directory = safe_path(selected, ".opencntx/visual-integrations", directory=True)
            directory.mkdir(exist_ok=True)
            source = safe_path(selected, relative)
            if source.stat().st_nlink != 1:
                raise KnowledgeError("Visual source acquired another hard link.")
            receipt_path = safe_path(selected, receipt_relative)
            backup_path = safe_path(selected, receipt_relative + ".before")
            for target in (source, receipt_path, backup_path):
                transaction.track_target(target)
            backup_path.write_bytes(current)
            # A tracked transaction restores original bytes if either write fails.
            source.write_bytes(current + valid["append_text"].encode("utf-8"))
            if (
                _digest(bounded_read(selected, relative, valid["maximum_bytes"]))
                != valid["result_digest"]
            ):
                raise KnowledgeError("Visual integration verification failed.")
            _atomic_json(receipt_path, receipt)
            for target in (source, receipt_path, backup_path):
                transaction.mark_target_published(target)
    except (IntegrityError, OSError) as exc:
        raise KnowledgeError("Visual integration failed; recover the tracked transaction.") from exc
    return receipt | {"writes": 3}


def rollback_visual_integration(root: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Restore exact prior bytes only while the current document is unchanged."""
    from .integrity import writer_transaction

    selected = _root(root)
    valid = _validate_plan(selected, plan)
    receipt_relative = f".opencntx/visual-integrations/{valid['plan_digest']}.json"
    current = bounded_read(selected, valid["path"], valid["maximum_bytes"])
    before = bounded_read(selected, receipt_relative + ".before", valid["maximum_bytes"])
    if _digest(before) != valid["source_digest"]:
        raise KnowledgeError("Visual rollback snapshot differs.")
    if _digest(current) == valid["source_digest"]:
        return {"status": "ALREADY_RESTORED", "writes": 0}
    if _digest(current) != valid["result_digest"]:
        raise KnowledgeError("Visual rollback refused: preserve newer user changes.")
    with writer_transaction(selected, "visual-integration-rollback") as transaction:
        if (
            _digest(bounded_read(selected, valid["path"], valid["maximum_bytes"]))
            != valid["result_digest"]
        ):
            raise KnowledgeError("Visual source changed before rollback.")
        source = safe_path(selected, valid["path"])
        if source.stat().st_nlink != 1:
            raise KnowledgeError("Visual rollback refuses a multiply linked source.")
        transaction.track_target(source)
        source.write_bytes(before)
        transaction.mark_target_published(source)
    return {"status": "RESTORED", "writes": 1}
