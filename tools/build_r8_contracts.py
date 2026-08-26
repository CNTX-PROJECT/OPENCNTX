#!/usr/bin/env python3
"""Build the checked-in R8 public and durable contract assets.

This maintenance tool consumes the accepted private R8 registers only while
building a candidate. Generated public assets contain no private paths,
source IDs, findings, or audit commands. Runtime OPENCNTX never reads the
private register inputs and never uses the network.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

PUBLIC_BASE_HEAD = "6f54cc5d763e4dd036db36955917d9d331dea404"
PUBLIC_BASE_TREE = "064f070b1a03e347b55141233fa13a0aa9060e14"
EVIDENCE_ROUTE_ID = "EVR-aacc085acb03f830"
SCHEMA_NAME_ROOT = "https://github.com/CNTX-PROJECT/OPENCNTX/schema"


def schema_urn(format_name: str, major: int = 1) -> str:
    name = f"{SCHEMA_NAME_ROOT}/{format_name}/v{major}"
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, name)}"


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("ascii")


def pretty(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("ascii")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected object: {path}")
    return value


FORMAT_FIELDS: dict[str, tuple[str, ...]] = {
    "opencntx-attempt-basis": ("format", "format_version", "inputs"),
    "opencntx-attempt-fingerprint": (
        "command_type",
        "error_class",
        "exit_status",
        "format",
        "format_version",
        "inputs",
        "target",
    ),
    "opencntx-capture-receipt": (
        "attempt_id",
        "bytes",
        "captured_at",
        "error",
        "error_code",
        "format",
        "format_version",
        "origin",
        "original_name",
        "privacy",
        "sha256",
        "source_id",
        "status",
    ),
    "opencntx-catalog": ("format", "format_version", "sources", "chapters", "issues"),
    "opencntx-catalog-receipt": (
        "attempt_id",
        "catalog_path",
        "chapter_count",
        "error",
        "error_code",
        "format",
        "format_version",
        "freshness",
        "generated_at",
        "index_path",
        "recovery_action",
        "source_count",
        "status",
        "workspace_state_digest",
    ),
    "opencntx-chapter": (
        "format",
        "format_version",
        "chapter_id",
        "title",
        "scope",
        "revision",
        "knowledge_status",
        "last_owner_approval",
        "dependency_ids",
        "source_refs",
    ),
    "opencntx-chapter-index": (
        "format",
        "format_version",
        "generated_at",
        "workspace_state_digest",
        "index_body_sha256",
    ),
    "opencntx-control-receipt": (
        "attempt_id",
        "block_bytes",
        "block_sha256",
        "created_at",
        "error",
        "error_code",
        "format",
        "format_version",
        "mode",
        "next_action",
        "roadmap_sha256",
        "snapshot_path",
        "snapshot_sha256",
        "status",
    ),
    "opencntx-control-snapshot": (
        "format",
        "format_version",
        "mode",
        "owner_sha256",
        "roadmap_sha256",
        "current_sha256",
        "block_sha256",
        "block_bytes",
    ),
    "opencntx-definition-approval": (
        "approved_at",
        "decision",
        "definition_digest",
        "definition_id",
        "definition_type",
        "document_digest",
        "format",
        "format_version",
        "owner",
        "record_digest",
        "revision",
    ),
    "opencntx-derived-content": (
        "content_bytes",
        "content_sha256",
        "created_at",
        "derivation_id",
        "format",
        "format_version",
        "kind",
        "locators",
        "privacy",
        "producer",
        "producer_class",
        "source_bytes",
        "source_id",
        "source_record_sha256",
        "source_sha256",
        "supersedes_derivation_id",
    ),
    "opencntx-derived-promotion": (
        "capture_status",
        "content_sha256",
        "derivation_id",
        "format",
        "format_version",
        "promoted_at",
        "promoted_source_id",
        "promoted_source_record_sha256",
        "promoted_source_sha256",
        "record_sha256",
        "review_sha256",
        "source_id",
        "source_sha256",
    ),
    "opencntx-derived-removal": (
        "content_sha256",
        "derivation_id",
        "format",
        "format_version",
        "owner",
        "record_sha256",
        "removed_at",
        "source_id",
        "source_sha256",
    ),
    "opencntx-derived-review": (
        "content_sha256",
        "decision",
        "derivation_id",
        "findings",
        "format",
        "format_version",
        "record_sha256",
        "reviewed_at",
        "reviewer",
        "source_id",
    ),
    "opencntx-executor-assignment": (
        "allowed_actions",
        "context",
        "created_at",
        "data_authority",
        "delegation_depth",
        "document",
        "evidence_requirements",
        "executor_id",
        "executor_statement",
        "forbidden_actions",
        "format",
        "format_version",
        "may_delegate",
        "playbook",
        "record_digest",
        "role",
        "steps",
        "stop_conditions",
        "task",
    ),
    "opencntx-lifecycle-checkpoint": (
        "checkpoint_id",
        "completed_at",
        "directory_flush",
        "format",
        "format_version",
        "plan_sha256",
        "targets",
    ),
    "opencntx-lifecycle-plan": (
        "compatibility_matrix_sha256",
        "format",
        "format_version",
        "operation",
        "schema_bundle_sha256",
    ),
    "opencntx-lifecycle-state": (
        "format",
        "format_version",
        "inventory_sha256",
        "record_count",
        "schema_bundle_sha256",
        "trust_statement",
    ),
    "opencntx-manifest": (
        "format",
        "format_version",
        "task",
        "selection",
        "package",
        "sources",
        "excluded",
        "ignored",
    ),
    "opencntx-media-receipt": (
        "content_sha256",
        "created_at",
        "derivation_id",
        "format",
        "format_version",
        "operation",
        "promoted_source_id",
        "record_sha256",
        "source_id",
        "status",
    ),
    "opencntx-navigation": (
        "format",
        "format_version",
        "task",
        "catalog_state_digest",
        "budget",
        "read",
        "chapters",
        "sources",
        "not_read",
        "warnings",
        "scope_statement",
    ),
    "opencntx-navigation-receipt": (
        "attempt_id",
        "created_at",
        "format",
        "format_version",
        "operation",
        "package_path",
        "status",
        "task_id",
    ),
    "opencntx-playbook": (
        "allowed_actions",
        "architect",
        "created_at",
        "definition_id",
        "definition_type",
        "document",
        "evidence_requirements",
        "forbidden_actions",
        "format",
        "format_version",
        "handoff",
        "inputs",
        "purpose",
        "revision",
        "steps",
        "stop_conditions",
        "supersedes_digest",
        "title",
    ),
    "opencntx-playbook-receipt": (
        "attempt_id",
        "created_at",
        "format",
        "format_version",
        "operation",
        "status",
    ),
    "opencntx-recovery-backup": (
        "backup_id",
        "current_targets",
        "format",
        "format_version",
        "intent_sha256",
        "transaction_id",
    ),
    "opencntx-recovery-receipt": (
        "action",
        "backup_path",
        "before_targets",
        "completed_at",
        "format",
        "format_version",
        "intent_sha256",
        "receipt_id",
        "status",
        "transaction_id",
    ),
    "opencntx-role": (
        "allowed_actions",
        "architect",
        "created_at",
        "definition_id",
        "definition_type",
        "delegation_depth",
        "document",
        "forbidden_actions",
        "format",
        "format_version",
        "handoff",
        "may_delegate",
        "owner_authority",
        "responsibilities",
        "revision",
        "supersedes_digest",
        "title",
    ),
    "opencntx-source": (
        "bytes",
        "captured_at",
        "format",
        "format_version",
        "origin",
        "original_name",
        "privacy",
        "sha256",
        "source_id",
        "status",
        "stored_path",
        "supersedes",
    ),
    "opencntx-task-event": (
        "format",
        "format_version",
        "task_id",
        "revision",
        "event_number",
        "event_type",
        "from_status",
        "to_status",
        "actor_role",
        "actor_id",
        "created_at",
        "previous_record_digest",
        "object_digest",
        "payload",
        "record_digest",
    ),
    "opencntx-task-receipt": (
        "format",
        "format_version",
        "status",
        "task_id",
        "created_at",
    ),
    "opencntx-task-view": ("format", "format_version", "body_sha256"),
    "opencntx-transaction": (
        "created_at",
        "expected_digest",
        "format",
        "format_version",
        "locks",
        "operation",
        "task_id",
        "transaction_id",
    ),
    "opencntx-transaction-completion": (
        "completed_at",
        "format",
        "format_version",
        "intent_sha256",
        "status",
        "transaction_id",
    ),
    "opencntx-transaction-phase": (
        "details",
        "directory_sync",
        "format",
        "format_version",
        "phase",
        "phase_number",
        "recorded_at",
        "transaction_id",
    ),
    "opencntx-workspace": ("format", "format_version", "max_source_bytes", "max_storage_bytes"),
    "opencntx-writer-lock": (
        "created_at",
        "format",
        "format_version",
        "host",
        "lock_id",
        "operation",
        "pid",
        "scope",
        "target",
    ),
}


OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    "opencntx-manifest": ("security",),
    "opencntx-lifecycle-plan": (
        "basis_inventory_sha256",
        "basis_targets_sha256",
        "checkpoint",
        "checkpoint_required_bytes",
        "record_count",
        "records",
        "state_before_sha256",
        "target_state",
        "targets",
    ),
    "opencntx-navigation-receipt": (
        "context_sha256",
        "error",
        "error_code",
        "file_count",
        "manifest_sha256",
        "next_action",
        "proposal_digest",
        "total_bytes",
    ),
    "opencntx-playbook-receipt": (
        "approval_record_digest",
        "definition_digest",
        "definition_id",
        "definition_type",
        "document_digest",
        "executor_id",
        "record_digest",
        "revision",
        "task_id",
    ),
    "opencntx-recovery-receipt": ("after_targets",),
    "opencntx-task-receipt": (
        "error",
        "error_code",
        "event_number",
        "event_type",
        "next_action",
        "object_digest",
        "operation",
        "record_digest",
        "revision",
        "task_path",
        "task_status",
    ),
}


NULLABLE_FIELDS = {
    "block_bytes",
    "block_sha256",
    "catalog_path",
    "checkpoint",
    "error",
    "error_code",
    "from_status",
    "index_path",
    "next_action",
    "origin",
    "package_path",
    "previous_record_digest",
    "promoted_source_id",
    "recovery_action",
    "snapshot_path",
    "snapshot_sha256",
    "supersedes",
    "supersedes_derivation_id",
    "task_id",
}


ARRAY_FIELDS = {
    "allowed_actions",
    "chapters",
    "dependency_ids",
    "evidence_requirements",
    "excluded",
    "findings",
    "forbidden_actions",
    "ignored",
    "inputs",
    "issues",
    "locators",
    "locks",
    "not_read",
    "read",
    "records",
    "responsibilities",
    "source_refs",
    "sources",
    "steps",
    "stop_conditions",
    "targets",
    "warnings",
}


OBJECT_FIELDS = {
    "after_targets",
    "before_targets",
    "budget",
    "checkpoint",
    "context",
    "current_targets",
    "details",
    "document",
    "freshness",
    "package",
    "payload",
    "playbook",
    "role",
    "selection",
    "security",
    "task",
    "target_state",
}


INTEGER_FIELDS = {
    "block_bytes",
    "bytes",
    "chapter_count",
    "content_bytes",
    "delegation_depth",
    "event_number",
    "exit_status",
    "file_count",
    "format_version",
    "max_source_bytes",
    "max_storage_bytes",
    "phase_number",
    "pid",
    "record_count",
    "revision",
    "source_bytes",
    "source_count",
    "total_bytes",
}


BOOLEAN_FIELDS = {"may_delegate"}


def json_types(field: str) -> list[str]:
    if field in ARRAY_FIELDS:
        result = ["array"]
    elif field in OBJECT_FIELDS:
        result = ["object"]
    elif field in INTEGER_FIELDS:
        result = ["integer"]
    elif field in BOOLEAN_FIELDS:
        result = ["boolean"]
    else:
        result = ["string"]
    if field in NULLABLE_FIELDS:
        result.append("null")
    return result


def example_value(field: str, types: list[str]) -> object:
    primary = next(item for item in types if item != "null")
    if primary == "array":
        return []
    if primary == "object":
        return {}
    if primary == "integer":
        return 1
    if primary == "boolean":
        return False
    if field.endswith(("sha256", "digest")):
        return "0" * 64
    if field == "status":
        return "CURRENT"
    if field == "privacy":
        return "PRIVATE"
    if field == "format":
        raise AssertionError("format is assigned separately")
    return f"fixture-{field.replace('_', '-')}"


def json_fixture(format_name: str, required: tuple[str, ...]) -> bytes:
    value: dict[str, object] = {}
    for field in required:
        if field == "format":
            value[field] = format_name
        elif field == "format_version":
            value[field] = 1
        else:
            value[field] = example_value(field, json_types(field))
    return pretty(value)


def markdown_fixture(format_name: str) -> bytes:
    zero = "0" * 64
    if format_name == "opencntx-workspace":
        return (
            b"---\nformat: opencntx-workspace\nformat_version: 1\n"
            b"max_source_bytes: 2147483648\nmax_storage_bytes: 21474836480\n---\n\n# CURRENT\n"
        )
    if format_name == "opencntx-chapter":
        return (
            b'+++\nformat = "opencntx-chapter"\nformat_version = 1\nchapter_id = "CH-FIXTURE"\n'
            b'title = "Fixture"\nscope = "v0.3 contract fixture"\nrevision = 1\n'
            b'knowledge_status = "DRAFT"\nlast_owner_approval = ""\ndependency_ids = []\nsource_refs = []\n'
            b"+++\n\n# Fixture\n"
        )
    if format_name == "opencntx-chapter-index":
        return (
            f"---\nformat: opencntx-chapter-index\nformat_version: 1\ngenerated_at: 2026-08-20T00:00:00.000000Z\n"
            f"workspace_state_digest: {zero}\nindex_body_sha256: {zero}\n---\n\n# Chapter index\n"
        ).encode()
    if format_name == "opencntx-control-snapshot":
        return (
            "<!-- OPENCNTX:MANAGED-CONTROL-SNAPSHOT -->\n---\nformat: opencntx-control-snapshot\n"
            f"format_version: 1\nmode: COMPACT_MARKED\nowner_sha256: {zero}\nroadmap_sha256: {zero}\n"
            f"current_sha256: {zero}\nblock_sha256: {zero}\nblock_bytes: 1\n---\n\n# OPENCNTX control snapshot\n"
        ).encode()
    if format_name == "opencntx-task-view":
        body = b"# Task TASK-20260820-0001\n"
        return (
            "<!-- opencntx-task-view\nformat: opencntx-task-view\nformat_version: 1\n"
            f"body_sha256: {digest(body)}\n-->\n"
        ).encode() + body
    raise AssertionError(format_name)


MARKDOWN_FORMATS = {
    "opencntx-chapter",
    "opencntx-chapter-index",
    "opencntx-control-snapshot",
    "opencntx-task-view",
    "opencntx-workspace",
}


TEST_FAMILIES = {
    "CLI_ARGUMENT": "cli",
    "CLI_ROUTE": "cli",
    "CONFIG_FIELD": "config",
    "DURABLE_FORMAT": "durable-format",
    "ERROR_CODE": "error",
    "EXIT_CODE": "exit",
    "MACHINE_OUTPUT": "machine-output",
    "PUBLIC_DOC_CLAIM": "public-doc",
    "PYTHON_SYMBOL": "python-symbol",
    "SCHEMA_OR_VALIDATOR": "schema-validator",
    "SUPPORT_CLAIM": "support",
}

TEST_IDS = {
    "CLI_ARGUMENT": "tests.test_contracts.PublicSurfaceContractTests.test_cli_routes_and_arguments_equal_the_live_parser_contract",
    "CLI_ROUTE": "tests.test_contracts.PublicSurfaceContractTests.test_cli_routes_and_arguments_equal_the_live_parser_contract",
    "CONFIG_FIELD": "tests.test_contracts.PublicSurfaceContractTests.test_catalog_contract_payload_is_complete",
    "DURABLE_FORMAT": "tests.test_contracts.DurableFormatContractTests.test_all_36_contracts_have_complete_registered_boundaries",
    "ERROR_CODE": "tests.test_contracts.PublicSurfaceContractTests.test_error_contract_matches_runtime_error_id_literals",
    "EXIT_CODE": "tests.test_contracts.PublicSurfaceContractTests.test_catalog_contract_payload_is_complete",
    "MACHINE_OUTPUT": "tests.test_contracts.PublicSurfaceContractTests.test_catalog_contract_payload_is_complete",
    "PUBLIC_DOC_CLAIM": "tests.test_contracts.PublicSurfaceContractTests.test_public_document_contract_paths_exist",
    "PYTHON_SYMBOL": "tests.test_contracts.PublicSurfaceContractTests.test_catalog_contract_payload_is_complete",
    "SCHEMA_OR_VALIDATOR": "tests.test_contracts.DurableFormatContractTests.test_schema_bundle_contains_contracts_and_no_unmanaged_domain",
    "SUPPORT_CLAIM": "tests.test_contracts.PublicSurfaceContractTests.test_catalog_contract_payload_is_complete",
}


def target_identity(identity: dict[str, Any]) -> dict[str, Any]:
    result = dict(identity)
    name = result.get("canonical_name")
    if isinstance(name, str) and name.startswith("https://opencntx.org/schemas/"):
        filename = name.rsplit("/", 1)[-1]
        stem = filename.removesuffix(".schema.json").removesuffix(".json")
        result["canonical_name"] = schema_urn(f"opencntx-{stem.removesuffix('-v1')}")
    return result


def candidate_contract(item: dict[str, Any]) -> object:
    claim = item["current_claim"]
    if item["kind"] == "CLI_ARGUMENT":
        parsed = json.loads(claim)
        if not isinstance(parsed, dict):
            raise TypeError("CLI argument claim must be an object")
        return parsed
    if item["kind"] == "SCHEMA_OR_VALIDATOR":
        old_identity = item["public_identity"]["canonical_name"]
        new_identity = target_identity(item["public_identity"])["canonical_name"]
        if isinstance(old_identity, str) and isinstance(new_identity, str):
            claim = claim.replace(old_identity, new_identity)
    return {
        "baseline_claim": claim,
        "candidate_requirement": item["stable_target"],
    }


def build_public_contract(route_path: Path, surfaces_path: Path) -> dict[str, Any]:
    route_doc = read_json(route_path)
    route = next(
        item for item in route_doc["records"] if item["evidence_route_id"] == EVIDENCE_ROUTE_ID
    )
    wanted = set(route["surface_ids"])
    surface_doc = read_json(surfaces_path)
    selected = [item for item in surface_doc["records"] if item["surface_id"] in wanted]
    if len(selected) != 1575 or {item["surface_id"] for item in selected} != wanted:
        raise ValueError("accepted surface route is not the exact 1,575-record set")
    records = []
    for item in selected:
        identity = item["public_identity"]
        records.append(
            {
                "surface_id": item["surface_id"],
                "kind": item["kind"],
                "public_identity": target_identity(identity),
                "baseline_identity_sha256": digest(canonical(identity)),
                "stable_target": item["stable_target"],
                "contract_status": "CANDIDATE_EXECUTABLE",
                "contract": candidate_contract(item),
                "contract_test_family": TEST_FAMILIES[item["kind"]],
                "test_id": TEST_IDS[item["kind"]],
            }
        )
    counts = dict(sorted(Counter(item["kind"] for item in records).items()))
    return {
        "$id": schema_urn("opencntx-public-contract"),
        "format": "opencntx-public-contract",
        "format_version": 1,
        "basis": {
            "public_head": PUBLIC_BASE_HEAD,
            "public_tree": PUBLIC_BASE_TREE,
        },
        "surface_count": len(records),
        "counts_by_kind": counts,
        "records": sorted(records, key=lambda item: item["surface_id"]),
    }


def build_durable_contracts(
    fixtures_root: Path, durable_register_path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    durable_register = read_json(durable_register_path)
    registered = {item["format_name"]: item for item in durable_register["records"]}
    if set(registered) != set(FORMAT_FIELDS) or len(registered) != 36:
        raise ValueError("durable register is not the exact 36-format set")
    records = []
    manifest_records = []
    fixtures_root.mkdir(parents=True, exist_ok=True)
    for format_name in FORMAT_FIELDS:
        for legacy_suffix in (".json", ".md"):
            legacy = fixtures_root / f"{format_name}-v1{legacy_suffix}"
            if legacy.is_file():
                legacy.unlink()
    for format_name in sorted(FORMAT_FIELDS):
        required = FORMAT_FIELDS[format_name]
        optional = OPTIONAL_FIELDS.get(format_name, ())
        encoding = "markdown" if format_name in MARKDOWN_FORMATS else "json"
        suffix = ".md.gz" if encoding == "markdown" else ".json.gz"
        fixture_name = f"{format_name}-v1{suffix}"
        payload = (
            markdown_fixture(format_name)
            if encoding == "markdown"
            else json_fixture(format_name, required)
        )
        compressed = bytearray(gzip.compress(payload, compresslevel=0, mtime=0))
        compressed[9] = 255
        content = bytes(compressed)
        fixture_path = fixtures_root / fixture_name
        fixture_path.write_bytes(content)
        fixture_sha = digest(content)
        types = {field: json_types(field) for field in sorted(set(required) | set(optional))}
        source_record = registered[format_name]
        validator = (
            "opencntx.contracts.validate_durable_metadata"
            if encoding == "markdown"
            else "opencntx.contracts.validate_durable_record"
        )
        records.append(
            {
                "format_id": source_record["format_id"],
                "format": format_name,
                "format_version": 1,
                "schema_id": schema_urn(format_name),
                "encoding": encoding,
                "producer_surface_ids": source_record["producer_surface_ids"],
                "reader_surface_ids": source_record["reader_surface_ids"],
                "validator_surface_ids": source_record["validator_surface_ids"],
                "required_fields": list(required),
                "optional_fields": list(optional),
                "field_types": types,
                "field_contracts": [
                    {
                        "path": field,
                        "required": field in required,
                        "types": types[field],
                        "nullable": "null" in types[field],
                        "enum": (
                            [format_name]
                            if field == "format"
                            else [1]
                            if field == "format_version"
                            else None
                        ),
                    }
                    for field in sorted(types)
                ],
                "unknown_fields": "REJECT",
                "unknown_major": "REJECT_BEFORE_WRITE",
                "relationships": [
                    {"kind": "const", "field": "format", "value": format_name},
                    {"kind": "const", "field": "format_version", "value": 1},
                ],
                "conditional_requirements": [],
                "canonicalization": {
                    "serialization": (
                        "UTF8_MARKDOWN_PRODUCER_BYTES"
                        if encoding == "markdown"
                        else "UTF8_JSON_SORTED_KEYS_INDENT_2"
                    ),
                    "fixture_digest_boundary": "EXACT_FILE_BYTES",
                    "digest_field_paths": [
                        field for field in sorted(types) if field.endswith(("sha256", "digest"))
                    ],
                },
                "fixture": {
                    "path": f"tests/fixtures/v0.3.0/durable-records/{fixture_name}",
                    "bytes": len(content),
                    "sha256": fixture_sha,
                    "payload_bytes": len(payload),
                    "payload_sha256": digest(payload),
                    "source_release": "v0.3.0",
                    "source_head": PUBLIC_BASE_HEAD,
                    "contains_user_data": False,
                    "generation": "REPRODUCIBLE_V030_PRODUCER_SHAPE",
                    "expected_read": "ACCEPT",
                    "expected_verify": "SHA256_AND_CONTRACT_MATCH",
                    "read_only": True,
                },
                "validator": validator,
                "read_claim": "FIXTURE_ACCEPTED_READ_ONLY",
                "verify_claim": "FIXTURE_SHA256_AND_CONTRACT_MATCH",
                "migration_claim": "NOT_REQUIRED_FOR_BOUND_V030_FIXTURE",
                "rollback_claim": "NOT_APPLICABLE_NO_FIXTURE_WRITE",
            }
        )
        manifest_records.append(
            {
                "format": format_name,
                "format_version": 1,
                "path": fixture_name,
                "bytes": len(content),
                "sha256": fixture_sha,
                "payload_bytes": len(payload),
                "payload_sha256": digest(payload),
                "schema_id": schema_urn(format_name),
                "expected_read": "ACCEPT",
                "expected_verify": "SHA256_AND_CONTRACT_MATCH",
                "read_only": True,
            }
        )
    if len(records) != 36:
        raise ValueError(f"expected 36 durable contracts, found {len(records)}")
    value = {
        "$id": schema_urn("opencntx-durable-format-contracts"),
        "format": "opencntx-durable-format-contracts",
        "format_version": 1,
        "basis_head": PUBLIC_BASE_HEAD,
        "contract_count": 36,
        "records": records,
    }
    return value, manifest_records


def build_composed_examples(
    fixtures_root: Path, fixture_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_format = {item["format"]: item for item in fixture_records}
    specifications = {
        "core-package-v1.json.gz": (
            "CORE_PACKAGE",
            ("opencntx-manifest",),
            ("manifest binds selected source bytes and the rendered context packet",),
        ),
        "workspace-v1.json.gz": (
            "WORKSPACE",
            (
                "opencntx-workspace",
                "opencntx-source",
                "opencntx-chapter",
                "opencntx-task-event",
                "opencntx-task-view",
            ),
            (
                "workspace owns the registered source and chapter",
                "task event and task view share one task boundary",
            ),
        ),
    }
    composed_root = fixtures_root.parent / "composed"
    composed_root.mkdir(parents=True, exist_ok=True)
    for legacy_name in ("core-package-v1.json", "workspace-v1.json"):
        legacy = composed_root / legacy_name
        if legacy.is_file():
            legacy.unlink()
    result = []
    for filename, (example_id, formats, relationships) in specifications.items():
        members = []
        for format_name in formats:
            fixture = by_format[format_name]
            members.append(
                {
                    "format": format_name,
                    "format_version": 1,
                    "path": f"../durable-records/{fixture['path']}",
                    "sha256": fixture["sha256"],
                }
            )
        value = {
            "format": "opencntx-v030-composed-fixture",
            "format_version": 1,
            "example_id": example_id,
            "members": members,
            "relationships": list(relationships),
            "read_only": True,
        }
        payload = pretty(value)
        compressed = bytearray(gzip.compress(payload, compresslevel=0, mtime=0))
        compressed[9] = 255
        content = bytes(compressed)
        (composed_root / filename).write_bytes(content)
        result.append(
            {
                "example_id": example_id,
                "path": f"composed/{filename}",
                "sha256": digest(content),
                "payload_sha256": digest(payload),
                "member_count": len(members),
                "read_only": True,
            }
        )
    return result


def update_existing_schema_ids(schemas: Path) -> None:
    names = {
        "durable-records-v1.schema.json": "opencntx-durable-records",
        "lifecycle-plan-v1.schema.json": "opencntx-lifecycle-plan-schema",
        "lifecycle-state-v1.schema.json": "opencntx-lifecycle-state-schema",
    }
    for filename, contract_name in names.items():
        path = schemas / filename
        value = read_json(path)
        value["$id"] = schema_urn(contract_name)
        path.write_bytes(pretty(value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-register", type=Path, required=True)
    parser.add_argument("--surface-register", type=Path, required=True)
    parser.add_argument("--durable-register", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path("."))
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    schemas = repository / "src" / "opencntx" / "schemas"
    fixtures = repository / "tests" / "fixtures" / "v0.3.0" / "durable-records"
    public_contract = build_public_contract(args.route_register, args.surface_register)
    durable_contracts, fixture_records = build_durable_contracts(fixtures, args.durable_register)
    composed_examples = build_composed_examples(fixtures, fixture_records)

    (schemas / "public-contract-v1.json").write_bytes(pretty(public_contract))
    (schemas / "durable-format-contracts-v1.json").write_bytes(pretty(durable_contracts))

    matrix = {
        "$id": schema_urn("opencntx-compatibility-matrix"),
        "format": "opencntx-compatibility-matrix",
        "format_version": 1,
        "records": [
            {
                "format": item["format"],
                "format_version": 1,
                "status": "CURRENT",
                "schema_id": item["schema_id"],
                "contract_asset": "durable-format-contracts-v1.json",
                "fixture_path": item["fixture"]["path"],
                "fixture_sha256": item["fixture"]["sha256"],
                "validator": item["validator"],
                "producer_surface_ids": item["producer_surface_ids"],
                "reader_surface_ids": item["reader_surface_ids"],
                "unknown_major": item["unknown_major"],
            }
            for item in durable_contracts["records"]
        ],
    }
    (schemas / "compatibility-matrix-v1.json").write_bytes(pretty(matrix))
    update_existing_schema_ids(schemas)

    fixture_manifest = {
        "format": "opencntx-v030-contract-fixture-manifest",
        "format_version": 1,
        "source_release": "v0.3.0",
        "source_head": PUBLIC_BASE_HEAD,
        "generation": "REPRODUCIBLE_V030_PRODUCER_SHAPE",
        "fixture_count": 36,
        "records": fixture_records,
        "composed_example_count": 2,
        "composed_examples": composed_examples,
    }
    (fixtures.parent / "manifest.json").write_bytes(pretty(fixture_manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
