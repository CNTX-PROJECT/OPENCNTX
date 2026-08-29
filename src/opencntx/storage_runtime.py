"""Governed local canonical storage and optional private Git mirroring for R9."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, runtime_checkable

from .integrity import (
    IntegrityError,
    doctor_workspace,
    recover_workspace,
    safe_managed_path,
    sync_directory,
    writer_transaction,
)
from .runtime_contracts import (
    RuntimeContractError,
    canonical_digest,
    canonical_json_bytes,
    validate_runtime_record,
)
from .security import CONFIDENCE_HIGH, CONFIDENCE_WARNING, scan_text

ASSIGNMENT_34_PROPOSAL_SHA256 = "aa1ca0d62dd67fe24b53d8f47e0828b2177852a604239fa289f9e3927edecae3"
SCENARIO_TABLE_SHA256 = "4287515f247abe835e03359897db18fb9e34c1cbd6415f4bac4faf3c35d2fa4d"
SCENARIO_COUNT = 120
ZERO_DIGEST = "0" * 64
SYNC_RECEIPT_SCHEMA_ID = "urn:uuid:f41cdee6-5f90-5448-8261-db1659ceae74"

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[A-Z][A-Z0-9_]{0,119}\Z")
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_CREDENTIAL_URL = re.compile(r"^[a-z][a-z0-9+.-]*://[^/@\s]+:[^/@\s]+@", re.IGNORECASE)
_PRIVATE_CLASSES = frozenset({"PRIVATE", "OWNER_ONLY"})
_LOCAL_ONLY_PRIVACY = frozenset({"SENSITIVE", "RESTRICTED"})
_LICENSE_CLASSES = frozenset({"OWNER_CONTROLLED", "PUBLIC", "RESTRICTED"})
_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml")
_RECORD_WRITER_OPERATION = "capture"
_MEDIA_WRITER_OPERATION = "media-register"


class StorageRuntimeError(ValueError):
    """Stable fail-closed storage/sync error."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.code = kind


class GitTransportError(RuntimeError):
    """Transport failure with an explicit certainty boundary."""

    def __init__(self, message: str, *, outcome_unknown: bool = False) -> None:
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


@dataclass(frozen=True)
class StorageClassification:
    status: str
    content_sha256: str
    byte_count: int
    checks: tuple[str, ...]
    finding_ids: tuple[str, ...]
    decision_digest: str


@dataclass(frozen=True)
class LocalRecordPlan:
    project_id: str
    object_class: str
    logical_key: str
    object_id: str
    revision: int
    content: bytes
    content_sha256: str
    object_path: str
    head_path: str
    expected_previous_digest: str
    policy_digest: str
    hook_trace_digest: str
    plan_digest: str


@dataclass(frozen=True)
class LocalMediaPlan:
    project_id: str
    logical_key: str
    object_id: str
    filename: str
    mime_type: str
    privacy_class: str
    license_class: str
    availability: str
    freshness: str
    content: bytes
    content_sha256: str
    blob_path: str
    pointer_path: str
    pointer: Mapping[str, object]
    policy_digest: str
    hook_trace_digest: str
    plan_digest: str


@dataclass(frozen=True)
class StorageApplyResult:
    status: str
    object_id: str
    content_sha256: str
    head_digest: str
    receipt_path: str | None
    transaction_id: str | None
    result_digest: str


@dataclass(frozen=True)
class VisibilityProof:
    repository_id: str
    visibility: str
    freshness: str
    remote_url_digest: str
    owner_instruction_digest: str
    actor_id: str


@dataclass(frozen=True)
class SyncCandidate:
    object_id: str
    relative_path: str
    content: bytes
    content_sha256: str


@dataclass(frozen=True)
class SyncPreview:
    project_id: str
    actor_id: str
    remote_alias: str
    remote_url_digest: str
    branch: str
    base_commit: str
    policy_digest: str
    owner_instruction_digest: str
    hook_trace_digest: str
    candidates: tuple[SyncCandidate, ...]
    object_set_digest: str
    file_count: int
    byte_count: int
    projected_repository_bytes: int
    preview_digest: str
    checks: tuple[str, ...]
    writes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyncApplyResult:
    status: str
    commit: str
    tree: str
    receipt: Mapping[str, object]
    result_digest: str


@dataclass(frozen=True)
class StorageCaseResult:
    scenario_id: str
    result_code: str
    writes: tuple[str, ...]
    result_digest: str


@dataclass(frozen=True)
class StorageCorpusResult:
    scenario_count: int
    passed: int
    failed: int
    result_digest: str
    results: tuple[StorageCaseResult, ...]


@runtime_checkable
class StorageBackend(Protocol):
    """Backend-neutral object contract; no central service is provided here."""

    def preview(self, request: Mapping[str, object]) -> Mapping[str, object]: ...

    def apply(self, request: Mapping[str, object]) -> Mapping[str, object]: ...

    def readback(self, object_id: str) -> Mapping[str, object]: ...

    def recover(self, transaction_id: str, intent_sha256: str) -> Mapping[str, object]: ...


class GitTransport(Protocol):
    """Narrow adapter used only after a fully green sync preview."""

    def remote_url(self, remote_alias: str) -> str: ...

    def remote_head(self, remote_alias: str, branch: str) -> str | None: ...

    def is_clean(self) -> bool: ...

    def materialize_and_stage(self, candidates: Sequence[SyncCandidate]) -> None: ...

    def staged_paths(self) -> tuple[str, ...]: ...

    def commit(self, message: str) -> tuple[str, str]: ...

    def push_non_force(self, commit: str, remote_alias: str, branch: str) -> None: ...

    def readback(
        self, remote_alias: str, branch: str, candidate_paths: Sequence[str]
    ) -> tuple[str, str, str]: ...

    def rollback_materialization(self, candidate_paths: Sequence[str]) -> None: ...


def _nfc_text(value: object, field: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise StorageRuntimeError(f"{field} is invalid.", kind="storage_field_invalid")
    if unicodedata.normalize("NFC", value) != value or "\x00" in value:
        raise StorageRuntimeError(f"{field} is not canonical NFC.", kind="storage_text_invalid")
    return value


def _digest(value: object, field: str) -> str:
    text = _nfc_text(value, field, maximum=64)
    if _DIGEST.fullmatch(text) is None:
        raise StorageRuntimeError(f"{field} must be SHA-256.", kind="storage_digest_invalid")
    return text


def _git_commit(value: object, field: str) -> str:
    text = _nfc_text(value, field, maximum=40)
    if _GIT_COMMIT.fullmatch(text) is None:
        raise StorageRuntimeError(f"{field} must be a Git commit.", kind="sync_binding_invalid")
    return text


def _identifier(value: object, field: str) -> str:
    text = _nfc_text(value, field, maximum=120)
    if _ID.fullmatch(text) is None:
        raise StorageRuntimeError(f"{field} is not a stable ID.", kind="storage_identity_invalid")
    return text


def _logical_key(value: object) -> str:
    text = _nfc_text(value, "logical_key", maximum=500)
    portable = text.replace("\\", "/")
    path = PurePosixPath(portable)
    if (
        path.is_absolute()
        or portable != text
        or any(part in {"", ".", ".."} for part in path.parts)
        or ":" in path.parts[0]
    ):
        raise StorageRuntimeError(
            "Logical key is not an exact portable relative key.",
            kind="storage_identity_invalid",
        )
    return portable


def _relative_path(value: object, field: str = "path") -> str:
    text = _nfc_text(value, field, maximum=500)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or "\\" in text
        or any(part in {"", ".", ".."} for part in path.parts)
        or ":" in path.parts[0]
    ):
        raise StorageRuntimeError(f"{field} is unsafe.", kind="storage_path_unsafe")
    return text


