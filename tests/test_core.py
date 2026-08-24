from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from opencntx.core import pack_project
from opencntx.lifecycle import LifecycleError


def write_config(root: Path) -> None:
    (root / "opencntx.toml").write_text(
        """[task]
goal = "Disk preflight"

[context]
include = ["README.md"]
required = ["README.md"]
exclude = []
max_files = 5
max_bytes = 10000
""",
        encoding="utf-8",
        newline="\n",
    )


class CoreLifecycleTests(unittest.TestCase):
    def test_pack_disk_preflight_blocks_before_temporary_or_final_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "README.md").write_text("# Test\n", encoding="utf-8")
            write_config(root)

            with (
                mock.patch(
                    "opencntx.lifecycle.shutil.disk_usage",
                    return_value=SimpleNamespace(total=100, used=100, free=0),
                ),
                self.assertRaises(LifecycleError) as context,
            ):
                pack_project(root)

            self.assertEqual(context.exception.code, "disk_space_insufficient")
            self.assertFalse((root / ".opencntx" / "latest").exists())
            self.assertEqual(list(root.glob(".opencntx/.building-*")), [])


if __name__ == "__main__":
    unittest.main()
