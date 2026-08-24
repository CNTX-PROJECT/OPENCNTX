from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.catalog import rebuild_catalog
from opencntx.navigator import build_context_package
from opencntx.playbook import (
    DATA_AUTHORITY_STATEMENT,
    LEGACY_OWNER_AUTHORITY_STATEMENT,
    LEGACY_PLAYBOOK_HANDOFF,
    OWNER_AUTHORITY_STATEMENT,
    RESERVED_AUTHORITY_ACTIONS,
    PlaybookError,
    _json_bytes,
    _render_playbook,
    _render_role,
    approve_playbook,
    approve_role,
    executor_status,
    playbook_status,
    prepare_executor,
    register_playbook,
    register_role,
    verify_executor,
    verify_playbook,
    verify_role,
)
from opencntx.workflow import (
    _append_event,
    _load_chain,
    approve_task,
    begin_task,
    propose_task,
    submit_result,
)
from opencntx.workspace import init_workspace

TASK_ID = "TASK-20260817-0001"
PLAYBOOK_ID = "PB-BRON-CONTROLE"
ROLE_ID = "ROLE-BRON-REVIEWER"
ALLOWED_ACTIONS = ("inspect-source", "write-bounded-result")


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


def register_definitions(workspace: Path, *, approve: bool = True):
    playbook = register_playbook(
        workspace,
        PLAYBOOK_ID,
        revision=1,
        title="Controleer één bron",
        purpose="Controleer uitsluitend de toegewezen bron.",
        inputs=["Eén taakgebonden contextpakket"],
        steps=[
            "Controleer eerst alle digests.",
            "Rapporteer feiten, aannames en onbekenden afzonderlijk.",
        ],
        stop_conditions=["Stop bij ontbrekende of gewijzigde bronbytes."],
        evidence_requirements=["Exacte bron-ID, versie en SHA-256."],
        allowed_actions=ALLOWED_ACTIONS,
        forbidden_actions=["external-send", "subdelegate"],
        architect="ARCHITECT",
    )
    role = register_role(
        workspace,
        ROLE_ID,
        revision=1,
        title="Begrensde bronreviewer",
        responsibilities=["Controleer uitsluitend de toegewezen bron."],
        allowed_actions=ALLOWED_ACTIONS,
        forbidden_actions=sorted(RESERVED_AUTHORITY_ACTIONS),
        handoff="Lever resultaat en bewijs terug aan de ARCHITECT.",
        architect="ARCHITECT",
    )
    if approve:
        approve_playbook(
            workspace,
            PLAYBOOK_ID,
            revision=1,
            definition_digest=playbook.definition_digest,
            owner="OWNER",
        )
        approve_role(
            workspace,
            ROLE_ID,
            revision=1,
            definition_digest=role.definition_digest,
            owner="OWNER",
        )
    return playbook, role


def set_current(workspace: Path, task_id: str = TASK_ID) -> None:
    path = workspace / "CONTROL" / "CURRENT.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("- Active task: none", f"- Active task: {task_id} revision 1")
    path.write_text(text, encoding="utf-8", newline="\n")


def start_execution(parent: Path, *, approve_definitions: bool = True):
    workspace = parent / "workspace"
    init_workspace(workspace)
    playbook, role = register_definitions(workspace, approve=approve_definitions)
    rebuild_catalog(workspace)
    set_current(workspace)
    inputs = [
        "CONTROL/OWNER.md",
        "CONTROL/ROADMAP.md",
        "CONTROL/CURRENT.md",
        playbook.definition_path.relative_to(workspace).as_posix(),
        role.definition_path.relative_to(workspace).as_posix(),
    ]
    proposed = propose_task(
        workspace,
        TASK_ID,
        title="Controleer begrensde projectcontext",
        goal="Controleer uitsluitend de goedgekeurde projectcontext.",
        definition_of_done="Resultaat verwijst naar alle gebruikte bronnen.",
        executor_role=ROLE_ID,
        input_paths=inputs,
        allowed_actions=ALLOWED_ACTIONS,
        forbidden_actions=["external-send", "subdelegate"],
        expected_output="Eén lokaal resultaat met bewijs.",
        acceptance_criteria=["Iedere claim verwijst naar een gepinde bron."],
        architect="ARCHITECT",
    )
    approve_task(
        workspace,
        TASK_ID,
        revision=1,
        proposal_digest=proposed.object_digest,
        owner="OWNER",
    )
    begin_task(workspace, TASK_ID, architect="ARCHITECT")
    context = build_context_package(
        workspace,
        TASK_ID,
        proposal_digest=proposed.object_digest,
        max_files=25,
        max_bytes=100_000,
    )
    return workspace, playbook, role, proposed, context