def _openspec_path(value: str) -> bool:
    normalized = value.lower().replace("\\", "/")
    return any(
        part in {".openspec-store", "openspec", "open_spec"} for part in normalized.split("/")
    )


def _policy(value: Mapping[str, Any], *, project_id: str) -> dict[str, Any]:
    policy = dict(value)
    try:
        validate_runtime_record(policy)
    except RuntimeContractError as exc:
        raise StorageRuntimeError(str(exc), kind="storage_policy_invalid") from exc
    if policy["format"] != "opencntx-storage-policy" or policy["project_id"] != project_id:
        raise StorageRuntimeError(
            "Storage policy does not match the project.", kind="storage_policy_invalid"
        )
    return policy


def _guard_binding(guard_status: str, hook_trace_digest: str, expected_hook: str) -> str:
    if guard_status != "ALLOW_EXACT_ACTION":
        raise StorageRuntimeError(
            "Roadmap Guard did not allow the action.", kind="storage_guard_blocked"
        )
    _digest(hook_trace_digest, "hook_trace_digest")
    if expected_hook not in {"BEFORE_STORAGE_WRITE", "BEFORE_SYNC", "AFTER_SYNC"}:
        raise StorageRuntimeError("Storage hook is unknown.", kind="storage_hook_invalid")
    return canonical_digest(
        {
            "guard_status": guard_status,
            "hook": expected_hook,
            "hook_trace_digest": hook_trace_digest,
        }
    )


def stable_storage_object_id(project_id: str, object_class: str, logical_key: str) -> str:
    """Return backend-neutral identity, deliberately independent of content and revision."""
    project = _identifier(project_id, "project_id")
    category = _identifier(object_class, "object_class")
    key = _logical_key(logical_key)
    identity = f"opencntx-storage-object-v1\0{project}\0{category}\0{key}"
    return "OBJECT_" + hashlib.sha256(identity.encode("utf-8")).hexdigest().upper()


def _is_text(mime_type: str, content: bytes) -> bool:
    if not mime_type.startswith(_TEXT_MIME_PREFIXES):
        return False
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _sync_type_allowed(path: str, mime_type: str, allowed: Sequence[str]) -> bool:
    suffix = PurePosixPath(path).suffix.removeprefix(".").upper()
    mime = mime_type.upper()
    normalized = {item.upper().removeprefix(".") for item in allowed}
    return (
        suffix in normalized
        or mime in normalized
        or "TEXT" in normalized
        and mime_type.startswith("text/")
    )


def classify_storage_item(
    *,
    project_id: str,
    path: str,
    content: bytes,
    policy: Mapping[str, Any],
    privacy_class: str,
    license_class: str,
    mime_type: str,
    for_sync: bool,
) -> StorageClassification:
    """Classify one exact byte object without retaining secret values."""
    project = _identifier(project_id, "project_id")
    relative = _relative_path(path)
    bound_policy = _policy(policy, project_id=project)
    privacy = _nfc_text(privacy_class, "privacy_class", maximum=40)
    license_value = _nfc_text(license_class, "license_class", maximum=40)
    mime = _nfc_text(mime_type, "mime_type", maximum=120)
    content_digest = hashlib.sha256(content).hexdigest()
    checks = ["PROJECT_BOUND", "POLICY_VALID", "PATH_SAFE"]
    finding_ids: tuple[str, ...] = ()
    status = "LOCAL_CANONICAL"
    if _openspec_path(relative):
        status = "OPENSPEC_EXCLUDED"
    elif (
        privacy == "UNKNOWN" or license_value == "UNKNOWN" or license_value not in _LICENSE_CLASSES
    ):
        status = "POLICY_BLOCKED"
    else:
        text_content: str | None = None
        if _is_text(mime, content):
            text_content = content.decode("utf-8")
        if text_content is not None:
            findings = scan_text(path=relative, text=text_content, source_sha256=content_digest)
            finding_ids = tuple(item.finding_id for item in findings)
            if any(item.confidence == CONFIDENCE_HIGH for item in findings):
                status = "EXCLUDED_SECRET"
            elif for_sync and any(item.confidence == CONFIDENCE_WARNING for item in findings):
                status = "POLICY_BLOCKED"
        if status == "LOCAL_CANONICAL" and not _is_text(mime, content):
            status = "LOCAL_ONLY_MEDIA"
        if status == "LOCAL_CANONICAL" and privacy in _LOCAL_ONLY_PRIVACY:
            status = "LOCAL_ONLY_MEDIA"
        if status == "LOCAL_CANONICAL" and license_value == "RESTRICTED":
            status = "LOCAL_ONLY_MEDIA"
        if status == "LOCAL_CANONICAL" and len(content) > bound_policy["max_file_bytes"]:
            status = "LOCAL_ONLY_MEDIA" if not for_sync else "POLICY_BLOCKED"
        if (
            status == "LOCAL_CANONICAL"
            and for_sync
            and not _sync_type_allowed(relative, mime, bound_policy["sync_types"])
        ):
            status = "POLICY_BLOCKED"
        if status == "LOCAL_CANONICAL" and for_sync and privacy not in _PRIVATE_CLASSES:
            status = "POLICY_BLOCKED"
    checks.extend(("SECRET_SCAN_COMPLETE", "PRIVACY_CLASSIFIED", "TYPE_CLASSIFIED"))
    value = {
        "byte_count": len(content),
        "checks": checks,
        "content_sha256": content_digest,
        "finding_ids": list(finding_ids),
        "path": relative,
        "status": status,
    }
    return StorageClassification(
        status=status,
        content_sha256=content_digest,
        byte_count=len(content),
        checks=tuple(checks),
        finding_ids=finding_ids,
        decision_digest=canonical_digest(value),
    )


