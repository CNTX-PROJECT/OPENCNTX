from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
import sys

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from opencntx import integrity
from opencntx.attempts import (
    MAX_TOTAL_ATTEMPTS,
    AttemptError,
    basis_digest,
    fingerprint,
    record_attempt,
)
from opencntx.playbook import executor_status
from opencntx.workflow import (
    WorkflowError,
    _load_chain,
    supersede_task,
    task_status,
)
from tests.test_playbook import (
    TASK_ID,
    append_legacy_attempt,
    prepare_ready_executor,
    run_cli,
    snapshot,
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def ready(parent: Path):
    workspace, _playbook, _role, _proposed, _context, prepared = prepare_ready_executor(parent)
    basis = workspace / "SOURCES" / "attempt-basis.txt"
    basis.write_text("initial attempt basis\n", encoding="utf-8")
    return workspace, prepared, basis


def append_attempt(
    parent: Path,
    workspace: Path,
    executor_id: str,
    basis: Path,
    number: int,
    *,
    error_class: str = "invalid-input",
    actions_used: int = 1,
    duration_ms: int = 10,
    new_evidence: bytes | None = None,
    action: str = "inspect-source",
    result_text: str | None = None,
):
    result = parent / f"attempt-result-{number}.txt"
    result.write_text(
        result_text or f"failed attempt wording {number}\n",
        encoding="utf-8",
    )
    new_path = None
    if new_evidence is not None:
        new_path = parent / f"new-evidence-{number}.bin"
        new_path.write_bytes(new_evidence)
    return record_attempt(
        workspace,
        TASK_ID,
        executor_id=executor_id,
        action=action,
        command_type="inspect-file",
        target="SOURCES/attempt-basis.txt",
        input_paths=[basis.relative_to(workspace).as_posix()],
        exit_status=2,
        error_class=error_class,
        actions_used=actions_used,
        duration_ms=duration_ms,
        result_evidence_path=result,
        new_evidence_path=new_path,
    )


class ObjectiveAttemptTests(unittest.TestCase):
    def test_fingerprint_is_canonical_and_uses_only_the_five_fact_classes(self) -> None:
        inputs = [
            {"path": "SOURCES/b.txt", "bytes": 1, "sha256": "b" * 64},
            {"path": "SOURCES/a.txt", "bytes": 1, "sha256": "a" * 64},
        ]
        expected = fingerprint(
            command_type="inspect-file",
            target="SOURCES/a.txt",
            inputs=inputs,
            exit_status=2,
            error_class="invalid-input",
        )
        self.assertEqual(
            expected,
            "281d90a9ccc2b26ce7fa1b9206e9e96f5f65456142ca45154e10d28b2bc619f6",
        )
        self.assertEqual(
            basis_digest(inputs),
            "c20812cd12b67a96df314ffab69914ab2f84e54e94a4a6c8be71d18522a6b4b5",
        )
        self.assertEqual(basis_digest(inputs), basis_digest(list(reversed(inputs))))
        self.assertEqual(
            expected,
            fingerprint(
                command_type="inspect-file",
                target="SOURCES/a.txt",
                inputs=list(reversed(inputs)),
                exit_status=2,
                error_class="invalid-input",
            ),
        )
        variants = (
            {"command_type": "read-file"},
            {"target": "SOURCES/b.txt"},
            {"inputs": [{"path": "SOURCES/a.txt", "bytes": 1, "sha256": "c" * 64}]},
            {"exit_status": 1},
            {"error_class": "tool-failure"},
        )
        base = {
            "command_type": "inspect-file",
            "target": "SOURCES/a.txt",
            "inputs": inputs,
            "exit_status": 2,
            "error_class": "invalid-input",
        }
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(expected, fingerprint(**(base | variant)))

    def test_three_semantically_equal_failures_with_different_wording_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            first = append_attempt(
                parent,
                workspace,
                prepared.executor_id,
                basis,
                1,
                result_text="first human wording\n",
            )
            self.assertEqual(first.task_status, "IN_EXECUTION")
            self.assertEqual(
                executor_status(workspace, TASK_ID, prepared.executor_id).status,
                "READY",
            )
            second = append_attempt(
                parent,
                workspace,
                prepared.executor_id,
                basis,
                2,
                new_evidence=b"new observation two\n",
                result_text="completely different wording\n",
            )
            third = append_attempt(
                parent,
                workspace,
                prepared.executor_id,
                basis,
                3,
                new_evidence=b"new observation three\n",
                result_text="third description of the same failure\n",
            )
            self.assertEqual(second.task_status, "IN_EXECUTION")
            self.assertEqual(third.task_status, "BLOCKED")
            self.assertEqual(
                executor_status(workspace, TASK_ID, prepared.executor_id).status,
                "TASK_FINISHED",
            )
            chain = _load_chain(workspace, TASK_ID)
            attempts = [
                event.payload for event in chain.events if event.event_type == "objective-attempt"
            ]
            self.assertEqual(len({item["error_fingerprint"] for item in attempts}), 1)
            self.assertEqual(attempts[-1]["block_reason"], "SEMANTIC_REPEAT_LIMIT")
            view = third.task_path.read_text(encoding="utf-8")
            self.assertIn("Primary block reason: `SEMANTIC_REPEAT_LIMIT`", view)
            self.assertNotIn("third description", view)

    def test_equal_fingerprints_are_counted_across_an_alternating_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            classes = ("invalid-input", "timeout", "invalid-input", "conflict", "invalid-input")
            result = None
            for number, error_class in enumerate(classes, start=1):
                result = append_attempt(
                    parent,
                    workspace,
                    prepared.executor_id,
                    basis,
                    number,
                    error_class=error_class,
                    new_evidence=(None if number == 1 else f"basis {number}".encode()),
                )
            assert result is not None
            self.assertEqual(result.task_status, "BLOCKED")
            latest = _load_chain(workspace, TASK_ID).events[-1].payload
            self.assertEqual(latest["block_reason"], "SEMANTIC_REPEAT_LIMIT")
            self.assertIn("TOTAL_ATTEMPT_LIMIT", latest["reached_limits"])

    def test_alternating_errors_reach_the_total_attempt_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            classes = (
                "invalid-input",
                "timeout",
                "conflict",
                "tool-failure",
                "dependency-failure",
            )
            result = None
            for number, error_class in enumerate(classes, start=1):
                result = append_attempt(
                    parent,
                    workspace,
                    prepared.executor_id,
                    basis,
                    number,
                    error_class=error_class,
                    new_evidence=(None if number == 1 else f"new {number}".encode()),
                )
            assert result is not None
            self.assertEqual(result.task_status, "BLOCKED")
            latest = _load_chain(workspace, TASK_ID).events[-1].payload
            self.assertEqual(latest["cumulative_attempts"], MAX_TOTAL_ATTEMPTS)
            self.assertEqual(latest["block_reason"], "TOTAL_ATTEMPT_LIMIT")

    def test_action_and_time_budgets_are_cumulative_and_deterministic(self) -> None:
        cases = (
            ("actions", 10, 0, 15, 0, "CUMULATIVE_ACTION_LIMIT"),
            (
                "time",
                1,
                900_000,
                1,
                900_000,
                "CUMULATIVE_TIME_LIMIT",
            ),
        )
        for label, actions_one, time_one, actions_two, time_two, reason in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary_directory:
                parent = Path(temporary_directory)
                workspace, prepared, basis = ready(parent)
                append_attempt(
                    parent,
                    workspace,
                    prepared.executor_id,
                    basis,
                    1,
                    actions_used=actions_one,
                    duration_ms=time_one,
                )
                blocked = append_attempt(
                    parent,
                    workspace,
                    prepared.executor_id,
                    basis,
                    2,
                    error_class="timeout",
                    actions_used=actions_two,
                    duration_ms=time_two,
                    new_evidence=b"unique second observation",
                )
                self.assertEqual(blocked.task_status, "BLOCKED")
                self.assertEqual(
                    _load_chain(workspace, TASK_ID).events[-1].payload["block_reason"], reason
                )

    def test_changed_input_digest_is_a_valid_new_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            basis.write_text("genuinely changed basis bytes\n", encoding="utf-8")
            second = append_attempt(
                parent,
                workspace,
                prepared.executor_id,
                basis,
                2,
                error_class="timeout",
            )
            self.assertEqual(second.task_status, "IN_EXECUTION")
            self.assertEqual(
                _load_chain(workspace, TASK_ID).events[-1].payload["basis_status"],
                "INPUT_DIGEST_CHANGED",
            )

    def test_unchanged_inputs_and_result_wording_are_not_a_new_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            before_events = list((workspace / "TASKS" / TASK_ID / "events").iterdir())
            before_artifacts = list((workspace / "TASKS" / TASK_ID / "artifacts").iterdir())
            with self.assertRaises(WorkflowError) as context:
                append_attempt(
                    parent,
                    workspace,
                    prepared.executor_id,
                    basis,
                    2,
                    error_class="timeout",
                    result_text="cosmetically different result evidence\n",
                )
            self.assertEqual(context.exception.code, "task_attempt_unchanged")
            self.assertEqual(
                list((workspace / "TASKS" / TASK_ID / "events").iterdir()), before_events
            )
            self.assertEqual(
                list((workspace / "TASKS" / TASK_ID / "artifacts").iterdir()), before_artifacts
            )

    def test_duplicate_explicit_new_evidence_is_not_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            append_attempt(
                parent,
                workspace,
                prepared.executor_id,
                basis,
                2,
                error_class="timeout",
                new_evidence=b"same evidence bytes",
            )
            with self.assertRaises(WorkflowError) as context:
                append_attempt(
                    parent,
                    workspace,
                    prepared.executor_id,
                    basis,
                    3,
                    error_class="conflict",
                    new_evidence=b"same evidence bytes",
                )
            self.assertEqual(context.exception.code, "task_attempt_unchanged")

    def test_executor_context_action_and_actor_bindings_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            with self.assertRaises(WorkflowError):
                append_attempt(
                    parent,
                    workspace,
                    "EXEC-20260820-000000000000",
                    basis,
                    1,
                )
            with self.assertRaises(WorkflowError) as action_error:
                append_attempt(
                    parent,
                    workspace,
                    prepared.executor_id,
                    basis,
                    1,
                    action="external-send",
                )
            self.assertEqual(action_error.exception.code, "executor_action_out_of_scope")
            result = append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            event = _load_chain(workspace, TASK_ID).events[-1]
            self.assertEqual(event.actor_id, "UITVOERDER-1")
            self.assertEqual(event.payload["executor_id"], prepared.executor_id)
            self.assertRegex(event.payload["context_manifest_digest"], r"[0-9a-f]{64}\Z")
            self.assertIn(
                "Actor ID is a local statement, not cryptographic identity evidence.",
                run_cli(
                    "workspace",
                    "task",
                    "status",
                    TASK_ID,
                    "--root",
                    str(workspace),
                    cwd=parent,
                ).stdout,
            )
            self.assertEqual(result.task_status, "IN_EXECUTION")

    def test_context_drift_blocks_attempt_before_artifact_or_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            context_path = workspace / ".opencntx" / "latest" / "CONTEXT.md"
            context_path.write_bytes(context_path.read_bytes() + b"drift\n")
            with self.assertRaises(WorkflowError) as context:
                append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            self.assertIn(
                context.exception.code, {"executor_context_stale", "executor_context_invalid"}
            )
            self.assertEqual(list((workspace / "TASKS" / TASK_ID / "artifacts").iterdir()), [])

    def test_status_is_read_only_and_artifact_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            before = snapshot(workspace)
            status = task_status(workspace, TASK_ID)
            self.assertEqual(status.task_status, "IN_EXECUTION")
            self.assertEqual(snapshot(workspace), before)
            artifact = workspace / "TASKS" / TASK_ID / "artifacts" / "attempt-0001-result.bin"
            artifact.write_bytes(b"tampered evidence\n")
            with self.assertRaises(WorkflowError) as context:
                task_status(workspace, TASK_ID)
            self.assertEqual(context.exception.code, "task_artifact_stale")

    def test_failed_transaction_rolls_attempt_artifact_and_event_back_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)

            def fail_after_first_publish(_transaction_id: str, phase: str) -> None:
                if phase == "TARGET_PUBLISHED":
                    raise RuntimeError("forced attempt publication failure")

            with (
                mock.patch.object(
                    integrity,
                    "_TEST_FAULT_HOOK",
                    side_effect=fail_after_first_publish,
                ),
                self.assertRaisesRegex(RuntimeError, "forced attempt"),
            ):
                append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            chain = _load_chain(workspace, TASK_ID)
            self.assertFalse(any(event.event_type == "objective-attempt" for event in chain.events))
            self.assertEqual(list((workspace / "TASKS" / TASK_ID / "artifacts").iterdir()), [])

    def test_recomputed_event_digest_cannot_hide_fingerprint_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            event_path = workspace / "TASKS" / TASK_ID / "events" / "0004-objective-attempt.json"
            value = json.loads(event_path.read_text(encoding="utf-8"))
            value["payload"]["error_fingerprint"] = "0" * 64
            value["object_digest"] = hashlib.sha256(_canonical(value["payload"])).hexdigest()
            without_record = {key: item for key, item in value.items() if key != "record_digest"}
            value["record_digest"] = hashlib.sha256(_canonical(without_record)).hexdigest()
            event_path.write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(WorkflowError) as context:
                _load_chain(workspace, TASK_ID)
            self.assertEqual(context.exception.code, "task_binding_invalid")

    def test_legacy_attempts_remain_readable_but_cannot_be_mixed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            append_legacy_attempt(workspace, 1)
            self.assertEqual(task_status(workspace, TASK_ID).task_status, "IN_EXECUTION")
            with self.assertRaises(WorkflowError) as context:
                append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            self.assertEqual(context.exception.code, "task_attempt_legacy_chain")

    def test_blocked_task_has_no_retry_and_owner_may_supersede_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            append_attempt(parent, workspace, prepared.executor_id, basis, 1)
            append_attempt(
                parent,
                workspace,
                prepared.executor_id,
                basis,
                2,
                new_evidence=b"second",
            )
            append_attempt(
                parent,
                workspace,
                prepared.executor_id,
                basis,
                3,
                new_evidence=b"third",
            )
            with self.assertRaises(WorkflowError):
                append_attempt(
                    parent,
                    workspace,
                    prepared.executor_id,
                    basis,
                    4,
                    new_evidence=b"fourth",
                )
            superseded = supersede_task(
                workspace,
                TASK_ID,
                replacement_task_id="TASK-20260820-9999",
                reason="OWNER requires one explicit new task",
                owner="OWNER",
            )
            self.assertEqual(superseded.task_status, "SUPERSEDED")

    def test_invalid_budget_types_and_unknown_error_classes_fail_closed(self) -> None:
        records = [{"path": "SOURCES/a.txt", "bytes": 1, "sha256": "a" * 64}]
        with self.assertRaises(AttemptError):
            fingerprint(
                command_type="inspect-file",
                target="SOURCES/a.txt",
                inputs=records,
                exit_status=True,
                error_class="invalid-input",
            )
        with self.assertRaises(AttemptError):
            fingerprint(
                command_type="inspect-file",
                target="SOURCES/a.txt",
                inputs=records,
                exit_status=2,
                error_class="invented-class",
            )
        with self.assertRaises(AttemptError):
            fingerprint(
                command_type="inspect-file",
                target="../outside.txt",
                inputs=records,
                exit_status=2,
                error_class="invalid-input",
            )
        with self.assertRaises(AttemptError):
            fingerprint(
                command_type="inspect-file",
                target="SOURCES/a.txt",
                inputs=[records[0], records[0]],
                exit_status=2,
                error_class="invalid-input",
            )

    def test_non_file_and_symlink_evidence_fail_before_task_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            before_events = list((workspace / "TASKS" / TASK_ID / "events").iterdir())
            with self.assertRaises(WorkflowError):
                record_attempt(
                    workspace,
                    TASK_ID,
                    executor_id=prepared.executor_id,
                    action="inspect-source",
                    command_type="inspect-file",
                    target="SOURCES/attempt-basis.txt",
                    input_paths=[basis.relative_to(workspace).as_posix()],
                    exit_status=2,
                    error_class="invalid-input",
                    actions_used=1,
                    duration_ms=10,
                    result_evidence_path=parent,
                )
            link = parent / "result-link.txt"
            target = parent / "result-target.txt"
            target.write_text("evidence\n", encoding="utf-8")
            try:
                link.symlink_to(target)
            except OSError:
                pass
            else:
                with self.assertRaises(WorkflowError) as context:
                    record_attempt(
                        workspace,
                        TASK_ID,
                        executor_id=prepared.executor_id,
                        action="inspect-source",
                        command_type="inspect-file",
                        target="SOURCES/attempt-basis.txt",
                        input_paths=[basis.relative_to(workspace).as_posix()],
                        exit_status=2,
                        error_class="invalid-input",
                        actions_used=1,
                        duration_ms=10,
                        result_evidence_path=link,
                    )
                self.assertEqual(context.exception.code, "task_artifact_unsafe")
            self.assertEqual(
                list((workspace / "TASKS" / TASK_ID / "events").iterdir()),
                before_events,
            )
            self.assertEqual(list((workspace / "TASKS" / TASK_ID / "artifacts").iterdir()), [])

    def test_cli_records_exact_objective_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, prepared, basis = ready(parent)
            result = parent / "cli-result.txt"
            result.write_text("bounded CLI failure evidence\n", encoding="utf-8")
            completed = run_cli(
                "workspace",
                "task",
                "record-attempt",
                TASK_ID,
                "--executor-id",
                prepared.executor_id,
                "--action",
                "inspect-source",
                "--command-type",
                "inspect-file",
                "--target",
                "SOURCES/attempt-basis.txt",
                "--input",
                basis.relative_to(workspace).as_posix(),
                "--exit-status",
                "2",
                "--error-class",
                "invalid-input",
                "--actions-used",
                "1",
                "--duration-ms",
                "10",
                "--result-evidence",
                str(result),
                "--root",
                str(workspace),
                cwd=parent,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("TASK_ATTEMPT_RECORDED", completed.stdout)
            self.assertIn("not cryptographic identity evidence", completed.stdout)
            help_result = run_cli(
                "workspace",
                "task",
                "record-attempt",
                "--help",
                cwd=parent,
            )
            self.assertEqual(help_result.returncode, 0)
            self.assertNotIn("--error-signature", help_result.stdout)
            self.assertNotIn("--new-basis", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
