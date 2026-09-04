from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import release_version_gate


class ReleaseVersionGateTests(unittest.TestCase):
    def _repository(self, root: Path, version: str) -> Path:
        (root / "pyproject.toml").write_text(
            f'[project]\nname = "opencntx"\nversion = "{version}"\n',
            encoding="utf-8",
        )
        return root

    def test_unreleased_version_must_be_ahead_of_latest_stable_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.1")
            responses = {
                ("tag", "--list", "v*"): "v1.0.0\nv1.1.0\nv1.1.0rc1",
                ("rev-parse", "HEAD"): "a" * 40,
            }
            with mock.patch.object(
                release_version_gate,
                "_git",
                side_effect=lambda _repository, *arguments: responses[arguments],
            ):
                result = release_version_gate.inspect_release_version(
                    repository,
                    expected_version="1.1.1",
                )
        self.assertEqual("v1.1.0", result["latest_tag"])
        self.assertEqual("UNRELEASED_VERSION_AHEAD", result["result"])

    def test_equal_version_rejects_non_documentation_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.0")
            responses = {
                ("tag", "--list", "v*"): "v1.1.0",
                ("rev-parse", "HEAD"): "b" * 40,
                ("rev-list", "-n", "1", "v1.1.0"): "a" * 40,
                ("merge-base", "--is-ancestor", "a" * 40, "b" * 40): "",
                (
                    "diff",
                    "--name-status",
                    "--no-renames",
                    "-z",
                    "a" * 40,
                    "b" * 40,
                ): "M\0src/opencntx/cli.py\0",
            }
            with (
                mock.patch.object(
                    release_version_gate,
                    "_git",
                    side_effect=lambda _repository, *arguments: responses[arguments],
                ),
                self.assertRaisesRegex(
                    release_version_gate.ReleaseVersionError,
                    "not docs-only",
                ),
            ):
                release_version_gate.inspect_release_version(repository)

    def test_exact_tag_commit_is_aligned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.0")
            commit = "a" * 40
            responses = {
                ("tag", "--list", "v*"): "v1.1.0",
                ("rev-parse", "HEAD"): commit,
                ("rev-list", "-n", "1", "v1.1.0"): commit,
            }
            with mock.patch.object(
                release_version_gate,
                "_git",
                side_effect=lambda _repository, *arguments: responses[arguments],
            ):
                result = release_version_gate.inspect_release_version(repository)
        self.assertEqual("TAG_ALIGNED", result["result"])
        self.assertEqual([], result["post_release_paths"])

    def test_equal_version_allows_documentation_and_exact_gate_support(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.0")
            tag_commit = "a" * 40
            head = "b" * 40
            changes = (
                "M\0README.md\0"
                "A\0docs/start-here.md\0"
                "M\0tools/release_version_gate.py\0"
                "M\0tests/test_release_version_gate.py\0"
                "M\0tests/test_quality.py\0"
            )
            responses = {
                ("tag", "--list", "v*"): "v1.1.0",
                ("rev-parse", "HEAD"): head,
                ("rev-list", "-n", "1", "v1.1.0"): tag_commit,
                ("merge-base", "--is-ancestor", tag_commit, head): "",
                (
                    "diff",
                    "--name-status",
                    "--no-renames",
                    "-z",
                    tag_commit,
                    head,
                ): changes,
            }
            with mock.patch.object(
                release_version_gate,
                "_git",
                side_effect=lambda _repository, *arguments: responses[arguments],
            ):
                result = release_version_gate.inspect_release_version(repository)
        self.assertEqual("POST_RELEASE_DOCS_ONLY", result["result"])
        self.assertEqual(
            [
                "README.md",
                "docs/start-here.md",
                "tests/test_quality.py",
                "tests/test_release_version_gate.py",
                "tools/release_version_gate.py",
            ],
            result["post_release_paths"],
        )

    def test_post_release_documentation_deletion_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.0")
            tag_commit = "a" * 40
            head = "b" * 40
            responses = {
                ("tag", "--list", "v*"): "v1.1.0",
                ("rev-parse", "HEAD"): head,
                ("rev-list", "-n", "1", "v1.1.0"): tag_commit,
                ("merge-base", "--is-ancestor", tag_commit, head): "",
                (
                    "diff",
                    "--name-status",
                    "--no-renames",
                    "-z",
                    tag_commit,
                    head,
                ): "D\0docs/removed.md\0",
            }
            with (
                mock.patch.object(
                    release_version_gate,
                    "_git",
                    side_effect=lambda _repository, *arguments: responses[arguments],
                ),
                self.assertRaisesRegex(
                    release_version_gate.ReleaseVersionError,
                    "not docs-only",
                ),
            ):
                release_version_gate.inspect_release_version(repository)

    def test_gate_support_without_documentation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.0")
            tag_commit = "a" * 40
            head = "b" * 40
            responses = {
                ("tag", "--list", "v*"): "v1.1.0",
                ("rev-parse", "HEAD"): head,
                ("rev-list", "-n", "1", "v1.1.0"): tag_commit,
                ("merge-base", "--is-ancestor", tag_commit, head): "",
                (
                    "diff",
                    "--name-status",
                    "--no-renames",
                    "-z",
                    tag_commit,
                    head,
                ): "M\0tools/release_version_gate.py\0",
            }
            with (
                mock.patch.object(
                    release_version_gate,
                    "_git",
                    side_effect=lambda _repository, *arguments: responses[arguments],
                ),
                self.assertRaisesRegex(
                    release_version_gate.ReleaseVersionError,
                    "requires a documentation path",
                ),
            ):
                release_version_gate.inspect_release_version(repository)

    def test_non_ancestor_stable_tag_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.0")
            tag_commit = "a" * 40
            head = "b" * 40

            def git_result(_repository: Path, *arguments: str) -> str:
                if arguments == ("tag", "--list", "v*"):
                    return "v1.1.0"
                if arguments == ("rev-parse", "HEAD"):
                    return head
                if arguments == ("rev-list", "-n", "1", "v1.1.0"):
                    return tag_commit
                if arguments == ("merge-base", "--is-ancestor", tag_commit, head):
                    raise release_version_gate.ReleaseVersionError("not an ancestor")
                raise AssertionError(arguments)

            with (
                mock.patch.object(release_version_gate, "_git", side_effect=git_result),
                self.assertRaisesRegex(
                    release_version_gate.ReleaseVersionError,
                    "not an ancestor of HEAD",
                ),
            ):
                release_version_gate.inspect_release_version(repository)

    def test_version_behind_latest_tag_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.0.0")
            responses = {
                ("tag", "--list", "v*"): "v1.1.0",
                ("rev-parse", "HEAD"): "a" * 40,
            }
            with (
                mock.patch.object(
                    release_version_gate,
                    "_git",
                    side_effect=lambda _repository, *arguments: responses[arguments],
                ),
                self.assertRaisesRegex(
                    release_version_gate.ReleaseVersionError,
                    "behind latest stable tag",
                ),
            ):
                release_version_gate.inspect_release_version(repository)

    def test_noncanonical_project_version_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.1rc1")
            with self.assertRaisesRegex(
                release_version_gate.ReleaseVersionError,
                "not a canonical stable version",
            ):
                release_version_gate.inspect_release_version(repository)


if __name__ == "__main__":
    unittest.main()