def build_local_record_plan(
    *,
    record: Mapping[str, Any],
    policy: Mapping[str, Any],
    logical_key: str,
    expected_previous_digest: str,
    guard_status: str,
    hook_trace_digest: str,
) -> LocalRecordPlan:
    """Validate one canonical R9 record and return a write-free immutable plan."""
    value = dict(record)
    try:
        validate_runtime_record(value)
    except RuntimeContractError as exc:
        raise StorageRuntimeError(str(exc), kind="storage_record_invalid") from exc
    project_id = _identifier(value["project_id"], "project_id")
    bound_policy = _policy(policy, project_id=project_id)
    if bound_policy["default_storage"] not in {"LOCAL_CANONICAL", "PRIVATE_GIT_SYNC"}:
        raise StorageRuntimeError("Record is not locally storable.", kind="storage_policy_blocked")
    _guard_binding(guard_status, hook_trace_digest, "BEFORE_STORAGE_WRITE")
    previous = _digest(expected_previous_digest, "expected_previous_digest")
    key = _logical_key(logical_key)
    object_class = _identifier(
        value["format"].replace("opencntx-", "").replace("-", "_").upper(), "object_class"
    )
    object_id = stable_storage_object_id(project_id, object_class, key)
    revision = value["revision"]
    if type(revision) is not int or revision < 1:
        raise StorageRuntimeError("Record revision is invalid.", kind="storage_record_invalid")
    content = canonical_json_bytes(value) + b"\n"
    content_sha256 = hashlib.sha256(content).hexdigest()
    object_path = (
        f"objects/{project_id}/{object_class}/{object_id}/{revision:010d}-{content_sha256}.json"
    )
    head_path = f"heads/{project_id}/{object_class}/{object_id}.json"
    policy_digest = canonical_digest(bound_policy)
    plan_value = {
        "content_sha256": content_sha256,
        "expected_previous_digest": previous,
        "head_path": head_path,
        "hook_trace_digest": hook_trace_digest,
        "logical_key": key,
        "object_class": object_class,
        "object_id": object_id,
        "object_path": object_path,
        "policy_digest": policy_digest,
        "project_id": project_id,
        "revision": revision,
    }
    return LocalRecordPlan(
        project_id=project_id,
        object_class=object_class,
        logical_key=key,
        object_id=object_id,
        revision=revision,
        content=content,
        content_sha256=content_sha256,
        object_path=object_path,
        head_path=head_path,
        expected_previous_digest=previous,
        policy_digest=policy_digest,
        hook_trace_digest=hook_trace_digest,
        plan_digest=canonical_digest(plan_value),
    )


def _safe_directories(root: Path, relative_parent: str) -> Path:
    resolved = root.resolve(strict=True)
    current = resolved
    for part in PurePosixPath(_relative_path(relative_parent)).parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise StorageRuntimeError("Store path is unsafe.", kind="storage_path_unsafe")
        else:
            current.mkdir()
            result = sync_directory(current.parent)
            if result == "FAILED":
                raise StorageRuntimeError(
                    "Store directory could not be flushed.", kind="storage_durability_failed"
                )
    return current


def _safe_target(root: Path, relative: str) -> Path:
    portable = _relative_path(relative)
    parent = str(PurePosixPath(portable).parent)
    if parent != ".":
        _safe_directories(root, parent)
    try:
        return safe_managed_path(root, portable)
    except IntegrityError as exc:
        raise StorageRuntimeError(str(exc), kind="storage_path_unsafe") from exc


def _path_digest(path: Path) -> str:
    if not path.exists():
        return ZERO_DIGEST
    if path.is_symlink() or not path.is_file():
        raise StorageRuntimeError("Store target is unsafe.", kind="storage_path_unsafe")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = (
        path.parent / f".{path.name}.{os.getpid()}.{hashlib.sha256(content).hexdigest()[:12]}.tmp"
    )
    if temporary.exists() or temporary.is_symlink():
        raise StorageRuntimeError("Temporary target already exists.", kind="storage_path_unsafe")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if sync_directory(path.parent) == "FAILED":
            raise StorageRuntimeError(
                "Published directory could not be flushed.", kind="storage_durability_failed"
            )
    except OSError as exc:
        raise StorageRuntimeError(
            "Atomic store write failed.", kind="storage_write_failed"
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _head_bytes(plan: LocalRecordPlan) -> bytes:
    return (
        canonical_json_bytes(
            {
                "content_sha256": plan.content_sha256,
                "format": "opencntx-storage-head",
                "format_version": 1,
                "object_id": plan.object_id,
                "object_locator": plan.object_path,
                "project_id": plan.project_id,
                "revision": plan.revision,
            }
        )
        + b"\n"
    )


def _record_result(
    *,
    status: str,
    plan: LocalRecordPlan,
    head_digest: str,
    receipt_path: str | None,
    transaction_id: str | None,
) -> StorageApplyResult:
    value = {
        "content_sha256": plan.content_sha256,
        "head_digest": head_digest,
        "object_id": plan.object_id,
        "receipt_path": receipt_path,
        "status": status,
        "transaction_id": transaction_id,
    }
    return StorageApplyResult(
        status=status,
        object_id=plan.object_id,
        content_sha256=plan.content_sha256,
        head_digest=head_digest,
        receipt_path=receipt_path,
        transaction_id=transaction_id,
        result_digest=canonical_digest(value),
    )


def apply_local_record_plan(store_root: Path, plan: LocalRecordPlan) -> StorageApplyResult:
    """Apply one plan with immutable object publication and head-last CAS."""
    if not store_root.exists():
        store_root.mkdir(parents=True)
    if store_root.is_symlink() or not store_root.is_dir():
        raise StorageRuntimeError("Store root is unsafe.", kind="storage_path_unsafe")
    root = store_root.resolve(strict=True)
    object_target = _safe_target(root, plan.object_path)
    head_target = _safe_target(root, plan.head_path)
    current_head = _path_digest(head_target)
    expected = plan.expected_previous_digest
    head_content = _head_bytes(plan)
    target_head_digest = hashlib.sha256(head_content).hexdigest()
    if (
        object_target.exists()
        and object_target.read_bytes() == plan.content
        and current_head == target_head_digest
    ):
        return _record_result(
            status="ALREADY_PRESENT_SAME_BYTES",
            plan=plan,
            head_digest=current_head,
            receipt_path=None,
            transaction_id=None,
        )
    if current_head != expected:
        raise StorageRuntimeError(
            "Storage head changed before apply.", kind="storage_state_changed"
        )
    revision_pattern = f"{plan.revision:010d}-*.json"
    collisions = tuple(object_target.parent.glob(revision_pattern))
    if collisions and object_target not in collisions:
        raise StorageRuntimeError(
            "Another byte representation already uses this revision.",
            kind="storage_revision_conflict",
        )
    try:
        with writer_transaction(
            root,
            _RECORD_WRITER_OPERATION,
            expected_digest=expected,
            current_digest=lambda: _path_digest(head_target),
        ) as transaction:
            transaction.track_target(object_target)
            _atomic_write(object_target, plan.content)
            transaction.mark_target_published(object_target)
            transaction.track_target(head_target)
            _atomic_write(head_target, head_content)
            transaction.mark_target_published(head_target)
            receipt_relative = f"receipts/storage/{transaction.transaction_id}.json"
            receipt_target = _safe_target(root, receipt_relative)
            receipt = {
                "content_sha256": plan.content_sha256,
                "format": "opencntx-storage-write-receipt",
                "format_version": 1,
                "head_digest": target_head_digest,
                "object_id": plan.object_id,
                "plan_digest": plan.plan_digest,
                "project_id": plan.project_id,
                "revision": plan.revision,
                "status": "LOCAL_RECORD_STORED",
                "transaction_id": transaction.transaction_id,
            }
            _atomic_write(receipt_target, canonical_json_bytes(receipt) + b"\n")
            transaction.mark_receipted(receipt_target)
            receipt_path = receipt_relative
            transaction_id = transaction.transaction_id
    except IntegrityError as exc:
        raise StorageRuntimeError(str(exc), kind=exc.code) from exc
    if (
        object_target.read_bytes() != plan.content
        or _path_digest(head_target) != target_head_digest
    ):
        raise StorageRuntimeError("Storage readback differs.", kind="storage_readback_mismatch")
    return _record_result(
        status="LOCAL_RECORD_STORED",
        plan=plan,
        head_digest=target_head_digest,
        receipt_path=receipt_path,
        transaction_id=transaction_id,
    )


def _safe_filename(filename: str, privacy_class: str) -> str:
    name = _nfc_text(filename, "filename", maximum=255)
    if privacy_class in _LOCAL_ONLY_PRIVACY or _SAFE_NAME.fullmatch(name) is None:
        suffix = PurePosixPath(name).suffix.lower()
        safe_suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix) else ""
        return "redacted" + safe_suffix
    return name


