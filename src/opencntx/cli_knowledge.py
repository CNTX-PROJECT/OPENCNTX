"""CLI routes for the 1.8.0 local knowledge contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .knowledge import (
    KnowledgeError,
    build_adoption_manifest,
    build_index,
    footer_output,
    list_techniques,
    load_footer_envelope,
    load_index,
    make_footer_contract,
    make_footer_contract_from_host_envelope,
    render_footer,
    save_technique,
    search_index,
    write_adoption_manifest,
)
from .search_index import build_search_index, search_full_text, search_index_status


def register_knowledge_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register bounded, local-only knowledge commands."""
    parser = subparsers.add_parser(
        "knowledge",
        help="index local sources, search exact-first, recall techniques, and adopt safely",
    )
    commands = parser.add_subparsers(dest="knowledge_command", required=True)
    index = commands.add_parser("index", help="build or query the local source index")
    index_commands = index.add_subparsers(dest="knowledge_index_command", required=True)
    build = index_commands.add_parser("build", help="write a deterministic metadata index")
    build.add_argument("--root", default=".")
    build.add_argument("--output")
    build.add_argument("--max-files", type=int, default=10_000)
    build.add_argument("--max-bytes", type=int, default=25_000_000)
    build.add_argument("--max-depth", type=int, default=32)
    build.add_argument(
        "--metadata-only",
        action="store_true",
        help="keep the legacy metadata index only",
    )
    build.add_argument(
        "--strict",
        action="store_true",
        help="rehash every source instead of reusing unchanged fingerprints",
    )
    search = index_commands.add_parser("search", help="search a local index without writes")
    search.add_argument("query")
    search.add_argument("--root", default=".")
    search.add_argument("--index", default=".opencntx/search-v2.sqlite")
    search.add_argument("--max-results", type=int, default=20)
    search.add_argument("--max-bytes", type=int, default=100_000)
    search.add_argument("--max-tokens", type=int, default=25_000)
    search.add_argument("--max-snippet-chars", type=int, default=600)
    search.add_argument("--delivery-report", action="store_true")
    search.add_argument("--max-output-bytes", type=int, default=100_000)
    search.add_argument(
        "--metadata-only",
        action="store_true",
        help="force the legacy index format for compatibility",
    )
    status = index_commands.add_parser("status", help="check search scope and source freshness")
    status.add_argument("--root", default=".")
    status.add_argument("--index", default=".opencntx/search-v2.sqlite")
    status.add_argument("--limit", type=int, help="opt into a bounded status page (1-1000)")
    status.add_argument("--offset", type=int, default=0)
    status.add_argument(
        "--fast",
        action="store_true",
        help="compare filesystem fingerprints without rehashing every source",
    )

    technique = commands.add_parser("technique", help="store or recall evidence-bound procedures")
    technique_commands = technique.add_subparsers(dest="knowledge_technique_command", required=True)
    add = technique_commands.add_parser("add", help="validate and store one JSON technique card")
    add.add_argument("--root", default=".")
    add.add_argument("--input", required=True)
    add.add_argument("--expected-digest", help="update only the exact previously read card")
    listing = technique_commands.add_parser("list", help="list stored technique cards")
    listing.add_argument("--root", default=".")
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--offset", type=int, default=0)

    adopt = commands.add_parser(
        "adopt", help="inventory an existing project without taking ownership"
    )
    adopt.add_argument("--root", default=".")
    adopt.add_argument("--output")
    adopt.add_argument(
        "--expected-manifest-digest",
        help="require the source tree to match a previously reviewed preview digest",
    )
    adopt.add_argument(
        "--write", action="store_true", help="write the exact manifest after inspection"
    )

    visual = commands.add_parser("visual", help="preview or apply one reviewed visual text section")
    visual_commands = visual.add_subparsers(dest="knowledge_visual_command", required=True)
    preview = visual_commands.add_parser("preview")
    preview.add_argument("--root", default=".")
    preview.add_argument("--document", required=True)
    preview.add_argument("--intent", type=Path, required=True)
    apply = visual_commands.add_parser("apply")
    apply.add_argument("--root", default=".")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--intent", type=Path, required=True)
    apply.add_argument("--review", type=Path, required=True)
    rollback = visual_commands.add_parser("rollback")
    rollback.add_argument("--root", default=".")
    rollback.add_argument("--plan", type=Path, required=True)

    footer = commands.add_parser("footer", help="render a provider-neutral footer contract")
    footer.add_argument("--task-note")
    footer.add_argument("--status")
    footer.add_argument("--now")
    footer.add_argument("--thereafter")
    footer.add_argument("--chat")
    footer.add_argument("--tokens")
    footer.add_argument("--model")
    footer.add_argument("--proposal")
    footer.add_argument("--from-host-envelope-v2", type=Path)
    footer.add_argument("--session-id")
    footer.add_argument("--context-generation")
    footer.add_argument("--source-digest")
    footer.add_argument("--locale", choices=("en",), default="en")
    footer.add_argument("--output-kind", choices=("text", "json", "tool", "code"), default="text")
    footer.add_argument(
        "--from-host-envelope",
        type=Path,
        help="compile host-bound telemetry from one validated JSON envelope",
    )
    footer.add_argument(
        "--profile", choices=("commonmark", "portable", "plain", "exact"), default="commonmark"
    )


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _index_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _dispatch_index(args: argparse.Namespace) -> int:
    if args.knowledge_index_command == "build":
        search_result = None
        if args.metadata_only:
            result = build_index(
                Path(args.root),
                output=Path(args.output) if args.output else None,
                max_files=args.max_files,
                max_bytes=args.max_bytes,
                max_depth=args.max_depth,
            )
        else:
            search_result = build_search_index(
                Path(args.root),
                max_files=args.max_files,
                max_bytes=args.max_bytes,
                max_depth=args.max_depth,
                strict=args.strict,
                legacy_output=Path(args.output)
                if args.output
                else Path(args.root).resolve() / ".opencntx" / "index-v1.json",
            )
            result = search_result.pop("legacy_index")
        response = {
            "status": "INDEX_BUILT",
            "path": args.output or str(Path(args.root) / ".opencntx" / "index-v1.json"),
            "index_digest": result["index_digest"],
            "stats": result["stats"],
        }
        if search_result is not None:
            response["search_index"] = search_result
        _json(response)
        return 0
    if args.knowledge_index_command == "status":
        root = Path(args.root)
        result = search_index_status(
            root,
            index=_index_path(root, args.index),
            strict=not args.fast,
        )
        if args.limit is not None:
            from .search_index import status_page

            result = status_page(result, limit=args.limit, offset=args.offset)
        elif args.offset:
            raise KnowledgeError("Status --offset requires --limit.")
        _json(result)
        return 0
    root = Path(args.root)
    index_path = _index_path(root, args.index)
    if args.delivery_report:
        from .search_index import search_delivery

        if args.metadata_only:
            raise KnowledgeError(
                "A delivery report requires the full-text index, not legacy metadata."
            )
        _json(
            search_delivery(
                index_path,
                args.query,
                root=root,
                max_results=args.max_results,
                max_bytes=args.max_bytes,
                max_tokens=args.max_tokens,
                max_snippet_chars=args.max_snippet_chars,
                max_output_bytes=args.max_output_bytes,
            )
        )
        return 0
    if args.metadata_only or not str(args.index).lower().endswith(".sqlite"):
        legacy_path = (
            index_path
            if not args.metadata_only or not str(args.index).lower().endswith(".sqlite")
            else root / ".opencntx" / "index-v1.json"
        )
        result = search_index(
            load_index(legacy_path),
            args.query,
            max_results=args.max_results,
            max_bytes=args.max_bytes,
        )
        _json(result)
        return 0
    try:
        result = search_full_text(
            index_path,
            args.query,
            root=root,
            max_results=args.max_results,
            max_bytes=args.max_bytes,
            max_tokens=args.max_tokens,
            max_snippet_chars=args.max_snippet_chars,
        )
    except KnowledgeError:
        if index_path.is_file():
            raise
        legacy = root / ".opencntx" / "index-v1.json"
        result = search_index(
            load_index(legacy),
            args.query,
            max_results=args.max_results,
            max_bytes=args.max_bytes,
        )
    _json(result)
    return 0


