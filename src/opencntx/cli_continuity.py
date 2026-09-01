"""Command-line facade for local roadmap continuity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .continuity import (
    FlowResult,
    advance_flow,
    discover_capabilities,
    export_capsule,
    flow_status,
    format_flow,
    health_report,
    import_capsule,
    inspect_adapter,
    preview_roadmap,
    start_flow,
    verify_capsule,
)
from .continuity_sync import apply_sync, build_sync_preview, configure_sync, sync_status
from .host_protocol import claim_host, host_status, resume_host


def register_continuity_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the additive universal flow command family."""
    parser = subparsers.add_parser(
        "flow",
        help="run a restart-safe local roadmap with one AUTO PILOT approval",
    )
    commands = parser.add_subparsers(dest="flow_command", required=True)

    preview = commands.add_parser("preview", help="check only existing paths touched by a roadmap")
    preview.add_argument("roadmap", help="portable roadmap JSON")
    _root_argument(preview)
    preview.add_argument("--json", action="store_true", help="print machine-readable JSON")

    start = commands.add_parser("start", help="start a complete bounded roadmap once")
    start.add_argument("roadmap", help="portable roadmap JSON")
    start.add_argument("--approval", required=True, help='exact approval: "AUTO PILOT"')
    _root_argument(start)
    start.add_argument("--json", action="store_true", help="print machine-readable JSON")

    status = commands.add_parser("status", help="rebuild current state from local history")
    _root_argument(status)
    status.add_argument("--json", action="store_true", help="print machine-readable JSON")

    advance = commands.add_parser(
        "advance", help="record PASS or FAIL and automatically trigger the next detail"
    )
    _root_argument(advance)
    advance.add_argument("--outcome", required=True, choices=("PASS", "FAIL"))
    advance.add_argument(
        "--evidence", action="append", required=True, help="relative evidence file"
    )
    advance.add_argument("--reason", default="", help="required one-line reason for FAIL")
    advance.add_argument(
        "--handoff",
        help="optional relative JSON with decisions, result, changed paths, explanation, and risks",
    )
    advance.add_argument("--host", help="portable host ID when the assignment was claimed")
    advance.add_argument(
        "--claim-digest", help="exact active host claim required after host claim"
    )
    advance.add_argument("--json", action="store_true", help="print machine-readable JSON")

    health = commands.add_parser("health", help="verify store, roadmap, detail and event chain")
    _root_argument(health)
    health.add_argument("--json", action="store_true", help="print machine-readable JSON")

    capabilities = commands.add_parser(
        "capabilities", help="discover local storage and Git capabilities without writes"
    )
    _root_argument(capabilities)
    capabilities.add_argument("--json", action="store_true", help="print machine-readable JSON")

    inspect = commands.add_parser("inspect", help="run one read-only local adapter")
    inspect.add_argument("adapter", choices=("file", "git", "markdown", "json"))
    inspect.add_argument("target", nargs="?", default=".")
    _root_argument(inspect)
    inspect.add_argument("--json", action="store_true", help="print machine-readable JSON")

    capsule = commands.add_parser("capsule", help="export, verify or import a portable capsule")
    capsule_commands = capsule.add_subparsers(dest="flow_capsule_command", required=True)
    capsule_export = capsule_commands.add_parser("export", help="export a deterministic capsule")
    capsule_export.add_argument("destination")
    _root_argument(capsule_export)
    capsule_verify = capsule_commands.add_parser("verify", help="independently verify a capsule")
    capsule_verify.add_argument("capsule")
    capsule_import = capsule_commands.add_parser("import", help="restore into a new local store")
    capsule_import.add_argument("capsule")
    _root_argument(capsule_import)

    sync = commands.add_parser("sync", help="preview, configure or apply an optional Git replica")
    sync_commands = sync.add_subparsers(dest="flow_sync_command", required=True)
    for name, help_text in (
        ("preview", "preview a filtered private Git replica without writes"),
        ("configure", "enable explicit EVERY_CHECKPOINT sync after PASS, FAIL, or BLOCKED"),
        ("apply", "apply one exact preview with non-force push and readback"),
    ):
        operation = sync_commands.add_parser(name, help=help_text)
        operation.add_argument("repository", help="dedicated local Git checkout for the replica")
        operation.add_argument("--remote", default="origin")
        operation.add_argument("--branch", default="main")
        operation.add_argument(
            "--private-repository",
            action="store_true",
            help="confirm that a non-local remote destination is private",
        )
        if name == "apply":
            operation.add_argument("--preview-digest", required=True)
        _root_argument(operation)
    sync_state = sync_commands.add_parser("status", help="show optional sync state")
    _root_argument(sync_state)

    host = commands.add_parser("host", help="deliver, claim, or resume one assignment safely")
    host_commands = host.add_subparsers(dest="flow_host_command", required=True)
    host_status_parser = host_commands.add_parser(
        "status", help="deliver exactly one current assignment without writes"
    )
    host_status_parser.add_argument("--host", required=True, help="portable uppercase host ID")
    _root_argument(host_status_parser)
    host_claim_parser = host_commands.add_parser(
        "claim", help="claim one exact delivery with idempotent retry behavior"
    )
    host_claim_parser.add_argument("--host", required=True, help="portable uppercase host ID")
    host_claim_parser.add_argument("--delivery-digest", required=True)
    _root_argument(host_claim_parser)
    host_resume_parser = host_commands.add_parser(
        "resume", help="resume a claim or route it to the next status transition"
    )
    host_resume_parser.add_argument("--host", required=True, help="portable uppercase host ID")
    host_resume_parser.add_argument("--claim-digest", required=True)
    _root_argument(host_resume_parser)


