from __future__ import annotations

import copy
import unittest

from opencntx.knowledge import KnowledgeError, _canonical_json, _digest
from opencntx.presentation import (
    append_footer_once,
    presentation_footer,
    validate_host_presentation,
    visual_projection,
)
from tests.test_visual_design import intent


def envelope() -> dict:
    unknown = {"value": None, "source": None, "measured_at": None}
    value = {
        "format": "ocx-footer-host-envelope-v2",
        "format_version": 2,
        "session_id": "SESSION-1",
        "context_generation": "GEN-1",
        "source_digest": "a" * 64,
        "proposal": None,
        "metrics": {
            name: dict(unknown) for name in ("chat_bytes", "total_tokens", "model", "reasoning")
        },
    }
    value["metrics"]["total_tokens"] = {
        "value": 1234,
        "source": "host cumulative counter",
        "measured_at": "2026-09-17T00:00:00+00:00",
    }
    return seal(value)


def seal(value: dict) -> dict:
    value["envelope_digest"] = _digest(
        _canonical_json({k: v for k, v in value.items() if k != "envelope_digest"})
    )
    return value


BINDING = {"session_id": "SESSION-1", "context_generation": "GEN-1", "source_digest": "a" * 64}


class PresentationTests(unittest.TestCase):
    def test_partial_metrics_are_explicit_and_provider_neutral(self) -> None:
        text = presentation_footer(envelope(), **BINDING)
        self.assertIn("**Chat:** not measured", text)
        self.assertIn("**Tokens:** \u22481,2k", text)
        self.assertIn("**Model:** unknown", text)
        self.assertNotIn("Luna", text)
        self.assertIn("**Proposal:** not specified", text)
        with self.assertRaises(KnowledgeError):
            presentation_footer(envelope(), **BINDING, locale="unsupported")

    def test_context_changes_and_unknown_fields_are_rejected(self) -> None:
        for key in BINDING:
            binding = BINDING | {key: "b" * 64}
            with self.subTest(key=key), self.assertRaises(KnowledgeError):
                validate_host_presentation(envelope(), **binding)
        value = envelope()
        value["extra"] = True
        with self.assertRaises(KnowledgeError):
            validate_host_presentation(seal(value), **BINDING)

    def test_provenance_and_counters_fail_closed(self) -> None:
        for change in (
            {"value": -1},
            {"value": True},
            {"measured_at": "yesterday"},
            {"source": ""},
        ):
            value = copy.deepcopy(envelope())
            value["metrics"]["total_tokens"].update(change)
            with self.subTest(change=change), self.assertRaises(KnowledgeError):
                validate_host_presentation(seal(value), **BINDING)

    def test_structured_output_and_repeat_rendering_are_preserved(self) -> None:
        for kind in ("json", "tool", "code"):
            self.assertEqual(presentation_footer(envelope(), **BINDING, output_kind=kind), "")
        footer = presentation_footer(envelope(), **BINDING)
        first = append_footer_once("Task finished.", footer)
        self.assertEqual(append_footer_once(first, footer), first)
        self.assertEqual(append_footer_once('{"ok":true}', ""), '{"ok":true}')

    def test_visual_role_and_fallback_never_invent_inspection(self) -> None:
        brief = intent()
        text = visual_projection(brief)
        graphic = visual_projection(brief, graphical_preview=True)
        self.assertEqual(text["role_id"], "VISUAL_ARTIST")
        self.assertEqual(text["intent_digest"], brief["intent_digest"])
        self.assertEqual(text["mode"], "TEXT_FALLBACK")
        self.assertEqual(graphic["mode"], "PREVIEW_REQUIRED")
        self.assertFalse(graphic["visual_inspection_performed"])


if __name__ == "__main__":
    unittest.main()
