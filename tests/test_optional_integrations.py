from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from opencntx.optional_integrations import (
    approve_companion_plan,
    build_companion_plan,
    build_continuity_sync_batch,
    build_continuity_target,
    build_onboarding_profile,
    build_start_authority_choice,
    resolve_start_authority_choice,
)
from opencntx.workspace import WorkspaceError

ROOT = Path(__file__).resolve().parents[1]


def onboarding(*, all_projects: bool = False, existing: bool = False) -> dict[str, object]:
    return build_onboarding_profile(
        project_id="PROJECT-A",
        project_scope="ALL_REGISTERED_PROJECTS" if all_projects else "CURRENT_PROJECT",
        registered_projects=["PROJECT-A", "PROJECT-B"],
        selected_tools=["TOOL-A", "TOOL-B"],
        existing_method_detected=existing,
        method_choice="PRESERVE_AND_LINK" if existing else "NONE",
    )


def start_choice(*, interactive: bool, started: bool = False) -> dict[str, object]:
    return build_start_authority_choice(
        roadmap_id="R11",
        roadmap_revision="REV-7",
        current_assignment="R11-07",
        remaining_assignments=["R11-07", "R11-08", "R11-09"],
        roadmap_started=started,
        host_capabilities=["INTERACTIVE_CHOICE"] if interactive else [],
        language="nl",
    )


def resolve(choice: dict[str, object], submitted: str) -> dict[str, object]:
    return resolve_start_authority_choice(
        choice,
        expected_choice_digest=str(choice["choice_digest"]),
        expected_roadmap_revision="REV-7",
        expected_current_assignment="R11-07",
        submitted_value=submitted,
    )


