from __future__ import annotations

import io
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import release_artifacts


class ReleaseArtifactUnitTests(unittest.TestCase):
    def _write_candidate_record(self, root: Path) -> dict[str, Any]:
        wheel = root / "opencntx-1.0.0-py3-none-any.whl"
        sdist = root / "opencntx-1.0.0.tar.gz"
        wheel.write_bytes(b"wheel")
        sdist.write_bytes(b"sdist")
        artifacts = (wheel, sdist)
        release_artifacts._write_checksums(root, artifacts)
        record = release_artifacts._record(
            artifacts=artifacts,
            version="1.0.0",
            commit="a" * 40,
            tree="b" * 40,
            source_date_epoch=1,
            sdist_byte_reproducible=False,
        )
        (root / release_artifacts.RECORD_NAME).write_bytes(
            release_artifacts._canonical_json(record)
        )
        return record

    def test_exact_build_toolchain_is_accepted(self) -> None:
        versions = {"build": "1.3.0", "setuptools": "83.0.0"}
        with mock.patch.object(
            release_artifacts.importlib.metadata,
            "version",
            side_effect=versions.__getitem__,
        ):
            release_artifacts._validate_build_toolchain()

    def test_build_toolchain_drift_fails_before_subprocess(self) -> None:
        for distribution, actual_version in (
            ("setuptools", "80.9.0"),
            ("build", "1.2.2"),
        ):
            versions = {"build": "1.3.0", "setuptools": "83.0.0"}
            versions[distribution] = actual_version
            with (
                self.subTest(distribution=distribution),
                tempfile.TemporaryDirectory() as temp_name,
                mock.patch.object(
                    release_artifacts.importlib.metadata,
                    "version",
                    side_effect=versions.__getitem__,
                ),
                mock.patch.object(release_artifacts, "_run") as run,
                self.assertRaises(release_artifacts.ReleaseArtifactError),
            ):
                release_artifacts.build_candidate(
                    ROOT,
                    Path(temp_name) / "candidate",
                    expected_commit="a" * 40,
                    expected_tree="b" * 40,
                )
            run.assert_not_called()

    def test_missing_build_tool_fails_before_subprocess(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_name,
            mock.patch.object(
                release_artifacts.importlib.metadata,
                "version",
                side_effect=release_artifacts.importlib.metadata.PackageNotFoundError,
            ),
            mock.patch.object(release_artifacts, "_run") as run,
            self.assertRaisesRegex(
                release_artifacts.ReleaseArtifactError,
                "required build tool is not installed",
            ),
        ):
            release_artifacts.build_candidate(
                ROOT,
                Path(temp_name) / "candidate",
                expected_commit="a" * 40,
                expected_tree="b" * 40,
            )
        run.assert_not_called()

    def test_verify_candidate_accepts_exact_build_toolchain_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            record = self._write_candidate_record(root)
            artifacts = tuple(
                root / item["filename"] for item in record["artifacts"]
            )
            with mock.patch.object(
                release_artifacts,
                "_inspect_pair",
                return_value=artifacts,
            ):
                self.assertEqual(
                    record,
                    release_artifacts.verify_candidate(
                        root,
                        expected_version="1.0.0",
                        expected_commit="a" * 40,
                        expected_tree="b" * 40,
                    ),
                )

    def test_verify_candidate_rejects_each_build_toolchain_record_drift(self) -> None:
        for field, value in (
            ("build_frontend", "build==1.2.2"),
            ("build_backend", "setuptools==80.9.0"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp_name:
                root = Path(temp_name)
                record = self._write_candidate_record(root)
                artifacts = tuple(
                    root / item["filename"] for item in record["artifacts"]
                )
                record[field] = value
                (root / release_artifacts.RECORD_NAME).write_bytes(
                    release_artifacts._canonical_json(record)
                )
                with (
                    mock.patch.object(
                        release_artifacts,
                        "_inspect_pair",
                        return_value=artifacts,
                    ),
                    self.assertRaises(release_artifacts.ReleaseArtifactError),
                ):
                    release_artifacts.verify_candidate(
                        root,
                        expected_version="1.0.0",
                        expected_commit="a" * 40,
                        expected_tree="b" * 40,
                    )

    def test_safe_member_path_rejects_escape_and_platform_variants(self) -> None:
        for value in (
            "../escape",
            "safe/../../escape",
            "/absolute",
            "C:/absolute",
            "safe\\windows",
            "./relative",
            "safe/./relative",
            "nul\x00byte",
        ):
            with (
                self.subTest(value=value),
                self.assertRaises(release_artifacts.ReleaseArtifactError),
            ):
                release_artifacts._safe_member_path(value)
        self.assertEqual(
            "opencntx-0.2.0/src/opencntx/__init__.py",
            release_artifacts._safe_member_path(
                "opencntx-0.2.0/src/opencntx/__init__.py"
            ).as_posix(),
        )

    def test_zip_inventory_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive = Path(temp_name) / "bad.whl"
            member = zipfile.ZipInfo("opencntx/link")
            member.create_system = 3
            member.external_attr = 0o120777 << 16
            with zipfile.ZipFile(archive, "w") as wheel:
                wheel.writestr(member, "target")
            with self.assertRaises(release_artifacts.ReleaseArtifactError):
                release_artifacts._zip_inventory(archive)

    def test_zip_inventory_rejects_oversized_member_before_reading(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive = Path(temp_name) / "large.whl"
            member = zipfile.ZipInfo("opencntx/large.bin")
            member.file_size = release_artifacts.MAX_ARCHIVE_MEMBER_BYTES + 1
            with zipfile.ZipFile(archive, "w") as wheel:
                wheel.writestr(member, b"small stored body")
            # zipfile rewrites the declared size, so exercise the exact guard
            # through the constant without allocating an oversized buffer.
            original = release_artifacts.MAX_ARCHIVE_MEMBER_BYTES
            release_artifacts.MAX_ARCHIVE_MEMBER_BYTES = 1
            try:
                with self.assertRaises(release_artifacts.ReleaseArtifactError):
                    release_artifacts._zip_inventory(archive)
            finally:
                release_artifacts.MAX_ARCHIVE_MEMBER_BYTES = original

    def test_tar_inventory_rejects_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive = Path(temp_name) / "bad.tar.gz"
            with tarfile.open(archive, "w:gz") as sdist:
                member = tarfile.TarInfo("opencntx-0.2.0/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "target"
                sdist.addfile(member)
            with self.assertRaises(release_artifacts.ReleaseArtifactError):
                release_artifacts._tar_inventory(archive)

    def test_canonical_json_is_ascii_sorted_and_lf_terminated(self) -> None:
        encoded = release_artifacts._canonical_json({"z": "é", "a": 1})
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertNotIn(b"\r\n", encoded)
        self.assertEqual({"a": 1, "z": "é"}, json.loads(encoded))
        self.assertLess(encoded.index(b'"a"'), encoded.index(b'"z"'))

    def test_checksum_file_is_sorted_and_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            later = root / "z.tar.gz"
            earlier = root / "a.whl"
            later.write_bytes(b"later")
            earlier.write_bytes(b"earlier")
            release_artifacts._write_checksums(root, (later, earlier))
            lines = (
                (root / release_artifacts.CHECKSUMS_NAME).read_text(encoding="ascii").splitlines()
            )
            self.assertEqual(
                ["a.whl", "z.tar.gz"],
                [line.split("  ", 1)[1] for line in lines],
            )
            self.assertTrue(lines[0].endswith("  a.whl"))
            self.assertTrue(lines[1].endswith("  z.tar.gz"))

    def test_sdist_inventory_reads_regular_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive = Path(temp_name) / "sample.tar.gz"
            content = b"bounded source\n"
            with tarfile.open(archive, "w:gz") as sdist:
                member = tarfile.TarInfo("opencntx-0.2.0/README.md")
                member.size = len(content)
                sdist.addfile(member, io.BytesIO(content))
            self.assertEqual(
                {"opencntx-0.2.0/README.md": content},
                release_artifacts._tar_inventory(archive),
            )

    def test_manifest_declares_release_sources_and_excludes_bytecode(self) -> None:
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        for line in (
            "include LICENSE",
            "include README.md",
            "include pyproject.toml",
            "recursive-include docs *.md",
            "recursive-include examples *.json",
            "recursive-include src *.py",
            "recursive-include src/opencntx/schemas *.json",
            "recursive-include tests *.py",
            "recursive-include tools *.py",
        ):
            self.assertIn(line, manifest)
        self.assertIn("prune tests/r9_conformance", manifest)
        for historical_test in (
            "r9_runtime_simulator.py",
            "test_intake_autopilot.py",
            "test_project_runtime.py",
            "test_roadmap_guard.py",
            "test_roadmap_runtime.py",
            "test_runtime_contracts.py",
            "test_runtime_hooks.py",
            "test_storage_runtime.py",
        ):
            self.assertIn(f"exclude tests/{historical_test}", manifest)

    def test_tool_contains_no_network_or_publication_client(self) -> None:
        source = (TOOLS / "release_artifacts.py").read_text(encoding="utf-8")
        for forbidden in (
            "requests",
            "urllib",
            "twine",
            "gh release",
            "pypi.org",
            "upload-artifact",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
