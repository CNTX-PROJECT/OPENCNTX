from __future__ import annotations

import json
import random
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from opencntx.adaptive_storage import (
    adaptive_storage_state,
    apply_storage_cleanup,
    build_storage_cleanup_plan,
    build_storage_profile_plan,
    build_storage_query,
    create_storage_generation,
    initialize_adaptive_storage,
    put_storage_record,
    recommend_storage_profile,
    release_storage_record,
    restore_storage_generation,
    search_adaptive_storage,
    team_compare_and_swap_event,
    validate_team_adapter,
)
from opencntx.workspace import WorkspaceError

ROOT = Path(__file__).resolve().parents[1]
MEASUREMENTS = {
    "object_count": 10,
    "total_bytes": 1_000,
    "monthly_change_bytes": 100,
    "queries_per_day": 2,
    "concurrent_writers": 1,
}


class MemoryTeamAdapter:
    def __init__(self, capabilities: dict[str, bool] | None = None) -> None:
        self._capabilities = capabilities or {
            "identity": True,
            "roles": True,
            "audit": True,
            "compare_and_swap": True,
            "distributed_lock": True,
        }
        self._states: dict[str, dict[str, object]] = {}
        self._lock = threading.Lock()

    def capabilities(self) -> dict[str, object]:
        return dict(self._capabilities)

    def read_state(self, project_id: str) -> dict[str, object] | None:
        with self._lock:
            value = self._states.get(project_id)
            return json.loads(json.dumps(value)) if value is not None else None

    def compare_and_swap(
        self, project_id: str, expected_revision: int, state: dict[str, object]
    ) -> bool:
        with self._lock:
            current = self._states.get(project_id)
            revision = int(current["revision"]) if current is not None else 0
            if revision != expected_revision:
                return False
            self._states[project_id] = json.loads(json.dumps(state))
            return True


class AdaptiveStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def create_store(
        self,
        profile: str,
        *,
        name: str | None = None,
        soft: int = 10 * 1024 * 1024,
        hard: int = 20 * 1024 * 1024,
        reserve: int = 1024 * 1024,
    ) -> Path:
        root = self.root / (name or profile.lower())
        root.mkdir()
        plan = build_storage_profile_plan(
            root,
            project_id="PROJECT-A",
            current_profile=profile,
            measurements=MEASUREMENTS,
            soft_limit_bytes=soft,
            hard_limit_bytes=hard,
            rollback_reserve_bytes=reserve,
        )
        initialize_adaptive_storage(root, plan)
        return root

    def put(
        self,
        root: Path,
        record_id: str,
        content: bytes,
        *,
        relations: tuple[str, ...] = (),
        data_class: str = "SEARCHABLE_TEXT",
    ) -> dict[str, object]:
        state = adaptive_storage_state(root, project_id="PROJECT-A")
        return put_storage_record(
            root,
            project_id="PROJECT-A",
            expected_revision=int(state["revision"]),
            record_id=record_id,
            content=content,
            data_class=data_class,
            source=f"source/{record_id}",
            relations=relations,
        )

    def test_recommendations_are_measured_and_million_scale_is_read_only(self) -> None:
        self.assertEqual(recommend_storage_profile(MEASUREMENTS), "TINY_LOCAL")
        self.assertEqual(
            recommend_storage_profile(MEASUREMENTS | {"object_count": 2_000}),
            "LOCAL_INDEXED",
        )
        large = MEASUREMENTS | {"object_count": 1_000_000, "total_bytes": 10 * 1024**3}
        self.assertEqual(recommend_storage_profile(large), "LARGE_LOCAL")
        self.assertEqual(
            recommend_storage_profile(MEASUREMENTS | {"concurrent_writers": 3}),
            "TEAM_SHARED",
        )
        root = self.root / "preview"
        root.mkdir()
        plan = build_storage_profile_plan(
            root,
            project_id="PROJECT-A",
            current_profile="TINY_LOCAL",
            measurements=large,
            soft_limit_bytes=100,
            hard_limit_bytes=1_000,
            rollback_reserve_bytes=100,
        )
        self.assertEqual(plan["recommended_profile"], "LARGE_LOCAL")
        self.assertFalse(plan["writes_performed"])
        self.assertEqual(list(root.iterdir()), [])

    def test_material_profile_change_requires_explicit_approval(self) -> None:
        root = self.root / "gate"
        root.mkdir()
        blocked = build_storage_profile_plan(
            root,
            project_id="PROJECT-A",
            current_profile="TINY_LOCAL",
            requested_profile="LOCAL_INDEXED",
            migration_approved=False,
            measurements=MEASUREMENTS,
            soft_limit_bytes=100,
            hard_limit_bytes=1_000,
            rollback_reserve_bytes=100,
        )
        self.assertEqual(blocked["target_profile"], "TINY_LOCAL")
        self.assertEqual(blocked["migration_status"], "OWNER_APPROVAL_REQUIRED")
        with self.assertRaises(WorkspaceError):
            initialize_adaptive_storage(root, blocked | {"target_profile": "LOCAL_INDEXED"})

    def test_tiny_profile_has_no_database_and_deduplicates_one_thousand_records(self) -> None:
        root = self.create_store("TINY_LOCAL", hard=30 * 1024 * 1024)
        content = b"one immutable checkpoint\n" * 100
        physical_writes = 0
        for index in range(1_000):
            receipt = self.put(root, f"REC-{index:04d}", content)
            physical_writes += int(bool(receipt["physical_object_written"]))
        self.assertEqual(physical_writes, 1)
        objects = list((root / ".opencntx" / "adaptive-storage" / "objects").rglob("*.gz"))
        self.assertEqual(len(objects), 1)
        self.assertFalse((root / ".opencntx" / "adaptive-storage" / "indexes").exists())

    def test_hard_limit_stops_before_new_object_write(self) -> None:
        root = self.create_store("TINY_LOCAL", name="budget", soft=2_000, hard=5_000, reserve=1_000)
        content = random.Random(7).randbytes(50_000)
        with self.assertRaisesRegex(WorkspaceError, "hard limit"):
            self.put(root, "REC-BIG", content)
        self.assertEqual(
            list((root / ".opencntx" / "adaptive-storage" / "objects").rglob("*.gz")),
            [],
        )
        self.assertEqual(adaptive_storage_state(root, project_id="PROJECT-A")["revision"], 0)

    def test_same_query_contract_for_all_local_profiles(self) -> None:
        observed = []
        for profile in ("TINY_LOCAL", "LOCAL_INDEXED", "LARGE_LOCAL"):
            root = self.create_store(profile, name=f"query-{profile}")
            self.put(root, "REC-A", b"dragon armor durable note", relations=("REC-B",))
            self.put(root, "REC-B", b"unrelated text")
            query = build_storage_query(
                project_id="PROJECT-A", text="dragon", relation_to="REC-B", limit=1
            )
            result = search_adaptive_storage(root, query)
            observed.append([item["record_id"] for item in result["results"]])
            self.assertEqual(result["semantic_status"], "DISABLED")
            self.assertEqual(result["results"][0]["provenance"]["profile"], profile)
            if profile == "TINY_LOCAL":
                self.assertEqual(result["strategy"], "MANIFEST_SCAN")
            else:
                self.assertEqual(result["strategy"], "SQLITE_INDEX")
        self.assertEqual(observed, [["REC-A"], ["REC-A"], ["REC-A"]])

    def test_pagination_and_optional_semantic_adapter_status(self) -> None:
        root = self.create_store("LOCAL_INDEXED", name="paging")
        for index in range(3):
            self.put(root, f"REC-{index}", f"shared term {index}".encode())
        first = search_adaptive_storage(
            root,
            build_storage_query(
                project_id="PROJECT-A", text="shared", limit=2, semantic_requested=True
            ),
        )
        self.assertEqual(len(first["results"]), 2)
        self.assertEqual(first["next_cursor"], 2)
        second = search_adaptive_storage(
            root,
            build_storage_query(project_id="PROJECT-A", text="shared", cursor=2, limit=2),
        )
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(first["semantic_status"], "ADAPTER_REQUIRED")

    def test_generations_restore_and_cleanup_only_unreferenced_managed_objects(self) -> None:
        root = self.create_store("LOCAL_INDEXED", name="restore")
        self.put(root, "REC-A", b"version one")
        state = adaptive_storage_state(root, project_id="PROJECT-A")
        first = create_storage_generation(
            root,
            project_id="PROJECT-A",
            expected_revision=int(state["revision"]),
            created_at="2026-09-01T00:00:00Z",
        )
        self.put(root, "REC-A", b"version two")
        state = adaptive_storage_state(root, project_id="PROJECT-A")
        second = create_storage_generation(
            root,
            project_id="PROJECT-A",
            expected_revision=int(state["revision"]),
            created_at="2026-09-02T00:00:00Z",
        )
        self.put(root, "REC-TEMP", b"temporary generation")
        state = adaptive_storage_state(root, project_id="PROJECT-A")
        release_storage_record(
            root,
            project_id="PROJECT-A",
            expected_revision=int(state["revision"]),
            record_id="REC-TEMP",
        )
        storage = root / ".opencntx" / "adaptive-storage"
        unknown = storage / "objects" / "do-not-touch.bin"
        unknown.write_bytes(b"owner data")
        plan = build_storage_cleanup_plan(root, project_id="PROJECT-A")
        self.assertEqual(len(plan["candidates"]), 1)
        receipt = apply_storage_cleanup(root, project_id="PROJECT-A", plan=plan)
        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertEqual(apply_storage_cleanup(root, project_id="PROJECT-A", plan=plan), receipt)
        self.assertEqual(unknown.read_bytes(), b"owner data")
        self.assertEqual(
            restore_storage_generation(
                root, project_id="PROJECT-A", generation_id=str(first["generation_id"])
            )["REC-A"],
            b"version one",
        )
        self.assertEqual(
            restore_storage_generation(
                root, project_id="PROJECT-A", generation_id=str(second["generation_id"])
            )["REC-A"],
            b"version two",
        )

    def test_cleanup_rolls_back_before_state_and_resumes_after_state(self) -> None:
        root = self.create_store("TINY_LOCAL", name="cleanup-crash")
        self.put(root, "REC-X", b"orphan after release")
        state = adaptive_storage_state(root, project_id="PROJECT-A")
        release_storage_record(
            root,
            project_id="PROJECT-A",
            expected_revision=int(state["revision"]),
            record_id="REC-X",
        )
        plan = build_storage_cleanup_plan(root, project_id="PROJECT-A")

        def before_state(phase: str) -> None:
            if phase.startswith("AFTER_STAGE"):
                raise RuntimeError("injected stage failure")

        with self.assertRaisesRegex(RuntimeError, "stage failure"):
            apply_storage_cleanup(
                root, project_id="PROJECT-A", plan=plan, fault_hook=before_state
            )
        self.assertEqual(len(build_storage_cleanup_plan(root, project_id="PROJECT-A")["candidates"]), 1)

        def after_state(phase: str) -> None:
            if phase == "AFTER_STATE":
                raise RuntimeError("injected receipt failure")

        with self.assertRaisesRegex(RuntimeError, "receipt failure"):
            apply_storage_cleanup(
                root, project_id="PROJECT-A", plan=plan, fault_hook=after_state
            )
        resumed = apply_storage_cleanup(root, project_id="PROJECT-A", plan=plan)
        self.assertEqual(resumed["status"], "COMPLETED")
        self.assertEqual(build_storage_cleanup_plan(root, project_id="PROJECT-A")["candidates"], [])

    def test_generation_retention_is_bounded_and_keeps_newest_two(self) -> None:
        root = self.create_store("TINY_LOCAL", name="retention")
        identifiers = []
        for index in range(40):
            self.put(root, "REC-A", f"version {index}".encode())
            state = adaptive_storage_state(root, project_id="PROJECT-A")
            generation = create_storage_generation(
                root,
                project_id="PROJECT-A",
                expected_revision=int(state["revision"]),
                created_at=f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}T00:00:00Z",
            )
            identifiers.append(generation["generation_id"])
        state = adaptive_storage_state(root, project_id="PROJECT-A")
        retained = [item["generation_id"] for item in state["generations"]]
        self.assertLessEqual(len(retained), 23)
        self.assertIn(identifiers[-1], retained)
        self.assertIn(identifiers[-2], retained)

    def test_team_capabilities_roles_audit_and_cas_allow_one_writer(self) -> None:
        adapter = MemoryTeamAdapter()
        self.assertEqual(validate_team_adapter(adapter)["status"], "READY")

        def write(index: int) -> str:
            try:
                team_compare_and_swap_event(
                    adapter,
                    project_id="PROJECT-A",
                    actor_id=f"ACTOR-{index}",
                    role="WRITER",
                    expected_revision=0,
                    operation_digest=f"digest-{index}",
                )
            except WorkspaceError:
                return "CONFLICT"
            return "COMMITTED"

        with ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(executor.map(write, range(8)))
        self.assertEqual(outcomes.count("COMMITTED"), 1)
        self.assertEqual(outcomes.count("CONFLICT"), 7)
        state = adapter.read_state("PROJECT-A")
        self.assertEqual(state["revision"], 1)
        self.assertEqual(len(state["audit"]), 1)
        with self.assertRaises(WorkspaceError):
            team_compare_and_swap_event(
                adapter,
                project_id="PROJECT-A",
                actor_id="READER-1",
                role="READER",
                expected_revision=1,
                operation_digest="read-only",
            )

    def test_incomplete_team_adapter_fails_closed(self) -> None:
        adapter = MemoryTeamAdapter(
            {
                "identity": True,
                "roles": True,
                "audit": True,
                "compare_and_swap": True,
                "distributed_lock": False,
            }
        )
        with self.assertRaisesRegex(WorkspaceError, "capability"):
            validate_team_adapter(adapter)

    def test_r11_05_schemas_are_closed_and_catalogued(self) -> None:
        names = {
            "storage-profile-plan-v1.schema.json",
            "adaptive-storage-state-v1.schema.json",
            "storage-query-v1.schema.json",
            "storage-query-result-v1.schema.json",
            "storage-cleanup-receipt-v1.schema.json",
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
