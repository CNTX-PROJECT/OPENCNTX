from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import re
import tomllib
import unittest
import uuid
from pathlib import Path

from opencntx.cli import build_parser
from opencntx.contracts import (
    ContractError,
    durable_contract_catalog,
    public_contract_catalog,
    schema_identifier,
    validate_durable_metadata,
    validate_durable_record,
)
from opencntx.lifecycle import schema_assets

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "v0.3.0"
SCHEMAS = ROOT / "src" / "opencntx" / "schemas"
EXPECTED_COUNTS = {
    "CLI_ARGUMENT": 210,
    "CLI_ROUTE": 113,
    "CONFIG_FIELD": 101,
    "DURABLE_FORMAT": 36,
    "ERROR_CODE": 273,
    "EXIT_CODE": 8,
    "MACHINE_OUTPUT": 37,
    "PUBLIC_DOC_CLAIM": 673,
    "PYTHON_SYMBOL": 3,
    "SCHEMA_OR_VALIDATOR": 113,
    "SUPPORT_CLAIM": 8,
}


def _simple_scalar(value: str) -> object:
    if value.isdigit() and len(value) < 16:
        return int(value)
    return value


def _markdown_metadata(content: bytes) -> dict[str, object]:
    text = content.decode("utf-8")
    if text.startswith("+++"):
        _, frontmatter, _ = text.split("+++", 2)
        value = tomllib.loads(frontmatter)
        return dict(value)
    if text.startswith("<!-- opencntx-task-view\n"):
        header = text.split("-->\n", 1)[0].splitlines()[1:]
    else:
        marker = "---\n"
        start = text.index(marker) + len(marker)
        end = text.index("\n---\n", start)
        header = text[start:end].splitlines()
    result: dict[str, object] = {}
    for line in header:
        key, raw = line.split(": ", 1)
        result[key] = _simple_scalar(raw)
    return result


def _action_contract(action: argparse.Action) -> dict[str, object]:
    action_type = action.type
    return {
        "choices": list(action.choices) if action.choices is not None else [],
        "default": "SUPPRESS" if action.default == argparse.SUPPRESS else action.default,
        "dest": action.dest,
        "nargs": action.nargs,
        "option_strings": action.option_strings,
        "required": action.required,
        "type": getattr(action_type, "__name__", "str"),
    }


def _parser_contract() -> tuple[set[str], dict[tuple[str, str, str], dict[str, object]]]:
    routes: set[str] = set()
    arguments: dict[tuple[str, str, str], dict[str, object]] = {}

    def walk(parser: argparse.ArgumentParser, parts: tuple[str, ...]) -> None:
        route = " ".join(parts)
        routes.update((route, f"{route} --help"))
        for action in parser._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    walk(child, (*parts, name))
                continue
            variant = action.option_strings[0] if action.option_strings else "POSITIONAL"
            arguments[(route, action.dest, variant)] = _action_contract(action)

    walk(build_parser(), ("opencntx",))
    routes.add("opencntx --version")
    return routes, arguments


