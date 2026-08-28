"""Strict, model-free contracts for the opt-in R9 project runtime foundation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import uuid
from dataclasses import dataclass
from importlib import resources
from typing import Any

SCHEMA_NAME_ROOT = "https://github.com/CNTX-PROJECT/OPENCNTX/schema"
FORMAT_VERSION = 1
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{0,119}\Z")
TOKEN_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
PATH_PATTERN = re.compile(r"(?!/)(?!.*(?:^|/)\.\.?/)(?!.*\\)[^\x00-\x1f\x7f]{1,500}\Z")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")

RUNTIME_SCHEMA_FILES = (
    "project-definition-v1.schema.json",
    "actor-binding-v1.schema.json",
    "roadmap-definition-v1.schema.json",
    "workstream-binding-v1.schema.json",
    "resource-claim-v1.schema.json",
    "action-envelope-v1.schema.json",
    "runtime-event-v1.schema.json",
    "evidence-v1.schema.json",
    "storage-policy-v1.schema.json",
    "runtime-pointer-v1.schema.json",
    "context-projection-v1.schema.json",
    "sync-receipt-v1.schema.json",
)

FORMAT_TO_SCHEMA = {
    f"opencntx-{name.removesuffix('-v1.schema.json')}": name for name in RUNTIME_SCHEMA_FILES
}

PROJECT_MODES = {
    "NEW_PROJECT",
    "EXISTING_TAKEOVER",
    "EXISTING_ASSIST",
    "MIGRATION",
    "READ_ONLY_RESEARCH",
    "UNRESOLVED",
}
PROJECT_SCOPES = {
    "FULL_PROJECT",
    "SUBPROJECT",
    "COMPONENT",
    "ONE_ASSIGNMENT",
    "READ_ONLY_SLICE",
    "UNRESOLVED",
}
SCALES = {
    "TINY_TASK",
    "SMALL_PROJECT",
    "MEDIUM_PROJECT",
    "LARGE_PROJECT",
    "MEGA_PROJECT",
    "UNRESOLVED",
}
ROLES = {"OWNER", "ARCHITECT", "WORKSTREAM_LEAD", "EXECUTOR", "REVIEWER", "OBSERVER"}
AVAILABILITY = {"AVAILABLE", "UNAVAILABLE", "PAUSED"}
ROADMAP_TYPES = {"MAIN_ROADMAP", "SUBROADMAP"}
NODE_TYPES = {"MAIN_ROADMAP", "SUBROADMAP", "PHASE", "MILESTONE", "ASSIGNMENT", "WORK_ITEM"}
NODE_STATUSES = {
    "PLANNED",
    "READY",
    "AWAITING_OWNER_APPROVAL",
    "ACTIVE",
    "DONE_CANDIDATE",
    "OWNER_ACCEPTED",
    "CLOSED",
    "BLOCKED",
    "RETURNED",
    "REJECTED",
    "PAUSED",
    "SUPERSEDED",
}
RELATION_TYPES = {
    "PARENT_OF",
    "DEPENDS_ON",
    "BLOCKS",
    "RELATES_TO",
    "SUPERSEDES",
    "CONFLICTS_WITH",
    "USES_RESOURCE",
    "OWNED_BY_WORKSTREAM",
    "RETURNS_TO",
}
RUNTIME_EVENT_TYPES = {
    "PROJECT_PROPOSED",
    "OWNER_PROJECT_BOUND",
    "INTAKE_FACT_RECORDED",
    "INTAKE_CONFLICT_RECORDED",
    "OWNER_PLAN_ACCEPTED",
    "ROADMAP_REVISION_BOUND",
    "ACTOR_BOUND",
    "ACTOR_AVAILABILITY_CHANGED",
    "WORKSTREAM_BOUND",
    "ASSIGNMENT_APPROVED",
    "ASSIGNMENT_ACTIVATED",
    "ACTION_ATTEMPT_RECORDED",
    "DONE_CANDIDATE_RECORDED",
    "ARCHITECT_REVIEWED",
    "OWNER_RESULT_ACCEPTED",
    "ASSIGNMENT_CLOSED",
    "SUBROADMAP_CLOSED",
    "RETURNED_TO_PARENT",
    "ASSIGNMENT_RETURNED",
    "ASSIGNMENT_REJECTED",
    "ASSIGNMENT_PAUSED",
    "ASSIGNMENT_BLOCKED",
    "ROADMAP_SUPERSEDED",
    "STORAGE_WRITTEN",
    "SYNC_PREVIEWED",
    "SYNC_APPLIED",
    "RECOVERY_RECORDED",
}
EVIDENCE_RESULTS = {"PASS", "FAIL", "UNKNOWN", "UNAVAILABLE", "UNSUPPORTED"}
STORAGE_CLASSES = {
    "LOCAL_CANONICAL",
    "PRIVATE_GIT_SYNC",
    "LOCAL_ONLY_MEDIA",
    "EXCLUDED_SECRET",
    "FUTURE_CENTRAL_OWNER_STORE",
}
SYNC_RESULTS = {
    "APPLIED",
    "ALREADY_PRESENT_SAME_BYTES",
    "CONFLICT",
    "NOT_FOUND",
    "POLICY_BLOCKED",
    "UNAVAILABLE",
    "UNSUPPORTED",
}

COMMON_FIELDS = {
    "format",
    "format_version",
    "schema_id",
    "record_id",
    "project_id",
    "revision",
}

FORMAT_FIELDS = {
    "opencntx-project-definition": COMMON_FIELDS
    | {
        "project_mode",
        "project_scope",
        "scale",
        "collaboration_mode",
        "declared_human_count",
        "declared_ai_worker_slots",
        "owner_actor_id",
        "parent_project_id",
        "goal",
        "non_goals",
        "source_count",
        "assignment_count",
        "dependency_depth",
        "system_count",
    },
    "opencntx-actor-binding": COMMON_FIELDS
    | {"actor_id", "role", "workstream_id", "capacity", "availability"},
    "opencntx-roadmap-definition": COMMON_FIELDS
    | {
        "roadmap_id",
        "roadmap_type",
        "parent_roadmap_id",
        "parent_node_id",
        "return_node_id",
        "nodes",
        "relations",
        "definition_of_done",
        "event_head",
    },
    "opencntx-workstream-binding": COMMON_FIELDS
    | {
        "workstream_id",
        "actor_id",
        "roadmap_id",
        "current_leaf_id",
        "max_parallelism",
        "resource_claim_ids",
    },
    "opencntx-resource-claim": COMMON_FIELDS
    | {"claim_id", "resource_ids", "conflict_set_ids", "exclusive"},
    "opencntx-action-envelope": COMMON_FIELDS
    | {
        "envelope_id",
        "actor_id",
        "workstream_id",
        "current_leaf_id",
        "roadmap_stack_digest",
        "proposal_digest",
        "input_digests",
        "allowed_actions",
        "allowed_paths",
        "protected_paths",
        "evidence_requirements",
        "budgets",
        "exact_stop",
        "rollback_boundary",
    },
    "opencntx-runtime-event": COMMON_FIELDS
    | {
        "event_id",
        "event_number",
        "event_type",
        "actor_id",
        "actor_role",
        "created_at",
        "previous_record_digest",
        "to_status",
        "payload",
    },
    "opencntx-evidence": COMMON_FIELDS
    | {
        "evidence_id",
        "evidence_type",
        "source_class",
        "locator",
        "bytes",
        "sha256",
        "captured_at",
        "freshness",
        "validator",
        "validator_version",
        "result",
        "limitations",
        "state_digest",
        "input_digests",
    },
    "opencntx-storage-policy": COMMON_FIELDS
    | {
        "policy_id",
        "default_storage",
        "private_git_sync_enabled",
        "private_remote",
        "private_branch",
        "sync_types",
        "max_file_bytes",
        "max_batch_files",
        "max_batch_bytes",
        "max_repository_bytes",
        "local_only_media",
        "excluded_classes",
    },
    "opencntx-runtime-pointer": COMMON_FIELDS
    | {
        "pointer_id",
        "mode",
        "main_roadmap_id",
        "roadmap_stack",
        "current_leaf_id",
        "event_head",
        "schema_digest",
        "policy_digest",
        "projected_state_digest",
        "expected_previous_digest",
    },
    "opencntx-context-projection": COMMON_FIELDS
    | {
        "projection_id",
        "current_leaf_id",
        "roadmap_stack_digest",
        "included",
        "excluded",
        "unread",
        "blocked",
        "max_files",
        "max_bytes",
        "total_files",
        "total_bytes",
        "breadcrumb",
        "justified_parent_fragment",
        "source_state_digest",
        "projection_digest",
    },
    "opencntx-sync-receipt": COMMON_FIELDS
    | {
        "sync_id",
        "policy_digest",
        "preview_digest",
        "base_commit",
        "result",
        "file_count",
        "byte_count",
        "commit",
        "remote_readback_digest",
        "conflicts",
    },
}

SORTED_UNIQUE_FIELDS = {
    "non_goals",
    "resource_claim_ids",
    "resource_ids",
    "conflict_set_ids",
    "input_digests",
    "allowed_actions",
    "allowed_paths",
    "protected_paths",
    "evidence_requirements",
    "limitations",
    "sync_types",
    "local_only_media",
    "excluded_classes",
    "included",
    "excluded",
    "unread",
    "blocked",
    "conflicts",
}


class RuntimeContractError(ValueError):
    """A fail-closed R9 contract error."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.code = reason


