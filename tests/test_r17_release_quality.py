from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import language_gate
import quality_gate
import schema_purpose_gate


class StartHereQualityTests(unittest.TestCase):
    def _measure(self, words: int) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "start-here.md"
            path.write_text(" ".join(f"word-{number}" for number in range(words)), encoding="utf-8")
            return quality_gate.check_start_here_budget(path)

    def test_one_tokenizer_warns_from_one_thousand_without_hard_limit(self) -> None:
        below = self._measure(999)
        boundary = self._measure(1000)
        above = self._measure(1500)
        self.assertEqual("OK", below["status"])
        self.assertEqual("WARN", boundary["status"])
        self.assertEqual("WARN", above["status"])
        self.assertIsNone(boundary["hard_limit"])

    def test_unicode_words_are_counted_as_data(self) -> None:
        self.assertEqual(5, quality_gate.count_document_words("café naïef 東京 привет data"))

    def test_real_start_here_is_measured_and_reported(self) -> None:
        result = quality_gate.check_start_here_budget()
        self.assertGreaterEqual(result["words"], 1000)
        self.assertEqual("WARN", result["status"])
        self.assertIsNone(result["hard_limit"])

    def test_solo_and_concurrent_routes_are_explicit(self) -> None:
        continuity = (ROOT / "docs" / "continuity.md").read_text(encoding="utf-8")
        self.assertIn("For one host", continuity)
        self.assertIn("concurrent-host protocol", continuity)
        self.assertIn("single writer", continuity)
        self.assertIn("GLOBAL_RECOVERY_2", continuity)


class LanguageQualityTests(unittest.TestCase):
    def test_current_source_has_only_intentional_unicode(self) -> None:
        result = language_gate.check_language()
        self.assertEqual(11, result["literal_count"])
        self.assertEqual(12, result["character_count"])
        self.assertEqual(["legacy_i18n", "unicode_symbol"], result["purposes"])
        self.assertEqual([], result["violations"])

    def test_unmarked_unicode_product_text_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            source = Path(temp_name) / "bad.py"
            source.write_text("message = 'café'\n", encoding="utf-8")
            with self.assertRaises(language_gate.LanguageGateError):
                language_gate.check_language([source])

    def test_explicit_legacy_translation_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            source = Path(temp_name) / "legacy.py"
            source.write_text(
                "message = 'Eén oud bericht' if legacy else 'One old message'\n",
                encoding="utf-8",
            )
            result = language_gate.check_language([source])
        self.assertEqual(["legacy_i18n"], result["purposes"])
        self.assertEqual([], result["violations"])


class SchemaPurposeTests(unittest.TestCase):
    def test_every_r17_schema_has_one_unique_declared_need(self) -> None:
        result = schema_purpose_gate.check_schema_purposes()
        self.assertEqual(84, result["schema_count"])
        self.assertEqual(73, result["baseline_count"])
        self.assertEqual(11, result["new_schema_count"])
        self.assertEqual(11, result["unique_purposes"])
        self.assertEqual([], result["undeclared_new"])

    def test_an_undeclared_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            schema_root = Path(temp_name)
            for path in (ROOT / "src" / "opencntx" / "schemas").iterdir():
                (schema_root / path.name).write_bytes(path.read_bytes())
            (schema_root / "surprise-v1.schema.json").write_text("{}\n", encoding="ascii")
            with self.assertRaises(schema_purpose_gate.SchemaPurposeError):
                schema_purpose_gate.check_schema_purposes(schema_root=schema_root)


class DistributionDecisionTests(unittest.TestCase):
    def test_pypi_remains_a_new_exact_owner_decision(self) -> None:
        text = (ROOT / "docs" / "release-artifacts.md").read_text(encoding="utf-8")
        self.assertIn("PyPI and TestPyPI remain outside the", text)
        self.assertIn("current distribution route", text)
        self.assertIn("materially changed", text)
        self.assertIn("new exact OWNER decision", text)


class PilotProtocolTests(unittest.TestCase):
    def test_real_pilot_remains_separate_measured_and_reversible(self) -> None:
        text = " ".join(
            (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8").split()
        )
        for required in (
            "local R17 implementation",
            "separate decision",
            "at least two weeks",
            "25 real tasks",
            "three genuine restart or handoff events",
            "Synthetic tasks may test the harness but never count as pilot success",
            "Rollback restores",
            "grants no publication, installation, or adoption authority",
        ):
            self.assertIn(required, text)

if __name__ == "__main__":
    unittest.main()
