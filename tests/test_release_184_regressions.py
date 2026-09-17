"""Behavioral regressions from the independent 1.8.3 audit."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import opencntx.search_index as search_module
from opencntx.knowledge import (
    KnowledgeError,
    build_index,
    list_techniques,
    make_technique_card,
    save_technique,
)
from opencntx.search_index import (
    MAX_JSON_ITEMS,
    _json_fields,
    _snippet,
    build_search_index,
    search_delivery,
    search_full_text,
    search_index_status,
)


def card(identifier: str = "procedure", name: str = "Procedure") -> dict:
    return make_technique_card(
        technique_id=identifier,
        name=name,
        trigger="Test fixture",
        preconditions=[],
        steps=["Inspect"],
        tools=[],
        risks=[],
        outputs=[],
        source_digests=[],
    )


class Release184Regressions(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ocx-184-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "note.md"
        self.source.write_text("# Note\n\nneedle\n", encoding="utf-8")

    def build(self) -> Path:
        return Path(build_search_index(self.root)["path"])

    def test_unsafe_technique_identifiers_cannot_escape_or_alias(self) -> None:
        for identifier in ("../../escape", "CON", "foo:bar", "a/b", "a\\b", "a."):
            with self.subTest(identifier=identifier), self.assertRaises(KnowledgeError):
                save_technique(self.root, card(identifier))
        self.assertFalse((self.root / "escape.json").exists())

    def test_create_preserves_existing_and_update_requires_current_digest(self) -> None:
        old = card()
        destination = save_technique(self.root, old)
        before = destination.read_bytes()
        with self.assertRaises(KnowledgeError):
            save_technique(self.root, card(name="replacement"))
        self.assertEqual(destination.read_bytes(), before)
        updated = card(name="accepted update")
        save_technique(self.root, updated, expected_digest=old["card_digest"])
        with self.assertRaises(KnowledgeError):
            save_technique(self.root, old, expected_digest=old["card_digest"])
        self.assertEqual(json.loads(destination.read_bytes()), updated)

    def test_wrong_project_root_is_rejected(self) -> None:
        database = self.build()
        other = self.root / "other"
        other.mkdir()
        (other / "note.md").write_bytes(self.source.read_bytes())
        with self.assertRaises(KnowledgeError):
            search_full_text(database, "needle", root=other)

    def test_growing_source_never_exceeds_read_budget(self) -> None:
        database = self.build()
        self.source.write_text("needle" * 10000, encoding="utf-8")
        result = search_full_text(database, "needle", root=self.root, max_bytes=20)
        self.assertLessEqual(result["loaded_bytes"], 20)
        self.assertNotEqual(result["results"][0]["state"], "loaded")

    def test_total_output_budget_rejects_an_impossible_envelope(self) -> None:
        database = self.build()
        with self.assertRaises(KnowledgeError):
            search_full_text(database, "needle", root=self.root, max_tokens=1)

    def test_noop_preserves_database_bytes_and_mtime(self) -> None:
        database = self.build()
        before = database.read_bytes(), database.stat().st_mtime_ns
        result = build_search_index(self.root)
        self.assertEqual(result["stats"]["read_files"], 0)
        self.assertEqual((database.read_bytes(), database.stat().st_mtime_ns), before)

    def test_json_truncation_is_bounded_and_visible(self) -> None:
        state, paths, values, _ids = _json_fields(
            json.dumps({f"key{n}": n for n in range(MAX_JSON_ITEMS + 300)})
        )
        self.assertNotEqual(state, "VALID")
        self.assertLessEqual(len(paths.split()) + len(values.split()), MAX_JSON_ITEMS)

    def test_casefold_offsets_refer_to_original_source(self) -> None:
        text = "ß" * 100 + "\nneedle\n"
        snippet, start, end = _snippet(text, ["needle"], 15)
        self.assertIn("needle", snippet)
        self.assertLessEqual(start, 2)
        self.assertGreaterEqual(end, 2)

    def test_fts_corruption_is_not_current(self) -> None:
        database = self.build()
        connection = sqlite3.connect(database)
        try:
            connection.execute("INSERT INTO documents_fts(documents_fts) VALUES('delete-all')")
            connection.commit()
        finally:
            connection.close()
        self.assertNotEqual(search_index_status(self.root)["status"], "CURRENT")

    def test_old_publisher_cannot_replace_new_generation(self) -> None:
        database = self.build()
        old_write = search_module._write_database
        captured = []
        self.source.write_text("new generation needle", encoding="utf-8")
        with patch.object(
            search_module, "_write_database", side_effect=lambda *a, **kw: captured.append((a, kw))
        ):
            build_search_index(self.root)
        self.source.write_text("newest generation needle", encoding="utf-8")
        build_search_index(self.root)
        before = database.read_bytes()
        args, kwargs = captured[0]
        with self.assertRaises(KnowledgeError):
            old_write(*args, **kwargs)
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(search_index_status(self.root)["status"], "CURRENT")

    def test_secret_delivery_is_blocked_without_echoing_value(self) -> None:
        secret = "ghp_" + "Q" * 36
        self.source.write_text("needle " + secret, encoding="utf-8")
        database = self.build()
        with self.assertRaises(KnowledgeError) as caught:
            search_full_text(database, "needle", root=self.root)
        self.assertNotIn(secret, str(caught.exception))

    def test_proven_evidence_must_be_current(self) -> None:
        proven = card()
        proven["verification_state"] = "PROVEN"
        proven["source_digests"] = [hashlib.sha256(self.source.read_bytes()).hexdigest()]

        def seal(value):
            from opencntx.knowledge import _canonical_json, _digest

            value["card_digest"] = _digest(
                _canonical_json({k: v for k, v in value.items() if k != "card_digest"})
            )

        seal(proven)
        save_technique(self.root, proven)
        self.assertEqual(list_techniques(self.root)[0]["verification_state"], "PROVEN")
        self.source.write_text("changed", encoding="utf-8")
        self.assertEqual(list_techniques(self.root)[0]["verification_state"], "STALE")
        proven["source_digests"] = []
        seal(proven)
        with self.assertRaises(KnowledgeError):
            save_technique(self.root, proven)

    def test_exact_path_is_not_crowded_out(self) -> None:
        (self.root / "needle.md").write_text("unrelated", encoding="utf-8")
        for number in range(40):
            (self.root / f"a{number}.md").write_text("needle md " * 20, encoding="utf-8")
        database = self.build()
        result = search_full_text(database, "needle.md", root=self.root, max_results=1)
        self.assertEqual(result["results"][0]["path"], "needle.md")

    def test_bm25_order_survives_equal_metadata_scores(self) -> None:
        (self.root / "a.md").write_text("needle " + "irrelevant " * 500, encoding="utf-8")
        (self.root / "z.md").write_text("needle " * 10, encoding="utf-8")
        result = search_full_text(self.build(), "needle", root=self.root)
        paths = [row["path"] for row in result["results"]]
        self.assertLess(paths.index("z.md"), paths.index("a.md"))

    def test_source_traversal_in_tampered_database_cannot_load(self) -> None:
        database = self.build()
        connection = sqlite3.connect(database)
        try:
            connection.execute("UPDATE documents SET path='../outside.md'")
            connection.commit()
        finally:
            connection.close()
        result = search_full_text(database, "needle", root=self.root)
        self.assertTrue(all(item["state"] != "loaded" for item in result["results"]))

    def test_scope_and_unsupported_encoding_match_in_both_projections(self) -> None:
        (self.root / "build").mkdir()
        (self.root / "build" / "generated.md").write_text("generated", encoding="utf-8")
        (self.root / "invalid.md").write_bytes(bytes([255, 254, 0]))
        legacy = build_index(self.root)
        modern = build_search_index(self.root)
        self.assertEqual(legacy["stats"]["files"], modern["stats"]["files"])
        self.assertEqual(modern["stats"]["unsupported_encoding_files"], 1)

    def test_negated_prose_does_not_create_hard_relationship(self) -> None:
        self.source.write_text("This does not require [[b]].", encoding="utf-8")
        (self.root / "b.md").write_text("# B", encoding="utf-8")
        index = build_index(self.root)
        self.assertTrue(all(link["relation"] == "references" for link in index["links"]))

    def test_dual_projection_failure_keeps_both_old_files(self) -> None:
        legacy = self.root / ".opencntx" / "index-v1.json"
        database = Path(build_search_index(self.root, legacy_output=legacy)["path"])
        before = (database.read_bytes(), legacy.read_bytes())
        self.source.write_text("# Changed\nneedle replacement", encoding="utf-8")
        with (
            patch.object(search_module, "_atomic_json", side_effect=OSError("disk full")),
            self.assertRaises(KnowledgeError),
        ):
            build_search_index(self.root, legacy_output=legacy)
        self.assertEqual((database.read_bytes(), legacy.read_bytes()), before)
        self.assertEqual(search_index_status(self.root)["status"], "STALE")

    def test_shared_snapshot_reads_each_source_once_and_noop_writes_neither(self) -> None:
        legacy = self.root / ".opencntx" / "index-v1.json"
        with patch.object(search_module, "bounded_read", wraps=search_module.bounded_read) as read:
            database = Path(build_search_index(self.root, legacy_output=legacy)["path"])
        self.assertEqual(read.call_count, 1)
        before = [path.stat().st_mtime_ns for path in (database, legacy)]
        with patch.object(search_module, "bounded_read", wraps=search_module.bounded_read) as read:
            build_search_index(self.root, legacy_output=legacy)
        self.assertEqual(read.call_count, 0)
        self.assertEqual([path.stat().st_mtime_ns for path in (database, legacy)], before)

    def test_delivery_report_bounds_serialized_bytes_and_exposes_stale_scope(self) -> None:
        database = self.build()
        report = search_delivery(database, "needle", root=self.root, max_output_bytes=1200)
        wire = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self.assertLessEqual(len(wire.encode("utf-8")), 1200)
        self.assertFalse(report["absence_proven"])
        (self.root / "new.md").write_text("needle", encoding="utf-8")
        report = search_delivery(database, "absent", root=self.root)
        self.assertEqual(report["coverage"]["added"], ["new.md"])
        self.assertFalse(report["complete"])
        with self.assertRaises(KnowledgeError):
            search_delivery(database, "needle", root=self.root, max_output_bytes=1)

    def test_strict_rebuild_repairs_external_content_mismatch(self) -> None:
        database = self.build()
        connection = sqlite3.connect(database)
        try:
            connection.execute("UPDATE documents SET body='tampered'")
            connection.commit()
        finally:
            connection.close()
        self.assertNotEqual(search_index_status(self.root)["status"], "CURRENT")
        build_search_index(self.root, strict=True)
        self.assertEqual(search_index_status(self.root)["status"], "CURRENT")
        self.assertEqual(
            search_full_text(database, "needle", root=self.root)["results"][0]["state"], "loaded"
        )

    def test_linked_sources_and_cache_outputs_fail_closed(self) -> None:
        link = self.root / "alias.md"
        try:
            link.symlink_to(self.source)
        except OSError:
            self.skipTest("This host does not permit creating a symbolic link.")
        from opencntx.knowledge_io import bounded_read

        with self.assertRaises(KnowledgeError):
            bounded_read(self.root, "alias.md", 1000)
        with self.assertRaises(KnowledgeError):
            build_index(self.root, output=link)

    def test_old_empty_proven_card_is_readable_stale_and_can_be_corrected(self) -> None:
        from opencntx.knowledge import _canonical_json, _digest

        previous = card()
        previous["verification_state"] = "PROVEN"
        previous["card_digest"] = _digest(
            _canonical_json({key: value for key, value in previous.items() if key != "card_digest"})
        )
        store = self.root / ".opencntx" / "techniques"
        store.mkdir(parents=True)
        target = store / "procedure.json"
        before = _canonical_json(previous)
        target.write_bytes(before)
        recalled = list_techniques(self.root)[0]
        self.assertEqual(recalled["verification_state"], "STALE")
        self.assertEqual(target.read_bytes(), before)
        save_technique(self.root, card(name="Corrected"), expected_digest=recalled["card_digest"])
        self.assertEqual(list_techniques(self.root)[0]["name"], "Corrected")


if __name__ == "__main__":
    unittest.main()
