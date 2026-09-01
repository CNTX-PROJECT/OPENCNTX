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

    def test_equal_version_requires_head_to_be_exact_tag_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            repository = self._repository(Path(temp_name), "1.1.0")
            responses = {
                ("tag", "--list", "v*"): "v1.1.0",
                ("rev-parse", "HEAD"): "b" * 40,
                ("rev-list", "-n", "1", "v1.1.0"): "a" * 40,
            }
            with (
                mock.patch.object(
                    release_version_gate,
                    "_git",
                    side_effect=lambda _repository, *arguments: responses[arguments],
                ),
                self.assertRaisesRegex(
                    release_version_gate.ReleaseVersionError,
                    "HEAD is not that release commit",
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
