"""Targeted product tests for the explicitly experimental owner preview."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from opencntx.cli import build_parser, main
from opencntx.cli_preview import serialize_preview_result
from opencntx.search_index import build_search_index


class OwnerPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ocx-owner-preview-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "notes.md"
        self.source.write_text("# Climate\n\nneedle: preserve these exact words.\n", encoding="utf-8")
        build_search_index(self.root, legacy_output=self.root / ".opencntx/index-v1.json")

    def invoke(self, arguments: list[str]) -> tuple[int, str, str]:
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            status = main(arguments)
        return status, output.getvalue(), error.getvalue()

    def test_serializer_preserves_unicode_and_all_fields(self) -> None:
        value = {"message": "café İstanbul 東京", "null": None, "list": [True, 2, {"k": "v"}]}
        pretty = serialize_preview_result(value)
        compact = serialize_preview_result(value, compact=True)
        self.assertEqual(json.loads(pretty), json.loads(compact))
        self.assertLess(len(compact.encode()), len(pretty.encode()))
        self.assertEqual(pretty, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def test_compact_cli_preserves_actual_search_result_and_digest(self) -> None:
        common = ["needle", "--root", str(self.root)]
        old = self.invoke(["knowledge", "index", "search", *common])
        new = self.invoke(["preview-search", *common, "--compact"])
        self.assertEqual(old[0], 0, old[2])
        self.assertEqual(new[0], 0, new[2])
        self.assertEqual(json.loads(old[1]), json.loads(new[1]))
        self.assertLess(len(new[1].encode()), len(old[1].encode()))

    def test_pretty_preview_is_byte_identical_to_existing_search(self) -> None:
        common = ["needle", "--root", str(self.root)]
        old = self.invoke(["knowledge", "index", "search", *common])
        new = self.invoke(["preview-search", *common])
        self.assertEqual(new, old)

    def test_delivery_report_limits_remain_enforced(self) -> None:
        args = ["preview-search", "needle", "--root", str(self.root), "--delivery-report", "--compact"]
        ok = self.invoke([*args, "--max-output-bytes", "6000"])
        self.assertEqual(ok[0], 0, ok[2])
        self.assertLessEqual(len(ok[1].encode()), 6000)
        value = json.loads(ok[1])
        self.assertIn("report_digest", value)
        blocked = self.invoke([*args, "--max-output-bytes", "1"])
        self.assertNotEqual(blocked[0], 0)
        self.assertEqual(blocked[1], "")

    def test_stale_source_is_not_delivered_and_source_is_not_modified(self) -> None:
        self.source.write_text("# Changed\nneedle: new content not yet indexed.\n", encoding="utf-8")
        before = self.source.read_bytes()
        result = self.invoke(["preview-search", "needle", "--root", str(self.root), "--compact"])
        self.assertEqual(result[0], 0, result[2])
        value = json.loads(result[1])
        self.assertTrue(value["results"])
        self.assertTrue(all(item["state"] == "stale_source" for item in value["results"]))
        self.assertTrue(all(item["snippet"] is None for item in value["results"]))
        self.assertEqual(self.source.read_bytes(), before)

    def test_compact_is_opt_in(self) -> None:
        args = build_parser().parse_args(["preview-search", "needle"])
        self.assertFalse(args.compact)
        args = build_parser().parse_args(["preview-search", "needle", "--compact"])
        self.assertTrue(args.compact)


if __name__ == "__main__":
    unittest.main()
