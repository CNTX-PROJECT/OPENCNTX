from __future__ import annotations

import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from opencntx import fixture_files as f
from opencntx.continuity import (
    _digest,
    _value_digest,
    advance_flow,
    execution_state_capsule,
    record_execution_checkpoint,
    start_flow,
)
from opencntx.goal_binding import HostSource
from opencntx.human_interface import build_intent_contract
from opencntx.reference_host import MAX_REQUEST, ReferenceHost, serve_reference_host
from opencntx.task_assessment import TaskFacts


def host(
    root: Path,
    *,
    source_role: str = "OWNER",
    fixture: Path | None = None,
    assessment_facts: TaskFacts | None = None,
    progress_node_id: str | None = None,
) -> ReferenceHost:
    intent = build_intent_contract(
        human_intent="Replace exactly parent files, preserve all children and backups.",
        language="en",
        goal="Parent fixture result",
        scope=["parent"],
        exclusions=["parent/child"],
        constraints=["No clobber"],
        authority_state="APPROVED",
        risks=["Wrong target"],
        definition_of_done=["Parent replaced, child preserved"],
        next_internal_action="Execute bound fixture",
    )
    return ReferenceHost(
        project_root=root,
        fixture_root=fixture or root / "fixture",
        intent=intent,
        source=HostSource(
            source_role, "fixture-host-message", _digest(intent["human_intent"].encode())
        ),
        request_id="FIXTURE-REQUEST",
        revision=1,
        assessment_facts=assessment_facts,
        progress_node_id=progress_node_id,
    )


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): _digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()
    }


