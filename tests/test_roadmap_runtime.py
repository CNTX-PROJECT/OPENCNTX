from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from opencntx.project_runtime import (
    ProjectRuntimeError,
    evaluate_workstream_state,
    prepare_return_to_parent,
    rebuild_runtime_status,
    roadmap_catalog,
    serialize_integration_queue,
    validate_roadmap_stack,
)
from opencntx.roadmap_runtime import (
    RoadmapRuntimeError,
    evaluate_nested_runtime,
    load_roadmap_corpus,
    restore_sticky_leaf,
    return_to_parent,
    run_roadmap_corpus,
    validate_roadmap_corpus,
)
from opencntx.runtime_contracts import canonical_digest
from tests.test_runtime_contracts import DIGEST, ZERO, samples

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "r9" / "assignment-32-roadmap-runtime-scenarios-v1.json"
SNAPSHOT = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-32-opencntx-public-snapshot-v1.json"
)
ASSIGNMENT_29 = ROOT / "tests" / "fixtures" / "r9" / "assignment-29-scenarios-v1.json"
ASSIGNMENT_31 = ROOT / "tests" / "fixtures" / "r9" / "assignment-31-intake-scenarios-v1.json"
ASSIGNMENT_31_SNAPSHOT = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-31-opencntx-public-snapshot-v1.json"
)


def runtime_records() -> dict[str, object]:
    base = samples()
    project = copy.deepcopy(base["opencntx-project-definition"])
    project.update(
        {
            "collaboration_mode": "TEAM",
            "declared_human_count": 2,
            "goal": "Validate a pure nested roadmap runtime.",
        }
    )
    owner = copy.deepcopy(base["opencntx-actor-binding"])
    architect = copy.deepcopy(owner)
    architect.update(
        {
            "actor_id": "ACTOR_ARCHITECT",
            "record_id": "ACTOR_BINDING_ARCHITECT_R1",
            "role": "ARCHITECT",
            "workstream_id": "WORKSTREAM_MAIN",
        }
    )
    main = copy.deepcopy(base["opencntx-roadmap-definition"])
    main["event_head"] = ZERO
    child = copy.deepcopy(main)
    child.update(
        {
            "record_id": "ROADMAP_DEFINITION_CHILD_R1",
            "roadmap_id": "ROADMAP_CHILD",
            "roadmap_type": "SUBROADMAP",
            "parent_roadmap_id": "ROADMAP_MAIN",
            "parent_node_id": "PHASE_A",
            "return_node_id": "ASSIGNMENT_30",
            "nodes": [
                {
                    "node_id": "ASSIGNMENT_32",
                    "node_type": "ASSIGNMENT",
                    "status": "ACTIVE",
                    "title": "Nested runtime",
                },
                {
                    "node_id": "PHASE_C",
                    "node_type": "PHASE",
                    "status": "ACTIVE",
                    "title": "Roadmap runtime",
                },
            ],
            "relations": [
                {"from": "PHASE_C", "to": "ASSIGNMENT_32", "type": "PARENT_OF"}
            ],
        }
    )
    main_frame = {
        "active_node_id": "ASSIGNMENT_30",
        "event_head": ZERO,
        "policy_digest": DIGEST,
        "projection_digest": DIGEST,
        "return_node_id": None,
        "roadmap_id": "ROADMAP_MAIN",
        "roadmap_revision": 1,
        "schema_digest": DIGEST,
    }
    child_frame = {
        "active_node_id": "ASSIGNMENT_32",
        "event_head": ZERO,
        "policy_digest": DIGEST,
        "projection_digest": DIGEST,
        "return_node_id": "ASSIGNMENT_30",
        "roadmap_id": "ROADMAP_CHILD",
        "roadmap_revision": 1,
        "schema_digest": DIGEST,
    }
    pointer = copy.deepcopy(base["opencntx-runtime-pointer"])
    pointer.update(
        {
            "mode": "LOCKED_EXECUTION",
            "roadmap_stack": [main_frame, child_frame],
            "current_leaf_id": "ASSIGNMENT_32",
            "event_head": ZERO,
        }
    )
    workstream = copy.deepcopy(base["opencntx-workstream-binding"])
    workstream.update(
        {
            "roadmap_id": "ROADMAP_CHILD",
            "current_leaf_id": "ASSIGNMENT_32",
            "actor_id": "ACTOR_ARCHITECT",
        }
    )
    resource = copy.deepcopy(base["opencntx-resource-claim"])
    return {
        "actors": [owner, architect],
        "child": child,
        "main": main,
        "pointer": pointer,
        "project": project,
        "resource": resource,
        "roadmaps": [main, child],
        "workstream": workstream,
    }


