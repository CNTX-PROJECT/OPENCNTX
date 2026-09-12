from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from opencntx.transactional_update import apply_update_plan, update_postflight
from tests import test_transactional_update as fixtures


class RuntimeUpdateHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.TransactionalUpdateTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_broken_candidate_is_detected_before_any_cutover(self) -> None:
        root, components = self.fixture.update_fixture("broken-candidate")
        candidate = Path(components[0]["candidate_path"])
        (candidate / "startup.py").write_text("raise RuntimeError('broken')\n", encoding="utf-8")
        plan = self.fixture.plan(root, components)

        def probe(selected, phase):
            runtime = next(item for item in selected["components"] if item["name"] == "RUNTIME")
            path = Path(runtime["candidate_path" if phase == "CANDIDATE" else "active_path"])
            subprocess.run(
                [sys.executable, "-I", "-B", str(path / "startup.py")],
                check=True,
                capture_output=True,
                timeout=30,
            )

        with self.assertRaises(subprocess.CalledProcessError):
            apply_update_plan(
                plan, approval=f"APPLY UPDATE {plan['plan_digest']}", runtime_check=probe
            )
        self.assertFalse(Path(plan["backup_path"]).exists())
        for item in components:
            self.assertTrue((Path(item["active_path"]) / "old-only.txt").is_file())

    def test_failed_active_health_restores_old_generation(self) -> None:
        root, components = self.fixture.update_fixture("failed-activation")
        plan = self.fixture.plan(root, components)
        phases = []

        def probe(selected, phase):
            phases.append(phase)
            if phase == "ACTIVE":
                self.assertTrue(
                    all(
                        (Path(item["active_path"]) / "new-only.txt").is_file()
                        for item in selected["components"]
                    )
                )
                raise RuntimeError("startup failed after activation")

        with self.assertRaisesRegex(RuntimeError, "startup failed"):
            apply_update_plan(
                plan, approval=f"APPLY UPDATE {plan['plan_digest']}", runtime_check=probe
            )
        self.assertEqual(["CANDIDATE", "ACTIVE"], phases)
        for item in components:
            self.assertTrue((Path(item["active_path"]) / "old-only.txt").is_file())
        self.assertEqual("REPAIR_REQUIRED", update_postflight(plan)["status"])

    def test_replay_rechecks_real_health(self) -> None:
        root, components = self.fixture.update_fixture("health-replay")
        plan = self.fixture.plan(root, components)
        phases = []
        approval = f"APPLY UPDATE {plan['plan_digest']}"
        first = apply_update_plan(
            plan, approval=approval, runtime_check=lambda _, phase: phases.append(phase)
        )
        second = apply_update_plan(
            plan, approval=approval, runtime_check=lambda _, phase: phases.append(phase)
        )
        self.assertEqual(first, second)
        self.assertEqual(["CANDIDATE", "ACTIVE", "ACTIVE"], phases)


if __name__ == "__main__":
    unittest.main()
