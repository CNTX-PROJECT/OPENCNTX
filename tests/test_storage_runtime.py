from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from opencntx.runtime_contracts import canonical_digest, validate_runtime_record
from opencntx.storage_runtime import (
    ASSIGNMENT_34_PROPOSAL_SHA256,
    CASE_RESULT_CODES,
    SCENARIO_COUNT,
    SCENARIO_TABLE_SHA256,
    GitTransportError,
    LocalCanonicalBackend,
    StorageBackend,
    StorageRuntimeError,
    SyncCandidate,
    VisibilityProof,
    apply_local_media_plan,
    apply_local_record_plan,
    apply_private_git_sync,
    build_local_media_plan,
    build_local_record_plan,
    build_sync_preview,
    classify_storage_item,
    load_storage_sync_corpus,
    recover_storage_transaction,
    run_storage_sync_corpus,
    stable_storage_object_id,
    validate_storage_sync_corpus,
)
from tests.test_runtime_contracts import ZERO, samples

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "r9" / "assignment-34-storage-sync-scenarios-v1.json"
SNAPSHOT = ROOT / "tests" / "fixtures" / "r9" / "assignment-34-opencntx-public-snapshot-v1.json"
HOOK_DIGEST = "a" * 64
OWNER_DIGEST = "b" * 64

ASSIGNMENT_29 = ROOT / "tests" / "fixtures" / "r9" / "assignment-29-scenarios-v1.json"
ASSIGNMENT_31 = ROOT / "tests" / "fixtures" / "r9" / "assignment-31-intake-scenarios-v1.json"
ASSIGNMENT_31_SNAPSHOT = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-31-opencntx-public-snapshot-v1.json"
)
ASSIGNMENT_32 = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-32-roadmap-runtime-scenarios-v1.json"
)
ASSIGNMENT_32_SNAPSHOT = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-32-opencntx-public-snapshot-v1.json"
)
ASSIGNMENT_33 = ROOT / "tests" / "fixtures" / "r9" / "assignment-33-runtime-hook-scenarios-v1.json"
ASSIGNMENT_33_SNAPSHOT = (
    ROOT / "tests" / "fixtures" / "r9" / "assignment-33-opencntx-public-snapshot-v1.json"
)