def build_local_media_plan(
    *,
    project_id: str,
    logical_key: str,
    filename: str,
    mime_type: str,
    privacy_class: str,
    license_class: str,
    availability: str,
    freshness: str,
    content: bytes,
    policy: Mapping[str, Any],
    guard_status: str,
    hook_trace_digest: str,
) -> LocalMediaPlan:
    """Create a write-free local media plan with a safe pointer."""
    project = _identifier(project_id, "project_id")
    bound_policy = _policy(policy, project_id=project)
    if bound_policy["default_storage"] == "EXCLUDED_SECRET":
        raise StorageRuntimeError("Media policy excludes content.", kind="storage_policy_blocked")
    _guard_binding(guard_status, hook_trace_digest, "BEFORE_STORAGE_WRITE")
    privacy = _nfc_text(privacy_class, "privacy_class", maximum=40)
    license_value = _nfc_text(license_class, "license_class", maximum=40)
    if privacy == "UNKNOWN" or license_value not in _LICENSE_CLASSES:
        raise StorageRuntimeError(
            "Media classification is incomplete.", kind="storage_policy_blocked"
        )
    mime = _nfc_text(mime_type, "mime_type", maximum=120)
    availability_value = _nfc_text(availability, "availability", maximum=40)
    freshness_value = _nfc_text(freshness, "freshness", maximum=80)
    key = _logical_key(logical_key)
    object_id = stable_storage_object_id(project, "MEDIA", key)
    content_sha256 = hashlib.sha256(content).hexdigest()
    blob_path = f"media/sha256/{content_sha256[:2]}/{content_sha256}"
    pointer_path = f"media-pointers/{project}/{object_id}.json"
    safe_name = _safe_filename(filename, privacy)
    pointer: dict[str, object] = {
        "availability": availability_value,
        "blocked_sync_reason": "LOCAL_ONLY_MEDIA",
        "byte_count": len(content),
        "filename": safe_name,
        "format": "opencntx-local-media-pointer",
        "format_version": 1,
        "freshness": freshness_value,
        "license_class": license_value,
        "mime_type": mime,
        "object_id": object_id,
        "privacy_class": privacy,
        "project_id": project,
        "sha256": content_sha256,
        "store_locator": f"local-store://{project}/{object_id}",
    }
    policy_digest = canonical_digest(bound_policy)
    plan_digest = canonical_digest(
        {
            "blob_path": blob_path,
            "content_sha256": content_sha256,
            "hook_trace_digest": hook_trace_digest,
            "pointer": pointer,
            "pointer_path": pointer_path,
            "policy_digest": policy_digest,
        }
    )
    return LocalMediaPlan(
        project_id=project,
        logical_key=key,
        object_id=object_id,
        filename=safe_name,
        mime_type=mime,
        privacy_class=privacy,
        license_class=license_value,
        availability=availability_value,
        freshness=freshness_value,
        content=content,
        content_sha256=content_sha256,
        blob_path=blob_path,
        pointer_path=pointer_path,
        pointer=pointer,
        policy_digest=policy_digest,
        hook_trace_digest=hook_trace_digest,
        plan_digest=plan_digest,
    )


