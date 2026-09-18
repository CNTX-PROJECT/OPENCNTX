"""Fail-closed regressions for directory enumeration errors."""

from __future__ import annotations

import errno
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from opencntx.knowledge import (
    KnowledgeError,
    build_adoption_manifest,
    build_index,
    write_adoption_manifest,
)
from opencntx.search_index import build_search_index, search_full_text, search_index_status


def fail_walk(top: str | bytes | Path, **kwargs: object):
    onerror = kwargs.get("onerror")
    if not callable(onerror):
        raise TypeError("directory walk must provide an onerror handler")
    failed = Path(top) / "unreadable"
    onerror(PermissionError(errno.EACCES, "permission denied", str(failed)))
    yield from ()


class WalkErrorRegressions(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="ocx-walk-errors-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "README.md").write_text("# Source\n", encoding="utf-8")

    def test_reparse_point_entries_are_pruned_and_reported(self) -> None:
        link = self.root / "junction"
        link.mkdir()
        (link / "hidden.md").write_text("# Must stay outside scope\n", encoding="utf-8")

        def real_reparse_check(path: Path) -> bool:
            if path == link:
                return True
            from opencntx.knowledge_io import is_link_or_reparse

            return is_link_or_reparse(path)

        with patch("opencntx.knowledge.is_link_or_reparse", side_effect=real_reparse_check):
            metadata = build_index(self.root, _publish=False)
            adoption = build_adoption_manifest(self.root)
        self.assertNotIn("junction/hidden.md", {node["path"] for node in metadata["nodes"]})
        self.assertIn("LINK_PRESENT", {finding["code"] for finding in adoption["audit"]["findings"]})

        with patch("opencntx.search_index.is_link_or_reparse", side_effect=real_reparse_check):
            built = build_search_index(self.root, strict=True)
            if built.get("engine") == "sqlite-fts5-external-content":
                result = search_full_text(
                    Path(built["path"]), "hidden scope", root=self.root, max_tokens=500
                )
                self.assertEqual(result["results"], [])
            status = search_index_status(self.root)
            self.assertEqual(status["status"], "CURRENT")

    def test_reparse_helper_uses_windows_file_attributes(self) -> None:
        from opencntx.knowledge_io import is_link_or_reparse

        path = self.root / "junction"
        fake_info = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x0400)
        with patch.object(Path, "lstat", return_value=fake_info):
            self.assertTrue(is_link_or_reparse(path))

    def test_metadata_index_does_not_publish_after_scan_error(self) -> None:
        destination = self.root / ".opencntx" / "index-v1.json"
        build_index(self.root)
        before = destination.read_bytes()

        with (
            patch("opencntx.knowledge.os.walk", side_effect=fail_walk),
            self.assertRaisesRegex(KnowledgeError, "Source enumeration failed"),
        ):
            build_index(self.root)

        self.assertEqual(destination.read_bytes(), before)

    def test_adoption_preview_and_manifest_write_fail_closed(self) -> None:
        preview = build_adoption_manifest(self.root)
        previous = write_adoption_manifest(
            self.root, expected_manifest_digest=preview["manifest_digest"]
        )
        destination = self.root / ".opencntx" / "adoption-v1.json"
        before = destination.read_bytes()

        with patch("opencntx.knowledge.os.walk", side_effect=fail_walk):
            with self.assertRaisesRegex(KnowledgeError, "Source enumeration failed"):
                build_adoption_manifest(self.root)
            with self.assertRaisesRegex(KnowledgeError, "Source enumeration failed"):
                write_adoption_manifest(
                    self.root,
                    expected_manifest_digest=previous["manifest_digest"],
                )

        self.assertEqual(destination.read_bytes(), before)

    def test_search_build_preserves_index_and_status_never_reports_current(self) -> None:
        built = build_search_index(self.root)
        if built.get("engine") != "sqlite-fts5-external-content":
            self.skipTest("SQLite FTS5 is unavailable on this Python build.")
        destination = Path(built["path"])
        before = destination.read_bytes()

        with patch("opencntx.search_index.os.walk", side_effect=fail_walk):
            status = search_index_status(self.root, strict=False)
            self.assertEqual(status["status"], "STALE_SCOPE")
            self.assertIn("Source enumeration failed", status["reason"])
            with self.assertRaisesRegex(KnowledgeError, "Source enumeration failed"):
                build_search_index(self.root)

        self.assertEqual(destination.read_bytes(), before)
        self.assertEqual(search_index_status(self.root)["status"], "CURRENT")


if __name__ == "__main__":
    unittest.main()
