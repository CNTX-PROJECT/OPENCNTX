from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))


def run_cli_bytes(
    *arguments: str,
    cwd: Path,
    io_encoding: str = "utf-8:strict",
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing_pythonpath) if part
    )
    environment["PYTHONIOENCODING"] = io_encoding
    return subprocess.run(
        [sys.executable, "-m", "opencntx", *arguments],
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
    )


def all_parsers(parser: argparse.ArgumentParser) -> tuple[argparse.ArgumentParser, ...]:
    found: list[argparse.ArgumentParser] = []

    def visit(current: argparse.ArgumentParser) -> None:
        found.append(current)
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    visit(child)

    visit(parser)
    return tuple(found)


class LanguageContractTests(unittest.TestCase):
    def test_r9_legacy_corpus_is_explicit_immutable_and_not_an_active_template(self) -> None:
        manifest_path = REPOSITORY_ROOT / "tests" / "legacy-compatibility-r9.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["format"], "opencntx-immutable-legacy-test-corpus")
        self.assertEqual(
            manifest["policy"],
            "READ_ONLY_COMPATIBILITY_INPUT_NEVER_CURRENT_PRODUCT_OUTPUT",
        )
        self.assertEqual(manifest["canonicalization"], "TEXT_CRLF_TO_LF_BEFORE_SHA256")
        legacy_paths = {item["path"] for item in manifest["files"]}
        self.assertEqual(len(legacy_paths), len(manifest["files"]))
        for item in manifest["files"]:
            path = REPOSITORY_ROOT / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            canonical_bytes = path.read_bytes().replace(b"\r\n", b"\n")
            self.assertNotIn(b"\r", canonical_bytes, item["path"])
            self.assertEqual(hashlib.sha256(canonical_bytes).hexdigest(), item["sha256"])

        active_files = [REPOSITORY_ROOT / "README.md"]
        for relative_root in ("src", "docs", "examples", "tests"):
            active_files.extend(
                path for path in (REPOSITORY_ROOT / relative_root).rglob("*") if path.is_file()
            )
        forbidden = (
            "sky" + "rim",
            "nano" + "pc",
            "one" + "drive",
            "home" + " assistant",
            "mod" + " organizer",
            "c:" + "\\users\\",
            "d:" + "\\codex\\",
        )
        for path in active_files:
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            if relative in legacy_paths or path.suffix.lower() in {
                ".gz",
                ".ico",
                ".jpg",
                ".png",
                ".pyc",
            }:
                continue
            try:
                text = path.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError:
                continue
            for marker in forbidden:
                self.assertNotIn(marker, text, relative)

    def test_every_reachable_help_route_is_ascii_english(self) -> None:
        from opencntx.cli import build_parser

        forbidden = re.compile(
            r"\b(?:fout|waarschuwing|gemaakt|controleer|toon|maak|registreer|"
            r"werkruimte|bronbestand|hoofdstuk|taak|uitvoerder|goedkeuring|"
            r"bewijs|huidige|standaard|een|geen|niet)\b",
            re.IGNORECASE,
        )
        for parser in all_parsers(build_parser()):
            help_text = parser.format_help()
            help_text.encode("ascii")
            self.assertIsNone(forbidden.search(help_text), help_text)
            self.assertNotIn("\ufffd", help_text)

    def test_root_help_orders_core_before_stable_workspace(self) -> None:
        result = run_cli_bytes("--help", cwd=REPOSITORY_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = result.stdout.decode("utf-8")
        self.assertLess(text.index("init"), text.index("workspace"))
        self.assertIn("pack --preview", text)
        self.assertIn("inspect CONTEXT.md", text)
        self.assertIn("Stable workspace", text)
        self.assertNotIn("Advanced / Alpha", text)

    def test_version_uses_the_single_package_version(self) -> None:
        from opencntx import __version__

        result = run_cli_bytes("--version", cwd=REPOSITORY_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"opencntx {__version__}\n".encode("ascii"))
        self.assertEqual(result.stderr, b"")

    def test_default_and_explicit_verify_are_equal_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.assertEqual(run_cli_bytes("init", cwd=root).returncode, 0)
            (root / "README.md").write_text("bounded source\n", encoding="utf-8")
            packed = run_cli_bytes("pack", cwd=root)
            self.assertEqual(packed.returncode, 0, packed.stderr)
            package = root / ".opencntx" / "latest"
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in package.rglob("*")
                if path.is_file()
            }

            default = run_cli_bytes("verify", cwd=root)
            explicit = run_cli_bytes("verify", ".opencntx/latest", cwd=root)

            self.assertEqual(default.returncode, 0, default.stderr)
            self.assertEqual(default.stdout, explicit.stdout)
            self.assertIn(b"result: OK", default.stdout)
            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in package.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_missing_default_verify_is_short_english_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_cli_bytes("verify", cwd=Path(temporary_directory))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertIn(b"Error: Package directory is missing or inaccessible", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)

    def test_cp1252_and_utf8_routes_never_emit_replacement_character(self) -> None:
        for encoding in ("cp1252:strict", "utf-8:strict"):
            help_result = run_cli_bytes("--help", cwd=REPOSITORY_ROOT, io_encoding=encoding)
            error_result = run_cli_bytes("verify", cwd=REPOSITORY_ROOT, io_encoding=encoding)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn(error_result.returncode, {0, 1, 2})
            combined = (
                help_result.stdout + help_result.stderr + error_result.stdout + error_result.stderr
            )
            self.assertNotIn(b"Traceback", combined)
            self.assertNotIn("\ufffd", combined.decode(encoding.split(":", 1)[0]))

    def test_unicode_path_is_exact_in_utf8_and_escaped_on_narrow_console(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            unicode_root = parent / "project-\U0001f680"
            unicode_root.mkdir()

            utf8 = run_cli_bytes("init", cwd=unicode_root, io_encoding="utf-8:strict")
            self.assertEqual(utf8.returncode, 0, utf8.stderr)
            self.assertIn(str(unicode_root).encode("utf-8"), utf8.stdout)

            narrow_root = parent / "narrow-\U0001f680"
            narrow_root.mkdir()
            narrow = run_cli_bytes("init", cwd=narrow_root, io_encoding="cp1252:strict")
            self.assertEqual(narrow.returncode, 0, narrow.stderr)
            decoded = narrow.stdout.decode("cp1252")
            self.assertIn(r"\U0001f680", decoded)
            self.assertNotIn("Traceback", decoded)

    def test_new_templates_are_english_and_legacy_current_is_read_only(self) -> None:
        from opencntx.workspace import init_workspace, validate_workspace

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            init_workspace(root)
            current = root / "CONTROL" / "CURRENT.md"
            self.assertIn("- Active task: none", current.read_text(encoding="utf-8"))
            legacy = current.read_text(encoding="utf-8").replace(
                "- Active task: none\n- Allowed actions: none\n- Next gate: OWNER instruction",
                "- Actieve taak: geen\n- Toegestane acties: geen\n- Volgende gate: OWNER-instructie",
            )
            current.write_text(legacy, encoding="utf-8", newline="\n")
            before = current.read_bytes()
            self.assertEqual(validate_workspace(root), root.resolve())
            self.assertEqual(current.read_bytes(), before)

    def test_generated_flow_detail_template_is_english(self) -> None:
        from opencntx.continuity import start_flow

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "input.txt").write_text("existing\n", encoding="utf-8")
            roadmap = root / "roadmap.json"
            roadmap.write_text(
                json.dumps(
                    {
                        "format": "opencntx-continuity-roadmap",
                        "format_version": 1,
                        "project_id": "LANGUAGE-TEST",
                        "roadmap_id": "ROADMAP-1",
                        "title": "English generated detail",
                        "assignments": [
                            {
                                "id": "TASK-1",
                                "title": "English task",
                                "detail": "Complete the bounded English task.",
                                "depends_on": [],
                                "touches": ["missing.txt"],
                                "conflict": "EXTEND",
                                "migration": "",
                                "definition_of_done": ["English evidence exists"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            start_flow(root, roadmap, "AUTO PILOT")
            detail = (root / ".opencntx" / "continuity" / "details" / "TASK-1.md").read_text(
                encoding="utf-8"
            )

            for expected in (
                "## Short existing check",
                "Conflict class: `EXTEND`",
                "Rev4 result: the objective in this detail wins within the bound scope.",
                "Migration/compatibility: Not required.",
                "Files: 0",
                "No existing touched file was found.",
            ):
                self.assertIn(expected, detail)
            forbidden = re.compile(
                r"\b(?:korte|bestaande|conflictklasse|uitkomst|doel|wint|"
                r"gebonden|migratie|bestanden|geen|niet|nodig)\b",
                re.IGNORECASE,
            )
            self.assertIsNone(forbidden.search(detail), detail)

    def test_generated_task_status_and_executor_fixed_text_are_english(self) -> None:
        from opencntx.workflow import propose_task
        from opencntx.workspace import init_workspace
        from tests.test_playbook import prepare_ready_executor

        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            workspace = parent / "task-workspace"
            init_workspace(workspace)
            proposed = propose_task(
                workspace,
                "TASK-20260901-0001",
                title="Inspect one bounded plan",
                goal="Inspect only the pinned plan.",
                definition_of_done="The evidence identifies every checked input.",
                executor_role="ROLE-REVIEWER",
                input_paths=["CONTROL/ROADMAP.md"],
                allowed_actions=["inspect-pinned-input"],
                forbidden_actions=["external-send"],
                expected_output="One local evidence report.",
                acceptance_criteria=["Every claim points to evidence."],
                architect="ARCHITECT",
            )
            task_text = proposed.task_path.read_text(encoding="utf-8")
            status = run_cli_bytes(
                "workspace",
                "task",
                "status",
                "TASK-20260901-0001",
                "--root",
                str(workspace),
                cwd=parent,
            )
            self.assertEqual(status.returncode, 0, status.stderr)

            _workspace, _playbook, _role, _proposal, _context, executor = prepare_ready_executor(
                parent / "executor"
            )
            executor_text = executor.assignment_path.read_text(encoding="utf-8")
            for text in (task_text, status.stdout.decode("utf-8"), executor_text):
                for phrase in (
                    "Gegenereerde taakkaart",
                    "Actuele staat",
                    "Toegestane acties",
                    "Verboden acties",
                    "Uitvoerderpakket",
                    "Doel en Definition of Done",
                    "Overdracht en authority",
                ):
                    self.assertNotIn(phrase, text)
            self.assertIn("Generated task card", task_text)
            self.assertIn("TASK_STATUS_VALID", status.stdout.decode("utf-8"))
            self.assertIn("Executor package", executor_text)
            self.assertIn("This package starts nothing", executor_text)

    def test_active_error_families_emit_only_short_english(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            digest = "0" * 64
            cases = (
                ("verify",),
                ("workspace", "doctor", "--root", str(root)),
                ("workspace", "control", "refresh", "--root", str(root)),
                ("workspace", "catalog", "rebuild", "--root", str(root)),
                ("workspace", "media", "status", "SRC-20260901-000000000000", "--root", str(root)),
                (
                    "workspace",
                    "playbook",
                    "status",
                    "PLAYBOOK-EXAMPLE",
                    "--revision",
                    "1",
                    "--root",
                    str(root),
                ),
                (
                    "workspace",
                    "context",
                    "verify",
                    "TASK-20260901-0001",
                    "--proposal-digest",
                    digest,
                    "--root",
                    str(root),
                ),
                (
                    "workspace",
                    "task",
                    "status",
                    "TASK-20260901-0001",
                    "--root",
                    str(root),
                ),
                ("flow", "status", "--root", str(root)),
                ("layout", "audit", "--contract", str(root / "missing.json")),
            )
            forbidden = re.compile(
                r"\b(?:fout|waarschuwing|bestand|map|werkruimte|taak|opdracht|"
                r"ontbreekt|ongeldig|geen|niet|moet|controleer)\b",
                re.IGNORECASE,
            )
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    result = run_cli_bytes(*arguments, cwd=root)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, b"")
                    rendered = result.stderr.decode("ascii")
                    self.assertTrue(rendered.startswith("Error:"), rendered)
                    self.assertIsNone(forbidden.search(rendered), rendered)
                    self.assertNotIn("Traceback", rendered)


if __name__ == "__main__":
    unittest.main()