@unittest.skipUnless(sys.platform == "win32", "Windows reference write capability only")
class ReferenceHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        definition = {
            "format": "opencntx-continuity-roadmap",
            "format_version": 1,
            "project_id": "FIXTURE",
            "roadmap_id": "R15-FIXTURE",
            "title": "Fixture",
            "assignments": [
                {
                    "id": "TASK-1",
                    "title": "Fixture action",
                    "detail": "Fixture only",
                    "depends_on": [],
                    "touches": [],
                    "conflict": "NO_CONFLICT",
                    "migration": "",
                    "definition_of_done": ["Exact result"],
                }
            ],
        }
        (self.root / "roadmap.json").write_text(json.dumps(definition), encoding="utf-8")
        start_flow(self.root, self.root / "roadmap.json", "AUTO PILOT")
        self.fixture = self.root / "fixture"
        for name in f.WATCHED:
            path = self.fixture / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                ("child" if "child/" in name else "parent") + Path(name).name, encoding="utf-8"
            )
        for folder in ("staging", "retained"):
            (self.fixture / folder).mkdir()
        self.host = host(self.root)
        self.request = self.host.expected.payload()
        self.before = snapshot(self.fixture)

    def denied_unchanged(self, message: object) -> dict:
        before = snapshot(self.fixture)
        result = self.host.dispatch(message)
        self.assertEqual(result["decision"], "DENY", result)
        self.assertEqual(snapshot(self.fixture), before)
        return result

    def test_correct_shared_binding_executes_only_exact_parent(self) -> None:
        reply = self.host.dispatch(self.request)
        self.assertEqual(reply["decision"], "ALLOW", reply)
        self.assertEqual(reply["binding_digest"], self.request["binding_digest"])
        for name in f.WATCHED[3:]:
            self.assertEqual(snapshot(self.fixture)[str(Path(name))], self.before[str(Path(name))])
        for name, data in zip(f.NAMES, self.host.physical.replacements):
            self.assertEqual((self.fixture / name).read_bytes(), data)
        self.denied_unchanged(self.request)

    def test_missing_parent_does_not_substitute_child(self) -> None:
        target = self.fixture / f.NAMES[0]
        target.rename(target.with_suffix(".retained.txt"))
        self.denied_unchanged(self.request)

    def test_complex_task_cannot_write_without_hierarchy(self) -> None:
        for facts in (
            TaskFacts(kind="MULTI_PHASE", dependent_phases=2),
            TaskFacts(kind="MULTI_STREAM", independent_large_streams=2),
        ):
            with self.subTest(facts=facts):
                self.host = host(self.root, assessment_facts=facts)
                reply = self.denied_unchanged(self.host.expected.payload())
                self.assertIn("planning", reply["reason"].lower())

    def test_uncertainty_cannot_masquerade_write_as_source_probe(self) -> None:
        self.host = host(self.root, assessment_facts=TaskFacts(uncertainty="NEEDS_PROBE"))
        reply = self.denied_unchanged(self.host.expected.payload())
        self.assertIn("reconnaissance", reply["reason"].lower())

    def test_client_cannot_rebind_or_rehash_child_target(self) -> None:
        self.request["action"]["targets"][0] = "parent/child/00.txt"
        self.request["binding_digest"] = _value_digest(
            {k: v for k, v in self.request.items() if k != "binding_digest"}
        )
        self.denied_unchanged(self.request)
        self.denied_unchanged({"bind": self.request})
        self.denied_unchanged({"shell": "unbounded command"})

    def test_recursive_or_stale_revision_refused(self) -> None:
        for section, field, value in (("action", "recursive", True), ("request", "revision", 2)):
            request = self.host.expected.payload()
            request[section][field] = value
            self.denied_unchanged(request)

    def test_new_user_bytes_refused(self) -> None:
        target = self.fixture / f.NAMES[0]
        target.write_bytes(b"new OWNER bytes")
        reply = self.denied_unchanged(self.request)
        self.assertIn("target_identity_or_content_drift", reply["reason"])

    def test_same_bytes_new_identity_refused(self) -> None:
        target = self.fixture / f.NAMES[0]
        original = target.read_bytes()
        target.rename(target.with_suffix(".retained.txt"))
        target.write_bytes(original)
        reply = self.denied_unchanged(self.request)
        self.assertIn("target_identity_or_content_drift", reply["reason"])

    def test_preexisting_hardlink_refused(self) -> None:
        os.link(self.fixture / f.NAMES[0], self.fixture / "prior-alias.txt")
        reply = self.denied_unchanged(self.request)
        self.assertIn("hardlink_or_oversize", reply["reason"])

    def test_directory_junction_refused(self) -> None:
        (self.fixture / "parent").rename(self.fixture / "retained-parent")
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", "parent", "retained-parent"],
            cwd=self.fixture,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = self.denied_unchanged(self.request)
        self.assertIn("reparse_point", reply["reason"])

    def test_protected_child_or_backup_drift_refused(self) -> None:
        for name in ("parent/child/00.txt", "backup/parent/00.txt"):
            with self.subTest(name=name):
                selected = host(self.root)
                original = (self.fixture / name).read_bytes()
                (self.fixture / name).write_bytes(b"new protected bytes")
                before = snapshot(self.fixture)
                reply = selected.dispatch(selected.expected.payload())
                self.assertEqual(reply["decision"], "DENY", reply)
                self.assertEqual(snapshot(self.fixture), before)
                (self.fixture / name).write_bytes(original)

    def test_existing_native_writer_lock_is_used_during_physical_action(self) -> None:
        original = f.Handle.replace
        capsule = execution_state_capsule(self.root)
        (self.root / "proof.txt").write_text("Competing fixture checkpoint", encoding="utf-8")
        checked = []

        def compete(handle: f.Handle, data: bytes) -> None:
            if not checked:
                code = (
                    "import sys; from pathlib import Path; "
                    "from opencntx.continuity import record_execution_checkpoint; "
                    "record_execution_checkpoint(Path(sys.argv[1]), checkpoint_id='RACE', "
                    "current_internal_task='RACE', next_internal_action='Fixture race', "
                    "evidence_paths=['proof.txt'], expected_state_digest=sys.argv[2])"
                )
                result = subprocess.run(
                    [sys.executable, "-B", "-c", code, str(self.root), capsule["state_digest"]],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Another continuity writer is active", result.stderr)
                checked.append(True)
            original(handle, data)

        with patch.object(f.Handle, "replace", compete):
            reply = self.host.dispatch(self.request)
        self.assertEqual(reply["decision"], "ALLOW", reply)
        self.assertEqual(checked, [True])
        self.assertEqual(execution_state_capsule(self.root), capsule)

    def test_native_state_change_refused(self) -> None:
        capsule = execution_state_capsule(self.root)
        (self.root / "proof.txt").write_text("New checkpoint", encoding="utf-8")
        record_execution_checkpoint(
            self.root,
            checkpoint_id="CHECK-1",
            current_internal_task="NEXT",
            next_internal_action="Next fixture step",
            evidence_paths=["proof.txt"],
            expected_state_digest=capsule["state_digest"],
        )
        self.denied_unchanged(self.request)

    def test_recovery_uses_same_native_continuation_decision(self) -> None:
        (self.root / "failure.txt").write_text("Synthetic failed fixture attempt", encoding="utf-8")
        advance_flow(
            self.root,
            outcome="FAIL",
            evidence_paths=["failure.txt"],
            reason="Injected fixture failure",
        )
        self.denied_unchanged(self.request)
        selected = host(self.root)
        self.assertEqual(
            selected.expected.payload()["execution_capsule_v1"]["assignment_status"],
            "RECOVERY_REQUIRED",
        )
        self.assertEqual(selected.dispatch(selected.expected.payload())["decision"], "ALLOW")

    def test_bounded_stream_refuses_duplicates_and_oversize(self) -> None:
        for raw, expected_code in ((b'{"a":1,"a":2}\n', 0), (b"x" * (MAX_REQUEST + 1), 2)):
            output = io.StringIO()
            self.assertEqual(
                serve_reference_host(self.host, io.BytesIO(raw), output), expected_code
            )
            self.assertEqual(json.loads(output.getvalue())["decision"], "DENY")
            self.assertEqual(snapshot(self.fixture), self.before)

    def test_case_equivalent_supervisor_path_is_supported(self) -> None:
        selected = host(self.root, fixture=Path(str(self.fixture).upper()))
        self.assertEqual(selected.dispatch(selected.expected.payload())["decision"], "ALLOW")

    def test_outside_and_prefix_collision_refused(self) -> None:
        with self.assertRaises(f.Refused):
            f.bind(self.root.with_name(self.root.name + "-other"), allowed_root=self.root)
        with self.assertRaises(f.Refused):
            f.bind(self.root / ".." / "outside", allowed_root=self.root)

    def test_unknown_and_ai_source_do_not_authorize_writes(self) -> None:
        for role in ("UNKNOWN", "AI_PROPOSAL"):
            selected = host(self.root, source_role=role)
            self.assertEqual(selected.dispatch(selected.expected.payload())["decision"], "DENY")
            self.assertEqual(snapshot(self.fixture), self.before)

    def test_competing_alias_keeps_original_bytes(self) -> None:
        original = f.Handle.replace
        alias = self.fixture / "alias.txt"

        def compete(handle: f.Handle, data: bytes) -> None:
            if not alias.exists():
                os.link(self.fixture / f.NAMES[0], alias)
            original(handle, data)

        with patch.object(f.Handle, "replace", compete):
            reply = self.host.dispatch(self.request)
        self.assertEqual(reply["decision"], "ALLOW", reply)
        self.assertEqual(alias.read_bytes(), self.host.physical.originals[0])

    def test_early_staging_alias_refuses_before_any_data_write(self) -> None:
        original = f.Handle.pending
        alias = self.fixture / "early-staging-alias.txt"

        def compete(handle: f.Handle, value: bool) -> None:
            if value and not alias.exists():
                os.link(handle.path, alias)
            original(handle, value)

        with patch.object(f.Handle, "pending", compete):
            reply = self.host.dispatch(self.request)
        self.assertEqual(reply["decision"], "DENY", reply)
        self.assertEqual(alias.read_bytes(), b"")
        after = snapshot(self.fixture)
        self.assertTrue(all(after[name] == digest for name, digest in self.before.items()))

    def test_pending_staging_blocks_alias_write_and_parent_rename(self) -> None:
        original = f.Handle.replace
        checks = []

        def compete(handle: f.Handle, data: bytes) -> None:
            with self.assertRaises(OSError):
                os.link(handle.path, self.fixture / ("late-alias-" + handle.path.name))
            with self.assertRaises(OSError):
                (self.fixture / f.NAMES[0]).write_bytes(b"competing bytes")
            with self.assertRaises(OSError):
                (self.fixture / "parent").rename(self.fixture / "replacement-parent")
            checks.append(True)
            original(handle, data)

        with patch.object(f.Handle, "replace", compete):
            reply = self.host.dispatch(self.request)
        self.assertEqual(reply["decision"], "ALLOW", reply)
        self.assertEqual(len(checks), 3)

    def test_sealed_staging_alias_has_no_later_byte_mutation(self) -> None:
        original = f.Handle.seal
        aliases = []

        def compete(handle: f.Handle) -> None:
            original(handle)
            alias = self.fixture / ("sealed-alias-" + handle.path.name)
            os.link(handle.path, alias)
            aliases.append(alias)
            with self.assertRaises(f.Refused):
                handle.replace(b"late overwrite")

        with patch.object(f.Handle, "seal", compete):
            reply = self.host.dispatch(self.request)
        self.assertEqual(reply["decision"], "ALLOW", reply)
        self.assertEqual(
            [path.read_bytes() for path in aliases], list(self.host.physical.replacements)
        )

    def test_competing_destination_survives_failed_recovery(self) -> None:
        original = f.Handle.rename
        target = self.fixture / f.NAMES[0]

        def compete(handle: f.Handle, destination: Path) -> None:
            original(handle, destination)
            if destination == self.fixture / f.RETAINED[0]:
                target.write_bytes(b"new OWNER destination")

        with patch.object(f.Handle, "rename", compete):
            reply = self.host.dispatch(self.request)
        self.assertEqual(reply["execution"], "PARTIAL_RECOVERY_REQUIRED", reply)
        self.assertEqual(target.read_bytes(), b"new OWNER destination")
        self.assertEqual(
            (self.fixture / f.RETAINED[0]).read_bytes(), self.host.physical.originals[0]
        )
        for name in f.WATCHED[3:]:
            self.assertEqual(snapshot(self.fixture)[str(Path(name))], self.before[str(Path(name))])

    def test_completed_rename_error_restores_actual_handle_positions(self) -> None:
        for method, total in (("replace", 3), ("seal", 3), ("rename", 6)):
            for ordinal in range(1, total + 1):
                with self.subTest(method=method, ordinal=ordinal):
                    fixture = ReferenceHostTests()
                    fixture.setUp()
                    self.addCleanup(fixture.doCleanups)
                    original = getattr(f.Handle, method)
                    calls = 0

                    def lost_reply(handle: f.Handle, *args, _original=original, _ordinal=ordinal) -> None:
                        nonlocal calls
                        old_path = handle.path
                        _original(handle, *args)
                        calls += 1
                        if calls == _ordinal:
                            # Even the handle wrapper's cached path may be stale.
                            handle.path = old_path
                            raise f.Refused("injected error after completed operation")

                    with patch.object(f.Handle, method, lost_reply):
                        reply = fixture.host.dispatch(fixture.request)
                    self.assertEqual(reply["decision"], "DENY")
                    self.assertEqual(reply["execution"], "NOT_PERFORMED_OR_ROLLED_BACK", reply)
                    for name in f.WATCHED:
                        self.assertTrue((fixture.fixture / name).is_file(), name)
                        self.assertEqual(f.digest((fixture.fixture / name).read_bytes()), fixture.before[str(Path(name))])

    def test_real_messages_only_subprocess(self) -> None:
        evidence = []
        with subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-m",
                "tests.test_reference_host",
                "--fixture-server",
                str(self.root),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as process:
            assert process.stdin and process.stdout
            lines: queue.Queue[str] = queue.Queue()

            def reader() -> None:
                assert process.stdout
                for line in process.stdout:
                    lines.put(line)

            threading.Thread(target=reader, daemon=True).start()

            def read() -> dict:
                try:
                    return json.loads(lines.get(timeout=30))
                except queue.Empty:
                    process.kill()
                    raise AssertionError("Fixture server timeout")

            ready = read()
            valid = ready["request"]
            for request, expected in (
                ({"bind": valid}, "DENY"),
                ({"shell": "anything"}, "DENY"),
                (valid, "ALLOW"),
                (valid, "DENY"),
            ):
                before = snapshot(self.fixture)
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
                reply = read()
                evidence.append(
                    {
                        "request": request,
                        "reply": reply,
                        "before": before,
                        "after": snapshot(self.fixture),
                    }
                )
                self.assertEqual(reply["decision"], expected, reply)
                if expected == "DENY":
                    self.assertEqual(snapshot(self.fixture), before)
            process.stdin.close()
            self.assertEqual(process.wait(timeout=30), 0)
        evidence_root = os.environ.get("OPENCNTX_TEST_EVIDENCE_ROOT")
        if evidence_root:
            (Path(evidence_root) / "reference-host-transport.json").write_text(
                json.dumps(evidence, indent=2), encoding="utf-8"
            )


class UnsupportedPlatformTests(unittest.TestCase):
    def test_unsupported_platform_refuses_before_open(self) -> None:
        with patch.object(f.sys, "platform", "unsupported"), self.assertRaises(f.Refused):
            f.Handle(Path("never-opened.txt"), create=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--fixture-server":
        selected = host(Path(sys.argv[2]))
        print(json.dumps({"request": selected.expected.payload()}), flush=True)
        raise SystemExit(serve_reference_host(selected, sys.stdin.buffer, sys.stdout))
    else:
        unittest.main()