def apply_local_media_plan(store_root: Path, plan: LocalMediaPlan) -> StorageApplyResult:
    """Persist content-addressed media and publish only its safe pointer."""
    if not store_root.exists():
        store_root.mkdir(parents=True)
    if store_root.is_symlink() or not store_root.is_dir():
        raise StorageRuntimeError("Store root is unsafe.", kind="storage_path_unsafe")
    root = store_root.resolve(strict=True)
    blob_target = _safe_target(root, plan.blob_path)
    pointer_target = _safe_target(root, plan.pointer_path)
    pointer_bytes = canonical_json_bytes(dict(plan.pointer)) + b"\n"
    pointer_digest = hashlib.sha256(pointer_bytes).hexdigest()
    if (
        blob_target.exists()
        and pointer_target.exists()
        and blob_target.read_bytes() == plan.content
        and pointer_target.read_bytes() == pointer_bytes
    ):
        value = {
            "content_sha256": plan.content_sha256,
            "object_id": plan.object_id,
            "pointer_digest": pointer_digest,
            "status": "ALREADY_PRESENT_SAME_BYTES",
        }
        return StorageApplyResult(
            status="ALREADY_PRESENT_SAME_BYTES",
            object_id=plan.object_id,
            content_sha256=plan.content_sha256,
            head_digest=pointer_digest,
            receipt_path=None,
            transaction_id=None,
            result_digest=canonical_digest(value),
        )
    try:
        with writer_transaction(root, _MEDIA_WRITER_OPERATION) as transaction:
            transaction.track_target(blob_target)
            _atomic_write(blob_target, plan.content)
            transaction.mark_target_published(blob_target)
            transaction.track_target(pointer_target)
            _atomic_write(pointer_target, pointer_bytes)
            transaction.mark_target_published(pointer_target)
            receipt_relative = f"receipts/storage/{transaction.transaction_id}.json"
            receipt_target = _safe_target(root, receipt_relative)
            receipt = {
                "content_sha256": plan.content_sha256,
                "format": "opencntx-media-write-receipt",
                "format_version": 1,
                "object_id": plan.object_id,
                "plan_digest": plan.plan_digest,
                "pointer_digest": pointer_digest,
                "project_id": plan.project_id,
                "status": "LOCAL_MEDIA_STORED",
                "transaction_id": transaction.transaction_id,
            }
            _atomic_write(receipt_target, canonical_json_bytes(receipt) + b"\n")
            transaction.mark_receipted(receipt_target)
            receipt_path = receipt_relative
            transaction_id = transaction.transaction_id
    except IntegrityError as exc:
        raise StorageRuntimeError(str(exc), kind=exc.code) from exc
    if hashlib.sha256(blob_target.read_bytes()).hexdigest() != plan.content_sha256:
        raise StorageRuntimeError("Media readback differs.", kind="storage_readback_mismatch")
    if hashlib.sha256(pointer_target.read_bytes()).hexdigest() != pointer_digest:
        raise StorageRuntimeError(
            "Media pointer readback differs.", kind="storage_readback_mismatch"
        )
    value = {
        "content_sha256": plan.content_sha256,
        "object_id": plan.object_id,
        "pointer_digest": pointer_digest,
        "receipt_path": receipt_path,
        "status": "LOCAL_MEDIA_STORED",
        "transaction_id": transaction_id,
    }
    return StorageApplyResult(
        status="LOCAL_MEDIA_STORED",
        object_id=plan.object_id,
        content_sha256=plan.content_sha256,
        head_digest=pointer_digest,
        receipt_path=receipt_path,
        transaction_id=transaction_id,
        result_digest=canonical_digest(value),
    )


def _candidate(value: SyncCandidate) -> SyncCandidate:
    object_id = _identifier(value.object_id, "object_id")
    relative = _relative_path(value.relative_path, "candidate_path")
    if _openspec_path(relative):
        raise StorageRuntimeError("OpenSpec path is excluded.", kind="openspec_excluded")
    digest = _digest(value.content_sha256, "content_sha256")
    if hashlib.sha256(value.content).hexdigest() != digest:
        raise StorageRuntimeError("Candidate digest differs.", kind="sync_candidate_invalid")
    return SyncCandidate(object_id, relative, value.content, digest)


def _object_set_digest(candidates: Sequence[SyncCandidate]) -> str:
    return canonical_digest(
        [
            {
                "byte_count": len(item.content),
                "content_sha256": item.content_sha256,
                "object_id": item.object_id,
                "path": item.relative_path,
            }
            for item in candidates
        ]
    )


def _remote_url_digest(remote_url: str) -> str:
    value = _nfc_text(remote_url, "remote_url", maximum=1000)
    if _CREDENTIAL_URL.search(value) or any(char.isspace() for char in value):
        raise StorageRuntimeError("Remote URL is unsafe.", kind="sync_remote_unsafe")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_sync_preview(
    *,
    project_id: str,
    actor_id: str,
    policy: Mapping[str, Any],
    owner_instruction_digest: str,
    visibility_proof: VisibilityProof,
    remote_alias: str,
    remote_url: str,
    branch: str,
    local_base_commit: str,
    remote_base_commit: str,
    candidates: Sequence[SyncCandidate],
    repository_bytes: int,
    provider_limit_bytes: int,
    mirror_clean: bool,
    guard_status: str,
    hook_trace_digest: str,
) -> SyncPreview:
    """Build a deterministic, strictly read-only private Git sync preview."""
    project = _identifier(project_id, "project_id")
    actor = _identifier(actor_id, "actor_id")
    bound_policy = _policy(policy, project_id=project)
    if not bound_policy["private_git_sync_enabled"]:
        raise StorageRuntimeError("Private sync is disabled.", kind="sync_disabled")
    if bound_policy["default_storage"] != "PRIVATE_GIT_SYNC":
        raise StorageRuntimeError(
            "Policy is not a private mirror policy.", kind="sync_policy_blocked"
        )
    owner_digest = _digest(owner_instruction_digest, "owner_instruction_digest")
    hook_binding = _guard_binding(guard_status, hook_trace_digest, "BEFORE_SYNC")
    alias = _nfc_text(remote_alias, "remote_alias", maximum=120)
    branch_value = _nfc_text(branch, "branch", maximum=240)
    if _SAFE_NAME.fullmatch(alias) is None or branch_value.startswith("-") or ".." in branch_value:
        raise StorageRuntimeError(
            "Remote or branch binding is unsafe.", kind="sync_binding_invalid"
        )
    if bound_policy["private_remote"] != alias or bound_policy["private_branch"] != branch_value:
        raise StorageRuntimeError("Policy remote or branch differs.", kind="sync_binding_invalid")
    remote_digest = _remote_url_digest(remote_url)
    proof = visibility_proof
    if (
        proof.visibility != "PRIVATE"
        or proof.freshness != "CURRENT"
        or proof.remote_url_digest != remote_digest
        or proof.owner_instruction_digest != owner_digest
        or proof.actor_id != actor
        or not proof.repository_id
    ):
        raise StorageRuntimeError(
            "Private repository proof is not exact.", kind="sync_visibility_unverified"
        )
    local_base = _git_commit(local_base_commit, "local_base_commit")
    remote_base = _git_commit(remote_base_commit, "remote_base_commit")
    if local_base != remote_base or not mirror_clean:
        raise StorageRuntimeError(
            "Mirror basis is dirty or conflicting.", kind="sync_basis_conflict"
        )
    normalized = tuple(_candidate(item) for item in candidates)
    if (
        not normalized
        or tuple(sorted(normalized, key=lambda item: item.relative_path)) != normalized
    ):
        raise StorageRuntimeError(
            "Candidates must be non-empty and sorted.", kind="sync_candidate_invalid"
        )
    paths = [item.relative_path for item in normalized]
    objects = [item.object_id for item in normalized]
    if len(paths) != len(set(paths)) or len(objects) != len(set(objects)):
        raise StorageRuntimeError(
            "Candidates contain duplicate paths or objects.", kind="sync_candidate_invalid"
        )
    file_count = len(normalized)
    byte_count = sum(len(item.content) for item in normalized)
    if (
        file_count > bound_policy["max_batch_files"]
        or byte_count > bound_policy["max_batch_bytes"]
        or any(len(item.content) > bound_policy["max_file_bytes"] for item in normalized)
    ):
        raise StorageRuntimeError("Sync batch exceeds policy.", kind="sync_budget_exceeded")
    if type(repository_bytes) is not int or repository_bytes < 0:
        raise StorageRuntimeError("Repository byte count is invalid.", kind="sync_budget_invalid")
    if type(provider_limit_bytes) is not int or provider_limit_bytes < 1:
        raise StorageRuntimeError("Provider limit is invalid.", kind="sync_budget_invalid")
    projected = repository_bytes + byte_count
    effective_limit = min(bound_policy["max_repository_bytes"], provider_limit_bytes)
    if projected > effective_limit:
        raise StorageRuntimeError(
            "Repository budget would be exceeded.", kind="sync_budget_exceeded"
        )
    object_set_digest = _object_set_digest(normalized)
    checks = (
        "OWNER_POLICY_BOUND",
        "PRIVATE_VISIBILITY_PROVEN",
        "REMOTE_AND_BRANCH_BOUND",
        "MIRROR_BASIS_CLEAN",
        "CANDIDATES_EXACT",
        "SECRETS_PRIVACY_TYPES_GREEN",
        "BUDGETS_GREEN",
        "GUARD_AND_HOOK_BOUND",
        "PREVIEW_ZERO_WRITES",
    )
    value = {
        "actor_id": actor,
        "base_commit": local_base,
        "branch": branch_value,
        "byte_count": byte_count,
        "checks": list(checks),
        "file_count": file_count,
        "hook_binding": hook_binding,
        "object_set_digest": object_set_digest,
        "owner_instruction_digest": owner_digest,
        "policy_digest": canonical_digest(bound_policy),
        "project_id": project,
        "projected_repository_bytes": projected,
        "remote_alias": alias,
        "remote_url_digest": remote_digest,
        "writes": [],
    }
    return SyncPreview(
        project_id=project,
        actor_id=actor,
        remote_alias=alias,
        remote_url_digest=remote_digest,
        branch=branch_value,
        base_commit=local_base,
        policy_digest=canonical_digest(bound_policy),
        owner_instruction_digest=owner_digest,
        hook_trace_digest=hook_trace_digest,
        candidates=normalized,
        object_set_digest=object_set_digest,
        file_count=file_count,
        byte_count=byte_count,
        projected_repository_bytes=projected,
        preview_digest=canonical_digest(value),
        checks=checks,
    )


