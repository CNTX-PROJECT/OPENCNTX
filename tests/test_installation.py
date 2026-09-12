from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import unittest
import venv
from pathlib import Path

from opencntx import __version__
from opencntx.installation import InstallationError, file_sha256, inspect_runtime, verify_runtime


class InstallationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = self.root / "runtime"
        builder = venv.EnvBuilder(with_pip=False)
        builder.create(self.environment)
        context = builder.ensure_directories(self.environment)
        self.python = Path(context.env_exec_cmd)
        self.site = (
            self.environment / "Lib/site-packages"
            if os.name == "nt"
            else next((self.environment / "lib").glob("python*/site-packages"))
        )

    def metadata(self) -> Path:
        directory = self.site / f"opencntx-{__version__}.dist-info"
        directory.mkdir()
        (directory / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: opencntx\nVersion: {__version__}\n", encoding="utf-8"
        )
        (directory / "INSTALLER").write_text("pip\n", encoding="utf-8")
        (directory / "RECORD").write_text("", encoding="utf-8")
        return directory

    def test_absent_distribution_is_inventory_not_healthy(self) -> None:
        inventory = inspect_runtime(self.python)
        self.assertEqual("ABSENT", inventory["owner"])
        self.assertEqual([], inventory["packages"])
        self.assertFalse(inventory["writes_performed"])
        with self.assertRaises(InstallationError):
            verify_runtime(self.python, expected_version=__version__)

    def test_correct_metadata_but_crashing_package_cannot_report_health(self) -> None:
        self.metadata()
        package = self.site / "opencntx"
        package.mkdir()
        (package / "__init__.py").write_text(
            'raise RuntimeError("private diagnostic must not be printed")\n', encoding="utf-8"
        )
        self.assertEqual("PIP_VENV", inspect_runtime(self.python)["owner"])
        with self.assertRaises(InstallationError) as raised:
            verify_runtime(self.python, expected_version=__version__)
        self.assertNotIn("private diagnostic", str(raised.exception))

    def test_real_package_checkpoints_and_reopens_in_a_fresh_process(self) -> None:
        self.metadata()
        source = Path(__file__).resolve().parents[1] / "src/opencntx"
        shutil.copytree(
            source, self.site / "opencntx", ignore=shutil.ignore_patterns("__pycache__")
        )
        health = verify_runtime(self.python, expected_version=__version__)
        self.assertEqual("RUNTIME_HEALTHY", health["status"])
        self.assertIn("fresh-process-resume", health["checks"])
        self.assertFalse(health["existing_projects_verified"])
        with self.assertRaises(InstallationError):
            verify_runtime(self.python, expected_version="0.0.0")

    def test_direct_url_credentials_are_not_part_of_inventory(self) -> None:
        metadata = self.metadata()
        (metadata / "direct_url.json").write_text(
            '{"url":"https://user:PRIVATE@example.invalid/source","dir_info":{"editable":true}}',
            encoding="utf-8",
        )
        result = inspect_runtime(self.python)
        self.assertEqual("EDITABLE", result["owner"])
        self.assertNotIn("PRIVATE", str(result))

    def test_streaming_digest_matches_artifact_bytes(self) -> None:
        path = self.root / "artifact.whl"
        payload = b"artifact" * 300_000
        path.write_bytes(payload)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), file_sha256(path))


if __name__ == "__main__":
    unittest.main()
