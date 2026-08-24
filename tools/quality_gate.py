"""Run the bounded, provider-neutral OPENCNTX quality ratchets."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "opencntx"
BASELINE_PATH = ROOT / "tests" / "fixtures" / "quality" / "metrics-baseline-v1.json"
REFACTOR_ALLOWLIST = (
    "src/opencntx/cli.py",
    "src/opencntx/cli_content.py",
    "src/opencntx/cli_core.py",
    "src/opencntx/cli_definitions.py",
    "src/opencntx/cli_lifecycle.py",
    "src/opencntx/cli_tasks.py",
    "src/opencntx/cli_workspace.py",
    "src/opencntx/primitives.py",
    "tests/test_properties.py",
    "tests/test_refactor_contract.py",
    "tools/quality_gate.py",
)
TYPELIST = tuple(path.relative_to(ROOT).as_posix() for path in sorted(SOURCE.glob("*.py")))
FORBIDDEN_SUPPRESSIONS = (
    "# " + "noqa",
    "# " + "type: ignore",
    "# " + "pragma: no cover",
)


class QualityGateError(RuntimeError):
    """Raised when a quality ratchet fails closed."""


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualityGateError(f"Expected a JSON object: {path}")
    return value


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=capture,
        check=False,
    )
    if completed.returncode:
        if capture:
            sys.stdout.write(completed.stdout)
            sys.stderr.write(completed.stderr)
        raise QualityGateError(f"Command failed with exit code {completed.returncode}: {command}")
    return completed


def _functions(path: Path) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _function_lines(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    if function.end_lineno is None:
        raise QualityGateError(f"Function has no end line: {function.name}")
    return function.end_lineno - function.lineno + 1


def _error_code_contract() -> tuple[int, str]:
    codes: set[str] = set()
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
                    codes.add(literal.value)
    encoded = (json.dumps(sorted(codes), separators=(",", ":")) + "\n").encode("ascii")
    return len(codes), hashlib.sha256(encoded).hexdigest()


def check_metrics() -> None:
    baseline = _load_object(BASELINE_PATH)
    long_functions: list[str] = []
    for path in sorted(SOURCE.glob("*.py")):
        for function in _functions(path):
            lines = _function_lines(function)
            if lines > 180:
                long_functions.append(f"{path.name}:{function.name}:{lines}")
    if long_functions:
        raise QualityGateError(f"Functions above 180 lines: {long_functions}")

    cli = SOURCE / "cli.py"
    cli_lines = len(cli.read_text(encoding="utf-8").splitlines())
    if cli_lines > 220:
        raise QualityGateError(f"cli.py exceeds 220 lines: {cli_lines}")
    facade = {function.name: function for function in _functions(cli)}
    for name in ("build_parser", "main"):
        lines = _function_lines(facade[name])
        if lines > 80:
            raise QualityGateError(f"{name} exceeds 80 lines: {lines}")

    count, digest = _error_code_contract()
    if count != baseline["error_code_count"] or digest != baseline["error_code_set_sha256"]:
        raise QualityGateError("The literal public error-code set changed")

    for relative in REFACTOR_ALLOWLIST:
        if not relative.endswith(".py"):
            continue
        text = (ROOT / relative).read_text(encoding="utf-8")
        for marker in FORBIDDEN_SUPPRESSIONS:
            if marker in text:
                raise QualityGateError(f"Forbidden suppression {marker!r} in {relative}")
    print(f"QUALITY_METRICS_OK cli_lines={cli_lines} functions_over_180=0 error_codes={count}")


def check_lint() -> None:
    baseline = _load_object(BASELINE_PATH)
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--output-format", "json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        sys.stderr.write(completed.stderr)
        raise QualityGateError(f"Ruff failed with exit code {completed.returncode}")
    findings = json.loads(completed.stdout)
    if not isinstance(findings, list):
        raise QualityGateError("Ruff did not return a JSON findings list")
    maximum = int(baseline["ruff_findings"])
    if findings or maximum != 0:
        if findings:
            sys.stderr.write(json.dumps(findings, indent=2, sort_keys=True) + "\n")
        raise QualityGateError(
            f"Ruff must remain at the zero-finding ratchet: {len(findings)} findings, "
            f"baseline {maximum}"
        )
    _run([sys.executable, "-m", "ruff", "check", *REFACTOR_ALLOWLIST])
    _run([sys.executable, "-m", "ruff", "format", "--check", *REFACTOR_ALLOWLIST])
    _run([sys.executable, "-m", "ruff", "check", "src/opencntx", "tools", "--select", "S"])
    print(f"QUALITY_LINT_OK findings={len(findings)} baseline_max={maximum}")


def check_types() -> None:
    _run([sys.executable, "-m", "mypy", *TYPELIST])
    print(f"QUALITY_TYPES_OK files={len(TYPELIST)} errors=0")


def _coverage_ratio(summary: dict[str, Any]) -> tuple[int, int, float]:
    covered = int(summary["covered_lines"]) + int(summary["covered_branches"])
    total = int(summary["num_statements"]) + int(summary["num_branches"])
    return covered, total, (100.0 * covered / total)


def check_coverage(path: Path) -> None:
    baseline = _load_object(BASELINE_PATH)
    report = _load_object(path)
    files = report.get("files")
    totals = report.get("totals")
    if not isinstance(files, dict) or not isinstance(totals, dict):
        raise QualityGateError("Coverage JSON is missing files or totals")

    total_percent = float(totals["percent_covered"])
    minimum_total = float(baseline["branch_coverage_percent"])
    if total_percent < minimum_total:
        raise QualityGateError(f"Total coverage fell: {total_percent:.2f} < {minimum_total:.2f}")

    cli_summaries = [
        value["summary"]
        for filename, value in files.items()
        if Path(filename).name == "cli.py" or Path(filename).name.startswith("cli_")
    ]
    cli_covered = sum(_coverage_ratio(summary)[0] for summary in cli_summaries)
    cli_total = sum(_coverage_ratio(summary)[1] for summary in cli_summaries)
    cli_percent = 100.0 * cli_covered / cli_total
    minimum_cli = float(baseline["cli_coverage_percent"])
    if cli_percent <= minimum_cli:
        raise QualityGateError(f"CLI coverage did not rise: {cli_percent:.2f} <= {minimum_cli:.2f}")

    platform = "windows" if os.name == "nt" else "posix"
    safety_baseline = baseline["safety_module_coverage"][platform]
    for module, expected in safety_baseline.items():
        matches = [
            value["summary"] for filename, value in files.items() if Path(filename).name == module
        ]
        if len(matches) != 1:
            raise QualityGateError(f"Coverage has no unique entry for {module}")
        covered, total, candidate_percent = _coverage_ratio(matches[0])
        basis_percent = 100.0 * int(expected["covered"]) / int(expected["total"])
        if candidate_percent < basis_percent:
            raise QualityGateError(
                f"{module} coverage fell: {covered}/{total}={candidate_percent:.4f}% "
                f"< {basis_percent:.4f}%"
            )
    print(f"QUALITY_COVERAGE_OK total={total_percent:.2f}% cli={cli_percent:.2f}%")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("metrics")
    subparsers.add_parser("lint")
    subparsers.add_parser("types")
    coverage = subparsers.add_parser("coverage")
    coverage.add_argument("report", type=Path)
    all_checks = subparsers.add_parser("all")
    all_checks.add_argument("--coverage-report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"metrics", "all"}:
            check_metrics()
        if args.command in {"lint", "all"}:
            check_lint()
        if args.command in {"types", "all"}:
            check_types()
        if args.command == "coverage":
            check_coverage(args.report)
        elif args.command == "all":
            check_coverage(args.coverage_report)
    except (KeyError, OSError, QualityGateError, TypeError, ValueError) as exc:
        print(f"QUALITY_GATE_FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
