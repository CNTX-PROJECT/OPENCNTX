from __future__ import annotations

import ast
import hashlib
import json
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "opencntx"
FIXTURES = ROOT / "tests" / "fixtures" / "hardening"
FAMILY_NAMES = (
    "PACKAGE",
    "SOURCE_CATALOG",
    "CONTROL",
    "TASK_WORKFLOW",
    "CONTEXT_EXECUTOR",
    "DEFINITION",
    "DERIVED_MEDIA",
    "LIFECYCLE",
)
ADVERSARIAL_CATEGORIES = {
    "path_escape",
    "path_swap",
    "symlink",
    "reparse_point",
    "source",
    "target",
    "lock",
    "transaction_root",
    "backup",
    "corrupt_json",
    "truncated_record",
    "wrong_type",
    "major_version",
    "digest_drift",
    "high_risk_secret",
    "low_risk_control",
    "binary_input",
    "file",
    "byte",
    "action",
    "time",
    "storage",
    "disk",
    "flush",
    "write",
    "replace",
    "before_publish",
    "after_publish",
    "unchanged_retry",
    "stale_digest",
    "unsafe_target",
    "drifted_target",
}


def _load(name: str) -> dict[str, object]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"hardening fixture must be an object: {name}")
    return value


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _discover_operations() -> tuple[set[str], int]:
    operations: list[str] = []
    dynamic_task_routes = 0
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name == "_workspace_writer" and node.args:
                argument = node.args[0]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    operations.append(argument.value)
            elif name == "writer_transaction" and len(node.args) >= 2:
                argument = node.args[1]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    operations.append(argument.value)
                elif isinstance(argument, ast.JoinedStr):
                    literal = "".join(
                        value.value
                        for value in argument.values
                        if isinstance(value, ast.Constant) and isinstance(value.value, str)
                    )
                    if literal == "task-":
                        dynamic_task_routes += 1
            if name == "_append_event":
                for keyword in node.keywords:
                    if (
                        keyword.arg == "event_type"
                        and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)
                    ):
                        operations.append(f"task-{keyword.value.value}")
    if len(operations) != len(set(operations)):
        raise AssertionError("writer operations must be discovered exactly once")
    return set(operations), dynamic_task_routes


def _canonical_vector(family: str, round_number: int) -> tuple[int, bytes, str]:
    seed_material = f"opencntx-r8-23-contention-v1|{family}|{round_number:02d}".encode()
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
    value = {
        "family": family,
        "round": round_number,
        "scenario_version": 1,
        "seed": seed,
    }
    content = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return seed, content, hashlib.sha256(content).hexdigest()


