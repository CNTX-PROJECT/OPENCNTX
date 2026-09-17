# OPENCNTX 1.8.4 qualification roadmap

> Historical version record, not the active backlog. [Current release](releases.md) · [Current work](roadmap.md) · [History](history.md).

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

Version 1.8.4 qualifies the package and explicit CLI routes against 1.8.3.
On 2026-09-17 the owner approved publication with automatic native chat-host
integration excluded. G10 live Desktop/CLI chat-host activation remains
unverified follow-up work, not a release claim or a passed test.

## Required work

| Phase | Audit mapping | Acceptance |
|---|---|---|
| R0: compatibility | F11/F13/F19, C06, D01/D02 | Preserve closed v1 contracts; declare new routes and exact upgrade artifacts. |
| R1: boundaries | F01–F04/F12/F13/F15/F17/F22, A01–A09 | Contained, bounded reads and writes; conditional technique updates; safe delivery and evidence. |
| R2: index | F05/F14/F15/F18/F21, B01–B03/B06/B07 | Shared source snapshot, conditional publication, visible integrity and freshness. |
| R3: retrieval | F06–F08/F11/F16–F18, C01–C08 | Bounded JSON, original Unicode offsets, exact candidates, ranking and typed relationships. |
| R4: efficiency | F09/F10/F20/F22, B04/B05/B08, D03/D06 | Less unnecessary work without worse retrieval or task completion. |
| R5: hosts and presentation | F19, D01–D06 | Host conformance, context binding, retained visual role and footer, restart and recovery. |
| R6: release | All mandatory gates | Exact artifacts, regression and OS/Python matrix, upgrades, rollback and channel read-back. |

All original T01–T22 scenarios remain acceptance requirements. Multiple failing
scenarios can expose the same underlying defect; they are not a unique defect count.
Optional MCP transport and provider tokenizers are not dependencies of the core.
Unavailable provider measurements must remain explicitly unavailable.

## Upgrade matrix

Test clean installation and exact wheels from 1.8.3, 1.8.2, 1.8.1, 1.8.0 and
1.7.6. Qualify other old releases individually, using a tested bridge when
necessary. Old format fixtures prove reader compatibility, not every historic
installation path. Test identical-artifact no-op, same-version changed artifact,
interruption, offline rollback and safe rejection of future formats.

Retain Windows/Ubuntu and Python 3.11–3.14 qualification for supported managed
pipx and dedicated-venv installations. Do not extrapolate these results to an
unqualified platform or installation owner. Code rollback, durable-state restore,
cache rebuild and presentation rollback are separate checks. Never restore an
old snapshot over newer user work.

## Twelve release gates

1. G01: every audit item has a result or explicit scoped decision.
2. G02: each promised upgrade path passes against exact candidate artifacts.
3. G03: offline recovery, interruption and idempotence preserve user data.
4. G04: existing consumers remain valid; new formats negotiate explicitly.
5. G05: source, write, secret, output and concurrency boundaries pass.
6. G06: index, FTS, freshness and delivery states do not overstate evidence.
7. G07: retrieval, JSON, Unicode, relation and evidence goldens pass.
8. G08: the supported VISUAL_ARTIST integration passes preview, apply, verify,
   repeated application and rollback, retaining human review requirements.
9. G09: footer compatibility and structured-output isolation pass.
10. G10: explicit package and fresh-process CLI routes preserve context binding
    and output isolation. Native Desktop/CLI chat-host activation, hook trust
    and live context-resume qualification are outside the approved 1.8.4 scope.
    Simulated delivery is not live model-residency proof.
11. G11: performance goals have repeatable measurements; token savings require
    complete task-level provider evidence before being advertised.
12. G12: full regression, quality, build, install and release-byte checks pass.

## Compatibility decisions

- Technique IDs must be portable single-file identifiers. Unsafe paths,
  implicit overwrites and stale expected digests are rejected. Identical create
  retries remain idempotent. CLI updates accept `--expected-digest`.
