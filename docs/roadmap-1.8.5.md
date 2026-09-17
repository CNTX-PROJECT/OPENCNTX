---
project: OPENCNTX
planned_release: "1.8.5"
revision: "UPDATED-R2-2026-09-17-PUBLIC-EN"
document_role: "PROPOSED_PLAN_WITH_ON_DEMAND_SPECIFICATION"
implementation_status: "PROPOSED_NOT_RELEASE_QUALIFIED"
baseline_commit: "6fc196b5ec90370c93c204a115ac58c73fd2bb32"
next_action: "P0_PRESERVE_AND_ISOLATE"
native_host_integration: "OUT_OF_SCOPE"
source_roadmap_sha256: "344957a0974e27baa47780cc98cb97d41915e42bf64c90424e89ac21e2aab857"
---

# OPENCNTX 1.8.5 — updated roadmap

**Date:** 17 September 2026. **Primary goal:** a safe, low-conflict upgrade from the existing 1.8.4 installation, preserving project data, existing contracts and recovery paths. Speed and smaller output are improvement goals, never reasons to remove necessary knowledge or safety checks.

[Current product roadmap](roadmap.md) · [1.8.4 release scope](release-1.8.4.md) · [Installation and updates](install-and-update.md)

> **Publication status: proposal, not a software release.**
> This is the English publication copy of the supplied UPDATED-R2 roadmap, whose SHA-256 is recorded above. It retains the 16-section plan, P0–P7 sequence, measurements with their limitations, and open G00–G12 gates. Private source notes and the research bundle are not included in this documentation-only proposal; local-only references are identified as retained inputs in section 16. Publishing this plan does not implement or qualify 1.8.5, approve a merge, change an installed runtime, or create a release tag.
>
> **Instruction for the implementing developer:** begin only with **P0: preserve, classify and isolate local work**. The installed 1.8.4 does not need preventive reinstallation. This roadmap does not authorize automatic changes to production, notes applications, native hooks or existing archives.
>
> The previous research used a **limited executable 1.8.5 design prototype** with selected 1.8.4 algorithms. Its results do not prove that the real 1.8.5 upgrade, official installer or any AI provider is qualified. Those experiments have not been rerun for this publication.

| Orientation | Answer |
|---|---|
| Canonical software baseline | Published v1.8.4 at the fixed commit above. |
| Proposed execution plan | This 1.8.5 plan, pending review; earlier release plans remain historical sources. |
| Next step | P0 preservation and isolation, followed by reproduction on exact source versions. |
| Upgrade priority | Existing managed 1.8.4 first; clean installation is additional evidence. |
| Main design choice | Preserve the existing manager and durable formats; enable new output features explicitly. |
| Software publication | Blocked until every applicable G00–G12 gate is satisfied and separate release approval exists. |

**Reading route:** use this orientation to resume work, then load only the relevant P phase and G gate. Do not load the entire roadmap or historical note for every task.

## 1. Provenance, boundaries and evidence terminology

This plan improves the supplied owner roadmap while preserving its core sequence: PORT/DEFER/REJECT decisions, three exact source identities, measurement before optimization, candidate freeze and separate release approval. That input reports an unqualified modified development tree, substantial no-op slowdown and missing current qualification. These are **supplied local audit observations**, not properties independently remeasured on the owner's computer during this research. [U1]

Published 1.8.4 source and installation documentation were inspected through GitHub during the preceding research. The release files could not be downloaded into that research runtime. Consequently, **no complete upstream checkout or official wheel was executed**. Selected query, ranking, snippet and FTS-integrity algorithms were transcribed into a separate component lab. This transcription was not byte-verified as a complete upstream module. [B1][B2]

Keep four evidence categories distinct:

- **SOURCE_OBSERVATION:** visible in a pinned source version.
- **SIMULATION_MEASURED:** executed in the retained prototype or component lab.
- **PRODUCT_QUALIFIED:** executed against an exact candidate artifact through a real product route on a named platform.
- **OPEN / UNKNOWN / OUT_OF_SCOPE:** not executed, unavailable or explicitly excluded.

A passing simulation never automatically passes a product gate. A matching hash, successful import, healthy package, current project and correctly completed task are different pieces of evidence.

The internal prototype identity is `1.8.5.dev0+roadmap.sim2`. This is **not a recommendation to put that version into the real package**: the existing version gate accepts canonical `major.minor.patch` versions. A real candidate can use the existing separation between package version `1.8.5`, published version `1.8.4` and `local-candidate`. [B5]

## 2. What remains; what must not be rebuilt