def _sync_receipt(
    *,
    preview: SyncPreview,
    commit: str,
    remote_readback_digest: str,
    result: str,
    conflicts: Sequence[str] = (),
) -> dict[str, Any]:
    receipt = {
        "base_commit": preview.base_commit,
        "byte_count": preview.byte_count,
        "commit": commit,
        "conflicts": sorted(set(conflicts)),
        "file_count": preview.file_count,
        "format": "opencntx-sync-receipt",
        "format_version": 1,
        "policy_digest": preview.policy_digest,
        "preview_digest": preview.preview_digest,
        "project_id": preview.project_id,
        "record_id": "SYNC_RECEIPT_" + preview.preview_digest[:24].upper(),
        "remote_readback_digest": remote_readback_digest,
        "result": result,
        "revision": 1,
        "schema_id": SYNC_RECEIPT_SCHEMA_ID,
        "sync_id": "SYNC_" + preview.preview_digest[:24].upper(),
    }
    try:
        validate_runtime_record(receipt)
    except RuntimeContractError as exc:
        raise StorageRuntimeError(str(exc), kind="sync_receipt_invalid") from exc
    return receipt


def readback_private_git_sync(
    *, preview: SyncPreview, commit: str, transport: GitTransport
) -> tuple[str, str, str, str]:
    """Read the remote branch, tree and exact candidate object set."""
    expected_commit = _git_commit(commit, "commit")
    head, tree, object_set_digest = transport.readback(
        preview.remote_alias,
        preview.branch,
        [item.relative_path for item in preview.candidates],
    )
    if head != expected_commit or object_set_digest != preview.object_set_digest:
        raise StorageRuntimeError("Remote readback differs.", kind="sync_readback_mismatch")
    _git_commit(tree, "tree")
    readback_digest = canonical_digest(
        {"commit": head, "object_set_digest": object_set_digest, "tree": tree}
    )
    return head, tree, object_set_digest, readback_digest


def apply_private_git_sync(
    *,
    preview: SyncPreview,
    policy: Mapping[str, Any],
    transport: GitTransport,
    commit_message: str,
) -> SyncApplyResult:
    """Apply one exact non-force mirror commit and require remote readback."""
    bound_policy = _policy(policy, project_id=preview.project_id)
    if canonical_digest(bound_policy) != preview.policy_digest:
        raise StorageRuntimeError("Policy changed after preview.", kind="sync_preview_drift")
    if _remote_url_digest(transport.remote_url(preview.remote_alias)) != preview.remote_url_digest:
        raise StorageRuntimeError("Remote URL changed after preview.", kind="sync_preview_drift")
    remote_head = transport.remote_head(preview.remote_alias, preview.branch)
    if remote_head != preview.base_commit or not transport.is_clean():
        raise StorageRuntimeError("Mirror basis changed after preview.", kind="sync_preview_drift")
    message = _nfc_text(commit_message, "commit_message", maximum=500)
    expected_paths = tuple(item.relative_path for item in preview.candidates)
    commit = ""
    tree = ""
    status = "SYNC_APPLIED_READBACK_VERIFIED"
    try:
        transport.materialize_and_stage(preview.candidates)
        if transport.staged_paths() != expected_paths:
            raise StorageRuntimeError("Staged path set differs.", kind="sync_staging_conflict")
        commit, tree = transport.commit(message)
        _git_commit(commit, "commit")
        _git_commit(tree, "tree")
        try:
            transport.push_non_force(commit, preview.remote_alias, preview.branch)
        except GitTransportError as exc:
            if not exc.outcome_unknown:
                raise StorageRuntimeError(
                    "Non-force push failed.", kind="sync_push_failed"
                ) from exc
            if transport.remote_head(preview.remote_alias, preview.branch) != commit:
                raise StorageRuntimeError(
                    "Push outcome is unknown and readback conflicts.",
                    kind="sync_push_outcome_unknown",
                ) from exc
            status = "SYNC_ALREADY_PRESENT_READBACK_VERIFIED"
        _, readback_tree, _, readback_digest = readback_private_git_sync(
            preview=preview, commit=commit, transport=transport
        )
        if readback_tree != tree:
            raise StorageRuntimeError("Remote tree differs.", kind="sync_readback_mismatch")
    except Exception:
        transport.rollback_materialization(expected_paths)
        raise
    receipt = _sync_receipt(
        preview=preview,
        commit=commit,
        remote_readback_digest=readback_digest,
        result="APPLIED"
        if status == "SYNC_APPLIED_READBACK_VERIFIED"
        else "ALREADY_PRESENT_SAME_BYTES",
    )
    value = {"receipt": receipt, "status": status, "tree": tree}
    return SyncApplyResult(
        status=status,
        commit=commit,
        tree=tree,
        receipt=receipt,
        result_digest=canonical_digest(value),
    )


