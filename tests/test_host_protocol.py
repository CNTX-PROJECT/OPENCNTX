from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
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
from opencntx.host_protocol import (
    claim_host,
    host_status,
    park_host_input,
    resume_host,
    return_host_input,
)

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
    def test_three_nested_inputs_return_to_exact_step_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = project(Path(temporary_directory))
            delivery = host_status(root, "HOST-A")
            claim = claim_host(root, "HOST-A", delivery["delivery_digest"])
            anchors = []
            for number, kind in enumerate(("SIDE_TOPIC", "FEEDBACK", "EXTENSION"), start=1):
                anchors.append(
                    park_host_input(
                        root,
                        "HOST-A",
                        claim["claim_digest"],
                        input_id=f"INPUT-{number}",
                        classification=kind,
                        step_id="STEP-1",
                        open_outcome_ids=("OUTCOME-1",),
                    )
                )
            self.assertIsNone(anchors[0]["parent_input_id"])
            self.assertEqual("INPUT-1", anchors[1]["parent_input_id"])
            self.assertEqual("INPUT-2", anchors[2]["parent_input_id"])
            with self.assertRaisesRegex(ContinuityError, "newest first"):
                return_host_input(
                    root,
                    "HOST-A",
                    input_id="INPUT-1",
                    input_digest=anchors[0]["input_digest"],
                )
            for anchor in reversed(anchors):
                acknowledgement = return_host_input(
                    root,
                    "HOST-A",
                    input_id=anchor["input_id"],
                    input_digest=anchor["input_digest"],
                )
                self.assertEqual("SAME_STEP", acknowledgement["route"])
                self.assertEqual("RESUME TASK-1 STEP-1", acknowledgement["next_action"])
                self.assertEqual(
                    acknowledgement,
                    return_host_input(
                        root,
                        "HOST-A",
                        input_id=anchor["input_id"],
                        input_digest=anchor["input_digest"],
                    ),
                )

    def test_input_requires_active_claim_and_rejects_state_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = project(Path(temporary_directory))
            with self.assertRaisesRegex(ContinuityError, "active claim"):
                park_host_input(
                    root, "HOST-A", "0" * 64, input_id="INPUT-1",
                    classification="SIDE_TOPIC", step_id="STEP-1"
                )
            delivery = host_status(root, "HOST-A")
            claim = claim_host(root, "HOST-A", delivery["delivery_digest"])
            anchor = park_host_input(
                root, "HOST-A", claim["claim_digest"], input_id="INPUT-1",
                classification="SIDE_TOPIC", step_id="STEP-1"
            )
            (root / "evidence.txt").write_text("changed\n", encoding="utf-8")
            # Evidence bytes are not part of the flow state until a checkpoint;
            # the exact parked state therefore remains resumable.
            acknowledgement = return_host_input(
                root, "HOST-A", input_id="INPUT-1", input_digest=anchor["input_digest"]
            )
            self.assertEqual("SAME_STEP", acknowledgement["route"])
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
            events = (root / ".opencntx" / "continuity" / "history" / "events.jsonl").read_text(
                encoding="utf-8"
            )
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
                host: host_status(root, host)["delivery_digest"] for host in ("HOST-A", "HOST-B")
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
            events = (root / ".opencntx" / "continuity" / "history" / "events.jsonl").read_text(
                encoding="utf-8"
            )
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

    def test_authority_is_bound_and_claim_protocol_remains_nonexecuting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = project(Path(temporary_directory))
            delivery = host_status(root, "HOST-A")
            claim = claim_host(root, "HOST-A", delivery["delivery_digest"])
            record = json.loads(
                (root / ".opencntx" / "continuity" / "claims" / "TASK-1.json").read_text(
                    encoding="utf-8"
                )
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

    def test_unbound_pilot_refuses_self_approval_and_valid_looking_actions_without_writes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "parent").mkdir()
            (root / "child").mkdir()
            source = root / "source.txt"
            expected = root / "parent" / "same-name.txt"
            wrong = root / "child" / "same-name.txt"
            source.write_text("approved bytes\n", encoding="utf-8")
            expected.write_text("old parent bytes\n", encoding="utf-8")
            wrong.write_text("protected child bytes\n", encoding="utf-8")

            def action(target: str, approved_target: str, **extra: object) -> Path:
                value: dict[str, object] = {
                    "format": "opencntx-guarded-copy",
                    "format_version": 1,
                    "source": "source.txt",
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "target": target,
                    "target_sha256": hashlib.sha256((root / target).read_bytes()).hexdigest(),
                    "approved_target": approved_target,
                }
                value.update(extra)
                path = root / "action.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                return path

            environment = os.environ.copy()
            existing = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = os.pathsep.join(
                part for part in (str(ROOT / "src"), existing) if part
            )

            def invoke(path: Path) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "opencntx",
                        "flow",
                        "guarded-copy",
                        str(path),
                        "--root",
                        str(root),
                        "--json",
                    ],
                    cwd=root,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )

            rejected = invoke(action("child/same-name.txt", "parent/same-name.txt"))
            self.assertEqual(2, rejected.returncode)
            self.assertIn("invalid choice: 'guarded-copy'", rejected.stderr)
            self.assertEqual("protected child bytes\n", wrong.read_text(encoding="utf-8"))
            self.assertEqual("old parent bytes\n", expected.read_text(encoding="utf-8"))

            unbounded = invoke(
                action(
                    "parent/same-name.txt",
                    "parent/same-name.txt",
                    command="copy source.txt parent/same-name.txt",
                )
            )
            self.assertEqual(2, unbounded.returncode)
            self.assertIn("invalid choice: 'guarded-copy'", unbounded.stderr)
            self.assertEqual("old parent bytes\n", expected.read_text(encoding="utf-8"))

            before = {p.relative_to(root): p.read_bytes() for p in (source, expected, wrong)}
            for target in ("parent/same-name.txt", "child/same-name.txt"):
                with self.subTest(target=target):
                    refused = invoke(action(target, target))
                    self.assertEqual(2, refused.returncode, refused.stderr)
                    self.assertIn("invalid choice: 'guarded-copy'", refused.stderr)
                    self.assertEqual("", refused.stdout)
                    self.assertEqual(
                        before,
                        {p.relative_to(root): p.read_bytes() for p in (source, expected, wrong)},
                    )
                    self.assertEqual(
                        {"source.txt", "parent", "child", "action.json"},
                        {p.name for p in root.iterdir()},
                    )

    def test_retired_pilot_refuses_before_any_action_path_access(self) -> None:
        from unittest.mock import patch

        from opencntx.host_protocol import guarded_copy

        with patch.object(Path, "resolve", side_effect=AssertionError("unexpected path access")):
            with self.assertRaises(ContinuityError) as caught:
                guarded_copy(Path("missing-root"), Path("missing-action"))
            self.assertEqual("guarded_copy_host_unbound", caught.exception.code)

    def test_host_claim_schema_is_closed(self) -> None:
        schema = json.loads(
            (ROOT / "src/opencntx/schemas/host-claim-v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual("AUTO PILOT", schema["properties"]["authority"]["const"])


if __name__ == "__main__":
    unittest.main()
