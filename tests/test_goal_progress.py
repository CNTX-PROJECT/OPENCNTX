from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from importlib import resources
from pathlib import Path
from unittest.mock import patch

from opencntx import goal_progress as p
from opencntx.continuity import (
    ContinuityError,
    execution_state_capsule,
    record_execution_checkpoint,
)
from opencntx.goal_binding import build_goal_binding
from opencntx.task_assessment import TaskFacts
from tests import test_goal_binding as goal_fixture
from tests import test_reference_host as host_fixture


def nodes() -> list[dict]:
    def node(identifier: str, outcomes: list[str], parent: str | None = "MAIN") -> dict:
        return {
            "id": identifier,
            "parent": parent,
            "return_to": parent,
            "children": [],
            "depends_on": [],
            "outcome_ids": outcomes,
            "source_snapshot": [{"reference": "probe.txt", "sha256": "a" * 64}],
            "evidence": [],
            "status": "OPEN",
            "next_action": "Continue exact outcome",
        }

    return [
        node("MAIN", ["PARENT-RESULT", "CHILD-PRESERVATION"], None)
        | {"children": ["WRITE", "PRESERVE"]},
        node("WRITE", ["PARENT-RESULT"]),
        node("PRESERVE", ["CHILD-PRESERVATION"]),
    ]


class GoalProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = goal_fixture.GoalBindingTests()
        fixture.setUp()
        self.goal, self.args = fixture.bound, fixture.args
        self.nodes = nodes()

    def build(self, **kwargs) -> p.GoalProgress:
        return p.build_goal_progress(self.goal, root_id="MAIN", nodes=self.nodes, **kwargs)

    def test_blocked_sibling_does_not_block_independent_leaf(self) -> None:
        self.nodes[2]["status"] = "BLOCKED"
        result = p.progress_readiness(self.build(), self.goal)
        self.assertEqual(result["ready_nodes"], ["WRITE"])
        self.assertEqual(result["blocked_nodes"], ["PRESERVE"])
        self.assertEqual(result["parent_status"], "PARTIAL")
        self.assertEqual(set(result["open_outcome_ids"]), set(self.args["outcome_ids"]))

    def test_blocked_dependency_or_parent_blocks_only_affected_work(self) -> None:
        self.nodes[2]["status"] = "BLOCKED"
        self.nodes[1]["depends_on"] = ["PRESERVE"]
        self.assertEqual(p.progress_readiness(self.build(), self.goal)["ready_nodes"], [])
        self.nodes[1]["depends_on"] = []
        self.nodes[0]["status"] = "BLOCKED"
        self.assertEqual(p.progress_readiness(self.build(), self.goal)["ready_nodes"], [])

    def test_labels_alone_never_close_parent(self) -> None:
        for node in self.nodes:
            node["status"] = "DELIVERED"
        self.assertEqual(p.progress_readiness(self.build(), self.goal)["parent_status"], "PARTIAL")

    def test_schema_version_and_node_catalog(self) -> None:
        schema = json.loads(
            resources.files("opencntx")
            .joinpath("schemas/goal-progress-v2.schema.json")
            .read_text(encoding="utf-8")
        )
        value = self.build().payload()
        self.assertEqual(set(schema["required"]), set(value))
        self.assertEqual(
            set(schema["properties"]["nodes"]["items"]["required"]), set(value["nodes"][0])
        )
        for version in (1, 3, True, "2"):
            altered = value | {"format_version": version}
            altered["progress_digest"] = p._value_digest(
                {k: v for k, v in altered.items() if k != "progress_digest"}
            )
            with self.assertRaises(ContinuityError):
                p.validate_goal_progress(p.GoalProgress(json.dumps(altered)), self.goal)

    def test_missing_cycle_duplicate_return_or_lost_outcome_rejected(self) -> None:
        changes = [
            lambda n: n.pop(),
            lambda n: n[1].update(parent="PRESERVE"),
            lambda n: n[1].update(return_to="OTHER"),
            lambda n: n[0].update(children=["WRITE"]),
            lambda n: n[1].update(depends_on=["WRITE"]),
            lambda n: n[0].update(depends_on=["WRITE"]),
            lambda n: n[1].update(depends_on=["MAIN"]),
            lambda n: (n[1].update(depends_on=["PRESERVE"]), n[2].update(depends_on=["WRITE"])),
            lambda n: n.append(copy.deepcopy(n[1])),
        ]
        for change in changes:
            candidate = copy.deepcopy(self.nodes)
            change(candidate)
            with self.subTest(change=change), self.assertRaises(ContinuityError):
                p.build_goal_progress(self.goal, root_id="MAIN", nodes=candidate)

    def test_stale_revision_and_foreign_request_rejected(self) -> None:
        progress = self.build()
        for change in ({"revision": 2}, {"request_id": "OTHER"}):
            newer = build_goal_binding(**(self.args | change))
            with self.assertRaises(ContinuityError):
                p.validate_goal_progress(progress, newer)

    def test_split_merge_retains_all_obligations_and_old_evidence(self) -> None:
        self.nodes[1]["evidence"] = [{"reference": "old.txt", "sha256": "b" * 64}]
        first = self.build()
        self.nodes = [
            self.nodes[0] | {"children": ["MERGED"]},
            self.nodes[1]
            | {"id": "MERGED", "outcome_ids": self.args["outcome_ids"], "evidence": []},
        ]
        merged = self.build(previous=first)
        self.assertEqual(merged.payload()["request"], first.payload()["request"])
        self.assertIn(
            {"reference": "old.txt", "sha256": "b" * 64}, merged.payload()["retained_evidence"]
        )
        self.nodes = nodes()
        split = self.build(previous=merged)
        self.assertEqual(split.payload()["revision"], 3)
        self.assertEqual(
            split.payload()["previous_progress_digest"], merged.payload()["progress_digest"]
        )
        self.assertEqual(
            set(p.progress_readiness(split, self.goal)["open_outcome_ids"]),
            set(self.args["outcome_ids"]),
        )


