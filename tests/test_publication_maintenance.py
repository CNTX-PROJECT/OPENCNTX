"""Negative controls for content-based publication maintenance, not a release bypass."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
_module = importlib.import_module("publication_maintenance")
allowed_change = _module.allowed_change


class MaintenanceBoundaryTests(unittest.TestCase):
    def test_current_docs_are_allowed(self) -> None:
        self.assertTrue(allowed_change("M", "README.md"))
        self.assertTrue(allowed_change("A", "docs/history.md"))
        self.assertTrue(allowed_change("M", "tools/release_version_gate.py"))

    def test_runtime_and_unknown_changes_fail(self) -> None:
        for path in (
            "src/opencntx/cli.py",
            "pyproject.toml",
            "MANIFEST.in",
            "LICENSE",
            "requirements-quality.txt",
            "tools/unknown.py",
            "../README.md",
        ):
            with self.subTest(path=path):
                self.assertFalse(allowed_change("M", path))

    def test_deletions_are_limited_to_retired_helpers(self) -> None:
        self.assertTrue(allowed_change("D", "tools/build_release_185.py"))
        self.assertFalse(allowed_change("M", "tools/build_release_185.py"))
        self.assertFalse(allowed_change("D", "docs/roadmap.md"))
        self.assertFalse(allowed_change("D", "tests/test_integrity.py"))

    def test_fixture_permission_is_exact(self) -> None:
        self.assertTrue(allowed_change("A", "tests/fixtures/release-baselines/manifest.json"))
        self.assertFalse(allowed_change("M", "tests/fixtures/v0.3.0/manifest.json"))
        self.assertFalse(allowed_change("A", "tests/fixtures/release-baselines/untrusted.whl"))

    def test_dirty_checkout_is_rejected_before_identity_claims(self) -> None:
        from publication_maintenance import inspect_maintenance
        from release_version_gate import ReleaseVersionError

        with (
            patch("publication_maintenance._git", return_value=" M README.md"),
            self.assertRaisesRegex(ReleaseVersionError, "clean"),
        ):
            inspect_maintenance(Path("."))


if __name__ == "__main__":
    unittest.main()
