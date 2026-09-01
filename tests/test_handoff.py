from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from opencntx.continuity import (
    ContinuityError,
    advance_flow,
    export_capsule,
    flow_status,
    health_report,
    import_capsule,
    start_flow,
    verify_capsule,
)
from opencntx.continuity_sync import _candidates

ROOT = Path(__file__).resolve().parents[1]


def roadmap_value() -> dict[str, object]:
    return {
        "format": "opencntx-continuity-roadmap",
        "format_version": 1,
        "project_id": "HANDOFF-TEST",
        "roadmap_id": "HANDOFF-ROADMAP",
        "title": "Durable handoff test",
        "assignments": [
            {
                "id": "TASK-1",
                "title": "First task",
                "detail": "Complete the first bounded task.",
                "depends_on": [],
                "touches": [],
                "conflict": "EXTEND",
                "migration": "",
                "definition_of_done": ["First evidence exists"],
            },
            {
                "id": "TASK-2",
                "title": "Second task",
                "detail": "Resume from the durable handoff.",
                "depends_on": ["TASK-1"],
                "touches": [],
                "conflict": "EXTEND",
                "migration": "",
                "definition_of_done": ["Second evidence exists"],
            },
        ],
    }


def start_project(parent: Path, name: str) -> Path:
    project = parent / name
    project.mkdir()
    roadmap = project / "roadmap.json"
    roadmap.write_text(json.dumps(roadmap_value()), encoding="utf-8")
    start_flow(project, roadmap, "AUTO PILOT")
    return project


def write_handoff_input(project: Path, *, result: str = "The implementation is green.") -> Path:
    path = project / "handoff-input.json"
    path.write_text(
        json.dumps(
            {
                "changed_paths": ["src/module.py", "docs/guide.md"],
                "decisions": ["Keep the durable format additive."],
                "evidence_explanation": "Tests and hashes explain the bounded result.",
                "result": result,
                "risks": ["Runtime behavior still needs its declared later simulation."],
            }
        ),
        encoding="utf-8",
    )
    return path


class DurableHandoffTests(unittest.TestCase):
    def test_fresh_session_route_contains_complete_bound_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = start_project(Path(temporary_directory), "project")
            evidence = project / "evidence.txt"
            evidence.write_text("green\n", encoding="utf-8")
            handoff_input = write_handoff_input(project)

            result = advance_flow(
                project,
                outcome="PASS",
                evidence_paths=[evidence.name],
                handoff_path=handoff_input.name,
            )

            handoff_path = project / ".opencntx" / "continuity" / "handoffs" / "TASK-1.json"
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            self.assertEqual("TASK-2", result.current_assignment)
            self.assertIn("handoffs/TASK-1.json", result.minimum_action)
            self.assertEqual(["Keep the durable format additive."], handoff["decisions"])
            self.assertEqual(["src/module.py", "docs/guide.md"], handoff["changed_paths"])
            self.assertEqual("TASK-2", handoff["next_assignment"])
            self.assertEqual([], handoff["dependencies"])
            self.assertEqual("HEALTHY", health_report(project)["status"])

    def test_handoff_drift_fails_status_health_capsule_and_sync_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = start_project(Path(temporary_directory), "project")
            (project / "evidence.txt").write_text("green\n", encoding="utf-8")
            advance_flow(project, outcome="PASS", evidence_paths=["evidence.txt"])
            handoff_path = project / ".opencntx" / "continuity" / "handoffs" / "TASK-1.json"
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            handoff["result"] = "tampered"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

            with self.assertRaisesRegex(ContinuityError, "Handoff differs"):
                flow_status(project)
            with self.assertRaises(ContinuityError):
                health_report(project)
            with self.assertRaises(ContinuityError):
                export_capsule(project, Path(temporary_directory) / "drift.ocx")
            with self.assertRaises(ContinuityError):
                _candidates(project)

    def test_secret_handoff_is_blocked_before_receipt_event_or_handoff_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = start_project(Path(temporary_directory), "project")
            (project / "evidence.txt").write_text("green\n", encoding="utf-8")
            handoff_input = write_handoff_input(
                project,
                result="DB_PASSWORD=super-secret-password",
            )
            store = project / ".opencntx" / "continuity"
            events_before = (store / "history" / "events.jsonl").read_bytes()

            with self.assertRaisesRegex(ContinuityError, "secret filter"):
                advance_flow(
                    project,
                    outcome="PASS",
                    evidence_paths=["evidence.txt"],
                    handoff_path=handoff_input.name,
                )

            self.assertEqual(events_before, (store / "history" / "events.jsonl").read_bytes())
            self.assertFalse((store / "receipts" / "TASK-1-complete.json").exists())
            self.assertFalse((store / "handoffs").exists())
            self.assertEqual("TASK-1", flow_status(project).current_assignment)

    def test_extended_secret_handoff_is_blocked_without_exposing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = start_project(Path(temporary_directory), "project")
            (project / "evidence.txt").write_text("green\n", encoding="utf-8")
            secret = "correct horse battery staple"
            handoff_input = write_handoff_input(
                project,
                result=f'APP_SECRET="{secret}"',
            )

            with self.assertRaises(ContinuityError) as caught:
                advance_flow(
                    project,
                    outcome="PASS",
                    evidence_paths=["evidence.txt"],
                    handoff_path=handoff_input.name,
                )

            self.assertIn("secret filter", str(caught.exception))
            self.assertNotIn(secret, str(caught.exception))

    def test_capsule_import_and_sync_candidates_preserve_exact_safe_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            project = start_project(parent, "project")
            (project / "evidence.txt").write_text("green\n", encoding="utf-8")
            handoff_input = write_handoff_input(project)
            advance_flow(
                project,
                outcome="PASS",
                evidence_paths=["evidence.txt"],
                handoff_path=handoff_input.name,
            )
            source = project / ".opencntx" / "continuity" / "handoffs" / "TASK-1.json"
            source_bytes = source.read_bytes()
            _project_id, candidates = _candidates(project)
            candidate_paths = {item["source"] for item in candidates}
            self.assertIn(source, candidate_paths)

            capsule = parent / "project.ocx"
            export_capsule(project, capsule)
            verification = verify_capsule(capsule)
            self.assertEqual("VERIFIED", verification["status"])
            with zipfile.ZipFile(capsule) as archive:
                self.assertIn("continuity/handoffs/TASK-1.json", archive.namelist())

            restored = parent / "restored"
            import_capsule(restored, capsule)
            restored_handoff = (
                restored / ".opencntx" / "continuity" / "handoffs" / "TASK-1.json"
            )
            self.assertEqual(source_bytes, restored_handoff.read_bytes())
            self.assertEqual("HEALTHY", health_report(restored)["status"])

    def test_handoff_schema_is_closed_and_packaged(self) -> None:
        schema = json.loads(
            (ROOT / "src/opencntx/schemas/continuity-handoff-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual("opencntx-continuity-handoff", schema["properties"]["format"]["const"])
        self.assertIn("handoff_digest", schema["required"])


if __name__ == "__main__":
    unittest.main()
