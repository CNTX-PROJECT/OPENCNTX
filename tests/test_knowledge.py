from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from io import StringIO
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


def run_knowledge_cli(arguments: list[str], *, cwd: Path) -> tuple[int, str, str]:
    from opencntx.cli import main

    stdout = StringIO()
    stderr = StringIO()
    with chdir(cwd), redirect_stdout(stdout), redirect_stderr(stderr):
        result = main(arguments)
    return result, stdout.getvalue(), stderr.getvalue()


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

    def test_cli_knowledge_routes_cover_build_search_technique_adoption_and_footer(self) -> None:
        root = self._project()
        try:
            built = run_knowledge_cli(
                ["knowledge", "index", "build", "--root", str(root)], cwd=root
            )
            self.assertEqual(built[0], 0, built[2])
            self.assertEqual(json.loads(built[1])["status"], "INDEX_BUILT")

            searched = run_knowledge_cli(
                [
                    "knowledge",
                    "index",
                    "search",
                    "technique",
                    "--index",
                    str(root / ".opencntx" / "index-v1.json"),
                ],
                cwd=root,
            )
            self.assertEqual(searched[0], 0, searched[2])
            self.assertEqual(json.loads(searched[1])["format"], "ocx-search-result-v1")

            card = make_technique_card(
                technique_id="cli-technique",
                name="CLI technique",
                trigger="A CLI route is exercised",
                preconditions=["The project exists"],
                steps=["Run the route"],
                tools=["opencntx"],
                risks=["A stale source"],
                outputs=["A receipt"],
                source_digests=["a" * 64],
            )
            card_path = root / "card.json"
            card_path.write_text(json.dumps(card), encoding="utf-8")
            added = run_knowledge_cli(
                ["knowledge", "technique", "add", "--root", str(root), "--input", str(card_path)],
                cwd=root,
            )
            self.assertEqual(added[0], 0, added[2])
            listed = run_knowledge_cli(
                ["knowledge", "technique", "list", "--root", str(root)], cwd=root
            )
            self.assertEqual(listed[0], 0, listed[2])
            self.assertEqual(len(json.loads(listed[1])["cards"]), 1)

            preview = run_knowledge_cli(["knowledge", "adopt", "--root", str(root)], cwd=root)
            written = run_knowledge_cli(
                ["knowledge", "adopt", "--root", str(root), "--write"], cwd=root
            )
            self.assertEqual(preview[0], 0, preview[2])
            self.assertEqual(written[0], 0, written[2])
            self.assertEqual(json.loads(written[1])["status"], "ADOPTION_MANIFEST_WRITTEN")

            for profile in ("commonmark", "portable", "plain"):
                footer = run_knowledge_cli(["knowledge", "footer", "--profile", profile], cwd=root)
                self.assertEqual(footer[0], 0, footer[2])
                self.assertIn("Opdracht", footer[1])
            exact = run_knowledge_cli(["knowledge", "footer", "--profile", "exact"], cwd=root)
            self.assertEqual(exact[0], 0, exact[2])
            self.assertIn("rendered_digest", json.loads(exact[1]))

            bad_input = root / "bad.json"
            bad_input.write_text("{", encoding="utf-8")
            failed = run_knowledge_cli(
                ["knowledge", "technique", "add", "--root", str(root), "--input", str(bad_input)],
                cwd=root,
            )
            self.assertEqual(failed[0], 2)
            self.assertIn("Technique card input cannot be read", failed[2])
        finally:
            import shutil

            shutil.rmtree(root)

    def test_validation_limits_links_adoption_kinds_and_footer_integrity(self) -> None:
        root = self._project()
        try:
            with self.assertRaises(KnowledgeError):
                build_index(root, max_files=0)
            with self.assertRaises(KnowledgeError):
                build_index(root, max_depth=1)
            with self.assertRaises(KnowledgeError):
                build_index(root, max_bytes=1)
            index = build_index(root)
            with self.assertRaises(KnowledgeError):
                search_index(index, "!!!")
            with self.assertRaises(KnowledgeError):
                search_index(index, "main", max_results=0)
            with self.assertRaises(KnowledgeError):
                search_index(index, "main", max_bytes=0)
            with self.assertRaises(KnowledgeError):
                load_index(root / "missing-index.json")

            card = make_technique_card(
                technique_id="validation",
                name="Validation",
                trigger="Validate a card",
                preconditions=["ready"],
                steps=["check"],
                tools=["tool"],
                risks=["risk"],
                outputs=["output"],
                source_digests=["b" * 64],
            )
            self.assertEqual(card["verification_state"], "PROPOSED")
            with self.assertRaises(KnowledgeError):
                make_technique_card(
                    technique_id="duplicate",
                    name="Duplicate",
                    trigger="bad",
                    preconditions=["same", "same"],
                    steps=["step"],
                    tools=["tool"],
                    risks=["risk"],
                    outputs=["output"],
                    source_digests=["b" * 64],
                )
            with self.assertRaises(KnowledgeError):
                make_technique_card(
                    technique_id="bad-digest",
                    name="Bad digest",
                    trigger="bad",
                    preconditions=["ready"],
                    steps=["check"],
                    tools=["tool"],
                    risks=["risk"],
                    outputs=["output"],
                    source_digests=["not-a-digest"],
                )
            empty = root / "empty"
            empty.mkdir()
            self.assertEqual(list_techniques(empty), [])
            with self.assertRaises(KnowledgeError):
                render_footer(make_footer_contract() | {"contract_digest": "tampered"})
            with self.assertRaises(KnowledgeError):
                make_footer_contract(profile="unsupported")
            self.assertIn("Opdracht:", render_footer(make_footer_contract(profile="plain")))

            for relative in (
                "CONTROL/ROADMAP.md",
                "TASKS/task.md",
                "PLAYBOOKS/playbook.md",
                "ROLES/role.md",
                "CHAPTERS/techniques/TECHNIQUES/card.md",
                "CHAPTERS/skill-guide.md",
                "CHAPTERS/agent-notes.md",
                "CHAPTERS/plugin-manifest.md",
                "INBOX/inbox.md",
                "opencntx.toml",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("content\n", encoding="utf-8")
            (root / ".opencntx" / "transactions").mkdir(parents=True, exist_ok=True)
            (root / ".opencntx" / "transactions" / "ignored.md").write_text(
                "ignored\n", encoding="utf-8"
            )
            manifest = build_adoption_manifest(root)
            kinds = {record["kind"] for record in manifest["records"]}
            self.assertTrue(
                {
                    "roadmap",
                    "task",
                    "playbook",
                    "role",
                    "technique",
                    "skill",
                    "agent",
                    "plugin",
                }.issubset(kinds)
            )
            self.assertNotIn(
                ".opencntx/transactions/ignored.md",
                {record["path"] for record in manifest["records"]},
            )
            with self.assertRaises(KnowledgeError):
                build_adoption_manifest(root, max_files=1)
        finally:
            import shutil

            shutil.rmtree(root)

    def test_links_cover_wiki_external_unresolved_and_contains_cycles(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opencntx-links-") as temporary_directory:
            root = Path(temporary_directory)
            (root / "a.md").write_text(
                "# A\n\nRequires [[b|B]] and [missing](missing.md).\nExternal [web](https://example.com).\n",
                encoding="utf-8",
            )
            (root / "b.md").write_text("# B\n\nA stable heading.\n", encoding="utf-8")
            index = build_index(root)
            self.assertEqual(len(index["links"]), 2)
            self.assertIn("unresolved_target", {link["reason"] for link in index["links"]})
            self.assertIn("requires", {link["relation"] for link in index["links"]})

            cycle_root = root / "cycle"
            cycle_root.mkdir()
            (cycle_root / "a.md").write_text("# A\nContains [B](b.md).\n", encoding="utf-8")
            (cycle_root / "b.md").write_text("# B\nContains [A](a.md).\n", encoding="utf-8")
            with self.assertRaises(KnowledgeError):
                build_index(cycle_root)


if __name__ == "__main__":
    unittest.main()