### 2.1 Preserve the foundation

Keep the local-first core, authoritative source files, bounded reads, project/path binding, secret policy, controlled writer transactions, generation checks, explicit status, readable metadata and existing managed installer. Do not add a second installer, second authoritative knowledge store or another global policy engine. [B2][B3][B4]

The 1.8.4 documentation qualifies pipx and a dedicated virtual environment. A shared Python, editable checkout, unknown owner, synchronized installation-state directory or custom wrapper requires diagnosis first. A notes document stored in a synchronized folder does not by itself prove that the **installer state** is misplaced: inspect the two locations separately. [B3]

### 2.2 Small core scope for 1.8.5

| Component | Decision |
|---|---|
| Dirty-state/version truth | Mandatory fix and tests. |
| Measured no-op regression in the local candidate | Reproduce first; apply a bounded fix. |
| Lossless compact serialization | Suitable as a small, negotiated output option. |
| Missing mandatory information | Make it explicit; never replace it with a reassuring `READY`. |
| 1.8.4 → 1.8.5 upgrade and rollback | Primary qualification path. |
| VISUAL_ARTIST-v2 | Include only with demonstrated need and a complete compatibility path; otherwise DEFER. |
| Footer improvement | Inventory existing v1/v2 contracts first; no accidental contract replacement. |
| Batch retrieval with a shared read snapshot | Promising optional optimization; not a prerequisite for a safe core update. |
| Embeddings, vector store, replacement search backend | DEFER without demonstrated retrieval shortcomings that the existing route cannot address. |
| Automatic native Desktop/CLI/WebUI hooks | Out of scope unless separately reopened and qualified live. |

Reduce release scope when an optional component lacks evidence. Do not remove safety, data preservation or truthful reporting to meet a date.

## 3. Research and previously executed simulations

### 3.1 Executed scope

The previous research produced an offline Python prototype using selected 1.8.4 component logic, an **independent fixture builder**, and a persistent update state model. The latter deliberately uses simulated artifact files rather than wheels. It tests transition design, not the real `opencntx-install` implementation. [S1][S2]

The main run contains **120 task steps: four predetermined instruction profiles repeated across three corpus sizes**. Each instruction has sixteen stages and is approximately 4 kB long. There are 177 passing assertions, of which 120 specifically compare JSON equality across two serializations. These are not 177 independent product scenarios or 120 distinct AI tasks.

Query plans and expected facts are predefined by the harness. **No natural-language planner or LLM execution was tested.** Sessions and context generations change as explicit test identities; this does not prove actual model residency after compaction.

The figures below are carried over from the supplied research report. Raw evidence remains in the separately retained research bundle; it is not shipped in this proposal. Reproduce product results independently before using them for release decisions.

### 3.2 Speed: a bounded component experiment

A performs a separate FTS-integrity check and read transaction for each of eight queries. B runs the same eight queries within one explicitly bounded, pinned read transaction with one integrity check. Selected content, ranking and source-hash checks were compared for equality. Twelve warm AB/BA pairs were measured per corpus without tracemalloc during timing.

| Files | Source bytes | A: median, eight separate checks | B: median, one batch check | Scripted task steps |
|---|---:|---:|---:|---:|
| 12 | 11,545 | 8.52 ms | 2.96 ms | 40/40 |
| 240 | 273,635 | 27.34 ms | 5.77 ms | 40/40 |
| 2,400 | 2,759,023 | 207.28 ms | 38.10 ms | 40/40 |

**This is not a benchmark of complete 1.8.4 versus complete 1.8.5.** It is not a no-op indexing benchmark either. The fixture builder, status route, installer, Windows and provider latency are excluded. Twelve pairs are exploratory; the final plan retains a larger measurement protocol.

### 3.3 Smaller output does not automatically mean fewer billed tokens

The same result objects were serialized as indented and compact JSON. Every field and its content were retained, and parsing both forms produced equal objects.

| Corpus | Fewer bytes in the same result | Fewer bytes in fixed instruction text + one result |
|---|---:|---:|
| 12 | 15.58% | 8.73% |
| 240 | 14.94% | 9.10% |
| 2,400 | 14.94% | 9.10% |

This supports investigating an optional compact output route. It does not establish a universal token-saving percentage: actual provider tokenizers, request wrappers, previous messages, tool definitions, output and retries were not measured. The combined instruction/result comparison is not a complete API-request measurement. `ceil(characters/4)` remains only an estimate. [S1][E4][E5][E6]

### 3.4 Upgrade and recovery probes

