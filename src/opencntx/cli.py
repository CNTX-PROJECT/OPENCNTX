"""Stable command-line facade for OPENCNTX."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .cli_continuity import dispatch_continuity, register_continuity_commands
from .cli_core import dispatch_core, init_project, register_core_commands
from .cli_layout import dispatch_layout, register_layout_commands
from .cli_workspace import dispatch_workspace, register_workspace_commands
from .core import OpenCntxError
from .integrity import IntegrityError
from .workspace import WorkspaceError

__all__ = ["build_parser", "init_project", "main"]


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser from stable command families."""
    parser = argparse.ArgumentParser(
        prog="opencntx",
        description="Create a small, explicit, and verifiable context package for one task.",
        epilog=(
            "Core route: init, pack --preview, pack, inspect CONTEXT.md, verify. "
            "Stable workspace: structured local flow for longer projects."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_core_commands(subparsers)
    register_workspace_commands(subparsers)
    register_continuity_commands(subparsers)
    register_layout_commands(subparsers)
    return parser


def _configure_console_output() -> None:
    """Escape unsupported user characters instead of crashing narrow consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the OPENCNTX command-line interface."""
    _configure_console_output()
    args = build_parser().parse_args(argv)
    try:
        result = dispatch_core(args)
        if result is None:
            result = dispatch_workspace(args)
        if result is None:
            result = dispatch_continuity(args)
        if result is None:
            result = dispatch_layout(args)
        return 2 if result is None else result
    except (IntegrityError, OpenCntxError, WorkspaceError) as exc:
        detail = (
            f"operation failed ({exc.code})"
            if isinstance(exc, (IntegrityError, WorkspaceError))
            else str(exc)
        )
        print(f"Error: {detail}", file=sys.stderr)
        return 2
