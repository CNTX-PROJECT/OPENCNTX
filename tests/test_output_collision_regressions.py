"""Regression tests for index output paths colliding with project data or caches."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from opencntx.knowledge import KnowledgeError, build_index
from opencntx.search_index import build_search_index, search_index_status

ROOT = Path(__file__).resolve().parents[1]


class IndexOutputCollisionRegressions(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="ocx-output-collision-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "README.md"
        self.source_bytes = b"# Human-owned source\nKeep these exact bytes.\n"
        self.source.write_bytes(self.source_bytes)

    def cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "opencntx", *arguments],
            cwd=self.root,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUTF8": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )

    def prime_indexes(self) -> tuple[Path, Path]:
        legacy = self.root / ".opencntx" / "index-v1.json"
        built = build_search_index(self.root, legacy_output=legacy)
        return Path(built["path"]), legacy

    def assert_cli_rejected_without_mutation(
        self,
        result: subprocess.CompletedProcess[str],
        *,
        source_bytes: bytes,
        search_index: Path,
        search_bytes: bytes,
        legacy_index: Path,
        legacy_bytes: bytes,
    ) -> None:
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.source.read_bytes(), source_bytes)
        self.assertEqual(search_index.read_bytes(), search_bytes)
        self.assertEqual(legacy_index.read_bytes(), legacy_bytes)
        self.assertEqual(search_index_status(self.root)["status"], "CURRENT")

    def test_api_rejects_legacy_output_that_is_a_source_file(self) -> None:
        with self.assertRaises(KnowledgeError):
            build_index(self.root, output=self.source)

        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertFalse((self.root / ".opencntx" / "index-v1.json").exists())

    def test_api_rejects_v2_output_that_is_a_source_file(self) -> None:
        with self.assertRaises(KnowledgeError):
            build_search_index(self.root, index=self.source)

        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertFalse((self.root / ".opencntx" / "search-v2.sqlite").exists())

    def test_api_rejects_hardlink_alias_of_a_source_file(self) -> None:
        alias = self.root.parent / f"{self.root.name}-source-alias.md"
        self.addCleanup(alias.unlink, missing_ok=True)
        try:
            os.link(self.source, alias)
        except OSError as exc:
            self.skipTest(f"This filesystem cannot create a hard link: {exc}")

        with self.assertRaises(KnowledgeError):
            build_index(self.root, output=alias)

        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(alias.read_bytes(), self.source_bytes)

    def test_api_preserves_existing_non_text_project_files(self) -> None:
        binary = self.root / "owner-image.bin"
        original = b"\x00\x01owner data\xff"
        binary.write_bytes(original)

        with self.assertRaises(KnowledgeError):
            build_index(self.root, output=binary)
        with self.assertRaises(KnowledgeError):
            build_search_index(self.root, index=binary)

        self.assertEqual(binary.read_bytes(), original)

    def test_api_rejects_new_output_inside_managed_owner_storage(self) -> None:
        destination = self.root / ".opencntx" / "derived" / "unrelated.json"

        with self.assertRaises(KnowledgeError):
            build_index(self.root, output=destination)

        self.assertFalse(destination.exists())
        self.assertFalse(destination.parent.exists())

    def test_api_rejects_output_that_aliases_the_search_catalog(self) -> None:
        catalog = self.root / ".opencntx" / "catalog.sqlite"

        with self.assertRaises(KnowledgeError):
            build_index(self.root, output=catalog)

        self.assertFalse(catalog.exists())

    def test_api_rejects_the_metadata_store_directory_as_an_output(self) -> None:
        destination = self.root / ".opencntx"

        with self.assertRaises(KnowledgeError):
            build_index(self.root, output=destination)

        self.assertFalse(destination.exists())

    def test_cli_rejects_legacy_output_that_is_a_source_file(self) -> None:
        search_index, legacy_index = self.prime_indexes()
        search_bytes = search_index.read_bytes()
        legacy_bytes = legacy_index.read_bytes()

        result = self.cli(
            "knowledge",
            "index",
            "build",
            "--root",
            str(self.root),
            "--output",
            str(self.source),
        )

        self.assert_cli_rejected_without_mutation(
            result,
            source_bytes=self.source_bytes,
            search_index=search_index,
            search_bytes=search_bytes,
            legacy_index=legacy_index,
            legacy_bytes=legacy_bytes,
        )

    def test_api_rejects_legacy_output_aliasing_v2_search_index(self) -> None:
        search_index, legacy_index = self.prime_indexes()
        search_bytes = search_index.read_bytes()
        legacy_bytes = legacy_index.read_bytes()

        with self.assertRaises(KnowledgeError):
            build_search_index(
                self.root,
                index=search_index,
                legacy_output=search_index,
            )

        self.assertEqual(search_index.read_bytes(), search_bytes)
        self.assertEqual(legacy_index.read_bytes(), legacy_bytes)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(search_index_status(self.root)["status"], "CURRENT")

    def test_cli_rejects_legacy_output_aliasing_v2_search_index(self) -> None:
        search_index, legacy_index = self.prime_indexes()
        search_bytes = search_index.read_bytes()
        legacy_bytes = legacy_index.read_bytes()

        result = self.cli(
            "knowledge",
            "index",
            "build",
            "--root",
            str(self.root),
            "--output",
            str(search_index),
        )

        self.assert_cli_rejected_without_mutation(
            result,
            source_bytes=self.source_bytes,
            search_index=search_index,
            search_bytes=search_bytes,
            legacy_index=legacy_index,
            legacy_bytes=legacy_bytes,
        )


if __name__ == "__main__":
    unittest.main()