@dataclass(frozen=True)
class RuntimeSchema:
    format_name: str
    version: int
    schema_id: str
    filename: str
    sha256: str


def schema_identifier(format_name: str, major: int = FORMAT_VERSION) -> str:
    if format_name not in FORMAT_TO_SCHEMA or type(major) is not int or major != FORMAT_VERSION:
        raise RuntimeContractError(
            "Runtime format or major is unsupported.", reason="runtime_contract_version_unsupported"
        )
    name = f"{SCHEMA_NAME_ROOT}/{format_name}/v{major}"
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, name)}"


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeContractError(
                "Duplicate JSON key.", reason="runtime_contract_duplicate_key"
            )
        result[key] = value
    return result


def load_json_record(content: bytes) -> dict[str, Any]:
    try:
        text = content.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except RuntimeContractError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeContractError(
            "Runtime record is not strict UTF-8 JSON.", reason="runtime_contract_json_invalid"
        ) from exc
    if not isinstance(value, dict):
        raise RuntimeContractError(
            "Runtime record must be an object.", reason="runtime_contract_record_invalid"
        )
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"unsupported JSON constant: {value}")


def _normalized(value: object, *, path: str = "$") -> object:
    if value is None or isinstance(value, bool) or type(value) is int:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeContractError(
                f"Non-finite number at {path}.", reason="runtime_contract_number_invalid"
            )
        return value
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise RuntimeContractError(
                f"String is not Unicode NFC at {path}.", reason="runtime_contract_text_invalid"
            )
        if any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in value):
            raise RuntimeContractError(
                f"String contains unsafe control characters at {path}.",
                reason="runtime_contract_text_invalid",
            )
        return value
    if isinstance(value, list):
        return [_normalized(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or unicodedata.normalize("NFC", key) != key:
                raise RuntimeContractError(
                    f"Object key is invalid at {path}.", reason="runtime_contract_text_invalid"
                )
            result[key] = _normalized(item, path=f"{path}.{key}")
        return result
    raise RuntimeContractError(
        f"Unsupported value at {path}.", reason="runtime_contract_type_invalid"
    )


def canonical_json_bytes(value: object) -> bytes:
    normalized = _normalized(value)
    try:
        text = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeContractError(
            "Runtime value cannot be canonicalized.", reason="runtime_contract_type_invalid"
        ) from exc
    return text.encode("utf-8")


def canonical_digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _schema_bytes(filename: str) -> bytes:
    if filename not in RUNTIME_SCHEMA_FILES:
        raise RuntimeContractError(
            "Unknown R9 schema asset.", reason="runtime_contract_schema_unknown"
        )
    try:
        return resources.files("opencntx").joinpath("schemas", filename).read_bytes()
    except (FileNotFoundError, OSError) as exc:
        raise RuntimeContractError(
            "R9 schema asset is unavailable.", reason="runtime_contract_schema_missing"
        ) from exc


def runtime_schema_catalog() -> dict[str, RuntimeSchema]:
    result: dict[str, RuntimeSchema] = {}
    seen_ids: set[str] = set()
    for format_name, filename in FORMAT_TO_SCHEMA.items():
        content = _schema_bytes(filename)
        value = load_json_record(content)
        expected_id = schema_identifier(format_name)
        if (
            value.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or value.get("$id") != expected_id
            or value.get("type") != "object"
            or value.get("additionalProperties") is not False
            or value.get("x-opencntx-format") != format_name
            or value.get("x-opencntx-format-version") != FORMAT_VERSION
            or set(value.get("required", [])) != FORMAT_FIELDS[format_name]
            or set(value.get("properties", {})) != FORMAT_FIELDS[format_name]
            or expected_id in seen_ids
        ):
            raise RuntimeContractError(
                "R9 schema asset differs from the executable contract.",
                reason="runtime_contract_schema_invalid",
            )
        seen_ids.add(expected_id)
        result[format_name] = RuntimeSchema(
            format_name=format_name,
            version=FORMAT_VERSION,
            schema_id=expected_id,
            filename=filename,
            sha256=hashlib.sha256(content).hexdigest(),
        )
    return result


def runtime_schema_bundle_digest() -> str:
    records = [
        {
            "filename": schema.filename,
            "format": schema.format_name,
            "schema_id": schema.schema_id,
            "sha256": schema.sha256,
        }
        for schema in runtime_schema_catalog().values()
    ]
    return canonical_digest(records)


def _require_string(value: object, field: str, *, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RuntimeContractError(
            f"{field} must be bounded text.", reason="runtime_contract_field_invalid"
        )
    _normalized(value, path=field)
    return value


def _require_id(value: object, field: str) -> str:
    text = _require_string(value, field, maximum=120)
    if ID_PATTERN.fullmatch(text) is None:
        raise RuntimeContractError(
            f"{field} must be a stable uppercase ID.", reason="runtime_contract_id_invalid"
        )
    return text


def _require_digest(value: object, field: str, *, allow_empty: bool = False) -> str:
    if allow_empty and value == "":
        return ""
    if not isinstance(value, str) or DIGEST_PATTERN.fullmatch(value) is None:
        raise RuntimeContractError(
            f"{field} must be a SHA-256 digest.", reason="runtime_contract_digest_invalid"
        )
    return value


def _require_int(value: object, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise RuntimeContractError(
            f"{field} is outside its integer range.", reason="runtime_contract_field_invalid"
        )
    return value


def _require_enum(value: object, field: str, allowed: set[str]) -> str:
    text = _require_string(value, field, maximum=120)
    if text not in allowed:
        raise RuntimeContractError(
            f"{field} uses an unknown value.", reason="runtime_contract_enum_unknown"
        )
    return text


def _require_string_list(
    value: object,
    field: str,
    *,
    maximum: int = 500,
    ids: bool = False,
    paths: bool = False,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise RuntimeContractError(
            f"{field} must be a bounded list.", reason="runtime_contract_field_invalid"
        )
    result: list[str] = []
    for item in value:
        text = _require_id(item, field) if ids else _require_string(item, field, maximum=500)
        if paths and PATH_PATTERN.fullmatch(text) is None:
            raise RuntimeContractError(
                f"{field} contains an unsafe path.", reason="runtime_contract_path_invalid"
            )
        result.append(text)
    if field in SORTED_UNIQUE_FIELDS and result != sorted(set(result)):
        raise RuntimeContractError(
            f"{field} must be sorted and unique.", reason="runtime_contract_order_invalid"
        )
    return result


def _validate_common(record: dict[str, Any]) -> str:
    format_name = record.get("format")
    if not isinstance(format_name, str) or format_name not in FORMAT_TO_SCHEMA:
        raise RuntimeContractError(
            "Runtime format is unsupported.", reason="runtime_contract_version_unsupported"
        )
    if record.get("format_version") != FORMAT_VERSION:
        raise RuntimeContractError(
            "Runtime format major is unsupported.", reason="runtime_contract_version_unsupported"
        )
    if set(record) != FORMAT_FIELDS[format_name]:
        raise RuntimeContractError(
            "Runtime record has unknown or missing fields.",
            reason="runtime_contract_fields_invalid",
        )
    if record.get("schema_id") != schema_identifier(format_name):
        raise RuntimeContractError(
            "Runtime record schema identity differs.", reason="runtime_contract_schema_invalid"
        )
    _require_id(record["record_id"], "record_id")
    _require_id(record["project_id"], "project_id")
    _require_int(record["revision"], "revision", 1, 2_147_483_647)
    return format_name


def validate_runtime_record(record: dict[str, Any]) -> dict[str, Any]:
    canonical_json_bytes(record)
    format_name = _validate_common(record)
    validator = _FORMAT_VALIDATORS[format_name]
    validator(record)
    return record


def _validate_project(record: dict[str, Any]) -> None:
    _require_enum(record["project_mode"], "project_mode", PROJECT_MODES)
    scope = _require_enum(record["project_scope"], "project_scope", PROJECT_SCOPES)
    _require_enum(record["scale"], "scale", SCALES)
    collaboration = _require_enum(
        record["collaboration_mode"], "collaboration_mode", {"SOLO", "TEAM"}
    )
    humans = _require_int(record["declared_human_count"], "declared_human_count", 1, 64)
    _require_int(record["declared_ai_worker_slots"], "declared_ai_worker_slots", 0, 64)
    _require_id(record["owner_actor_id"], "owner_actor_id")
    parent = record["parent_project_id"]
    if parent is not None:
        _require_id(parent, "parent_project_id")
    if scope in {"SUBPROJECT", "COMPONENT"} and parent is None:
        raise RuntimeContractError(
            "Partial scope requires a parent project.", reason="runtime_contract_binding_invalid"
        )
    if (collaboration == "SOLO" and humans != 1) or (collaboration == "TEAM" and humans < 2):
        raise RuntimeContractError(
            "Collaboration mode differs from human count.",
            reason="runtime_contract_binding_invalid",
        )
    _require_string(record["goal"], "goal")
    _require_string_list(record["non_goals"], "non_goals", maximum=64)
    for field in ("source_count", "assignment_count", "dependency_depth", "system_count"):
        _require_int(record[field], field, 0, 1_000_000)


def _validate_actor(record: dict[str, Any]) -> None:
    _require_id(record["actor_id"], "actor_id")
    _require_enum(record["role"], "role", ROLES)
    if record["workstream_id"] is not None:
        _require_id(record["workstream_id"], "workstream_id")
    _require_int(record["capacity"], "capacity", 0, 100)
    _require_enum(record["availability"], "availability", AVAILABILITY)


def _validate_roadmap(record: dict[str, Any]) -> None:
    _require_id(record["roadmap_id"], "roadmap_id")
    roadmap_type = _require_enum(record["roadmap_type"], "roadmap_type", ROADMAP_TYPES)
    for field in ("parent_roadmap_id", "parent_node_id", "return_node_id"):
        if record[field] is not None:
            _require_id(record[field], field)
    if roadmap_type == "SUBROADMAP" and any(
        record[field] is None for field in ("parent_roadmap_id", "parent_node_id", "return_node_id")
    ):
        raise RuntimeContractError(
            "Subroadmap requires parent and return bindings.",
            reason="runtime_contract_binding_invalid",
        )
    nodes = record["nodes"]
    if not isinstance(nodes, list) or not nodes or len(nodes) > 500:
        raise RuntimeContractError(
            "Roadmap nodes are invalid.", reason="runtime_contract_graph_invalid"
        )
    node_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"node_id", "node_type", "status", "title"}:
            raise RuntimeContractError(
                "Roadmap node is invalid.", reason="runtime_contract_graph_invalid"
            )
        node_ids.append(_require_id(node["node_id"], "node_id"))
        _require_enum(node["node_type"], "node_type", NODE_TYPES)
        _require_enum(node["status"], "status", NODE_STATUSES)
        _require_string(node["title"], "title")
    if node_ids != sorted(set(node_ids)):
        raise RuntimeContractError(
            "Roadmap nodes must be sorted and unique.", reason="runtime_contract_graph_invalid"
        )
    relations = record["relations"]
    if not isinstance(relations, list) or len(relations) > 20_000:
        raise RuntimeContractError(
            "Roadmap relations are invalid.", reason="runtime_contract_graph_invalid"
        )
    known = set(node_ids)
    keys: list[tuple[str, str, str]] = []
    for relation in relations:
        if not isinstance(relation, dict) or set(relation) != {"from", "to", "type"}:
            raise RuntimeContractError(
                "Roadmap relation is invalid.", reason="runtime_contract_graph_invalid"
            )
        source = _require_id(relation["from"], "from")
        target = _require_id(relation["to"], "to")
        relation_type = _require_enum(relation["type"], "type", RELATION_TYPES)
        if source not in known or target not in known:
            raise RuntimeContractError(
                "Roadmap relation references an orphan.", reason="runtime_contract_graph_invalid"
            )
        keys.append((source, target, relation_type))
    if keys != sorted(set(keys)):
        raise RuntimeContractError(
            "Roadmap relations must be sorted and unique.",
            reason="runtime_contract_graph_invalid",
        )
    _require_string_list(record["definition_of_done"], "definition_of_done", maximum=64)
    _require_digest(record["event_head"], "event_head", allow_empty=True)


def _validate_workstream(record: dict[str, Any]) -> None:
    for field in ("workstream_id", "actor_id", "roadmap_id", "current_leaf_id"):
        _require_id(record[field], field)
    _require_int(record["max_parallelism"], "max_parallelism", 1, 16)
    _require_string_list(record["resource_claim_ids"], "resource_claim_ids", ids=True)


def _validate_resource(record: dict[str, Any]) -> None:
    _require_id(record["claim_id"], "claim_id")
    _require_string_list(record["resource_ids"], "resource_ids", ids=True)
    _require_string_list(record["conflict_set_ids"], "conflict_set_ids", ids=True)
    if not isinstance(record["exclusive"], bool):
        raise RuntimeContractError(
            "exclusive must be boolean.", reason="runtime_contract_field_invalid"
        )


def _validate_action(record: dict[str, Any]) -> None:
    for field in ("envelope_id", "actor_id", "workstream_id", "current_leaf_id"):
        _require_id(record[field], field)
    for field in ("roadmap_stack_digest", "proposal_digest"):
        _require_digest(record[field], field)
    _require_string_list(record["input_digests"], "input_digests")
    for digest in record["input_digests"]:
        _require_digest(digest, "input_digests")
    _require_string_list(record["allowed_actions"], "allowed_actions", maximum=64)
    _require_string_list(record["allowed_paths"], "allowed_paths", maximum=500, paths=True)
    _require_string_list(record["protected_paths"], "protected_paths", maximum=500, paths=True)
    _require_string_list(record["evidence_requirements"], "evidence_requirements", maximum=64)
    budgets = record["budgets"]
    expected = {"max_actions", "max_attempts", "max_bytes", "max_files", "max_minutes"}
    if not isinstance(budgets, dict) or set(budgets) != expected:
        raise RuntimeContractError(
            "Action budgets are invalid.", reason="runtime_contract_field_invalid"
        )
    for field in expected:
        _require_int(budgets[field], field, 1, 2_147_483_647)
    _require_string(record["exact_stop"], "exact_stop")
    _require_string(record["rollback_boundary"], "rollback_boundary")


def _validate_event(record: dict[str, Any]) -> None:
    _require_id(record["event_id"], "event_id")
    _require_int(record["event_number"], "event_number", 1, 2_147_483_647)
    _require_enum(record["event_type"], "event_type", RUNTIME_EVENT_TYPES)
    _require_id(record["actor_id"], "actor_id")
    _require_enum(record["actor_role"], "actor_role", ROLES)
    timestamp = _require_string(record["created_at"], "created_at", maximum=40)
    if TIMESTAMP_PATTERN.fullmatch(timestamp) is None:
        raise RuntimeContractError(
            "created_at is not UTC RFC 3339.", reason="runtime_contract_field_invalid"
        )
    _require_digest(record["previous_record_digest"], "previous_record_digest")
    _require_enum(record["to_status"], "to_status", NODE_STATUSES | {"BOUND", "UNBOUND"})
    if not isinstance(record["payload"], dict):
        raise RuntimeContractError(
            "Event payload must be an object.", reason="runtime_contract_field_invalid"
        )


def _validate_evidence(record: dict[str, Any]) -> None:
    _require_id(record["evidence_id"], "evidence_id")
    for field in ("evidence_type", "source_class", "locator", "freshness", "validator"):
        _require_string(record[field], field)
    _require_int(record["bytes"], "bytes", 0, (1 << 63) - 1)
    _require_digest(record["sha256"], "sha256")
    timestamp = _require_string(record["captured_at"], "captured_at", maximum=40)
    if TIMESTAMP_PATTERN.fullmatch(timestamp) is None:
        raise RuntimeContractError(
            "captured_at is not UTC RFC 3339.", reason="runtime_contract_field_invalid"
        )
    _require_string(record["validator_version"], "validator_version", maximum=120)
    _require_enum(record["result"], "result", EVIDENCE_RESULTS)
    _require_string_list(record["limitations"], "limitations", maximum=64)
    _require_digest(record["state_digest"], "state_digest")
    _require_string_list(record["input_digests"], "input_digests")
    for digest in record["input_digests"]:
        _require_digest(digest, "input_digests")


def _validate_storage(record: dict[str, Any]) -> None:
    _require_id(record["policy_id"], "policy_id")
    _require_enum(record["default_storage"], "default_storage", STORAGE_CLASSES)
    enabled = record["private_git_sync_enabled"]
    if not isinstance(enabled, bool):
        raise RuntimeContractError(
            "private_git_sync_enabled must be boolean.", reason="runtime_contract_field_invalid"
        )
    for field in ("private_remote", "private_branch"):
        if record[field] is not None:
            _require_string(record[field], field, maximum=500)
    if enabled and (record["private_remote"] is None or record["private_branch"] is None):
        raise RuntimeContractError(
            "Enabled private sync requires remote and branch.",
            reason="runtime_contract_binding_invalid",
        )
    _require_string_list(record["sync_types"], "sync_types", maximum=64)
    limits = {
        "max_file_bytes": 10 * 1024**2,
        "max_batch_files": 100,
        "max_batch_bytes": 50 * 1024**2,
        "max_repository_bytes": 1024**3,
    }
    for field, maximum in limits.items():
        _require_int(record[field], field, 1, maximum)
    _require_string_list(record["local_only_media"], "local_only_media", maximum=500)
    _require_string_list(record["excluded_classes"], "excluded_classes", maximum=64)


def _validate_pointer(record: dict[str, Any]) -> None:
    _require_id(record["pointer_id"], "pointer_id")
    _require_enum(
        record["mode"], "mode", {"INTAKE_PLANNING", "LOCKED_EXECUTION", "RETURN_TO_PARENT"}
    )
    _require_id(record["main_roadmap_id"], "main_roadmap_id")
    stack = record["roadmap_stack"]
    if not isinstance(stack, list) or not 1 <= len(stack) <= 8:
        raise RuntimeContractError(
            "Roadmap stack depth is invalid.", reason="runtime_contract_stack_invalid"
        )
    frame_keys = {
        "active_node_id",
        "event_head",
        "policy_digest",
        "projection_digest",
        "return_node_id",
        "roadmap_id",
        "roadmap_revision",
        "schema_digest",
    }
    for frame in stack:
        if not isinstance(frame, dict) or set(frame) != frame_keys:
            raise RuntimeContractError(
                "Roadmap stack frame is invalid.", reason="runtime_contract_stack_invalid"
            )
        for field in ("active_node_id", "roadmap_id"):
            _require_id(frame[field], field)
        if frame["return_node_id"] is not None:
            _require_id(frame["return_node_id"], "return_node_id")
        _require_int(frame["roadmap_revision"], "roadmap_revision", 1, 2_147_483_647)
        for field in ("event_head", "policy_digest", "projection_digest", "schema_digest"):
            _require_digest(frame[field], field)
    _require_id(record["current_leaf_id"], "current_leaf_id")
    for field in (
        "event_head",
        "schema_digest",
        "policy_digest",
        "projected_state_digest",
        "expected_previous_digest",
    ):
        _require_digest(record[field], field)


def _validate_projection(record: dict[str, Any]) -> None:
    _require_id(record["projection_id"], "projection_id")
    _require_id(record["current_leaf_id"], "current_leaf_id")
    _require_digest(record["roadmap_stack_digest"], "roadmap_stack_digest")
    for field in ("included", "excluded", "unread", "blocked"):
        _require_string_list(record[field], field, maximum=500, paths=True)
    max_files = _require_int(record["max_files"], "max_files", 1, 80)
    max_bytes = _require_int(record["max_bytes"], "max_bytes", 1, 1_048_576)
    total_files = _require_int(record["total_files"], "total_files", 0, max_files)
    total_bytes = _require_int(record["total_bytes"], "total_bytes", 0, max_bytes)
    if total_files > max_files or total_bytes > max_bytes:
        raise RuntimeContractError(
            "Context projection exceeds budget.", reason="runtime_contract_budget_exceeded"
        )
    breadcrumb = _require_string(record["breadcrumb"], "breadcrumb", maximum=8192)
    if len(breadcrumb.encode("utf-8")) > 8192:
        raise RuntimeContractError(
            "Breadcrumb exceeds its byte budget.", reason="runtime_contract_budget_exceeded"
        )
    fragment = record["justified_parent_fragment"]
    if fragment is not None:
        if not isinstance(fragment, dict) or set(fragment) != {
            "bytes",
            "expires_at",
            "path",
            "reason",
            "sha256",
        }:
            raise RuntimeContractError(
                "Justified parent fragment is invalid.", reason="runtime_contract_field_invalid"
            )
        _require_int(fragment["bytes"], "bytes", 1, 32_768)
        _require_string(fragment["path"], "path", maximum=500)
        _require_string(fragment["reason"], "reason")
        _require_string(fragment["expires_at"], "expires_at", maximum=120)
        _require_digest(fragment["sha256"], "sha256")
    _require_digest(record["source_state_digest"], "source_state_digest")
    _require_digest(record["projection_digest"], "projection_digest")


def _validate_sync(record: dict[str, Any]) -> None:
    _require_id(record["sync_id"], "sync_id")
    for field in ("policy_digest", "preview_digest"):
        _require_digest(record[field], field)
    for field in ("base_commit", "commit"):
        value = record[field]
        if value is not None and (
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None
        ):
            raise RuntimeContractError(
                f"{field} must be a Git commit.", reason="runtime_contract_field_invalid"
            )
    _require_enum(record["result"], "result", SYNC_RESULTS)
    _require_int(record["file_count"], "file_count", 0, 100)
    _require_int(record["byte_count"], "byte_count", 0, 50 * 1024**2)
    if record["remote_readback_digest"] is not None:
        _require_digest(record["remote_readback_digest"], "remote_readback_digest")
    _require_string_list(record["conflicts"], "conflicts", maximum=100)


_FORMAT_VALIDATORS = {
    "opencntx-project-definition": _validate_project,
    "opencntx-actor-binding": _validate_actor,
    "opencntx-roadmap-definition": _validate_roadmap,
    "opencntx-workstream-binding": _validate_workstream,
    "opencntx-resource-claim": _validate_resource,
    "opencntx-action-envelope": _validate_action,
    "opencntx-runtime-event": _validate_event,
    "opencntx-evidence": _validate_evidence,
    "opencntx-storage-policy": _validate_storage,
    "opencntx-runtime-pointer": _validate_pointer,
    "opencntx-context-projection": _validate_projection,
    "opencntx-sync-receipt": _validate_sync,
}
