from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from opencntx.continuity import (
    ContinuityError,
    _value_digest,
    execution_state_capsule,
    start_flow,
)
from opencntx.human_interface import (
    build_intent_contract,
    intent_readback,
    select_output_profile,
    validate_intent_contract,
)
from opencntx.navigation import (
    activate_chat,
    finalize_chat,
    initialize_navigation,
    navigation_index,
    preview_name_migration,
    register_projection,
    render_navigation_index,
    reserve_chat,
    reserve_note,
    rollover_chat,
    suggest_compact_title,
)
from opencntx.output_contract import (
    build_output_contract,
    extract_bound_session_metrics,
    render_output,
)

ROOT = Path(__file__).resolve().parents[1]


def roadmap(path: Path) -> Path:
    value = {
        "format": "opencntx-continuity-roadmap",
        "format_version": 1,
        "project_id": "PROJECT-A",
        "roadmap_id": "ROADMAP-1",
        "title": "Human interface",
        "assignments": [
            {
                "id": "TASK-1",
                "title": "Interpret intent",
                "detail": "Keep human and technical meaning equal.",
                "depends_on": [],
                "touches": ["input.txt"],
                "conflict": "EXTEND",
                "migration": "Existing input remains readable.",
                "definition_of_done": ["Meaning is preserved"],
            },
            {
                "id": "TASK-2",
                "title": "Render result",
                "detail": "Return a clear human result.",
                "depends_on": ["TASK-1"],
                "touches": ["result.txt"],
                "conflict": "NO_CONFLICT",
                "migration": "",
                "definition_of_done": ["Output is clear"],
            },
        ],
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def metric_records(tokens: int = 16_624_059) -> list[dict[str, object]]:
    return [
        {"type": "message", "payload": {}},
        {
            "type": "token_count",
            "payload": {"info": {"total_token_usage": {"total_tokens": tokens}}},
        },
    ]


class HumanOutputNavigationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def flow_project(self, name: str = "flow") -> Path:
        project = self.root / name
        project.mkdir()
        (project / "input.txt").write_text("existing\n", encoding="utf-8")
        start_flow(project, roadmap(project / "roadmap.json"), "AUTO PILOT")
        return project

    def navigation_project(self, name: str = "navigation") -> Path:
        project = self.root / name
        project.mkdir()
        initialize_navigation(project, project_id="PROJECT-A")
        return project

    def metrics(self, *, tokens: int = 16_624_059) -> dict[str, object]:
        return extract_bound_session_metrics(
            session_id="SESSION-1",
            source_session_id="SESSION-1",
            chat_bytes=17_616_077,
            records=metric_records(tokens),
        )

    def intent(self, language: str, text: str) -> dict[str, object]:
        return build_intent_contract(
            human_intent=text,
            language=language,
            goal="Keep the project understandable and safe.",
            scope=["Current approved assignment"],
            exclusions=["No release"],
            constraints=["Preserve existing evidence"],
            authority_state="APPROVED",
            risks=["Meaning drift"],
            definition_of_done=["Human and machine readback remain equal"],
            next_internal_action="Run the bounded verification.",
        )

    def test_multilingual_intent_round_trip_preserves_semantics(self) -> None:
        for language, text in (
            ("nl", "Hou het kort en ga veilig verder."),
            ("en", "Keep it short and continue safely."),
            ("fr", "Reste bref et continue prudemment."),
        ):
            contract = self.intent(language, text)
            readback = intent_readback(contract)
            self.assertEqual(readback["goal"], contract["goal"])
            self.assertEqual(readback["scope"], contract["scope"])
            self.assertEqual(readback["exclusions"], contract["exclusions"])
            self.assertEqual(readback["authority_state"], contract["authority_state"])
            self.assertEqual(validate_intent_contract(contract), contract)
        altered = self.intent("nl", "Werk veilig.")
        altered["goal"] = "Expanded goal"
        with self.assertRaisesRegex(ContinuityError, "digest"):
            validate_intent_contract(altered)

    def test_missing_material_decision_is_explicit(self) -> None:
        contract = build_intent_contract(
            human_intent="Kies wat veilig is.",
            language="nl",
            goal="Choose a storage boundary.",
            scope=[],
            exclusions=[],
            constraints=[],
            authority_state="OWNER_REQUIRED",
            risks=[],
            definition_of_done=["One boundary is selected"],
            next_internal_action="Wait for the exact choice.",
            missing_material_decision="Use this project or all registered projects?",
        )
        self.assertEqual(
            intent_readback(contract)["missing_material_decision"],
            "Use this project or all registered projects?",
        )
        with self.assertRaisesRegex(ContinuityError, "must be named"):
            build_intent_contract(
                human_intent="Kies.",
                language="nl",
                goal="Choose.",
                scope=[],
                exclusions=[],
                constraints=[],
                authority_state="OWNER_REQUIRED",
                risks=[],
                definition_of_done=[],
                next_internal_action="Wait.",
            )

    def test_output_profile_is_explicit_and_does_not_change_state(self) -> None:
        simple = select_output_profile()
        detailed = select_output_profile("TECHNICAL_DETAILED", scope="SESSION")
        self.assertEqual(simple["profile"], "HUMAN_SIMPLE")
        self.assertEqual(detailed["profile"], "TECHNICAL_DETAILED")
        self.assertFalse(detailed["state_changed"])
        self.assertFalse(detailed["authority_changed"])

    def test_nested_metric_path_and_session_binding_are_exact(self) -> None:
        metric = self.metrics()
        self.assertEqual(metric["status"], "OK")
        self.assertEqual(metric["total_tokens"], 16_624_059)
        self.assertEqual(metric["chat_megabytes"], 16.8)
        wrong_session = extract_bound_session_metrics(
            session_id="SESSION-2",
            source_session_id="SESSION-1",
            chat_bytes=100,
            records=metric_records(),
        )
        self.assertEqual(wrong_session["status"], "SESSION_NOT_FOUND")
        self.assertIsNone(wrong_session["total_tokens"])
        self.assertIsNone(wrong_session["chat_megabytes"])
        missing = extract_bound_session_metrics(
            session_id="SESSION-1",
            source_session_id="SESSION-1",
            chat_bytes=None,
            records=[],
        )
        self.assertEqual(missing["status"], "TOKEN_EVENT_NOT_FOUND")
        malformed = extract_bound_session_metrics(
            session_id="SESSION-1",
            source_session_id="SESSION-1",
            chat_bytes=1,
            records=[{"type": "token_count", "payload": {}}],
        )
        self.assertEqual(malformed["status"], "PARSE_ERROR")
        self.assertIsNone(malformed["total_tokens"])

    def test_active_dutch_output_has_quiet_required_shape(self) -> None:
        capsule = execution_state_capsule(self.flow_project())
        contract = build_output_contract(
            execution_capsule=capsule,
            roadmap_label="R11 — 3/10",
            summary="De controle loopt veilig verder.",
            language="nl",
            metrics=self.metrics(),
            required_capability="STANDARD",
            reasoning_level="LOW",
            thereafter="Controleer het volgende bewijs.",
        )
        rendered = render_output(contract)
        self.assertIn("De controle loopt veilig verder.\n\n\n---\n", rendered)
        self.assertIn("**Roadmap:** R11 — 3/10", rendered)
        self.assertIn("**Nu:** TASK-1 — ACTIVE", rendered)
        self.assertIn("**Daarna:** Controleer het volgende bewijs.", rendered)
        self.assertIn("**Volgende opdracht:** TASK-2 — CONTINUE_AUTOMATICALLY", rendered)
        self.assertIn("**Chat:** 16,80 MB", rendered)
        self.assertIn("**Tokens:** 16.624.059", rendered)
        self.assertNotIn("```text", rendered)

    def changed_capsule(self, project: Path, **changes: object) -> dict[str, object]:
        capsule = execution_state_capsule(project) | changes
        capsule.pop("capsule_digest")
        capsule["capsule_digest"] = _value_digest(capsule)
        return capsule

    def test_owner_gate_has_exactly_one_copy_block_and_no_authority_change(self) -> None:
        project = self.flow_project()
        capsule = self.changed_capsule(project, authority_state="OWNER_REQUIRED")
        contract = build_output_contract(
            execution_capsule=capsule,
            roadmap_label="R11 — assignment complete",
            summary="De huidige opdracht is afgerond.",
            language="nl",
            metrics=self.metrics(),
            required_capability="STANDARD",
            reasoning_level="LOW",
            exact_human_action="START TASK-2",
        )
        rendered = render_output(contract)
        self.assertEqual(rendered.count("```text"), 1)
        self.assertEqual(rendered.count("START TASK-2"), 1)
        self.assertEqual(contract["next_action_state"], "OWNER_DECISION_REQUIRED")
        self.assertFalse(contract["authority_changed"])

    def test_blocked_complete_and_external_states_are_unambiguous(self) -> None:
        project = self.flow_project()
        blocked = self.changed_capsule(
            project,
            assignment_status="BLOCKED",
            continuation_mode="STOP_FAIL_CLOSED",
            recovery_round=3,
        )
        blocked_contract = build_output_contract(
            execution_capsule=blocked,
            roadmap_label="R11 — blocked",
            summary="De bewijsgrens blokkeert verdere uitvoering.",
            language="en",
            metrics=self.metrics(),
            required_capability="ADVANCED",
            reasoning_level="HIGH",
        )
        self.assertEqual(blocked_contract["next_action_state"], "BLOCKED")
        complete = self.changed_capsule(
            project,
            assignment_status="COMPLETED",
            continuation_mode="STOP_COMPLETE",
            current_assignment=None,
            current_internal_task=None,
            next_internal_action=None,
            next_assignment_after_completion=None,
        )
        complete_contract = build_output_contract(
            execution_capsule=complete,
            roadmap_label="R11 — complete",
            summary="The roadmap is fully complete.",
            language="en",
            metrics=self.metrics(),
            required_capability="STANDARD",
            reasoning_level="LOW",
        )
        self.assertEqual(complete_contract["next_action_state"], "NO_FURTHER_ACTION")
        capsule = execution_state_capsule(project)
        external = build_output_contract(
            execution_capsule=capsule,
            roadmap_label="R11 — external check",
            summary="One external action is required.",
            language="en",
            metrics=self.metrics(),
            required_capability="STANDARD",
            reasoning_level="LOW",
            exact_human_action="CONFIRM EXTERNAL RESULT",
            external_action=True,
        )
        self.assertEqual(external["state_digest"], capsule["state_digest"])
        self.assertEqual(external["next_action_state"], "EXTERNAL_ACTION_REQUIRED")

    def test_custom_language_labels_and_detailed_profile(self) -> None:
        capsule = execution_state_capsule(self.flow_project())
        labels = {
            "roadmap": "Feuille de route",
            "now": "Maintenant",
            "thereafter": "Ensuite",
            "next_assignment": "Prochaine mission",
            "chat": "Conversation",
            "tokens": "Jetons",
            "required_model": "Capacité requise",
            "unavailable": "indisponible de façon fiable",
        }
        contract = build_output_contract(
            execution_capsule=capsule,
            roadmap_label="R11 — phase 3",
            summary="Le travail continue.",
            language="fr",
            labels=labels,
            metrics=self.metrics(),
            required_capability="STANDARD",
            reasoning_level="LOW",
            output_profile="TECHNICAL_DETAILED",
            technical_details=["Le digest d'état reste identique."],
        )
        rendered = render_output(contract)
        self.assertIn("**Feuille de route:**", rendered)
        self.assertIn("- Le digest d'état reste identique.", rendered)

    def test_chat_and_note_namespaces_are_separate_and_sortable(self) -> None:
        project = self.navigation_project()
        chats = [
            reserve_chat(
                project,
                project_id="PROJECT-A",
                reservation_key=f"RES-{number}",
                provisional_title=f"Analysis subject {number}",
                topic_id="TOPIC-A",
            )
            for number in range(1, 13)
        ]
        notes = [
            reserve_note(
                project,
                project_id="PROJECT-A",
                note_key=f"NOTE-{number}",
                title=f"Living subject {number}",
            )
            for number in range(1, 4)
        ]
        chat_ids = [item["chat_id"] for item in chats]
        note_ids = [item["note_id"] for item in notes]
        self.assertEqual(chat_ids, sorted(chat_ids))
        self.assertEqual(note_ids, sorted(note_ids))
        self.assertTrue(all(identifier.startswith("C") for identifier in chat_ids))
        self.assertTrue(all(identifier.startswith("N") for identifier in note_ids))
        self.assertFalse(set(chat_ids) & set(note_ids))

    def test_concurrent_chat_reservations_are_unique_and_idempotent(self) -> None:
        project = self.navigation_project()
        results: list[str] = []
        errors: list[str] = []

        def writer(number: int) -> None:
            try:
                record = reserve_chat(
                    project,
                    project_id="PROJECT-A",
                    reservation_key=f"RES-{number}",
                    provisional_title=f"Concurrent analysis {number}",
                    topic_id="TOPIC-A",
                )
                results.append(str(record["chat_id"]))
            except ContinuityError as exc:
                errors.append(exc.code)

        threads = [threading.Thread(target=writer, args=(number,)) for number in range(1, 81)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 80)
        self.assertEqual(len(set(results)), 80)
        index = navigation_index(project, project_id="PROJECT-A")
        ids = [item["chat_id"] for item in index["chats"]]
        self.assertEqual(ids, sorted(ids))
        retry = reserve_chat(
            project,
            project_id="PROJECT-A",
            reservation_key="RES-1",
            provisional_title="Concurrent analysis 1",
            topic_id="TOPIC-A",
        )
        self.assertIn(retry["chat_id"], ids)
        self.assertEqual(len(navigation_index(project, project_id="PROJECT-A")["chats"]), 80)

    def test_rollover_finalizes_source_before_exactly_one_successor(self) -> None:
        project = self.navigation_project()
        source = reserve_chat(
            project,
            project_id="PROJECT-A",
            reservation_key="SOURCE-1",
            provisional_title="Analyzer preparation",
            topic_id="TOPIC-A",
        )
        activate_chat(
            project,
            project_id="PROJECT-A",
            chat_id=str(source["chat_id"]),
            external_metadata={"provider_object": "opaque-123"},
        )
        rollover = rollover_chat(
            project,
            project_id="PROJECT-A",
            source_chat_id=str(source["chat_id"]),
            source_content_summary="Designed a scalable analyzer and verified the durable handoff.",
            source_final_title="Scalable analyzer handoff",
            successor_reservation_key="SUCCESSOR-1",
            successor_provisional_title="Analyzer implementation",
        )
        retry = rollover_chat(
            project,
            project_id="PROJECT-A",
            source_chat_id=str(source["chat_id"]),
            source_content_summary="Designed a scalable analyzer and verified the durable handoff.",
            source_final_title="Scalable analyzer handoff",
            successor_reservation_key="SUCCESSOR-1",
            successor_provisional_title="Analyzer implementation",
        )
        self.assertEqual(rollover["successor"], retry["successor"])
        self.assertEqual(rollover["source"]["state"], "HANDED_OFF")
        self.assertEqual(rollover["source"]["final_title"], "Scalable analyzer handoff")
        self.assertEqual(rollover["successor"]["parent_chat_id"], source["chat_id"])
        self.assertEqual(len(navigation_index(project, project_id="PROJECT-A")["chats"]), 2)

    def test_titles_projection_index_and_migration_preview(self) -> None:
        project = self.navigation_project()
        chat = reserve_chat(
            project,
            project_id="PROJECT-A",
            reservation_key="SOURCE-1",
            provisional_title="Hardware benchmark analysis",
            topic_id="TOPIC-A",
        )
        activate_chat(project, project_id="PROJECT-A", chat_id=str(chat["chat_id"]))
        final = finalize_chat(
            project,
            project_id="PROJECT-A",
            chat_id=str(chat["chat_id"]),
            content_summary="Graphics benchmark performance optimization and stable settings.",
        )
        self.assertLessEqual(len(str(final["final_title"]).split()), 7)
        projection = register_projection(
            project,
            project_id="PROJECT-A",
            stable_id=str(chat["chat_id"]),
            adapter_kind="SYNCED_FOLDER",
            external_id="opaque-file-44",
            sort_order="MODIFIED",
        )
        self.assertFalse(projection["canonical_order_preserved"])
        rendered = render_navigation_index(project, project_id="PROJECT-A")
        self.assertIn(str(final["visible_title"]), rendered)
        before = navigation_index(project, project_id="PROJECT-A")["index_digest"]
        preview = preview_name_migration(["Old analysis", "Old analysis", "Different subject"])
        self.assertTrue(preview["duplicates"])
        self.assertFalse(preview["writes_performed"])
        self.assertEqual(navigation_index(project, project_id="PROJECT-A")["index_digest"], before)
        with self.assertRaisesRegex(ContinuityError, "meaningful"):
            suggest_compact_title("new chat project update")

    def test_contract_catalog_lists_all_r11_03_schemas(self) -> None:
        names = {
            "human-intent-v1.schema.json",
            "human-output-v1.schema.json",
            "session-footer-metrics-v1.schema.json",
            "navigation-index-v1.schema.json",
        }
        catalog = json.loads(
            (ROOT / "src/opencntx/schemas/continuity-contract-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(names.issubset(catalog["schemas"]))
        for name in names:
            schema = json.loads(
                (ROOT / "src/opencntx/schemas" / name).read_text(encoding="utf-8")
            )
            self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
