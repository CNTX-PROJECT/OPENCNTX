"""Fresh-process qualification of the new negotiated CLI routes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_presentation import BINDING, envelope

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


if __name__ == "__main__":
    unittest.main()
