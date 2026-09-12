"""Measure bounded context planning for the frozen 1.7.6 checkpoint scales."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from opencntx.project_planning import ContextSource, plan_context_load

SCALES = (0, 100, 1_000, 10_000)


def _digest(identifier: str) -> str:
    return hashlib.sha256(identifier.encode("ascii")).hexdigest()


def measure(*, repeats: int = 9) -> dict[str, object]:
    if not 3 <= repeats <= 25:
        raise ValueError("repeats must be between 3 and 25")
    results: list[dict[str, object]] = []
    for checkpoints in SCALES:
        required = (
            ContextSource("current-step", 1, _digest("current-step"), 4_096, "CURRENT_STEP"),
            ContextSource("return-anchor", 1, _digest("return-anchor"), 2_048, "RETURN_ANCHOR"),
            ContextSource("owner-decision", 1, _digest("owner-decision"), 2_048, "DECISION"),
        )
        history = tuple(
            ContextSource(f"checkpoint-{number:05}", 1, _digest(f"checkpoint-{number:05}"), 512)
            for number in range(checkpoints)
        )
        sources = (*required, *history)
        previous = {item.source_id: item.sha256 for item in history}
        available = tuple(previous)
        durations: list[float] = []
        plan: dict[str, object] = {}
        for _ in range(repeats):
            started = time.perf_counter_ns()
            plan = plan_context_load(
                sources,
                previous_digests=previous,
                available_source_ids=available,
                max_bytes=16_384,
            )
            durations.append((time.perf_counter_ns() - started) / 1_000_000)
        ordered = sorted(durations)
        p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
        results.append(
            {
                "checkpoints": checkpoints,
                "objects_considered": len(sources),
                "objects_loaded": len(plan["load_source_ids"]),
                "objects_referenced": len(plan["reference_source_ids"]),
                "naive_bytes": plan["naive_bytes"],
                "read_bytes": plan["loaded_bytes"],
                "reduction_percent": plan["reduction_percent"],
                "p50_ms": round(statistics.median(durations), 3),
                "p95_ms": round(ordered[p95_index], 3),
            }
        )
    scalable = [item for item in results if int(item["checkpoints"]) > 0]
    status = "PASS" if all(float(item["reduction_percent"]) >= 30.0 for item in scalable) else "FAIL"
    return {
        "format": "opencntx-1.7.6-efficiency-evidence",
        "format_version": 1,
        "repeats": repeats,
        "minimum_required_reduction_percent": 30.0,
        "cases": results,
        "status": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = measure(repeats=args.repeats)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
