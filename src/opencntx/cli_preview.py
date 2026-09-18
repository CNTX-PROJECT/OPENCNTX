"""Opt-in owner-preview search; reuse the existing bounded retrieval engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .search_index import search_delivery, search_full_text


def register_preview_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Keep the preview separate from every existing command and output contract."""
    parser = subparsers.add_parser(
        "preview-search",
        help="experimental 1.8.5 search with optional compact JSON output",
    )
    parser.add_argument("query")
    parser.add_argument("--root", default=".")
    parser.add_argument("--index", default=".opencntx/search-v2.sqlite")
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--max-bytes", type=int, default=100_000)
    parser.add_argument("--max-tokens", type=int, default=25_000)
    parser.add_argument("--max-snippet-chars", type=int, default=600)
    parser.add_argument("--delivery-report", action="store_true")
    parser.add_argument(
        "--max-output-bytes", type=int, default=100_000,
        help="complete output-byte limit for --delivery-report",
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="remove JSON formatting whitespace without dropping result fields",
    )


def serialize_preview_result(value: object, *, compact: bool = False) -> str:
    """Return the same JSON value; do not change digests or claim provider tokens."""
    if compact:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def dispatch_preview(args: argparse.Namespace) -> int | None:
    if args.command != "preview-search":
        return None
    root = Path(args.root)
    index = Path(args.index)
    if not index.is_absolute():
        index = root / index
    options = {
        "root": root,
        "max_results": args.max_results,
        "max_bytes": args.max_bytes,
        "max_tokens": args.max_tokens,
        "max_snippet_chars": args.max_snippet_chars,
    }
    if args.delivery_report:
        result = search_delivery(
            index, args.query, max_output_bytes=args.max_output_bytes, **options
        )
    else:
        result = search_full_text(index, args.query, **options)
    # Existing safety and pretty-output budgets are enforced before serialization.
    # Compact mode is opt-in and does not use its byte savings to add more results.
    print(serialize_preview_result(result, compact=args.compact), end="")
    return 0