The state model tested seven named crash points with subprocesses that actually terminate through `os._exit`: before the journal, after staging, before activation, after activation, after the simulated health check, after the healthy journal record, and after commit. A fresh process then recovers the model.

Other cases include eight identical retries, two competing activations with exactly one winner, an incorrect hash, a stale plan, a missing rollback artifact, an unknown format, and preservation of a later user edit. Pending recovery must not be hidden by a quick same-version no-op response. [S1]

**Limit:** the health check is simulated. These probes did not execute a pipx upgrade, actual import qualification, Windows lock test, power failure or failed pip installation. Crash points occur between named stages, not at every possible write byte.

### 3.5 Two findings from additional probes

**SIM-GAP-01 — correct file, incorrect coverage claim.** The first prototype could deliver a mandatory file while a critical constraint remained outside the snippet. Sim2 checks explicit, source-bound test requirements and reports `INSUFFICIENT_EVIDENCE` when they are missing. This fixes the **first research prototype**, not automatically a proven 1.8.4 product defect. Literal test markers do not establish full semantic task coverage. [S2]

**COMP-184-01 — FTS match without a matching snippet.** With the transcribed 1.8.4 snippet logic, FTS finds a distant `café` for the query `cafe`, while the snippet stays at the beginning. The FTS tokenizer and casefold-only snippet selection differ for this case. This remains an **open component finding** that must first be reproduced against the real 1.8.4 wheel. [B2][E1][S2]

An additional sweep of twenty byte/estimate-budget combinations produced fitting output or explicit budget rejection; mandatory context was not silently removed. The unresolved accent case remains open even though the other main-run checks passed.

## 4. Upgrade contract: minimize conflicts with 1.8.4

### 4.1 Hard invariants

1. **No automatic rewriting of human-owned project data during a software upgrade.** Source files, notes, rules, entity names, links, decisions, roadmap numbering and other non-product-owned files remain byte-identical unless a separately approved project action changes them.
2. **No re-adoption merely because the package version changes.** An existing managed root remains the same root. Successful installation does not approve a previously blocked adoption audit.
3. **No mandatory durable-format migration without necessity.** Test existing index-v1, search-v2, technique cards, journals, intents/reviews and receipts using real 1.8.4 fixtures first. Readability includes verification, idempotent repeat, recovery and permitted writes where applicable.
4. **Software rollback is not document rollback.** A user edit made after upgrading remains intact when software returns to 1.8.4.
5. **No native activation or network feature as an installation side effect.** CLI availability and automatic chat integration are separate capabilities.
6. **Uncertain state stops in a controlled way.** Unknown ownership, future schemas, missing recovery artifacts and ambiguous locks require diagnosis/recovery, not forced installation.

### 4.2 Data classes

| Class | Upgrade policy | Rollback policy |
|---|---|---|
| Human documents/configuration | Zero unplanned writes. | Never restore an old full-project snapshot over newer edits. |
| Durable OPENCNTX records | Compatible reads; only necessary, explicit migration. | Old reader/manager handles named records correctly or refuses safely. |
| Derived indexes/caches | Reuse when semantically compatible; otherwise rebuild explicitly. | Restore/rebuild separately from human data; never label an old cache current without evidence. |
| Installation state and journals | Existing manager and ownership boundaries. | Offline recovery using the exact artifact corresponding to that installation. |
| Presentation/notes application | No automatic layout changes from a package upgrade. | Revert only a specifically approved, unchanged managed block. |

A parser change may require cache refresh without constituting a project migration. A version difference alone is not a reason to delete every cache.

### 4.3 Upgrade sequence

**Read-only preflight → establish ownership and rollback → stage candidate → isolated product health → controlled activation → fresh-process resume → terminal evidence.** Use the existing manager and its existing states, including `NEW_HEALTHY`, `OLD_RESTORED` and `RECOVERY_REQUIRED`. Do not change names or meanings without a format/compatibility decision. [B3]

Expose the intended write set beforehand. Do not resolve an active writer or pending transaction by blindly removing locks. Follow the existing recovery protocol, then recheck the actual active artifact identity.

The rollback hash below was obtained from release metadata and must be checked again against the actual published bytes when downloaded:

```text
baseline release: v1.8.4
baseline commit: 6fc196b5ec90370c93c204a115ac58c73fd2bb32
baseline wheel: opencntx-1.8.4-py3-none-any.whl
baseline wheel SHA-256:
b3fe658c5071b17e1835be65cc10df3c025dd03677c1be45c9b8aeb977d011d9
candidate wheel SHA-256: UNKNOWN — record only after a real candidate build
```