- PROVEN requires nonempty digest evidence. Recall reports STALE when that
  evidence cannot be found in current bounded project sources; stored card
  bytes are preserved. This does not prove that a procedure is correct.
  Legacy empty PROVEN cards remain readable as STALE. Conditional correction
  accepts the digest of either the exact stored card or its STALE recall view;
  changes to any other card field invalidate both bindings.
- Only explicit `Requires:`, `Contains:` and other declared relation prefixes
  create hard relationships. Ordinary prose, including negation, is a reference.
- Legacy v1 search is a metadata-only contract. Its historical `loaded` field
  is not a receipt for source-text delivery. The opt-in `--delivery-report`
  route gives explicit source-read units, coverage and complete output limits.
- Root identity in old durable formats is retained. Search caches bind to
  case-sensitive root paths on POSIX and normalized Windows paths; relocation
  requires rebuilding the cache. Copying a cache is not project adoption.
- Enumeration refuses more than 1,000,000 visited filesystem entries or
  10,000 technique cards. Recall reads at most 1,000 cards per requested page,
  at most 100,000 bytes each. Status pagination is opt-in to preserve the old
  envelope. Filesystem enumeration itself is not a hard OS-level memory or
  timeout guarantee; source-content and serialized-delivery limits are separate.
- Footer v1 remains closed. Partial metrics use a separate v2 host envelope,
  bound to session, context generation and source digest, with per-field provenance.

## Measurements and remaining evidence

Measure at least 30 warm samples, report corpus hashes and hardware, and label
process startup separately from cold filesystem cache. Target a 30% improvement
in the representative 10,000-file no-op median, without more than 10% p95
regression on small profiles. Report all reads/writes and task success. A
character-based token estimate is not an exact provider tokenizer.

### Recorded indexing comparison

Thirty warm repetitions on Windows 11 build 26200, Python 3.12.10,
AMD64 Family 23 Model 113. Both versions used identical synthetic corpus
bytes and the ordinary v1 plus v2 build workload. This is not a cold-cache
or provider-token benchmark.

| Corpus | 1.8.3 no-op p50 / p95 | 1.8.4 no-op p50 / p95 | Candidate source reads / index publications |
|---|---|---|---|
| 12 files, 916 bytes | 63.14 / 67.66 ms | 15.65 / 16.18 ms | 0 / 0 per repetition |
| 10,000 files, 730,040 bytes | 4704.07 / 4996.67 ms | 1802.19 / 1838.85 ms | 0 / 0 per repetition |

The large-profile median improved by 61.69%; the small-profile p95 also
improved. The 30% no-op target and small-index regression limit pass for
these workloads. Retrieval goldens remained correct through modify, add,
rename and delete operations.

There are measured costs: the separate 10,000-file Python-heap sample grew
from 28.31 MB to 37.37 MB while both projections shared one snapshot. The
single retrieval samples rose from about 2–3 ms to 9 ms with the additional
source and delivery checks; those single samples are not a search p95.
New-process help/version medians stayed around 225–228 ms. No lazy-import
rewrite or universal latency, memory, token or cost improvement is claimed.

Raw samples: [1.8.3 baseline](evidence/1.8.4/benchmark-1.8.3.json) and
[1.8.4 candidate](evidence/1.8.4/benchmark-1.8.4.json). Reproduce with
`tools/release_184_benchmark.py --source SOURCE_CHECKOUT --output REPORT.json`.

### Host qualification boundary

| Route | Available evidence | Remaining requirement |
|---|---|---|
| Python package | Typed context binding, negative cases, presentation and recovery tests | No claim that an LLM has accepted the data |
| CLI in fresh processes | Retrieval pilot, persisted index, conditional concurrent writers and footer isolation | No automatic native chat-hook activation |
| Native Desktop/CLI chat hosts | Existing adapter contracts and local helper | Excluded from 1.8.4; native hook trust and live host/context-resume evidence remain open |

The owner explicitly excluded the last row from the 1.8.4 release on
2026-09-17. Passing library and CLI tests does not close this retained
follow-up. Installing this release does not activate native chat hooks.

Native hook trust remains host-owned. Do not edit trust hashes or bypass native
review to manufacture integration evidence. Human visual approval must refer
to the actual proposed change; disposable test approval is only a fixture.

[Documentation home](README.md)
