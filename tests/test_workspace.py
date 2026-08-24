from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.workspace import (
    WorkspaceError,
    capture_source,
    init_workspace,
    load_workspace_config,
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


def records(workspace: Path) -> list[Path]:
    return sorted((workspace / "SOURCES").glob("*/*/SRC-*/record.json"))


def receipts(workspace: Path) -> list[Path]:
    return sorted((workspace / ".opencntx" / "receipts").glob("ATT-*.json"))


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


class WorkspaceTests(unittest.TestCase):
    def test_init_creates_exact_foundation_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "project"

            first = init_workspace(workspace)

            self.assertTrue(first.created)
            expected_directories = {
                "CONTROL",
                "INBOX",
                "SOURCES",
                "CHAPTERS",
                "TASKS",
                "PLAYBOOKS",
                "ROLES",
                ".opencntx",
                ".opencntx/receipts",
                ".opencntx/lifecycle",
            }
            actual_directories = {
                path.relative_to(workspace).as_posix()
                for path in workspace.rglob("*")
                if path.is_dir()
            }
            self.assertEqual(actual_directories, expected_directories)
            expected_files = {
                "CONTROL/OWNER.md",
                "CONTROL/ROADMAP.md",
                "CONTROL/CURRENT.md",
                "CHAPTERS/INDEX.md",
                ".opencntx/lifecycle/state.json",
            }
            actual_files = {
                path.relative_to(workspace).as_posix()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual_files, expected_files)
            before = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }

            second = init_workspace(workspace)

            self.assertFalse(second.created)
            after = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in workspace.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_init_and_capture_disk_preflight_fail_before_content_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            missing = parent / "missing-workspace"
            no_space = mock.Mock(total=100, used=100, free=0)
            with (
                mock.patch("opencntx.lifecycle.shutil.disk_usage", return_value=no_space),
                self.assertRaises(WorkspaceError) as init_error,
            ):
                init_workspace(missing)
            self.assertEqual(init_error.exception.code, "disk_space_insufficient")
            self.assertFalse(missing.exists())

            workspace = parent / "workspace"
            init_workspace(workspace)
            source = parent / "source.bin"
            source.write_bytes(b"disk-preflight")
            with (
                mock.patch("opencntx.lifecycle.shutil.disk_usage", return_value=no_space),
                self.assertRaises(WorkspaceError) as capture_error,
            ):
                capture_source(workspace, source)
            self.assertEqual(capture_error.exception.code, "disk_space_insufficient")
            self.assertEqual(list((workspace / "SOURCES").rglob("original*")), [])
            self.assertEqual(list((workspace / ".opencntx").glob(".capture-*")), [])

    def test_init_preserves_existing_package_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            latest = workspace / ".opencntx" / "latest"
            latest.mkdir(parents=True)
            marker = latest / "manifest.json"
            marker.write_text("bewaar mij\n", encoding="utf-8")

            result = init_workspace(workspace)

            self.assertTrue(result.created)
            self.assertEqual(marker.read_text(encoding="utf-8"), "bewaar mij\n")
            self.assertTrue((workspace / ".opencntx" / "receipts").is_dir())

    def test_init_refuses_partial_or_conflicting_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            inbox = workspace / "INBOX"
            inbox.mkdir()
            marker = inbox / "owner.txt"
            marker.write_text("bewaar mij", encoding="utf-8")

            with self.assertRaisesRegex(WorkspaceError, "niets overschreven"):
                init_workspace(workspace)

            self.assertEqual(marker.read_text(encoding="utf-8"), "bewaar mij")
            self.assertFalse((workspace / "CONTROL").exists())

    def test_init_failure_rolls_back_only_new_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            latest = workspace / ".opencntx" / "latest"
            latest.mkdir(parents=True)
            marker = latest / "manifest.json"
            marker.write_text("bestaande pakketstaat\n", encoding="utf-8")
            real_replace = os.replace

            def fail_during_init(source_path: object, destination_path: object) -> None:
                destination = Path(destination_path)  # type: ignore[arg-type]
                if destination == workspace / "SOURCES":
                    raise OSError("gesimuleerde initialisatiefout")
                real_replace(source_path, destination_path)  # type: ignore[arg-type]

            with (
                mock.patch(
                    "opencntx.workspace.os.replace",
                    side_effect=fail_during_init,
                ),
                self.assertRaisesRegex(WorkspaceError, "niet volledig"),
            ):
                init_workspace(workspace)

            self.assertEqual(marker.read_text(encoding="utf-8"), "bestaande pakketstaat\n")
            for relative in ("CONTROL", "INBOX", "SOURCES", "CHAPTERS"):
                self.assertFalse((workspace / relative).exists())
            self.assertFalse((workspace / ".opencntx" / "receipts").exists())
            self.assertFalse(any(workspace.glob(".opencntx-init-*")))

    def test_capture_text_is_exact_private_and_receipted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "brief.md"
            content = "Eerste regel\nTweede regel met café.\n".encode()
            source.write_bytes(content)
            source_before = source.read_bytes()

            result = capture_source(workspace, source, origin="OWNER")

            self.assertEqual(result.status, "CAPTURED")
            self.assertRegex(result.source_id, r"^SRC-\d{8}-[0-9a-f]{12}$")
            self.assertEqual(result.byte_count, len(content))
            self.assertEqual(result.sha256, hashlib.sha256(content).hexdigest())
            self.assertEqual(source.read_bytes(), source_before)
            record = read_json(records(workspace)[0])
            self.assertEqual(record["privacy"], "PRIVATE")
            self.assertEqual(record["origin"], "OWNER")
            self.assertEqual(record["source_id"], result.source_id)
            stored = workspace.joinpath(*Path(str(record["stored_path"])).parts)
            self.assertEqual(stored.read_bytes(), content)
            receipt = read_json(result.receipt_path)
            self.assertEqual(receipt["status"], "CAPTURED")
            self.assertEqual(receipt["source_id"], result.source_id)
            self.assertNotIn(str(source.parent), result.receipt_path.read_text(encoding="utf-8"))
            completed = workspace / ".opencntx" / "transactions" / "completed"
            self.assertEqual(len(list(completed.iterdir())), 1)
            self.assertEqual(
                list((workspace / ".opencntx" / "transactions" / "locks").rglob("*.lock")), []
            )

    def test_capture_binary_is_byte_exact_and_never_interpreted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "beeld.bin"
            content = bytes(range(256)) + b"\x00\xff\x00"
            source.write_bytes(content)

            result = capture_source(workspace, source, privacy="RESTRICTED")

            record = read_json(records(workspace)[0])
            stored = workspace.joinpath(*Path(str(record["stored_path"])).parts)
            self.assertEqual(stored.read_bytes(), content)
            self.assertEqual(record["privacy"], "RESTRICTED")
            self.assertEqual(result.sha256, hashlib.sha256(content).hexdigest())

    def test_duplicate_reuses_source_without_second_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "schema.txt"
            source.write_text("zelfde bytes", encoding="utf-8")

            first = capture_source(workspace, source)
            second = capture_source(workspace, source, origin="tweede ontvangst")

            self.assertEqual(first.status, "CAPTURED")
            self.assertEqual(second.status, "DUPLICATE")
            self.assertEqual(second.source_id, first.source_id)
            self.assertEqual(len(records(workspace)), 1)
            self.assertEqual(len(receipts(workspace)), 2)
            duplicate_receipt = read_json(second.receipt_path)
            self.assertEqual(duplicate_receipt["status"], "DUPLICATE")

    def test_duplicate_never_changes_existing_privacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "privaat.txt"
            source.write_text("dezelfde gevoelige bytes", encoding="utf-8")
            first = capture_source(workspace, source, privacy="PRIVATE")

            with self.assertRaisesRegex(WorkspaceError, "ander privacylabel"):
                capture_source(workspace, source, privacy="PUBLIC")

            self.assertEqual(len(records(workspace)), 1)
            record = read_json(records(workspace)[0])
            self.assertEqual(record["source_id"], first.source_id)
            self.assertEqual(record["privacy"], "PRIVATE")
            failure = read_json(receipts(workspace)[-1])
            self.assertEqual(failure["status"], "NOT_CAPTURED")
            self.assertEqual(failure["error_code"], "duplicate_privacy_conflict")

    def test_duplicate_refuses_drifted_existing_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "bron.bin"
            source.write_bytes(b"ABCD")
            capture_source(workspace, source)
            record = read_json(records(workspace)[0])
            stored = workspace.joinpath(*Path(str(record["stored_path"])).parts)
            stored.write_bytes(b"WXYZ")

            with self.assertRaisesRegex(WorkspaceError, "wijkt af"):
                capture_source(workspace, source)

            self.assertEqual(len(records(workspace)), 1)
            failure = read_json(receipts(workspace)[-1])
            self.assertEqual(failure["status"], "NOT_CAPTURED")
            self.assertEqual(failure["error_code"], "stored_source_drift")

    def test_supersedes_requires_existing_source_and_preserves_both(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "plan.txt"
            source.write_text("versie één", encoding="utf-8")
            first = capture_source(workspace, source)
            source.write_text("versie twee", encoding="utf-8")

            second = capture_source(
                workspace,
                source,
                privacy="PUBLIC",
                supersedes=first.source_id,
            )

            self.assertEqual(second.status, "CAPTURED")
            self.assertEqual(len(records(workspace)), 2)
            second_record = next(
                read_json(path)
                for path in records(workspace)
                if read_json(path)["source_id"] == second.source_id
            )
            self.assertEqual(second_record["supersedes"], first.source_id)
            self.assertEqual(second_record["privacy"], "PUBLIC")

            source.write_text("versie drie", encoding="utf-8")
            with self.assertRaisesRegex(WorkspaceError, "Onbekende supersedes-bron"):
                capture_source(
                    workspace,
                    source,
                    supersedes="SRC-20260816-000000000000",
                )
            failure = read_json(receipts(workspace)[-1])
            self.assertEqual(failure["status"], "NOT_CAPTURED")
            self.assertEqual(failure["error_code"], "supersedes_invalid")

    def test_source_and_total_budgets_are_separate_and_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            current = workspace / "CONTROL" / "CURRENT.md"
            text = current.read_text(encoding="utf-8")
            text = text.replace("max_source_bytes: 2147483648", "max_source_bytes: 4")
            text = text.replace("max_storage_bytes: 21474836480", "max_storage_bytes: 5")
            current.write_text(text, encoding="utf-8", newline="\n")
            config = load_workspace_config(workspace)
            self.assertEqual(config.max_source_bytes, 4)
            self.assertEqual(config.max_storage_bytes, 5)

            too_large = workspace / "INBOX" / "large.bin"
            too_large.write_bytes(b"12345")
            with self.assertRaisesRegex(WorkspaceError, "Bronbudget overschreden"):
                capture_source(workspace, too_large)

            first = workspace / "INBOX" / "first.bin"
            first.write_bytes(b"1234")
            capture_source(workspace, first)
            second = workspace / "INBOX" / "second.bin"
            second.write_bytes(b"56")
            with self.assertRaisesRegex(WorkspaceError, "Totaal opslagbudget"):
                capture_source(workspace, second)

            self.assertEqual(len(records(workspace)), 1)
            statuses = [read_json(path)["status"] for path in receipts(workspace)]
            self.assertEqual(statuses.count("CAPTURED"), 1)
            self.assertEqual(statuses.count("NOT_CAPTURED"), 2)

    def test_invalid_current_config_stops_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            current = workspace / "CONTROL" / "CURRENT.md"
            current.write_text("---\nformat: verkeerd\n---\n", encoding="utf-8")
            source = workspace / "INBOX" / "bron.txt"
            source.write_text("inhoud", encoding="utf-8")

            with self.assertRaises(WorkspaceError):
                capture_source(workspace, source)

            self.assertEqual(records(workspace), [])

    def test_directory_and_managed_source_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)

            with self.assertRaisesRegex(WorkspaceError, "regulier bestand"):
                capture_source(workspace, workspace / "INBOX")

            source = workspace / "INBOX" / "bron.txt"
            source.write_text("inhoud", encoding="utf-8")
            captured = capture_source(workspace, source)
            record = read_json(records(workspace)[0])
            managed = workspace.joinpath(*Path(str(record["stored_path"])).parts)
            with self.assertRaisesRegex(WorkspaceError, "niet opnieuw"):
                capture_source(workspace, managed)
            self.assertEqual(captured.status, "CAPTURED")

    def test_symlink_source_is_refused_when_platform_allows_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            target = workspace / "INBOX" / "target.txt"
            target.write_text("inhoud", encoding="utf-8")
            link = workspace / "INBOX" / "link.txt"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"Symlinks zijn niet beschikbaar: {exc}")

            with self.assertRaisesRegex(WorkspaceError, "geen symlink"):
                capture_source(workspace, link)

            self.assertEqual(records(workspace), [])

    def test_source_change_during_copy_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "verander.txt"
            source.write_text("voor", encoding="utf-8")

            from opencntx import workspace as workspace_module

            original_copy = workspace_module._copy_and_hash

            def copy_then_change(source_file: object, destination: object) -> tuple[int, str]:
                result = original_copy(source_file, destination)  # type: ignore[arg-type]
                source.write_text("na de kopie", encoding="utf-8")
                return result

            with (
                mock.patch(
                    "opencntx.workspace._copy_and_hash",
                    side_effect=copy_then_change,
                ),
                self.assertRaisesRegex(WorkspaceError, "veranderde tijdens capture"),
            ):
                capture_source(workspace, source)

            self.assertEqual(records(workspace), [])
            failure = read_json(receipts(workspace)[0])
            self.assertEqual(failure["status"], "NOT_CAPTURED")
            self.assertEqual(failure["error_code"], "source_changed")

    def test_atomic_publish_failure_leaves_no_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "bron.txt"
            source.write_text("inhoud", encoding="utf-8")

            real_replace = os.replace

            def fail_source_publish(source_path: object, destination_path: object) -> None:
                destination = Path(destination_path)  # type: ignore[arg-type]
                if destination.name.startswith("SRC-"):
                    raise OSError("gesimuleerde publicatiefout")
                real_replace(source_path, destination_path)  # type: ignore[arg-type]

            with (
                mock.patch(
                    "opencntx.workspace.os.replace",
                    side_effect=fail_source_publish,
                ),
                self.assertRaisesRegex(WorkspaceError, "atomair zichtbaar"),
            ):
                capture_source(workspace, source)

            self.assertEqual(records(workspace), [])
            self.assertFalse(any((workspace / ".opencntx").glob(".capture-*")))
            failure = read_json(receipts(workspace)[0])
            self.assertEqual(failure["status"], "NOT_CAPTURED")
            self.assertEqual(failure["error_code"], "source_publish_failed")

    def test_cli_init_capture_and_duplicate_are_under_workspace_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace = parent / "project"
            source = parent / "schema.bin"
            source.write_bytes(b"\x00schema\xff")

            initialized = run_cli("workspace", "init", str(workspace), cwd=parent)
            captured = run_cli(
                "workspace",
                "capture",
                str(source),
                "--root",
                str(workspace),
                "--origin",
                "OWNER",
                cwd=parent,
            )
            duplicate = run_cli(
                "workspace",
                "capture",
                str(source),
                "--root",
                str(workspace),
                cwd=parent,
            )

            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            self.assertIn("Created: project workspace", initialized.stdout)
            self.assertEqual(captured.returncode, 0, captured.stderr)
            self.assertIn("CAPTURED: SRC-", captured.stdout)
            self.assertIn("Receipt:", captured.stdout)
            self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
            self.assertIn("DUPLICATE: SRC-", duplicate.stdout)

    def test_cli_failure_returns_two_and_writes_not_captured_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            initialized = run_cli("workspace", "init", cwd=workspace)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            failed = run_cli(
                "workspace",
                "capture",
                "ontbreekt.txt",
                cwd=workspace,
            )

            self.assertEqual(failed.returncode, 2)
            self.assertIn("Error:", failed.stderr)
            failure = read_json(receipts(workspace)[0])
            self.assertEqual(failure["status"], "NOT_CAPTURED")
            self.assertEqual(failure["error_code"], "source_not_file")
            self.assertNotIn(
                str(workspace),
                receipts(workspace)[0].read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
