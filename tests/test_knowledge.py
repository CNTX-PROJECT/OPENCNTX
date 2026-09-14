from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from opencntx.knowledge import (
    KnowledgeError,
    build_adoption_manifest,
    build_index,
    list_techniques,
    load_index,
    make_footer_contract,
    make_technique_card,
    render_footer,
    save_technique,
    search_index,
    write_adoption_manifest,
)


class KnowledgeIndexTests(unittest.TestCase):
    def _project(self) -> Path:
        temporary = Path(tempfile.mkdtemp(prefix="opencntx-knowledge-"))
        (temporary / "main").mkdir()
        (temporary / "main.md").write_text(
            "# Main\n\nSee [child](main/child.md).\n",
            encoding="utf-8",
        )
        (temporary / "main" / "child.md").write_text(
            "# Child\n\nA proven technique lives here.\n",
            encoding="utf-8",
        )
        (temporary / "roadmap.json").write_text(
            '{"topic": "technique", "state": "ready"}\n',
            encoding="utf-8",
        )
        return temporary

    def test_build_and_search_are_deterministic_and_hierarchical(self) -> None:
        root = self._project()
        try:
            first = build_index(root)
            second = build_index(root)
            self.assertEqual(first, second)
            by_path = {node["path"]: node for node in first["nodes"]}
            self.assertEqual(by_path["main/child.md"]["parent_id"], by_path["main.md"]["ocx_id"])
            self.assertEqual(first["links"][0]["reason"], "resolved")
            result = search_index(
                load_index(root / ".opencntx" / "index-v1.json"), "technique", max_bytes=1
            )
            self.assertEqual(result["format"], "ocx-search-result-v1")
            self.assertIn(result["results"][0]["state"], {"loaded", "skipped"})
            self.assertTrue(result["result_digest"])
        finally:
            import shutil

            shutil.rmtree(root)

    def test_tampered_index_fails_closed(self) -> None:
        root = self._project()
        try:
            build_index(root)
            path = root / ".opencntx" / "index-v1.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            value["nodes"][0]["title"] = "changed"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(KnowledgeError):
                load_index(path)
        finally:
            import shutil

            shutil.rmtree(root)

    def test_techniques_and_adoption_are_explicit_and_digest_bound(self) -> None:
        root = self._project()
        try:
            card = make_technique_card(
                technique_id="index-search",
                name="Exact-first search",
                trigger="A source must be found quickly",
                preconditions=["The index is current"],
                steps=["Build the index", "Search exact terms", "Inspect the reason codes"],
                tools=["opencntx knowledge index"],
                risks=["A stale index may omit a changed source"],
                outputs=["A bounded result manifest"],
                source_digests=["a" * 64],
                verification_state="PROVEN",
            )
            self.assertTrue(save_technique(root, card).is_file())
            self.assertEqual(list_techniques(root)[0]["verification_state"], "PROVEN")
            preview = build_adoption_manifest(root)
            self.assertEqual(preview["proposed_action"], "BIND_READ_ONLY")
            written = write_adoption_manifest(root)
            self.assertEqual(
                written, json.loads((root / ".opencntx" / "adoption-v1.json").read_text())
            )
            self.assertEqual(written, build_adoption_manifest(root))
        finally:
            import shutil

            shutil.rmtree(root)

    def test_footer_always_has_fallbacks_and_exact_profile(self) -> None:
        contract = make_footer_contract(profile="exact")
        rendered = render_footer(contract)
        self.assertIn("geen opdrachtnotitie", rendered)
        self.assertIn("niet gemeten", rendered)
        self.assertIn("contract_digest", rendered)
        self.assertTrue(contract["contract_digest"])


if __name__ == "__main__":
    unittest.main()
