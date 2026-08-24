from __future__ import annotations

import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.attempts import record_attempt
from opencntx.catalog import create_chapter, rebuild_catalog
from opencntx.integrity import (
    IntegrityError,
    _create_integrity_directory,
    _read_json,
    doctor_workspace,
    recover_workspace,
    safe_managed_path,
    state_digest,
    sync_directory,
    writer_transaction,
)
from opencntx.navigator import build_context_package
from opencntx.playbook import (
    RESERVED_AUTHORITY_ACTIONS,
    approve_playbook,
    approve_role,
    prepare_executor,
    register_playbook,
    register_role,
)
from opencntx.workflow import (
    approve_task,
    begin_task,
    propose_task,
    task_status,
)
from opencntx.workspace import capture_source, init_workspace

TASK_ID = "TASK-20260820-0001"
PLAYBOOK_ID = "PB-INTEGRITY-CHECK"
ROLE_ID = "ROLE-INTEGRITY-CHECKER"
ALLOWED_ACTIONS = ("inspect-source", "write-bounded-result")


def _result(queue, function) -> None:
    try:
        value = function()
        queue.put(("success", getattr(value, "status", "OK")))
    except BaseException as exc:
        queue.put(("error", getattr(exc, "code", type(exc).__name__)))


def _approval_worker(root, proposal_digest, barrier, queue) -> None:
    from opencntx import workflow

    workflow._TEST_BEFORE_TASK_LOCK = barrier.wait
    _result(
        queue,
        lambda: approve_task(
            Path(root),
            TASK_ID,
            revision=1,
            proposal_digest=proposal_digest,
            owner="OWNER",
        ),
    )


def _attempt_worker(root, executor_id, evidence, barrier, queue) -> None:
    from opencntx import workflow

    workflow._TEST_BEFORE_TASK_LOCK = barrier.wait
    _result(
        queue,
        lambda: record_attempt(
            Path(root),
            TASK_ID,
            executor_id=executor_id,
            action="inspect-source",
            command_type="inspect-file",
            target="CONTROL/ROADMAP.md",
            input_paths=["CONTROL/ROADMAP.md"],
            exit_status=2,
            error_class="invalid-input",
            actions_used=1,
            duration_ms=10,
            result_evidence_path=Path(evidence),
        ),
    )


def _capture_worker(root, source, barrier, queue) -> None:
    from opencntx import workspace

    workspace._TEST_BEFORE_CAPTURE_LOCK = barrier.wait
    _result(queue, lambda: capture_source(Path(root), Path(source), origin="OWNER"))


def _context_worker(root, proposal_digest, barrier, queue) -> None:
    from opencntx import navigator

    navigator._TEST_BEFORE_CONTEXT_LOCK = barrier.wait
    _result(
        queue,
        lambda: build_context_package(
            Path(root),
            TASK_ID,
            proposal_digest=proposal_digest,
            max_files=25,
            max_bytes=100_000,
        ),
    )


def _executor_worker(root, arguments, barrier, queue) -> None:
    from opencntx import playbook

    playbook._TEST_BEFORE_EXECUTOR_LOCK = barrier.wait
    _result(
        queue,
        lambda: prepare_executor(
            Path(root),
            TASK_ID,
            revision=1,
            proposal_digest=arguments["proposal_digest"],
            playbook_id=PLAYBOOK_ID,
            playbook_revision=1,
            playbook_digest=arguments["playbook_digest"],
            role_id=ROLE_ID,
            role_revision=1,
            role_digest=arguments["role_digest"],
            context_manifest_digest=arguments["context_manifest_digest"],
            executor="EXECUTOR-1",
        ),
    )


def _catalog_worker(root, barrier, queue) -> None:
    from opencntx import catalog

    catalog._TEST_BEFORE_CATALOG_LOCK = barrier.wait
    _result(queue, lambda: rebuild_catalog(Path(root)))


def _crash_capture_worker(root, source, phase) -> None:
    from opencntx import integrity

    def crash(_transaction_id: str, observed: str) -> None:
        if observed == phase:
            os._exit(91)

    integrity._TEST_FAULT_HOOK = crash
    capture_source(Path(root), Path(source), origin="OWNER")