class HardeningContractTests(unittest.TestCase):
    def test_contention_accepts_every_safe_loser_race(self) -> None:
        path = ROOT / "tools" / "r8_hardening.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assignments = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "LOCK_FAILURES"
                for target in node.targets
            )
        ]
        self.assertEqual(1, len(assignments))
        self.assertEqual(
            {
                "transaction_locked",
                "transaction_recovery_required",
                "transaction_state_changed",
            },
            ast.literal_eval(assignments[0].value),
        )

    def test_registry_is_set_equal_to_every_current_writer_operation(self) -> None:
        register = _load("mutation-families-v1.json")
        families = register["families"]
        self.assertIsInstance(families, dict)
        assert isinstance(families, dict)
        self.assertEqual(FAMILY_NAMES, tuple(families))
        registered: list[str] = []
        for family, value in families.items():
            with self.subTest(family=family):
                self.assertIsInstance(value, dict)
                assert isinstance(value, dict)
                operations = value["operations"]
                representative = value["representative"]
                self.assertIsInstance(operations, list)
                self.assertIn(representative, operations)
                registered.extend(operations)
        self.assertEqual(len(registered), len(set(registered)))
        discovered, dynamic_task_routes = _discover_operations()
        self.assertEqual(1, dynamic_task_routes)
        self.assertEqual(discovered, set(registered))

    def test_exact_two_hundred_contention_vectors_are_deterministic(self) -> None:
        vectors = {
            (family, round_number, *_canonical_vector(family, round_number))
            for family in FAMILY_NAMES
            for round_number in range(1, 26)
        }
        self.assertEqual(200, len(vectors))
        self.assertEqual(200, len({vector[-1] for vector in vectors}))

    def test_adversarial_manifest_is_closed_and_references_real_tests(self) -> None:
        manifest = _load("adversarial-fixtures-v1.json")
        self.assertEqual(["ubuntu", "windows"], manifest["platforms"])
        fixtures = manifest["fixtures"]
        self.assertIsInstance(fixtures, list)
        assert isinstance(fixtures, list)
        categories: set[str] = set()
        coverage_ids: set[str] = set()
        for fixture in fixtures:
            self.assertIsInstance(fixture, dict)
            assert isinstance(fixture, dict)
            coverage_id = fixture["coverage_id"]
            self.assertNotIn(coverage_id, coverage_ids)
            coverage_ids.add(coverage_id)
            categories.update(fixture["categories"])
            for test_id in fixture["tests"]:
                parts = test_id.split(".")
                self.assertEqual(4, len(parts), test_id)
                path = ROOT / "tests" / f"{parts[1]}.py"
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                classes = {
                    node.name: {
                        child.name for child in node.body if isinstance(child, ast.FunctionDef)
                    }
                    for node in tree.body
                    if isinstance(node, ast.ClassDef)
                }
                self.assertIn(parts[2], classes, test_id)
                self.assertIn(parts[3], classes[parts[2]], test_id)
        self.assertEqual(ADVERSARIAL_CATEGORIES, categories)

    def test_security_auditor_is_exactly_pinned(self) -> None:
        requirements = (ROOT / "requirements-security.txt").read_text(encoding="utf-8")
        self.assertEqual("pip-audit==2.10.1\n", requirements)

    def test_dependency_finding_is_explicitly_closed_by_the_candidate_pin(self) -> None:
        register = _load("dependency-findings-v1.json")
        findings = register["findings"]
        self.assertIsInstance(findings, list)
        assert isinstance(findings, list)
        self.assertEqual(1, len(findings))
        finding = findings[0]
        self.assertEqual("P1", finding["severity"])
        self.assertEqual("setuptools", finding["package"])
        self.assertEqual("80.9.0", finding["affected_version"])
        self.assertEqual("83.0.0", finding["resolved_version"])
        self.assertEqual("CLOSED_IN_CANDIDATE", finding["status"])
        quality = (ROOT / "requirements-quality.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("setuptools==83.0.0", quality)

    def test_every_baseline_ruff_finding_has_a_closed_disposition(self) -> None:
        register = _load("ruff-findings-v1.json")
        self.assertEqual(
            {"ubuntu_ci": 155, "windows_export": 154}, register["basis_observed_counts"]
        )
        self.assertEqual(0, register["candidate_findings"])
        entries = register["entries"]
        self.assertIsInstance(entries, list)
        assert isinstance(entries, list)
        self.assertEqual(154, len(entries))
        self.assertTrue(
            all(
                entry["category"] in {"correctness", "security", "style-modernization"}
                and entry["risk"] in {"low", "medium", "high"}
                and entry["disposition"] == "CANDIDATE_FIXED"
                for entry in entries
            )
        )
        security = [entry for entry in entries if entry["category"] == "security"]
        self.assertEqual(["S110"], [entry["code"] for entry in security])

    def test_static_security_exceptions_are_exact_and_justified(self) -> None:
        register = _load("security-exceptions-v1.json")
        exceptions = register["exceptions"]
        self.assertIsInstance(exceptions, list)
        assert isinstance(exceptions, list)
        expected = {item["path"]: set(item["codes"]) for item in exceptions}
        self.assertTrue(all(len(item["reason"]) >= 40 for item in exceptions))
        with (ROOT / "pyproject.toml").open("rb") as source:
            configured = tomllib.load(source)["tool"]["ruff"]["lint"]["per-file-ignores"]
        actual = {
            path: {code for code in codes if code.startswith("S")}
            for path, codes in configured.items()
            if path.startswith(("src/", "tools/")) and any(code.startswith("S") for code in codes)
        }
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
