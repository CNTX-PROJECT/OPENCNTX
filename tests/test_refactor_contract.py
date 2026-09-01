from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "opencntx"
FIXTURES = ROOT / "tests" / "fixtures" / "quality"
CLI_FACADE = SOURCE / "cli.py"
CLI_FAMILIES = tuple(sorted(SOURCE.glob("cli_*.py")))


def _functions(path: Path) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _function_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    assert node.end_lineno is not None
    return node.end_lineno - node.lineno + 1


def _error_code_contract() -> tuple[int, str]:
    values: set[str] = set()
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                literal = keyword.value
                if (
                    keyword.arg == "code"
                    and isinstance(literal, ast.Constant)
                    and isinstance(literal.value, str)
                ):
                    values.add(literal.value)
    encoded = (json.dumps(sorted(values), ensure_ascii=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )
    return len(values), hashlib.sha256(encoded).hexdigest()


class RefactorContractTests(unittest.TestCase):
    def test_cli_facade_and_function_sizes_are_bounded(self) -> None:
        self.assertLessEqual(len(CLI_FACADE.read_text(encoding="utf-8").splitlines()), 220)
        self.assertEqual(
            {
                "cli_content.py",
                "cli_continuity.py",
                "cli_core.py",
                "cli_definitions.py",
                "cli_lifecycle.py",
                "cli_tasks.py",
                "cli_workspace.py",
            },
            {path.name for path in CLI_FAMILIES},
        )
        for path in sorted(SOURCE.glob("*.py")):
            for function in _functions(path):
                with self.subTest(path=path.name, function=function.name):
                    self.assertLessEqual(_function_lines(function), 180)
                    if path in (*CLI_FAMILIES, SOURCE / "primitives.py"):
                        self.assertLessEqual(_function_lines(function), 120)

        facade_functions = {function.name: function for function in _functions(CLI_FACADE)}
        self.assertLessEqual(_function_lines(facade_functions["build_parser"]), 80)
        self.assertLessEqual(_function_lines(facade_functions["main"]), 80)

    def test_cli_families_are_one_way_dependencies(self) -> None:
        for path in sorted(SOURCE.glob("*.py")):
            if path.name.startswith("cli") or path.name == "__main__.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.level == 1
            }
            self.assertFalse(
                any(module is not None and module.startswith("cli") for module in imports),
                path.name,
            )

    def test_primitives_use_only_the_standard_library(self) -> None:
        tree = ast.parse(
            (SOURCE / "primitives.py").read_text(encoding="utf-8"),
            filename="primitives.py",
        )
        self.assertFalse(
            any(isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(tree))
        )

    def test_error_code_set_is_byte_exact_to_the_basis(self) -> None:
        baseline = json.loads((FIXTURES / "metrics-baseline-v1.json").read_text(encoding="utf-8"))
        count, digest = _error_code_contract()
        self.assertEqual(baseline["error_code_count"], count)
        self.assertEqual(baseline["error_code_set_sha256"], digest)

    def test_cli_golden_outputs_match_the_exact_basis(self) -> None:
        contract = json.loads((FIXTURES / "cli-contract-v1.json").read_text(encoding="utf-8"))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        python_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
        for name, case in contract["cases"].items():
            with self.subTest(case=name):
                completed = subprocess.run(
                    [sys.executable, "-m", "opencntx", *case["argv"]],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(case["exit_code"], completed.returncode)
                expected_stdout = case.get("stdout_sha256_by_python_minor", {}).get(
                    python_minor,
                    case["stdout_sha256"],
                )
                self.assertEqual(expected_stdout, hashlib.sha256(completed.stdout).hexdigest())
                self.assertEqual(
                    case["stderr_sha256"],
                    hashlib.sha256(completed.stderr).hexdigest(),
                )

    def test_each_cli_family_dispatches_and_fails_closed_on_an_invalid_workspace(self) -> None:
        cli_main = importlib.import_module("opencntx.cli").main
        with tempfile.TemporaryDirectory() as temporary_directory:
            invalid_root = str(Path(temporary_directory))
            cases = {
                "chapter": [
                    "workspace",
                    "chapter",
                    "create",
                    "CH-TEST",
                    "--title",
                    "Test",
                    "--root",
                    invalid_root,
                ],
                "catalog": ["workspace", "catalog", "rebuild", "--root", invalid_root],
                "media": [
                    "workspace",
                    "media",
                    "status",
                    "SRC-20260820-0001",
                    "--root",
                    invalid_root,
                ],
                "playbook": [
                    "workspace",
                    "playbook",
                    "status",
                    "PB-TEST",
                    "--revision",
                    "1",
                    "--root",
                    invalid_root,
                ],
                "lifecycle": ["workspace", "lifecycle", "status", "--root", invalid_root],
                "task": [
                    "workspace",
                    "task",
                    "status",
                    "TASK-20260820-0001",
                    "--root",
                    invalid_root,
                ],
            }
            for family, arguments in cases.items():
                with self.subTest(family=family):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        result = cli_main(arguments)
                    self.assertEqual(2, result)
                    self.assertEqual("", stdout.getvalue())
                    self.assertTrue(stderr.getvalue().startswith("Error: "))


if __name__ == "__main__":
    unittest.main()
