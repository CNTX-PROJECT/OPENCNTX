"""Shared R15 binding, not a host authenticator, executor or second state store.

A supervisor retains BoundGoal separately from its messages-only client. Merely
calling these Python APIs from arbitrary code does not establish OWNER authority.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .continuity import _digest, _fail, _value_digest, decide_finalization
from .human_interface import validate_intent_contract

FORMAT = "opencntx-goal-binding"
VERSION = 2
MAX_BYTES = 262_144
SHA = re.compile(r"[0-9a-f]{64}\Z")
OPERATIONS = frozenset({"READ_EXACT", "REPLACE_EXACT"})
ACTION_FIELDS = frozenset(
    {
        "outcome_id",
        "operation",
        "targets",
        "recursive",
        "protected_targets",
        "preconditions",
        "capability_ref",
    }
)


def _text(value: object, name: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _fail("goal_binding_invalid", f"{name} is not a nonempty canonical string.")
    if len(value) > maximum or any(ord(char) < 32 for char in value):
        raise _fail("goal_binding_invalid", f"{name} exceeds its text boundary.")
    return value


def _sha(value: object, name: str) -> str:
    text = _text(value, name, 64)
    if SHA.fullmatch(text) is None:
        raise _fail("goal_binding_invalid", f"{name} is not SHA256.")
    return text


def _path(value: object) -> str:
    text = _text(value, "relative_path")
    if "\\" in text or ":" in text or any(p in {"", ".", ".."} for p in text.split("/")):
        raise _fail("goal_binding_invalid", "Paths must be explicit portable relative names.")
    return text


def _unique(values: object, name: str, *, paths: bool = False) -> list[str]:
    if not isinstance(values, (list, tuple)) or len(values) > 50:
        raise _fail("goal_binding_invalid", f"{name} must be a bounded sequence.")
    result = [_path(v) if paths else _text(v, name, 120) for v in values]
    if len(result) != len(set(result)):
        raise _fail("goal_binding_invalid", f"{name} contains duplicates.")
    return result


def _canonical(value: object) -> str:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise _fail("goal_binding_invalid", "Binding must be bounded JSON.") from exc
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise _fail("goal_binding_invalid", "Binding exceeds its byte boundary.")
    return text


@dataclass(frozen=True)
class HostSource:
    """Metadata supplied by trusted host registration, never by the action client.

    A copied AI proposal keeps its role and derivation; a new explicit OWNER
    instruction needs a distinct host record. None yields UNKNOWN, not OWNER.
    """

    role: str
    reference: str
    content_sha256: str
    derived_from: str | None = None

    def payload(self) -> dict[str, object]:
        if self.role not in {"OWNER", "AI_PROPOSAL", "UNKNOWN"}:
            raise _fail("goal_binding_invalid", "Unsupported source role.")
        return {
            "role": self.role,
            "reference": _text(self.reference, "source_reference"),
            "content_sha256": _sha(self.content_sha256, "source_digest"),
            "derived_from": None
            if self.derived_from is None
            else _text(self.derived_from, "derived_from"),
        }


@dataclass(frozen=True)
class BoundGoal:
    """Supervisor-owned immutable expectation, not a serialized bearer token."""

    canonical_json: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def _capsule(value: Mapping[str, object]) -> dict[str, Any]:
    if type(value.get("format_version")) is not int or value.get("format_version") != 1:
        raise _fail("goal_binding_invalid", "Unsupported execution capsule version.")
    if decide_finalization(value)["decision"] == "RECONCILE_REQUIRED":
        raise _fail("goal_binding_invalid", "Execution capsule is invalid or stale.")
    return json.loads(_canonical(dict(value)))


def build_goal_binding(
    *,
    intent: Mapping[str, object],
    execution_capsule: Mapping[str, object],
    request_id: str,
    revision: int,
    parent_request_id: str | None,
    outcome_ids: Sequence[str],
    action: Mapping[str, object],
    evidence: Sequence[Mapping[str, object]] = (),
    source: HostSource | None = None,
    write_version: int = VERSION,
) -> BoundGoal:
    """Prepare a binding in the supervisor; does not execute or grant permission."""
    if type(write_version) is not int or write_version != VERSION:
        raise _fail("goal_binding_version", "New goal bindings require version 2.")
    if type(revision) is not int or revision < 1:
        raise _fail("goal_binding_invalid", "Request revision must be a positive integer.")
    if type(intent.get("format_version")) is not int:
        raise _fail("goal_binding_invalid", "Intent version must be an integer.")
    legacy = validate_intent_contract(intent)
    capsule = _capsule(execution_capsule)
    outcomes = _unique(outcome_ids, "outcomes")
    if not outcomes or set(action) != ACTION_FIELDS:
        raise _fail("goal_binding_invalid", "Outcomes or action fields differ.")
    targets = _unique(action["targets"], "targets", paths=True)
    protected = _unique(action["protected_targets"], "protected_targets", paths=True)
    if not targets or set(targets) & set(protected):
        raise _fail("goal_binding_invalid", "Targets are empty or explicitly protected.")
    selected_outcome = _text(action["outcome_id"], "outcome_id")
    selected_operation = _text(action["operation"], "operation")
    if selected_outcome not in outcomes or selected_operation not in OPERATIONS:
        raise _fail("goal_binding_invalid", "Action has no matching outcome/operation.")
    if action["recursive"] is not False:
        raise _fail("goal_binding_invalid", "This exact-target contract forbids recursion.")
    _text(action["capability_ref"], "capability_ref")
    preconditions = action["preconditions"]
    if not isinstance(preconditions, list) or len(preconditions) != len(targets):
        raise _fail("goal_binding_invalid", "Every target needs one precondition.")
    names = []
    for item in preconditions:
        if not isinstance(item, dict) or set(item) != {"target", "sha256", "identity_ref"}:
            raise _fail("goal_binding_invalid", "Precondition fields differ.")
        names.append(_path(item["target"]))
        _sha(item["sha256"], "target_digest")
        _text(item["identity_ref"], "identity_ref")
    if names != targets:
        raise _fail("goal_binding_invalid", "Preconditions differ from the ordered targets.")
    if not isinstance(evidence, (list, tuple)) or len(evidence) > 50:
        raise _fail("goal_binding_invalid", "Evidence must be bounded.")
    seen = set()
    for item in evidence:
        if not isinstance(item, Mapping) or set(item) != {"outcome_id", "reference", "sha256"}:
            raise _fail("goal_binding_invalid", "Evidence fields differ.")
        if item["outcome_id"] not in outcomes:
            raise _fail("goal_binding_invalid", "Evidence refers to another outcome.")
        key = (_text(item["outcome_id"], "outcome_id"), _path(item["reference"]))
        if key in seen:
            raise _fail("goal_binding_invalid", "Duplicate outcome evidence reference.")
        seen.add(key)
        _sha(item["sha256"], "evidence_digest")
    if source is not None and not isinstance(source, HostSource):
        raise _fail("goal_binding_invalid", "Source must come from host metadata.")
    if source is not None and source.content_sha256 != _digest(
        legacy["human_intent"].encode("utf-8")
    ):
        raise _fail("goal_binding_invalid", "Host source does not bind the original intent text.")
    source_value = (
        {"role": "UNKNOWN", "reference": None, "content_sha256": None, "derived_from": None}
        if source is None
        else source.payload()
    )
    identifier = _text(request_id, "request_id", 120)
    parent = (
        None if parent_request_id is None else _text(parent_request_id, "parent_request_id", 120)
    )
    if parent == identifier:
        raise _fail("goal_binding_invalid", "A request cannot be its own parent.")
    value = {
        "format": FORMAT,
        "format_version": VERSION,
        "request": {
            "id": identifier,
            "revision": revision,
            "parent_id": parent,
            "outcome_ids": outcomes,
            "source": source_value,
        },
        "intent_v1": legacy,
        "execution_capsule_v1": capsule,
        "action": dict(action),
        "evidence": list(evidence),
        "execution": "NOT_PERFORMED",
        "authority_granted": False,
    }
    # Freeze nested caller-owned data too, not merely the outer dataclass.
    frozen = json.loads(_canonical(value))
    return BoundGoal(_canonical(frozen | {"binding_digest": _value_digest(frozen)}))


def validate_goal_binding(
    value: Mapping[str, object],
    *,
    expected: BoundGoal,
    current_execution_capsule: Mapping[str, object],
) -> dict[str, Any]:
    """Reject even rehashed mutations against the independent supervisor binding."""
    candidate = _canonical(dict(value))
    if candidate != expected.canonical_json:
        raise _fail("goal_binding_mismatch", "Payload differs from the retained host binding.")
    accepted = expected.payload()
    if accepted["execution_capsule_v1"] != _capsule(current_execution_capsule):
        raise _fail("goal_binding_stale", "Execution state changed; rebind before acting.")
    return accepted


def read_legacy_intent(value: Mapping[str, object]) -> dict[str, Any]:
    """Read v1 unchanged; reading never implies a v2 or ENFORCED capability."""
    if type(value.get("format_version")) is not int or value.get("format_version") != 1:
        raise _fail("goal_binding_version", "Unsupported legacy intent version.")
    return validate_intent_contract(value)