Do not invent a candidate digest, download automatically into production or run a global `pip install` over an unknown installation. Hash checking supports integrity within a trusted distribution path; an accompanying hash is not independent proof of origin. [B1][E3]

## 5. P0 — preserve, isolate and restore version truth

**Goal:** lose no existing work and never treat dirty source as a qualified release.

- [ ] Create a recoverable bundle of tracked, staged and necessary untracked development files; inventory ignored build inputs separately.
- [ ] Preserve existing snapshots and evidence bundles. Do not discard work through checkout/reset/cleanup before recovery is verified.
- [ ] Create a change ledger recording purpose, baseline, PORT/DEFER/REJECT, dependencies, risk and evidence for each file or logical change.
- [ ] Isolate development, reference source, fixtures and evidence. Evidence must not change the source tree being benchmarked.
- [ ] Record three exact identities: clean 1.8.4, clean pre-fix reproduction of the local problem, and the later fixed RC.
- [ ] Distinguish HEAD/tag alignment from worktree cleanliness in the version gate. `TAG_ALIGNED` must not become an unqualified all-clear summary when executable dirty changes exist.
- [ ] Test staged changes, unstaged changes, untracked importable modules and missing build inputs. Relevant unknown inputs must block release builds.

**Done when:** the original development state is recoverable, every change has a decision, and the defect is measurable on a clean, exactly identified pre-fix state. Repeating the previously reported local counts of modified/new files is insufficient; inventory the current state. [U1][B5]

## 6. P1 — compatibility and upgrade proof before broad optimization

- [ ] Create a baseline fixture with the **real published 1.8.4 wheel**: an existing project, technique cards, indexes, roadmap/checkpoint, footer-v1/v2, and an applied VISUAL_ARTIST-v1 receipt.
- [ ] Record canonical source hashes, ownership, active executable/interpreter, project roots, pending journals and recovery artifact.
- [ ] Execute a minimal candidate upgrade without automatic project migration or presentation activation.
- [ ] Check both ordinary old readers and actual product routes: status, search, pack/verify and fresh-process resume where supported.
- [ ] Make new user changes **after** upgrading, then roll back the software. Compare human-owned bytes, not only file lists.
- [ ] Leave an existing valid 1.8.4 installation unchanged when candidate qualification fails.

**Decision:** do not combine multiple index, footer, VISUAL_ARTIST and installation-format changes immediately. Establish one working compatible upgrade foundation, then port bounded improvements.

## 7. P2 — restore speed without weakening safety

### 7.1 Precise no-op measurements

Replace zero reads/writes with separate units:

| Metric | Expected for an ordinary warm no-op |
|---|---|
| `source_content_bytes_read` | Zero for demonstrably reusable sources within the selected fast contract. |
| `human_source_bytes_written` | Always zero. |
| `index_publications` | Zero when content/semantics are unchanged. |
| `cache_bytes_read` | Measure separately; do not silently mix with source reads or report as zero. |
| `metadata_probes` | Measure by operation type and platform. |
| `lock_operations`, temporary writes | Measure and justify necessity. |
| `strict_source_bytes_read` | May increase: actual strict hashing requires source inspection. |

Fast fingerprint checking and strict digest checking provide different guarantees. Neither must claim that all project truth is current in every circumstance.

### 7.2 Bounded optimization of path work

Profile the reported `paths_alias`/reparse costs on the **available pre-fix source**, not a simplified model. The local dirty source was unavailable to the research lab; the component experiment does not remeasure that cause. [U1]

Determine the identity of a fixed number of output files once per operation where safe. Reuse measured metadata within that operation, but retain last-moment checks when opening and publishing.

Define `N` as candidate files, `D` as visited directories and `K` as output targets. A scan still generally depends on N and D; only identity work for fixed K can be constant relative to N. Use `2N+8` as a fixture-specific counter bound if useful, not an unproven universal filesystem contract.

### 7.3 Optional read batches

The component experiment motivates a separate opt-in batch route. Define maximum queries, total source bytes, output bytes and transaction duration in advance. Use one pinned read transaction and a checked index; still hash selected source content before delivery.

A persistent index-was-once-approved flag outside that transaction is **not** the same optimization. A pinned snapshot is not automatically the latest project state. Report its generation, scope and limitation. A new batch or generation requires the agreed evidence again.

Measure potential memory and lock costs. SQLite documents FTS-specific consistency checks and transaction behavior; replacing one file successfully does not make several separate files one crash-safe publication. [E1][E2][E7]

