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
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.media import (
    MediaError,
    media_status,
    promote_derivation,
    register_derivation,
    remove_derivation,
    review_derivation,
    verify_media,
)
from opencntx.workspace import (
    WorkspaceError,
    capture_source,
    init_workspace,
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


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def source_record(workspace: Path, source_id: str) -> tuple[Path, dict[str, object]]:
    for path in (workspace / "SOURCES").glob("*/*/SRC-*/record.json"):
        value = read_json(path)
        if value["source_id"] == source_id:
            return path, value
    raise AssertionError(f"source record not found: {source_id}")


def derivation_directory(workspace: Path, source_id: str, derivation_id: str) -> Path:
    return workspace / ".opencntx" / "derived" / source_id / derivation_id


def setup_media(
    parent: Path,
    *,
    privacy: str = "PRIVATE",
    original_bytes: bytes = b"\x89PNG\r\n\x1a\nopaque-media",
    derived_text: str = "Herkenbare afgeleide tekst.\n",
) -> tuple[Path, object, Path]:
    workspace = parent / "workspace"
    init_workspace(workspace)
    original = workspace / "INBOX" / "drawing.png"
    original.write_bytes(original_bytes)
    captured = capture_source(workspace, original, privacy=privacy, origin="OWNER")
    text_path = parent / "derived.txt"
    text_path.write_text(derived_text, encoding="utf-8", newline="\n")
    return workspace, captured, text_path


def register_default(workspace: Path, captured: object, text_path: Path):
    return register_derivation(
        workspace,
        captured.source_id,
        text_path,
        kind="OCR",
        producer_class="LOCAL_TOOL",
        producer="offline-tool 1",
        locators=["pagina 1", "detail B"],
    )


def accept_default(workspace: Path, registered: object):
    reviewed = review_derivation(
        workspace,
        registered.source_id,
        registered.derivation_id,
        content_sha256=registered.content_sha256,
        decision="ACCEPT",
        findings=["Pagina 1 handmatig vergeleken"],
        reviewer="ARCHITECT",
    )
    status = media_status(workspace, registered.source_id, registered.derivation_id)[0]
    assert status.review_sha256 is not None
    return reviewed, status.review_sha256


def set_budgets(workspace: Path, *, source_bytes: int, storage_bytes: int) -> None:
    current = workspace / "CONTROL" / "CURRENT.md"
    text = current.read_text(encoding="utf-8")
    text = text.replace("max_source_bytes: 2147483648", f"max_source_bytes: {source_bytes}")
    text = text.replace("max_storage_bytes: 21474836480", f"max_storage_bytes: {storage_bytes}")
    current.write_text(text, encoding="utf-8", newline="\n")


class MediaTests(unittest.TestCase):
    def test_registration_disk_preflight_blocks_before_derived_content_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            no_space = mock.Mock(total=100, used=100, free=0)

            with (
                mock.patch("opencntx.lifecycle.shutil.disk_usage", return_value=no_space),
                self.assertRaises(WorkspaceError) as context,
            ):
                register_default(workspace, captured, text_path)

            self.assertEqual(context.exception.code, "disk_space_insufficient")
            self.assertFalse((workspace / ".opencntx" / "derived").exists())
            self.assertEqual(list((workspace / ".opencntx").glob(".media-register-*")), [])

    def test_status_is_explicit_when_media_was_not_investigated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, _ = setup_media(Path(temporary_directory))

            entries = media_status(workspace, captured.source_id)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].status, "NOT_INVESTIGATED")
            self.assertEqual(entries[0].statement, "CONTENT NOT INVESTIGATED")
            self.assertFalse((workspace / ".opencntx" / "derived").exists())

    def test_register_preserves_original_and_binds_exact_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            record_path, source = source_record(workspace, captured.source_id)
            original = workspace.joinpath(*Path(str(source["stored_path"])).parts)
            original_before = original.read_bytes()
            source_record_before = record_path.read_bytes()

            result = register_default(workspace, captured, text_path)

            self.assertEqual(result.status, "REGISTERED")
            self.assertRegex(result.derivation_id, r"^DRV-\d{8}-[0-9a-f]{12}$")
            directory = derivation_directory(workspace, result.source_id, result.derivation_id)
            self.assertEqual((directory / "content.txt").read_bytes(), text_path.read_bytes())
            record = read_json(directory / "record.json")
            self.assertEqual(record["source_id"], captured.source_id)
            self.assertEqual(record["source_sha256"], captured.sha256)
            self.assertEqual(
                record["source_record_sha256"],
                hashlib.sha256(source_record_before).hexdigest(),
            )
            self.assertEqual(record["privacy"], "PRIVATE")
            self.assertEqual(record["kind"], "OCR")
            self.assertEqual(record["producer_class"], "LOCAL_TOOL")
            self.assertEqual(record["locators"], ["pagina 1", "detail B"])
            self.assertEqual(original.read_bytes(), original_before)
            self.assertEqual(record_path.read_bytes(), source_record_before)
            self.assertTrue(result.receipt_path.is_file())
            self.assertEqual(media_status(workspace, captured.source_id)[0].status, "UNREVIEWED")
            completed = workspace / ".opencntx" / "transactions" / "completed"
            self.assertGreaterEqual(len(list(completed.iterdir())), 2)
            self.assertEqual(
                list((workspace / ".opencntx" / "transactions" / "locks").rglob("*.lock")), []
            )

    def test_exact_duplicate_does_not_make_second_content_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            first = register_default(workspace, captured, text_path)

            second = register_default(workspace, captured, text_path)

            self.assertEqual(second.status, "DUPLICATE_DERIVATION")
            self.assertEqual(second.derivation_id, first.derivation_id)
            directories = list((workspace / ".opencntx" / "derived" / captured.source_id).iterdir())
            self.assertEqual(len(directories), 1)

    def test_register_rejects_invalid_utf8_and_nul_without_partial_state(self) -> None:
        for content in (b"\xff\xfe", b"tekst\x00verborgen"):
            with (
                self.subTest(content=content),
                tempfile.TemporaryDirectory() as temporary_directory,
            ):
                workspace, captured, text_path = setup_media(Path(temporary_directory))
                text_path.write_bytes(content)

                with self.assertRaises(MediaError):
                    register_default(workspace, captured, text_path)

                self.assertEqual(
                    media_status(workspace, captured.source_id)[0].status, "NOT_INVESTIGATED"
                )
                self.assertFalse(any((workspace / ".opencntx").glob(".media-register-*")))

    def test_register_rejects_managed_content_and_absolute_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, _ = setup_media(Path(temporary_directory))
            _, source = source_record(workspace, captured.source_id)
            managed = workspace.joinpath(*Path(str(source["stored_path"])).parts)

            with self.assertRaisesRegex(MediaError, "Beheerde"):
                register_derivation(
                    workspace,
                    captured.source_id,
                    managed,
                    kind="OCR",
                    producer_class="LOCAL_TOOL",
                    producer="tool",
                )
            with self.assertRaisesRegex(MediaError, "absoluut persoonlijk pad"):
                register_derivation(
                    workspace,
                    captured.source_id,
                    workspace / "INBOX" / "drawing.png",
                    kind="OCR",
                    producer_class="LOCAL_TOOL",
                    producer="C:\\private\\tool.exe",
                )

    def test_quarantined_source_cannot_be_derived(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(
                Path(temporary_directory), privacy="QUARANTINED"
            )

            with self.assertRaisesRegex(MediaError, "QUARANTINED"):
                register_default(workspace, captured, text_path)

            self.assertEqual(
                media_status(workspace, captured.source_id)[0].status, "NOT_INVESTIGATED"
            )

    def test_source_drift_is_visible_and_blocks_new_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            _, source = source_record(workspace, captured.source_id)
            original = workspace.joinpath(*Path(str(source["stored_path"])).parts)
            original.write_bytes(b"changed-media-same-size"[: captured.byte_count])

            report = verify_media(workspace, captured.source_id, registered.derivation_id)

            self.assertFalse(report.ok)
            self.assertEqual(report.entries[0].status, "STALE")
            with self.assertRaises(MediaError):
                register_default(workspace, captured, text_path)

    def test_review_accept_is_digest_bound_and_not_a_fact_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)

            reviewed, review_digest = accept_default(workspace, registered)

            self.assertEqual(reviewed.status, "REVIEWED")
            self.assertRegex(review_digest, r"^[0-9a-f]{64}$")
            entry = media_status(workspace, captured.source_id, registered.derivation_id)[0]
            self.assertEqual(entry.status, "REVIEWED")
            self.assertIn("NOT AUTOMATICALLY FACT", entry.statement)
            review = read_json(
                derivation_directory(workspace, captured.source_id, registered.derivation_id)
                / "review.json"
            )
            self.assertEqual(review["decision"], "ACCEPT")
            self.assertEqual(review["content_sha256"], registered.content_sha256)

    def test_review_reject_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            review_derivation(
                workspace,
                captured.source_id,
                registered.derivation_id,
                content_sha256=registered.content_sha256,
                decision="REJECT",
                findings=["Tekst wijkt af"],
                reviewer="ARCHITECT",
            )
            entry = media_status(workspace, captured.source_id, registered.derivation_id)[0]

            self.assertEqual(entry.status, "REJECTED")
            with self.assertRaisesRegex(MediaError, "REVIEWED"):
                promote_derivation(
                    workspace,
                    captured.source_id,
                    registered.derivation_id,
                    review_digest=entry.review_sha256 or "0" * 64,
                )

    def test_review_refuses_wrong_digest_and_second_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            with self.assertRaisesRegex(MediaError, "verschilt"):
                review_derivation(
                    workspace,
                    captured.source_id,
                    registered.derivation_id,
                    content_sha256="0" * 64,
                    decision="ACCEPT",
                    findings=["controle"],
                    reviewer="ARCHITECT",
                )
            accept_default(workspace, registered)

            with self.assertRaisesRegex(MediaError, "exact één review"):
                review_derivation(
                    workspace,
                    captured.source_id,
                    registered.derivation_id,
                    content_sha256=registered.content_sha256,
                    decision="ACCEPT",
                    findings=["tweede controle"],
                    reviewer="ARCHITECT",
                )

    def test_promotion_creates_normal_captured_source_with_exact_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            _, review_digest = accept_default(workspace, registered)

            promoted = promote_derivation(
                workspace,
                captured.source_id,
                registered.derivation_id,
                review_digest=review_digest,
            )

            self.assertEqual(promoted.status, "PROMOTED")
            self.assertIsNotNone(promoted.promoted_source_id)
            _, promoted_record = source_record(workspace, promoted.promoted_source_id or "")
            self.assertEqual(promoted_record["status"], "CAPTURED")
            self.assertEqual(promoted_record["privacy"], "PRIVATE")
            self.assertEqual(promoted_record["sha256"], registered.content_sha256)
            self.assertEqual(
                promoted_record["origin"],
                f"DERIVED:{registered.derivation_id};ORIGINAL:{captured.source_id}@{captured.sha256}",
            )
            entry = media_status(workspace, captured.source_id, registered.derivation_id)[0]
            self.assertEqual(entry.status, "PROMOTED")
            self.assertEqual(entry.promoted_source_id, promoted.promoted_source_id)
            self.assertTrue(verify_media(workspace, captured.source_id).ok)

    def test_promotion_requires_exact_review_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            accept_default(workspace, registered)

            with self.assertRaisesRegex(MediaError, "Reviewdigest verschilt"):
                promote_derivation(
                    workspace,
                    captured.source_id,
                    registered.derivation_id,
                    review_digest="0" * 64,
                )

            self.assertEqual(len(list((workspace / "SOURCES").glob("*/*/SRC-*"))), 1)

    def test_second_promoted_derivation_reuses_exact_captured_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            first = register_default(workspace, captured, text_path)
            _, first_review = accept_default(workspace, first)
            first_promotion = promote_derivation(
                workspace, captured.source_id, first.derivation_id, review_digest=first_review
            )
            second = register_derivation(
                workspace,
                captured.source_id,
                text_path,
                kind="TEXT_EXTRACTION",
                producer_class="HUMAN",
                producer="OWNER",
            )
            _, second_review = accept_default(workspace, second)

            second_promotion = promote_derivation(
                workspace, captured.source_id, second.derivation_id, review_digest=second_review
            )

            self.assertEqual(
                second_promotion.promoted_source_id, first_promotion.promoted_source_id
            )
            self.assertEqual(len(list((workspace / "SOURCES").glob("*/*/SRC-*"))), 2)
            self.assertTrue(verify_media(workspace, captured.source_id).ok)

    def test_remove_deletes_only_derived_content_and_keeps_tombstone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            record_path, source = source_record(workspace, captured.source_id)
            original = workspace.joinpath(*Path(str(source["stored_path"])).parts)
            original_before = original.read_bytes()

            removed = remove_derivation(
                workspace,
                captured.source_id,
                registered.derivation_id,
                record_digest=registered.record_sha256,
                content_sha256=registered.content_sha256,
                owner="OWNER",
            )

            self.assertEqual(removed.status, "REMOVED")
            directory = derivation_directory(
                workspace, captured.source_id, registered.derivation_id
            )
            self.assertFalse((directory / "content.txt").exists())
            self.assertTrue((directory / "record.json").is_file())
            self.assertTrue((directory / "removed.json").is_file())
            self.assertEqual(original.read_bytes(), original_before)
            self.assertTrue(record_path.is_file())
            self.assertEqual(media_status(workspace, captured.source_id)[0].status, "REMOVED")
            self.assertTrue(verify_media(workspace, captured.source_id).ok)

    def test_remove_promoted_derivation_keeps_promoted_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            _, review_digest = accept_default(workspace, registered)
            promoted = promote_derivation(
                workspace, captured.source_id, registered.derivation_id, review_digest=review_digest
            )
            promoted_record_path, _ = source_record(workspace, promoted.promoted_source_id or "")

            remove_derivation(
                workspace,
                captured.source_id,
                registered.derivation_id,
                record_digest=registered.record_sha256,
                content_sha256=registered.content_sha256,
                owner="OWNER",
            )

            self.assertTrue(promoted_record_path.is_file())
            entry = media_status(workspace, captured.source_id, registered.derivation_id)[0]
            self.assertEqual(entry.status, "REMOVED")
            self.assertEqual(entry.promoted_source_id, promoted.promoted_source_id)

    def test_remove_requires_exact_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)

            with self.assertRaisesRegex(MediaError, "verschillen"):
                remove_derivation(
                    workspace,
                    captured.source_id,
                    registered.derivation_id,
                    record_digest="0" * 64,
                    content_sha256=registered.content_sha256,
                    owner="OWNER",
                )

            directory = derivation_directory(
                workspace, captured.source_id, registered.derivation_id
            )
            self.assertTrue((directory / "content.txt").is_file())
            self.assertFalse((directory / "removed.json").exists())

    def test_renewal_uses_new_id_and_explicit_supersedes_relation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, captured, text_path = setup_media(parent)
            first = register_default(workspace, captured, text_path)
            text_path.write_text("Nieuwe afgeleide versie.\n", encoding="utf-8")

            second = register_derivation(
                workspace,
                captured.source_id,
                text_path,
                kind="OCR",
                producer_class="LOCAL_TOOL",
                producer="offline-tool 2",
                supersedes_derivation_id=first.derivation_id,
            )

            self.assertNotEqual(second.derivation_id, first.derivation_id)
            record = read_json(
                derivation_directory(workspace, captured.source_id, second.derivation_id)
                / "record.json"
            )
            self.assertEqual(record["supersedes_derivation_id"], first.derivation_id)
            self.assertEqual(len(media_status(workspace, captured.source_id)), 2)

    def test_content_drift_makes_status_stale_and_verify_fails_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            directory = derivation_directory(
                workspace, captured.source_id, registered.derivation_id
            )
            content = directory / "content.txt"
            content.write_text("Gemuteerde tekst.\n", encoding="utf-8")
            before = {path: path.read_bytes() for path in directory.iterdir() if path.is_file()}

            entry = media_status(workspace, captured.source_id, registered.derivation_id)[0]
            report = verify_media(workspace, captured.source_id, registered.derivation_id)

            self.assertEqual(entry.status, "STALE")
            self.assertFalse(report.ok)
            after = {path: path.read_bytes() for path in directory.iterdir() if path.is_file()}
            self.assertEqual(after, before)

    def test_unexpected_managed_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            registered = register_default(workspace, captured, text_path)
            directory = derivation_directory(
                workspace, captured.source_id, registered.derivation_id
            )
            (directory / "surprise.bin").write_bytes(b"unexpected")

            with self.assertRaisesRegex(MediaError, "onverwachte"):
                media_status(workspace, captured.source_id)

    def test_active_derived_bytes_count_toward_future_capture_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, captured, text_path = setup_media(
                parent, original_bytes=b"1234", derived_text="abcd"
            )
            set_budgets(workspace, source_bytes=10, storage_bytes=10)
            register_default(workspace, captured, text_path)
            extra = workspace / "INBOX" / "extra.bin"
            extra.write_bytes(b"xyz")

            with self.assertRaisesRegex(WorkspaceError, "opslagbudget"):
                capture_source(workspace, extra)

            self.assertEqual(len(list((workspace / "SOURCES").glob("*/*/SRC-*"))), 1)

    def test_registration_respects_combined_storage_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, captured, text_path = setup_media(
                parent, original_bytes=b"123456", derived_text="abcde"
            )
            set_budgets(workspace, source_bytes=10, storage_bytes=10)

            with self.assertRaisesRegex(MediaError, "opslagbudget"):
                register_default(workspace, captured, text_path)

            self.assertEqual(
                media_status(workspace, captured.source_id)[0].status, "NOT_INVESTIGATED"
            )

    def test_media_operations_do_not_modify_official_layers_until_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace, captured, text_path = setup_media(Path(temporary_directory))
            official_roots = ("CONTROL", "SOURCES", "CHAPTERS", "TASKS", "PLAYBOOKS", "ROLES")
            before = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for name in official_roots
                for path in (workspace / name).rglob("*")
                if path.is_file()
            }

            registered = register_default(workspace, captured, text_path)
            accept_default(workspace, registered)
            verify_media(workspace, captured.source_id)

            after = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for name in official_roots
                for path in (workspace / name).rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_cli_full_flow_is_explicit_and_verify_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace, captured, text_path = setup_media(parent)
            registered = run_cli(
                "workspace",
                "media",
                "register",
                captured.source_id,
                "--text",
                str(text_path),
                "--kind",
                "OCR",
                "--producer-class",
                "LOCAL_TOOL",
                "--producer",
                "offline-tool 1",
                "--locator",
                "pagina 1",
                "--root",
                str(workspace),
                cwd=parent,
            )
            self.assertEqual(registered.returncode, 0, registered.stderr)
            self.assertIn("REGISTERED:", registered.stdout)
            status_entry = media_status(workspace, captured.source_id)[0]
            reviewed = run_cli(
                "workspace",
                "media",
                "review",
                captured.source_id,
                status_entry.derivation_id or "",
                "--content-sha256",
                status_entry.content_sha256 or "",
                "--decision",
                "ACCEPT",
                "--finding",
                "handmatig gecontroleerd",
                "--reviewer",
                "ARCHITECT",
                "--root",
                str(workspace),
                cwd=parent,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            accepted = media_status(workspace, captured.source_id, status_entry.derivation_id)[0]
            promoted = run_cli(
                "workspace",
                "media",
                "promote",
                captured.source_id,
                status_entry.derivation_id or "",
                "--review-digest",
                accepted.review_sha256 or "",
                "--root",
                str(workspace),
                cwd=parent,
            )
            self.assertEqual(promoted.returncode, 0, promoted.stderr)
            self.assertIn("PROMOTED:", promoted.stdout)
            before_receipts = sorted((workspace / ".opencntx" / "receipts").glob("*.json"))
            verified = run_cli(
                "workspace",
                "media",
                "verify",
                captured.source_id,
                status_entry.derivation_id or "",
                "--root",
                str(workspace),
                cwd=parent,
            )
            after_receipts = sorted((workspace / ".opencntx" / "receipts").glob("*.json"))
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertIn("OK: media registration is exact", verified.stdout)
            self.assertEqual(after_receipts, before_receipts)


if __name__ == "__main__":
    unittest.main()
