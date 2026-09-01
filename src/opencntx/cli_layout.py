"""Read-only layout command family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .layout import audit_layout, format_layout_report, layout_report_record
from .layout_plan import build_layout_plan, verify_layout_plan


def register_layout_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the additive layout family."""
    parser = subparsers.add_parser(
        "layout",
        help="audit a versioned workspace order contract without writes",
    )
    commands = parser.add_subparsers(dest="layout_command", required=True)
    for name, help_text in (
        ("audit", "report deterministic order findings without changing paths"),
        ("verify", "require a zero-finding order result without changing paths"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--contract", required=True, help="order contract JSON file")
        command.add_argument("--base", default=".", help="base for relative registered roots")
        command.add_argument("--json", action="store_true", help="emit stable JSON output")
    plan = commands.add_parser("plan", help="preview or verify a digest-bound layout migration")
    plan_commands = plan.add_subparsers(dest="layout_plan_command", required=True)
    preview = plan_commands.add_parser("preview", help="build one read-only migration plan")
    preview.add_argument("--manifest", required=True, help="layout migration manifest JSON")
    preview.add_argument("--base", default=".", help="base for relative manifest paths")
    verify_plan = plan_commands.add_parser(
        "verify", help="refuse a plan when any preview base has changed"
    )
    verify_plan.add_argument("--plan", required=True, help="saved READY layout plan JSON")


def dispatch_layout(args: argparse.Namespace) -> int | None:
    """Dispatch one layout command, or return None for another root family."""
    if args.command != "layout":
        return None
    if args.layout_command == "plan":
        if args.layout_plan_command == "preview":
            result = build_layout_plan(Path(args.manifest), Path(args.base))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["status"] == "READY" else 1
        result = verify_layout_plan(Path(args.plan))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "VERIFIED" else 1
    report = audit_layout(Path(args.contract), Path(args.base))
    if args.json:
        print(json.dumps(layout_report_record(report), indent=2, sort_keys=True))
    else:
        print(format_layout_report(report))
    return 0 if args.layout_command == "audit" or report.ok else 1
