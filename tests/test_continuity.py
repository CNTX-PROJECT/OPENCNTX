from __future__ import annotations

import json
import os
import subprocess
import sys
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
    inspect_adapter,
    preview_roadmap,
    start_flow,
    verify_capsule,
)
from opencntx.continuity_sync import (
    apply_sync,
    build_sync_preview,
    configure_sync,
    sync_status,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"


def roadmap(path: Path) -> Path:
    value = {
        "format": "opencntx-continuity-roadmap",
        "format_version": 1,
        "project_id": "PROJECT-A",
        "roadmap_id": "ROADMAP-1",
        "title": "Portable local flow",
        "assignments": [
            {
                "id": "TASK-1",
                "title": "First task",
                "detail": "Extend the existing local example.",
                "depends_on": [],
                "touches": ["input.txt"],
                "conflict": "EXTEND",
                "migration": "Existing input remains readable.",
                "definition_of_done": ["Evidence exists", "Local state is healthy"],
            },
            {
                "id": "TASK-2",
                "title": "Second task",
                "detail": "Finish the bounded portable flow.",
                "depends_on": ["TASK-1"],
                "touches": ["*.txt"],
                "conflict": "NO_CONFLICT",
                "migration": "",
                "definition_of_done": ["Final evidence exists"],
            },
        ],
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def long_roadmap(path: Path, count: int = 10) -> Path:
    assignments = []
    for number in range(1, count + 1):
        identifier = f"TASK-{number}"
        assignments.append(
            {
                "id": identifier,
                "title": f"Task {number}",
                "detail": f"Complete bounded task {number}.",
                "depends_on": [] if number == 1 else [f"TASK-{number - 1}"],
                "touches": ["input.txt"],
                "conflict": "NO_CONFLICT",
                "migration": "",
                "definition_of_done": [f"Evidence {number} exists"],
            }
        )
    value = {
        "format": "opencntx-continuity-roadmap",
        "format_version": 1,
        "project_id": "PROJECT-A",
        "roadmap_id": "ROADMAP-LONG",
        "title": "Ten task restart proof",
        "assignments": assignments,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class ContinuityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _project(self, name: str = "project") -> tuple[Path, Path]:
        project = self.root / name
        project.mkdir()
        (project / "input.txt").write_text("existing\n", encoding="utf-8")
        return project, roadmap(project / "roadmap.json")

    def _private_replica(self, name: str) -> tuple[Path, Path]:
        bare = self.root / f"{name}.git"
        mirror = self.root / f"{name}-mirror"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        subprocess.run(["git", "init", "-q", str(mirror)], check=True)
        subprocess.run(["git", "-C", str(mirror), "config", "user.name", "Example"], check=True)
        subprocess.run(
            ["git", "-C", str(mirror), "config", "user.email", "example@example.invalid"],
            check=True,
        )
        (mirror / "README.md").write_text("# Private replica\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(mirror), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(mirror), "commit", "-qm", "initial"], check=True)
        subprocess.run(["git", "-C", str(mirror), "branch", "-M", "main"], check=True)
        subprocess.run(["git", "-C", str(mirror), "remote", "add", "origin", str(bare)], check=True)
        subprocess.run(["git", "-C", str(mirror), "push", "-qu", "origin", "main"], check=True)
        return bare, mirror

    def test_preview_is_read_only_and_one_approval_triggers_the_complete_cycle(self) -> None:
        project, roadmap_path = self._project()
        (project / "first.txt").write_text("pass one\n", encoding="utf-8")
        (project / "second.txt").write_text("pass two\n", encoding="utf-8")
        before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
        preview = preview_roadmap(project, roadmap_path)
        after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
        started = start_flow(project, roadmap_path, "AUTO PILOT")
        restarted = flow_status(project)
        second = advance_flow(project, outcome="PASS", evidence_paths=["first.txt"])
        complete = advance_flow(project, outcome="PASS", evidence_paths=["second.txt"])

        self.assertEqual(before, after)
        self.assertEqual(preview["writes"], [])
        self.assertEqual(
            preview["assignments"][0]["existing_check"]["included"][0]["path"],
            "input.txt",
        )
        self.assertEqual(started.current_assignment, "TASK-1")
        self.assertEqual(restarted.state_digest, started.state_digest)
        self.assertEqual(second.current_assignment, "TASK-2")
        self.assertEqual(complete.status, "COMPLETE")
        self.assertEqual(complete.completed, ("TASK-1", "TASK-2"))
        self.assertEqual(health_report(project)["status"], "HEALTHY")

    def test_authority_and_three_round_recovery_fail_closed(self) -> None:
        project, roadmap_path = self._project()
        with self.assertRaisesRegex(ContinuityError, "AUTO PILOT"):
            start_flow(project, roadmap_path, "yes")
        self.assertFalse((project / ".opencntx").exists())
        start_flow(project, roadmap_path, "AUTO PILOT")
        evidence = project / "failure.txt"
        result = None
        for number in range(1, 4):
            evidence.write_text(f"failure {number}\n", encoding="utf-8")
            result = advance_flow(
                project,
                outcome="FAIL",
                evidence_paths=["failure.txt"],
                reason=f"changed failure {number}",
            )
        assert result is not None
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.next_action, "STOP_FAIL_CLOSED")

    def test_recovery_rounds_reset_for_each_assignment(self) -> None:
        project, roadmap_path = self._project()
        start_flow(project, roadmap_path, "AUTO PILOT")
        evidence = project / "evidence.txt"
        for number in range(1, 3):
            evidence.write_text(f"task one failure {number}\n", encoding="utf-8")
            result = advance_flow(
                project,
                outcome="FAIL",
                evidence_paths=[evidence.name],
                reason=f"task one strategy {number}",
            )
            self.assertEqual(result.status, "RECOVERY_REQUIRED")
        evidence.write_text("task one green\n", encoding="utf-8")
        result = advance_flow(project, outcome="PASS", evidence_paths=[evidence.name])
        state = json.loads(
            (project / ".opencntx" / "continuity" / "state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result.current_assignment, "TASK-2")
        self.assertEqual(state["recovery_rounds"], 0)
        self.assertEqual(state["failure_fingerprints"], [])

        for number in range(1, 4):
            evidence.write_text(f"task two failure {number}\n", encoding="utf-8")
            result = advance_flow(
                project,
                outcome="FAIL",
                evidence_paths=[evidence.name],
                reason=f"task two strategy {number}",
            )
            expected = "BLOCKED" if number == 3 else "RECOVERY_REQUIRED"
            self.assertEqual(result.status, expected)

    def test_bound_roadmap_and_all_generated_details_reject_drift(self) -> None:
        roadmap_project, roadmap_path = self._project("roadmap-drift")
        start_flow(roadmap_project, roadmap_path, "AUTO PILOT")
        stored_roadmap = roadmap_project / ".opencntx" / "continuity" / "roadmaps" / "roadmap.json"
        value = json.loads(stored_roadmap.read_text(encoding="utf-8"))
        value["assignments"][1]["detail"] = "Tampered next assignment."
        stored_roadmap.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ContinuityError, "roadmap bound"):
            flow_status(roadmap_project)

        current_project, current_roadmap = self._project("current-detail-drift")
        start_flow(current_project, current_roadmap, "AUTO PILOT")
        current_detail = current_project / ".opencntx" / "continuity" / "details" / "TASK-1.md"
        current_detail.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(ContinuityError, "detail differs"):
            health_report(current_project)
        with self.assertRaises(ContinuityError):
            export_capsule(current_project, self.root / "tampered.ocx")

        historical_project, historical_roadmap = self._project("historical-detail-drift")
        start_flow(historical_project, historical_roadmap, "AUTO PILOT")
        evidence = historical_project / "evidence.txt"
        evidence.write_text("green\n", encoding="utf-8")
        advance_flow(historical_project, outcome="PASS", evidence_paths=[evidence.name])
        historical_detail = (
            historical_project / ".opencntx" / "continuity" / "details" / "TASK-1.md"
        )
        historical_detail.write_text("tampered after completion\n", encoding="utf-8")
        with self.assertRaisesRegex(ContinuityError, "detail differs"):
            flow_status(historical_project)

    def test_current_context_rejects_drift(self) -> None:
        project, roadmap_path = self._project()
        start_flow(project, roadmap_path, "AUTO PILOT")
        context_path = project / ".opencntx" / "continuity" / "context" / "current.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["detail_path"] = "details/TASK-2.md"
        context_path.write_text(json.dumps(context), encoding="utf-8")
        with self.assertRaisesRegex(ContinuityError, "Current context differs"):
            flow_status(project)

    def test_ten_tasks_use_one_authority_and_restart_at_every_transition(self) -> None:
        project = self.root / "long-project"
        project.mkdir()
        (project / "input.txt").write_text("existing\n", encoding="utf-8")
        roadmap_path = long_roadmap(project / "roadmap.json")
        result = start_flow(project, roadmap_path, "AUTO PILOT")
        for number in range(1, 11):
            self.assertEqual(flow_status(project).current_assignment, f"TASK-{number}")
            evidence = project / f"evidence-{number}.txt"
            evidence.write_text(f"green {number}\n", encoding="utf-8")
            result = advance_flow(
                project,
                outcome="PASS",
                evidence_paths=[evidence.name],
            )
            self.assertEqual(flow_status(project).state_digest, result.state_digest)
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(len(result.completed), 10)

    def test_writer_conflict_and_unsafe_or_future_input_fail_closed(self) -> None:
        project, roadmap_path = self._project()
        start_flow(project, roadmap_path, "AUTO PILOT")
        evidence = project / "evidence.txt"
        evidence.write_text("green\n", encoding="utf-8")
        lock = project / ".opencntx" / "continuity" / ".operation.lock"
        before = flow_status(project).state_digest
        lock.write_text("busy\n", encoding="utf-8")
        with self.assertRaisesRegex(ContinuityError, "writer"):
            advance_flow(project, outcome="PASS", evidence_paths=[evidence.name])
        lock.unlink()
        self.assertEqual(flow_status(project).state_digest, before)

        unsafe = json.loads(roadmap_path.read_text(encoding="utf-8"))
        unsafe["assignments"][0]["touches"] = ["../outside.txt"]
        roadmap_path.write_text(json.dumps(unsafe), encoding="utf-8")
        with self.assertRaises(ContinuityError):
            preview_roadmap(project, roadmap_path)
        unsafe["assignments"][0]["touches"] = ["input.txt"]
        unsafe["format_version"] = 2
        roadmap_path.write_text(json.dumps(unsafe), encoding="utf-8")
        with self.assertRaises(ContinuityError):
            preview_roadmap(project, roadmap_path)

    def test_capsule_restore_and_four_adapters_are_read_only(self) -> None:
        project, roadmap_path = self._project()
        (project / "README.md").write_text("# Example\n", encoding="utf-8")
        (project / "data.json").write_text('{"value": 1}\n', encoding="utf-8")
        start_flow(project, roadmap_path, "AUTO PILOT")
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        subprocess.run(["git", "-C", str(project), "config", "user.name", "Example"], check=True)
        subprocess.run(
            ["git", "-C", str(project), "config", "user.email", "example@example.invalid"],
            check=True,
        )
        subprocess.run(["git", "-C", str(project), "add", "README.md", "data.json"], check=True)
        subprocess.run(["git", "-C", str(project), "commit", "-qm", "initial"], check=True)
        results = (
            inspect_adapter(project, "file", "README.md"),
            inspect_adapter(project, "json", "data.json"),
            inspect_adapter(project, "markdown", "."),
            inspect_adapter(project, "git"),
        )
        capsule = self.root / "flow.ocx"
        exported = export_capsule(project, capsule)
        verified = verify_capsule(capsule)
        restored = self.root / "restored"
        imported = import_capsule(restored, capsule)

        self.assertEqual([item["adapter"] for item in results], ["file", "json", "markdown", "git"])
        self.assertTrue(all(item["writes"] == [] for item in results))
        self.assertEqual(exported["capsule_digest"], verified["capsule_digest"])
        self.assertEqual(imported["status"], "IMPORTED")
        self.assertEqual(flow_status(restored).current_assignment, "TASK-1")

        with zipfile.ZipFile(capsule, "a") as archive:
            archive.writestr("continuity/unexpected.txt", b"tamper")
        with self.assertRaises(ContinuityError):
            verify_capsule(capsule)

    def test_optional_git_replica_is_previewed_non_force_and_automatic(self) -> None:
        project, roadmap_path = self._project()
        start_flow(project, roadmap_path, "AUTO PILOT")
        (project / "evidence.txt").write_text("green\n", encoding="utf-8")
        bare = self.root / "private.git"
        mirror = self.root / "mirror"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        subprocess.run(["git", "init", "-q", str(mirror)], check=True)
        subprocess.run(["git", "-C", str(mirror), "config", "user.name", "Example"], check=True)
        subprocess.run(
            ["git", "-C", str(mirror), "config", "user.email", "example@example.invalid"],
            check=True,
        )
        (mirror / "README.md").write_text("# Private replica\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(mirror), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(mirror), "commit", "-qm", "initial"], check=True)
        subprocess.run(["git", "-C", str(mirror), "branch", "-M", "main"], check=True)
        subprocess.run(["git", "-C", str(mirror), "remote", "add", "origin", str(bare)], check=True)
        subprocess.run(["git", "-C", str(mirror), "push", "-qu", "origin", "main"], check=True)
        preview = build_sync_preview(
            project,
            mirror,
            remote="origin",
            branch="main",
            private_repository_confirmed=False,
        )
        applied = apply_sync(
            project,
            mirror,
            remote="origin",
            branch="main",
            private_repository_confirmed=False,
            expected_preview_digest=preview["preview_digest"],
        )
        configure_sync(
            project,
            mirror,
            remote="origin",
            branch="main",
            private_repository_confirmed=False,
        )
        second = advance_flow(project, outcome="PASS", evidence_paths=["evidence.txt"])
        status = sync_status(project)

        self.assertEqual(preview["writes"], [])
        self.assertEqual(applied.status, "SYNCED")
        self.assertEqual(applied.commit, applied.remote_head)
        self.assertEqual(second.current_assignment, "TASK-2")
        self.assertTrue(status["configured"])
        self.assertEqual(status["last_receipt"]["status"], "SYNCED")

    def test_automatic_sync_failure_is_latched_until_explicit_rearm(self) -> None:
        project, roadmap_path = self._project()
        start_flow(project, roadmap_path, "AUTO PILOT")
        _, mirror = self._private_replica("latched")
        configure_sync(
            project,
            mirror,
            remote="origin",
            branch="main",
            private_repository_confirmed=False,
        )
        (mirror / "README.md").write_text("dirty\n", encoding="utf-8")
        first = project / "first.txt"
        first.write_text("green one\n", encoding="utf-8")
        result = advance_flow(project, outcome="PASS", evidence_paths=[first.name])
        error_path = project / ".opencntx" / "continuity" / "sync" / "last-error.json"
        first_error = error_path.read_bytes()
        first_mtime = error_path.stat().st_mtime_ns
        self.assertEqual(result.current_assignment, "TASK-2")
        self.assertEqual(sync_status(project)["last_error"]["retry"], "NOT_AUTOMATIC")

        second = project / "second.txt"
        second.write_text("green two\n", encoding="utf-8")
        result = advance_flow(project, outcome="PASS", evidence_paths=[second.name])
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(error_path.read_bytes(), first_error)
        self.assertEqual(error_path.stat().st_mtime_ns, first_mtime)

        subprocess.run(["git", "-C", str(mirror), "restore", "--", "README.md"], check=True)
        preview = build_sync_preview(
            project,
            mirror,
            remote="origin",
            branch="main",
            private_repository_confirmed=False,
        )
        apply_sync(
            project,
            mirror,
            remote="origin",
            branch="main",
            private_repository_confirmed=False,
            expected_preview_digest=preview["preview_digest"],
        )
        self.assertIsNone(sync_status(project)["last_error"])

        error_path.write_bytes(first_error)
        configure_sync(
            project,
            mirror,
            remote="origin",
            branch="main",
            private_repository_confirmed=False,
        )
        self.assertIsNone(sync_status(project)["last_error"])

    def test_git_replica_blocks_structured_password_signals(self) -> None:
        project, roadmap_path = self._project()
        start_flow(project, roadmap_path, "AUTO PILOT")
        _, mirror = self._private_replica("secret-filter")
        store = project / ".opencntx" / "continuity"
        samples = {
            "information/password.json": '{"password": "correct-horse-battery-staple"}\n',
            "documentation/database.md": (
                "DATABASE_URL=postgres://app:correct-horse-battery-staple@"
                "db.example.invalid:5432/app\n"
            ),
            "information/environment.json": "DB_PASSWORD=correct-horse-battery-staple\n",
        }
        for relative, value in samples.items():
            with self.subTest(relative=relative):
                path = store / relative
                path.write_text(value, encoding="utf-8")
                with self.assertRaisesRegex(ContinuityError, "secret filter"):
                    build_sync_preview(
                        project,
                        mirror,
                        remote="origin",
                        branch="main",
                        private_repository_confirmed=False,
                    )
                path.unlink()

    def test_cli_and_contract_catalog_are_machine_readable(self) -> None:
        project, roadmap_path = self._project()
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(SOURCE)
        started = subprocess.run(
            [
                sys.executable,
                "-m",
                "opencntx",
                "flow",
                "start",
                str(roadmap_path),
                "--approval",
                "AUTO PILOT",
                "--json",
            ],
            cwd=project,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        status = subprocess.run(
            [sys.executable, "-m", "opencntx", "flow", "status", "--json"],
            cwd=project,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        catalog = json.loads(
            (SOURCE / "opencntx/schemas/continuity-contract-v1.json").read_text(encoding="utf-8")
        )

        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(started.stdout)["current_assignment"], "TASK-1")
        self.assertTrue(json.loads(status.stdout)["minimum_action"].endswith("TASK-1.md"))
        self.assertEqual(catalog["release"], "1.1.1")
        self.assertEqual(catalog["stable_baseline"], "1.0.0")
        self.assertEqual(len(catalog["commands"]), 14)

    def test_public_product_bytes_are_name_neutral(self) -> None:
        public_files = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
        for directory in (SOURCE / "opencntx", ROOT / "examples"):
            public_files.extend(path for path in directory.rglob("*") if path.is_file())
        forbidden = ("skyrim", "nanopc", "onedrive", "c:\\users\\", "d:\\codex\\")
        for path in public_files:
            if path.suffix.lower() in {".pyc", ".png", ".jpg", ".ico"}:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for marker in forbidden:
                self.assertNotIn(marker, text, path.relative_to(ROOT))


if __name__ == "__main__":
    unittest.main()
