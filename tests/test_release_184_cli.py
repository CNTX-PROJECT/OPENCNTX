"""Fresh-process qualification of the new negotiated CLI routes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from opencntx.knowledge import list_techniques, save_technique
from tests.test_presentation import BINDING, envelope
from tests.test_release_184_regressions import card

ROOT = Path(__file__).resolve().parents[1]


class Release184CliTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="ocx-184-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

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

    def test_footer_context_binding_suppression_and_duplicate_keys(self) -> None:
        path = self.root / "envelope.json"
        path.write_text(json.dumps(envelope()), encoding="utf-8")
        args = [
            "knowledge",
            "footer",
            "--from-host-envelope-v2",
            str(path),
            "--session-id",
            BINDING["session_id"],
            "--context-generation",
            BINDING["context_generation"],
            "--source-digest",
            BINDING["source_digest"],
        ]
        rendered = self.cli(*args)
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        self.assertIn("**Model:** unknown", rendered.stdout)
        machine = self.cli(*args, "--output-kind", "json")
        self.assertEqual((machine.returncode, machine.stdout), (0, ""))
        rejected = self.cli(*args, "--context-generation", "NEW-CONTEXT")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn("Traceback", rejected.stderr)
        path.write_text('{"format":"duplicate",' + json.dumps(envelope())[1:], encoding="utf-8")
        rejected = self.cli(*args)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn("Traceback", rejected.stderr)

    def test_search_delivery_and_status_pages_preserve_negative_evidence(self) -> None:
        (self.root / "source.md").write_text("# Source\nneedle", encoding="utf-8")
        built = self.cli("knowledge", "index", "build")
        self.assertEqual(built.returncode, 0, built.stderr)
        for number in range(4):
            (self.root / f"new-{number}.md").write_text("needle", encoding="utf-8")
        page = self.cli("knowledge", "index", "status", "--limit", "2", "--offset", "1")
        self.assertEqual(page.returncode, 0, page.stderr)
        value = json.loads(page.stdout)
        self.assertEqual((value["total"], value["next_offset"], len(value["items"])), (4, 3, 2))
        report = self.cli("knowledge", "index", "search", "absent", "--delivery-report")
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertFalse(json.loads(report.stdout)["complete"])
        self.assertFalse(json.loads(report.stdout)["absence_proven"])
        rejected = self.cli("knowledge", "index", "search", "needle", "--max-tokens", "1")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn("Traceback", rejected.stderr)

    def test_two_process_technique_updates_have_exactly_one_winner(self) -> None:
        initial = card()
        save_technique(self.root, initial)
        paths = []
        for number in range(2):
            path = self.root / f"update-{number}.json"
            path.write_text(json.dumps(card(name=f"Writer {number}")), encoding="utf-8")
            paths.append(path)

        def update(path: Path):
            return self.cli(
                "knowledge",
                "technique",
                "add",
                "--input",
                str(path),
                "--expected-digest",
                initial["card_digest"],
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, paths))
        self.assertEqual(sum(result.returncode == 0 for result in results), 1)
        self.assertEqual(len(list_techniques(self.root)), 1)
        self.assertTrue(all("Traceback" not in result.stderr for result in results))

    def test_sanitized_pilot_retrieves_facts_after_process_restart(self) -> None:
        sources = {
            "configuration.yaml": "sensor:\n  - name: Living Room Temperature\n    unique_id: sensor.living_room_temperature\n    platform: mqtt\n",
            "decision.md": "# Current decision\nThe legacy MQTT route was replaced by WebSocket because duplicate updates occurred.\n",
            "change-policy.md": "# Safe change conditions\nPreserve unique_id and entity_id. Propose a YAML edit only; do not execute it.\n",
            "history.md": "# History\nOld MQTT settings are retained only for historical comparison.\n",
        }
        for name, text in sources.items():
            (self.root / name).write_text(text, encoding="utf-8")
        built = self.cli("knowledge", "index", "build")
        self.assertEqual(built.returncode, 0, built.stderr)
        questions = (
            ("sensor living room temperature", "configuration.yaml"),
            ("legacy MQTT replaced WebSocket duplicate updates", "decision.md"),
            ("preserve unique_id entity_id propose YAML", "change-policy.md"),
        )
        for query, expected in questions:
            # Each call is a fresh CLI process reading the same persisted index.
            result = self.cli("knowledge", "index", "search", query, "--delivery-report")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            loaded = [item["path"] for item in report["items"] if item["state"] == "loaded"]
            self.assertIn(expected, loaded)
        for name, text in sources.items():
            self.assertEqual((self.root / name).read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()
