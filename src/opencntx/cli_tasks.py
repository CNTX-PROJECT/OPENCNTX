"""Task command parser and dispatch for OPENCNTX."""

from __future__ import annotations

import argparse
from pathlib import Path

from .attempts import ERROR_CLASSES, record_attempt
from .workflow import (
    TaskResult,
    accept_result,
    approve_task,
    begin_task,
    cancel_task,
    close_task,
    propose_task,
    review_result,
    submit_result,
    supersede_task,
    task_status,
)


def register_task_commands(
    workspace_subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the complete task command family."""
    parser = workspace_subparsers.add_parser(
        "task",
        help="register one bounded task with exact OWNER gates",
    )
    subparsers = parser.add_subparsers(
        dest="workspace_task_command",
        required=True,
    )
    _register_task_proposal(subparsers)
    _register_task_progress(subparsers)
    _register_task_review(subparsers)
    _register_task_attempt_and_terminal(subparsers)


def _register_task_proposal(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    propose = subparsers.add_parser(
        "propose",
        help="create one task proposal that waits for exact OWNER approval",
    )
    propose.add_argument("task_id", help="task ID, for example TASK-20260816-0001")
    propose.add_argument("--title", required=True, help="short task title")
    propose.add_argument("--goal", required=True, help="one bounded goal")
    propose.add_argument("--done", required=True, help="exact Definition of Done")
    propose.add_argument(
        "--executor-role",
        required=True,
        help="bounded executor role",
    )
    propose.add_argument(
        "--input",
        action="append",
        required=True,
        help="official relative input path; repeatable",
    )
    propose.add_argument(
        "--allow",
        action="append",
        required=True,
        help="allowed action; repeatable",
    )
    propose.add_argument(
        "--forbid",
        action="append",
        required=True,
        help="forbidden action; repeatable",
    )
    propose.add_argument(
        "--expected-output",
        required=True,
        help="expected result form",
    )
    propose.add_argument(
        "--acceptance",
        action="append",
        required=True,
        help="acceptance criterion; repeatable",
    )
    propose.add_argument(
        "--architect",
        required=True,
        help="local ARCHITECT actor statement",
    )
    propose.add_argument("--root", default=".", help="project workspace")

    approve = subparsers.add_parser(
        "approve",
        help="register an exact local OWNER approval",
    )
    approve.add_argument("task_id")
    approve.add_argument("--revision", required=True, type=int)
    approve.add_argument("--proposal-digest", required=True)
    approve.add_argument("--owner", required=True)
    approve.add_argument("--root", default=".")


def _register_task_progress(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    begin = subparsers.add_parser(
        "begin",
        help="register execution without starting a process or agent",
    )
    begin.add_argument("task_id")
    begin.add_argument("--architect", required=True)
    begin.add_argument("--root", default=".")

    result = subparsers.add_parser(
        "submit-result",
        help="store one result and optional evidence as bytes",
    )
    result.add_argument("task_id")
    result.add_argument("--result", required=True)
    result.add_argument("--evidence", action="append", default=[])
    result.add_argument("--limitation", action="append", default=[])
    result.add_argument("--open-question", action="append", default=[])
    result.add_argument("--executor", required=True)
    result.add_argument("--root", default=".")


def _register_task_review(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    review = subparsers.add_parser(
        "review-result",
        help="bind ARCHITECT review to the exact result",
    )
    review.add_argument("task_id")
    review.add_argument("--result-digest", required=True)
    review.add_argument("--outcome", required=True, choices=("PASS", "RETURN"))
    review.add_argument("--finding", action="append", required=True)
    review.add_argument("--architect", required=True)
    review.add_argument("--root", default=".")

    accept = subparsers.add_parser(
        "accept-result",
        help="register exact local OWNER acceptance or return",
    )
    accept.add_argument("task_id")
    accept.add_argument("--result-digest", required=True)
    accept.add_argument("--review-digest", required=True)
    accept.add_argument("--decision", required=True, choices=("ACCEPT", "RETURN"))
    accept.add_argument("--owner", required=True)
    accept.add_argument("--root", default=".")

    close = subparsers.add_parser(
        "close",
        help="write closure evidence only after OWNER acceptance",
    )
    close.add_argument("task_id")
    close.add_argument("--architect", required=True)
    close.add_argument("--root", default=".")

    status = subparsers.add_parser(
        "status",
        help="verify record chain, inputs, artifacts, and current gate",
    )
    status.add_argument("task_id")
    status.add_argument("--root", default=".")


def _register_task_attempt_and_terminal(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    attempt = subparsers.add_parser(
        "record-attempt",
        help="record one objective failed attempt; never execute or retry it",
    )
    attempt.add_argument("task_id")
    attempt.add_argument("--executor-id", required=True)
    attempt.add_argument("--action", required=True)
    attempt.add_argument("--command-type", required=True)
    attempt.add_argument("--target", required=True)
    attempt.add_argument("--input", action="append", required=True)
    attempt.add_argument("--exit-status", required=True, type=int)
    attempt.add_argument("--error-class", required=True, choices=ERROR_CLASSES)
    attempt.add_argument("--actions-used", required=True, type=int)
    attempt.add_argument("--duration-ms", required=True, type=int)
    attempt.add_argument("--result-evidence", required=True)
    attempt.add_argument("--new-evidence")
    attempt.add_argument("--root", default=".")

    cancel = subparsers.add_parser(
        "cancel",
        help="end a non-terminal task with an OWNER statement",
    )
    cancel.add_argument("task_id")
    cancel.add_argument("--reason", required=True)
    cancel.add_argument("--owner", required=True)
    cancel.add_argument("--root", default=".")

    supersede = subparsers.add_parser(
        "supersede",
        help="identify a replacement task ID with an OWNER statement",
    )
    supersede.add_argument("task_id")
    supersede.add_argument("--replacement-task-id", required=True)
    supersede.add_argument("--reason", required=True)
    supersede.add_argument("--owner", required=True)
    supersede.add_argument("--root", default=".")


def _print_task_result(root: Path, result: TaskResult) -> None:
    resolved_root = root.resolve(strict=True)
    task_path = result.task_path.relative_to(resolved_root).as_posix()
    print(f"{result.status}: {result.task_id} revision {result.revision}")
    print(f"Task status: {result.task_status}")
    print(f"Object digest: {result.object_digest}")
    print(f"Record digest: {result.record_digest}")
    print(f"Task card: {task_path}")
    if result.receipt_path is not None:
        receipt = result.receipt_path.relative_to(resolved_root).as_posix()
        print(f"Receipt: {receipt}")
    print("Actor ID is a local statement, not cryptographic identity evidence.")


def _dispatch_task_transition(
    args: argparse.Namespace,
    root: Path,
) -> TaskResult | None:
    command = args.workspace_task_command
    if command == "propose":
        return propose_task(
            root,
            args.task_id,
            title=args.title,
            goal=args.goal,
            definition_of_done=args.done,
            executor_role=args.executor_role,
            input_paths=args.input,
            allowed_actions=args.allow,
            forbidden_actions=args.forbid,
            expected_output=args.expected_output,
            acceptance_criteria=args.acceptance,
            architect=args.architect,
        )
    if command == "approve":
        return approve_task(
            root,
            args.task_id,
            revision=args.revision,
            proposal_digest=args.proposal_digest,
            owner=args.owner,
        )
    if command == "begin":
        return begin_task(root, args.task_id, architect=args.architect)
    if command == "close":
        return close_task(root, args.task_id, architect=args.architect)
    if command == "status":
        return task_status(root, args.task_id)
    if command == "cancel":
        return cancel_task(root, args.task_id, reason=args.reason, owner=args.owner)
    if command == "supersede":
        return supersede_task(
            root,
            args.task_id,
            replacement_task_id=args.replacement_task_id,
            reason=args.reason,
            owner=args.owner,
        )
    return None


def _dispatch_task_evidence(args: argparse.Namespace, root: Path) -> TaskResult | None:
    command = args.workspace_task_command
    if command == "submit-result":
        return submit_result(
            root,
            args.task_id,
            result_path=Path(args.result),
            evidence_paths=[Path(path) for path in args.evidence],
            limitations=args.limitation,
            open_questions=args.open_question,
            executor=args.executor,
        )
    if command == "review-result":
        return review_result(
            root,
            args.task_id,
            result_digest=args.result_digest,
            outcome=args.outcome,
            findings=args.finding,
            architect=args.architect,
        )
    if command == "accept-result":
        return accept_result(
            root,
            args.task_id,
            result_digest=args.result_digest,
            review_digest=args.review_digest,
            decision=args.decision,
            owner=args.owner,
        )
    if command == "record-attempt":
        new_evidence = None if args.new_evidence is None else Path(args.new_evidence)
        return record_attempt(
            root,
            args.task_id,
            executor_id=args.executor_id,
            action=args.action,
            command_type=args.command_type,
            target=args.target,
            input_paths=args.input,
            exit_status=args.exit_status,
            error_class=args.error_class,
            actions_used=args.actions_used,
            duration_ms=args.duration_ms,
            result_evidence_path=Path(args.result_evidence),
            new_evidence_path=new_evidence,
        )
    return None


def dispatch_task(args: argparse.Namespace) -> int:
    """Dispatch one task command."""
    root = Path(args.root)
    result = _dispatch_task_transition(args, root)
    if result is None:
        result = _dispatch_task_evidence(args, root)
    if result is None:
        return 2
    _print_task_result(root, result)
    return 0
