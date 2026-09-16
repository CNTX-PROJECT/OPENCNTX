from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from opencntx.knowledge import KnowledgeError, build_adoption_manifest, write_adoption_manifest
from opencntx.project_planning import ContextSource, plan_context_load
from opencntx.search_index import (
    build_search_index,
    search_full_text,
    search_index_status,
)


class SearchIndexV2Tests(unittest.TestCase):
    def test_body_json_identifier_and_encoding_search(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opencntx-search-v2-") as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "# Guide\n\nA unique body-only canary is here.\n", encoding="utf-8"
            )
            (root / "records.json").write_text(
                json.dumps(
                    {
                        "record_id": "REC-001",
                        "metadata": {"runtime": {"feature": "json-field-canary"}},
                    }
                ),
                encoding="utf-8",
            )
            (root / "utf16.md").write_bytes("# UTF16\n\nEncoding canary.\n".encode("utf-16"))

            built = build_search_index(root, strict=True)
            self.assertEqual(built["status"], "SEARCH_INDEX_BUILT")
            self.assertEqual(built["stats"]["files"], 3)

            body = search_full_text(
                Path(built["path"]), "body-only canary", root=root, max_tokens=500
            )
            self.assertEqual(body["status"], "CURRENT_UNVERIFIED_SOURCE")
            self.assertEqual(body["results"][0]["path"], "docs/guide.md")
            self.assertEqual(body["results"][0]["state"], "loaded")
            self.assertIn("body-only", body["results"][0]["snippet"])

            json_result = search_full_text(
                Path(built["path"]), "json-field-canary", root=root, max_tokens=500
            )
            self.assertEqual(json_result["results"][0]["path"], "records.json")
            self.assertEqual(json_result["results"][0]["parse_status"], "VALID")
            self.assertIn("json_value_term", json_result["results"][0]["reason_codes"])

            identifier = search_full_text(Path(built["path"]), "REC-001", root=root, max_tokens=500)
            self.assertEqual(identifier["results"][0]["path"], "records.json")
            self.assertIn("exact_identifier", identifier["results"][0]["reason_codes"])

            encoding = search_full_text(
                Path(built["path"]), "Encoding canary", root=root, max_tokens=500
            )
            self.assertEqual(encoding["results"][0]["encoding"], "utf-16")
            self.assertEqual(search_index_status(root)["status"], "CURRENT")

    def test_incremental_refresh_and_strict_freshness(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opencntx-search-refresh-") as temporary:
            root = Path(temporary)
            source = root / "note.md"
            source.write_text("# Note\n\nold canary\n", encoding="utf-8")
            first = build_search_index(root, strict=True)
            second = build_search_index(root)
            self.assertEqual(second["stats"]["reused_files"], 1)
            self.assertEqual(search_index_status(root)["status"], "CURRENT")

            source.write_text("# Note\n\nnew canary\n", encoding="utf-8")
            self.assertEqual(search_index_status(root)["status"], "STALE")
            refreshed = build_search_index(root)
            self.assertEqual(refreshed["stats"]["read_files"], 1)
            self.assertNotEqual(first["source_tree_digest"], refreshed["source_tree_digest"])
            result = search_full_text(
                Path(refreshed["path"]), "new canary", root=root, max_tokens=500
            )
            self.assertEqual(result["results"][0]["state"], "loaded")

    def test_scope_fallback_and_failed_refresh_keep_previous_database(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opencntx-search-safety-") as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "docs" / "valid.md").write_text("# Valid\n", encoding="utf-8")
            (root / "malformed.json").write_text('{"broken":\n', encoding="utf-8")
            (root / "duplicate.json").write_text('{"id": 1, "id": 2}\n', encoding="utf-8")
            (root / "invalid.md").write_bytes(b"\xff\xfe\x00")
            (root / "build").mkdir()
            (root / "build" / "generated.md").write_text("generated", encoding="utf-8")
            built = build_search_index(root, strict=True)
            self.assertEqual(built["stats"]["files"], 4)
            self.assertEqual(built["stats"]["fallback_files"], 2)
            self.assertEqual(built["stats"]["unsupported_encoding_files"], 1)
            self.assertEqual(search_index_status(root)["status"], "PARTIAL")
            database = Path(built["path"])
            before = database.read_bytes()
            with self.assertRaises(KnowledgeError):
                build_search_index(root, max_bytes=1, strict=True)
            self.assertEqual(database.read_bytes(), before)

    def test_existing_unmanaged_adoption_is_broad_but_requires_reviewed_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opencntx-adoption-v2-") as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("# Existing project\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (root / "notes").mkdir()
            (root / "notes" / "decision.json").write_text(
                '{"decision": "preserve"}\n', encoding="utf-8"
            )
            preview = build_adoption_manifest(root)
            self.assertEqual(preview["audit"]["project_state"], "EXISTING_UNMANAGED_PARTIAL")
            self.assertEqual(preview["proposed_action"], "AUDIT_THEN_BIND")
            self.assertEqual(preview["audit"]["coverage"], "FULL_SUPPORTED_TEXT_SCOPE")
            self.assertEqual(
                {item["path"] for item in preview["records"]},
                {"README.md", "docs/guide.md", "notes/decision.json"},
            )
            with self.assertRaisesRegex(KnowledgeError, "reviewed preview digest"):
                write_adoption_manifest(root)
            written = write_adoption_manifest(
                root, expected_manifest_digest=preview["manifest_digest"]
            )
            self.assertEqual(written["proposed_action"], "AUDIT_THEN_BIND")

    def test_context_planning_enforces_optional_token_budget(self) -> None:
        required = ContextSource("step", 1, "a" * 64, 40, "CURRENT_STEP")
        optional = ContextSource("support", 1, "b" * 64, 40, "SUPPORTING")
        with self.assertRaisesRegex(ValueError, "token budget"):
            plan_context_load((required,), max_bytes=1_000, max_tokens=9)
        result = plan_context_load((required, optional), max_bytes=1_000, max_tokens=10)
        self.assertEqual(result["required_token_floor"], 10)
        self.assertEqual(result["estimated_loaded_tokens"], 10)
        self.assertEqual(result["token_budget_status"], "OK")
        self.assertEqual(result["skipped_source_ids"], ["support"])


if __name__ == "__main__":
    unittest.main()
