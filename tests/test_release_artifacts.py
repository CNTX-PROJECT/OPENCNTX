from __future__ import annotations

import io
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import release_artifacts


class ReleaseArtifactUnitTests(unittest.TestCase):
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
            "recursive-include src *.py",
            "recursive-include src/opencntx/schemas *.json",
            "recursive-include tests *.py",
            "recursive-include tools *.py",
        ):
            self.assertIn(line, manifest)

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
