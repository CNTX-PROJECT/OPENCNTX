from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from opencntx import core
from opencntx.core import OpenCntxError, pack_project
from opencntx.lifecycle import LifecycleError
from opencntx.security import SecretAssessment, SecretFinding


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


class CoreBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _write_config(
        self,
        *,
        include: str = 'include = ["README.md"]',
        required: str = 'required = ["README.md"]',
        extra: str = "",
    ) -> None:
        (self.root / "opencntx.toml").write_text(
            f'''[task]
goal = "Boundary test"

[context]
{include}
{required}
exclude = []
max_files = 5
max_bytes = 10000
{extra}
''',
            encoding="utf-8",
        )

    def _pack(self) -> tuple[Path, dict[str, object]]:
        (self.root / "README.md").write_text("# Test\n", encoding="utf-8")
        self._write_config()
        return pack_project(self.root)

    def test_pattern_and_configuration_boundaries(self) -> None:
        self.assertEqual(core._deduplicate(["a", "b", "a"]), ("a", "b"))
        self.assertEqual(core._normalize_pattern(" ./folder//file.txt ", "pattern"), "folder/file.txt")
        for value in (None, "", "./", "bad\x00name"):
            with self.subTest(value=value), self.assertRaises(OpenCntxError):
                core._normalize_pattern(value, "pattern")
        for value in ("/absolute", "C:\\absolute", "../outside"):
            with self.subTest(value=value), self.assertRaises(OpenCntxError):
                core._normalize_pattern(value, "pattern")
        with self.assertRaisesRegex(OpenCntxError, "literal relative"):
            core._normalize_relative_path("*.txt", "path")

        with self.assertRaisesRegex(OpenCntxError, "must be a list"):
            core._string_list({}, "include", allow_empty=True)
        with self.assertRaisesRegex(OpenCntxError, "must be a list"):
            core._string_list({"include": [1]}, "include", allow_empty=True)
        with self.assertRaisesRegex(OpenCntxError, "must not be empty"):
            core._string_list({"include": []}, "include", allow_empty=False)
        for integer_candidate in (True, 0, -1, "1"):
            with self.subTest(value=integer_candidate), self.assertRaises(OpenCntxError):
                core._positive_integer({"max_files": integer_candidate}, "max_files")

        context = {
            "include": ["README.md", "README.md"],
            "required": [],
            "exclude": ["custom/**"],
            "max_files": 2,
            "max_bytes": 20,
        }
        configured = core._config_from_tables(
            {"goal": "  Goal  "}, context, add_default_excludes=False
        )
        self.assertEqual(configured.goal, "Goal")
        self.assertEqual(configured.include, ("README.md",))
        self.assertEqual(configured.exclude, ("custom/**",))
        with self.assertRaisesRegex(OpenCntxError, "task.goal"):
            core._config_from_tables({}, context, add_default_excludes=True)

    def test_load_config_reports_each_structural_boundary(self) -> None:
        with self.assertRaisesRegex(OpenCntxError, "missing"):
            core.load_config(self.root)

        invalid_documents = {
            "invalid TOML": "[task\n",
            "Unknown TOML": "extra = 1\n[task]\ngoal='x'\n[context]\ninclude=['x']\nrequired=[]\nexclude=[]\nmax_files=1\nmax_bytes=1\n",
            "requires the": "[task]\ngoal='x'\n",
            "Unknown configuration": "[task]\ngoal='x'\nextra=1\n[context]\ninclude=['x']\nrequired=[]\nexclude=[]\nmax_files=1\nmax_bytes=1\n",
        }
        for expected, document in invalid_documents.items():
            with self.subTest(expected=expected):
                (self.root / "opencntx.toml").write_text(document, encoding="utf-8")
                with self.assertRaisesRegex(OpenCntxError, expected):
                    core.load_config(self.root)

        self._write_config()
        loaded = core.load_config(self.root)
        self.assertIn(".git/**", loaded.exclude)
        with (
            mock.patch.object(Path, "open", side_effect=OSError("unreadable")),
            self.assertRaisesRegex(OpenCntxError, "cannot be read"),
        ):
            core.load_config(self.root)

    def test_discovery_covers_excluded_ignored_and_required_paths(self) -> None:
        (self.root / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "skip.txt").write_text("skip", encoding="utf-8")
        (self.root / "folder").mkdir()
        (self.root / ".opencntx").mkdir()
        (self.root / ".opencntx" / "hidden.txt").write_text("hidden", encoding="utf-8")
        config = core.ContextConfig(
            goal="Discover",
            include=("*.txt", "folder", "missing*", ".opencntx/**"),
            required=("a.txt",),
            exclude=("skip.txt", ".opencntx/**"),
            max_files=10,
            max_bytes=100,
        )
        selection = core.discover_sources(self.root, config, enforce_required=True)
        self.assertEqual([path for path, _ in selection.files], ["a.txt"])
        self.assertEqual(selection.excluded[0]["path"], "skip.txt")
        self.assertEqual(
            {item["reason"] for item in selection.ignored},
            {"directory is not a text source", "include pattern matched no path"},
        )
        self.assertEqual(selection.included[0].required_by, ("a.txt",))

        missing_required = core.ContextConfig(
            goal="Discover",
            include=("a.txt",),
            required=("missing.txt",),
            exclude=(),
            max_files=10,
            max_bytes=100,
        )
        with self.assertRaisesRegex(OpenCntxError, "Required pattern"):
            core.discover_sources(self.root, missing_required, enforce_required=True)
        with (
            mock.patch.object(Path, "glob", side_effect=OSError("glob failed")),
            self.assertRaisesRegex(OpenCntxError, "cannot be expanded"),
        ):
            core._expand(self.root, "*.txt")

    def test_source_reading_and_budget_failures_are_explicit(self) -> None:
        source_path = self.root / "source.txt"
        source_path.write_text("text\n", encoding="utf-8", newline="\n")
        source = core._read_source(self.root, "source.txt", byte_budget=20)
        self.assertEqual(source.byte_count, 5)
        self.assertEqual(source.sha256, hashlib.sha256(b"text\n").hexdigest())

        for path, content, expected in (
            ("binary.txt", b"text\x00data", "Binary source"),
            ("control.txt", b"text\x01data", "Binary source"),
            ("invalid.txt", b"\xff", "valid UTF-8"),
        ):
            (self.root / path).write_bytes(content)
            with self.subTest(path=path), self.assertRaisesRegex(OpenCntxError, expected):
                core._read_source(self.root, path)
        with self.assertRaisesRegex(OpenCntxError, "literal relative"):
            core._read_source(self.root, "*.txt")
        with self.assertRaisesRegex(OpenCntxError, "missing or inaccessible"):
            core._read_source(self.root, "missing.txt")
        with self.assertRaisesRegex(OpenCntxError, "before reading"):
            core._read_source(self.root, "source.txt", byte_budget=4)
        with (
            mock.patch.object(Path, "read_bytes", side_effect=OSError("read failed")),
            self.assertRaisesRegex(OpenCntxError, "cannot be read"),
        ):
            core._read_source(self.root, "source.txt")

        empty = core.Selection(files=(), excluded=(), ignored=())
        config = core.ContextConfig("g", ("*.txt",), (), (), 1, 4)
        with self.assertRaisesRegex(OpenCntxError, "No text sources"):
            core.read_sources(self.root, empty, config)
        two_files = core.Selection(
            files=(("a", source_path), ("b", source_path)), excluded=(), ignored=()
        )
        with self.assertRaisesRegex(OpenCntxError, "File budget"):
            core.read_sources(self.root, two_files, config)
        oversized = core.Source("source.txt", b"12345", "12345", "0" * 64)
        one_file = core.Selection(files=(("source.txt", source_path),), excluded=(), ignored=())
        with (
            mock.patch.object(core, "_read_source", return_value=oversized),
            self.assertRaisesRegex(OpenCntxError, "Byte budget exceeded"),
        ):
            core.read_sources(self.root, one_file, config)

    def test_render_preview_manifest_and_plan_error_paths(self) -> None:
        finding = SecretFinding("a" * 64, "synthetic", "WARNING", "a.txt", 1, 1)
        security = SecretAssessment((finding,), (), (finding,))
        source = core.Source("a.txt", b"````\n", "````\n", hashlib.sha256(b"````\n").hexdigest())
        selection = core.Selection(
            files=(("a.txt", self.root / "a.txt"),),
            included=(core.IncludedPath("a.txt", "*.txt", ("a.txt",)),),
            excluded=({"path": "x", "pattern": "x", "reason": "excluded"},),
            ignored=({"pattern": "missing*", "reason": "no match"},),
        )
        config = core.ContextConfig("Goal", ("*.txt",), ("a.txt",), (), 2, 100)
        plan = core.PackPlan(config, selection, (source,), security)
        preview = core.format_pack_preview(plan)
        self.assertIn("required=a.txt", preview)
        self.assertIn("warnings (1)", preview)
        self.assertIn("result: PACK_WOULD_SUCCEED", preview)
        self.assertIn("## Task", core.render_context("Goal", (source,)))
        self.assertIn("## Taak", core.render_context("Goal", (source,), legacy=True))
        self.assertIn("`````text", core.render_context("Goal", (source,)))
        self.assertIn("Secret policy blocks", str(core._blocked_secret_error((finding,))))
        self.assertNotIn("security", core._manifest(config, selection, (source,), b"context"))
        self.assertIn("security", core._manifest(config, selection, (source,), b"context", security))

        (self.root / "README.md").write_text("# Test\n", encoding="utf-8")
        self._write_config()
        with (
            mock.patch.object(core, "assess_findings", side_effect=ValueError("stale")),
            self.assertRaisesRegex(OpenCntxError, "stale"),
        ):
            core.plan_project(self.root)

    def test_atomic_package_failures_leave_no_partial_output(self) -> None:
        output = self.root / ".opencntx"
        output.mkdir()
        (output / "latest").write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(OpenCntxError, "not a package directory"):
            core._atomic_package_write(self.root, b"context", b"{}")
        (output / "latest").unlink()
        with (
            mock.patch.object(core, "_write_file", side_effect=OSError("write failed")),
            self.assertRaisesRegex(OpenCntxError, "could not be written atomically"),
        ):
            core._atomic_package_write(self.root, b"context", b"{}")
        self.assertEqual(list(output.glob(".building-*")), [])

    def test_manifest_loading_and_source_metadata_fail_closed(self) -> None:
        with self.assertRaisesRegex(OpenCntxError, "missing or inaccessible"):
            core._load_manifest(self.root / "missing")
        wrong = self.root / "wrong"
        wrong.mkdir()
        (wrong / "manifest.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(OpenCntxError, "directly below"):
            core._load_manifest(wrong)

        package, _ = self._pack()
        manifest_path = package / "manifest.json"
        original = manifest_path.read_text(encoding="utf-8")
        variants = (
            ("{", "invalid or unreadable"),
            ("[]", "valid object structure"),
            ('{"format":"wrong","format_version":1}', "unknown format"),
            ('{"format":"opencntx-manifest","format_version":1}', "missing task"),
        )
        for content, expected in variants:
            with self.subTest(expected=expected):
                manifest_path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(OpenCntxError, expected):
                    core._load_manifest(package)
        manifest_path.write_text(original, encoding="utf-8")
        manifest_path.unlink()
        with self.assertRaisesRegex(OpenCntxError, "manifest.json is missing"):
            core._load_manifest(package)

        invalid_source_lists: tuple[tuple[dict[str, Any], str], ...] = (
            ({}, "valid source list"),
            ({"sources": ["bad"]}, "invalid source record"),
            ({"sources": [{"path": "a", "bytes": True, "sha256": "0" * 64}]}, "invalid metadata"),
            (
                {
                    "sources": [
                        {"path": "a", "bytes": 1, "sha256": "0" * 64},
                        {"path": "a", "bytes": 1, "sha256": "0" * 64},
                    ]
                },
                "duplicate source",
            ),
        )
        for value, expected in invalid_source_lists:
            with self.subTest(expected=expected), self.assertRaisesRegex(OpenCntxError, expected):
                core._expected_sources(value)

    def test_manifest_security_metadata_boundaries(self) -> None:
        source = core.Source("a.txt", b"safe", "safe", hashlib.sha256(b"safe").hexdigest())
        current = {"a.txt": source}
        self.assertEqual(core._manifest_security_errors({}, current), ())
        invalid: tuple[tuple[dict[str, Any], str], ...] = (
            ({"security": []}, "invalid security metadata"),
            ({"security": {}}, "invalid security metadata"),
            (
                {"security": {"policy_version": 99, "warnings": [], "overrides": []}},
                "unknown secret policy",
            ),
            (
                {"security": {"policy_version": 1, "warnings": {}, "overrides": []}},
                "invalid security metadata",
            ),
            (
                {"security": {"policy_version": 1, "warnings": ["bad"], "overrides": []}},
                "invalid security metadata",
            ),
            (
                {
                    "security": {
                        "policy_version": 1,
                        "warnings": [],
                        "overrides": [{"finding_id": 1}],
                    }
                },
                "invalid override data",
            ),
        )
        for manifest, expected in invalid:
            with self.subTest(expected=expected):
                self.assertIn(expected, core._manifest_security_errors(manifest, current)[0])

        stale_override = {
            "security": {
                "policy_version": 1,
                "warnings": [],
                "overrides": [{"finding_id": "0" * 64}],
            }
        }
        self.assertIn("invalid override", core._manifest_security_errors(stale_override, current)[0])
        mismatched = {"security": {"policy_version": 1, "warnings": [], "overrides": []}}
        self.assertEqual(core._manifest_security_errors(mismatched, current), ())

        secret_text = "-----BEGIN " + "PRIVATE KEY-----\n"
        secret = core.Source(
            "secret.txt",
            secret_text.encode(),
            secret_text,
            hashlib.sha256(secret_text.encode()).hexdigest(),
        )
        self.assertIn(
            "missing a required secret block",
            core._manifest_security_errors(mismatched, {"secret.txt": secret})[0],
        )

    def test_verify_reports_changed_missing_unexpected_and_context_drift(self) -> None:
        (self.root / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "b.txt").write_text("b", encoding="utf-8")
        self._write_config(include='include = ["*.txt"]', required="required = []")
        package, _ = pack_project(self.root)
        (self.root / "a.txt").write_text("changed", encoding="utf-8")
        (self.root / "b.txt").unlink()
        (self.root / "c.txt").write_text("c", encoding="utf-8")
        (package / "CONTEXT.md").write_text("drift", encoding="utf-8")
        report = core.verify_package(package)
        self.assertEqual(report.changed, ("a.txt",))
        self.assertEqual(report.missing, ("b.txt",))
        self.assertEqual(report.unexpected, ("c.txt",))
        self.assertTrue(any("CONTEXT.md differs" in error for error in report.errors))
        rendered = core.format_verify_report(report)
        self.assertIn("result: DRIFT OR INCOMPLETE", rendered)
        self.assertFalse(report.ok)

        clean = core.VerifyReport(("a",), (), (), (), ())
        self.assertTrue(clean.ok)
        self.assertIn("result: OK", core.format_verify_report(clean))

    def test_verify_rejects_inconsistent_package_metadata(self) -> None:
        package, _ = self._pack()
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["package"]["file_count"] = True
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report = core.verify_package(package)
        self.assertTrue(any("inconsistent package metadata" in error for error in report.errors))


if __name__ == "__main__":
    unittest.main()
