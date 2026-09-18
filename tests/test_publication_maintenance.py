"""Negative controls for content-based publication maintenance, not a release bypass."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
import tomllib
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
        self.assertFalse(allowed_change("M", "pyproject.toml"))

    def test_post_release_pyproject_allows_only_the_published_state_transition(self) -> None:
        from publication_maintenance import _validate_release_metadata_transition
        from release_version_gate import ReleaseVersionError

        tagged = '''
[project]
name = "opencntx"
version = "1.8.6"
requires-python = ">=3.11"

[tool.opencntx.release]
published_version = "1.8.5"
status = "local-candidate"
'''
        published = tagged.replace(
            'published_version = "1.8.5"\nstatus = "local-candidate"',
            'published_version = "1.8.6"\nstatus = "published"',
        )
        _validate_release_metadata_transition(tagged, published, version="1.8.6")

        changed_packaging = published.replace('requires-python = ">=3.11"', 'requires-python = ">=3.12"')
        with self.assertRaisesRegex(ReleaseVersionError, "packaging metadata"):
            _validate_release_metadata_transition(tagged, changed_packaging, version="1.8.6")

        wrong_published_state = published.replace('published_version = "1.8.6"', 'published_version = "1.8.7"')
        with self.assertRaisesRegex(ReleaseVersionError, "exact published version"):
            _validate_release_metadata_transition(
                tagged,
                wrong_published_state,
                version="1.8.6",
            )

    def test_maintenance_accepts_the_exact_post_release_metadata_commit(self) -> None:
        from publication_maintenance import inspect_maintenance

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "docs").mkdir()
            candidate_project = '''
[project]
name = "opencntx"
version = "1.8.6"
requires-python = ">=3.11"

[tool.opencntx.release]
published_version = "1.8.5"
status = "local-candidate"
'''
            (root / "pyproject.toml").write_text(candidate_project, encoding="utf-8")
            (root / "docs" / "publication.json").write_text(
                json.dumps({
                    "format": "opencntx-publication-v1",
                    "version": "1.8.5",
                    "tag": "v1.8.5",
                    "source_commit": "previous-tag",
                }),
                encoding="utf-8",
            )
            (root / "docs" / "release-1.8.6.md").write_text(
                "# OPENCNTX 1.8.6\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Release test"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "release-test@example.invalid"],
                check=True,
                capture_output=True,
            )

            def commit_all(message: str) -> None:
                subprocess.run(
                    ["git", "-C", str(root), "add", "--all"],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "-C", str(root), "commit", "-m", message],
                    check=True,
                    capture_output=True,
                )

            commit_all("Prepare 1.8.6 candidate")
            tag_commit = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
            subprocess.run(
                ["git", "-C", str(root), "tag", "v1.8.6"], check=True, capture_output=True
            )
            (root / "pyproject.toml").write_text(
                candidate_project.replace(
                    'published_version = "1.8.5"\nstatus = "local-candidate"',
                    'published_version = "1.8.6"\nstatus = "published"',
                ),
                encoding="utf-8",
            )
            (root / "docs" / "publication.json").write_text(
                json.dumps({
                    "format": "opencntx-publication-v1",
                    "version": "1.8.6",
                    "tag": "v1.8.6",
                    "source_commit": tag_commit,
                }),
                encoding="utf-8",
            )
            commit_all("Record published 1.8.6 artifacts")

            result = inspect_maintenance(root)

        self.assertEqual("RELEASE_RUNTIME_ALIGNED_MAINTENANCE", result["result"])
        self.assertFalse(result["artifact_equivalence_claimed"])
        self.assertEqual("v1.8.6", result["latest_tag"])

    def test_runtime_and_unknown_changes_fail(self) -> None:
        for path in (
            "src/opencntx/cli.py",
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
        from release_version_gate import inspect_current_version_surfaces, inspect_release_version

        root = Path(__file__).resolve().parents[1]
        with (root / "pyproject.toml").open("rb") as project_file:
            project = tomllib.load(project_file)
        release = project["tool"]["opencntx"]["release"]
        version = project["project"]["version"]
        if release.get("status") == "local-candidate":
            result = inspect_release_version(root, expected_version=version)
            self.assertEqual("UNRELEASED_VERSION_AHEAD", result["result"])
            self.assertEqual(f"v{release['published_version']}", result["latest_tag"])
        else:
            result = inspect_maintenance(root)
            self.assertEqual("RELEASE_RUNTIME_ALIGNED_MAINTENANCE", result["result"])
            self.assertFalse(result["artifact_equivalence_claimed"])
        self.assertEqual(12, inspect_current_version_surfaces(root)["surface_count"])

    def test_newer_stable_tag_blocks_stale_maintenance(self) -> None:
        from publication_maintenance import inspect_maintenance
        from release_version_gate import ReleaseVersionError, StableVersion

        root = Path(__file__).resolve().parents[1]
        real_git = _module._git

        def clean_git(repository: Path, *arguments: str) -> str:
            if arguments[:2] == ("status", "--porcelain"):
                return ""
            return real_git(repository, *arguments)

        with (
            patch("publication_maintenance._git", side_effect=clean_git),
            patch("publication_maintenance._project_version", return_value=StableVersion.parse("1.8.5")),
            patch(
                "publication_maintenance._stable_tags",
                return_value={StableVersion.parse("9.9.9"): "v9.9.9"},
            ),
            self.assertRaisesRegex(ReleaseVersionError, "latest stable"),
        ):
            inspect_maintenance(root)

    def test_runtime_diff_blocks_a_same_version_maintenance_claim(self) -> None:
        from publication_maintenance import inspect_maintenance
        from release_version_gate import ReleaseVersionError, StableVersion

        real_git = _module._git

        def changed_runtime(root: Path, *args: str) -> str:
            if args[:2] == ("status", "--porcelain"):
                return ""
            if args[:2] == ("diff", "--name-only"):
                return "src/opencntx/cli.py"
            return real_git(root, *args)

        with (
            patch("publication_maintenance._git", side_effect=changed_runtime),
            patch("publication_maintenance._project_version", return_value=StableVersion.parse("1.8.5")),
            self.assertRaisesRegex(ReleaseVersionError, "runtime or packaging"),
        ):
            inspect_maintenance(Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
