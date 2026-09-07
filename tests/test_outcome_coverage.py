from __future__ import annotations

import json
import tempfile
import unittest
from importlib import resources
from pathlib import Path

from opencntx.continuity import (
    ContinuityError,
    _digest,
    _value_digest,
    advance_flow,
    execution_state_capsule,
    start_flow,
)
from opencntx.goal_binding import HostSource, build_goal_binding
from opencntx.goal_followup import compile_goal_context
from opencntx.goal_progress import build_goal_progress, persist_goal_progress
from opencntx.human_interface import build_intent_contract
from opencntx.outcome_coverage import (
    OutcomeReport,
    SourceQuery,
    compile_current_outcomes,
    integrate_outcomes,
    run_source_query,
    verify_outcome_source,
)


class OutcomeCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        roadmap = {
            "format": "opencntx-continuity-roadmap",
            "format_version": 1,
            "project_id": "FIXTURE",
            "roadmap_id": "COVERAGE",
            "title": "Source coverage",
            "assignments": [
                {
                    "id": "TASK-1",
                    "title": "Analyze",
                    "detail": "Generic fixture",
                    "depends_on": [],
                    "touches": [],
                    "conflict": "NO_CONFLICT",
                    "migration": "",
                    "definition_of_done": ["All outcomes"],
                }
            ],
        }
        (self.root / "roadmap.json").write_text(json.dumps(roadmap), encoding="utf-8")
        start_flow(self.root, self.root / "roadmap.json", "AUTO PILOT")
        (self.root / "evidence").mkdir()
        self.intent = build_intent_contract(
            human_intent="Analyze the exact generic source fixtures for A, B and C.",
            language="en",
            goal="Three source-backed outcomes",
            scope=["sources"],
            exclusions=[],
            constraints=["Read only"],
            authority_state="APPROVED",
            risks=["Missing data"],
            definition_of_done=["All three outcomes and synthesis"],
            next_internal_action="Read exact source",
        )
        self.source = HostSource(
            "OWNER", "owner-fixture-message", _digest(self.intent["human_intent"].encode())
        )
        self.oracles = json.loads(
            Path(__file__)
            .with_name("fixtures")
            .joinpath("r15_coverage_oracle.json")
            .read_text(encoding="utf-8")
        )["cases"]

    def goal(self, outcome: str, source_path: str, digest: str):
        return build_goal_binding(
            intent=self.intent,
            execution_capsule=execution_state_capsule(self.root),
            request_id="REQUEST-COVERAGE",
            revision=1,
            parent_request_id=None,
            outcome_ids=["A", "B", "C"],
            source=self.source,
            action={
                "outcome_id": outcome,
                "operation": "READ_EXACT",
                "targets": [source_path],
                "recursive": False,
                "protected_targets": [],
                "preconditions": [
                    {
                        "target": source_path,
                        "sha256": digest,
                        "identity_ref": "immutable-fixture-snapshot",
                    }
                ],
                "capability_ref": "closed-json-source-read",
            },
        )

    def query(self, outcome="A", records=None, limit=None, **kwargs):
        records = self.oracles[0]["records"] if records is None else records
        path = f"source-{outcome}.json"
        content = json.dumps(records).encode()
        (self.root / path).write_bytes(content)
        digest = _digest(content)
        goal = self.goal(outcome, path, digest)
        query = SourceQuery(outcome, path, digest, ("kind",), "kind", "match", **kwargs)
        return goal, run_source_query(
            self.root, message=goal.payload(), expected=goal, query=query, inspect_limit=limit
        )

    def test_manual_three_row_oracle_missing_is_not_zero(self) -> None:
        for oracle in self.oracles:
            with self.subTest(case=oracle["name"]):
                _, report = self.query(records=oracle["records"])
                value = report.payload()
                self.assertEqual(value["denominator"], 3)
                self.assertEqual(value["finding_ids"], oracle["expected_findings"])
                self.assertEqual(list(value["missing_fields"]), oracle["expected_missing"])
                self.assertEqual(value["status"], oracle["expected_status"])
                self.assertEqual(value["acceptance"], "UNKNOWN")

    def test_selective_depth_stays_partial_even_with_match(self) -> None:
        _, report = self.query(limit=1)
        self.assertEqual(report.payload()["finding_ids"], ["A"])
        self.assertEqual(report.payload()["status"], "PARTIAL")

    def test_rehashed_false_green_fails_actual_source_recheck(self) -> None:
        goal, report = self.query(records=self.oracles[2]["records"])
        value = report.payload() | {
            "missing_fields": {},
            "status": "DELIVERED",
            "usability": "USABLE",
        }
        value["report_digest"] = _value_digest(
            {k: v for k, v in value.items() if k != "report_digest"}
        )
        with self.assertRaises(ContinuityError):
            verify_outcome_source(self.root, OutcomeReport(json.dumps(value)), goal)

    def test_empty_verified_collection_can_deliver_zero(self) -> None:
        _, report = self.query(records=[])
        self.assertEqual(report.payload()["denominator"], 0)
        self.assertEqual(report.payload()["status"], "DELIVERED")

    def test_report_and_matrix_schema_catalogs(self) -> None:
        goal, report = self.query()
        for name, value in (
            ("outcome-report-v2", report.payload()),
            ("outcome-matrix-v2", integrate_outcomes(goal, [report])),
        ):
            schema = json.loads(
                resources.files("opencntx")
                .joinpath(f"schemas/{name}.schema.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(set(schema["required"]), set(value))
            self.assertIs(schema["additionalProperties"], False)

    def test_ambiguous_record_identity_or_json_is_rejected(self) -> None:
        for content in (
            b'[{"id":"A","kind":"match"},{"id":"A","kind":"clear"}]',
            b'[{"id":"A","kind":"match","kind":"clear"}]',
            b"{}",
        ):
            (self.root / "bad.json").write_bytes(content)
            goal = self.goal("A", "bad.json", _digest(content))
            query = SourceQuery("A", "bad.json", _digest(content), ("kind",), "kind", "match")
            with self.assertRaises(ContinuityError):
                run_source_query(self.root, message=goal.payload(), expected=goal, query=query)

    def test_source_missing_or_changed_never_becomes_zero(self) -> None:
        goal, _ = self.query()
        digest = goal.payload()["action"]["preconditions"][0]["sha256"]
        query = SourceQuery("A", "source-A.json", digest, ("kind",), "kind", "match")
        (self.root / "source-A.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ContinuityError):
            run_source_query(self.root, message=goal.payload(), expected=goal, query=query)
        (self.root / "source-A.json").unlink()
        with self.assertRaises(ContinuityError):
            run_source_query(self.root, message=goal.payload(), expected=goal, query=query)

    def test_wrong_actual_request_refuses_before_source_read(self) -> None:
        goal, _ = self.query()
        request = goal.payload()
        request["action"]["targets"] = ["other.json"]
        query = SourceQuery(
            "A",
            "source-A.json",
            goal.payload()["action"]["preconditions"][0]["sha256"],
            ("kind",),
            "kind",
            "match",
        )
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.assertRaises(ContinuityError):
            run_source_query(self.root, message=request, expected=goal, query=query)
        self.assertEqual(
            {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before
        )

    def test_two_of_three_and_duplicate_credit_do_not_complete(self) -> None:
        goal, a = self.query("A")
        _, b = self.query("B")
        result = integrate_outcomes(goal, [a, b])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["outcomes"]["C"], "NOT_ASSESSED")
        with self.assertRaises(ContinuityError):
            integrate_outcomes(goal, [a, a])

    def test_conflicting_child_advice_blocks_synthesis(self) -> None:
        goal, a = self.query("A", claim_key="ORDER", match_conclusion="A_FIRST")
        _, b = self.query("B", claim_key="ORDER", match_conclusion="B_FIRST")
        _, c = self.query("C")
        proof = {
            "reports_digest": _value_digest(
                sorted(r.payload()["report_digest"] for r in [a, b, c])
            ),
            "reference": "synthesis.json",
            "sha256": "f" * 64,
            "conclusion": "Host review",
        }
        result = integrate_outcomes(goal, [a, b, c], synthesis_proof=proof)
        self.assertEqual(result["conflicting_claim_keys"], ["ORDER"])
        self.assertEqual(result["status"], "PARTIAL")

    def test_native_bound_reports_and_actual_synthesis_file(self) -> None:
        reports = [self.query(outcome)[1] for outcome in ("A", "B", "C")]
        goal = self.goal("A", "source-A.json", reports[0].payload()["query"]["source_sha256"])

        def ref(name, content):
            (self.root / name).write_bytes(content)
            return {"reference": name, "sha256": _digest(content)}

        children = []
        for report in reports:
            value = report.payload()
            children.append(
                {
                    "id": value["outcome_id"],
                    "parent": "MAIN",
                    "return_to": "MAIN",
                    "children": [],
                    "depends_on": [],
                    "outcome_ids": [value["outcome_id"]],
                    "source_snapshot": [
                        {
                            "reference": value["query"]["source_path"],
                            "sha256": value["query"]["source_sha256"],
                        }
                    ],
                    "evidence": [
                        ref(f"evidence/{value['outcome_id']}.json", report.canonical_json.encode())
                    ],
                    "status": "DELIVERED",
                    "next_action": "Synthesize",
                }
            )
        synthesis = ref(
            "evidence/synthesis.json",
            json.dumps(
                {
                    "reports_digest": _value_digest(
                        sorted(report.payload()["report_digest"] for report in reports)
                    ),
                    "conclusion": "All A/B/C findings match the three-record oracle.",
                }
            ).encode(),
        )
        parent = {
            "id": "MAIN",
            "parent": None,
            "return_to": None,
            "children": ["A", "B", "C"],
            "depends_on": [],
            "outcome_ids": ["A", "B", "C"],
            "source_snapshot": [],
            "evidence": [synthesis],
            "status": "OPEN",
            "next_action": "Review synthesis",
        }
        progress = build_goal_progress(goal, root_id="MAIN", nodes=[parent, *children])
        persist_goal_progress(self.root, goal, progress, evidence_directory=self.root / "evidence")
        fresh = self.goal("A", "source-A.json", reports[0].payload()["query"]["source_sha256"])
        self.assertEqual(compile_current_outcomes(self.root, fresh)["status"], "PARTIAL")
        result = compile_current_outcomes(
            self.root, fresh, synthesis_reference="evidence/synthesis.json"
        )
        self.assertEqual(result["status"], "TECHNICALLY_COMPLETE")
        self.assertEqual(result["acceptance"], "UNKNOWN")
        with self.assertRaises(ContinuityError):
            compile_current_outcomes(self.root, fresh, synthesis_reference="unbound.json")
        advance_flow(self.root, outcome="PASS", evidence_paths=["evidence/synthesis.json"])
        closed_goal = self.goal(
            "A", "source-A.json", reports[0].payload()["query"]["source_sha256"]
        )
        closed = compile_goal_context(
            self.root, closed_goal, synthesis_reference="evidence/synthesis.json"
        )
        self.assertEqual(closed["decision"], "COMPLETE_ROADMAP")
        self.assertEqual(closed["open_outcome_ids"], [])
        from opencntx.connected_state import connected_status, publish_connected_state

        publish_connected_state(
            self.root,
            goal=closed_goal,
            expected_state_digest=closed_goal.payload()["execution_capsule_v1"]["state_digest"],
            synthesis_reference="evidence/synthesis.json",
        )
        self.assertTrue(connected_status(self.root)["completion_allowed"])
        from opencntx.combo import load_combo

        combo = load_combo(self.root)
        self.assertFalse(combo["active"])
        self.assertEqual(combo["recent_completed"][0]["status"], "COMPLETED")

    def test_scale_has_exact_independent_denominator_and_findings(self) -> None:
        for count in (10, 100, 1000, 4001):
            records = [
                {"id": str(i), "kind": "match" if i % 7 == 0 else "clear"} for i in range(count)
            ]
            _, report = self.query(records=records)
            value = report.payload()
            self.assertEqual(value["denominator"], count)
            self.assertEqual(value["finding_ids"], [str(i) for i in range(0, count, 7)])
            self.assertEqual(value["status"], "DELIVERED")


if __name__ == "__main__":
    unittest.main()
