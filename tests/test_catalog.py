from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from opencntx.catalog import (
    LEGACY_REQUIRED_SECTIONS,
    REQUIRED_SECTIONS,
    CatalogError,
    create_chapter,
    rebuild_catalog,
)
from opencntx.workspace import capture_source, init_workspace


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


def chapter_path(workspace: Path, chapter_id: str) -> Path:
    return workspace / "CHAPTERS" / chapter_id / "CHAPTER.md"


def promote_chapter(workspace: Path, chapter_id: str) -> None:
    path = chapter_path(workspace, chapter_id)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'knowledge_status = "DRAFT"', 'knowledge_status = "OWNER_ACCEPTED"'
    ).replace(
        'last_owner_approval = ""',
        'last_owner_approval = "OWNER-TEST-REVISION-1"',
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def archive_chapter(workspace: Path, chapter_id: str) -> None:
    path = chapter_path(workspace, chapter_id)
    text = path.read_text(encoding="utf-8").replace(
        'knowledge_status = "DRAFT"', 'knowledge_status = "ARCHIVED"'
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def source_record(workspace: Path, source_id: str) -> tuple[Path, dict[str, object]]:
    matches = list((workspace / "SOURCES").glob(f"*/*/{source_id}/record.json"))
    assert len(matches) == 1
    return matches[0], read_json(matches[0])


def stored_original(workspace: Path, source_id: str) -> Path:
    _, record = source_record(workspace, source_id)
    return workspace.joinpath(*Path(str(record["stored_path"])).parts)


def catalog_value(workspace: Path, query: str, parameters: tuple[object, ...] = ()) -> object:
    with closing(sqlite3.connect(workspace / ".opencntx" / "catalog.sqlite")) as connection:
        row = connection.execute(query, parameters).fetchone()
    assert row is not None
    return row[0]


class CatalogTests(unittest.TestCase):
    def test_create_chapter_pins_exact_source_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "schema.txt"
            source.write_text("exacte bron", encoding="utf-8")
            captured = capture_source(workspace, source)
            index_before = (workspace / "CHAPTERS" / "INDEX.md").read_bytes()

            result = create_chapter(
                workspace,
                "CH-ELEKTRICITEIT",
                title="Elektriciteit",
                scope="Elektrische installatie.",
                source_ids=[captured.source_id],
            )

            self.assertEqual(result.status, "CHAPTER_CREATED")
            content = result.chapter_path.read_text(encoding="utf-8")
            self.assertIn('knowledge_status = "DRAFT"', content)
            self.assertIn(captured.source_id, content)
            self.assertIn(captured.sha256, content)
            self.assertEqual(content.count("## "), 9)
            before = result.chapter_path.read_bytes()
            with self.assertRaisesRegex(CatalogError, "bestaat al"):
                create_chapter(
                    workspace,
                    "CH-ELEKTRICITEIT",
                    title="Andere titel",
                )
            self.assertEqual(result.chapter_path.read_bytes(), before)
            self.assertEqual((workspace / "CHAPTERS" / "INDEX.md").read_bytes(), index_before)
            self.assertFalse((workspace / ".opencntx" / "catalog.sqlite").exists())

    def test_create_rejects_invalid_unknown_drifted_and_duplicate_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            with self.assertRaises(CatalogError):
                create_chapter(workspace, "chapter one", title="Fout")
            with self.assertRaisesRegex(CatalogError, "Onbekende bron"):
                create_chapter(
                    workspace,
                    "CH-ONBEKEND",
                    title="Onbekend",
                    source_ids=["SRC-20260816-000000000000"],
                )
            source = workspace / "INBOX" / "bron.txt"
            source.write_text("inhoud", encoding="utf-8")
            captured = capture_source(workspace, source)
            stored_original(workspace, captured.source_id).write_text("gewijzigd", encoding="utf-8")
            with self.assertRaisesRegex(CatalogError, "niet exact"):
                create_chapter(
                    workspace,
                    "CH-DRIFT",
                    title="Drift",
                    source_ids=[captured.source_id],
                )
            with self.assertRaisesRegex(CatalogError, "Dubbele --source"):
                create_chapter(
                    workspace,
                    "CH-DUBBEL",
                    title="Dubbel",
                    source_ids=[captured.source_id, captured.source_id],
                )
            with self.assertRaisesRegex(CatalogError, "Onbekend afhankelijk"):
                create_chapter(
                    workspace,
                    "CH-DEPENDENCY",
                    title="Dependency",
                    dependency_ids=["CH-ONTBREEKT"],
                )

    def test_empty_rebuild_is_valid_and_logically_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)

            first = rebuild_catalog(workspace)
            second = rebuild_catalog(workspace)

            self.assertEqual(first.state_digest, second.state_digest)
            self.assertEqual(first.chapter_count, 0)
            self.assertEqual(first.source_count, 0)
            self.assertEqual(second.freshness_counts["CURRENT"], 0)
            self.assertEqual(
                catalog_value(
                    workspace,
                    "SELECT value FROM catalog_meta WHERE key = 'workspace_state_digest'",
                ),
                second.state_digest,
            )
            self.assertEqual(
                catalog_value(
                    workspace,
                    "SELECT value FROM catalog_meta WHERE key = 'index_sha256'",
                ),
                hashlib.sha256(second.index_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(catalog_value(workspace, "PRAGMA integrity_check"), "ok")
            index = (workspace / "CHAPTERS" / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn(second.state_digest, index)
            self.assertIn("No chapters registered yet", index)
            receipt = read_json(second.receipt_path)
            self.assertEqual(receipt["status"], "CATALOG_REBUILT")
            completed = workspace / ".opencntx" / "transactions" / "completed"
            self.assertEqual(len(list(completed.iterdir())), 2)
            self.assertEqual(
                list((workspace / ".opencntx" / "transactions" / "locks").rglob("*.lock")), []
            )

    def test_owner_accepted_exact_chapter_becomes_current(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "plan.md"
            source.write_text("planinhoud", encoding="utf-8")
            captured = capture_source(workspace, source, privacy="RESTRICTED")
            create_chapter(
                workspace,
                "CH-PLAN",
                title="Plan",
                scope="Planonderdelen.",
                source_ids=[captured.source_id],
            )
            promote_chapter(workspace, "CH-PLAN")

            result = rebuild_catalog(workspace)

            self.assertEqual(result.freshness_counts["CURRENT"], 1)
            self.assertEqual(
                catalog_value(
                    workspace,
                    "SELECT freshness FROM chapters WHERE chapter_id = ?",
                    ("CH-PLAN",),
                ),
                "CURRENT",
            )
            self.assertEqual(
                catalog_value(
                    workspace,
                    "SELECT privacy FROM sources WHERE source_id = ?",
                    (captured.source_id,),
                ),
                "RESTRICTED",
            )
            index = result.index_path.read_text(encoding="utf-8")
            self.assertIn("| CH-PLAN | Plan |", index)
            self.assertIn("| CURRENT |", index)

    def test_draft_is_incomplete_and_explicit_archive_is_archived(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            create_chapter(workspace, "CH-DRAFT", title="Draft")

            draft_result = rebuild_catalog(workspace)
            self.assertEqual(draft_result.freshness_counts["INCOMPLETE"], 1)

            path = chapter_path(workspace, "CH-DRAFT")
            text = path.read_text(encoding="utf-8").replace(
                'knowledge_status = "DRAFT"',
                'knowledge_status = "OWNER_ACCEPTED"',
            )
            path.write_text(text, encoding="utf-8", newline="\n")
            missing_approval = rebuild_catalog(workspace)
            self.assertEqual(missing_approval.freshness_counts["INCOMPLETE"], 1)
            self.assertEqual(
                catalog_value(
                    workspace,
                    "SELECT code FROM catalog_issues WHERE object_id = 'CH-DRAFT'",
                ),
                "owner_approval_missing",
            )

            text = path.read_text(encoding="utf-8").replace(
                'knowledge_status = "OWNER_ACCEPTED"',
                'knowledge_status = "ARCHIVED"',
            )
            path.write_text(text, encoding="utf-8", newline="\n")
            archived_result = rebuild_catalog(workspace)
            self.assertEqual(archived_result.freshness_counts["ARCHIVED"], 1)
            self.assertEqual(archived_result.freshness_counts["INCOMPLETE"], 0)

    def test_superseded_and_drifted_sources_make_chapter_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "versie.txt"
            source.write_text("versie één", encoding="utf-8")
            first = capture_source(workspace, source)
            create_chapter(
                workspace,
                "CH-VERSIES",
                title="Versies",
                source_ids=[first.source_id],
            )
            promote_chapter(workspace, "CH-VERSIES")
            self.assertEqual(rebuild_catalog(workspace).freshness_counts["CURRENT"], 1)

            source.write_text("versie twee", encoding="utf-8")
            capture_source(workspace, source, supersedes=first.source_id)
            superseded = rebuild_catalog(workspace)
            self.assertEqual(superseded.freshness_counts["STALE"], 1)
            with closing(sqlite3.connect(workspace / ".opencntx" / "catalog.sqlite")) as connection:
                issue_codes = {
                    row[0] for row in connection.execute("SELECT code FROM catalog_issues")
                }
            self.assertIn("chapter_source_superseded", issue_codes)

            stored_original(workspace, first.source_id).write_text("drift", encoding="utf-8")
            drifted = rebuild_catalog(workspace)
            self.assertEqual(drifted.freshness_counts["STALE"], 1)
            self.assertEqual(
                catalog_value(
                    workspace,
                    "SELECT integrity FROM sources WHERE source_id = ?",
                    (first.source_id,),
                ),
                "DRIFTED",
            )

    def test_dependency_freshness_propagates_and_cycle_stops_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "basis.txt"
            source.write_text("basis", encoding="utf-8")
            captured = capture_source(workspace, source)
            create_chapter(
                workspace,
                "CH-BASIS",
                title="Basis",
                source_ids=[captured.source_id],
            )
            promote_chapter(workspace, "CH-BASIS")
            create_chapter(
                workspace,
                "CH-AFHANKELIJK",
                title="Afhankelijk",
                source_ids=[captured.source_id],
                dependency_ids=["CH-BASIS"],
            )
            promote_chapter(workspace, "CH-AFHANKELIJK")
            self.assertEqual(rebuild_catalog(workspace).freshness_counts["CURRENT"], 2)

            stored_original(workspace, captured.source_id).write_text("drift", encoding="utf-8")
            stale = rebuild_catalog(workspace)
            self.assertEqual(stale.freshness_counts["STALE"], 2)
            old_catalog = stale.catalog_path.read_bytes()

            basis = chapter_path(workspace, "CH-BASIS")
            text = basis.read_text(encoding="utf-8").replace(
                "dependency_ids = []",
                'dependency_ids = ["CH-AFHANKELIJK"]',
            )
            basis.write_text(text, encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(CatalogError, "cyclus"):
                rebuild_catalog(workspace)
            self.assertEqual(stale.catalog_path.read_bytes(), old_catalog)
            receipts = sorted((workspace / ".opencntx" / "receipts").glob("CAT-*.json"))
            self.assertEqual(read_json(receipts[-1])["status"], "CATALOG_NOT_REBUILT")

    def test_unknown_source_and_dependency_are_visible_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "bron.txt"
            source.write_text("bron", encoding="utf-8")
            captured = capture_source(workspace, source)
            create_chapter(
                workspace,
                "CH-ONVOLLEDIG",
                title="Onvolledig",
                source_ids=[captured.source_id],
            )
            promote_chapter(workspace, "CH-ONVOLLEDIG")
            path = chapter_path(workspace, "CH-ONVOLLEDIG")
            text = path.read_text(encoding="utf-8")
            text = text.replace(captured.source_id, "SRC-20260816-000000000000")
            text = text.replace("dependency_ids = []", 'dependency_ids = ["CH-ONTBREEKT"]')
            path.write_text(text, encoding="utf-8", newline="\n")

            result = rebuild_catalog(workspace)

            self.assertEqual(result.freshness_counts["INCOMPLETE"], 1)
            with closing(sqlite3.connect(result.catalog_path)) as connection:
                codes = {row[0] for row in connection.execute("SELECT code FROM catalog_issues")}
                source_links = connection.execute(
                    "SELECT COUNT(*) FROM chapter_sources"
                ).fetchone()[0]
            self.assertIn("chapter_source_unknown", codes)
            self.assertIn("chapter_dependency_unknown", codes)
            self.assertEqual(source_links, 0)

    def test_unmanaged_index_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            index = workspace / "CHAPTERS" / "INDEX.md"
            index.write_text("# Mijn unieke handmatige notitie\n", encoding="utf-8")
            before = index.read_bytes()

            with self.assertRaisesRegex(CatalogError, "niets overschreven"):
                rebuild_catalog(workspace)

            self.assertEqual(index.read_bytes(), before)
            self.assertFalse((workspace / ".opencntx" / "catalog.sqlite").exists())
            receipts = sorted((workspace / ".opencntx" / "receipts").glob("CAT-*.json"))
            self.assertEqual(len(receipts), 1)
            self.assertEqual(read_json(receipts[0])["status"], "CATALOG_NOT_REBUILT")

    def test_unknown_frontmatter_and_missing_section_stop_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            create_chapter(workspace, "CH-SCHEMA", title="Schema")
            path = chapter_path(workspace, "CH-SCHEMA")
            original = path.read_text(encoding="utf-8")
            path.write_text(
                original.replace("revision = 1", "revision = 1\nunexpected = true"),
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(CatalogError, "onbekende of ontbrekende"):
                rebuild_catalog(workspace)

            path.write_text(
                original.replace("## Freshness\n", "## Verkeerde sectie\n"),
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaisesRegex(CatalogError, "complete current or legacy"):
                rebuild_catalog(workspace)

    def test_manually_changed_generated_index_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            first = rebuild_catalog(workspace)
            catalog_before = first.catalog_path.read_bytes()
            first.index_path.write_text(
                first.index_path.read_text(encoding="utf-8") + "handmatige toevoeging\n",
                encoding="utf-8",
                newline="\n",
            )
            index_before = first.index_path.read_bytes()

            with self.assertRaisesRegex(CatalogError, "niets overschreven"):
                rebuild_catalog(workspace)

            self.assertEqual(first.index_path.read_bytes(), index_before)
            self.assertEqual(first.catalog_path.read_bytes(), catalog_before)

    def test_generated_index_detects_manual_change_without_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            first = rebuild_catalog(workspace)
            first.catalog_path.unlink()
            first.index_path.write_text(
                first.index_path.read_text(encoding="utf-8") + "handmatig\n",
                encoding="utf-8",
                newline="\n",
            )
            index_before = first.index_path.read_bytes()

            with self.assertRaisesRegex(CatalogError, "niets overschreven"):
                rebuild_catalog(workspace)

            self.assertEqual(first.index_path.read_bytes(), index_before)
            self.assertFalse(first.catalog_path.exists())

    def test_symlinked_chapter_is_rejected_when_platform_allows_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            create_chapter(workspace, "CH-LINK", title="Link")
            path = chapter_path(workspace, "CH-LINK")
            real = workspace / "INBOX" / "chapter-copy.md"
            real.write_bytes(path.read_bytes())
            path.unlink()
            try:
                path.symlink_to(real)
            except OSError as exc:
                self.skipTest(f"Symlinks zijn niet beschikbaar: {exc}")

            with self.assertRaisesRegex(CatalogError, "symlink"):
                rebuild_catalog(workspace)

    def test_deleted_or_corrupt_catalog_is_fully_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            create_chapter(workspace, "CH-LEEG", title="Leeg")
            first = rebuild_catalog(workspace)
            first.catalog_path.write_bytes(b"geen sqlite")

            second = rebuild_catalog(workspace)

            self.assertEqual(first.state_digest, second.state_digest)
            self.assertEqual(catalog_value(workspace, "PRAGMA integrity_check"), "ok")
            second.catalog_path.unlink()
            third = rebuild_catalog(workspace)
            self.assertEqual(third.state_digest, first.state_digest)
            self.assertTrue(third.catalog_path.is_file())

    def test_catalog_uses_parameters_and_does_not_copy_source_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            secret_content = "BRONINHOUD-DIE-NIET-IN-DE-CATALOGUS-MAG"
            source = workspace / "INBOX" / "bron.txt"
            source.write_text(secret_content, encoding="utf-8")
            captured = capture_source(workspace, source)
            title = "Titel | x'; DROP TABLE sources; --"
            create_chapter(
                workspace,
                "CH-INJECTIE",
                title=title,
                source_ids=[captured.source_id],
            )

            result = rebuild_catalog(workspace)

            self.assertEqual(
                catalog_value(
                    workspace,
                    "SELECT title FROM chapters WHERE chapter_id = ?",
                    ("CH-INJECTIE",),
                ),
                title,
            )
            self.assertEqual(catalog_value(workspace, "SELECT COUNT(*) FROM sources"), 1)
            self.assertNotIn(secret_content.encode("utf-8"), result.catalog_path.read_bytes())
            self.assertNotIn(secret_content, result.index_path.read_text(encoding="utf-8"))
            self.assertIn("Titel \\|", result.index_path.read_text(encoding="utf-8"))
            self.assertNotIn(str(workspace), result.receipt_path.read_text(encoding="utf-8"))

    def test_publish_failure_never_changes_official_sources_or_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            source = workspace / "INBOX" / "bron.txt"
            source.write_text("officieel", encoding="utf-8")
            captured = capture_source(workspace, source)
            create_chapter(
                workspace,
                "CH-OFFICIEEL",
                title="Officieel",
                source_ids=[captured.source_id],
            )
            official_before = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in list((workspace / "SOURCES").rglob("*"))
                + list((workspace / "CHAPTERS" / "CH-OFFICIEEL").rglob("*"))
                if path.is_file()
            }
            real_replace = os.replace

            def fail_index_publish(source_path: object, destination_path: object) -> None:
                destination = Path(destination_path)  # type: ignore[arg-type]
                if destination == workspace / "CHAPTERS" / "INDEX.md":
                    raise OSError("gesimuleerde indexfout")
                real_replace(source_path, destination_path)  # type: ignore[arg-type]

            with (
                mock.patch("opencntx.catalog.os.replace", side_effect=fail_index_publish),
                self.assertRaisesRegex(CatalogError, "niet volledig"),
            ):
                rebuild_catalog(workspace)

            official_after = {
                path.relative_to(workspace).as_posix(): path.read_bytes()
                for path in list((workspace / "SOURCES").rglob("*"))
                + list((workspace / "CHAPTERS" / "CH-OFFICIEEL").rglob("*"))
                if path.is_file()
            }
            self.assertEqual(official_after, official_before)
            receipts = sorted((workspace / ".opencntx" / "receipts").glob("CAT-*.json"))
            failure_receipt = read_json(receipts[-1])
            self.assertEqual(failure_receipt["status"], "CATALOG_NOT_REBUILT")
            self.assertEqual(failure_receipt["error_code"], "catalog_publish_failed")
            self.assertNotIn(str(workspace), receipts[-1].read_text(encoding="utf-8"))

    def test_cli_chapter_and_catalog_flow_is_bounded_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            initialized = run_cli("workspace", "init", cwd=workspace)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            source = workspace / "INBOX" / "bron.txt"
            source.write_text("bron", encoding="utf-8")
            captured = run_cli(
                "workspace",
                "capture",
                str(source),
                cwd=workspace,
            )
            self.assertEqual(captured.returncode, 0, captured.stderr)
            source_id_match = re.search(r"CAPTURED: (SRC-[0-9a-f-]+)", captured.stdout)
            self.assertIsNotNone(source_id_match)
            source_id = source_id_match.group(1)  # type: ignore[union-attr]

            chapter = run_cli(
                "workspace",
                "chapter",
                "create",
                "CH-CLI",
                "--title",
                "CLI-hoofdstuk",
                "--source",
                source_id,
                cwd=workspace,
            )
            rebuilt = run_cli(
                "workspace",
                "catalog",
                "rebuild",
                cwd=workspace,
            )

            self.assertEqual(chapter.returncode, 0, chapter.stderr)
            self.assertIn("CHAPTER_CREATED: CH-CLI", chapter.stdout)
            self.assertIn("grants no OWNER approval", chapter.stdout)
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertIn("CATALOG_REBUILT", rebuilt.stdout)
            self.assertIn("INCOMPLETE=1", rebuilt.stdout)
            self.assertTrue((workspace / ".opencntx" / "catalog.sqlite").is_file())

    def test_exact_legacy_chapter_headings_remain_valid_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            init_workspace(workspace)
            created = create_chapter(
                workspace,
                "CH-LEGACY",
                title="Legacy chapter",
                source_ids=[],
            )
            chapter = created.chapter_path
            text = chapter.read_text(encoding="utf-8")
            for current, legacy in zip(REQUIRED_SECTIONS, LEGACY_REQUIRED_SECTIONS):
                text = text.replace(f"## {current}\n", f"## {legacy}\n")
            chapter.write_text(text, encoding="utf-8", newline="\n")
            before = chapter.read_bytes()

            result = rebuild_catalog(workspace)

            self.assertEqual(result.status, "CATALOG_REBUILT")
            self.assertEqual(chapter.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
