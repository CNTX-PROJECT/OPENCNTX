from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.catalog import create_chapter, rebuild_catalog
from opencntx.core import verify_package
from opencntx.navigator import (
    NavigatorError,
    build_context_package,
    verify_context_package,
)
from opencntx.workflow import approve_task, begin_task, propose_task
from opencntx.workspace import capture_source, init_workspace

TASK_ID = "TASK-20260816-0001"
HOT_PATHS_FOR_TEST = (
    "CONTROL/OWNER.md",
    "CONTROL/ROADMAP.md",
    "CONTROL/CURRENT.md",
)


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


def set_current(workspace: Path, task_id: str = TASK_ID) -> None:
    path = workspace / "CONTROL" / "CURRENT.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("- Active task: none", f"- Active task: {task_id} revision 1")
    path.write_text(text, encoding="utf-8", newline="\n")


def accept_chapter(path: Path, approval: str = "OWNER-DECISION-1") -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('knowledge_status = "DRAFT"', 'knowledge_status = "OWNER_ACCEPTED"')
    text = text.replace('last_owner_approval = ""', f'last_owner_approval = "{approval}"')
    path.write_text(text, encoding="utf-8", newline="\n")


def add_source(
    workspace: Path,
    name: str,
    content: bytes,
    *,
    privacy: str = "PRIVATE",
) -> tuple[str, str, str]:
    inbox = workspace / "INBOX" / name
    inbox.write_bytes(content)
    result = capture_source(workspace, inbox, privacy=privacy, origin="OWNER")
    record_path = next(
        path
        for path in (workspace / "SOURCES").glob("*/*/SRC-*/record.json")
        if json.loads(path.read_text(encoding="utf-8"))["source_id"] == result.source_id
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    return result.source_id, record_path.relative_to(workspace).as_posix(), record["stored_path"]


def add_accepted_chapter(
    workspace: Path,
    chapter_id: str,
    source_id: str,
    *,
    dependencies: tuple[str, ...] = (),
) -> str:
    result = create_chapter(
        workspace,
        chapter_id,
        title=chapter_id.removeprefix("CH-").title(),
        scope=f"Begrensde scope voor {chapter_id}.",
        source_ids=[source_id],
        dependency_ids=dependencies,
    )
    accept_chapter(result.chapter_path)
    return result.chapter_path.relative_to(workspace).as_posix()


def activate_task(
    workspace: Path,
    content_inputs: list[str],
    *,
    begin: bool = True,
    current_task_id: str = TASK_ID,
):
    set_current(workspace, current_task_id)
    proposed = propose_task(
        workspace,
        TASK_ID,
        title="Controleer begrensde projectcontext",
        goal="Controleer uitsluitend de goedgekeurde projectcontext.",
        definition_of_done="Resultaat verwijst naar alle gebruikte bronnen.",
        executor_role="ROLE-CONTROLEUR",
        input_paths=[
            "CONTROL/OWNER.md",
            "CONTROL/ROADMAP.md",
            "CONTROL/CURRENT.md",
            *content_inputs,
        ],
        allowed_actions=["Lees uitsluitend het taakgebonden contextpakket"],
        forbidden_actions=["Geen externe verzending"],
        expected_output="Eén lokaal resultaat met bewijs",
        acceptance_criteria=["Iedere claim verwijst naar een gepinde bron"],
        architect="ARCHITECT",
    )
    approved = approve_task(
        workspace,
        TASK_ID,
        revision=1,
        proposal_digest=proposed.object_digest,
        owner="OWNER",
    )
    started = begin_task(workspace, TASK_ID, architect="ARCHITECT") if begin else None
    return proposed, approved, started


def ready_workspace(
    parent: Path,
    *,
    privacy: str = "PRIVATE",
    content: bytes = b"Exacte projectbron.\n",
    legacy: bool = False,
    roadmap_history: str = "",
) -> tuple[Path, str, str, str, object]:
    workspace = parent / "workspace"
    init_workspace(workspace)
    roadmap = workspace / "CONTROL" / "ROADMAP.md"
    if legacy:
        text = roadmap.read_text(encoding="utf-8")
        text = text.replace("<!-- OPENCNTX:CONTROL:START -->\n", "")
        text = text.replace("<!-- OPENCNTX:CONTROL:END -->\n", "")
        roadmap.write_text(text, encoding="utf-8", newline="\n")
    if roadmap_history:
        roadmap.write_text(
            roadmap.read_text(encoding="utf-8") + roadmap_history,
            encoding="utf-8",
            newline="\n",
        )
    source_id, record_path, original_path = add_source(
        workspace, "bron.txt", content, privacy=privacy
    )
    chapter_path = add_accepted_chapter(workspace, "CH-PLAN", source_id)
    rebuild_catalog(workspace)
    proposed, _, _ = activate_task(workspace, [chapter_path])
    return workspace, source_id, record_path, original_path, proposed


def official_snapshot(workspace: Path) -> dict[str, bytes]:
    roots = ("CONTROL", "SOURCES", "CHAPTERS", "TASKS", "PLAYBOOKS", "ROLES")
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for name in roots
        for path in (workspace / name).rglob("*")
        if path.is_file()
    }


