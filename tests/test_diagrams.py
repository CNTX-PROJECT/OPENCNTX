from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools" / "render_diagrams.py"


class DiagramRendererTests(unittest.TestCase):
    def test_committed_light_and_dark_diagrams_match_the_shared_renderer(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONUTF8"] = "1"
        completed = subprocess.run(
            [sys.executable, str(RENDERER), "--check"],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("DOCUMENTATION_DIAGRAMS_OK", completed.stdout.strip())


if __name__ == "__main__":
    unittest.main()
