from __future__ import annotations

import ast
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from opencntx.continuity import (
    ContinuityError,
    advance_flow,
    flow_status,
    health_report,
    start_flow,
)
from opencntx.host_protocol import claim_host, host_status, resume_host

ROOT = Path(__file__).resolve().parents[1]


def roadmap() -> dict[str, object]:
    assignments = []
    for number in (1, 2):
        assignments.append(
            {
                "id": f"TASK-{number}",
                "title": f"Task {number}",
                "detail": f"Complete bounded task {number}.",
                "depends_on": [] if number == 1 else ["TASK-1"],
                "touches": [],
                "conflict": "EXTEND",
                "migration": "",
                "definition_of_done": [f"Evidence {number} exists"],
            }
        )
    return {
        "format": "opencntx-continuity-roadmap",
        "format_version": 1,
        "project_id": "HOST-TEST",
        "roadmap_id": "HOST-ROADMAP",
        "title": "Host protocol",
        "assignments": assignments,
    }


def project(parent: Path) -> Path:
    target = parent / "project"
    target.mkdir()
    roadmap_path = target / "roadmap.json"
    roadmap_path.write_text(json.dumps(roadmap()), encoding="utf-8")
    start_flow(target, roadmap_path, "AUTO PILOT")
    (target / "evidence.txt").write_text("green\n", encoding="utf-8")
    return target


class HostProtocolTests(unittest.TestCase):
    def test_status_claim_and_retry_deliver_one_idempotent_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = project(Path(temporary_directory))
            delivery = host_status(root, "HOST-A")
            self.assertEqual("DETAIL", delivery["phase"])
            self.assertEqual("TASK-1", delivery["current_assignment"])
            self.assertEqual("NOT_PERFORMED", delivery["execution"])

            first = claim_host(root, "HOST-A", delivery["delivery_digest"])
            retry = claim_host(root, "HOST-A", delivery["delivery_digest"])

            self.assertEqual(first, retry)
            self.assertEqual("EXECUTE", first["phase"])
            self.assertEqual("TASK-1", first["claimed_assignment"])
            events = (
                root / ".opencntx" / "continuity" / "history" / "events.jsonl"
            ).read_text(encoding="utf-8")
            self.assertEqual(1, events.count('"type":"ASSIGNMENT_CLAIMED"'))
            other = host_status(root, "HOST-B")
            self.assertEqual("CLAIMED", other["phase"])
            self.assertIsNone(other["claim_digest"])

    def test_claim_must_bind_advance_and_resume_routes_to_next(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = project(Path(temporary_directory))
            delivery = host_status(root, "HOST-A")
            claim = claim_host(root, "HOST-A", delivery["delivery_digest"])
            with self.assertRaisesRegex(ContinuityError, "claim must bind"):
                advance_flow(root, outcome="PASS", evidence_paths=["evidence.txt"])
            with self.assertRaises(ContinuityError):
                advance_flow(
                    root,
                    outcome="PASS",
                    evidence_paths=["evidence.txt"],
                    host_id="HOST-A",
                    claim_digest="0" * 64,
                )

            advanced = advance_flow(
                root,
                outcome="PASS",
                evidence_paths=["evidence.txt"],
                host_id="HOST-A",
                claim_digest=claim["claim_digest"],
            )
            resumed = resume_host(root, "HOST-A", claim["claim_digest"])
            next_delivery = host_status(root, "HOST-A")

            self.assertEqual("TASK-2", advanced.current_assignment)
            self.assertEqual("NEXT", resumed["phase"])
            self.assertEqual("STATUS TASK-2", resumed["next_action"])
            self.assertEqual("DETAIL", next_delivery["phase"])
            self.assertEqual("TASK-2", next_delivery["current_assignment"])
            self.assertEqual("HEALTHY", health_report(root)["status"])

    def test_concurrent_hosts_produce_exactly_one_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = project(Path(temporary_directory))
            deliveries = {
                host: host_status(root, host)["delivery_digest"]
                for host in ("HOST-A", "HOST-B")
            }

            def attempt(host: str) -> tuple[str, str]:
                try:
                    claim_host(root, host, deliveries[host])
                    return host, "CLAIMED"
                except ContinuityError as exc:
                    return host, exc.code

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(attempt, ("HOST-A", "HOST-B")))

            codes = [code for _host, code in results]
            self.assertEqual(1, codes.count("CLAIMED"))
            conflict_codes = {"continuity_claim_conflict", "continuity_write_conflict"}
            self.assertEqual(1, sum(code in conflict_codes for code in codes))
            losing_host = next(host for host, code in results if code != "CLAIMED")
            with self.assertRaisesRegex(ContinuityError, "already has another claim"):
                claim_host(root, losing_host, deliveries[losing_host])
            events = (
                root / ".opencntx" / "continuity" / "history" / "events.jsonl"
            ).read_text(encoding="utf-8")
            self.assertEqual(1, events.count('"type":"ASSIGNMENT_CLAIMED"'))

    def test_claim_drift_fails_every_normal_read_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = project(Path(temporary_directory))
            delivery = host_status(root, "HOST-A")
            claim_host(root, "HOST-A", delivery["delivery_digest"])
            path = root / ".opencntx" / "continuity" / "claims" / "TASK-1.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            record["host_id"] = "HOST-X"
            path.write_text(json.dumps(record), encoding="utf-8")

            with self.assertRaisesRegex(ContinuityError, "claim differs"):
                host_status(root, "HOST-A")
            with self.assertRaises(ContinuityError):
                flow_status(root)
            with self.assertRaises(ContinuityError):
                health_report(root)

    def test_authority_is_bound_and_protocol_has_no_execution_primitive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = project(Path(temporary_directory))
            delivery = host_status(root, "HOST-A")
            claim = claim_host(root, "HOST-A", delivery["delivery_digest"])
            record = json.loads(
                (
                    root / ".opencntx" / "continuity" / "claims" / "TASK-1.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual("AUTO PILOT", delivery["authority"])
            self.assertEqual("AUTO PILOT", record["authority"])
            self.assertEqual("NOT_PERFORMED", claim["execution"])

        tree = ast.parse((ROOT / "src/opencntx/host_protocol.py").read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("os", imported)

    def test_host_claim_schema_is_closed(self) -> None:
        schema = json.loads(
            (ROOT / "src/opencntx/schemas/host-claim-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual("AUTO PILOT", schema["properties"]["authority"]["const"])


if __name__ == "__main__":
    unittest.main()
