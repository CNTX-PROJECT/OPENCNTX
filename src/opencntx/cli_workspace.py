"""Workspace command parser and dispatch coordinator for OPENCNTX."""

from __future__ import annotations

import argparse
from pathlib import Path

from .cli_content import (
    dispatch_catalog,
    dispatch_chapter,
    dispatch_context,
    dispatch_media,
    register_catalog_commands,
    register_chapter_commands,
    register_context_commands,
    register_media_commands,
)
from .cli_definitions import (
    dispatch_executor,
    dispatch_playbook,
    dispatch_role,
    register_executor_commands,
    register_playbook_commands,
    register_role_commands,
)
from .cli_lifecycle import dispatch_lifecycle, register_lifecycle_commands
from .cli_tasks import dispatch_task, register_task_commands
from .control import refresh_control_snapshot
from .integrity import (
    doctor_workspace,
    format_doctor_report,
    format_recovery_plan,
    recover_workspace,
)
from .workspace import PRIVACY_LABELS, capture_source, init_workspace


def register_workspace_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register workspace commands in their stable public order."""
    parser = subparsers.add_parser(
        "workspace",
        help="Stable workspace: local sources, knowledge, task gates, and navigation",
    )
    workspace = parser.add_subparsers(dest="workspace_command", required=True)
    _register_workspace_foundation(workspace)
    register_lifecycle_commands(workspace)
    _register_control_commands(workspace)
    register_chapter_commands(workspace)
    register_catalog_commands(workspace)
    register_media_commands(workspace)
    register_playbook_commands(workspace)
    register_role_commands(workspace)
    register_executor_commands(workspace)
    register_context_commands(workspace)
    register_task_commands(workspace)


def _register_workspace_foundation(
    workspace: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    init = workspace.add_parser(
        "init",
        help="safely create the fixed project workspace structure",
    )
    init.add_argument(
        "project",
        nargs="?",
        default=".",
        help="project directory; default: current directory",
    )
    capture = workspace.add_parser(
        "capture",
        help="capture one regular local file without executing it",
    )
    capture.add_argument("source", help="local source file")
    capture.add_argument(
        "--root",
        default=".",
        help="project workspace; default: current directory",
    )
    capture.add_argument(
        "--privacy",
        choices=PRIVACY_LABELS,
        default="PRIVATE",
        help="privacy label; default: PRIVATE",
    )
    capture.add_argument("--origin", help="short origin on one line")
    capture.add_argument(
        "--supersedes",
        help="optional existing source ID superseded by this new source",
    )
    doctor = workspace.add_parser(
        "doctor",
        help="read-only diagnosis of active or incomplete writer transactions",
    )
    doctor.add_argument(
        "--root",
        default=".",
        help="project workspace; default: current directory",
    )
    recover = workspace.add_parser(
        "recover",
        help="preview or apply exact backup-first transaction recovery",
    )
    recover.add_argument(
        "--root",
        default=".",
        help="project workspace; default: current directory",
    )
    recover.add_argument(
        "--transaction",
        required=True,
        help="exact transaction ID reported by workspace doctor",
    )
    recover.add_argument(
        "--intent-sha256",
        required=True,
        help="exact intent SHA-256 reported by workspace doctor",
    )
    recover.add_argument(
        "--apply",
        action="store_true",
        help="apply the exact recovery after a read-only preview",
    )


def _register_control_commands(
    workspace: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    control = workspace.add_parser(
        "control",
        help="manage the compact derived current roadmap control",
    )
    subparsers = control.add_subparsers(
        dest="workspace_control_command",
        required=True,
    )
    refresh = subparsers.add_parser(
        "refresh",
        help="refresh the control snapshot without changing the official roadmap",
    )
    refresh.add_argument(
        "--root",
        default=".",
        help="project workspace; default: current directory",
    )


def _dispatch_workspace_foundation(args: argparse.Namespace) -> int | None:
    command = args.workspace_command
    if command == "init":
        init_result = init_workspace(Path(args.project))
        if init_result.created:
            print(f"Created: project workspace {init_result.root}")
        else:
            print(f"Already exists: project workspace {init_result.root}; nothing changed.")
        return 0
    if command == "capture":
        root = Path(args.root)
        capture_result = capture_source(
            root,
            Path(args.source),
            privacy=args.privacy,
            origin=args.origin,
            supersedes=args.supersedes,
        )
        receipt = capture_result.receipt_path.relative_to(root.resolve(strict=True)).as_posix()
        print(
            f"{capture_result.status}: {capture_result.source_id} "
            f"({capture_result.byte_count} bytes, SHA-256 {capture_result.sha256})"
        )
        print(f"Receipt: {receipt}")
        return 0
    if command == "doctor":
        report = doctor_workspace(Path(args.root))
        print(format_doctor_report(report))
        return 0 if report.ok else 1
    if command == "recover":
        plan = recover_workspace(
            Path(args.root),
            args.transaction,
            args.intent_sha256,
            apply=args.apply,
        )
        print(format_recovery_plan(plan, applied=args.apply))
        return 0
    return None


def _dispatch_control(args: argparse.Namespace) -> int:
    if args.workspace_control_command != "refresh":
        return 2
    root = Path(args.root)
    result = refresh_control_snapshot(root)
    resolved_root = root.resolve(strict=True)
    assert result.receipt_path is not None
    receipt = result.receipt_path.relative_to(resolved_root).as_posix()
    print(f"{result.status}: {result.mode}")
    print(f"Roadmap-SHA-256: {result.roadmap_sha256}")
    if result.block_sha256 is not None:
        print(f"Control block: {result.block_bytes} bytes, SHA-256 {result.block_sha256}")
    if result.snapshot_sha256 is not None:
        print(f"Snapshot-SHA-256: {result.snapshot_sha256}")
    if result.snapshot_path is not None:
        snapshot = result.snapshot_path.relative_to(resolved_root).as_posix()
        print(f"Snapshot: {snapshot}")
    print(f"Receipt: {receipt}")
    print("Derived evidence; this grants no OWNER authority.")
    return 0


def dispatch_workspace(args: argparse.Namespace) -> int | None:
    """Dispatch a workspace command, or return None for another root family."""
    if args.command != "workspace":
        return None
    foundation = _dispatch_workspace_foundation(args)
    if foundation is not None:
        return foundation
    dispatchers = {
        "lifecycle": dispatch_lifecycle,
        "control": _dispatch_control,
        "chapter": dispatch_chapter,
        "catalog": dispatch_catalog,
        "media": dispatch_media,
        "playbook": dispatch_playbook,
        "role": dispatch_role,
        "executor": dispatch_executor,
        "context": dispatch_context,
        "task": dispatch_task,
    }
    dispatcher = dispatchers.get(args.workspace_command)
    return 2 if dispatcher is None else dispatcher(args)