@unittest.skipUnless(sys.platform == "win32", "Closed Windows reference host integration")
class NativeGoalProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        host_fixture.ReferenceHostTests.setUp(self)
        self.nodes = nodes()
        self.evidence_directory = self.root / "evidence"
        self.evidence_directory.mkdir()
        (self.root / "probe.txt").write_bytes(b"Representative immutable source fixture")
        for node in self.nodes:
            node["source_snapshot"][0]["sha256"] = host_fixture._digest(
                (self.root / "probe.txt").read_bytes()
            )

    def prepare(self) -> p.GoalProgress:
        progress = p.build_goal_progress(self.host.expected, root_id="MAIN", nodes=self.nodes)
        p.persist_goal_progress(
            self.root, self.host.expected, progress, evidence_directory=self.evidence_directory
        )
        self.host = host_fixture.host(
            self.root,
            assessment_facts=TaskFacts(kind="MULTI_STREAM", independent_large_streams=2),
            progress_node_id="WRITE",
        )
        return progress

    def test_native_checkpoint_resume_and_independent_actual_execution(self) -> None:
        self.nodes[2]["status"] = "BLOCKED"
        progress = self.prepare()
        loaded = p.load_goal_progress(self.root, self.host.expected)
        self.assertEqual(loaded, progress)
        before = host_fixture.snapshot(self.fixture)
        reply = self.host.dispatch(self.host.expected.payload())
        self.assertEqual(reply["decision"], "ALLOW", reply)
        for name in host_fixture.f.WATCHED[3:]:
            self.assertEqual(
                host_fixture.snapshot(self.fixture)[str(Path(name))], before[str(Path(name))]
            )

    def test_missing_hierarchy_is_not_a_ready_flag(self) -> None:
        self.host = host_fixture.host(self.root, progress_node_id="WRITE")
        before = host_fixture.snapshot(self.fixture)
        self.assertEqual(self.host.dispatch(self.host.expected.payload())["decision"], "DENY")
        self.assertEqual(host_fixture.snapshot(self.fixture), before)

    def test_changed_source_snapshot_refuses_before_native_progress(self) -> None:
        progress = p.build_goal_progress(self.host.expected, root_id="MAIN", nodes=self.nodes)
        before = execution_state_capsule(self.root)
        (self.root / "probe.txt").write_bytes(b"Different source")
        with self.assertRaises(ContinuityError):
            p.persist_goal_progress(
                self.root, self.host.expected, progress, evidence_directory=self.evidence_directory
            )
        self.assertEqual(execution_state_capsule(self.root), before)

    def test_protected_state_cannot_be_caller_evidence_directory(self) -> None:
        progress = p.build_goal_progress(self.host.expected, root_id="MAIN", nodes=self.nodes)
        with self.assertRaises(ContinuityError):
            p.persist_goal_progress(
                self.root, self.host.expected, progress, evidence_directory=self.root / ".opencntx"
            )

    def test_blocked_exact_node_never_borrows_sibling_readiness(self) -> None:
        self.nodes[1]["status"] = "BLOCKED"
        self.prepare()
        before = host_fixture.snapshot(self.fixture)
        reply = self.host.dispatch(self.host.expected.payload())
        self.assertEqual(reply["decision"], "DENY", reply)
        self.assertEqual(host_fixture.snapshot(self.fixture), before)

    def test_orphan_preparation_is_not_current_after_restart(self) -> None:
        first = self.prepare()
        changed = copy.deepcopy(self.nodes)
        changed[1]["status"] = "BLOCKED"
        second = p.build_goal_progress(
            self.host.expected, root_id="MAIN", nodes=changed, previous=first
        )
        before = execution_state_capsule(self.root)
        with (
            patch.object(
                p, "record_execution_checkpoint", side_effect=RuntimeError("Injected prepare crash")
            ),
            self.assertRaises(RuntimeError),
        ):
            p.persist_goal_progress(
                self.root, self.host.expected, second, evidence_directory=self.evidence_directory
            )
        self.assertEqual(execution_state_capsule(self.root), before)
        self.assertEqual(p.load_goal_progress(self.root, self.host.expected), first)

    def test_concurrent_native_state_change_refuses_stale_commit(self) -> None:
        progress = p.build_goal_progress(self.host.expected, root_id="MAIN", nodes=self.nodes)
        original = p.store_evidence_object
        (self.root / "other.txt").write_text("Independent native writer", encoding="utf-8")

        def competing(*args, **kwargs):
            result = original(*args, **kwargs)
            record_execution_checkpoint(
                self.root,
                checkpoint_id="OTHER",
                current_internal_task="OTHER",
                next_internal_action="Other state",
                evidence_paths=["other.txt"],
                expected_state_digest=execution_state_capsule(self.root)["state_digest"],
            )
            return result

        with (
            patch.object(p, "store_evidence_object", side_effect=competing),
            self.assertRaises(ContinuityError),
        ):
            p.persist_goal_progress(
                self.root, self.host.expected, progress, evidence_directory=self.evidence_directory
            )
        with self.assertRaises(ContinuityError):
            p.load_goal_progress(self.root, self.host.expected)

    def test_package_only_reopen_without_test_imports(self) -> None:
        progress = self.prepare()
        source = str(Path(p.__file__).resolve().parents[1])
        script = """import json,sys
sys.path.insert(0,sys.argv[1])
class NoTests:
 def find_spec(self,fullname,path=None,target=None):
  if fullname == 'tests' or fullname.startswith('tests.'): raise AssertionError('test import')
sys.meta_path.insert(0,NoTests())
from pathlib import Path
from opencntx.goal_binding import BoundGoal
from opencntx.goal_progress import load_goal_progress,progress_readiness
goal=BoundGoal(sys.argv[3])
progress=load_goal_progress(Path(sys.argv[2]),goal)
print(json.dumps({'digest':progress.payload()['progress_digest'],'ready':progress_readiness(progress,goal)['ready_nodes']}))
"""
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                script,
                source,
                str(self.root),
                self.host.expected.canonical_json,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["digest"], progress.payload()["progress_digest"])
        self.assertIn("WRITE", json.loads(result.stdout)["ready"])


if __name__ == "__main__":
    unittest.main()