class RoadmapRuntimeTests(unittest.TestCase):
    def test_catalog_stack_and_sticky_leaf_are_deterministic_and_pure(self) -> None:
        records = runtime_records()
        roadmaps = records["roadmaps"]
        pointer = records["pointer"]
        before = copy.deepcopy((roadmaps, pointer))
        catalog = roadmap_catalog(roadmaps, project_id="PROJECT_R9")
        stack, digest = validate_roadmap_stack(
            stack=pointer["roadmap_stack"],
            roadmaps=roadmaps,
            project_id="PROJECT_R9",
            main_roadmap_id="ROADMAP_MAIN",
            current_leaf_id="ASSIGNMENT_32",
        )
        self.assertEqual(set(catalog), {"ROADMAP_CHILD", "ROADMAP_MAIN"})
        self.assertEqual(len(stack), 2)
        self.assertEqual(digest, canonical_digest(pointer["roadmap_stack"]))
        self.assertEqual(restore_sticky_leaf(pointer, roadmaps), "ASSIGNMENT_32")
        self.assertEqual((roadmaps, pointer), before)

    def test_stack_drift_parent_return_depth_and_duplicate_fail_closed(self) -> None:
        records = runtime_records()
        pointer = records["pointer"]
        roadmaps = records["roadmaps"]
        cases = []
        stale = copy.deepcopy(pointer["roadmap_stack"])
        stale[-1]["roadmap_revision"] = 2
        cases.append((stale, "runtime_roadmap_drift"))
        wrong_return = copy.deepcopy(pointer["roadmap_stack"])
        wrong_return[-1]["return_node_id"] = "PHASE_A"
        cases.append((wrong_return, "runtime_return_invalid"))
        duplicate = copy.deepcopy(pointer["roadmap_stack"])
        duplicate[-1]["roadmap_id"] = "ROADMAP_MAIN"
        cases.append((duplicate, "runtime_stack_invalid"))
        too_deep = [copy.deepcopy(pointer["roadmap_stack"][0]) for _ in range(9)]
        cases.append((too_deep, "runtime_stack_invalid"))
        for stack, code in cases:
            with self.subTest(code=code), self.assertRaises(ProjectRuntimeError) as error:
                validate_roadmap_stack(
                    stack=stack,
                    roadmaps=roadmaps,
                    project_id="PROJECT_R9",
                    main_roadmap_id="ROADMAP_MAIN",
                    current_leaf_id="ASSIGNMENT_32",
                )
            self.assertEqual(error.exception.code, code)

    def test_workstream_dependency_resource_path_and_serialization_contract(self) -> None:
        records = runtime_records()
        arguments = {
            "project": records["project"],
            "actors": records["actors"],
            "roadmaps": records["roadmaps"],
            "workstreams": [records["workstream"]],
            "resources": [records["resource"]],
        }
        ready = evaluate_workstream_state(**arguments)
        pending = evaluate_workstream_state(**arguments, dependencies={"ASSIGNMENT_31": "ACTIVE"})
        serialized = evaluate_workstream_state(**arguments, shared_integration=True)
        self.assertEqual(ready["result_code"], "WORKSTREAMS_READY")
        self.assertEqual(pending["result_code"], "BLOCKED_DEPENDENCY_NOT_READY")
        self.assertEqual(serialized["result_code"], "SERIALIZED_SHARED_INTEGRATION")
        second_actor = copy.deepcopy(records["actors"][-1])
        second_actor.update(
            {
                "actor_id": "ACTOR_EXECUTOR",
                "record_id": "ACTOR_BINDING_EXECUTOR_R1",
                "role": "EXECUTOR",
                "workstream_id": "WORKSTREAM_SECOND",
            }
        )
        second_stream = copy.deepcopy(records["workstream"])
        second_stream.update(
            {
                "actor_id": "ACTOR_EXECUTOR",
                "record_id": "WORKSTREAM_BINDING_SECOND_R1",
                "workstream_id": "WORKSTREAM_SECOND",
            }
        )
        conflict = evaluate_workstream_state(
            **(
                arguments
                | {
                    "actors": records["actors"] + [second_actor],
                    "workstreams": [records["workstream"], second_stream],
                }
            ),
            target_paths={
                "WORKSTREAM_MAIN": ["shared/path"],
                "WORKSTREAM_SECOND": ["shared/path"],
            },
        )
        self.assertEqual(conflict["result_code"], "BLOCKED_TEAM_OR_RESOURCE_CONFLICT")

    def test_integration_queue_is_order_independent(self) -> None:
        items = [
            {
                "event_digest": "b" * 64,
                "node_id": "NODE_B",
                "roadmap_id": "ROADMAP_MAIN",
                "workstream_id": "WORKSTREAM_B",
            },
            {
                "event_digest": "a" * 64,
                "node_id": "NODE_A",
                "roadmap_id": "ROADMAP_MAIN",
                "workstream_id": "WORKSTREAM_A",
            },
        ]
        self.assertEqual(
            serialize_integration_queue(items),
            serialize_integration_queue(list(reversed(items))),
        )
        self.assertEqual(serialize_integration_queue(items)[0]["node_id"], "NODE_A")

    def test_return_pops_exactly_one_frame_and_never_starts_next_assignment(self) -> None:
        records = runtime_records()
        pointer = copy.deepcopy(records["pointer"])
        pointer["mode"] = "RETURN_TO_PARENT"
        candidate = prepare_return_to_parent(
            pointer=pointer,
            roadmaps=records["roadmaps"],
            owner_accepted=True,
            child_closed=True,
            definition_of_done_complete=True,
            event_chain_valid=True,
        )
        wrapper = return_to_parent(
            pointer=pointer,
            roadmaps=records["roadmaps"],
            owner_accepted=True,
            child_closed=True,
            definition_of_done_complete=True,
            event_chain_valid=True,
        )
        self.assertEqual(candidate, wrapper)
        self.assertEqual(len(candidate["roadmap_stack"]), 1)
        self.assertEqual(candidate["current_leaf_id"], "ASSIGNMENT_30")
        self.assertEqual(candidate["mode"], "LOCKED_EXECUTION")
        self.assertEqual(candidate["revision"], pointer["revision"] + 1)
        self.assertEqual(candidate["expected_previous_digest"], canonical_digest(pointer))
        blocked = copy.deepcopy(pointer)
        blocked["mode"] = "LOCKED_EXECUTION"
        with self.assertRaises(ProjectRuntimeError) as error:
            return_to_parent(
                pointer=blocked,
                roadmaps=records["roadmaps"],
                owner_accepted=True,
                child_closed=True,
                definition_of_done_complete=True,
                event_chain_valid=True,
            )
        self.assertEqual(error.exception.code, "runtime_return_invalid")

    def test_rebuilt_status_has_no_titles_or_leaf_bodies_and_is_deterministic(self) -> None:
        records = runtime_records()
        arguments = {
            "project": records["project"],
            "pointer": records["pointer"],
            "actors": records["actors"],
            "roadmaps": records["roadmaps"],
            "workstreams": [records["workstream"]],
            "resources": [records["resource"]],
        }
        first = evaluate_nested_runtime(**arguments)
        second = evaluate_nested_runtime(**arguments)
        self.assertEqual(first, second)
        encoded = json.dumps(first, sort_keys=True)
        self.assertNotIn("Nested runtime", encoded)
        self.assertNotIn("title", encoded)
        self.assertNotIn("definition_of_done", encoded)
        direct = rebuild_runtime_status(
            pointer=records["pointer"],
            roadmaps=records["roadmaps"],
            workstream_state=first["workstreams"],
        )
        self.assertEqual(first["projection"], direct)

    def test_exact_84_scenario_corpus_is_green_model_free_and_write_free(self) -> None:
        corpus = load_roadmap_corpus(FIXTURE)
        result = run_roadmap_corpus(corpus)
        self.assertEqual(result.scenario_count, 84)
        self.assertEqual(result.passed, 84)
        self.assertEqual(result.failed, 0)
        self.assertTrue(all(not item.writes for item in result.results))
        self.assertRegex(result.result_digest, r"^[0-9a-f]{64}$")

    def test_corpus_unknown_fields_order_digest_and_expected_values_fail_closed(self) -> None:
        corpus = load_roadmap_corpus(FIXTURE)
        mutations = []
        unknown = copy.deepcopy(corpus)
        unknown["unexpected"] = True
        mutations.append(unknown)
        reordered = copy.deepcopy(corpus)
        reordered["records"][0], reordered["records"][1] = (
            reordered["records"][1],
            reordered["records"][0],
        )
        mutations.append(reordered)
        stale_digest = copy.deepcopy(corpus)
        stale_digest["records"][0]["input_digest"] = DIGEST
        mutations.append(stale_digest)
        for mutation in mutations:
            with self.assertRaises(RoadmapRuntimeError) as error:
                validate_roadmap_corpus(mutation)
            self.assertEqual(error.exception.code, "roadmap_corpus_invalid")
        wrong_expected = copy.deepcopy(corpus)
        wrong_expected["records"][0]["expected_result_code"] = "WRONG"
        wrong_expected["records"][0]["scenario"] = "wrong frozen row"
        wrong_expected["records"][0]["input_digest"] = canonical_digest(
            wrong_expected["records"][0]["input"]
        )
        with self.assertRaises(RoadmapRuntimeError):
            run_roadmap_corpus(wrong_expected)

    def test_corpus_input_actor_workstream_unicode_and_duplicate_keys_are_strict(self) -> None:
        corpus = load_roadmap_corpus(FIXTURE)
        canonical = copy.deepcopy(corpus)
        canonical["records"][0]["input"] = dict(
            reversed(list(canonical["records"][0]["input"].items()))
        )
        canonical["records"][0]["input_digest"] = canonical_digest(
            canonical["records"][0]["input"]
        )
        validate_roadmap_corpus(canonical)
        mutations = []
        unknown_field = copy.deepcopy(corpus)
        unknown_field["records"][0]["input"]["unexpected"] = True
        mutations.append(unknown_field)
        unknown_enum = copy.deepcopy(corpus)
        unknown_enum["records"][0]["input"]["actor"]["availability"] = "UNKNOWN"
        mutations.append(unknown_enum)
        non_nfc = copy.deepcopy(corpus)
        non_nfc["records"][0]["input"]["actor"]["actor_id"] = "ACTOR_e\u0301"
        mutations.append(non_nfc)
        for mutation in mutations[:2]:
            mutation["records"][0]["input_digest"] = canonical_digest(
                mutation["records"][0]["input"]
            )
        for mutation in mutations:
            with self.assertRaises(RoadmapRuntimeError) as error:
                validate_roadmap_corpus(mutation)
            self.assertEqual(error.exception.code, "roadmap_corpus_invalid")
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"format": 1, "format": 2}', encoding="utf-8")
            with self.assertRaises(RoadmapRuntimeError) as error:
                load_roadmap_corpus(duplicate)
            self.assertEqual(error.exception.code, "roadmap_corpus_invalid")

    def test_snapshot_and_previous_corpus_bytes_are_frozen(self) -> None:
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["commit"], "29fcbfafeab26b0d881c2e54e8bfc655713e4e50")
        self.assertEqual(snapshot["tree"], "c9fee295032a674a7d35452a50e13c83d9365798")
        self.assertEqual(snapshot["file_count"], 197)
        self.assertEqual(snapshot["total_blob_bytes"], 3_858_552)
        expected = {
            ASSIGNMENT_29: "1d89046fcf8a6ef81724a7a2f3ef7754babe4d684fbff5050b599d0343134088",
            ASSIGNMENT_31: "24d8ef89418a093882af7ff42dee00315d21ee90613ce87a76c5d924ab62e5a4",
            ASSIGNMENT_31_SNAPSHOT: (
                "62ce3ca3d16fe4e5999624fbd405693ce8e7fa38cee0c12c461c1d935901e117"
            ),
        }
        for path, digest in expected.items():
            with self.subTest(path=path.name):
                canonical_bytes = path.read_bytes().replace(b"\r\n", b"\n")
                self.assertEqual(hashlib.sha256(canonical_bytes).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