def _dispatch_technique(args: argparse.Namespace) -> int:
    if args.knowledge_technique_command == "list":
        _json(
            {
                "format": "ocx-technique-list-v1",
                "cards": list_techniques(Path(args.root), limit=args.limit, offset=args.offset),
            }
        )
        return 0
    try:
        value = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError(f"Technique card input cannot be read: {args.input}") from exc
    if not isinstance(value, dict):
        raise KnowledgeError("Technique card input must contain one JSON object.")
    destination = save_technique(Path(args.root), value, expected_digest=args.expected_digest)
    _json(
        {
            "status": "TECHNIQUE_SAVED",
            "path": str(destination),
            "technique_id": value["technique_id"],
        }
    )
    return 0


def _dispatch_adopt(args: argparse.Namespace) -> int:
    if args.expected_manifest_digest and not args.write:
        raise KnowledgeError("--expected-manifest-digest requires --write.")
    if args.write:
        manifest = write_adoption_manifest(
            Path(args.root),
            Path(args.output) if args.output else None,
            expected_manifest_digest=args.expected_manifest_digest,
        )
        status = "ADOPTION_MANIFEST_WRITTEN"
    else:
        manifest = build_adoption_manifest(Path(args.root))
        status = "ADOPTION_PREVIEW"
    _json({"status": status, "output": args.output, "manifest": manifest})
    return 0


