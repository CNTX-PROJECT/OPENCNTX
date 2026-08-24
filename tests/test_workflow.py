from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.workflow import (
    WorkflowError,
    _append_event,
    _load_chain,
    _task_view_bytes,
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
from opencntx.workspace import init_workspace

TASK_ID = "TASK-20260816-0001"


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing_pythonpath) if part
    )
    return subprocess.run(
        [sys.executable, "-m", "opencntx", *arguments],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def propose(workspace: Path, task_id: str = TASK_ID):
    return propose_task(
        workspace,
        task_id,
        title="Controleer het plan",
        goal="Controleer één begrensd plan.",
        definition_of_done="Resultaat en bewijs zijn ingeleverd.",
        executor_role="ROLE-CONTROLEUR",
        input_paths=["CONTROL/ROADMAP.md"],
        allowed_actions=["Lees uitsluitend de gepinde input"],
        forbidden_actions=["Geen externe verzending"],
        expected_output="Eén lokaal resultaatbestand",
        acceptance_criteria=["Iedere claim verwijst naar bewijs"],
        architect="ARCHITECT",
    )


def begin(workspace: Path):
    proposed = propose(workspace)
    approve_task(
        workspace,
        TASK_ID,
        revision=1,
        proposal_digest=proposed.object_digest,
        owner="OWNER",
    )
    started = begin_task(workspace, TASK_ID, architect="ARCHITECT")
    return proposed, started


def record_attempt(
    workspace: Path,
    task_id: str,
    *,
    error_code: str,
    error_signature: str,
    new_basis: str,
    executor: str,
):
    """Create one historical v1 text attempt for read-compatibility tests."""
    chain = _load_chain(workspace, task_id)
    attempts = [event for event in chain.events if event.event_type == "attempt"]
    if (
        attempts
        and attempts[-1].payload["error_signature"] == error_signature
        and attempts[-1].payload["new_basis"] == new_basis
    ):
        raise WorkflowError(
            "Historical attempt has no changed text basis.",
            code="task_attempt_unchanged",
        )
    consecutive = 1
    for previous in reversed(attempts):
        if previous.payload["error_signature"] != error_signature:
            break
        consecutive += 1
    blocked = consecutive >= 3
    return _append_event(
        workspace,
        chain,
        event_type="attempt",
        to_status="BLOCKED" if blocked else "IN_EXECUTION",
        actor_id=executor,
        payload={
            "proposal_digest": chain.proposal_digest,
            "attempt_number": len(attempts) + 1,
            "error_code": error_code,
            "error_signature": error_signature,
            "new_basis": new_basis,
        },
        success_status="TASK_BLOCKED" if blocked else "TASK_ATTEMPT_RECORDED",
    )


def submit(workspace: Path, outside: Path):
    proposed, _ = begin(workspace)
    result_file = outside / "result.md"
    evidence_file = outside / "evidence.txt"
    result_file.write_text("begrensd resultaat", encoding="utf-8")
    evidence_file.write_text("controlebewijs", encoding="utf-8")
    result = submit_result(
        workspace,
        TASK_ID,
        result_path=result_file,
        evidence_paths=[evidence_file],
        limitations=["Alleen het gepinde plan is gelezen"],
        open_questions=["Geen"],
        executor="UITVOERDER-1",
    )
    return proposed, result


class WorkflowTests(unittest.TestCase):
    def test_exact_legacy_task_card_remains_readable_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            proposed = propose(workspace)
            chain = _load_chain(workspace, TASK_ID)
            proposed.task_path.write_bytes(_task_view_bytes(chain, legacy=True))
            before = proposed.task_path.read_bytes()

            status = task_status(workspace, TASK_ID)

            self.assertEqual(status.status, "TASK_STATUS_VALID")
            self.assertEqual(status.task_status, "AWAITING_OWNER_APPROVAL")
            self.assertEqual(proposed.task_path.read_bytes(), before)

    def test_proposal_is_append_only_digest_bound_and_human_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            roadmap_before = (workspace / "CONTROL" / "ROADMAP.md").read_bytes()

            result = propose(workspace)

            self.assertEqual(result.status, "TASK_PROPOSED")
            self.assertEqual(result.task_status, "AWAITING_OWNER_APPROVAL")
            self.assertRegex(result.object_digest, r"[0-9a-f]{64}\Z")
            events = list((workspace / "TASKS" / TASK_ID / "events").iterdir())
            self.assertEqual([path.name for path in events], ["0001-proposal.json"])
            task_text = result.task_path.read_text(encoding="utf-8")
            self.assertIn("Generated task card", task_text)
            self.assertIn("Geen externe verzending", task_text)
            self.assertIn(result.object_digest, task_text)
            self.assertEqual((workspace / "CONTROL" / "ROADMAP.md").read_bytes(), roadmap_before)
            self.assertIsNotNone(result.receipt_path)

    def test_wrong_digest_and_status_skip_are_rejected_without_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            proposed = propose(workspace)

            with self.assertRaises(WorkflowError) as digest_error:
                approve_task(
                    workspace,
                    TASK_ID,
                    revision=1,
                    proposal_digest="0" * 64,
                    owner="OWNER",
                )
            self.assertEqual(digest_error.exception.code, "task_digest_mismatch")
            failure_receipts = list((workspace / ".opencntx" / "receipts").glob("TASK-FAIL-*.json"))
            self.assertEqual(len(failure_receipts), 1)
            failure = json.loads(failure_receipts[0].read_text(encoding="utf-8"))
            self.assertEqual(failure["status"], "TASK_COMMAND_FAILED")
            self.assertEqual(failure["operation"], "approve")
            self.assertEqual(failure["error_code"], "task_digest_mismatch")
            self.assertNotIn(str(workspace), json.dumps(failure))
            with self.assertRaises(WorkflowError) as transition_error:
                begin_task(workspace, TASK_ID, architect="ARCHITECT")
            self.assertEqual(transition_error.exception.code, "task_record_invalid")
            self.assertEqual(len(list((workspace / "TASKS" / TASK_ID / "events").iterdir())), 1)
            self.assertEqual(task_status(workspace, TASK_ID).object_digest, proposed.object_digest)

    def test_complete_flow_requires_all_seven_events_and_closes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            outside = Path(temporary_directory)
            workspace = outside / "workspace"
            init_workspace(workspace)
            _, result = submit(workspace, outside)
            review = review_result(
                workspace,
                TASK_ID,
                result_digest=result.object_digest,
                outcome="PASS",
                findings=["Resultaat en bewijs zijn exact gekoppeld"],
                architect="ARCHITECT",
            )
            acceptance = accept_result(
                workspace,
                TASK_ID,
                result_digest=result.object_digest,
                review_digest=review.object_digest,
                decision="ACCEPT",
                owner="OWNER",
            )
            closed = close_task(workspace, TASK_ID, architect="ARCHITECT")

            self.assertEqual(acceptance.task_status, "OWNER_ACCEPTED")
            self.assertEqual(closed.status, "TASK_CLOSED")
            self.assertEqual(closed.task_status, "CLOSED")
            self.assertEqual(task_status(workspace, TASK_ID).task_status, "CLOSED")
            task_view = closed.task_path.read_text(encoding="utf-8")
            self.assertIn("Alleen het gepinde plan is gelezen", task_view)
            self.assertIn("Open questions", task_view)
            event_names = [
                path.name for path in sorted((workspace / "TASKS" / TASK_ID / "events").iterdir())
            ]
            self.assertEqual(
                event_names,
                [
                    "0001-proposal.json",
                    "0002-owner-approval.json",
                    "0003-execution-begun.json",
                    "0004-result.json",
                    "0005-architect-review.json",
                    "0006-owner-acceptance.json",
                    "0007-closure.json",
                ],
            )
            self.assertIn(closed.object_digest, closed.task_path.read_text(encoding="utf-8"))
            completed = workspace / ".opencntx" / "transactions" / "completed"
            self.assertGreaterEqual(len(list(completed.iterdir())), 7)
            self.assertEqual(
                list((workspace / ".opencntx" / "transactions" / "locks").rglob("*.lock")), []
            )

    def test_changed_input_invalidates_old_owner_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            proposed = propose(workspace)
            approve_task(
                workspace,
                TASK_ID,
                revision=1,
                proposal_digest=proposed.object_digest,
                owner="OWNER",
            )
            (workspace / "CONTROL" / "ROADMAP.md").write_text(
                "gewijzigde roadmap\n", encoding="utf-8"
            )

            with self.assertRaises(WorkflowError) as context:
                begin_task(workspace, TASK_ID, architect="ARCHITECT")

            self.assertEqual(context.exception.code, "task_input_stale")
            self.assertEqual(len(list((workspace / "TASKS" / TASK_ID / "events").iterdir())), 2)

    def test_tampered_event_and_unknown_task_content_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            propose(workspace)
            event_path = workspace / "TASKS" / TASK_ID / "events" / "0001-proposal.json"
            value = json.loads(event_path.read_text(encoding="utf-8"))
            value["payload"]["goal"] = "verborgen wijziging"
            event_path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaises(WorkflowError) as context:
                task_status(workspace, TASK_ID)
            self.assertEqual(context.exception.code, "task_object_digest_mismatch")

            event_path.unlink()
            (workspace / "TASKS" / TASK_ID / "onbekend.txt").write_text(
                "onbekend", encoding="utf-8"
            )
            with self.assertRaises(WorkflowError) as layout_context:
                task_status(workspace, TASK_ID)
            self.assertEqual(layout_context.exception.code, "task_path_unsafe")

    def test_manual_task_view_change_stops_next_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            proposed = propose(workspace)
            task_view = workspace / "TASKS" / TASK_ID / "TASK.md"
            task_view.write_text("handmatige waarheid\n", encoding="utf-8")

            with self.assertRaises(WorkflowError) as context:
                approve_task(
                    workspace,
                    TASK_ID,
                    revision=1,
                    proposal_digest=proposed.object_digest,
                    owner="OWNER",
                )
            self.assertEqual(context.exception.code, "task_view_unmanaged")

    def test_result_and_evidence_are_copied_as_bytes_and_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            outside = Path(temporary_directory)
            workspace = outside / "workspace"
            init_workspace(workspace)
            _, result = submit(workspace, outside)
            copied = workspace / "TASKS" / TASK_ID / "artifacts" / "result-r0001.bin"
            self.assertEqual(copied.read_bytes(), b"begrensd resultaat")
            copied.write_bytes(b"drift")

            with self.assertRaises(WorkflowError) as context:
                review_result(
                    workspace,
                    TASK_ID,
                    result_digest=result.object_digest,
                    outcome="PASS",
                    findings=["controle"],
                    architect="ARCHITECT",
                )
            self.assertEqual(context.exception.code, "task_artifact_stale")

    def test_unknown_artifact_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            propose(workspace)
            (workspace / "TASKS" / TASK_ID / "artifacts" / "unknown.bin").write_bytes(b"x")

            with self.assertRaises(WorkflowError) as context:
                task_status(workspace, TASK_ID)
            self.assertEqual(context.exception.code, "task_artifact_inventory_mismatch")

    def test_incomplete_staging_directory_stops_new_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            (workspace / "TASKS" / ".task-interrupted.tmp").mkdir()

            with self.assertRaises(WorkflowError) as context:
                propose(workspace)
            self.assertEqual(context.exception.code, "task_staging_incomplete")

    def test_returned_result_cannot_be_accepted_or_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            outside = Path(temporary_directory)
            workspace = outside / "workspace"
            init_workspace(workspace)
            _, result = submit(workspace, outside)
            returned = review_result(
                workspace,
                TASK_ID,
                result_digest=result.object_digest,
                outcome="RETURN",
                findings=["Bewijs ontbreekt"],
                architect="ARCHITECT",
            )
            self.assertEqual(returned.task_status, "RETURNED")
            with self.assertRaises(WorkflowError):
                accept_result(
                    workspace,
                    TASK_ID,
                    result_digest=result.object_digest,
                    review_digest=returned.object_digest,
                    decision="ACCEPT",
                    owner="OWNER",
                )
            with self.assertRaises(WorkflowError):
                close_task(workspace, TASK_ID, architect="ARCHITECT")

    def test_three_equal_failure_signatures_block_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            begin(workspace)

            first = record_attempt(
                workspace,
                TASK_ID,
                error_code="input_error",
                error_signature="zelfde-fout",
                new_basis="controle A",
                executor="UITVOERDER",
            )
            second = record_attempt(
                workspace,
                TASK_ID,
                error_code="input_error",
                error_signature="zelfde-fout",
                new_basis="controle B",
                executor="UITVOERDER",
            )
            third = record_attempt(
                workspace,
                TASK_ID,
                error_code="input_error",
                error_signature="zelfde-fout",
                new_basis="controle C",
                executor="UITVOERDER",
            )

            self.assertEqual(first.task_status, "IN_EXECUTION")
            self.assertEqual(second.task_status, "IN_EXECUTION")
            self.assertEqual(third.status, "TASK_BLOCKED")
            self.assertEqual(third.task_status, "BLOCKED")
            blocked_view = third.task_path.read_text(encoding="utf-8")
            self.assertIn("Attempt 3", blocked_view)
            self.assertIn("OWNER direction required", blocked_view)
            with self.assertRaises(WorkflowError):
                record_attempt(
                    workspace,
                    TASK_ID,
                    error_code="input_error",
                    error_signature="zelfde-fout",
                    new_basis="controle D",
                    executor="UITVOERDER",
                )

    def test_equal_failure_signature_requires_a_changed_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            begin(workspace)
            record_attempt(
                workspace,
                TASK_ID,
                error_code="input_error",
                error_signature="zelfde-fout",
                new_basis="zelfde aanpak",
                executor="UITVOERDER",
            )

            with self.assertRaises(WorkflowError) as context:
                record_attempt(
                    workspace,
                    TASK_ID,
                    error_code="input_error",
                    error_signature="zelfde-fout",
                    new_basis="zelfde aanpak",
                    executor="UITVOERDER",
                )
            self.assertEqual(context.exception.code, "task_attempt_unchanged")

    def test_blocked_task_requires_and_accepts_explicit_owner_termination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            begin(workspace)
            for number in range(1, 4):
                blocked = record_attempt(
                    workspace,
                    TASK_ID,
                    error_code="input_error",
                    error_signature="zelfde-fout",
                    new_basis=f"gewijzigde aanpak {number}",
                    executor="UITVOERDER",
                )
            self.assertEqual(blocked.task_status, "BLOCKED")

            cancelled = cancel_task(
                workspace,
                TASK_ID,
                reason="OWNER beëindigt de geblokkeerde taak",
                owner="OWNER",
            )
            self.assertEqual(cancelled.task_status, "CANCELLED")
            self.assertEqual(
                propose(workspace, "TASK-20260816-0002").task_status,
                "AWAITING_OWNER_APPROVAL",
            )

    def test_task_view_escapes_html_and_markdown_code_delimiters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            result = propose_task(
                workspace,
                TASK_ID,
                title="<script>alert(1)</script> `code`",
                goal="Veilig weergeven",
                definition_of_done="Geen actieve HTML",
                executor_role="ROLE-CONTROLEUR",
                input_paths=["CONTROL/ROADMAP.md"],
                allowed_actions=["Lees <alleen> lokaal"],
                forbidden_actions=["Geen `uitvoering`"],
                expected_output="Tekst",
                acceptance_criteria=["Veilig"],
                architect="ARCHITECT",
            )
            view = result.task_path.read_text(encoding="utf-8")
            self.assertNotIn("<script>", view)
            self.assertIn("&lt;script&gt;", view)
            self.assertIn("&#96;code&#96;", view)

    def test_only_one_non_terminal_task_and_owner_cancel_allows_next(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            propose(workspace)
            with self.assertRaises(WorkflowError) as context:
                propose(workspace, "TASK-20260816-0002")
            self.assertEqual(context.exception.code, "task_active_exists")

            cancelled = cancel_task(workspace, TASK_ID, reason="OWNER stopt de taak", owner="OWNER")
            self.assertEqual(cancelled.task_status, "CANCELLED")
            next_task = propose(workspace, "TASK-20260816-0002")
            self.assertEqual(next_task.task_status, "AWAITING_OWNER_APPROVAL")

    def test_owner_can_supersede_with_a_different_future_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            propose(workspace)
            result = supersede_task(
                workspace,
                TASK_ID,
                replacement_task_id="TASK-20260816-0002",
                reason="Nieuw voorstel vereist",
                owner="OWNER",
            )
            self.assertEqual(result.task_status, "SUPERSEDED")
            self.assertEqual(
                propose(workspace, "TASK-20260816-0002").task_status,
                "AWAITING_OWNER_APPROVAL",
            )

    def test_symlink_and_parent_escape_inputs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            outside = Path(temporary_directory)
            workspace = outside / "workspace"
            init_workspace(workspace)
            with self.assertRaises(WorkflowError) as parent_context:
                propose_task(
                    workspace,
                    TASK_ID,
                    title="Fout",
                    goal="Fout",
                    definition_of_done="Fout",
                    executor_role="ROL",
                    input_paths=["../secret.txt"],
                    allowed_actions=["lezen"],
                    forbidden_actions=["delen"],
                    expected_output="resultaat",
                    acceptance_criteria=["bewijs"],
                    architect="ARCHITECT",
                )
            self.assertEqual(parent_context.exception.code, "task_input_path_invalid")

            target = workspace / "CONTROL" / "ROADMAP.md"
            link = workspace / "CONTROL" / "LINK.md"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("Symlinks zijn niet beschikbaar in deze testomgeving")
            with self.assertRaises(WorkflowError) as link_context:
                propose_task(
                    workspace,
                    TASK_ID,
                    title="Fout",
                    goal="Fout",
                    definition_of_done="Fout",
                    executor_role="ROL",
                    input_paths=["CONTROL/LINK.md"],
                    allowed_actions=["lezen"],
                    forbidden_actions=["delen"],
                    expected_output="resultaat",
                    acceptance_criteria=["bewijs"],
                    architect="ARCHITECT",
                )
            self.assertEqual(link_context.exception.code, "task_input_unsafe")

    def test_cli_propose_and_exact_owner_approve_show_identity_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            proposed = run_cli(
                "workspace",
                "task",
                "propose",
                TASK_ID,
                "--title",
                "CLI-taak",
                "--goal",
                "CLI controleren",
                "--done",
                "CLI-resultaat",
                "--executor-role",
                "ROLE-CLI",
                "--input",
                "CONTROL/ROADMAP.md",
                "--allow",
                "lokaal lezen",
                "--forbid",
                "extern delen",
                "--expected-output",
                "lokaal bestand",
                "--acceptance",
                "digest klopt",
                "--architect",
                "ARCHITECT",
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )
            self.assertEqual(proposed.returncode, 0, proposed.stderr)
            self.assertIn("TASK_PROPOSED", proposed.stdout)
            self.assertIn("not cryptographic identity evidence", proposed.stdout)
            digest_match = re.search(r"Object digest: ([0-9a-f]{64})", proposed.stdout)
            self.assertIsNotNone(digest_match)

            approved = run_cli(
                "workspace",
                "task",
                "approve",
                TASK_ID,
                "--revision",
                "1",
                "--proposal-digest",
                digest_match.group(1),
                "--owner",
                "OWNER",
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertIn("TASK_APPROVED", approved.stdout)
            self.assertIn("APPROVED_FOR_EXECUTION", approved.stdout)

    def test_complete_cli_flow_reaches_closed_without_starting_an_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            outside = Path(temporary_directory)
            workspace = outside / "workspace"
            init_workspace(workspace)

            common_proposal = (
                "workspace",
                "task",
                "propose",
                TASK_ID,
                "--title",
                "Volledige CLI-taak",
                "--goal",
                "Controleer de CLI-flow",
                "--done",
                "Taak is exact gesloten",
                "--executor-role",
                "ROLE-CLI",
                "--input",
                "CONTROL/ROADMAP.md",
                "--allow",
                "lokaal lezen",
                "--forbid",
                "geen externe actie",
                "--expected-output",
                "één resultaat",
                "--acceptance",
                "digests zijn gelijk",
                "--architect",
                "ARCHITECT",
                "--root",
                str(workspace),
            )
            proposed = run_cli(*common_proposal, cwd=REPOSITORY_ROOT)
            proposal_digest = re.search(r"Object digest: ([0-9a-f]{64})", proposed.stdout).group(1)
            approved = run_cli(
                "workspace",
                "task",
                "approve",
                TASK_ID,
                "--revision",
                "1",
                "--proposal-digest",
                proposal_digest,
                "--owner",
                "OWNER",
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )
            begun = run_cli(
                "workspace",
                "task",
                "begin",
                TASK_ID,
                "--architect",
                "ARCHITECT",
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )
            result_file = outside / "cli-result.txt"
            evidence_file = outside / "cli-evidence.txt"
            result_file.write_text("resultaat", encoding="utf-8")
            evidence_file.write_text("bewijs", encoding="utf-8")
            submitted = run_cli(
                "workspace",
                "task",
                "submit-result",
                TASK_ID,
                "--result",
                str(result_file),
                "--evidence",
                str(evidence_file),
                "--limitation",
                "begrensde test",
                "--open-question",
                "geen",
                "--executor",
                "UITVOERDER",
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )
            result_digest = re.search(r"Object digest: ([0-9a-f]{64})", submitted.stdout).group(1)
            reviewed = run_cli(
                "workspace",
                "task",
                "review-result",
                TASK_ID,
                "--result-digest",
                result_digest,
                "--outcome",
                "PASS",
                "--finding",
                "resultaat en bewijs zijn gekoppeld",
                "--architect",
                "ARCHITECT",
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )
            review_digest = re.search(r"Object digest: ([0-9a-f]{64})", reviewed.stdout).group(1)
            accepted = run_cli(
                "workspace",
                "task",
                "accept-result",
                TASK_ID,
                "--result-digest",
                result_digest,
                "--review-digest",
                review_digest,
                "--decision",
                "ACCEPT",
                "--owner",
                "OWNER",
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )
            closed = run_cli(
                "workspace",
                "task",
                "close",
                TASK_ID,
                "--architect",
                "ARCHITECT",
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )
            status = run_cli(
                "workspace",
                "task",
                "status",
                TASK_ID,
                "--root",
                str(workspace),
                cwd=REPOSITORY_ROOT,
            )

            for completed in (
                proposed,
                approved,
                begun,
                submitted,
                reviewed,
                accepted,
                closed,
                status,
            ):
                self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("TASK_CLOSED", closed.stdout)
            self.assertIn("Task status: CLOSED", status.stdout)
            self.assertFalse((workspace / ".opencntx" / "agent").exists())


if __name__ == "__main__":
    unittest.main()