class NavigatorTests(unittest.TestCase):
    def test_build_creates_standard_task_bound_package_and_both_verifiers_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, source_id, _, _, proposed = ready_workspace(Path(temporary_directory))
            before = official_snapshot(workspace)

            result = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )

            self.assertEqual(result.status, "CONTEXT_BUILT")
            self.assertEqual(result.file_count, 7)
            self.assertTrue(verify_package(result.package_path).ok)
            self.assertTrue(
                verify_context_package(
                    workspace, TASK_ID, proposal_digest=proposed.object_digest
                ).ok
            )
            manifest = json.loads(
                (result.package_path / "manifest.json").read_text(encoding="utf-8")
            )
            navigation = manifest["navigation"]
            self.assertEqual(navigation["task"]["task_id"], TASK_ID)
            self.assertEqual(navigation["sources"][0]["source_id"], source_id)
            self.assertEqual(navigation["control"]["mode"], "COMPACT_MARKED")
            self.assertFalse(navigation["control"]["roadmap_body_loaded"])
            self.assertEqual(
                navigation["read"][1]["path"],
                ".opencntx/control-snapshot.md",
            )
            self.assertEqual(
                [
                    item["path"]
                    for item in navigation["read"]
                    if item["path"].startswith(".opencntx/")
                ],
                [".opencntx/control-snapshot.md"],
            )
            self.assertEqual(
                navigation["not_read"]["control"][0]["reason"],
                "FULL_DIGEST_PINNED_COMPACT_BLOCK_LOADED",
            )
            self.assertEqual(
                [item["layer"] for item in navigation["read"]],
                ["HOT", "HOT", "HOT", "HOT", "WARM", "COLD", "COLD"],
            )
            self.assertEqual(official_snapshot(workspace), before)
            self.assertIn(
                "does not grant permission",
                run_cli(
                    "workspace",
                    "context",
                    "build",
                    TASK_ID,
                    "--proposal-digest",
                    proposed.object_digest,
                    "--max-files",
                    "25",
                    "--max-bytes",
                    "100000",
                    "--root",
                    str(workspace),
                    cwd=workspace,
                ).stdout,
            )
            completed = workspace / ".opencntx" / "transactions" / "completed"
            self.assertTrue(any(completed.iterdir()))
            self.assertEqual(
                list((workspace / ".opencntx" / "transactions" / "locks").rglob("*.lock")), []
            )

    def test_compact_mode_excludes_history_but_pins_full_roadmap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            history = "\n## Historisch archief\n\nZEER-GROTE-OUDE-GESCHIEDENIS\n"
            workspace, _, _, _, proposed = ready_workspace(
                Path(temporary_directory), roadmap_history=history
            )
            roadmap = (workspace / "CONTROL" / "ROADMAP.md").read_bytes()
            result = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            context = (result.package_path / "CONTEXT.md").read_text(encoding="utf-8")
            manifest = json.loads(
                (result.package_path / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("ZEER-GROTE-OUDE-GESCHIEDENIS", context)
            self.assertIn("<!-- OPENCNTX:CONTROL:START -->", context)
            self.assertEqual(
                manifest["navigation"]["control"]["roadmap_sha256"],
                hashlib.sha256(roadmap).hexdigest(),
            )
            self.assertTrue(
                verify_context_package(
                    workspace, TASK_ID, proposal_digest=proposed.object_digest
                ).ok
            )

    def test_legacy_mode_keeps_full_roadmap_and_old_hot_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            history = "\n## Historisch archief\n\nLEGACY-GESCHIEDENIS\n"
            workspace, _, _, _, proposed = ready_workspace(
                Path(temporary_directory), legacy=True, roadmap_history=history
            )
            result = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            context = (result.package_path / "CONTEXT.md").read_text(encoding="utf-8")
            manifest = json.loads(
                (result.package_path / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertIn("LEGACY-GESCHIEDENIS", context)
            self.assertEqual(
                manifest["navigation"]["control"]["mode"],
                "LEGACY_FULL_ROADMAP",
            )
            self.assertTrue(manifest["navigation"]["control"]["roadmap_body_loaded"])
            self.assertEqual(
                [item["path"] for item in manifest["navigation"]["read"][:3]],
                list(HOT_PATHS_FOR_TEST),
            )
            self.assertFalse((workspace / ".opencntx" / "control-snapshot.md").exists())

    def test_pre_control_legacy_package_remains_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory), legacy=True)
            result = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            manifest_path = result.package_path / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["navigation"]["control"]
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            self.assertTrue(
                verify_context_package(
                    workspace, TASK_ID, proposal_digest=proposed.object_digest
                ).ok
            )

    def test_compact_mode_fits_budget_that_rejects_same_legacy_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            history = "\n## Historisch\n\n" + ("oude-informatie\n" * 3_000)
            compact, _, _, _, compact_task = ready_workspace(
                parent / "compact", roadmap_history=history
            )
            legacy, _, _, _, legacy_task = ready_workspace(
                parent / "legacy", legacy=True, roadmap_history=history
            )

            built = build_context_package(
                compact,
                TASK_ID,
                proposal_digest=compact_task.object_digest,
                max_files=25,
                max_bytes=20_000,
            )
            self.assertEqual(built.status, "CONTEXT_BUILT")
            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    legacy,
                    TASK_ID,
                    proposal_digest=legacy_task.object_digest,
                    max_files=25,
                    max_bytes=20_000,
                )
            self.assertEqual(context.exception.code, "context_budget_exceeded")

    def test_control_drift_is_detected_without_refresh_during_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory))
            built = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            snapshot = workspace / ".opencntx" / "control-snapshot.md"
            snapshot_before = snapshot.read_bytes()
            roadmap = workspace / "CONTROL" / "ROADMAP.md"
            roadmap.write_text(
                roadmap.read_text(encoding="utf-8") + "\nNieuwe geschiedenis.\n",
                encoding="utf-8",
                newline="\n",
            )
            report = verify_context_package(
                workspace, TASK_ID, proposal_digest=proposed.object_digest
            )
            self.assertFalse(report.ok)
            self.assertEqual(snapshot.read_bytes(), snapshot_before)
            self.assertTrue(built.package_path.is_dir())

    def test_exact_control_inputs_and_non_control_content_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace = parent / "missing-control"
            init_workspace(workspace)
            source_id, _, _ = add_source(workspace, "bron.txt", b"tekst\n")
            chapter = add_accepted_chapter(workspace, "CH-PLAN", source_id)
            rebuild_catalog(workspace)
            set_current(workspace)
            proposed = propose_task(
                workspace,
                TASK_ID,
                title="Mist OWNER-input",
                goal="Controleer begrensde context.",
                definition_of_done="Context is begrensd.",
                executor_role="ROLE-CONTROLEUR",
                input_paths=["CONTROL/ROADMAP.md", "CONTROL/CURRENT.md", chapter],
                allowed_actions=["Alleen lezen"],
                forbidden_actions=["Niet extern delen"],
                expected_output="Lokaal resultaat",
                acceptance_criteria=["Exacte bronnen"],
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
            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "context_control_inputs_invalid")

            workspace = parent / "missing-content"
            init_workspace(workspace)
            rebuild_catalog(workspace)
            set_current(workspace)
            proposed = propose_task(
                workspace,
                TASK_ID,
                title="Mist inhoud",
                goal="Controleer begrensde context.",
                definition_of_done="Context is begrensd.",
                executor_role="ROLE-CONTROLEUR",
                input_paths=list(HOT_PATHS_FOR_TEST),
                allowed_actions=["Alleen lezen"],
                forbidden_actions=["Niet extern delen"],
                expected_output="Lokaal resultaat",
                acceptance_criteria=["Exacte bronnen"],
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
            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "context_content_input_missing")

    def test_equal_inputs_and_budgets_produce_equal_package_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory))
            first = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            first_context = (first.package_path / "CONTEXT.md").read_bytes()
            first_manifest = (first.package_path / "manifest.json").read_bytes()

            second = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )

            self.assertEqual((second.package_path / "CONTEXT.md").read_bytes(), first_context)
            self.assertEqual((second.package_path / "manifest.json").read_bytes(), first_manifest)
            receipts = list((workspace / ".opencntx" / "receipts").glob("CTX-*.json"))
            self.assertEqual(len(receipts), 2)

    def test_budget_failure_preserves_previous_package_and_writes_failure_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory))
            built = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            before = {path.name: path.read_bytes() for path in built.package_path.iterdir()}

            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=1,
                    max_bytes=1,
                )

            self.assertEqual(context.exception.code, "context_budget_exceeded")
            self.assertEqual(
                {path.name: path.read_bytes() for path in built.package_path.iterdir()}, before
            )
            receipts = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((workspace / ".opencntx" / "receipts").glob("CTX-*.json"))
            ]
            self.assertEqual(receipts[-1]["status"], "CONTEXT_NOT_BUILT")
            self.assertNotIn(str(workspace), json.dumps(receipts[-1]))

    def test_task_must_be_in_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            source_id, _, _ = add_source(workspace, "bron.txt", b"tekst\n")
            chapter = add_accepted_chapter(workspace, "CH-PLAN", source_id)
            rebuild_catalog(workspace)
            proposed, _, _ = activate_task(workspace, [chapter], begin=False)

            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "context_task_not_executing")
            self.assertFalse((workspace / ".opencntx" / "control-snapshot.md").exists())

    def test_current_must_name_exact_task_and_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            source_id, _, _ = add_source(workspace, "bron.txt", b"tekst\n")
            chapter = add_accepted_chapter(workspace, "CH-PLAN", source_id)
            rebuild_catalog(workspace)
            proposed, _, _ = activate_task(
                workspace, [chapter], current_task_id="TASK-20260816-9999"
            )

            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "context_current_mismatch")

    def test_catalog_drift_requires_explicit_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory))
            chapter = workspace / "CHAPTERS" / "CH-PLAN" / "CHAPTER.md"
            text = chapter.read_text(encoding="utf-8").replace(
                "Begrensde scope voor CH-PLAN.", "Gewijzigde begrensde scope."
            )
            chapter.write_text(text, encoding="utf-8", newline="\n")

            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "task_input_stale")

    def test_missing_catalog_has_stable_rebuild_required_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory))
            (workspace / ".opencntx" / "catalog.sqlite").unlink()

            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )

            self.assertEqual(context.exception.code, "catalog_rebuild_required")
            receipt = max(
                (workspace / ".opencntx" / "receipts").glob("CTX-*.json"),
                key=lambda path: path.stat().st_mtime_ns,
            )
            value = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertIn("catalog rebuild", value["next_action"])

    def test_draft_chapter_is_not_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            source_id, _, _ = add_source(workspace, "bron.txt", b"tekst\n")
            chapter = (
                create_chapter(workspace, "CH-PLAN", title="Plan", source_ids=[source_id])
                .chapter_path.relative_to(workspace)
                .as_posix()
            )
            rebuild_catalog(workspace)
            proposed, _, _ = activate_task(workspace, [chapter])

            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "context_chapter_not_current")

    def test_restricted_source_requires_explicit_source_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace = parent / "workspace"
            init_workspace(workspace)
            source_id, record_path, _ = add_source(
                workspace, "restricted.txt", b"beperkt\n", privacy="RESTRICTED"
            )
            chapter = add_accepted_chapter(workspace, "CH-PLAN", source_id)
            rebuild_catalog(workspace)
            proposed, _, _ = activate_task(workspace, [chapter])
            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "context_source_restricted")

            other = parent / "allowed"
            init_workspace(other)
            source_id, record_path, _ = add_source(
                other, "restricted.txt", b"beperkt\n", privacy="RESTRICTED"
            )
            chapter = add_accepted_chapter(other, "CH-PLAN", source_id)
            rebuild_catalog(other)
            proposed, _, _ = activate_task(other, [chapter, record_path])
            result = build_context_package(
                other,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            self.assertEqual(result.status, "CONTEXT_BUILT")

    def test_quarantined_source_is_always_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            source_id, record_path, _ = add_source(
                workspace, "unknown.txt", b"onbekend\n", privacy="QUARANTINED"
            )
            chapter = add_accepted_chapter(workspace, "CH-PLAN", source_id)
            rebuild_catalog(workspace)
            proposed, _, _ = activate_task(workspace, [chapter, record_path])
            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "context_source_quarantined")

    def test_binary_source_stops_without_partial_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(
                Path(temporary_directory), content=b"tekst\x00binair"
            )
            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "context_source_invalid")
            self.assertFalse((workspace / ".opencntx" / "latest").exists())

    def test_dependency_closure_and_unread_ids_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            init_workspace(workspace)
            child_source, _, _ = add_source(workspace, "child.txt", b"child\n")
            parent_source, _, _ = add_source(workspace, "parent.txt", b"parent\n")
            other_source, _, _ = add_source(workspace, "other.txt", b"other\n")
            add_accepted_chapter(workspace, "CH-CHILD", child_source)
            parent = add_accepted_chapter(
                workspace, "CH-PARENT", parent_source, dependencies=("CH-CHILD",)
            )
            add_accepted_chapter(workspace, "CH-OTHER", other_source)
            rebuild_catalog(workspace)
            proposed, _, _ = activate_task(workspace, [parent])

            built = build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            navigation = json.loads(
                (built.package_path / "manifest.json").read_text(encoding="utf-8")
            )["navigation"]
            self.assertEqual(
                [item["chapter_id"] for item in navigation["chapters"]],
                ["CH-CHILD", "CH-PARENT"],
            )
            self.assertEqual(
                navigation["not_read"]["chapters"],
                [{"chapter_id": "CH-OTHER", "reason": "OUTSIDE_APPROVED_TASK_SCOPE"}],
            )
            self.assertEqual(
                navigation["not_read"]["sources"],
                [{"reason": "OUTSIDE_APPROVED_TASK_SCOPE", "source_id": other_source}],
            )

    def test_workspace_verify_detects_live_drift_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory))
            build_context_package(
                workspace,
                TASK_ID,
                proposal_digest=proposed.object_digest,
                max_files=25,
                max_bytes=100_000,
            )
            receipts_before = sorted(
                path.name for path in (workspace / ".opencntx" / "receipts").iterdir()
            )
            current = workspace / "CONTROL" / "CURRENT.md"
            current.write_text(
                current.read_text(encoding="utf-8") + "\ngewijzigd\n",
                encoding="utf-8",
                newline="\n",
            )

            report = verify_context_package(
                workspace, TASK_ID, proposal_digest=proposed.object_digest
            )

            self.assertFalse(report.ok)
            self.assertTrue(report.errors)
            self.assertEqual(
                sorted(path.name for path in (workspace / ".opencntx" / "receipts").iterdir()),
                receipts_before,
            )

    def test_tampered_catalog_row_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory))
            catalog = workspace / ".opencntx" / "catalog.sqlite"
            connection = sqlite3.connect(catalog)
            connection.execute("UPDATE chapters SET title = 'VERVALST'")
            connection.commit()
            connection.close()

            with self.assertRaises(NavigatorError) as context:
                build_context_package(
                    workspace,
                    TASK_ID,
                    proposal_digest=proposed.object_digest,
                    max_files=25,
                    max_bytes=100_000,
                )
            self.assertEqual(context.exception.code, "catalog_rebuild_required")

    def test_cli_build_and_verify_use_expected_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, _, _, _, proposed = ready_workspace(Path(temporary_directory))
            build = run_cli(
                "workspace",
                "context",
                "build",
                TASK_ID,
                "--proposal-digest",
                proposed.object_digest,
                "--max-files",
                "25",
                "--max-bytes",
                "100000",
                "--root",
                str(workspace),
                cwd=workspace,
            )
            verify = run_cli(
                "workspace",
                "context",
                "verify",
                TASK_ID,
                "--proposal-digest",
                proposed.object_digest,
                "--root",
                str(workspace),
                cwd=workspace,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertIn("CONTEXT_BUILT", build.stdout)
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertIn("result: OK", verify.stdout)

            (workspace / "CONTROL" / "OWNER.md").write_text("gewijzigd\n", encoding="utf-8")
            drift = run_cli(
                "workspace",
                "context",
                "verify",
                TASK_ID,
                "--proposal-digest",
                proposed.object_digest,
                "--root",
                str(workspace),
                cwd=workspace,
            )
            self.assertEqual(drift.returncode, 1, drift.stderr)
            self.assertIn("DRIFT OR INCOMPLETE", drift.stdout)


if __name__ == "__main__":
    unittest.main()
