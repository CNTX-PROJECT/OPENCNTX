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

    def test_actual_checkout_matches_the_published_runtime(self) -> None:
        from publication_maintenance import inspect_maintenance
        from release_version_gate import inspect_current_version_surfaces

        root = Path(__file__).resolve().parents[1]
        result = inspect_maintenance(root)
        self.assertEqual("RELEASE_RUNTIME_ALIGNED_MAINTENANCE", result["result"])
        self.assertFalse(result["artifact_equivalence_claimed"])
        self.assertEqual(12, inspect_current_version_surfaces(root)["surface_count"])

    def test_newer_stable_tag_blocks_stale_maintenance(self) -> None:
        from publication_maintenance import inspect_maintenance
        from release_version_gate import ReleaseVersionError, StableVersion

        root = Path(__file__).resolve().parents[1]
        with (
            patch(
                "publication_maintenance._stable_tags",
                return_value={StableVersion.parse("9.9.9"): "v9.9.9"},
            ),
            self.assertRaisesRegex(ReleaseVersionError, "latest stable"),
        ):
            inspect_maintenance(root)

    def test_runtime_diff_blocks_a_same_version_maintenance_claim(self) -> None:
        from publication_maintenance import inspect_maintenance
        from release_version_gate import ReleaseVersionError

        real_git = _module._git

        def changed_runtime(root: Path, *args: str) -> str:
            if args[:2] == ("diff", "--name-only"):
                return "src/opencntx/cli.py"
            return real_git(root, *args)

        with (
            patch("publication_maintenance._git", side_effect=changed_runtime),
            self.assertRaisesRegex(ReleaseVersionError, "runtime or packaging"),
        ):
            inspect_maintenance(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