**Done when:** the same safety and retrieval cases pass, independent counters show less unnecessary work, and actual product benchmarks meet their targets.

## 8. P3 — sufficient correct information, not merely less context

### 8.1 Separate the instruction from the search query

Do not pass a long user instruction unchanged into a query-limited search interface. Keep the complete instruction at the host and construct a bounded task plan containing required sources, claims, dependencies, queries, stop conditions and a resume anchor. The lab uses predefined plans; automatic planning requires separate tests.

A query plan is not execution authority. Retrieved documents, imported instructions and historical checkboxes remain source data.

### 8.2 Make mandatory coverage explicit

- [ ] Define minimum task anchors: current roadmap/step, relevant decisions, specific source versions and critical constraints.
- [ ] Require not only a path but, where necessary, a section, line range, structured field or verifiable evidence reference.
- [ ] Check coverage **in the final serialized output**, after deduplication and budget selection.
- [ ] Distinguish missing mandatory evidence from an insufficient budget, with a concrete next action.
- [ ] Count historical material only in its agreed role; archive status must accompany the snippet.
- [ ] Verify that each claimed mandatory fact comes from its required source, not a coincidental echo in another document.

The prototype uses literal, path-bound markers as its test oracle. This is useful for regressions, not a product-wide method for declaring AI answers true.

### 8.3 Query/snippet consistency

Reproduce COMP-184-01 with the real baseline. Also test diacritics, `ß`, `İ`, combining Unicode, underscores, hashes, versions, JSON paths and terms matching metadata only. Do not confuse a valid document match with evidence that the delivered passage answers the question.

A fix must preserve original source positions. Do not blindly apply aggressive ASCII normalization: it can damage other identifiers or offsets. Define and test the relationship between FTS tokenization, matched text and source position. [B2][E1]

### 8.4 No overstated completeness

Expose truncation, candidate limits, missing sources, parser fallbacks and stale results. `complete` applies only to the stated scope. No result does not prove that information is absent. An index hash proves neither truth nor current live Home Assistant state.

## 9. P4 — economical output and provider independence

### 9.1 Low-cost first improvement

Keep existing CLI and v1/v2 output as the default. Add explicit compact serialization without losing fields or silently changing bytes for old consumers. Define the actual option name in the product CLI contract; prototype functions are not existing OPENCNTX commands.

Measure lossless representation changes first. Diagnostic detail can later become a separately requested profile, but preserve source binding, missing coverage, budget state and critical warnings in ordinary model-facing output.

### 9.2 Budget contract

Require three distinct values: source bytes read, output bytes sent, and measured tokens or an explicitly labeled estimate. For real provider requests include system instructions, tool definitions, task text, history and reserved response space.

A hard **byte limit** is locally verifiable. A hard **provider-token limit** requires an appropriate counter and the complete request. Without that counter, never present an estimate as a guarantee. Define a safe fallback or `TOKEN_COUNT_REQUIRED` for a genuinely strict provider budget.

OpenAI, Anthropic and Gemini document their own counting routes. These are potential optional adapters, not mandatory network dependencies of the core. No provider requests or paid benchmarks were executed in the research. External counting may send content to a provider and must respect authorization and privacy boundaries. [E4][E5][E6]

### 9.3 Capabilities, not a list of model names

Record host capabilities: text/JSON output, tool results, fetch support, exact counting, cache telemetry and demonstrable context residency. A provider or model name does not imply that all capabilities exist in the actual desktop tool.

After a new session, compaction, model/host change or context generation change, an old hash must not replace necessary source content. Resend minimum required context when the host cannot prove availability. Cache savings, fewer bytes and less model context are different claims.

**Release requirement:** portable text/JSON through explicit routes works without a provider SDK. **Claim requirement:** provider-specific token, cost or quality improvements require real task-level measurements.

## 10. P5 — VISUAL_ARTIST and footer without upgrade surprises

### 10.1 VISUAL_ARTIST

1.8.4 already has a writing v1 plan/receipt/rollback route. Merely preserving v1 readability is insufficient. Specify behavior separately for an old unapplied plan, an applied plan, identical repeat and rollback. [B4]

Bind new review evidence to the concrete artifact, document bytes, proposed result and exact change. An old approval must not silently authorize a different v2 operation. Deliberately blocking an unsafe old write requires an explicit security-compatibility decision with recovery/review guidance.

Do not run VISUAL_ARTIST automatically during package installation. Preserve old receipts and protect edits made after apply. Broad project takeover or a general layout writer remains outside the small core update without qualification.

### 10.2 Footer