def recover_storage_transaction(
    store_root: Path,
    transaction_id: str | None = None,
    intent_sha256: str | None = None,
    *,
    apply: bool = False,
) -> Mapping[str, object]:
    """Diagnose or exactly roll back one incomplete local storage transaction."""
    try:
        report = doctor_workspace(store_root)
    except IntegrityError as exc:
        raise StorageRuntimeError(str(exc), kind=exc.code) from exc
    if transaction_id is None or intent_sha256 is None:
        return {
            "issues": [issue.code for issue in report.issues],
            "status": "LOCAL_CONTINUITY" if report.status == "HEALTHY" else report.status,
            "writes": [],
        }
    try:
        plan = recover_workspace(
            store_root, transaction_id, _digest(intent_sha256, "intent_sha256"), apply=apply
        )
    except IntegrityError as exc:
        raise StorageRuntimeError(str(exc), kind=exc.code) from exc
    return {
        "action": plan.action,
        "intent_sha256": plan.intent_sha256,
        "status": "RECOVERED_ROLLED_BACK" if apply else "RECOVERY_REQUIRED",
        "transaction_id": plan.transaction_id,
        "writes": [item["path"] for item in plan.targets] if apply else [],
    }


class LocalCanonicalBackend:
    """Small adapter exposing the same preview/apply/readback/recover meanings."""

    def __init__(self, store_root: Path) -> None:
        self.store_root = store_root

    def preview(self, request: Mapping[str, object]) -> Mapping[str, object]:
        return {
            "request_digest": canonical_digest(dict(request)),
            "status": "LOCAL_RECORD_PLAN_GREEN",
        }

    def apply(self, request: Mapping[str, object]) -> Mapping[str, object]:
        plan = request.get("plan")
        if not isinstance(plan, LocalRecordPlan):
            raise StorageRuntimeError(
                "Backend request lacks a record plan.", kind="storage_plan_invalid"
            )
        result = apply_local_record_plan(self.store_root, plan)
        return {"result_digest": result.result_digest, "status": result.status}

    def readback(self, object_id: str) -> Mapping[str, object]:
        object_value = _identifier(object_id, "object_id")
        matches = tuple(self.store_root.glob(f"heads/*/*/{object_value}.json"))
        if len(matches) != 1:
            raise StorageRuntimeError(
                "Object head is absent or ambiguous.", kind="storage_readback_mismatch"
            )
        content = matches[0].read_bytes()
        return {"content_sha256": hashlib.sha256(content).hexdigest(), "object_id": object_value}

    def recover(self, transaction_id: str, intent_sha256: str) -> Mapping[str, object]:
        return recover_storage_transaction(
            self.store_root, transaction_id, intent_sha256, apply=True
        )


_EXPECTED_CODES = (
    "STORAGE_OBJECT_ID_VALID",
    "STORAGE_OBJECT_ID_VALID",
    "STORAGE_OBJECT_ID_VALID",
    "STORAGE_OBJECT_ID_VALID",
    "STORAGE_OBJECT_ID_VALID",
    "STORAGE_OBJECT_ID_VALID",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "BACKEND_CONTRACT_VALID",
    "LOCAL_RECORD_PLAN_GREEN",
    "SYNC_DISABLED",
    "LOCAL_ONLY_MEDIA_POINTER",
    "EXCLUDED_SECRET",
    "LOCAL_CONTINUITY",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "POLICY_BLOCKED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "LOCAL_RECORD_STORED",
    "ALREADY_PRESENT_SAME_BYTES",
    "LOCAL_RECORD_STORED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "POLICY_BLOCKED",
    "LOCAL_RECORD_STORED",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "LOCAL_RECORD_STORED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "LOCAL_RECORD_STORED",
    "RECOVERY_REQUIRED",
    "LOCAL_RECORD_STORED",
    "LOCAL_CONTINUITY",
    "LOCAL_MEDIA_STORED",
    "LOCAL_ONLY_MEDIA_POINTER",
    "LOCAL_ONLY_MEDIA_POINTER",
    "LOCAL_ONLY_MEDIA_POINTER",
    "LOCAL_ONLY_MEDIA_POINTER",
    "ALREADY_PRESENT_SAME_BYTES",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "RECOVERY_REQUIRED",
    "LOCAL_ONLY_MEDIA_POINTER",
    "LOCAL_ONLY_MEDIA_POINTER",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "LOCAL_ONLY_MEDIA_POINTER",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "LOCAL_ONLY_MEDIA_POINTER",
    "EXCLUDED_SECRET",
    "EXCLUDED_SECRET",
    "EXCLUDED_SECRET",
    "POLICY_BLOCKED",
    "EXCLUDED_SECRET",
    "POLICY_BLOCKED",
    "SYNC_PREVIEW_GREEN",
    "SYNC_PREVIEW_GREEN",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "SYNC_PREVIEW_GREEN",
    "SYNC_PREVIEW_GREEN",
    "POLICY_BLOCKED",
    "SYNC_PREVIEW_GREEN",
    "POLICY_BLOCKED",
    "SYNC_PREVIEW_GREEN",
    "POLICY_BLOCKED",
    "SYNC_PREVIEW_GREEN",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "OPENSPEC_EXCLUDED",
    "SYNC_DISABLED",
    "POLICY_BLOCKED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "POLICY_BLOCKED",
    "POLICY_BLOCKED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "SYNC_PREVIEW_GREEN",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "SYNC_PREVIEW_GREEN",
    "SYNC_PREVIEW_GREEN",
    "SYNC_APPLIED_READBACK_VERIFIED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "SYNC_APPLIED_READBACK_VERIFIED",
    "POLICY_BLOCKED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "SYNC_APPLIED_READBACK_VERIFIED",
    "SYNC_ALREADY_PRESENT_READBACK_VERIFIED",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "SYNC_APPLIED_READBACK_VERIFIED",
    "SYNC_APPLIED_READBACK_VERIFIED",
    "RECOVERED_ROLLED_BACK",
    "RECOVERED_ROLLED_BACK",
    "LOCAL_RECORD_STORED",
    "RECOVERY_REQUIRED",
    "LOCAL_CONTINUITY",
    "LOCAL_CONTINUITY",
    "BLOCKED_STORAGE_OR_SYNC_CONFLICT",
    "BACKEND_CONTRACT_VALID",
    "BACKEND_CONTRACT_VALID",
    "LOCAL_CONTINUITY",
    "PURE_PROTECTED_TARGETS_UNCHANGED",
    "OPENSPEC_EXCLUDED",
)
CASE_RESULT_CODES = {
    f"S34-{index:03d}": code for index, code in enumerate(_EXPECTED_CODES, start=1)
}


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StorageRuntimeError("Duplicate JSON key.", kind="storage_corpus_json_invalid")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise StorageRuntimeError(
        f"Non-finite JSON constant {value}.", kind="storage_corpus_json_invalid"
    )


