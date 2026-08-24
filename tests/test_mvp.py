from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from opencntx.cli import main as cli_main
from opencntx.core import OpenCntxError, pack_project
from opencntx.integrity import IntegrityError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing_pythonpath) if part
    )
    return subprocess.run(
        [sys.executable, "-m", "opencntx", *arguments],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def toml_array(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value, ensure_ascii=False) for value in values) + "]"


def write_config(
    root: Path,
    *,
    include: list[str],
    required: list[str] | None = None,
    exclude: list[str] | None = None,
    max_files: int = 25,
    max_bytes: int = 100_000,
) -> None:
    content = "\n".join(
        [
            "[task]",
            'goal = "Test één concrete taak"',
            "",
            "[context]",
            f"include = {toml_array(include)}",
            f"required = {toml_array(required or [])}",
            f"exclude = {toml_array(exclude or [])}",
            f"max_files = {max_files}",
            f"max_bytes = {max_bytes}",
            "",
        ]
    )
    (root / "opencntx.toml").write_text(content, encoding="utf-8", newline="\n")


class MvpTests(unittest.TestCase):
    def test_01_happy_minimal_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

            init_result = run_cli("init", cwd=root)
            pack_result = run_cli("pack", cwd=root)
            verify_result = run_cli("verify", ".opencntx/latest", cwd=root)

            self.assertEqual(init_result.returncode, 0, init_result.stderr)
            self.assertEqual(pack_result.returncode, 0, pack_result.stderr)
            self.assertEqual(verify_result.returncode, 0, verify_result.stderr)
            package = root / ".opencntx" / "latest"
            self.assertEqual(
                sorted(path.name for path in package.iterdir()),
                ["CONTEXT.md", "manifest.json"],
            )
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [source["path"] for source in manifest["sources"]],
                ["README.md", "src/app.py"],
            )
            self.assertIn("unchanged (2):", verify_result.stdout)
            self.assertIn("changed (0):", verify_result.stdout)
            self.assertIn("missing (0):", verify_result.stdout)
            self.assertIn("unexpected (0):", verify_result.stdout)
            self.assertIn("result: OK", verify_result.stdout)
            completed = root / ".opencntx" / "transactions" / "completed"
            self.assertTrue(any(completed.iterdir()))
            self.assertEqual(
                list((root / ".opencntx" / "transactions" / "locks").rglob("*.lock")), []
            )

    def test_02_repeated_pack_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "a.txt").write_text("dezelfde bytes\n", encoding="utf-8")
            write_config(root, include=["**/*"], required=["a.txt"])

            first = run_cli("pack", cwd=root)
            first_context = (root / ".opencntx/latest/CONTEXT.md").read_bytes()
            first_manifest = (root / ".opencntx/latest/manifest.json").read_bytes()
            second = run_cli("pack", cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(
                (root / ".opencntx/latest/CONTEXT.md").read_bytes(),
                first_context,
            )
            self.assertEqual(
                (root / ".opencntx/latest/manifest.json").read_bytes(),
                first_manifest,
            )

    def test_03_budget_overflow_leaves_no_partial_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "large.txt").write_text("te groot", encoding="utf-8")
            write_config(root, include=["large.txt"], max_bytes=3)

            result = run_cli("pack", cwd=root)

            self.assertEqual(result.returncode, 2)
            self.assertIn("Byte budget exceeded", result.stderr)
            self.assertIn("required=8 bytes; allowed=3 bytes", result.stderr)
            self.assertFalse((root / ".opencntx/latest").exists())
            self.assertEqual(list((root / ".opencntx").glob(".building-*")), [])
            self.assertEqual(list((root / ".opencntx/transactions/active").glob("*")), [])
            self.assertEqual(list((root / ".opencntx/transactions/locks").rglob("*.lock")), [])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "a.txt").write_text("abc", encoding="utf-8")
            (root / "b.txt").write_text("defg", encoding="utf-8")
            write_config(root, include=["*.txt"], max_bytes=5)

            preview = run_cli("pack", "--preview", cwd=root)
            packed = run_cli("pack", cwd=root)

            for result in (preview, packed):
                self.assertEqual(result.returncode, 2)
                self.assertIn("required=7 bytes; allowed=5 bytes", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((root / ".opencntx/latest").exists())
            self.assertEqual(list((root / ".opencntx").glob(".building-*")), [])
            self.assertEqual(list((root / ".opencntx/transactions/active").glob("*")), [])
            self.assertEqual(list((root / ".opencntx/transactions/locks").rglob("*.lock")), [])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "one.txt").write_text("een", encoding="utf-8")
            (root / "two.txt").write_text("twee", encoding="utf-8")
            write_config(root, include=["*.txt"], max_files=1)

            result = run_cli("pack", cwd=root)

            self.assertEqual(result.returncode, 2)
            self.assertIn("File budget exceeded", result.stderr)
            self.assertFalse((root / ".opencntx/latest").exists())

    def test_integrity_access_error_is_short_and_has_no_traceback(self) -> None:
        stderr = io.StringIO()
        with (
            patch(
                "opencntx.cli.dispatch_core",
                side_effect=IntegrityError(
                    "Transaction state path is inaccessible.",
                    code="managed_path_unsafe",
                ),
            ),
            redirect_stderr(stderr),
        ):
            returncode = cli_main(["pack"])

        self.assertEqual(returncode, 2)
        self.assertEqual(
            stderr.getvalue(),
            "Error: operation failed (managed_path_unsafe)\n",
        )
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_integrity_access_error_preserves_existing_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "source.txt").write_text("stable bytes\n", encoding="utf-8")
            write_config(root, include=["source.txt"], required=["source.txt"])
            package, _ = pack_project(root)
            package_before = {path.name: path.read_bytes() for path in package.iterdir()}

            with (
                patch(
                    "opencntx.core.state_digest",
                    side_effect=IntegrityError(
                        "Transaction state path is inaccessible.",
                        code="managed_path_unsafe",
                    ),
                ),
                self.assertRaisesRegex(IntegrityError, "state path is inaccessible") as error,
            ):
                pack_project(root)

            self.assertEqual(error.exception.code, "managed_path_unsafe")
            self.assertEqual(
                {path.name: path.read_bytes() for path in package.iterdir()},
                package_before,
            )
            self.assertEqual(list((root / ".opencntx").glob(".building-*")), [])
            self.assertEqual(list((root / ".opencntx/transactions/active").iterdir()), [])
            self.assertEqual(list((root / ".opencntx/transactions/locks").rglob("*.lock")), [])

    def test_04_missing_required_file_is_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "optional.txt").write_text("optioneel", encoding="utf-8")
            write_config(
                root,
                include=["*.txt"],
                required=["required.txt"],
            )

            result = run_cli("pack", cwd=root)

            self.assertEqual(result.returncode, 2)
            self.assertIn("Required pattern", result.stderr)
            self.assertIn("required.txt", result.stderr)

    def test_05_exclusions_and_sensitive_defaults_apply_before_reading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "notes.txt").write_text("publiek", encoding="utf-8")
            (root / ".env").write_text("DEMO_SECRET=not-real", encoding="utf-8")
            (root / "secret.pem").write_bytes(b"\x00binary-secret")
            (root / "private.key").write_bytes(b"\x00binary-key")
            write_config(
                root,
                include=["notes.txt", ".env", "secret.pem", "private.key", "missing*.md"],
                required=["notes.txt"],
            )

            result = run_cli("pack", cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(
                (root / ".opencntx/latest/manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual([item["path"] for item in manifest["sources"]], ["notes.txt"])
            self.assertEqual(
                {item["path"] for item in manifest["excluded"]},
                {".env", "private.key", "secret.pem"},
            )
            self.assertTrue(
                any(item.get("pattern") == "missing*.md" for item in manifest["ignored"])
            )
            context = (root / ".opencntx/latest/CONTEXT.md").read_text(encoding="utf-8")
            self.assertNotIn("not-real", context)

    def test_06_binary_and_unreadable_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "binary.bin").write_bytes(b"text\x00binary")
            write_config(root, include=["binary.bin"])

            binary_result = run_cli("pack", cwd=root)

            self.assertEqual(binary_result.returncode, 2)
            self.assertIn("Binary source", binary_result.stderr)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "blocked.txt").write_text("tekst", encoding="utf-8")
            write_config(root, include=["blocked.txt"])
            with (
                patch.object(Path, "read_bytes", side_effect=PermissionError("geen toegang")),
                self.assertRaisesRegex(OpenCntxError, "cannot be read"),
            ):
                pack_project(root)

    def test_07_path_traversal_and_symlink_escape_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            root = parent / "project"
            root.mkdir()
            outside = parent / "outside.txt"
            outside.write_text("buiten", encoding="utf-8")
            write_config(root, include=["../outside.txt"])

            traversal_result = run_cli("pack", cwd=root)

            self.assertEqual(traversal_result.returncode, 2)
            self.assertIn("project root", traversal_result.stderr)

            write_config(root, include=["link.txt"])
            link = root / "link.txt"
            try:
                link.symlink_to(outside)
            except OSError:
                return
            symlink_result = run_cli("pack", cwd=root)
            self.assertEqual(symlink_result.returncode, 2)
            self.assertIn("project root through a symlink", symlink_result.stderr)

    def test_08_verify_reports_all_drift_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name in ("a.txt", "b.txt", "stable.txt"):
                (root / name).write_text(f"origineel {name}\n", encoding="utf-8")
            write_config(root, include=["*.txt"], required=["a.txt"])
            pack_result = run_cli("pack", cwd=root)
            self.assertEqual(pack_result.returncode, 0, pack_result.stderr)

            (root / "a.txt").write_text("gewijzigd\n", encoding="utf-8")
            (root / "b.txt").unlink()
            (root / "new.txt").write_text("nieuw\n", encoding="utf-8")
            verify_result = run_cli("verify", ".opencntx/latest", cwd=root)

            self.assertEqual(verify_result.returncode, 1)
            self.assertRegex(verify_result.stdout, r"(?s)unchanged \(1\):.*stable\.txt")
            self.assertRegex(verify_result.stdout, r"(?s)changed \(1\):.*a\.txt")
            self.assertRegex(verify_result.stdout, r"(?s)missing \(1\):.*b\.txt")
            self.assertRegex(verify_result.stdout, r"(?s)unexpected \(1\):.*new\.txt")
            self.assertIn("result: DRIFT OR INCOMPLETE", verify_result.stdout)

    def test_09_windows_style_paths_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            folder = root / "folder"
            folder.mkdir()
            (folder / "note.txt").write_text("Windows-pad", encoding="utf-8")
            write_config(
                root,
                include=[r"folder\*.txt"],
                required=[r"folder\note.txt"],
            )

            pack_result = run_cli("pack", cwd=root)
            verify_result = run_cli("verify", r".opencntx\latest", cwd=root)

            self.assertEqual(pack_result.returncode, 0, pack_result.stderr)
            self.assertEqual(verify_result.returncode, 0, verify_result.stderr)
            self.assertIn("folder/note.txt", verify_result.stdout)

    def test_10_pack_and_verify_never_mutate_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "source.txt"
            source_path.write_bytes(b"ongewijzigde bron\n")
            write_config(root, include=["source.txt"], required=["source.txt"])
            before_bytes = source_path.read_bytes()
            before_mtime = source_path.stat().st_mtime_ns

            pack_result = run_cli("pack", cwd=root)
            verify_result = run_cli("verify", ".opencntx/latest", cwd=root)

            self.assertEqual(pack_result.returncode, 0, pack_result.stderr)
            self.assertEqual(verify_result.returncode, 0, verify_result.stderr)
            self.assertEqual(source_path.read_bytes(), before_bytes)
            self.assertEqual(source_path.stat().st_mtime_ns, before_mtime)

    def test_invalid_toml_is_a_short_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "opencntx.toml").write_text("[task\n", encoding="utf-8")

            result = run_cli("pack", cwd=root)

            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid TOML", result.stderr)

    def test_tampered_context_makes_verify_nonzero_without_rewriting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "source.txt").write_text("bron", encoding="utf-8")
            write_config(root, include=["source.txt"])
            self.assertEqual(run_cli("pack", cwd=root).returncode, 0)
            context_path = root / ".opencntx/latest/CONTEXT.md"
            context_path.write_text("gemanipuleerd", encoding="utf-8")
            before = context_path.read_bytes()

            result = run_cli("verify", ".opencntx/latest", cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("CONTEXT.md differs", result.stdout)
            self.assertEqual(context_path.read_bytes(), before)

    def test_preview_is_deterministic_and_never_writes_or_changes_a_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "a.txt").write_text("preview source\n", encoding="utf-8")
            (root / ".env").write_text("EXCLUDED=value\n", encoding="utf-8")
            write_config(
                root,
                include=["*.txt", ".env", "missing*.md"],
                required=["a.txt"],
            )

            first = run_cli("pack", "--preview", cwd=root)
            second = run_cli("pack", "--preview", cwd=root)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertFalse((root / ".opencntx").exists())
            self.assertIn("a.txt | include=*.txt | required=a.txt", first.stdout)
            self.assertIn(".env | pattern=.env*", first.stdout)
            self.assertIn("missing*.md", first.stdout)
            self.assertIn("files=1/25", first.stdout)
            self.assertIn("PACK_WOULD_SUCCEED", first.stdout)

            packed = run_cli("pack", cwd=root)
            self.assertEqual(packed.returncode, 0, packed.stderr)
            package = root / ".opencntx" / "latest"
            before = {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in package.iterdir()
            }
            source_before = ((root / "a.txt").read_bytes(), (root / "a.txt").stat().st_mtime_ns)

            preview = run_cli("pack", "--preview", cwd=root)

            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertEqual(
                {
                    path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                    for path in package.iterdir()
                },
                before,
            )
            self.assertEqual(
                ((root / "a.txt").read_bytes(), (root / "a.txt").stat().st_mtime_ns),
                source_before,
            )

    def test_high_confidence_secret_blocks_safely_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "safe.txt").write_text("safe\n", encoding="utf-8")
            write_config(root, include=["safe.txt"])
            self.assertEqual(run_cli("pack", cwd=root).returncode, 0)
            package = root / ".opencntx" / "latest"
            package_before = {path.name: path.read_bytes() for path in package.iterdir()}

            secret_value = "gh" + "p_" + ("Z" * 36)
            (root / "secret.txt").write_text(secret_value + "\n", encoding="utf-8")
            write_config(root, include=["secret.txt"], required=["secret.txt"])

            preview = run_cli("pack", "--preview", cwd=root)
            pack = run_cli("pack", cwd=root)

            self.assertEqual(preview.returncode, 2)
            self.assertIn("PACK_WOULD_BE_BLOCKED", preview.stdout)
            self.assertIn("github-classic-token", preview.stdout)
            self.assertNotIn(secret_value, preview.stdout + preview.stderr)
            self.assertEqual(pack.returncode, 2)
            self.assertIn("Secret policy blocks", pack.stderr)
            self.assertNotIn(secret_value, pack.stdout + pack.stderr)
            self.assertEqual(
                {path.name: path.read_bytes() for path in package.iterdir()},
                package_before,
            )

    def test_warning_does_not_block_and_is_safely_manifested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            warning_value = "client_secret=synthetic-value"
            (root / "warning.txt").write_text(warning_value + "\n", encoding="utf-8")
            write_config(root, include=["warning.txt"])

            result = run_cli("pack", cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Secret policy warning", result.stderr)
            self.assertNotIn(warning_value, result.stdout + result.stderr)
            manifest_text = (root / ".opencntx/latest/manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertEqual(manifest["security"]["policy_version"], 1)
            self.assertEqual(len(manifest["security"]["warnings"]), 1)
            self.assertEqual(manifest["security"]["overrides"], [])
            self.assertEqual(
                manifest["security"]["warnings"][0]["rule_id"],
                "credential-like-assignment",
            )
            self.assertNotIn(warning_value, manifest_text)
            self.assertEqual(
                run_cli("verify", ".opencntx/latest", cwd=root).returncode,
                0,
            )

    def test_exact_override_is_manifested_and_source_drift_invalidates_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            secret_value = "-----BEGIN " + "PRIVATE KEY-----"
            source = root / "private.txt"
            source.write_text(secret_value + "\n", encoding="utf-8")
            write_config(root, include=["private.txt"])

            preview = run_cli("pack", "--preview", cwd=root)
            finding_ids = re.findall(r"\b[0-9a-f]{64}\b", preview.stdout)
            self.assertEqual(preview.returncode, 2)
            self.assertEqual(len(finding_ids), 1)
            finding_id = finding_ids[0]

            allowed_preview = run_cli(
                "pack",
                "--preview",
                "--allow-secret",
                finding_id,
                cwd=root,
            )
            self.assertEqual(allowed_preview.returncode, 0, allowed_preview.stderr)
            self.assertIn("overrides (1)", allowed_preview.stdout)
            self.assertIn("PACK_WOULD_SUCCEED", allowed_preview.stdout)
            self.assertFalse((root / ".opencntx").exists())

            packed = run_cli("pack", "--allow-secret", finding_id, cwd=root)
            self.assertEqual(packed.returncode, 0, packed.stderr)
            manifest_path = root / ".opencntx/latest/manifest.json"
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertEqual(
                [item["finding_id"] for item in manifest["security"]["overrides"]],
                [finding_id],
            )
            self.assertNotIn(secret_value, manifest_text)
            self.assertEqual(
                run_cli("verify", ".opencntx/latest", cwd=root).returncode,
                0,
            )

            duplicate = run_cli(
                "pack",
                "--allow-secret",
                finding_id,
                "--allow-secret",
                finding_id,
                cwd=root,
            )
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("only once", duplicate.stderr)

            previous_package = {
                path.name: path.read_bytes() for path in (root / ".opencntx/latest").iterdir()
            }
            source.write_text(secret_value + "\nchanged\n", encoding="utf-8")
            stale = run_cli("pack", "--allow-secret", finding_id, cwd=root)
            self.assertEqual(stale.returncode, 2)
            self.assertIn("Unknown or stale", stale.stderr)
            self.assertEqual(
                {path.name: path.read_bytes() for path in (root / ".opencntx/latest").iterdir()},
                previous_package,
            )

    def test_known_credential_paths_are_excluded_before_reading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / ".aws").mkdir()
            (root / ".ssh").mkdir()
            (root / ".docker").mkdir()
            blocked_paths = (
                root / ".aws" / "credentials",
                root / ".ssh" / "id_demo",
                root / ".npmrc",
                root / ".docker" / "config.json",
                root / "application_default_credentials.json",
            )
            for path in blocked_paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"unreadable\x00credential")
            (root / "safe.txt").write_text("safe\n", encoding="utf-8")
            write_config(
                root,
                include=[
                    "safe.txt",
                    ".aws/credentials",
                    ".ssh/id_demo",
                    ".npmrc",
                    ".docker/config.json",
                    "application_default_credentials.json",
                ],
            )

            result = run_cli("pack", cwd=root)

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(
                (root / ".opencntx/latest/manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual([item["path"] for item in manifest["sources"]], ["safe.txt"])
            self.assertEqual(
                {item["path"] for item in manifest["excluded"]},
                {
                    ".aws/credentials",
                    ".ssh/id_demo",
                    ".npmrc",
                    ".docker/config.json",
                    "application_default_credentials.json",
                },
            )

    def test_legacy_manifest_without_security_remains_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "source.txt").write_text("legacy-safe\n", encoding="utf-8")
            write_config(root, include=["source.txt"])
            self.assertEqual(run_cli("pack", cwd=root).returncode, 0)
            manifest_path = root / ".opencntx/latest/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            del manifest["security"]
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )

            result = run_cli("verify", ".opencntx/latest", cwd=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("result: OK", result.stdout)

    def test_verify_detects_security_metadata_tampering_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "warning.txt").write_text("password=synthetic-value\n", encoding="utf-8")
            write_config(root, include=["warning.txt"])
            self.assertEqual(run_cli("pack", cwd=root).returncode, 0)
            manifest_path = root / ".opencntx/latest/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["security"]["warnings"] = []
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            before = manifest_path.read_bytes()

            result = run_cli("verify", ".opencntx/latest", cwd=root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("security metadata differs", result.stdout)
            self.assertEqual(manifest_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
