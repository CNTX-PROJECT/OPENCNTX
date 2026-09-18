"""Directory scan failures must not produce partial storage measurements."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opencntx.lifecycle import LifecycleError, _safe_files
from opencntx.workspace import WorkspaceError, _derived_storage_bytes


class ScanFailClosedTests(unittest.TestCase):
    def test_derived_storage_measurement_fails_on_walk_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            derived = root / ".opencntx" / "derived"
            derived.mkdir(parents=True)

            def fail_walk(path: Path, **kwargs: object):
                onerror = kwargs.get("onerror")
                if not callable(onerror):
                    raise TypeError("derived storage walk must provide an error handler")
                onerror(PermissionError(13, "Permission denied", str(path / "unreadable")))
                yield from ()

            with (
                patch("opencntx.workspace.os.walk", side_effect=fail_walk),
                self.assertRaises(WorkspaceError) as raised,
            ):
                _derived_storage_bytes(root)

            self.assertEqual("derived_storage_unavailable", raised.exception.code)

    def test_managed_storage_inventory_fails_on_walk_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "CONTROL").mkdir()

            def fail_walk(path: Path, **kwargs: object):
                onerror = kwargs.get("onerror")
                if not callable(onerror):
                    raise TypeError("managed storage walk must provide an error handler")
                onerror(PermissionError(13, "Permission denied", str(path / "unreadable")))
                yield from ()

            with (
                patch("opencntx.lifecycle.os.walk", side_effect=fail_walk),
                self.assertRaises(LifecycleError) as raised,
            ):
                _safe_files(root)

            self.assertEqual("lifecycle_storage_changed", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