class OptionalIntegrationTests(unittest.TestCase):
    def test_start_choice_has_exactly_two_capability_adaptive_options(self) -> None:
        interactive = start_choice(interactive=True)
        fallback = start_choice(interactive=False)
        self.assertEqual(interactive["presentation"], "INTERACTIVE_CHOICE")
        self.assertEqual(fallback["presentation"], "COPY_COMMANDS")
        self.assertEqual(len(interactive["choices"]), 2)
        self.assertEqual(
            [item["choice_id"] for item in interactive["choices"]],
            ["CURRENT_ASSIGNMENT", "REMAINING_ROADMAP"],
        )
        self.assertFalse(interactive["authority_granted"])

    def test_button_and_cli_routes_produce_identical_authority(self) -> None:
        button = resolve(start_choice(interactive=True), "REMAINING_ROADMAP")
        command = resolve(start_choice(interactive=False), "AUTO PILOT R11")
        self.assertEqual(button, command)
        self.assertEqual(button["approved_assignments"], ["R11-07", "R11-08", "R11-09"])
        self.assertFalse(button["release_authorized"])
        self.assertFalse(button["publication_authorized"])

    def test_current_assignment_scope_stops_at_current_leaf(self) -> None:
        authority = resolve(start_choice(interactive=False), "START R11-07")
        self.assertEqual(authority["scope"], "CURRENT_ASSIGNMENT")
        self.assertEqual(authority["approved_assignments"], ["R11-07"])

    def test_started_roadmap_uses_remaining_label(self) -> None:
        choice = start_choice(interactive=False, started=True)
        self.assertIn("resterende roadmap", choice["question"].lower())
        self.assertEqual(choice["choices"][1]["label"], "Resterende roadmap")

    def test_stale_ambiguous_or_unknown_start_selection_is_rejected(self) -> None:
        choice = start_choice(interactive=False)
        with self.assertRaisesRegex(WorkspaceError, "binding changed"):
            resolve_start_authority_choice(
                choice,
                expected_choice_digest=str(choice["choice_digest"]),
                expected_roadmap_revision="REV-8",
                expected_current_assignment="R11-07",
                submitted_value="AUTO PILOT R11",
            )
        with self.assertRaisesRegex(WorkspaceError, "one non-empty line"):
            resolve(choice, "START R11-07\nAUTO PILOT R11")
        altered = copy.deepcopy(choice)
        altered["roadmap_revision"] = "REV-8"
        with self.assertRaisesRegex(WorkspaceError, "digest differs"):
            resolve(altered, "AUTO PILOT R11")

    def test_onboarding_preserves_current_or_all_registered_scope(self) -> None:
        current = onboarding(existing=True)
        all_projects = onboarding(all_projects=True)
        self.assertEqual(current["selected_projects"], ["PROJECT-A"])
        self.assertEqual(all_projects["selected_projects"], ["PROJECT-A", "PROJECT-B"])
        self.assertTrue(all_projects["future_registered_projects"])
        self.assertEqual(current["method_choice"], "PRESERVE_AND_LINK")
        self.assertEqual(current["writes"], [])

    def test_companion_is_optional_and_compatible_installation_is_reused(self) -> None:
        declined = build_companion_plan(
            onboarding=onboarding(),
            requested=False,
            adapter_id="SPEC-ADAPTER",
            detection={"state": "ABSENT", "provenance": "none"},
            target_version="1.0",
        )
        self.assertEqual(declined["status"], "DECLINED")
        self.assertEqual(declined["proposed_writes"], [])
        compatible = build_companion_plan(
            onboarding=onboarding(),
            requested=True,
            adapter_id="SPEC-ADAPTER",
            detection={
                "state": "COMPATIBLE",
                "provenance": "managed-runtime",
                "installed_version": "1.0",
                "projects_initialized": True,
            },
            target_version="1.0",
        )
        self.assertEqual(compatible["action"], "VALIDATE")
        self.assertFalse(compatible["approval_required"])
        receipt = approve_companion_plan(
            compatible,
            expected_plan_digest=str(compatible["plan_digest"]),
            approved=False,
        )
        self.assertEqual(receipt["status"], "NO_MUTATION_REQUIRED")

    def test_companion_mutation_needs_exact_approval_and_ambiguity_blocks(self) -> None:
        install = build_companion_plan(
            onboarding=onboarding(all_projects=True),
            requested=True,
            adapter_id="SPEC-ADAPTER",
            detection={"state": "ABSENT", "provenance": "not-found"},
            target_version="1.0",
        )
        self.assertTrue(install["approval_required"])
        declined = approve_companion_plan(
            install,
            expected_plan_digest=str(install["plan_digest"]),
            approved=False,
        )
        self.assertEqual(declined["status"], "DECLINED")
        ambiguous = build_companion_plan(
            onboarding=onboarding(),
            requested=True,
            adapter_id="SPEC-ADAPTER",
            detection={"state": "AMBIGUOUS", "provenance": "two-runtimes"},
            target_version="1.0",
        )
        with self.assertRaisesRegex(WorkspaceError, "cannot be approved"):
            approve_companion_plan(
                ambiguous,
                expected_plan_digest=str(ambiguous["plan_digest"]),
                approved=True,
            )

    def test_continuity_target_defaults_off_and_enforces_project_isolation(self) -> None:
        disabled = build_continuity_target(project_id="PROJECT-A", opt_in=False)
        self.assertFalse(disabled["enabled"])
        self.assertIsNone(disabled["target_id"])
        target = build_continuity_target(
            project_id="PROJECT-A",
            opt_in=True,
            target_id="TARGET-ONE",
            target_kind="SYNCED_FOLDER",
            allowed_content=["STATUS", "ROADMAP"],
        )
        with self.assertRaisesRegex(WorkspaceError, "another project"):
            build_continuity_sync_batch(
                target,
                expected_target_digest=str(target["target_digest"]),
                project_id="PROJECT-B",
                changes=[],
                online=True,
                conflict=False,
            )

    def test_sync_batch_filters_secrets_and_handles_offline_and_conflict(self) -> None:
        target = build_continuity_target(
            project_id="PROJECT-A",
            opt_in=True,
            target_id="TARGET-ONE",
            target_kind="API_ADAPTER",
            allowed_content=["STATUS"],
            conflict_policy="CREATE_CONFLICT_COPY",
        )
        changes = [
            {
                "change_id": "CHANGE-1",
                "content_class": "STATUS",
                "sha256": "a" * 64,
                "bytes": 100,
                "contains_secret": False,
            },
            {
                "change_id": "CHANGE-2",
                "content_class": "STATUS",
                "sha256": "b" * 64,
                "bytes": 10,
                "contains_secret": True,
            },
            {
                "change_id": "CHANGE-3",
                "content_class": "RAW_LOG",
                "sha256": "c" * 64,
                "bytes": 200,
                "contains_secret": False,
            },
        ]
        offline = build_continuity_sync_batch(
            target,
            expected_target_digest=str(target["target_digest"]),
            project_id="PROJECT-A",
            changes=changes,
            online=False,
            conflict=False,
        )
        self.assertEqual(offline["status"], "QUEUED_OFFLINE")
        self.assertEqual([item["change_id"] for item in offline["included"]], ["CHANGE-1"])
        self.assertEqual(
            [item["reason"] for item in offline["excluded"]],
            ["SECRET_FILTERED", "CONTENT_CLASS_BLOCKED"],
        )
        conflict = build_continuity_sync_batch(
            target,
            expected_target_digest=str(target["target_digest"]),
            project_id="PROJECT-A",
            changes=changes[:1],
            online=True,
            conflict=True,
        )
        self.assertEqual(conflict["status"], "CONFLICT")
        self.assertEqual(conflict["external_writes_performed"], 0)

    def test_new_schemas_are_valid_json_and_listed_in_continuity_contract(self) -> None:
        schema_names = {
            "start-authority-choice-v1.schema.json",
            "start-authority-v1.schema.json",
            "integration-onboarding-v1.schema.json",
            "specification-companion-plan-v1.schema.json",
            "integration-approval-v1.schema.json",
            "continuity-target-v1.schema.json",
            "continuity-sync-batch-v1.schema.json",
        }
        contract = json.loads(
            (ROOT / "src/opencntx/schemas/continuity-contract-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(schema_names.issubset(set(contract["schemas"])))
        for name in schema_names:
            with self.subTest(schema=name):
                schema = json.loads(
                    (ROOT / "src/opencntx/schemas" / name).read_text(encoding="utf-8")
                )
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")


if __name__ == "__main__":
    unittest.main()