def _git_blob_id(path: Path) -> str:
    return subprocess.run(
        ["git", "hash-object", str(path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _policy(*, sync: bool = False) -> dict:
    policy = samples()["opencntx-storage-policy"]
    if sync:
        policy.update(
            {
                "default_storage": "PRIVATE_GIT_SYNC",
                "private_branch": "mirror",
                "private_git_sync_enabled": True,
                "private_remote": "origin",
                "sync_types": ["JSON"],
            }
        )
    return policy


def _record(*, revision: int = 1) -> dict:
    record = samples()["opencntx-evidence"]
    record["revision"] = revision
    return record


def _record_plan(*, record: dict | None = None, expected: str = ZERO):
    return build_local_record_plan(
        record=record or _record(),
        policy=_policy(),
        logical_key="records/evidence/current",
        expected_previous_digest=expected,
        guard_status="ALLOW_EXACT_ACTION",
        hook_trace_digest=HOOK_DIGEST,
    )


def _run(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class LocalGitTransport:
    def __init__(self, root: Path, *, lose_push_response: bool = False) -> None:
        self.root = root
        self.lose_push_response = lose_push_response
        self.candidates: tuple[SyncCandidate, ...] = ()
        self.previous: dict[str, bytes | None] = {}

    def remote_url(self, remote_alias: str) -> str:
        return _run(self.root, "git", "remote", "get-url", remote_alias).stdout.strip()

    def remote_head(self, remote_alias: str, branch: str) -> str | None:
        result = _run(
            self.root,
            "git",
            "ls-remote",
            "--heads",
            remote_alias,
            f"refs/heads/{branch}",
        ).stdout.strip()
        return result.split()[0] if result else None

    def is_clean(self) -> bool:
        return not _run(self.root, "git", "status", "--porcelain=v1").stdout.strip()

    def materialize_and_stage(self, candidates) -> None:
        self.candidates = tuple(candidates)
        for candidate in self.candidates:
            target = self.root / candidate.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            self.previous[candidate.relative_path] = (
                target.read_bytes() if target.exists() else None
            )
            target.write_bytes(candidate.content)
        _run(self.root, "git", "add", "--", *(item.relative_path for item in self.candidates))

    def staged_paths(self) -> tuple[str, ...]:
        output = _run(
            self.root, "git", "diff", "--cached", "--name-only", "--diff-filter=ACMRT"
        ).stdout
        return tuple(sorted(line for line in output.splitlines() if line))

    def commit(self, message: str) -> tuple[str, str]:
        _run(self.root, "git", "commit", "-m", message)
        commit = _run(self.root, "git", "rev-parse", "HEAD").stdout.strip()
        tree = _run(self.root, "git", "show", "-s", "--format=%T", "HEAD").stdout.strip()
        return commit, tree

    def push_non_force(self, commit: str, remote_alias: str, branch: str) -> None:
        _run(self.root, "git", "push", remote_alias, f"{commit}:refs/heads/{branch}")
        if self.lose_push_response:
            raise GitTransportError("simulated lost response", outcome_unknown=True)

    def readback(self, remote_alias: str, branch: str, candidate_paths) -> tuple[str, str, str]:
        head = self.remote_head(remote_alias, branch)
        assert head is not None
        tree = _run(self.root, "git", "show", "-s", "--format=%T", head).stdout.strip()
        by_path = {item.relative_path: item for item in self.candidates}
        exact = tuple(by_path[path] for path in candidate_paths)
        digest = canonical_digest(
            [
                {
                    "byte_count": len(item.content),
                    "content_sha256": item.content_sha256,
                    "object_id": item.object_id,
                    "path": item.relative_path,
                }
                for item in exact
            ]
        )
        return head, tree, digest

    def rollback_materialization(self, candidate_paths) -> None:
        for relative in candidate_paths:
            target = self.root / relative
            previous = self.previous.get(relative)
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(previous)
        _run(self.root, "git", "reset", "--quiet", "HEAD", "--", *candidate_paths, check=False)


def _git_fixture(root: Path, *, lose_push_response: bool = False) -> LocalGitTransport:
    origin = root / "origin.git"
    seed = root / "seed"
    mirror = root / "mirror"
    origin.mkdir()
    seed.mkdir()
    _run(origin, "git", "init", "--bare")
    _run(seed, "git", "init", "-b", "mirror")
    _run(seed, "git", "config", "user.name", "OPENCNTX Test")
    _run(seed, "git", "config", "user.email", "opencntx@example.invalid")
    (seed / "README.md").write_text("private mirror test\n", encoding="utf-8")
    _run(seed, "git", "add", "README.md")
    _run(seed, "git", "commit", "-m", "seed")
    _run(seed, "git", "remote", "add", "origin", origin.as_posix())
    _run(seed, "git", "push", "-u", "origin", "mirror")
    _run(root, "git", "clone", "--branch", "mirror", origin.as_posix(), mirror.as_posix())
    _run(mirror, "git", "config", "user.name", "OPENCNTX Test")
    _run(mirror, "git", "config", "user.email", "opencntx@example.invalid")
    return LocalGitTransport(mirror, lose_push_response=lose_push_response)


def _preview(transport: LocalGitTransport):
    remote_url = transport.remote_url("origin")
    base = _run(transport.root, "git", "rev-parse", "HEAD").stdout.strip()
    content = b'{"safe":true}\n'
    candidate = SyncCandidate(
        object_id=stable_storage_object_id("PROJECT_R9", "RECORD", "records/safe"),
        relative_path="records/safe.json",
        content=content,
        content_sha256=hashlib.sha256(content).hexdigest(),
    )
    proof = VisibilityProof(
        repository_id="PRIVATE_REPOSITORY_1",
        visibility="PRIVATE",
        freshness="CURRENT",
        remote_url_digest=hashlib.sha256(remote_url.encode()).hexdigest(),
        owner_instruction_digest=OWNER_DIGEST,
        actor_id="ACTOR_ARCHITECT",
    )
    return build_sync_preview(
        project_id="PROJECT_R9",
        actor_id="ACTOR_ARCHITECT",
        policy=_policy(sync=True),
        owner_instruction_digest=OWNER_DIGEST,
        visibility_proof=proof,
        remote_alias="origin",
        remote_url=remote_url,
        branch="mirror",
        local_base_commit=base,
        remote_base_commit=base,
        candidates=[candidate],
        repository_bytes=100,
        provider_limit_bytes=2 * 1024**3,
        mirror_clean=True,
        guard_status="ALLOW_EXACT_ACTION",
        hook_trace_digest=HOOK_DIGEST,
    )


class StorageRuntimeTests(unittest.TestCase):
    def test_stable_ids_are_backend_content_and_revision_neutral(self) -> None:
        first = stable_storage_object_id("PROJECT_R9", "EVIDENCE", "records/current")
        second = stable_storage_object_id("PROJECT_R9", "EVIDENCE", "records/current")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^OBJECT_[0-9A-F]{64}$")
        self.assertNotEqual(
            first, stable_storage_object_id("PROJECT_OTHER", "EVIDENCE", "records/current")
        )
        self.assertNotEqual(
            first, stable_storage_object_id("PROJECT_R9", "MEDIA", "records/current")
        )
        self.assertNotEqual(
            first, stable_storage_object_id("PROJECT_R9", "EVIDENCE", "records/other")
        )

    def test_stable_ids_reject_empty_non_nfc_absolute_traversal_and_windows_keys(self) -> None:
        invalid = ("", "e\u0301", "/absolute", "../outside", "C:/outside", "a\\b")
        for key in invalid:
            with self.subTest(key=key), self.assertRaises(StorageRuntimeError):
                stable_storage_object_id("PROJECT_R9", "EVIDENCE", key)

    def test_record_plan_is_write_free_canonical_and_bound(self) -> None:
        plan = _record_plan()
        self.assertEqual(plan.expected_previous_digest, ZERO)
        self.assertTrue(plan.content.endswith(b"\n"))
        self.assertEqual(hashlib.sha256(plan.content).hexdigest(), plan.content_sha256)
        self.assertIn(plan.object_id, plan.object_path)
        self.assertRegex(plan.plan_digest, r"^[0-9a-f]{64}$")

    def test_record_apply_is_atomic_readback_verified_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _record_plan()
            first = apply_local_record_plan(root, plan)
            second = apply_local_record_plan(root, plan)
            self.assertEqual(first.status, "LOCAL_RECORD_STORED")
            self.assertEqual(second.status, "ALREADY_PRESENT_SAME_BYTES")
            self.assertTrue((root / plan.object_path).is_file())
            self.assertTrue((root / plan.head_path).is_file())
            self.assertTrue(first.receipt_path and (root / first.receipt_path).is_file())
            self.assertNotIn("captured_at", (root / first.receipt_path).read_text(encoding="utf-8"))

    def test_record_revision_requires_exact_previous_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = apply_local_record_plan(root, _record_plan())
            second_plan = _record_plan(record=_record(revision=2), expected=first.head_digest)
            second = apply_local_record_plan(root, second_plan)
            self.assertEqual(second.status, "LOCAL_RECORD_STORED")
            stale = _record_plan(record=_record(revision=3), expected=first.head_digest)
            with self.assertRaises(StorageRuntimeError) as caught:
                apply_local_record_plan(root, stale)
            self.assertEqual(caught.exception.code, "storage_state_changed")

    def test_record_plan_rejects_schema_policy_guard_and_digest_drift(self) -> None:
        invalid_record = _record()
        invalid_record["unknown"] = True
        cases = (
            {"record": invalid_record},
            {"policy": _policy() | {"project_id": "PROJECT_OTHER"}},
            {"guard_status": "READ_ONLY_ONLY"},
            {"expected_previous_digest": "bad"},
            {"hook_trace_digest": "bad"},
        )
        base = {
            "record": _record(),
            "policy": _policy(),
            "logical_key": "records/evidence/current",
            "expected_previous_digest": ZERO,
            "guard_status": "ALLOW_EXACT_ACTION",
            "hook_trace_digest": HOOK_DIGEST,
        }
        for override in cases:
            with self.subTest(override=tuple(override)), self.assertRaises(StorageRuntimeError):
                build_local_record_plan(**(base | override))

    def test_store_rejects_symlinked_managed_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            try:
                (root / "objects").symlink_to(Path(outside), target_is_directory=True)
            except OSError:
                self.skipTest("Symlink creation is unavailable")
            with self.assertRaises(StorageRuntimeError):
                apply_local_record_plan(root, _record_plan())

    def test_media_pointer_is_safe_local_only_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = build_local_media_plan(
                project_id="PROJECT_R9",
                logical_key="media/private-image",
                filename="private family photo.png",
                mime_type="image/png",
                privacy_class="SENSITIVE",
                license_class="OWNER_CONTROLLED",
                availability="AVAILABLE",
                freshness="CURRENT",
                content=b"\x89PNG\r\n\x1a\nprivate-bytes",
                policy=_policy(),
                guard_status="ALLOW_EXACT_ACTION",
                hook_trace_digest=HOOK_DIGEST,
            )
            self.assertEqual(plan.filename, "redacted.png")
            self.assertNotIn(directory, json.dumps(plan.pointer))
            self.assertTrue(str(plan.pointer["store_locator"]).startswith("local-store://"))
            first = apply_local_media_plan(root, plan)
            second = apply_local_media_plan(root, plan)
            self.assertEqual(first.status, "LOCAL_MEDIA_STORED")
            self.assertEqual(second.status, "ALREADY_PRESENT_SAME_BYTES")

    def test_media_plan_rejects_unknown_privacy_or_license(self) -> None:
        base = {
            "project_id": "PROJECT_R9",
            "logical_key": "media/file",
            "filename": "file.bin",
            "mime_type": "application/octet-stream",
            "privacy_class": "PRIVATE",
            "license_class": "OWNER_CONTROLLED",
            "availability": "AVAILABLE",
            "freshness": "CURRENT",
            "content": b"bytes",
            "policy": _policy(),
            "guard_status": "ALLOW_EXACT_ACTION",
            "hook_trace_digest": HOOK_DIGEST,
        }
        for override in ({"privacy_class": "UNKNOWN"}, {"license_class": "UNKNOWN"}):
            with self.assertRaises(StorageRuntimeError):
                build_local_media_plan(**(base | override))

    def test_classification_blocks_secrets_warning_types_privacy_and_openspec(self) -> None:
        high = classify_storage_item(
            project_id="PROJECT_R9",
            path="records/key.json",
            content=b"-----BEGIN PRIVATE KEY-----\nsecret\n",
            policy=_policy(sync=True),
            privacy_class="PRIVATE",
            license_class="OWNER_CONTROLLED",
            mime_type="application/json",
            for_sync=True,
        )
        warning = classify_storage_item(
            project_id="PROJECT_R9",
            path="records/config.json",
            content=b"password=abcdefghijk",
            policy=_policy(sync=True),
            privacy_class="PRIVATE",
            license_class="OWNER_CONTROLLED",
            mime_type="application/json",
            for_sync=True,
        )
        binary = classify_storage_item(
            project_id="PROJECT_R9",
            path="media/file.bin",
            content=b"\x00binary",
            policy=_policy(),
            privacy_class="PRIVATE",
            license_class="OWNER_CONTROLLED",
            mime_type="application/octet-stream",
            for_sync=False,
        )
        excluded = classify_storage_item(
            project_id="PROJECT_R9",
            path=".openspec-store/history.json",
            content=b"{}",
            policy=_policy(),
            privacy_class="PRIVATE",
            license_class="OWNER_CONTROLLED",
            mime_type="application/json",
            for_sync=False,
        )
        self.assertEqual(high.status, "EXCLUDED_SECRET")
        self.assertEqual(warning.status, "POLICY_BLOCKED")
        self.assertEqual(binary.status, "LOCAL_ONLY_MEDIA")
        self.assertEqual(excluded.status, "OPENSPEC_EXCLUDED")
        self.assertTrue(high.finding_ids)

    def test_safe_sync_classification_accepts_allowlisted_json(self) -> None:
        result = classify_storage_item(
            project_id="PROJECT_R9",
            path="records/safe.json",
            content=b'{"safe":true}\n',
            policy=_policy(sync=True),
            privacy_class="PRIVATE",
            license_class="OWNER_CONTROLLED",
            mime_type="application/json",
            for_sync=True,
        )
        self.assertEqual(result.status, "LOCAL_CANONICAL")
        self.assertFalse(result.finding_ids)

    def test_local_backend_conforms_to_backend_neutral_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = LocalCanonicalBackend(Path(directory))
            self.assertIsInstance(backend, StorageBackend)
            preview = backend.preview({"project_id": "PROJECT_R9"})
            self.assertEqual(preview["status"], "LOCAL_RECORD_PLAN_GREEN")
            result = backend.apply({"plan": _record_plan()})
            self.assertEqual(result["status"], "LOCAL_RECORD_STORED")

    def test_healthy_store_recovery_is_read_only_local_continuity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apply_local_record_plan(root, _record_plan())
            result = recover_storage_transaction(root)
            self.assertEqual(result["status"], "LOCAL_CONTINUITY")
            self.assertEqual(result["writes"], [])

    def test_sync_preview_is_deterministic_private_bound_and_write_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = _git_fixture(Path(directory))
            first = _preview(transport)
            second = _preview(transport)
            self.assertEqual(first.preview_digest, second.preview_digest)
            self.assertEqual(first.writes, ())
            self.assertEqual(first.file_count, 1)
            self.assertIn("PRIVATE_VISIBILITY_PROVEN", first.checks)
            self.assertTrue(transport.is_clean())

    def test_sync_preview_rejects_disabled_public_stale_dirty_drift_and_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = _git_fixture(Path(directory))
            good = _preview(transport)
            remote_url = transport.remote_url("origin")
            proof = VisibilityProof(
                repository_id="PRIVATE_REPOSITORY_1",
                visibility="PRIVATE",
                freshness="CURRENT",
                remote_url_digest=hashlib.sha256(remote_url.encode()).hexdigest(),
                owner_instruction_digest=OWNER_DIGEST,
                actor_id="ACTOR_ARCHITECT",
            )
            base = {
                "project_id": "PROJECT_R9",
                "actor_id": "ACTOR_ARCHITECT",
                "policy": _policy(sync=True),
                "owner_instruction_digest": OWNER_DIGEST,
                "visibility_proof": proof,
                "remote_alias": "origin",
                "remote_url": remote_url,
                "branch": "mirror",
                "local_base_commit": good.base_commit,
                "remote_base_commit": good.base_commit,
                "candidates": good.candidates,
                "repository_bytes": 100,
                "provider_limit_bytes": 2 * 1024**3,
                "mirror_clean": True,
                "guard_status": "ALLOW_EXACT_ACTION",
                "hook_trace_digest": HOOK_DIGEST,
            }
            mutations = (
                {"policy": _policy()},
                {
                    "visibility_proof": proof.__class__(
                        **(proof.__dict__ | {"visibility": "PUBLIC"})
                    )
                },
                {"visibility_proof": proof.__class__(**(proof.__dict__ | {"freshness": "STALE"}))},
                {"mirror_clean": False},
                {"remote_base_commit": "f" * 40},
                {"remote_url": "https://user:password@example.invalid/private.git"},
            )
            for mutation in mutations:
                with self.subTest(fields=tuple(mutation)), self.assertRaises(StorageRuntimeError):
                    build_sync_preview(**(base | mutation))

    def test_sync_preview_rejects_unsorted_duplicate_digest_and_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = _git_fixture(Path(directory))
            preview = _preview(transport)
            candidate = preview.candidates[0]
            duplicate = SyncCandidate(
                candidate.object_id,
                "records/second.json",
                candidate.content,
                candidate.content_sha256,
            )
            with self.assertRaises(StorageRuntimeError):
                _preview_with(transport, candidates=[duplicate, candidate])
            with self.assertRaises(StorageRuntimeError):
                _preview_with(transport, candidates=[candidate, duplicate])
            bad = SyncCandidate(
                candidate.object_id, candidate.relative_path, b"different", candidate.content_sha256
            )
            with self.assertRaises(StorageRuntimeError):
                _preview_with(transport, candidates=[bad])
            with self.assertRaises(StorageRuntimeError):
                _preview_with(transport, repository_bytes=1024**3)

    def test_private_git_sync_commits_pushes_and_readbacks_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = _git_fixture(Path(directory))
            preview = _preview(transport)
            result = apply_private_git_sync(
                preview=preview,
                policy=_policy(sync=True),
                transport=transport,
                commit_message="Mirror exact OPENCNTX records",
            )
            self.assertEqual(result.status, "SYNC_APPLIED_READBACK_VERIFIED")
            self.assertEqual(transport.remote_head("origin", "mirror"), result.commit)
            self.assertEqual(result.receipt["result"], "APPLIED")
            validate_runtime_record(dict(result.receipt))

    def test_private_git_sync_recovers_lost_push_response_by_readback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = _git_fixture(Path(directory), lose_push_response=True)
            preview = _preview(transport)
            result = apply_private_git_sync(
                preview=preview,
                policy=_policy(sync=True),
                transport=transport,
                commit_message="Mirror exact OPENCNTX records",
            )
            self.assertEqual(result.status, "SYNC_ALREADY_PRESENT_READBACK_VERIFIED")
            self.assertEqual(result.receipt["result"], "ALREADY_PRESENT_SAME_BYTES")

    def test_private_git_sync_stops_on_policy_and_remote_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = _git_fixture(Path(directory))
            preview = _preview(transport)
            changed = _policy(sync=True)
            changed["max_batch_files"] = 99
            with self.assertRaises(StorageRuntimeError):
                apply_private_git_sync(
                    preview=preview,
                    policy=changed,
                    transport=transport,
                    commit_message="Mirror exact OPENCNTX records",
                )
            transport.root.joinpath("dirty.txt").write_text("dirty", encoding="utf-8")
            with self.assertRaises(StorageRuntimeError):
                apply_private_git_sync(
                    preview=preview,
                    policy=_policy(sync=True),
                    transport=transport,
                    commit_message="Mirror exact OPENCNTX records",
                )

    def test_exact_120_case_corpus_is_model_free(self) -> None:
        corpus = load_storage_sync_corpus(FIXTURE.read_bytes())
        result = run_storage_sync_corpus(corpus)
        self.assertEqual(len(CASE_RESULT_CODES), SCENARIO_COUNT)
        self.assertEqual(result.scenario_count, 120)
        self.assertEqual(result.passed, 120)
        self.assertEqual(result.failed, 0)
        self.assertRegex(result.result_digest, r"^[0-9a-f]{64}$")
        self.assertEqual(corpus["table_digest"], SCENARIO_TABLE_SHA256)

    def test_corpus_rejects_count_ids_expected_writes_bindings_and_metadata_drift(self) -> None:
        corpus = load_storage_sync_corpus(FIXTURE.read_bytes())
        mutations = []
        missing = copy.deepcopy(corpus)
        missing["records"].pop()
        mutations.append(missing)
        duplicate = copy.deepcopy(corpus)
        duplicate["records"][1]["scenario_id"] = "S34-001"
        mutations.append(duplicate)
        expected = copy.deepcopy(corpus)
        expected["records"][0]["expected_result_code"] = "WRONG"
        mutations.append(expected)
        writes = copy.deepcopy(corpus)
        writes["records"][0]["expected_writes"] = [123]
        mutations.append(writes)
        binding = copy.deepcopy(corpus)
        binding["records"][0]["input"]["bindings_digest"] = "0" * 64
        mutations.append(binding)
        metadata = copy.deepcopy(corpus)
        metadata["table_digest"] = "0" * 64
        mutations.append(metadata)
        extra = copy.deepcopy(corpus)
        extra["unknown"] = True
        mutations.append(extra)
        for mutation in mutations:
            with self.subTest(keys=tuple(mutation)), self.assertRaises(StorageRuntimeError):
                validate_storage_sync_corpus(mutation)

    def test_strict_corpus_rejects_duplicate_non_nfc_constant_utf8_and_non_object(self) -> None:
        cases = (
            b'{"format":"x","format":"y"}',
            '{"value":"e\u0301"}'.encode(),
            b'{"value":NaN}',
            b"\xff",
            b"[]",
        )
        for content in cases:
            with self.subTest(content=content), self.assertRaises(StorageRuntimeError):
                load_storage_sync_corpus(content)

    def test_snapshot_and_all_previous_r9_bytes_are_frozen(self) -> None:
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["commit"], "0b28c1702cfb09b0641ab7ad44af311fdf26574f")
        self.assertEqual(snapshot["tree"], "c0b26c4960d2812454a4c394f69d72e0e242b94e")
        self.assertEqual(snapshot["file_count"], 205)
        self.assertEqual(snapshot["total_blob_bytes"], 4_177_882)
        self.assertEqual(snapshot["relevant_path_count"], 28)
        frozen = {
            ASSIGNMENT_29: "220d6ea7f3c0fbd0d84ee054e2f904bbfa0f21dc",
            ASSIGNMENT_31: "e25c3ccec031e3ff938d0dcaa1eb7ec0bcb3991b",
            ASSIGNMENT_31_SNAPSHOT: "9bf13af2caf13697a5549f9c8a34391f8f20a03c",
            ASSIGNMENT_32: "c6474f90cb0b1869d83130469417e4287ddf57eb",
            ASSIGNMENT_32_SNAPSHOT: "53fe93ac779f6573572f8d53b99c9591e05c39ee",
            ASSIGNMENT_33: "e712be822cb8633fc5078d8edb5367e387f9304f",
            ASSIGNMENT_33_SNAPSHOT: "35a2a7ebfea9d204982f52064a18e3764fc3ff2f",
        }
        for path, expected_blob in frozen.items():
            self.assertEqual(_git_blob_id(path), expected_blob)

    def test_module_has_no_central_service_or_forbidden_git_implementation(self) -> None:
        source = (ROOT / "src" / "opencntx" / "storage_runtime.py").read_text(encoding="utf-8")
        lowered = source.lower()
        for marker in (
            "import socket",
            "import subprocess",
            "import urllib",
            "import requests",
            "force_push",
            "git lfs",
            "central_owner_url",
            "assignment_35_active",
        ):
            self.assertNotIn(marker, lowered)
        self.assertEqual(
            ASSIGNMENT_34_PROPOSAL_SHA256,
            "aa1ca0d62dd67fe24b53d8f47e0828b2177852a604239fa289f9e3927edecae3",
        )


def _preview_with(
    transport: LocalGitTransport,
    *,
    candidates=None,
    repository_bytes: int = 100,
):
    good = _preview(transport)
    remote_url = transport.remote_url("origin")
    proof = VisibilityProof(
        repository_id="PRIVATE_REPOSITORY_1",
        visibility="PRIVATE",
        freshness="CURRENT",
        remote_url_digest=hashlib.sha256(remote_url.encode()).hexdigest(),
        owner_instruction_digest=OWNER_DIGEST,
        actor_id="ACTOR_ARCHITECT",
    )
    return build_sync_preview(
        project_id="PROJECT_R9",
        actor_id="ACTOR_ARCHITECT",
        policy=_policy(sync=True),
        owner_instruction_digest=OWNER_DIGEST,
        visibility_proof=proof,
        remote_alias="origin",
        remote_url=remote_url,
        branch="mirror",
        local_base_commit=good.base_commit,
        remote_base_commit=good.base_commit,
        candidates=candidates or good.candidates,
        repository_bytes=repository_bytes,
        provider_limit_bytes=2 * 1024**3,
        mirror_clean=True,
        guard_status="ALLOW_EXACT_ACTION",
        hook_trace_digest=HOOK_DIGEST,
    )


if __name__ == "__main__":
    unittest.main()