class PublicSurfaceContractTests(unittest.TestCase):
    def test_exact_accepted_surface_set_is_finite_and_classified(self) -> None:
        catalog = public_contract_catalog()
        self.assertEqual(1575, catalog["surface_count"])
        self.assertEqual(EXPECTED_COUNTS, catalog["counts_by_kind"])
        records = catalog["records"]
        self.assertEqual(1575, len({item["surface_id"] for item in records}))
        for item in records:
            self.assertEqual(item["kind"], item["public_identity"]["kind"])
            self.assertTrue(item["stable_target"])
            self.assertTrue(item["contract_test_family"])
            self.assertEqual("CANDIDATE_EXECUTABLE", item["contract_status"])
            self.assertTrue(item["test_id"].startswith("tests.test_contracts."))
            self.assertIn("contract", item)

    def test_catalog_contract_payload_is_complete(self) -> None:
        records = public_contract_catalog()["records"]
        expected_kinds = set(EXPECTED_COUNTS)
        self.assertEqual(expected_kinds, {item["kind"] for item in records})
        for item in records:
            with self.subTest(surface_id=item["surface_id"]):
                self.assertTrue(item["baseline_identity_sha256"])
                self.assertTrue(item["contract"])
                method_name = item["test_id"].rsplit(".", 1)[-1]
                test_class = (
                    DurableFormatContractTests
                    if ".DurableFormatContractTests." in item["test_id"]
                    else PublicSurfaceContractTests
                )
                self.assertTrue(hasattr(test_class, method_name), item["test_id"])

    def test_cli_routes_and_arguments_equal_the_live_parser_contract(self) -> None:
        records = public_contract_catalog()["records"]
        expected_routes = {
            item["public_identity"]["canonical_name"]
            for item in records
            if item["kind"] == "CLI_ROUTE"
        }
        expected_arguments = {
            (
                item["public_identity"]["parent_identity"],
                item["public_identity"]["canonical_name"],
                item["public_identity"]["variant"],
            ): item["contract"]
            for item in records
            if item["kind"] == "CLI_ARGUMENT"
        }
        routes, arguments = _parser_contract()
        self.assertTrue(expected_routes.issubset(routes))
        self.assertTrue(all(route.startswith("opencntx flow") for route in routes - expected_routes))
        self.assertTrue(set(expected_arguments).issubset(arguments))
        self.assertTrue(
            all(identity[0].startswith("opencntx flow") for identity in set(arguments) - set(expected_arguments))
        )
        for identity, expected in expected_arguments.items():
            with self.subTest(argument=identity):
                self.assertEqual(expected, arguments[identity])

    def test_public_document_contract_paths_exist(self) -> None:
        records = public_contract_catalog()["records"]
        paths = {
            item["public_identity"]["parent_identity"]
            for item in records
            if item["kind"] == "PUBLIC_DOC_CLAIM"
        }
        self.assertEqual(26, len(paths))
        for relative in paths:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_error_contract_matches_runtime_error_id_literals(self) -> None:
        records = public_contract_catalog()["records"]
        expected = {
            item["public_identity"]["canonical_name"]
            for item in records
            if item["kind"] == "ERROR_CODE"
        }
        observed: set[str] = set()
        pattern = re.compile(r'code=["\']([a-z][a-z0-9_]*)["\']')
        for path in sorted((ROOT / "src" / "opencntx").glob("*.py")):
            if path.name == "contracts.py":
                continue
            observed.update(pattern.findall(path.read_text(encoding="utf-8")))
        self.assertEqual(expected, observed)


