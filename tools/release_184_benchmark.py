"""Repeatable synthetic comparison of the ordinary v1/v2 indexing route."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path


def measure(operation):
    start = time.perf_counter()
    value = operation()
    return value, (time.perf_counter() - start) * 1000


def profile(count, samples, knowledge, search):
    with tempfile.TemporaryDirectory(prefix="ocx-184-benchmark-") as temporary:
        root = Path(temporary)
        corpus = hashlib.sha256()
        source_bytes = 0
        for number in range(count):
            name = f"doc-{number:05}.md"
            content = "# Synthetic source\n\nDeterministic project context for scale measurement.\n"
            if number == count // 2:
                content += "\ngoldenrecordmarker confirms retrieval.\n"
            data = content.encode("utf-8")
            (root / name).write_bytes(data)
            source_bytes += len(data)
            corpus.update(name.encode() + b"\0" + data)
        legacy = root / ".opencntx" / "index-v1.json"
        shared = "legacy_output" in inspect.signature(search.build_search_index).parameters

        def build():
            if shared:
                return search.build_search_index(root, max_files=count + 1, legacy_output=legacy)
            knowledge.build_index(root, output=legacy, max_files=count + 1)
            return search.build_search_index(root, max_files=count + 1)

        built, first_ms = measure(build)
        database = Path(built["path"])
        durations = []
        changed_publications = 0
        source_reads = []
        for _ in range(samples):
            before = (database.stat().st_mtime_ns, legacy.stat().st_mtime_ns)
            result, elapsed = measure(build)
            durations.append(elapsed)
            source_reads.append(result["stats"]["read_files"] + (0 if shared else count))
            after = (database.stat().st_mtime_ns, legacy.stat().st_mtime_ns)
            changed_publications += sum(old != new for old, new in zip(before, after, strict=True))
        tracemalloc.start()
        build()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        mutations = {}
        for name, change in (
            (
                "modify",
                lambda: (root / "doc-00000.md").write_text("# Changed\nneedle", encoding="utf-8"),
            ),
            ("add", lambda: (root / "added.md").write_text("# Added", encoding="utf-8")),
            ("rename", lambda: (root / "added.md").rename(root / "renamed.md")),
            ("delete", lambda: (root / "renamed.md").unlink()),
        ):
            change()
            value, elapsed = measure(build)
            mutations[name] = {"wall_ms": elapsed, "stats": value["stats"]}
        retrieved, search_ms = measure(
            lambda: search.search_full_text(
                database,
                "goldenrecordmarker",
                root=root,
                max_results=1,
                max_tokens=2000,
                max_snippet_chars=120,
            )
        )
        actual = retrieved["results"][0]["path"] if retrieved["results"] else None
        expected = f"doc-{count // 2:05}.md"
        if actual != expected:
            raise RuntimeError("Retrieval golden failed; timing is not accepted.")
        ordered = sorted(durations)
        return {
            "files": count,
            "source_bytes": source_bytes,
            "corpus_sha256": corpus.hexdigest(),
            "route": "default CLI v1+v2 projection workload, in one process",
            "first_build_warm_filesystem_ms": first_ms,
            "warm_noop": {
                "samples_ms": durations,
                "p50_ms": statistics.median(durations),
                "p95_ms": ordered[max(0, (95 * samples + 99) // 100 - 1)],
                "source_reads_per_sample": source_reads,
                "changed_index_files": changed_publications,
                "python_heap_peak_bytes_separate_sample": peak,
            },
            "mutations": mutations,
            "retrieval": {"expected": expected, "actual": actual, "wall_ms": search_ms},
            "provider_tokens": None,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args()
    if not 30 <= args.samples <= 100:
        parser.error("samples must be between 30 and 100")
    sys.path.insert(0, str(args.source.resolve(strict=True) / "src"))
    import opencntx
    from opencntx import knowledge, search_index

    result = {
        "format": "opencntx-release-184-benchmark-v1",
        "version": opencntx.__version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor()),
        "cache": "warm filesystem; no cold-cache claim",
        "tokenizer": "none; no provider token or cost claim",
        "profiles": [
            profile(count, args.samples, knowledge, search_index) for count in (12, 10000)
        ],
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"version": result["version"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