def _install_crash_hook(phase: str, exit_code: int) -> None:
    from opencntx import integrity

    def crash(_transaction_id: str, observed: str) -> None:
        if observed == phase:
            os._exit(exit_code)

    integrity._TEST_FAULT_HOOK = crash


def _crash_approval_worker(root, proposal_digest, phase) -> None:
    _install_crash_hook(phase, 93)
    approve_task(
        Path(root),
        TASK_ID,
        revision=1,
        proposal_digest=proposal_digest,
        owner="OWNER",
    )


def _crash_catalog_worker(root, phase) -> None:
    _install_crash_hook(phase, 93)
    rebuild_catalog(Path(root))


def _crash_context_worker(root, proposal_digest, phase) -> None:
    _install_crash_hook(phase, 93)
    build_context_package(
        Path(root),
        TASK_ID,
        proposal_digest=proposal_digest,
        max_files=25,
        max_bytes=100_000,
    )


def _crash_executor_worker(root, arguments, phase) -> None:
    _install_crash_hook(phase, 93)
    prepare_executor(
        Path(root),
        TASK_ID,
        revision=1,
        proposal_digest=arguments["proposal_digest"],
        playbook_id=PLAYBOOK_ID,
        playbook_revision=1,
        playbook_digest=arguments["playbook_digest"],
        role_id=ROLE_ID,
        role_revision=1,
        role_digest=arguments["role_digest"],
        context_manifest_digest=arguments["context_manifest_digest"],
        executor="EXECUTOR-1",
    )


def _crash_transaction_worker(root, phase) -> None:
    from opencntx import integrity

    def crash(_transaction_id: str, observed: str) -> None:
        if observed == phase:
            os._exit(92)

    integrity._TEST_FAULT_HOOK = crash
    target = Path(root) / ".opencntx" / "phase-target.txt"
    with integrity.writer_transaction(Path(root), "phase-matrix") as transaction:
        transaction.track_target(target)
        target.write_text("new state\n", encoding="utf-8")
        transaction.mark_published()
        transaction.mark_receipted(None)


def _holding_writer(root, ready, release) -> None:
    from opencntx.integrity import writer_transaction

    with writer_transaction(Path(root), "test-active-writer"):
        ready.set()
        release.wait(20)


