"""Read-only layout command family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .layout import audit_layout, format_layout_report, layout_report_record


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


def dispatch_layout(args: argparse.Namespace) -> int | None:
    """Dispatch one layout command, or return None for another root family."""
    if args.command != "layout":
        return None
    report = audit_layout(Path(args.contract), Path(args.base))
    if args.json:
        print(json.dumps(layout_report_record(report), indent=2, sort_keys=True))
    else:
        print(format_layout_report(report))
    return 0 if args.layout_command == "audit" or report.ok else 1