def _dispatch_footer(args: argparse.Namespace) -> int:
    if args.from_host_envelope_v2 is not None:
        from .knowledge import _strict_object
        from .knowledge_io import bounded_read
        from .presentation import presentation_footer

        if args.from_host_envelope is not None or any(
            value is not None for value in (args.chat, args.tokens, args.model, args.proposal)
        ):
            raise KnowledgeError("A v2 host envelope cannot be mixed with other telemetry.")
        path = args.from_host_envelope_v2.absolute()
        try:
            envelope = json.loads(
                bounded_read(path.parent, path.name, 65_536), object_pairs_hook=_strict_object
            )
        except (ValueError, UnicodeError) as exc:
            raise KnowledgeError("Presentation envelope is not valid bounded JSON.") from exc
        if not isinstance(envelope, dict):
            raise KnowledgeError("Presentation envelope must be an object.")
        rendered = presentation_footer(
            envelope,
            session_id=args.session_id,
            context_generation=args.context_generation,
            source_digest=args.source_digest,
            locale=args.locale,
            output_kind=args.output_kind,
            profile=args.profile,
            task_note=args.task_note,
            status=args.status,
            now=args.now,
            thereafter=args.thereafter,
        )
        print(rendered, end="")
        return 0
    if args.from_host_envelope is not None:
        if any(value is not None for value in (args.chat, args.tokens, args.model, args.proposal)):
            raise KnowledgeError(
                "Host envelope telemetry cannot be combined with explicit metric arguments."
            )
        contract = make_footer_contract_from_host_envelope(
            load_footer_envelope(args.from_host_envelope),
            task_note=args.task_note,
            status=args.status,
            now=args.now,
            thereafter=args.thereafter,
            profile=args.profile,
        )
    else:
        contract = make_footer_contract(
            task_note=args.task_note,
            status=args.status,
            now=args.now,
            thereafter=args.thereafter,
            chat=args.chat,
            tokens=args.tokens,
            model=args.model,
            proposal=args.proposal,
            profile=args.profile,
        )
    if args.profile == "exact":
        _json(footer_output(contract))
    else:
        print(render_footer(contract), end="")
    return 0


def _visual_object(path: Path) -> dict:
    from .knowledge import _strict_object
    from .knowledge_io import bounded_read

    selected = path.absolute()
    try:
        value = json.loads(
            bounded_read(selected.parent, selected.name, 100_000), object_pairs_hook=_strict_object
        )
    except (ValueError, UnicodeError) as exc:
        raise KnowledgeError("Visual input is not valid bounded JSON.") from exc
    if not isinstance(value, dict):
        raise KnowledgeError("Visual input must be a JSON object.")
    return value


def _dispatch_visual(args: argparse.Namespace) -> int:
    from .visual_integration import (
        apply_visual_integration,
        preview_visual_integration,
        rollback_visual_integration,
    )

    try:
        if args.knowledge_visual_command == "preview":
            result = preview_visual_integration(
                Path(args.root), args.document, _visual_object(args.intent)
            )
        elif args.knowledge_visual_command == "apply":
            result = apply_visual_integration(
                Path(args.root),
                _visual_object(args.plan),
                _visual_object(args.intent),
                _visual_object(args.review),
            )
        else:
            result = rollback_visual_integration(Path(args.root), _visual_object(args.plan))
    except OSError as exc:
        raise KnowledgeError("Visual integration filesystem operation failed.") from exc
    _json(result)
    return 0


def dispatch_knowledge(args: argparse.Namespace) -> int | None:
    """Dispatch knowledge commands or leave the root family to another module."""
    if args.command != "knowledge":
        return None
    if args.knowledge_command == "index":
        return _dispatch_index(args)
    if args.knowledge_command == "technique":
        return _dispatch_technique(args)
    if args.knowledge_command == "adopt":
        return _dispatch_adopt(args)
    if args.knowledge_command == "visual":
        return _dispatch_visual(args)
    if args.knowledge_command == "footer":
        return _dispatch_footer(args)
    return 2