def _snapshot(root: Path) -> dict[str, tuple[str, int, int, bytes | None]]:
    result: dict[str, tuple[str, int, int, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        item = path.lstat()
        kind = "link" if path.is_symlink() else "directory" if path.is_dir() else "file"
        if kind == "file":
            try:
                content = path.read_bytes()
            except PermissionError:
                content = None
        else:
            content = None
        result[relative] = (kind, item.st_size, item.st_mtime_ns, content)
    return result


def _proposal(root: Path, *, role_id: str = ROLE_ID, extra_inputs=()):
    return propose_task(
        root,
        TASK_ID,
        title="Verify one bounded integrity route",
        goal="Verify only the exact approved local inputs.",
        definition_of_done="Result and evidence remain local and digest-bound.",
        executor_role=role_id,
        input_paths=[
            "CONTROL/OWNER.md",
            "CONTROL/ROADMAP.md",
            "CONTROL/CURRENT.md",
            *extra_inputs,
        ],
        allowed_actions=list(ALLOWED_ACTIONS),
        forbidden_actions=["external-send", "subdelegate"],
        expected_output="One bounded local result.",
        acceptance_criteria=["Every claim names exact evidence."],
        architect="ARCHITECT",
    )


def _run_pair(target, arguments) -> list[tuple[str, str]]:
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    queue = context.Queue()
    processes = [
        context.Process(target=target, args=(*arguments, barrier, queue)) for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(30)
        if process.is_alive():
            process.terminate()
            process.join(5)
            raise AssertionError("Writer process timed out.")
    results = [queue.get(timeout=5) for _ in processes]
    queue.close()
    return results


def _accepted_chapter(root: Path) -> str:
    source = root / "INBOX" / "source.txt"
    source.write_text("Exact bounded source.\n", encoding="utf-8")
    captured = capture_source(root, source, origin="OWNER")
    chapter = create_chapter(
        root,
        "CH-INTEGRITY",
        title="Integrity",
        scope="Exact bounded integrity source.",
        source_ids=[captured.source_id],
    )
    text = chapter.chapter_path.read_text(encoding="utf-8")
    text = text.replace('knowledge_status = "DRAFT"', 'knowledge_status = "OWNER_ACCEPTED"')
    text = text.replace('last_owner_approval = ""', 'last_owner_approval = "OWNER-INTEGRITY"')
    chapter.chapter_path.write_text(text, encoding="utf-8", newline="\n")
    rebuild_catalog(root)
    return chapter.chapter_path.relative_to(root).as_posix()


def _context_ready(root: Path):
    chapter_path = _accepted_chapter(root)
    current = root / "CONTROL" / "CURRENT.md"
    current.write_text(
        current.read_text(encoding="utf-8").replace(
            "- Active task: none", f"- Active task: {TASK_ID} revision 1"
        ),
        encoding="utf-8",
        newline="\n",
    )
    proposed = _proposal(root, extra_inputs=(chapter_path,))
    approve_task(root, TASK_ID, revision=1, proposal_digest=proposed.object_digest, owner="OWNER")
    begin_task(root, TASK_ID, architect="ARCHITECT")
    return proposed


def _executor_ready(root: Path):
    playbook = register_playbook(
        root,
        PLAYBOOK_ID,
        revision=1,
        title="Check integrity",
        purpose="Check only exact local evidence.",
        inputs=["One task-bound context package"],
        steps=["Verify every digest before reading."],
        stop_conditions=["Stop when any exact digest differs."],
        evidence_requirements=["Report the exact input digest."],
        allowed_actions=ALLOWED_ACTIONS,
        forbidden_actions=["external-send", "subdelegate"],
        architect="ARCHITECT",
    )
    role = register_role(
        root,
        ROLE_ID,
        revision=1,
        title="Integrity checker",
        responsibilities=["Check only assigned evidence."],
        allowed_actions=ALLOWED_ACTIONS,
        forbidden_actions=sorted(RESERVED_AUTHORITY_ACTIONS),
        handoff="Return result and evidence to the ARCHITECT.",
        architect="ARCHITECT",
    )
    approve_playbook(
        root,
        PLAYBOOK_ID,
        revision=1,
        definition_digest=playbook.definition_digest,
        owner="OWNER",
    )
    approve_role(
        root,
        ROLE_ID,
        revision=1,
        definition_digest=role.definition_digest,
        owner="OWNER",
    )
    rebuild_catalog(root)
    current = root / "CONTROL" / "CURRENT.md"
    current.write_text(
        current.read_text(encoding="utf-8").replace(
            "- Active task: none", f"- Active task: {TASK_ID} revision 1"
        ),
        encoding="utf-8",
        newline="\n",
    )
    proposed = _proposal(
        root,
        extra_inputs=(
            playbook.definition_path.relative_to(root).as_posix(),
            role.definition_path.relative_to(root).as_posix(),
        ),
    )
    approve_task(root, TASK_ID, revision=1, proposal_digest=proposed.object_digest, owner="OWNER")
    begin_task(root, TASK_ID, architect="ARCHITECT")
    context = build_context_package(
        root,
        TASK_ID,
        proposal_digest=proposed.object_digest,
        max_files=25,
        max_bytes=100_000,
    )
    return proposed, playbook, role, context


class IntegrityTests(unittest.TestCase):
    def _recover_crashed(self, root: Path) -> None:
        report = doctor_workspace(root)
        self.assertEqual(report.status, "RECOVERY_REQUIRED", report)
        issue = next(item for item in report.issues if item.transaction_id is not None)
        assert issue.transaction_id is not None
        assert issue.intent_sha256 is not None
        recover_workspace(root, issue.transaction_id, issue.intent_sha256, apply=True)
        self.assertEqual(doctor_workspace(root).status, "HEALTHY")

    def test_transaction_json_must_be_an_object(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "not-an-object.json"
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaises(IntegrityError) as context:
                _read_json(path, label="Transaction fixture")
            self.assertEqual("transaction_invalid", context.exception.code)

    def test_doctor_is_byte_type_name_and_mtime_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            before = _snapshot(root)
            report = doctor_workspace(root)
            after = _snapshot(root)
            self.assertEqual(report.status, "HEALTHY")
            self.assertEqual(before, after)
            self.assertFalse((root / ".opencntx" / "transactions").exists())

    def test_active_writer_is_reported_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            context = multiprocessing.get_context("spawn")
            ready = context.Event()
            release = context.Event()
            process = context.Process(target=_holding_writer, args=(root, ready, release))
            process.start()
            self.assertTrue(ready.wait(10))
            before = _snapshot(root)
            report = doctor_workspace(root)
            after = _snapshot(root)
            self.assertEqual(report.status, "ACTIVE")
            self.assertEqual(before, after)
            release.set()
            process.join(20)
            self.assertEqual(process.exitcode, 0)

    def test_crashed_capture_is_exactly_previewed_backed_up_and_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            source = root / "INBOX" / "crash.txt"
            source.write_text("crash publication\n", encoding="utf-8")
            context = multiprocessing.get_context("spawn")
            process = context.Process(
                target=_crash_capture_worker, args=(root, source, "PUBLISHED")
            )
            process.start()
            process.join(20)
            self.assertEqual(process.exitcode, 91)
            report = doctor_workspace(root)
            self.assertEqual(report.status, "RECOVERY_REQUIRED")
            issue = next(item for item in report.issues if item.transaction_id is not None)
            assert issue.transaction_id is not None
            assert issue.intent_sha256 is not None
            before = _snapshot(root)
            preview = recover_workspace(root, issue.transaction_id, issue.intent_sha256)
            self.assertEqual(preview.status, "RECOVERY_PREVIEW")
            self.assertEqual(before, _snapshot(root))
            applied = recover_workspace(root, issue.transaction_id, issue.intent_sha256, apply=True)
            self.assertEqual(applied.status, "RECOVERED")
            self.assertTrue(applied.backup_path.is_dir())
            self.assertTrue(applied.receipt_path and applied.receipt_path.is_file())
            self.assertEqual(list((root / "SOURCES").glob("*/*/SRC-*")), [])
            self.assertEqual(doctor_workspace(root).status, "HEALTHY")

    def test_recovery_rejects_wrong_exact_intent_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            source = root / "INBOX" / "crash.txt"
            source.write_text("crash publication\n", encoding="utf-8")
            context = multiprocessing.get_context("spawn")
            process = context.Process(
                target=_crash_capture_worker, args=(root, source, "PUBLISHED")
            )
            process.start()
            process.join(20)
            issue = next(
                item for item in doctor_workspace(root).issues if item.transaction_id is not None
            )
            assert issue.transaction_id is not None
            before = _snapshot(root)
            with self.assertRaisesRegex(IntegrityError, "does not match"):
                recover_workspace(root, issue.transaction_id, "0" * 64, apply=True)
            self.assertEqual(before, _snapshot(root))

    def test_recovery_rejects_target_drift_and_unknown_transaction_content(self) -> None:
        for mutation in ("target-drift", "unknown-content"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as temporary_directory,
            ):
                root = Path(temporary_directory) / "workspace"
                init_workspace(root)
                source = root / "INBOX" / "crash.txt"
                source.write_text("crash publication\n", encoding="utf-8")
                context = multiprocessing.get_context("spawn")
                process = context.Process(
                    target=_crash_capture_worker,
                    args=(root, source, "PUBLISHED"),
                )
                process.start()
                process.join(20)
                self.assertEqual(process.exitcode, 91)
                issue = next(
                    item
                    for item in doctor_workspace(root).issues
                    if item.transaction_id is not None
                )
                assert issue.transaction_id is not None
                active = root / ".opencntx" / "transactions" / "active" / issue.transaction_id
                if mutation == "target-drift":
                    captured = next((root / "SOURCES").glob("*/*/SRC-*"))
                    (captured / "content.bin").write_bytes(b"unexpected drift\n")
                else:
                    (active / "unknown.bin").write_bytes(b"unknown")
                before = _snapshot(root)
                report = doctor_workspace(root)
                self.assertEqual(report.status, "UNSAFE_UNKNOWN_STATE")
                with self.assertRaises(IntegrityError):
                    recover_workspace(
                        root, issue.transaction_id, issue.intent_sha256 or "", apply=True
                    )
                self.assertEqual(before, _snapshot(root))

    def test_active_writer_cannot_be_recovered_or_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            context = multiprocessing.get_context("spawn")
            ready = context.Event()
            release = context.Event()
            process = context.Process(target=_holding_writer, args=(root, ready, release))
            process.start()
            try:
                self.assertTrue(ready.wait(10))
                issue = next(
                    item
                    for item in doctor_workspace(root).issues
                    if item.transaction_id is not None
                )
                assert issue.transaction_id is not None
                assert issue.intent_sha256 is not None
                before = _snapshot(root)
                with self.assertRaisesRegex(IntegrityError, "active"):
                    recover_workspace(root, issue.transaction_id, issue.intent_sha256, apply=True)
                self.assertEqual(before, _snapshot(root))
                self.assertTrue(process.is_alive())
            finally:
                release.set()
                process.join(20)
            self.assertEqual(process.exitcode, 0)

    def test_recovery_manifest_receipt_and_second_apply_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            source = root / "INBOX" / "crash.txt"
            source.write_text("crash publication\n", encoding="utf-8")
            context = multiprocessing.get_context("spawn")
            process = context.Process(
                target=_crash_capture_worker, args=(root, source, "RECEIPTED")
            )
            process.start()
            process.join(20)
            self.assertEqual(process.exitcode, 91)
            issue = next(
                item for item in doctor_workspace(root).issues if item.transaction_id is not None
            )
            assert issue.transaction_id is not None
            assert issue.intent_sha256 is not None
            preview = recover_workspace(root, issue.transaction_id, issue.intent_sha256)
            applied = recover_workspace(root, issue.transaction_id, issue.intent_sha256, apply=True)
            self.assertEqual(applied.backup_path, preview.backup_path)
            manifest = json.loads(
                (applied.backup_path / "manifest.json").read_text(encoding="utf-8")
            )
            receipt = json.loads(applied.receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["intent_sha256"], issue.intent_sha256)
            self.assertTrue(receipt["before_targets"])
            self.assertTrue(receipt["after_targets"])
            before = _snapshot(root)
            with self.assertRaises(IntegrityError):
                recover_workspace(root, issue.transaction_id, issue.intent_sha256, apply=True)
            self.assertEqual(before, _snapshot(root))

    def test_every_transaction_phase_is_diagnosable_and_recoverable(self) -> None:
        phases = ("INTENT_DURABLE", "TARGET_TRACKED", "PUBLISHED", "RECEIPTED", "COMPLETED")
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory) / "workspace"
                init_workspace(root)
                target = root / ".opencntx" / "phase-target.txt"
                target.write_text("previous state\n", encoding="utf-8")
                context = multiprocessing.get_context("spawn")
                process = context.Process(target=_crash_transaction_worker, args=(root, phase))
                process.start()
                process.join(20)
                self.assertEqual(process.exitcode, 92)
                report = doctor_workspace(root)
                self.assertEqual(report.status, "RECOVERY_REQUIRED")
                issue = next(item for item in report.issues if item.transaction_id is not None)
                assert issue.transaction_id is not None
                assert issue.intent_sha256 is not None
                recover_workspace(root, issue.transaction_id, issue.intent_sha256, apply=True)
                self.assertEqual(target.read_text(encoding="utf-8"), "previous state\n")
                self.assertEqual(doctor_workspace(root).status, "HEALTHY")

    def test_each_multi_file_domain_recovers_an_intermediate_publication(self) -> None:
        context = multiprocessing.get_context("spawn")
        with self.subTest(domain="task"), tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            proposed = _proposal(root)
            process = context.Process(
                target=_crash_approval_worker,
                args=(root, proposed.object_digest, "TARGET_PUBLISHED"),
            )
            process.start()
            process.join(20)
            self.assertEqual(process.exitcode, 93)
            self._recover_crashed(root)
            self.assertEqual(task_status(root, TASK_ID).task_status, "AWAITING_OWNER_APPROVAL")

        with self.subTest(domain="catalog"), tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            _accepted_chapter(root)
            database = root / ".opencntx" / "catalog.sqlite"
            index = root / "CHAPTERS" / "INDEX.md"
            previous = (database.read_bytes(), index.read_bytes())
            process = context.Process(target=_crash_catalog_worker, args=(root, "TARGET_PUBLISHED"))
            process.start()
            process.join(20)
            self.assertEqual(process.exitcode, 93)
            self._recover_crashed(root)
            self.assertEqual((database.read_bytes(), index.read_bytes()), previous)

        with self.subTest(domain="context"), tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            proposed = _context_ready(root)
            process = context.Process(
                target=_crash_context_worker,
                args=(root, proposed.object_digest, "TARGET_PUBLISHED"),
            )
            process.start()
            process.join(20)
            self.assertEqual(process.exitcode, 93)
            self._recover_crashed(root)
            self.assertFalse((root / ".opencntx" / "latest").exists())

        with self.subTest(domain="executor"), tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            proposed, playbook, role, built = _executor_ready(root)
            arguments = {
                "proposal_digest": proposed.object_digest,
                "playbook_digest": playbook.definition_digest,
                "role_digest": role.definition_digest,
                "context_manifest_digest": built.manifest_digest,
            }
            process = context.Process(
                target=_crash_executor_worker,
                args=(root, arguments, "TARGET_PUBLISHED"),
            )
            process.start()
            process.join(20)
            self.assertEqual(process.exitcode, 93)
            self._recover_crashed(root)
            executor_root = root / ".opencntx" / "executors" / TASK_ID
            self.assertEqual(list(executor_root.glob("EXEC-*")), [])

    def test_two_exact_approvals_have_one_successful_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            proposed = _proposal(root)
            results = _run_pair(_approval_worker, (root, proposed.object_digest))
            self.assertEqual(sum(status == "success" for status, _ in results), 1, results)
            self.assertEqual(sum(status == "error" for status, _ in results), 1, results)

    def test_two_exact_attempts_have_one_successful_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            proposed, playbook, role, context = _executor_ready(root)
            prepared = prepare_executor(
                root,
                TASK_ID,
                revision=1,
                proposal_digest=proposed.object_digest,
                playbook_id=PLAYBOOK_ID,
                playbook_revision=1,
                playbook_digest=playbook.definition_digest,
                role_id=ROLE_ID,
                role_revision=1,
                role_digest=role.definition_digest,
                context_manifest_digest=context.manifest_digest,
                executor="EXECUTOR-1",
            )
            evidence = root / "INBOX" / "attempt-result.txt"
            evidence.write_text("same exact failed result\n", encoding="utf-8")
            results = _run_pair(
                _attempt_worker,
                (root, prepared.executor_id, evidence),
            )
            self.assertEqual(sum(status == "success" for status, _ in results), 1, results)
            self.assertEqual(sum(status == "error" for status, _ in results), 1, results)

    def test_two_exact_captures_have_one_successful_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            source = root / "INBOX" / "source.txt"
            source.write_text("same exact capture\n", encoding="utf-8")
            results = _run_pair(_capture_worker, (root, source))
            self.assertEqual(sum(status == "success" for status, _ in results), 1)
            self.assertEqual(sum(status == "error" for status, _ in results), 1)

    def test_two_exact_context_builds_have_one_successful_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            proposed = _context_ready(root)
            results = _run_pair(_context_worker, (root, proposed.object_digest))
            self.assertEqual(sum(status == "success" for status, _ in results), 1, results)
            self.assertEqual(sum(status == "error" for status, _ in results), 1, results)

    def test_two_exact_executor_preparations_have_one_successful_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            proposed, playbook, role, context = _executor_ready(root)
            arguments = {
                "proposal_digest": proposed.object_digest,
                "playbook_digest": playbook.definition_digest,
                "role_digest": role.definition_digest,
                "context_manifest_digest": context.manifest_digest,
            }
            results = _run_pair(_executor_worker, (root, arguments))
            self.assertEqual(sum(status == "success" for status, _ in results), 1)
            self.assertEqual(sum(status == "error" for status, _ in results), 1)

    def test_two_catalog_rebuilds_have_one_successful_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            _accepted_chapter(root)
            results = _run_pair(_catalog_worker, (root,))
            self.assertEqual(sum(status == "success" for status, _ in results), 1)
            self.assertEqual(sum(status == "error" for status, _ in results), 1)

    def test_stale_expected_digest_fails_after_the_first_writer_releases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            target = root / ".opencntx" / "cas-target.txt"
            expected = state_digest((target,))
            with writer_transaction(
                root,
                "cas-first",
                expected_digest=expected,
                current_digest=lambda: state_digest((target,)),
            ) as transaction:
                transaction.track_target(target)
                target.write_text("new state\n", encoding="utf-8")
                transaction.mark_target_published(target)
                transaction.mark_published()
                transaction.mark_receipted(None)
            with (
                self.assertRaisesRegex(IntegrityError, "basis changed") as error,
                writer_transaction(
                    root,
                    "cas-stale",
                    expected_digest=expected,
                    current_digest=lambda: state_digest((target,)),
                ),
            ):
                self.fail("A stale writer must never enter its mutation body.")
            self.assertEqual(error.exception.code, "transaction_state_changed")

    def test_path_safety_and_directory_sync_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            init_workspace(root)
            directory_sync = sync_directory(root)
            print(f"PLATFORM_DIRECTORY_SYNC={directory_sync}")
            self.assertIn(directory_sync, {"SYNCED", "UNSUPPORTED"})
            with self.assertRaisesRegex(IntegrityError, "exact relative"):
                safe_managed_path(root, "../outside")
            target = root / "CONTROL" / "OWNER.md"
            link = root / "INBOX" / "owner-link"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("Symlink creation is unavailable on this platform.")
            with self.assertRaisesRegex(IntegrityError, "link or reparse"):
                safe_managed_path(root, "INBOX/owner-link", must_exist=True)

    def test_integrity_directory_creation_preserves_platform_contract(self) -> None:
        directory = Path("synthetic-integrity-directory")
        resolved = Path("synthetic-integrity-directory-resolved")
        scan = mock.MagicMock()
        scan.__enter__.return_value = iter(())
        with (
            mock.patch.object(Path, "mkdir") as mkdir,
            mock.patch.object(Path, "resolve", return_value=resolved),
            mock.patch.object(Path, "is_dir", return_value=True),
            mock.patch("opencntx.integrity.os.scandir", return_value=scan),
            mock.patch("opencntx.integrity.os.name", "nt"),
        ):
            _create_integrity_directory(directory)
        mkdir.assert_called_once_with()

        scan = mock.MagicMock()
        scan.__enter__.return_value = iter(())
        with (
            mock.patch.object(Path, "mkdir") as mkdir,
            mock.patch.object(Path, "resolve", return_value=resolved),
            mock.patch.object(Path, "is_dir", return_value=True),
            mock.patch("opencntx.integrity.os.scandir", return_value=scan),
            mock.patch("opencntx.integrity.os.name", "posix"),
        ):
            _create_integrity_directory(directory)
        mkdir.assert_called_once_with(mode=0o700)

    def test_state_digest_normalizes_inaccessible_paths(self) -> None:
        with (
            mock.patch(
                "opencntx.integrity._path_digest",
                side_effect=PermissionError(5, "Access is denied"),
            ),
            self.assertRaisesRegex(IntegrityError, "state path is inaccessible") as error,
        ):
            state_digest((Path("inaccessible"),))
        self.assertEqual(error.exception.code, "managed_path_unsafe")

    def test_directory_sync_capability_matrix_is_explicit(self) -> None:
        path = Path("capability-test")
        with (
            mock.patch("opencntx.integrity.os.name", "posix"),
            mock.patch("opencntx.integrity.os.open", return_value=17),
            mock.patch("opencntx.integrity.os.fsync"),
            mock.patch("opencntx.integrity.os.close"),
        ):
            self.assertEqual(sync_directory(path), "SYNCED")
        with (
            mock.patch("opencntx.integrity.os.name", "posix"),
            mock.patch("opencntx.integrity.os.open", side_effect=NotImplementedError),
        ):
            self.assertEqual(sync_directory(path), "UNSUPPORTED")
        with (
            mock.patch("opencntx.integrity.os.name", "posix"),
            mock.patch("opencntx.integrity.os.open", side_effect=OSError),
        ):
            self.assertEqual(sync_directory(path), "FAILED")


if __name__ == "__main__":
    unittest.main()