Inventory the footer contract, host envelope v1, already existing host envelope v2, presentation profile, owner layout and append logic first. Do not accidentally build another v2 because different layers share a short name. [B6]

A telemetry error must not discard a valid task result. Strict JSON, code and tool payloads remain byte-identical; send diagnostics through a separate channel where needed. Repetition must not duplicate footers. Localized owner presentation remains a profile; the public product interface remains English under the existing project convention. [U1][B6]

Test an actual explicit product route, not only a helper. Native hook trust remains separate and out of scope; never edit trust hashes to manufacture evidence.

## 11. P6 — final test matrix

### 11.1 Installation and upgrades

| Scenario | Minimum evidence |
|---|---|
| 1.8.4 → candidate, existing managed root | Existing state readable, sources preserved, product health and resume. |
| Upgrade with multiple existing roots | One correct runtime/owner; no duplicates or unintended root migration. |
| Repeat the exact candidate | Idempotent; assess pending recovery first. |
| Same version label, different hash | Do not confuse with an identical artifact; explicitly permit or reject. |
| Interrupted staging/activation/health check | Safe resume or exact offline rollback; no false health. |
| User edit after upgrade, then rollback | Preserve newer human-owned content. |
| Old/future record formats | Stated compatibility or safe rejection without mutation. |
| Active writer or two updaters | No double winner, stale publication or blindly removed lock. |
| Missing/damaged rollback wheel | Stop before destructive activation. |
| New empty installation | First useful task without fictitious missing project history. |
| New installation with an existing unmanaged project | Read-only inventory; no silent takeover. |
| Pipx versus dedicated venv | Prove ownership, interpreter and recovery separately. |

Windows and Ubuntu, Python 3.11–3.14 remain the baseline. Qualify the main 1.8.4 → 1.8.5 route across this matrix. Retain earlier qualified paths as regressions where appropriate; do not extrapolate to every historical wheel. ARM64, macOS, synchronized-storage placeholders and wrappers need explicit test rows or remain unqualified.

In synchronized-storage environments, distinguish notes, source projects, caches and installation state. Test placeholders, sync-conflict files and changing paths in an isolated Windows fixture. Move nothing automatically and never silently treat synchronization metadata as new active instructions.

### 11.2 Workloads

Keep `TINY_SHORT_SIMPLE`, `SMALL_LONG_SIMPLE`, `LARGE_LONG_COMPLEX` and `MEGA_VERY_COMPLEX`. Add independent axes for instruction length, source volume, file count, dependencies, mutations and resume points. [U1]

| Corpus | Purpose |
|---|---|
| 12 small sources | Startup and minimum overhead. |
| 240 mixed sources | Ordinary development and multiple topics. |
| 2,400 mixed sources | Many historical/current relationships and larger output. |
| 10,000 small sources | Metadata and path-scanning work; not equivalent to large data volume. |
| A large Markdown monolith and substantial JSON | Small useful passage, high read costs, parser/offset limits. |
| Sanitized representative Home Assistant/notes fixture | Realistic structure, versions, historical decisions and difficult queries. |

Use explicit budget profiles when a corpus exceeds defaults. A correct budget rejection is not a benchmark failure to bypass by disabling checks.

### 11.3 Long scenarios

Create multiple reproducible sequences with at least 100 state transitions: normal tasks, side questions, a changed dependency, rename/delete, duplicate identifier, partial index, stale source, resume, upgrade, rollback and Stop. Keep independent expected facts/outcomes and unanswerable questions.

Additionally test real host/LLM execution on an authorized, sanitized subset when provider claims are desired. Measure total task duration, all tool calls, retries, input/output tokens and final outcome. The previous 120 scripted steps do not replace this qualification.

## 12. P7 — measurement plan, freeze and artifacts

### 12.1 Fix the protocol before the code fix

Retain **100 warm AB/BA no-op pairs** for the main fixed profiles and **20 reset build/mutation trials**, as proposed in the supplied roadmap. Record seeds, corpus manifests, hardware, background load, power profile, Python/SQLite, import path and artifact identity. Warm process, fresh process and cold filesystem cache are separate conditions. [U1][E8]

Time latency without a profiler; measure profiler/heap/RSS separately. Report raw samples, p50, p95 and dispersion. The twelve component pairs and RSS snapshots are exploratory, not final p95/memory qualification. Python tracemalloc does not automatically cover all native SQLite allocations.

### 12.2 Acceptance and claims

