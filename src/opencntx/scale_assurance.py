"""No-network scale planning, resumable acquisition state, and adaptive assurance."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

from .continuity import _fail, _identifier, _one_line, _value_digest, _write_atomic, _writer_lock

SCALE_FORMAT = "opencntx-scale-plan"
ASSURANCE_FORMAT = "opencntx-assurance-plan"
QUEUE_STATUSES = frozenset(
    {"PENDING", "IN_FLIGHT", "FETCHED", "NOT_FOUND", "RETRY_AFTER", "REVIEW_REQUIRED", "COMPLETE"}
)
RISK_LEVELS = ("LIGHT", "STANDARD", "CRITICAL")


def _pretty(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _fail("continuity_store_invalid", f"{name} is invalid.")
    return value


def _scale_root(project_root: Path) -> Path:
    root = project_root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise _fail("continuity_root_invalid", "Scale project root is invalid.")
    return root / ".opencntx" / "scale"


def _validate_request_classes(values: Sequence[Mapping[str, object]]) -> list[dict[str, Any]]:
    required = {
        "name",
        "scope",
        "official_interface",
        "endpoint_proven",
        "cost_per_request",
        "batch_size",
        "payload_limit_bytes",
        "ttl_seconds",
        "storage_bytes_per_item",
    }
    records = []
    names: set[str] = set()
    for item in values:
        if set(item) != required or item.get("scope") not in {"BASIC", "DETAIL"}:
            raise _fail("continuity_store_invalid", "Scale request class differs from the contract.")
        name = _identifier(item["name"], "request_class.name")
        if name in names:
            raise _fail("continuity_store_invalid", "Scale request class names must be unique.")
        names.add(name)
        record = {
            "name": name,
            "scope": item["scope"],
            "official_interface": item["official_interface"] is True,
            "endpoint_proven": item["endpoint_proven"] is True,
            "cost_per_request": _integer(item["cost_per_request"], "request cost", minimum=1),
            "batch_size": _integer(item["batch_size"], "batch size", minimum=1),
            "payload_limit_bytes": _integer(
                item["payload_limit_bytes"], "payload limit", minimum=1
            ),
            "ttl_seconds": _integer(item["ttl_seconds"], "TTL", minimum=1),
            "storage_bytes_per_item": _integer(
                item["storage_bytes_per_item"], "storage projection", minimum=1
            ),
        }
        records.append(record)
    if {item["scope"] for item in records} != {"BASIC", "DETAIL"}:
        raise _fail("continuity_store_invalid", "Basic and detail request classes are required.")
    return sorted(records, key=lambda item: item["name"])


def build_scale_plan(
    *,
    project_id: str,
    identity_counts: Mapping[str, object],
    pilot_count: int,
    selective_depth_basis_points: int,
    request_classes: Sequence[Mapping[str, object]],
    quota_windows: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    """Build an exact no-network scale-up projection."""
    identity_fields = {
        "total_local",
        "unique_external",
        "missing_external",
        "invalid_external",
        "duplicate_links",
        "fresh_cached",
    }
    if set(identity_counts) != identity_fields:
        raise _fail("continuity_store_invalid", "Scale identity counts differ from the contract.")
    counts = {name: _integer(identity_counts[name], name) for name in identity_fields}
    if (
        counts["unique_external"]
        + counts["missing_external"]
        + counts["invalid_external"]
        + counts["duplicate_links"]
        != counts["total_local"]
        or counts["fresh_cached"] > counts["unique_external"]
    ):
        raise _fail("continuity_store_invalid", "Scale identity accounting does not balance.")
    pilot = _integer(pilot_count, "pilot_count")
    depth_points = _integer(selective_depth_basis_points, "depth basis points")
    if pilot > counts["unique_external"] or depth_points > 10_000:
        raise _fail("continuity_store_invalid", "Scale coverage exceeds its population.")
    classes = _validate_request_classes(request_classes)
    quota_records: list[dict[str, Any]] = []
    for window in quota_windows:
        if set(window) != {"name", "remaining", "reserve", "reset_at"}:
            raise _fail("continuity_store_invalid", "Quota window differs from the contract.")
        remaining = _integer(window["remaining"], "quota remaining")
        reserve = _integer(window["reserve"], "quota reserve")
        if reserve > remaining:
            raise _fail("continuity_store_invalid", "Quota reserve exceeds remaining quota.")
        quota_records.append(
            {
                "name": _identifier(window["name"], "quota.name"),
                "remaining": remaining,
                "reserve": reserve,
                "usable": remaining - reserve,
                "reset_at": _one_line(window["reset_at"], "quota.reset_at", 80),
            }
        )
    fetchable = counts["unique_external"] - counts["fresh_cached"]
    depth_items = math.ceil(counts["unique_external"] * depth_points / 10_000)
    request_projection = []
    projected_requests = 0
    projected_storage = 0
    for item in classes:
        item_count = fetchable if item["scope"] == "BASIC" else depth_items
        requests = math.ceil(item_count / item["batch_size"]) * item["cost_per_request"]
        storage = item_count * item["storage_bytes_per_item"]
        projected_requests += requests
        projected_storage += storage
        request_projection.append(
            {
                "name": item["name"],
                "scope": item["scope"],
                "item_count": item_count,
                "requests": requests,
                "storage_bytes": storage,
                "batch_size": item["batch_size"],
                "payload_limit_bytes": item["payload_limit_bytes"],
                "ttl_seconds": item["ttl_seconds"],
                "official_interface": item["official_interface"],
                "endpoint_proven": item["endpoint_proven"],
            }
        )
    interfaces_ready = all(
        item["official_interface"] and item["endpoint_proven"] for item in classes
    )
    quota_capacity = min((item["usable"] for item in quota_records), default=0)
    quota_ready = projected_requests <= quota_capacity
    target = counts["total_local"]
    gates = sorted({value for value in (0, 10, 100, 1_000, target) if value <= target})
    if target not in gates:
        gates.append(target)
    status = "READY" if interfaces_ready and quota_ready else "BLOCKED"
    pilot_status = "TARGET_PROVEN" if target == 0 or pilot == target else "PILOT_ONLY"
    basis = {
        "format": SCALE_FORMAT,
        "format_version": 1,
        "project_id": _identifier(project_id, "project_id"),
        "identity_counts": counts,
        "pilot_count": pilot,
        "target_count": target,
        "pilot_ratio": {"numerator": pilot, "denominator": target},
        "pilot_status": pilot_status,
        "basic_coverage_target": counts["unique_external"],
        "selective_depth_basis_points": depth_points,
        "selective_depth_target": depth_items,
        "review_required_count": counts["missing_external"] + counts["invalid_external"],
        "request_classes": classes,
        "request_projection": request_projection,
        "worst_case_requests": projected_requests,
        "projected_storage_bytes": projected_storage,
        "quota_windows": sorted(quota_records, key=lambda item: str(item["name"])),
        "quota_capacity": quota_capacity,
        "scale_gates": gates,
        "status": status,
        "blockers": [
            item
            for item, active in (
                ("OFFICIAL_INTERFACE_PROOF_REQUIRED", not interfaces_ready),
                ("QUOTA_RESERVE_WOULD_BE_CROSSED", not quota_ready),
            )
            if active
        ],
        "network_requests_performed": 0,
    }
    return basis | {"plan_digest": _value_digest(basis)}


def _validate_scale_plan(plan: Mapping[str, object]) -> dict[str, Any]:
    basis = {key: item for key, item in plan.items() if key != "plan_digest"}
    if (
        plan.get("format") != SCALE_FORMAT
        or plan.get("format_version") != 1
        or plan.get("network_requests_performed") != 0
        or plan.get("plan_digest") != _value_digest(basis)
    ):
        raise _fail("continuity_store_invalid", "Scale plan is invalid or drifted.")
    return dict(plan)


def initialize_acquisition_queue(
    project_root: Path,
    *,
    plan: Mapping[str, object],
    identities: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    """Create a compact durable local queue without making any request."""
    value = _validate_scale_plan(plan)
    if value["status"] != "READY":
        raise _fail("continuity_store_invalid", "Blocked scale plan cannot create a queue.")
    expected = {"local_id", "external_id", "fingerprint", "fresh"}
    prepared = []
    external_ids: set[str] = set()
    for item in identities:
        if set(item) != expected or not isinstance(item.get("fresh"), bool):
            raise _fail("continuity_store_invalid", "Scale identity differs from the contract.")
        local_id = _identifier(item["local_id"], "local_id")
        external = item["external_id"]
        if external is not None:
            external = _identifier(external, "external_id")
            if external in external_ids:
                raise _fail("continuity_store_invalid", "Duplicate external identity was rejected.")
            external_ids.add(external)
        status = "REVIEW_REQUIRED" if external is None else "FETCHED" if item["fresh"] else "PENDING"
        prepared.append(
            (
                local_id,
                external,
                _one_line(item["fingerprint"], "fingerprint", 128),
                status,
                None,
                None,
                None,
                0,
            )
        )
    counts = value["identity_counts"]
    if len(prepared) != counts["total_local"] or len(external_ids) != counts["unique_external"]:
        raise _fail("continuity_store_invalid", "Queue identities differ from scale accounting.")
    root = _scale_root(project_root)
    database = root / f"queue-{value['plan_digest'][:24]}.sqlite"
    root.mkdir(parents=True, exist_ok=True)
    with _writer_lock(root / ".writer.lock"):
        if database.exists():
            return acquisition_queue_status(project_root, plan_digest=str(value["plan_digest"]))
        temporary = database.with_suffix(".building.sqlite")
        try:
            with closing(sqlite3.connect(temporary)) as connection:
                connection.execute(
                    "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE items (local_id TEXT PRIMARY KEY, external_id TEXT UNIQUE, "
                    "fingerprint TEXT NOT NULL, status TEXT NOT NULL, batch_id TEXT, "
                    "lease_expires INTEGER, response_hash TEXT, attempts INTEGER NOT NULL)"
                )
                connection.execute("CREATE INDEX items_status ON items(status)")
                connection.executemany("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?)", prepared)
                connection.executemany(
                    "INSERT INTO metadata VALUES (?, ?)",
                    [("plan_digest", value["plan_digest"]), ("revision", "0")],
                )
                connection.commit()
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise _fail("continuity_store_invalid", "Scale queue integrity check failed.")
            temporary.replace(database)
        finally:
            temporary.unlink(missing_ok=True)
        _write_atomic(root / f"plan-{value['plan_digest'][:24]}.json", _pretty(value))
    return acquisition_queue_status(project_root, plan_digest=str(value["plan_digest"]))


def _queue_path(project_root: Path, plan_digest: str) -> Path:
    if len(plan_digest) != 64:
        raise _fail("continuity_store_invalid", "Scale plan digest is invalid.")
    return _scale_root(project_root) / f"queue-{plan_digest[:24]}.sqlite"


def acquisition_queue_status(project_root: Path, *, plan_digest: str) -> dict[str, Any]:
    database = _queue_path(project_root, plan_digest)
    try:
        with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
            bound = connection.execute(
                "SELECT value FROM metadata WHERE key = 'plan_digest'"
            ).fetchone()[0]
            revision = int(
                connection.execute("SELECT value FROM metadata WHERE key = 'revision'").fetchone()[0]
            )
            rows = connection.execute(
                "SELECT status, COUNT(*) FROM items GROUP BY status"
            ).fetchall()
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise _fail("continuity_store_missing", "Scale queue is unavailable.") from exc
    if bound != plan_digest or any(status not in QUEUE_STATUSES for status, _count in rows):
        raise _fail("continuity_store_invalid", "Scale queue binding is invalid.")
    counts = {status: 0 for status in sorted(QUEUE_STATUSES)}
    counts.update({str(status): int(count) for status, count in rows})
    value = {
        "format": "opencntx-acquisition-queue-status",
        "format_version": 1,
        "plan_digest": plan_digest,
        "revision": revision,
        "counts": counts,
        "complete": counts["PENDING"] == 0 and counts["IN_FLIGHT"] == 0 and counts["RETRY_AFTER"] == 0,
    }
    return value | {"status_digest": _value_digest(value)}


def claim_acquisition_batch(
    project_root: Path,
    *,
    plan_digest: str,
    expected_revision: int,
    batch_size: int,
    quota_remaining: int,
    quota_reserve: int,
    now_epoch: int,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    """Atomically lease one bounded batch while preserving the declared quota reserve."""
    size = _integer(batch_size, "batch_size", minimum=1)
    remaining = _integer(quota_remaining, "quota_remaining")
    reserve = _integer(quota_reserve, "quota_reserve")
    now = _integer(now_epoch, "now_epoch")
    lease = _integer(lease_seconds, "lease_seconds", minimum=1)
    if remaining <= reserve:
        return {"status": "QUOTA_RESERVED", "items": [], "revision": expected_revision}
    database = _queue_path(project_root, plan_digest)
    with closing(sqlite3.connect(database, timeout=30)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        revision = int(
            connection.execute("SELECT value FROM metadata WHERE key = 'revision'").fetchone()[0]
        )
        if revision != expected_revision:
            raise _fail("continuity_write_conflict", "Scale queue revision changed before claim.")
        connection.execute(
            "UPDATE items SET status = 'PENDING', batch_id = NULL, lease_expires = NULL "
            "WHERE status = 'IN_FLIGHT' AND lease_expires <= ?",
            (now,),
        )
        connection.execute(
            "UPDATE items SET status = 'PENDING' WHERE status = 'RETRY_AFTER' "
            "AND lease_expires <= ?",
            (now,),
        )
        rows = connection.execute(
            "SELECT local_id, external_id FROM items WHERE status = 'PENDING' "
            "ORDER BY local_id LIMIT ?",
            (size,),
        ).fetchall()
        if not rows:
            connection.rollback()
            return {"status": "EMPTY", "items": [], "revision": revision}
        batch_basis = {"plan_digest": plan_digest, "revision": revision, "items": rows}
        batch_id = f"BATCH-{_value_digest(batch_basis)[:24].upper()}"
        connection.executemany(
            "UPDATE items SET status = 'IN_FLIGHT', batch_id = ?, lease_expires = ?, "
            "attempts = attempts + 1 WHERE local_id = ? AND status = 'PENDING'",
            [(batch_id, now + lease, local_id) for local_id, _external_id in rows],
        )
        next_revision = revision + 1
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'revision'", (str(next_revision),)
        )
        connection.commit()
    return {
        "status": "LEASED",
        "batch_id": batch_id,
        "items": [{"local_id": row[0], "external_id": row[1]} for row in rows],
        "revision": next_revision,
        "lease_expires": now + lease,
        "quota_after_claim": remaining - 1,
    }


def complete_acquisition_batch(
    project_root: Path,
    *,
    plan_digest: str,
    expected_revision: int,
    batch_id: str,
    outcomes: Sequence[Mapping[str, object]],
) -> dict[str, Any]:
    allowed = {"FETCHED", "NOT_FOUND", "RETRY_AFTER", "REVIEW_REQUIRED"}
    prepared = []
    for item in outcomes:
        if set(item) != {"local_id", "status", "response_hash", "retry_at"}:
            raise _fail("continuity_store_invalid", "Scale result differs from the contract.")
        status = str(item["status"])
        if status not in allowed:
            raise _fail("continuity_store_invalid", "Scale result status is invalid.")
        retry_at = item["retry_at"]
        if status == "RETRY_AFTER":
            retry_at = _integer(retry_at, "retry_at", minimum=1)
        elif retry_at is not None:
            raise _fail("continuity_store_invalid", "Only retry results may set retry_at.")
        response = item["response_hash"]
        if status == "FETCHED" and not isinstance(response, str):
            raise _fail("continuity_store_invalid", "Fetched result needs a response hash.")
        prepared.append((_identifier(item["local_id"], "local_id"), status, response, retry_at))
    database = _queue_path(project_root, plan_digest)
    with closing(sqlite3.connect(database, timeout=30)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        revision = int(
            connection.execute("SELECT value FROM metadata WHERE key = 'revision'").fetchone()[0]
        )
        if revision != expected_revision:
            raise _fail("continuity_write_conflict", "Scale queue revision changed before result.")
        leased = {
            row[0]
            for row in connection.execute(
                "SELECT local_id FROM items WHERE batch_id = ? AND status = 'IN_FLIGHT'",
                (batch_id,),
            ).fetchall()
        }
        if leased != {item[0] for item in prepared}:
            raise _fail("continuity_write_conflict", "Scale result does not match its batch lease.")
        for local_id, status, response, retry_at in prepared:
            connection.execute(
                "UPDATE items SET status = ?, response_hash = ?, lease_expires = ?, "
                "batch_id = NULL WHERE local_id = ?",
                (status, response, retry_at, local_id),
            )
        next_revision = revision + 1
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'revision'", (str(next_revision),)
        )
        connection.commit()
    return {
        "status": "COMMITTED",
        "batch_id": batch_id,
        "result_count": len(prepared),
        "revision": next_revision,
    }


def classify_assurance_risk(
    *,
    impact: str,
    newness: str,
    contract_change: bool,
    migration_change: bool,
    security_change: bool,
    remote_effect: bool,
    rollback: str,
    concurrent_writers: int,
) -> str:
    """Classify risk independently from project size."""
    if impact not in {"LOW", "MEDIUM", "HIGH"} or newness not in {"KNOWN", "NEW"}:
        raise _fail("continuity_store_invalid", "Assurance risk axis is invalid.")
    if rollback not in {"TRIVIAL", "TESTED", "DIFFICULT"}:
        raise _fail("continuity_store_invalid", "Assurance rollback axis is invalid.")
    writers = _integer(concurrent_writers, "concurrent_writers", minimum=1)
    if (
        impact == "HIGH"
        or contract_change
        or migration_change
        or security_change
        or remote_effect
        or rollback == "DIFFICULT"
        or writers > 1
    ):
        return "CRITICAL"
    if impact == "MEDIUM" or newness == "NEW" or rollback == "TESTED":
        return "STANDARD"
    return "LIGHT"


def _impact_closure(changed: Sequence[str], graph: Mapping[str, Sequence[str]]) -> set[str]:
    closure = {_identifier(item, "changed_component") for item in changed}
    pending = list(closure)
    while pending:
        current = pending.pop()
        for dependent in graph.get(current, ()):
            selected = _identifier(dependent, "dependent_component")
            if selected not in closure:
                closure.add(selected)
                pending.append(selected)
    return closure


def build_assurance_plan(
    *,
    project_id: str,
    changed_components: Sequence[str],
    dependency_graph: Mapping[str, Sequence[str]],
    test_manifest: Sequence[Mapping[str, object]],
    risk_axes: Mapping[str, object],
    terminal_boundary: bool,
    estimates: Mapping[str, object],
) -> dict[str, Any]:
    risk_fields = {
        "impact",
        "newness",
        "contract_change",
        "migration_change",
        "security_change",
        "remote_effect",
        "rollback",
        "concurrent_writers",
    }
    if set(risk_axes) != risk_fields or not all(
        isinstance(risk_axes[name], bool)
        for name in ("contract_change", "migration_change", "security_change", "remote_effect")
    ):
        raise _fail("continuity_store_invalid", "Assurance risk axes differ from the contract.")
    risk = classify_assurance_risk(
        impact=str(risk_axes["impact"]),
        newness=str(risk_axes["newness"]),
        contract_change=bool(risk_axes["contract_change"]),
        migration_change=bool(risk_axes["migration_change"]),
        security_change=bool(risk_axes["security_change"]),
        remote_effect=bool(risk_axes["remote_effect"]),
        rollback=str(risk_axes["rollback"]),
        concurrent_writers=_integer(risk_axes["concurrent_writers"], "concurrent_writers"),
    )
    impacted = _impact_closure(changed_components, dependency_graph)
    records: list[dict[str, Any]] = []
    for item in test_manifest:
        if set(item) != {"test_id", "covers", "tier", "read_only", "estimated_ms"}:
            raise _fail("continuity_store_invalid", "Assurance test differs from the contract.")
        tier = item["tier"]
        if tier not in {"TARGETED", "FULL", "ROLLBACK", "SECURITY", "TERMINAL"}:
            raise _fail("continuity_store_invalid", "Assurance test tier is invalid.")
        covers = item["covers"]
        if not isinstance(covers, list) or not all(isinstance(value, str) for value in covers):
            raise _fail("continuity_store_invalid", "Assurance test coverage is invalid.")
        records.append(
            {
                "test_id": _identifier(item["test_id"], "test_id"),
                "covers": sorted({_identifier(value, "test.cover") for value in covers}),
                "tier": tier,
                "read_only": item["read_only"] is True,
                "estimated_ms": _integer(item["estimated_ms"], "estimated_ms"),
            }
        )
    critical = risk == "CRITICAL" or terminal_boundary
    selected: list[dict[str, Any]] = []
    for item in records:
        relevant = bool(impacted.intersection(item["covers"]))
        mandatory = item["tier"] == "TERMINAL" or (
            critical and item["tier"] in {"FULL", "ROLLBACK", "SECURITY"}
        )
        if critical or mandatory or relevant:
            selected.append(item)
    if not selected:
        raise _fail("continuity_store_invalid", "Assurance plan selected no proof.")
    read_only = [item["test_id"] for item in selected if item["read_only"]]
    writers = [item["test_id"] for item in selected if not item["read_only"]]
    groups = [read_only[index::4] for index in range(min(4, len(read_only)))] if read_only else []
    groups.extend([[item] for item in writers])
    estimate_fields = {"duration_ms", "storage_bytes", "model_units"}
    if set(estimates) != estimate_fields:
        raise _fail("continuity_store_invalid", "Assurance estimate differs from the contract.")
    estimate_values = {name: _integer(estimates[name], name) for name in estimate_fields}
    basis = {
        "format": ASSURANCE_FORMAT,
        "format_version": 1,
        "project_id": _identifier(project_id, "project_id"),
        "risk": "CRITICAL" if terminal_boundary else risk,
        "specification_profile": "COMPACT" if risk == "LIGHT" and not terminal_boundary else "FULL",
        "terminal_boundary": terminal_boundary,
        "impacted_components": sorted(impacted),
        "selected_tests": selected,
        "parallel_read_groups": groups,
        "single_writer_preserved": True,
        "estimates": estimate_values,
        "test_manifest_digest": _value_digest(records),
    }
    return basis | {"plan_digest": _value_digest(basis)}


def build_assurance_receipt(
    plan: Mapping[str, object],
    *,
    bindings: Mapping[str, object],
    test_results: Mapping[str, object],
    actuals: Mapping[str, object],
) -> dict[str, Any]:
    plan_value: dict[str, Any] = dict(plan)
    basis = {key: item for key, item in plan.items() if key != "plan_digest"}
    if plan.get("format") != ASSURANCE_FORMAT or plan.get("plan_digest") != _value_digest(basis):
        raise _fail("continuity_store_invalid", "Assurance plan is invalid or drifted.")
    binding_fields = {
        "code_tree_digest",
        "environment_digest",
        "dependencies_digest",
        "test_manifest_digest",
        "input_digests",
    }
    if set(bindings) != binding_fields or bindings["test_manifest_digest"] != plan["test_manifest_digest"]:
        raise _fail("continuity_store_invalid", "Assurance bindings differ from the plan.")
    selected_tests = plan_value.get("selected_tests")
    estimates = plan_value.get("estimates")
    if not isinstance(selected_tests, list) or not all(
        isinstance(item, dict) for item in selected_tests
    ) or not isinstance(estimates, dict):
        raise _fail("continuity_store_invalid", "Assurance plan contents are invalid.")
    selected = {item["test_id"] for item in selected_tests}
    if set(test_results) != selected or any(value != "PASS" for value in test_results.values()):
        raise _fail("continuity_evidence_missing", "Assurance tests are incomplete or not green.")
    actual_fields = {"duration_ms", "storage_bytes", "model_units"}
    if set(actuals) != actual_fields:
        raise _fail("continuity_store_invalid", "Assurance actuals differ from the contract.")
    actual_values = {name: _integer(actuals[name], name) for name in actual_fields}
    comparison = {
        name: {
            "estimated": estimates[name],
            "actual": actual_values[name],
            "delta": actual_values[name] - _integer(estimates[name], f"estimated {name}"),
        }
        for name in actual_fields
    }
    value = {
        "format": "opencntx-assurance-receipt",
        "format_version": 1,
        "project_id": plan["project_id"],
        "plan_digest": plan["plan_digest"],
        "risk": plan["risk"],
        "bindings": dict(bindings),
        "test_results": dict(sorted(test_results.items())),
        "actuals": actual_values,
        "estimate_comparison": comparison,
        "status": "GREEN",
    }
    return value | {"receipt_digest": _value_digest(value)}


def assurance_receipt_reusable(
    receipt: Mapping[str, object], *, current_bindings: Mapping[str, object]
) -> dict[str, Any]:
    basis = {key: item for key, item in receipt.items() if key != "receipt_digest"}
    valid = (
        receipt.get("format") == "opencntx-assurance-receipt"
        and receipt.get("status") == "GREEN"
        and receipt.get("receipt_digest") == _value_digest(basis)
    )
    differences = []
    stored = receipt.get("bindings")
    if not isinstance(stored, dict):
        valid = False
        stored = {}
    for name in sorted(set(stored) | set(current_bindings)):
        if stored.get(name) != current_bindings.get(name):
            differences.append(name)
    value = {
        "reusable": valid and not differences,
        "differences": differences,
        "status": "REUSABLE" if valid and not differences else "RERUN_REQUIRED",
    }
    return value | {"decision_digest": _value_digest(value)}