class DurableFormatContractTests(unittest.TestCase):
    def test_all_36_contracts_have_complete_registered_boundaries(self) -> None:
        records = durable_contract_catalog()["records"]
        for item in records:
            with self.subTest(format=item["format"]):
                self.assertTrue(item["format_id"].startswith("FMT-"))
                self.assertTrue(item["producer_surface_ids"])
                self.assertTrue(item["reader_surface_ids"])
                self.assertTrue(item["validator_surface_ids"])
                self.assertEqual(
                    set(item["required_fields"]) | set(item["optional_fields"]),
                    {field["path"] for field in item["field_contracts"]},
                )
                for field in item["field_contracts"]:
                    self.assertEqual(field["path"] in item["required_fields"], field["required"])
                    self.assertEqual(
                        "null" in field["types"],
                        field["nullable"],
                    )
                self.assertEqual([], item["conditional_requirements"])
                self.assertEqual(
                    "EXACT_FILE_BYTES", item["canonicalization"]["fixture_digest_boundary"]
                )
                self.assertEqual("FIXTURE_ACCEPTED_READ_ONLY", item["read_claim"])
                self.assertEqual("FIXTURE_SHA256_AND_CONTRACT_MATCH", item["verify_claim"])
                self.assertEqual("NOT_REQUIRED_FOR_BOUND_V030_FIXTURE", item["migration_claim"])
                self.assertEqual("NOT_APPLICABLE_NO_FIXTURE_WRITE", item["rollback_claim"])

    def test_all_36_contracts_have_unique_deterministic_schema_ids(self) -> None:
        records = durable_contract_catalog()["records"]
        self.assertEqual(36, len(records))
        self.assertEqual(36, len({item["format"] for item in records}))
        self.assertEqual(36, len({item["schema_id"] for item in records}))
        for item in records:
            identifier = item["schema_id"]
            self.assertEqual(schema_identifier(item["format"], 1), identifier)
            self.assertEqual("urn", identifier.split(":", 1)[0])
            uuid.UUID(identifier.removeprefix("urn:uuid:"))
            self.assertEqual("REJECT", item["unknown_fields"])
            self.assertEqual("REJECT_BEFORE_WRITE", item["unknown_major"])
            self.assertEqual(
                set(item["required_fields"]) | set(item["optional_fields"]),
                set(item["field_types"]),
            )

    def test_v030_fixture_manifest_is_exact_and_read_only(self) -> None:
        manifest_path = FIXTURE_ROOT / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        self.assertEqual("v0.3.0", manifest["source_release"])
        self.assertEqual(36, manifest["fixture_count"])
        self.assertEqual(36, len(manifest["records"]))
        self.assertEqual(2, manifest["composed_example_count"])
        contract_by_format = {
            item["format"]: item for item in durable_contract_catalog()["records"]
        }
        for item in manifest["records"]:
            path = FIXTURE_ROOT / "durable-records" / item["path"]
            before = path.read_bytes()
            self.assertEqual(item["bytes"], len(before))
            self.assertEqual(item["sha256"], hashlib.sha256(before).hexdigest())
            payload = gzip.decompress(before)
            self.assertEqual(item["payload_bytes"], len(payload))
            self.assertEqual(item["payload_sha256"], hashlib.sha256(payload).hexdigest())
            contract = contract_by_format[item["format"]]
            self.assertEqual(contract["fixture"]["sha256"], item["sha256"])
            self.assertEqual(contract["schema_id"], item["schema_id"])
            self.assertEqual("ACCEPT", item["expected_read"])
            self.assertEqual("SHA256_AND_CONTRACT_MATCH", item["expected_verify"])
            self.assertTrue(item["read_only"])
            if contract["encoding"] == "json":
                metadata = json.loads(payload.decode("ascii"))
                self.assertEqual(contract, validate_durable_record(metadata))
            else:
                metadata = _markdown_metadata(payload)
                self.assertEqual(contract, validate_durable_metadata(metadata))
            self.assertEqual(before, path.read_bytes())

        for item in manifest["composed_examples"]:
            path = FIXTURE_ROOT / item["path"]
            before = path.read_bytes()
            self.assertEqual(item["sha256"], hashlib.sha256(before).hexdigest())
            payload = gzip.decompress(before)
            self.assertEqual(item["payload_sha256"], hashlib.sha256(payload).hexdigest())
            example = json.loads(payload.decode("ascii"))
            self.assertEqual("opencntx-v030-composed-fixture", example["format"])
            self.assertEqual(item["member_count"], len(example["members"]))
            self.assertTrue(example["relationships"])
            for member in example["members"]:
                member_path = path.parent / member["path"]
                self.assertEqual(
                    member["sha256"],
                    hashlib.sha256(member_path.read_bytes()).hexdigest(),
                )
            self.assertEqual(before, path.read_bytes())

    def test_every_unknown_major_fails_closed_without_mutation(self) -> None:
        for contract in durable_contract_catalog()["records"]:
            value = {
                field: (
                    contract["format"]
                    if field == "format"
                    else 99
                    if field == "format_version"
                    else None
                )
                for field in contract["required_fields"]
            }
            before = copy.deepcopy(value)
            with self.subTest(format=contract["format"]):
                with self.assertRaises(ContractError) as context:
                    validate_durable_metadata(value)
                self.assertEqual("contract_version_unsupported", context.exception.code)
                self.assertEqual(before, value)

    def test_manifest_accepts_existing_security_object_and_rejects_other_fields(self) -> None:
        manifest = {
            "format": "opencntx-manifest",
            "format_version": 1,
            "task": {},
            "selection": {},
            "package": {},
            "sources": [],
            "excluded": [],
            "ignored": [],
            "security": {},
        }
        contract = validate_durable_record(manifest)
        self.assertEqual(["security"], contract["optional_fields"])
        self.assertEqual(["object"], contract["field_types"]["security"])

        unknown = {**manifest, "unexpected": True}
        with self.assertRaises(ContractError) as context:
            validate_durable_record(unknown)
        self.assertEqual("contract_fields_invalid", context.exception.code)

        wrong_type = {**manifest, "security": []}
        with self.assertRaises(ContractError) as type_context:
            validate_durable_record(wrong_type)
        self.assertEqual("contract_field_type_invalid", type_context.exception.code)

    def test_schema_bundle_contains_contracts_and_no_unmanaged_domain(self) -> None:
        assets = schema_assets()
        self.assertEqual(
            {
                "compatibility-matrix-v1.json",
                "durable-format-contracts-v1.json",
                "durable-records-v1.schema.json",
                "lifecycle-plan-v1.schema.json",
                "lifecycle-state-v1.schema.json",
                "public-contract-v1.json",
            },
            set(assets),
        )
        for name, content in assets.items():
            self.assertNotIn(b"opencntx.org", content, name)
            value = json.loads(content.decode("ascii"))
            self.assertTrue(value["$id"].startswith("urn:uuid:"), name)
        central_ids = {json.loads(content.decode("ascii"))["$id"] for content in assets.values()}
        durable_ids = {item["schema_id"] for item in durable_contract_catalog()["records"]}
        self.assertEqual(6, len(central_ids))
        self.assertTrue(central_ids.isdisjoint(durable_ids))


if __name__ == "__main__":
    unittest.main()