def _root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".", help="project root; default: current directory")


def _flow_value(result: FlowResult) -> dict[str, object]:
    return {
        "status": result.status,
        "current_assignment": result.current_assignment,
        "completed": list(result.completed),
        "total": result.total,
        "next_action": result.next_action,
        "minimum_action": result.minimum_action,
        "state_digest": result.state_digest,
    }


def _print(value: object, *, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(value)


def _dispatch_capsule(args: argparse.Namespace) -> int:
    command = args.flow_capsule_command
    if command == "export":
        _print(export_capsule(Path(args.root), Path(args.destination)))
        return 0
    if command == "verify":
        _print(verify_capsule(Path(args.capsule)))
        return 0
    if command == "import":
        _print(import_capsule(Path(args.root), Path(args.capsule)))
        return 0
    return 2


def _dispatch_sync(args: argparse.Namespace) -> int:
    command = args.flow_sync_command
    root = Path(args.root)
    if command == "status":
        _print(sync_status(root))
        return 0
    repository = Path(args.repository)
    options = {
        "remote": args.remote,
        "branch": args.branch,
        "private_repository_confirmed": args.private_repository,
    }
    if command == "preview":
        _print(build_sync_preview(root, repository, **options))
        return 0
    if command == "configure":
        _print(configure_sync(root, repository, **options))
        return 0
    if command == "apply":
        result = apply_sync(
            root,
            repository,
            expected_preview_digest=args.preview_digest,
            **options,
        )
        _print(
            {
                "status": result.status,
                "preview_digest": result.preview_digest,
                "commit": result.commit,
                "tree": result.tree,
                "remote_head": result.remote_head,
                "file_count": result.file_count,
                "byte_count": result.byte_count,
                "checks": list(result.checks),
                "checkpoint_policy": result.checkpoint_policy,
                "trigger": result.trigger,
            }
        )
        return 0
    return 2


def _dispatch_host(args: argparse.Namespace) -> int:
    command = args.flow_host_command
    root = Path(args.root)
    if command == "status":
        _print(host_status(root, args.host))
        return 0
    if command == "claim":
        _print(claim_host(root, args.host, args.delivery_digest))
        return 0
    if command == "resume":
        _print(resume_host(root, args.host, args.claim_digest))
        return 0
    return 2


def dispatch_continuity(args: argparse.Namespace) -> int | None:
    """Dispatch one flow command, or return None for another family."""
    if args.command != "flow":
        return None
    command = args.flow_command
    root = Path(getattr(args, "root", "."))
    if command == "preview":
        _print(preview_roadmap(root, Path(args.roadmap)))
        return 0
    if command == "start":
        result = start_flow(root, Path(args.roadmap), args.approval)
        _print(_flow_value(result)) if args.json else print(format_flow(result))
        return 0
    if command == "status":
        result = flow_status(root)
        _print(_flow_value(result)) if args.json else print(format_flow(result))
        return 0
    if command == "advance":
        result = advance_flow(
            root,
            outcome=args.outcome,
            evidence_paths=args.evidence,
            reason=args.reason,
            handoff_path=args.handoff,
            host_id=args.host,
            claim_digest=args.claim_digest,
        )
        _print(_flow_value(result)) if args.json else print(format_flow(result))
        return 0
    if command == "health":
        value = health_report(root)
        _print(value)
        return 0 if value["status"] == "HEALTHY" else 1
    if command == "capabilities":
        _print(discover_capabilities(root))
        return 0
    if command == "inspect":
        _print(inspect_adapter(root, args.adapter, args.target))
        return 0
    if command == "capsule":
        return _dispatch_capsule(args)
    if command == "sync":
        return _dispatch_sync(args)
    if command == "host":
        return _dispatch_host(args)
    return 2