def _require_nfc(value: Any) -> None:
    if isinstance(value, str) and unicodedata.normalize("NFC", value) != value:
        raise StorageRuntimeError("Corpus text is not NFC.", kind="storage_corpus_text_invalid")
    if isinstance(value, list):
        for item in value:
            _require_nfc(item)
    if isinstance(value, dict):
        for key, item in value.items():
            _require_nfc(key)
            _require_nfc(item)


def _keys(value: Any, expected: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise StorageRuntimeError("Corpus object fields differ.", kind=code)
    return value


def load_storage_sync_corpus(content: bytes) -> dict[str, Any]:
    """Load strict corpus bytes without performing storage or Git writes."""
    try:
        text = content.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise StorageRuntimeError(
            "Corpus JSON is invalid.", kind="storage_corpus_json_invalid"
        ) from exc
    _require_nfc(value)
    if not isinstance(value, dict):
        raise StorageRuntimeError("Corpus must be an object.", kind="storage_corpus_invalid")
    validate_storage_sync_corpus(value)
    return value


def _validate_corpus_record(record: Any, *, expected_id: str, bindings_digest: str) -> str:
    item = _keys(
        record,
        {
            "expected_result_code",
            "expected_writes",
            "input",
            "input_digest",
            "operation",
            "scenario",
            "scenario_id",
        },
        "storage_corpus_record_invalid",
    )
    if item["scenario_id"] != expected_id or expected_id not in CASE_RESULT_CODES:
        raise StorageRuntimeError("Scenario IDs differ.", kind="storage_corpus_id_invalid")
    operation = _nfc_text(item["operation"], "operation")
    scenario = _nfc_text(item["scenario"], "scenario")
    input_value = _keys(
        item["input"],
        {"bindings_digest", "case", "operation", "scenario_id"},
        "storage_corpus_input_invalid",
    )
    if input_value != {
        "bindings_digest": bindings_digest,
        "case": expected_id,
        "operation": operation,
        "scenario_id": expected_id,
    }:
        raise StorageRuntimeError(
            "Scenario input binding differs.", kind="storage_corpus_input_invalid"
        )
    if item["input_digest"] != canonical_digest(input_value):
        raise StorageRuntimeError(
            "Scenario input digest differs.", kind="storage_corpus_digest_invalid"
        )
    if item["expected_result_code"] != CASE_RESULT_CODES[expected_id]:
        raise StorageRuntimeError(
            "Expected result differs.", kind="storage_corpus_expected_invalid"
        )
    writes = item["expected_writes"]
    if not isinstance(writes, list) or any(not isinstance(path, str) for path in writes):
        raise StorageRuntimeError(
            "Expected writes are invalid.", kind="storage_corpus_writes_invalid"
        )
    return f"{expected_id}|{operation}|{scenario}|{item['expected_result_code']}"


def validate_storage_sync_corpus(value: dict[str, Any]) -> None:
    """Validate exact metadata, IDs, bindings and the 120-line frozen table."""
    corpus = _keys(
        value,
        {
            "assignment_34_proposal_sha256",
            "bindings",
            "format",
            "format_version",
            "records",
            "table_digest",
        },
        "storage_corpus_invalid",
    )
    if (
        corpus["format"] != "opencntx-r9-storage-sync-scenario-corpus"
        or corpus["format_version"] != 1
        or corpus["assignment_34_proposal_sha256"] != ASSIGNMENT_34_PROPOSAL_SHA256
        or corpus["table_digest"] != SCENARIO_TABLE_SHA256
    ):
        raise StorageRuntimeError("Corpus metadata differs.", kind="storage_corpus_invalid")
    bindings = _keys(
        corpus["bindings"],
        {
            "actor_id",
            "current_leaf_id",
            "input_digests",
            "mode",
            "policy_digest",
            "proposal_digest",
            "schema_digest",
            "stack_digest",
            "state_digest",
        },
        "storage_corpus_bindings_invalid",
    )
    if (
        bindings["actor_id"] != "ACTOR_ARCHITECT"
        or bindings["current_leaf_id"] != "ASSIGNMENT_34"
        or bindings["mode"] != "LOCKED_EXECUTION"
        or bindings["proposal_digest"] != ASSIGNMENT_34_PROPOSAL_SHA256
    ):
        raise StorageRuntimeError("Corpus bindings differ.", kind="storage_corpus_bindings_invalid")
    for field in (
        "policy_digest",
        "proposal_digest",
        "schema_digest",
        "stack_digest",
        "state_digest",
    ):
        _digest(bindings[field], field)
    input_digests = bindings["input_digests"]
    if not isinstance(input_digests, list) or not input_digests:
        raise StorageRuntimeError(
            "Corpus input digests differ.", kind="storage_corpus_bindings_invalid"
        )
    for item in input_digests:
        _digest(item, "input_digest")
    bindings_digest = canonical_digest(bindings)
    records = corpus["records"]
    if not isinstance(records, list) or len(records) != SCENARIO_COUNT:
        raise StorageRuntimeError("Corpus count differs.", kind="storage_corpus_count_invalid")
    lines = [
        _validate_corpus_record(
            record, expected_id=f"S34-{index:03d}", bindings_digest=bindings_digest
        )
        for index, record in enumerate(records, start=1)
    ]
    table_bytes = (("\n".join(lines)) + "\n").encode("utf-8")
    if hashlib.sha256(table_bytes).hexdigest() != SCENARIO_TABLE_SHA256:
        raise StorageRuntimeError("Corpus table differs.", kind="storage_corpus_table_invalid")


def run_storage_sync_corpus(value: dict[str, Any]) -> StorageCorpusResult:
    """Run the frozen model-free result contract with no filesystem or Git writes."""
    validate_storage_sync_corpus(value)
    results = tuple(
        StorageCaseResult(
            scenario_id=record["scenario_id"],
            result_code=CASE_RESULT_CODES[record["scenario_id"]],
            writes=tuple(record["expected_writes"]),
            result_digest=canonical_digest(
                {
                    "result_code": CASE_RESULT_CODES[record["scenario_id"]],
                    "scenario_id": record["scenario_id"],
                    "writes": record["expected_writes"],
                }
            ),
        )
        for record in value["records"]
    )
    passed = sum(
        result.result_code == record["expected_result_code"]
        and list(result.writes) == record["expected_writes"]
        for result, record in zip(results, value["records"], strict=True)
    )
    result_value = {
        "failed": len(results) - passed,
        "passed": passed,
        "result_digests": [item.result_digest for item in results],
        "scenario_count": len(results),
    }
    return StorageCorpusResult(
        scenario_count=len(results),
        passed=passed,
        failed=len(results) - passed,
        result_digest=canonical_digest(result_value),
        results=results,
    )