| Dimension | Release boundary / decision rule |
|---|---|
| Safety and human data | Zero unexpected mutations or boundary violations in mandatory tests. |
| Mandatory task coverage | No silent omission of specified necessary facts/constraints. |
| Ordinary no-op | p50 and p95 at most 110% of fresh 1.8.4 on fixed profiles. |
| Historical 10k comparison | Optionally retain ≤70% of fresh 1.8.3 as an additional target, not a replacement for comparison with 1.8.4. |
| First build, mutation, retrieval, startup | Set regression budgets before measurement. Proposal: >10% requires analysis and an explicit decision. |
| Memory | Separate peak RSS and Python heap. Proposal: >15% requires analysis and an explicit decision. |
| Compact output | Same content within the same profile, correct byte accounting and lossless decoding. No mandatory universal percentage claim. |
| Provider tokens/costs | Claim only with complete task measurements on named host/model configurations. |

A 110% boundary means **a small permitted regression**, not faster operation. Publish speed claims only for routes with demonstrated improvement. Safety improvements may justify measured tradeoffs, but those tradeoffs must remain visible.

### 12.3 Freeze without an evidence loop

Freeze code, tests, schemas, documentation, version, packaging and CI. Keep associated results outside the frozen product source, bound to commit/tree/wheel/test harness. Every relevant subsequent change reopens the corresponding evidence route.

Use separate source-qualification and black-box artifact-qualification lanes. Run the artifact lane outside the checkout, without a source `PYTHONPATH`, recording `__file__` and import paths. Otherwise both lanes may accidentally test the same development source.

Before publication, run the full suite, coverage, quality gates, upgrades, artifact checks and all applicable gates against the exact same RC. A passing PR is insufficient if published bytes have a different identity. Publish only after separate approval and read back remote artifact bytes.

## 13. G00–G12 — release decision

This table is an execution contract, not a completed success checklist. Product status on delivery of the roadmap is **OPEN**, except explicitly excluded scope.

| Gate | Required evidence | Current status |
|---|---|---|
| G00 | Recoverable source bundle, clean identities, truthful dirty/version gate. | OPEN |
| G01 | Mapping/decision for each original audit finding and new finding. | OPEN |
| G02 | Exact 1.8.4 → candidate route and agreed additional version paths. | OPEN; state-model results are not installer evidence. |
| G03 | Interruption, offline recovery, idempotence, preservation of later edits. | OPEN; retained prototype evidence only. |
| G04 | Preserve existing consumers/format meanings; negotiate changes explicitly. | OPEN |
| G05 | Actual path, secret, read/write, budget and concurrency boundaries. | OPEN; no Windows race qualification in the research. |
| G06 | Coherent generation, FTS integrity, truthful freshness/coverage. | OPEN |
| G07 | Retrieval goldens, Unicode/JSON, exact IDs, mandatory facts; resolve COMP-184-01. | OPEN |
| G08 | Included VISUAL_ARTIST scope only: exact review/apply/repeat/rollback. | OPEN or explicitly DEFER; preserve existing v1 regression coverage. |
| G09 | Footer compatibility, non-blocking error handling and byte-exact structured output. | OPEN; retained wrapper probe only. |
| G10 | Explicit package/CLI handoff within scope; native activation separate. | CLI OPEN; native OUT_OF_SCOPE, not passed. |
| G11 | Product benchmarks and claim review; tokens unknown unless measured. | OPEN; retained component measurements only. |
| G12 | One RC identity, complete qualification, separate release approval and remote read-back. | OPEN |

DEFER requires an explicit scope decision before the final freeze, not a retrospective excuse for a failed safety test. A run without a final summary remains unproven. Historical test counts are not evidence for a new source tree. [U1]

## 14. Traceability to the original roadmap

| Original point | Preserved / clarified |
|---|---|
| Preservation and PORT/DEFER/REJECT | P0, including relevant untracked/ignored build inputs. |
| Three exact identities | P0/P7; simulation identity separate from the real candidate. |
| Measurement before the fix | P2/P7; predicted improvement is not measured evidence. |
| O(1), `2N+8`, zero reads/writes | Restated per operation, dataset and unit without weakening safety. |
| Junction, link and swap races | G05; actual platform tests required, not only a static symlink probe. |
| VISUAL_ARTIST-v1 readable, v2 writes | P5; broader compatibility decision because v1 already supports writes. |
| Exact footer / new version | Explicit existing host-envelope-v2 inventory, product route and failure isolation. |
| Freeze and source/artifact lanes | P7; evidence outside source, demonstrate imports from installed artifact. |
| 110% and historical 70% bounds | Retained with correct claim meaning and additional regression dimensions. |
| Upgrade and exact rollback | Primary P1 route; never roll old documents over new work. |
| G00–G12 / separate release decision | Preserved; prototype passes do not close product gates. |
| Historical open checkboxes | Preserve with a historical role; do not delete silently or index as current tasks. |

