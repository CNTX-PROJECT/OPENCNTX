from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from opencntx.continuity import (
    ContinuityError,
    _value_digest,
    execution_state_capsule,
    record_execution_checkpoint,
    start_flow,
)
from opencntx.session_continuity import (
    accept_session_handoff,
    assess_session_rollover,
    normalize_session_metrics,
    prepare_session_handoff,
    session_handoff_status,
    session_heartbeat,
    store_evidence_object,
    verify_evidence_object,
)

ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = {
    "can_create_target": True,
    "can_report_ready": True,
    "can_acknowledge": True,
}


def roadmap(path: Path, *, project_id: str = "PROJECT-A") -> Path:
    value = {
        "format": "opencntx-continuity-roadmap",
        "format_version": 1,
        "project_id": project_id,
        "roadmap_id": "ROADMAP-1",
        "title": "Session continuity",
        "assignments": [
            {
                "id": "TASK-1",
                "title": "Continue safely",
                "detail": "Preserve the exact active task.",
                "depends_on": [],
                "touches": ["input.txt"],
                "conflict": "EXTEND",
                "migration": "Existing content remains readable.",
                "definition_of_done": ["Target acknowledgement is bound"],
            },
            {
                "id": "TASK-2",
                "title": "Finish safely",
                "detail": "Close only after exact proof.",
                "depends_on": ["TASK-1"],
                "touches": ["result.txt"],
                "conflict": "NO_CONFLICT",
                "migration": "",
                "definition_of_done": ["Roadmap is complete"],
            },
        ],
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class SessionContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def project(self, name: str = "project", *, project_id: str = "PROJECT-A") -> Path:
        project = self.root / name
        project.mkdir()
        (project / "input.txt").write_text("existing\n", encoding="utf-8")
        start_flow(project, roadmap(project / "roadmap.json", project_id=project_id), "AUTO PILOT")
        return project

    def handoff(self, project: Path, identifier: str = "HANDOFF-1") -> dict[str, object]:
        return prepare_session_handoff(
            project,
            handoff_id=identifier,
            source_part="10 - Analysis part one",
            target_part="11 - Analysis part two",
            provider_capabilities=CAPABILITIES,
            rollback_boundary="Keep the source active until target acknowledgement.",
            exclusions=["Do not start TASK-2."],
        )

    def test_metrics_are_normalized_and_advisory(self) -> None:
        project = self.project()
        before = execution_state_capsule(project)["state_digest"]
        normalized = normalize_session_metrics({"chat_bytes": 30 * 1_048_576})
        self.assertEqual(normalized["available"], ["chat_bytes"])
        self.assertEqual(
            assess_session_rollover({"chat_bytes": 30 * 1_048_576})["signal"],
            "PREPARE_HANDOFF",
        )
        self.assertEqual(
            assess_session_rollover({"context_percent": 95})["signal"],
            "HANDOFF_NOW",
        )
        self.assertEqual(assess_session_rollover({})["signal"], "METRICS_UNAVAILABLE")
        self.assertEqual(execution_state_capsule(project)["state_digest"], before)
        with self.assertRaisesRegex(ContinuityError, "unknown fields"):
            normalize_session_metrics({"provider_magic": 1})

    def test_heartbeat_is_compact_and_does_not_write_state(self) -> None:
        project = self.project()
        before = execution_state_capsule(project)
        heartbeat = session_heartbeat(project, elapsed_seconds=125)
        self.assertEqual(heartbeat["active_assignment"], "TASK-1")
        self.assertEqual(heartbeat["last_checkpoint"], 0)
        self.assertFalse(heartbeat["intervention_required"])
        self.assertEqual(heartbeat["decision"], "CONTINUE")
        self.assertEqual(execution_state_capsule(project), before)

    def test_evidence_is_compressed_deduplicated_and_byte_equal(self) -> None:
        project = self.project()
        content = b"\xff" + (b"bounded evidence\n" * 2_000_000)
        first = store_evidence_object(
            project,
            content=content,
            summary="Large synthetic tool output stored outside the chat.",
            error_lines=["No unique errors."],
        )
        second = store_evidence_object(
            project,
            content=content,
            summary="A later duplicate may use a different summary.",
            error_lines=["A duplicate does not create a second object."],
        )
        self.assertEqual(first, second)
        self.assertLess(first["compressed_bytes"], first["bytes"])
        self.assertTrue(verify_evidence_object(project, str(first["sha256"]))["verified"])
        objects = project / ".opencntx" / "continuity" / "evidence-objects"
        self.assertEqual(len(list(objects.glob("*.gz"))), 1)
        self.assertEqual(len(list(objects.glob("*.json"))), 1)

    def test_handoff_is_compact_idempotent_and_acknowledged(self) -> None:
        project = self.project()
        evidence = store_evidence_object(
            project, content=b"full output\n", summary="One compact evidence reference."
        )
        values = {
            "handoff_id": "HANDOFF-1",
            "source_part": "10 - Analysis part one",
            "target_part": "11 - Analysis part two",
            "provider_capabilities": CAPABILITIES,
            "rollback_boundary": "Keep source active until acknowledgement.",
            "evidence_object_digests": [str(evidence["sha256"])],
        }
        first = prepare_session_handoff(project, **values)
        second = prepare_session_handoff(project, **values)
        self.assertEqual(first, second)
        self.assertNotIn("full output", json.dumps(first))
        self.assertEqual(session_handoff_status(project, "HANDOFF-1")["source_may_idle"], False)
        acknowledgement = accept_session_handoff(
            project, handoff_id="HANDOFF-1", target_part="11 - Analysis part two"
        )
        self.assertEqual(acknowledgement["status"], "RESUME_AUTOMATICALLY")
        self.assertEqual(
            accept_session_handoff(
                project, handoff_id="HANDOFF-1", target_part="11 - Analysis part two"
            ),
            acknowledgement,
        )
        self.assertTrue(session_handoff_status(project, "HANDOFF-1")["source_may_idle"])

    def test_state_change_requires_reconciliation(self) -> None:
        project = self.project()
        self.handoff(project)
        initial = execution_state_capsule(project)
        record_execution_checkpoint(
            project,
            checkpoint_id="CP-1",
            current_internal_task="Verify new state",
            next_internal_action="Continue after verification",
            evidence_paths=["input.txt"],
            expected_state_digest=initial["state_digest"],
        )
        acknowledgement = accept_session_handoff(
            project, handoff_id="HANDOFF-1", target_part="11 - Analysis part two"
        )
        self.assertEqual(acknowledgement["status"], "RECONCILE_REQUIRED")
        status = session_handoff_status(project, "HANDOFF-1")
        self.assertFalse(status["source_may_idle"])
        self.assertEqual(status["next_action"], "SOURCE_REMAINS_ACTIVE")

    def test_owner_blocker_and_complete_states_stop_safely(self) -> None:
        for name, changes, expected in (
            ("owner", {"authority_state": "OWNER_REQUIRED"}, "WAIT_FOR_OWNER"),
            (
                "blocked",
                {
                    "assignment_status": "BLOCKED",
                    "continuation_mode": "STOP_FAIL_CLOSED",
                    "recovery_round": 3,
                },
                "STOP_WITH_EVIDENCE",
            ),
            (
                "complete",
                {
                    "assignment_status": "COMPLETED",
                    "continuation_mode": "STOP_COMPLETE",
                    "current_assignment": None,
                    "current_internal_task": None,
                    "next_internal_action": None,
                    "next_assignment_after_completion": None,
                },
                "STOP_WITH_EVIDENCE",
            ),
        ):
            project = self.project(name)
            self.handoff(project)
            capsule = execution_state_capsule(project) | changes
            capsule.pop("capsule_digest")
            capsule["capsule_digest"] = _value_digest(capsule)
            with patch("opencntx.session_continuity._capsule_from_loaded", return_value=capsule):
                acknowledgement = accept_session_handoff(
                    project, handoff_id="HANDOFF-1", target_part="11 - Analysis part two"
                )
            self.assertEqual(acknowledgement["status"], expected)

    def test_cross_project_and_tampered_handoffs_fail_closed(self) -> None:
        source = self.project("source", project_id="PROJECT-A")
        target = self.project("target", project_id="PROJECT-B")
        self.handoff(source)
        destination = target / ".opencntx" / "continuity" / "session-handoffs"
        destination.mkdir()
        shutil.copy2(
            source / ".opencntx" / "continuity" / "session-handoffs" / "HANDOFF-1.json",
            destination / "HANDOFF-1.json",
        )
        with self.assertRaisesRegex(ContinuityError, "another project"):
            accept_session_handoff(
                target, handoff_id="HANDOFF-1", target_part="11 - Analysis part two"
            )
        path = source / ".opencntx" / "continuity" / "session-handoffs" / "HANDOFF-1.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["next_internal_action"] = "stale"
        path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ContinuityError, "capsule is invalid"):
            session_handoff_status(source, "HANDOFF-1")

    def test_degrade_path_yields_exactly_one_copy_action(self) -> None:
        project = self.project()
        capabilities = CAPABILITIES | {"can_create_target": False}
        handoff = prepare_session_handoff(
            project,
            handoff_id="HANDOFF-1",
            source_part="10 - Analysis part one",
            target_part="11 - Analysis part two",
            provider_capabilities=capabilities,
            rollback_boundary="Keep source active.",
        )
        self.assertEqual(handoff["target_creation"], "COPY_ACTION_REQUIRED")
        self.assertEqual(handoff["continuation_action"], "OPEN HANDOFF HANDOFF-1")
        self.assertEqual(
            session_handoff_status(project, "HANDOFF-1")["next_action"],
            "OPEN HANDOFF HANDOFF-1",
        )

    def test_concurrent_prepare_has_one_record(self) -> None:
        project = self.project()
        results: list[str] = []
        errors: list[str] = []

        def writer() -> None:
            try:
                results.append(str(self.handoff(project)["handoff_digest"]))
            except ContinuityError as exc:
                errors.append(exc.code)

        threads = [threading.Thread(target=writer) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(len(set(results)), 1)
        handoffs = project / ".opencntx" / "continuity" / "session-handoffs"
        self.assertEqual(len(list(handoffs.glob("*.json"))), 1)

    def test_contract_catalog_lists_all_additive_schemas(self) -> None:
        schema_names = {
            "session-metrics-v1.schema.json",
            "session-handoff-v1.schema.json",
            "session-handoff-ack-v1.schema.json",
            "evidence-object-v1.schema.json",
        }
        catalog = json.loads(
            (ROOT / "src/opencntx/schemas/continuity-contract-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(schema_names.issubset(catalog["schemas"]))
        for name in schema_names:
            schema = json.loads(
                (ROOT / "src/opencntx/schemas" / name).read_text(encoding="utf-8")
            )
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
