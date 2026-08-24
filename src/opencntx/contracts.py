"""Closed public and durable-format contracts for the R8 Stable line."""

from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from importlib import resources
from typing import Any

CONTRACT_ASSET = "durable-format-contracts-v1.json"
PUBLIC_CONTRACT_ASSET = "public-contract-v1.json"
SCHEMA_NAME_ROOT = "https://github.com/CNTX-PROJECT/OPENCNTX/schema"
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_ASSET_INVALID = "contract_asset_invalid"
_ASSET_MISSING = "contract_asset_missing"
_ENCODING_INVALID = "contract_encoding_invalid"
_FIELD_TYPE_INVALID = "contract_field_type_invalid"
_FIELDS_INVALID = "contract_fields_invalid"
_RECORD_INVALID = "contract_record_invalid"
_RELATIONSHIP_INVALID = "contract_relationship_invalid"
_SCHEMA_INVALID = "contract_schema_invalid"
_VERSION_UNSUPPORTED = "contract_version_unsupported"


class ContractError(ValueError):
    """A stable fail-closed contract error."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def schema_identifier(format_name: str, major: int = 1) -> str:
    """Return the deterministic, domain-independent schema identity."""
    if (
        not isinstance(format_name, str)
        or not format_name.startswith("opencntx-")
        or not isinstance(major, int)
        or isinstance(major, bool)
        or major < 1
    ):
        raise ContractError("Schema identity input is invalid.", code=_SCHEMA_INVALID)
    name = f"{SCHEMA_NAME_ROOT}/{format_name}/v{major}"
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, name)}"


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _asset(name: str) -> bytes:
    try:
        return resources.files("opencntx").joinpath("schemas", name).read_bytes()
    except (FileNotFoundError, OSError) as exc:
        raise ContractError("Contract asset is unavailable.", code=_ASSET_MISSING) from exc


def _load_asset(name: str) -> dict[str, Any]:
    try:
        value = json.loads(_asset(name).decode("ascii"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ContractError("Contract asset is invalid.", code=_ASSET_INVALID) from exc
    if not isinstance(value, dict):
        raise ContractError("Contract asset is not an object.", code=_ASSET_INVALID)
    return value


@lru_cache(maxsize=1)
def durable_contract_catalog() -> dict[str, Any]:
    """Load and structurally verify the 36-format contract catalog."""
    value = _load_asset(CONTRACT_ASSET)
    if (
        value.get("format") != "opencntx-durable-format-contracts"
        or value.get("format_version") != 1
        or value.get("contract_count") != 36
        or not isinstance(value.get("records"), list)
        or len(value["records"]) != 36
    ):
        raise ContractError("Durable contract catalog is invalid.", code=_ASSET_INVALID)
    seen: set[tuple[str, int]] = set()
    seen_schema_ids: set[str] = set()
    for record in value["records"]:
        if not isinstance(record, dict):
            raise ContractError("Durable contract record is invalid.", code=_ASSET_INVALID)
        format_name = record.get("format")
        version = record.get("format_version")
        schema_id = record.get("schema_id")
        if (
            not isinstance(format_name, str)
            or not isinstance(version, int)
            or isinstance(version, bool)
            or version != 1
            or record.get("unknown_fields") != "REJECT"
            or record.get("unknown_major") != "REJECT_BEFORE_WRITE"
        ):
            raise ContractError("Durable contract record is invalid.", code=_ASSET_INVALID)
        key = (format_name, version)
        if (
            schema_id != schema_identifier(format_name, version)
            or key in seen
            or schema_id in seen_schema_ids
        ):
            raise ContractError("Durable contract record is invalid.", code=_ASSET_INVALID)
        seen.add(key)
        seen_schema_ids.add(schema_id)
    return value


@lru_cache(maxsize=1)
def public_contract_catalog() -> dict[str, Any]:
    """Load and structurally verify the accepted 1,575-surface contract."""
    value = _load_asset(PUBLIC_CONTRACT_ASSET)
    records = value.get("records")
    if (
        value.get("format") != "opencntx-public-contract"
        or value.get("format_version") != 1
        or value.get("surface_count") != 1575
        or not isinstance(records, list)
        or len(records) != 1575
    ):
        raise ContractError("Public contract catalog is invalid.", code=_ASSET_INVALID)
    ids: set[str] = set()
    for record in records:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("surface_id"), str)
            or record["surface_id"] in ids
            or not isinstance(record.get("public_identity"), dict)
            or not isinstance(record.get("contract_test_family"), str)
            or record.get("contract_status") != "CANDIDATE_EXECUTABLE"
            or not isinstance(record.get("test_id"), str)
            or "contract" not in record
            or not isinstance(record.get("baseline_identity_sha256"), str)
            or DIGEST_PATTERN.fullmatch(record["baseline_identity_sha256"]) is None
        ):
            raise ContractError("Public contract record is invalid.", code=_ASSET_INVALID)
        ids.add(record["surface_id"])
    return value


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unsupported"


def _contract_index() -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (record["format"], record["format_version"]): record
        for record in durable_contract_catalog()["records"]
    }


def validate_durable_metadata(value: object) -> dict[str, Any]:
    """Validate durable metadata for either a JSON or text-backed format."""
    if not isinstance(value, dict):
        raise ContractError("Durable record must be an object.", code=_RECORD_INVALID)
    format_name = value.get("format")
    version = value.get("format_version")
    if (
        not isinstance(format_name, str)
        or not isinstance(version, int)
        or isinstance(version, bool)
    ):
        raise ContractError("Durable discriminator is invalid.", code=_VERSION_UNSUPPORTED)
    contract = _contract_index().get((format_name, version))
    if contract is None:
        raise ContractError(
            f"Unsupported durable record format: {format_name} v{version}.",
            code=_VERSION_UNSUPPORTED,
        )
    required = contract.get("required_fields")
    optional = contract.get("optional_fields")
    field_types = contract.get("field_types")
    if (
        not isinstance(required, list)
        or not isinstance(optional, list)
        or not isinstance(field_types, dict)
    ):
        raise ContractError("Durable contract fields are invalid.", code=_ASSET_INVALID)
    keys = set(value)
    missing = sorted(set(required) - keys)
    extra = sorted(keys - set(required) - set(optional))
    if missing or extra:
        raise ContractError(
            f"Durable record field set differs; missing={missing}, extra={extra}.",
            code=_FIELDS_INVALID,
        )
    for field in sorted(keys):
        allowed = field_types.get(field)
        if not isinstance(allowed, list) or _json_type(value[field]) not in allowed:
            raise ContractError(
                f"Durable field has the wrong type: {field}.",
                code=_FIELD_TYPE_INVALID,
            )
    for relationship in contract.get("relationships", []):
        if not isinstance(relationship, dict) or relationship.get("kind") != "const":
            raise ContractError("Contract relationship is invalid.", code=_ASSET_INVALID)
        field = relationship.get("field")
        if value.get(field) != relationship.get("value"):
            raise ContractError(
                f"Durable relationship failed: {field}.",
                code=_RELATIONSHIP_INVALID,
            )
    return contract


def validate_durable_record(value: object) -> dict[str, Any]:
    """Validate one JSON durable record against its complete closed contract.

    The function never mutates *value*. Unknown formats and unknown major
    versions are rejected before any caller is allowed to write or migrate.
    """
    contract = validate_durable_metadata(value)
    if contract.get("encoding") != "json":
        raise ContractError("Durable record uses a non-JSON contract.", code=_ENCODING_INVALID)
    return contract


def durable_contract_records() -> tuple[dict[str, Any], ...]:
    """Return immutable caller copies of the 36 contract records."""
    return tuple(dict(item) for item in durable_contract_catalog()["records"])