## 15. Handoff and first concrete task

**Start with P0, not installation.** Preserve local work, create the ledger and prepare an isolated clean reproduction. Then qualify a minimal upgrade from 1.8.4 while preserving durable bytes. Only afterward add measured performance and output improvements one at a time.

Each work-step handoff records at least: P/G ID, exact source identity, goal, expected write set, result, verification, open limitations and next step. Keep the record to what the next task needs. Link full logs outside the active context.

**Do not:** use the research simulator as an installer, publish its prototype version as product software, re-adopt existing projects, load every old note into one prompt, overwrite the original roadmap without retaining history, or present a passing component run as a perfect 1.8.5 release.

The original supplied note remains in the retained research bundle and is not republished here. This proposal changes only the **active 1.8.5 execution direction after review**; it does not rewrite historical facts.

## 16. Sources and research inputs

GitHub source references are pinned to the 1.8.4 commit. External documentation below was referenced by the preceding research on 17 September 2026; this documentation-publication action does not claim a new technical review of those pages.

### Retained research inputs

The following inputs are retained separately and **are not included in this public proposal**. Their labels identify provenance, not publicly downloadable evidence:

- **U1:** the complete owner-supplied original roadmap, retained unchanged in the research bundle. Private operational notes and local paths are not republished.
- **S1:** `simulation_results.json`, the sim2 main-run results, raw samples and 177 assertions.
- **S2:** `directed_results_sim2.json`, the directed coverage probe, open accent finding and twenty budget combinations.
- **Publication source:** `OPENCNTX_Roadmap_1.8.5_UPDATED_2026-09-17.md`, revision UPDATED-R2, SHA-256 `344957a0974e27baa47780cc98cb97d41915e42bf64c90424e89ac21e2aab857`.

A product qualification reviewer must obtain the authorized evidence or reproduce the experiments. Reported simulation results in this proposal are not independently verified release evidence.

[U1]: #retained-research-inputs "Owner source retained separately; not published"
[S1]: #retained-research-inputs "Main sim2 evidence retained separately; not published"
[S2]: #retained-research-inputs "Directed sim2 evidence retained separately; not published"
[B1]: https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.4 "Release and artifact metadata"
[B2]: https://github.com/CNTX-PROJECT/OPENCNTX/blob/6fc196b5ec90370c93c204a115ac58c73fd2bb32/src/opencntx/search_index.py "Search, snippets, output and FTS integrity"
[B3]: https://github.com/CNTX-PROJECT/OPENCNTX/blob/6fc196b5ec90370c93c204a115ac58c73fd2bb32/docs/install-and-update.md "Managed installation, ownership and recovery"
[B4]: https://github.com/CNTX-PROJECT/OPENCNTX/blob/6fc196b5ec90370c93c204a115ac58c73fd2bb32/src/opencntx/visual_integration.py "Existing VISUAL_ARTIST-v1 writes and rollback"
[B5]: https://github.com/CNTX-PROJECT/OPENCNTX/blob/6fc196b5ec90370c93c204a115ac58c73fd2bb32/tools/release_version_gate.py "Version and release states"
[B6]: https://github.com/CNTX-PROJECT/OPENCNTX/blob/6fc196b5ec90370c93c204a115ac58c73fd2bb32/src/opencntx/presentation.py "Existing host envelope v2 and presentation"
[E1]: https://www.sqlite.org/fts5.html "SQLite FTS5 tokenization, external content and integrity"
[E2]: https://docs.python.org/3/library/os.html#os.replace "Python filesystem operations and replacement"
[E3]: https://pip.pypa.io/en/stable/topics/secure-installs/ "Hashed installation inputs"
[E4]: https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens "OpenAI input-token counting"
[E5]: https://platform.claude.com/docs/en/api/typescript/messages/count_tokens "Anthropic message-token counting"
[E6]: https://ai.google.dev/gemini-api/docs/tokens "Gemini token counting and usage"
[E7]: https://www.sqlite.org/atomiccommit.html "SQLite transactions and failure models"
[E8]: https://pyperf.readthedocs.io/en/latest/analyze.html "Benchmark analysis and measurement variation"

**Important:** citing source code does not mean the complete product was executed. Planned acceptance criteria are design proposals. Only the explicitly labeled simulation measurements originate from the prior component lab, and none qualifies a product release by itself.