def prepare_ready_executor(parent: Path):
    workspace, playbook, role, proposed, context = start_execution(parent)
    prepared = prepare_executor(
        workspace,
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
        executor="UITVOERDER-1",
    )
    return workspace, playbook, role, proposed, context, prepared


def snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


def append_legacy_attempt(workspace: Path, number: int):
    """Append historical text-attempt evidence for one compatibility boundary."""
    chain = _load_chain(workspace, TASK_ID)
    blocked = number >= 3
    return _append_event(
        workspace,
        chain,
        event_type="attempt",
        to_status="BLOCKED" if blocked else "IN_EXECUTION",
        actor_id="UITVOERDER-1",
        payload={
            "proposal_digest": chain.proposal_digest,
            "attempt_number": number,
            "error_code": "zelfde_fout",
            "error_signature": "zelfde blokkade",
            "new_basis": f"nieuwe basis {number}",
        },
        success_status="TASK_BLOCKED" if blocked else "TASK_ATTEMPT_RECORDED",
    )


class PlaybookTests(unittest.TestCase):
    def test_exact_legacy_definition_documents_remain_verifiable_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            playbook, role = register_definitions(workspace, approve=False)

            fixtures = (
                (playbook.definition_path, _render_playbook, "handoff", LEGACY_PLAYBOOK_HANDOFF),
                (
                    role.definition_path,
                    _render_role,
                    "owner_authority",
                    LEGACY_OWNER_AUTHORITY_STATEMENT,
                ),
            )
            before: dict[Path, tuple[bytes, bytes]] = {}
            for document_path, renderer, field, legacy_value in fixtures:
                record_path = document_path.parent / "record.json"
                record = json.loads(record_path.read_text(encoding="utf-8"))
                record[field] = legacy_value
                document = renderer(record, legacy=True)
                record["document"] = {
                    "bytes": len(document),
                    "path": document_path.name,
                    "sha256": hashlib.sha256(document).hexdigest(),
                }
                document_path.write_bytes(document)
                record_path.write_bytes(_json_bytes(record))
                before[document_path] = (document_path.read_bytes(), record_path.read_bytes())

            self.assertTrue(verify_playbook(workspace, PLAYBOOK_ID, 1).ok)
            self.assertTrue(verify_role(workspace, ROLE_ID, 1).ok)
            for document_path, expected in before.items():
                self.assertEqual(
                    (
                        document_path.read_bytes(),
                        (document_path.parent / "record.json").read_bytes(),
                    ),
                    expected,
                )

    def test_mixed_current_record_and_legacy_document_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            playbook = register_definitions(workspace, approve=False)[0]
            record_path = playbook.definition_path.parent / "record.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            document = _render_playbook(record, legacy=True)
            record["document"] = {
                "bytes": len(document),
                "path": playbook.definition_path.name,
                "sha256": hashlib.sha256(document).hexdigest(),
            }
            playbook.definition_path.write_bytes(document)
            record_path.write_bytes(_json_bytes(record))

            report = verify_playbook(workspace, PLAYBOOK_ID, 1)

            self.assertFalse(report.ok)
            self.assertEqual(report.status, "STALE")

    def test_playbook_registration_is_proposed_immutable_and_human_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)

            result = register_playbook(
                workspace,
                PLAYBOOK_ID,
                revision=1,
                title="Controleer bron",
                purpose="Controleer één bron.",
                inputs=["Eén contextpakket"],
                steps=["Controleer de digest."],
                stop_conditions=["Stop bij drift."],
                evidence_requirements=["Bewaar de SHA-256."],
                allowed_actions=["inspect-source"],
                forbidden_actions=["external-send"],
                architect="ARCHITECT",
            )

            self.assertEqual(result.status, "DEFINITION_PROPOSED")
            self.assertRegex(result.definition_digest, r"[0-9a-f]{64}\Z")
            self.assertEqual(playbook_status(workspace, PLAYBOOK_ID, 1).status, "PROPOSED")
            self.assertTrue(verify_playbook(workspace, PLAYBOOK_ID, 1).ok)
            text = result.definition_path.read_text(encoding="utf-8")
            self.assertIn("non-executing playbook", text)
            self.assertIn("`inspect-source`", text)
            self.assertFalse((result.definition_path.parent / "approval.json").exists())
            with self.assertRaises(PlaybookError):
                register_playbook(
                    workspace,
                    PLAYBOOK_ID,
                    revision=1,
                    title="Anders",
                    purpose="Anders.",
                    inputs=["Input"],
                    steps=["Stap"],
                    stop_conditions=["Stop"],
                    evidence_requirements=["Bewijs"],
                    allowed_actions=["inspect-source"],
                    forbidden_actions=["external-send"],
                    architect="ARCHITECT",
                )

    def test_role_requires_every_reserved_authority_action_and_fixed_depth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            with self.assertRaisesRegex(PlaybookError, "mist vaste verboden"):
                register_role(
                    workspace,
                    ROLE_ID,
                    revision=1,
                    title="Reviewer",
                    responsibilities=["Controleer."],
                    allowed_actions=["inspect-source"],
                    forbidden_actions=["subdelegate"],
                    handoff="Lever terug aan ARCHITECT.",
                    architect="ARCHITECT",
                )

            _, role = register_definitions(workspace)
            record = json.loads(
                (role.definition_path.parent / "record.json").read_text(encoding="utf-8")
            )
            self.assertEqual(record["delegation_depth"], 1)
            self.assertIs(record["may_delegate"], False)
            self.assertEqual(record["owner_authority"], OWNER_AUTHORITY_STATEMENT)
            self.assertTrue(RESERVED_AUTHORITY_ACTIONS.issubset(record["forbidden_actions"]))

    def test_exact_approval_changes_only_status_and_cannot_be_repeated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            playbook, _ = register_definitions(workspace, approve=False)
            before_document = playbook.definition_path.read_bytes()

            with self.assertRaisesRegex(PlaybookError, "Definitiedigest wijkt af"):
                approve_playbook(
                    workspace,
                    PLAYBOOK_ID,
                    revision=1,
                    definition_digest="0" * 64,
                    owner="OWNER",
                )
            self.assertFalse((playbook.definition_path.parent / "approval.json").exists())

            result = approve_playbook(
                workspace,
                PLAYBOOK_ID,
                revision=1,
                definition_digest=playbook.definition_digest,
                owner="OWNER",
            )
            self.assertEqual(result.status, "DEFINITION_APPROVED")
            status = playbook_status(workspace, PLAYBOOK_ID, 1)
            self.assertEqual(status.status, "APPROVED")
            self.assertRegex(status.approval_digest or "", r"[0-9a-f]{64}\Z")
            self.assertEqual(playbook.definition_path.read_bytes(), before_document)
            with self.assertRaisesRegex(PlaybookError, "al goedgekeurd"):
                approve_playbook(
                    workspace,
                    PLAYBOOK_ID,
                    revision=1,
                    definition_digest=playbook.definition_digest,
                    owner="OWNER",
                )

    def test_new_revision_requires_exact_immediate_predecessor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            first, _ = register_definitions(workspace, approve=False)
            with self.assertRaises(PlaybookError):
                register_playbook(
                    workspace,
                    PLAYBOOK_ID,
                    revision=2,
                    title="Tweede",
                    purpose="Tweede revisie.",
                    inputs=["Input"],
                    steps=["Stap"],
                    stop_conditions=["Stop"],
                    evidence_requirements=["Bewijs"],
                    allowed_actions=["inspect-source"],
                    forbidden_actions=["external-send"],
                    architect="ARCHITECT",
                    supersedes_digest="0" * 64,
                )
            second = register_playbook(
                workspace,
                PLAYBOOK_ID,
                revision=2,
                title="Tweede",
                purpose="Tweede revisie.",
                inputs=["Input"],
                steps=["Stap"],
                stop_conditions=["Stop"],
                evidence_requirements=["Bewijs"],
                allowed_actions=["inspect-source"],
                forbidden_actions=["external-send"],
                architect="ARCHITECT",
                supersedes_digest=first.definition_digest,
            )
            self.assertNotEqual(first.definition_digest, second.definition_digest)
            self.assertTrue(first.definition_path.exists())

    def test_invalid_ids_actions_conflicts_and_absolute_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            common = {
                "revision": 1,
                "title": "Titel",
                "purpose": "Doel.",
                "inputs": ["Input"],
                "steps": ["Stap"],
                "stop_conditions": ["Stop"],
                "evidence_requirements": ["Bewijs"],
                "allowed_actions": ["inspect-source"],
                "forbidden_actions": ["external-send"],
                "architect": "ARCHITECT",
            }
            with self.assertRaises(PlaybookError):
                register_playbook(workspace, "pb-fout", **common)
            with self.assertRaises(PlaybookError):
                register_playbook(
                    workspace,
                    PLAYBOOK_ID,
                    **{**common, "allowed_actions": ["Lees bron"]},
                )
            with self.assertRaises(PlaybookError):
                register_playbook(
                    workspace,
                    PLAYBOOK_ID,
                    **{**common, "forbidden_actions": ["inspect-source"]},
                )
            with self.assertRaisesRegex(PlaybookError, "absoluut persoonlijk pad"):
                private_path = "Lees " + "C:" + r"\Users\Naam\private.txt"
                register_playbook(
                    workspace,
                    PLAYBOOK_ID,
                    **{**common, "purpose": private_path},
                )

    def test_document_and_approval_drift_are_visible_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            playbook, _ = register_definitions(workspace)
            playbook.definition_path.write_text("gewijzigd\n", encoding="utf-8")

            status = playbook_status(workspace, PLAYBOOK_ID, 1)
            self.assertEqual(status.status, "STALE")
            self.assertFalse(verify_playbook(workspace, PLAYBOOK_ID, 1).ok)
            self.assertEqual(playbook.definition_path.read_text(encoding="utf-8"), "gewijzigd\n")

    def test_unknown_definition_file_and_json_field_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            _, role = register_definitions(workspace)
            unexpected = role.definition_path.parent / "extra.txt"
            unexpected.write_text("extra", encoding="utf-8")
            self.assertFalse(verify_role(workspace, ROLE_ID, 1).ok)
            unexpected.unlink()
            record_path = role.definition_path.parent / "record.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["unknown"] = True
            record_path.write_text(json.dumps(record), encoding="utf-8")
            self.assertFalse(verify_role(workspace, ROLE_ID, 1).ok)

    def test_executor_prepare_binds_all_layers_without_starting_any_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, playbook, role, proposed, context, prepared = prepare_ready_executor(
                Path(temporary_directory)
            )

            self.assertEqual(prepared.status, "EXECUTOR_PACKAGE_PREPARED")
            self.assertEqual(
                executor_status(workspace, TASK_ID, prepared.executor_id).status, "READY"
            )
            self.assertTrue(verify_executor(workspace, TASK_ID, prepared.executor_id).ok)
            record = json.loads(
                (prepared.assignment_path.parent / "record.json").read_text(encoding="utf-8")
            )
            self.assertEqual(record["task"]["proposal_digest"], proposed.object_digest)
            self.assertEqual(record["context"]["manifest_digest"], context.manifest_digest)
            self.assertEqual(record["playbook"]["definition_digest"], playbook.definition_digest)
            self.assertEqual(record["role"]["definition_digest"], role.definition_digest)
            self.assertEqual(record["delegation_depth"], 1)
            self.assertIs(record["may_delegate"], False)
            self.assertTrue(RESERVED_AUTHORITY_ACTIONS.issubset(record["forbidden_actions"]))
            self.assertEqual(record["data_authority"], DATA_AUTHORITY_STATEMENT)
            text = prepared.assignment_path.read_text(encoding="utf-8")
            self.assertIn("This package starts nothing", text)
            self.assertIn("no OWNER authority", text)
            completed = workspace / ".opencntx" / "transactions" / "completed"
            self.assertTrue(any(completed.iterdir()))
            self.assertEqual(
                list((workspace / ".opencntx" / "transactions" / "locks").rglob("*.lock")), []
            )

    def test_executor_requires_approved_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, playbook, role, proposed, context = start_execution(
                Path(temporary_directory), approve_definitions=False
            )
            with self.assertRaisesRegex(PlaybookError, "niet exact door de OWNER"):
                prepare_executor(
                    workspace,
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
                    executor="UITVOERDER-1",
                )

    def test_executor_rejects_wrong_task_definition_and_context_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, playbook, role, proposed, context = start_execution(
                Path(temporary_directory)
            )
            base = {
                "project_root": workspace,
                "task_id": TASK_ID,
                "revision": 1,
                "proposal_digest": proposed.object_digest,
                "playbook_id": PLAYBOOK_ID,
                "playbook_revision": 1,
                "playbook_digest": playbook.definition_digest,
                "role_id": ROLE_ID,
                "role_revision": 1,
                "role_digest": role.definition_digest,
                "context_manifest_digest": context.manifest_digest,
                "executor": "UITVOERDER-1",
            }
            for field in (
                "proposal_digest",
                "playbook_digest",
                "role_digest",
                "context_manifest_digest",
            ):
                with self.subTest(field=field), self.assertRaises(PlaybookError):
                    prepare_executor(**{**base, field: "0" * 64})

    def test_role_id_must_equal_task_executor_role(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, playbook, _role, proposed, context = start_execution(parent)
            other_role = register_role(
                workspace,
                "ROLE-ANDERE",
                revision=1,
                title="Andere",
                responsibilities=["Andere rol."],
                allowed_actions=ALLOWED_ACTIONS,
                forbidden_actions=sorted(RESERVED_AUTHORITY_ACTIONS),
                handoff="Lever terug aan ARCHITECT.",
                architect="ARCHITECT",
            )
            approve_role(
                workspace,
                "ROLE-ANDERE",
                revision=1,
                definition_digest=other_role.definition_digest,
                owner="OWNER",
            )
            with self.assertRaisesRegex(PlaybookError, "Taakrol"):
                prepare_executor(
                    workspace,
                    TASK_ID,
                    revision=1,
                    proposal_digest=proposed.object_digest,
                    playbook_id=PLAYBOOK_ID,
                    playbook_revision=1,
                    playbook_digest=playbook.definition_digest,
                    role_id="ROLE-ANDERE",
                    role_revision=1,
                    role_digest=other_role.definition_digest,
                    context_manifest_digest=context.manifest_digest,
                    executor="UITVOERDER-1",
                )

    def test_action_outside_playbook_or_role_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            playbook, role = register_definitions(workspace)
            rebuild_catalog(workspace)
            set_current(workspace)
            inputs = [
                "CONTROL/OWNER.md",
                "CONTROL/ROADMAP.md",
                "CONTROL/CURRENT.md",
                playbook.definition_path.relative_to(workspace).as_posix(),
                role.definition_path.relative_to(workspace).as_posix(),
            ]
            proposed = propose_task(
                workspace,
                TASK_ID,
                title="Te ruime taak",
                goal="Controleer scope.",
                definition_of_done="Bewijs bestaat.",
                executor_role=ROLE_ID,
                input_paths=inputs,
                allowed_actions=["inspect-source", "unknown-action"],
                forbidden_actions=["external-send"],
                expected_output="Resultaat.",
                acceptance_criteria=["Bewijs."],
                architect="ARCHITECT",
            )
            approve_task(
                workspace,
                TASK_ID,
                revision=1,
                proposal_digest=proposed.object_digest,
                owner="OWNER",
            )
            begin_task(workspace, TASK_ID, architect="ARCHITECT")
            context = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            with self.assertRaisesRegex(PlaybookError, "buiten playbook of rol"):
                prepare_executor(
                    workspace,
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
                    executor="UITVOERDER-1",
                )

    def test_second_executor_package_for_same_task_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, playbook, role, proposed, context, _ = prepare_ready_executor(
                Path(temporary_directory)
            )
            with self.assertRaisesRegex(PlaybookError, "al een uitvoerderpakket"):
                prepare_executor(
                    workspace,
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
                    executor="UITVOERDER-2",
                )

    def test_assignment_and_context_drift_are_reported_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, _, prepared = prepare_ready_executor(Path(temporary_directory))
            assignment = prepared.assignment_path
            before = snapshot(workspace)
            self.assertEqual(
                executor_status(workspace, TASK_ID, prepared.executor_id).status, "READY"
            )
            self.assertEqual(snapshot(workspace), before)

            assignment.write_text("drift\n", encoding="utf-8")
            report = verify_executor(workspace, TASK_ID, prepared.executor_id)
            self.assertFalse(report.ok)
            self.assertEqual(report.status, "STALE")
            self.assertEqual(assignment.read_text(encoding="utf-8"), "drift\n")

    def test_context_drift_invalidates_ready_executor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, _, prepared = prepare_ready_executor(Path(temporary_directory))
            context_path = workspace / ".opencntx" / "latest" / "CONTEXT.md"
            context_path.write_bytes(context_path.read_bytes() + b"drift\n")
            report = verify_executor(workspace, TASK_ID, prepared.executor_id)
            self.assertFalse(report.ok)
            self.assertEqual(report.status, "STALE")

    def test_task_leaving_execution_reports_finished_without_new_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, _, _, _, _, prepared = prepare_ready_executor(parent)
            result_path = parent / "result.txt"
            result_path.write_text("resultaat", encoding="utf-8")
            submit_result(
                workspace,
                TASK_ID,
                result_path=result_path,
                evidence_paths=[],
                limitations=[],
                open_questions=[],
                executor="UITVOERDER-1",
            )
            status = executor_status(workspace, TASK_ID, prepared.executor_id)
            self.assertEqual(status.status, "TASK_FINISHED")
            self.assertFalse(status.errors)

    def test_blocked_task_cannot_receive_a_new_executor_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, playbook, role, proposed, context = start_execution(
                Path(temporary_directory)
            )
            for number in range(1, 4):
                append_legacy_attempt(workspace, number)
            with self.assertRaisesRegex(PlaybookError, "niet exact in IN_EXECUTION"):
                prepare_executor(
                    workspace,
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
                    executor="UITVOERDER-1",
                )

    def test_cli_register_approve_status_and_verify_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            registered = run_cli(
                "workspace",
                "playbook",
                "register",
                PLAYBOOK_ID,
                "--revision",
                "1",
                "--title",
                "Controleer bron",
                "--purpose",
                "Controleer één bron.",
                "--input",
                "Eén contextpakket",
                "--step",
                "Controleer de digest.",
                "--stop",
                "Stop bij drift.",
                "--evidence",
                "Bewaar de SHA-256.",
                "--allow",
                "inspect-source",
                "--forbid",
                "external-send",
                "--architect",
                "ARCHITECT",
                "--root",
                str(workspace),
                cwd=workspace,
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            self.assertIn("DEFINITION_PROPOSED", registered.stdout)
            digest = playbook_status(workspace, PLAYBOOK_ID, 1).definition_digest
            self.assertIsNotNone(digest)
            approved = run_cli(
                "workspace",
                "playbook",
                "approve",
                PLAYBOOK_ID,
                "--revision",
                "1",
                "--definition-digest",
                digest or "",
                "--owner",
                "OWNER",
                "--root",
                str(workspace),
                cwd=workspace,
            )
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertIn("local statement", approved.stdout)
            verified = run_cli(
                "workspace",
                "playbook",
                "verify",
                PLAYBOOK_ID,
                "--revision",
                "1",
                "--root",
                str(workspace),
                cwd=workspace,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertIn("result: OK", verified.stdout)

    def test_cli_executor_prepare_states_that_nothing_was_started(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, playbook, role, proposed, context = start_execution(
                Path(temporary_directory)
            )
            result = run_cli(
                "workspace",
                "executor",
                "prepare",
                TASK_ID,
                "--revision",
                "1",
                "--proposal-digest",
                proposed.object_digest,
                "--playbook-id",
                PLAYBOOK_ID,
                "--playbook-revision",
                "1",
                "--playbook-digest",
                playbook.definition_digest,
                "--role-id",
                ROLE_ID,
                "--role-revision",
                "1",
                "--role-digest",
                role.definition_digest,
                "--context-manifest-digest",
                context.manifest_digest,
                "--executor",
                "UITVOERDER-1",
                "--root",
                str(workspace),
                cwd=workspace,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("EXECUTOR_PACKAGE_PREPARED", result.stdout)
            self.assertIn("No person, process, tool, model, or agent was started", result.stdout)


if __name__ == "__main__":
    unittest.main()
