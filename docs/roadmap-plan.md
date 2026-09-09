---
title: OPENCNTX 1.7.2 — Recovery, simplification and targeted improvement
project: OPENCNTX
type: roadmap
status: planned
created: 2026-09-09
updated: 2026-09-09
planning_revision: 3
source_versions: ["1.7.0", "1.7.1"]
source_commit: 6b80cc41529653eac0b16b4238a4b7692eebb4f7
published_baseline: 1.7.1
target_version: 1.7.2
analysis_basis: "Deep review of versions 1.7.0 and 1.7.1"
publication_scope: roadmap-only
---

# OPENCNTX 1.7.2 — Recovery, simplification and targeted improvement

[Overview](roadmap.md) · [README](../README.md) · [Current release](release-1.7.1.md)

## 1. Direction and current status

**Goal:** preserve the useful techniques while making their interaction simpler and more reliable. Reduce unnecessary stops, questions and wasted context; prevent unjustified internal blocks; make updates predictable, with no unexplained active remnants.

The guiding rule is: **improve transitions, not the number of rules.** Authority, verification evidence, native progress, memory views and the active installation each have a distinct responsibility. A failure in an optional component must not restart the entire task.

This revision replaces the previous public plan. It incorporates the deeper 1.7.0/1.7.1 review, retains earlier recovery work and keeps task identifiers N01–N24. There is one execution backlog; analyses remain sources, not competing task trackers.

| Item | Status |
|---|---|
| Reviewed baseline | 1.7.0 and 1.7.1; runtime identical except for the version number |
| Published baseline | 1.7.1, commit `6b80cc41529653eac0b16b4238a4b7692eebb4f7` |
| Meaning of 1.7.1 | Published documentation and roadmap, not their implementation |
| Planning | Revision 3; 24 tasks; none of the new tasks completed |
| Active implementation task | None — roadmap preparation only |
| Next implementation step | N01, followed by the targeted regression baseline N02 |
| Next version | 1.7.2; existing tags and releases remain unchanged |
| Publication of this revision | A published plan, not software release 1.7.2 |
| Local installation and activation | Outside roadmap publication scope |

A phase is a grouping, not a mandatory pause. Preparing the roadmap does not authorize implementation. Once implementation is requested, ordinary implementation and verification within that scope do not require repeated permission. Publication, installation and broad activation are separate effects requiring a concrete instruction.

### Reuse existing evidence

The deeper review contains eight newly reproduced behaviors D01–D08 and two source/architecture findings D09–D10. Results were equal on both releases. Another 60 existing targeted tests passed on 1.7.1. This demonstrates preservation of those tests, not resolution of the new findings.

Earlier F04–F16 remain relevant wherever their code is unchanged. F01–F03 include release provenance, version communication and publication order: individual publications improved, while structural automation remains planned. Valid evidence need not be collected in full again every session.

**Historical lesson:** the reported stop loop came from leftover user-wide hooks. This roadmap therefore introduces no universal stop marker, mandatory global completion hook or system-wide cleanup.

## 2. Techniques retained and additions avoided

| Retained technique | Explicit boundary |
|---|---|
| Local context bundles, source selection and hashes | Establish bytes, not truth or authority |
| Ledger, receipts, original outcomes and AUTO PILOT | One authoritative progress state; every mutation bound to its intended task |
| Three proportional work profiles | Stronger verification never grants additional authority |
| Verification leases and reusable checks | Only relevant changes invalidate a check |
| Evidence-based recovery and fingerprints | A new approach within valid scope; no mandatory scope expansion |
| Combo, supersession and compact knowledge | Presentation limits never discard a still-valid decision |
| Adaptive storage, deduplication and optional index | Search coverage and current source binding are visible |
| Connected state and compact resume information | A derived view, not a second planner or progress authority |
| Update journal, staging and generations | Each reader sees one combination; data and registrations have separate compatibility |
| Provider-neutral adapters | Optional; described as proven integrations only when actually connected |

No complete rewrite, new universal policy engine, mandatory model call, vector server, extra coordination agent, daemon, cloud stack or large GUI. Add a component only when an observed problem cannot be solved more simply with existing building blocks.

This is a product plan, not a new user-wide host instruction. Historical analyses, old rules and this document are not automatically loaded as additional execution policy on every AI turn.

## 3. Five user requirements and eight correctness invariants

| Requirement | Intended result | Evaluation |
|---|---|---|
| U1 — Fewer stops and questions | Continue within clear existing scope | Zero unnecessary internal reconfirmations in the defined positive scenario set |
| U2 — No unnecessary token cost | Relevant context, reusable checks and compact output | No model calls for bookkeeping; no unexplained overhead regression at equal task correctness |
| U3 — Proportional protection | One current decision path; isolated optional failures | Old policy copies gain no additional authority; the healthy core remains usable |
| U4 — No unjustified internal refusals | Correct action/target binding and recovery from stale blocks | Zero false internal refusals in permitted scenarios; external causes identified separately |
| U5 — Clean updates | One explained active generation with safe recovery | No orphaned owned active registrations; user data preserved; explainable rollback and cleanup |

OPENCNTX cannot override host policy, provider limits or missing access. It can fix its own unjustified refusals, avoid pointless repetition and allow independently permitted work to continue. “Never refuse again” is not a supportable universal guarantee.

These are test invariants, not eight additional approval screens:

1. **I1:** promotion or a cache miss never gives an answer-only task write permission.
2. **I2:** revoked or changed authority is never reused through old evidence.
3. **I3:** the same operation ID can never complete two different tasks.
4. **I4:** an optional failure never retrospectively turns a successful native commit into “nothing happened.”
5. **I5:** every open obligation remains canonical and directly reachable.
6. **I6:** every still-valid decision remains findable by ID and can be correctly superseded.
7. **I7:** incomplete search is never presented as complete absence.
8. **I8:** a reader sees one compatible runtime generation; cleanup never touches unrelated or still-needed data.

### Execute without additional bureaucracy

- Ask only when decision-critical information is missing or a materially new effect lies outside the instruction. Group known choices.
- Passing a test, completing a subtask or crossing a phase boundary is not itself a reason to stop.
- Use one retry budget per concrete operation; layers must not silently multiply retries.
- Suppress the same failed approach when nothing relevant changed. New bounded diagnostics may still gather useful evidence.
- Respect an actual stop or scope change. Block only the dependent path.
- Keep lengthy raw logs outside default context. Retain one reference, result and limitation.
- No separate dossier per tool call, new policy note per failure or model call to maintain counters.
- Required CI still applies. Local test selection and evidence reuse do not bypass repository rules.

## 4. Execution order and delivery scopes

| Phase | Result | Tasks |
|---|---|---|
| A — Known baseline | Reusable evidence, real regressions and early measurements | N01–N02; baseline from N16 |
| B — Correct transitions | Correct authority, retry-safe progress, bounded side effects and critical input validation | N03–N09 |
| C — Understandable daily work | Diagnostics, reliable memory, compact resume and demonstrated efficiency | N13–N17; N20 where needed |
| D — Clean lifecycle | Installation-channel ownership, generations, readers, data compatibility and recovery | N10–N12 |
| E — Selected practical expansion | One real adapter, optional export and an appropriate pilot | N18–N21 |
| F — Evidence-backed release | Source-bound build, verified scope and checked publication | N22–N24 |

**Initial recovery order:** N01 → targeted N02 baseline → N03 → N04. Prioritize D01/D02 in N03 and give D06 an explicit implementation unit in N04. Then address relevant sync, recovery, input and isolation defects. Capture the N16 baseline before changing the behavior being measured, not at the end.

This is not an instruction to run parallel agents. Independent work may be prepared alongside other tasks provided files and responsibilities do not conflict. N05/N06, N07/N08 and N22 need not wait for every later feature.

### Four possible delivery scopes

- **Recovery core:** concrete defect fixes and retry-safe transitions. No claim that the complete updater or every host integration is ready.
- **Daily simplicity:** connected lightweight routes, diagnostics, memory/resume and initial comparable measurements.
- **Clean update:** one fully proven installation route with reader and data rollback boundaries.
- **Practical expansion:** only selected adapter/export features and substantiated usage claims.

These are scope choices, not four mandatory releases. When implementation is requested, N01 selects one initial bounded scope from that instruction; N23 evaluates precisely that scope. Undelivered work stays open. A narrow defect fix need not wait for a two-week pilot; broad savings or adoption claims require appropriate practical evidence.

## 5. Tasks N01–N09 — Baseline and correct transitions

### N01 — Establish source, initial delivery scope and baseline

- [ ] **Status: Planned**

**Work:** confirm the actual checkout and changes; use the reviewed 1.7.1 commit as a reference. Record one initial delivery scope and relevant U/I criteria. Link existing audit evidence rather than copying it. Select fixed scenarios and capture a minimal baseline before behavioral changes; N16 expands it later. Keep design choices in the task log or existing code/documentation.

**Done when:** source and instruction are unambiguous, user changes are preserved, claimed scope is bounded and its baseline is available or explicitly limited. No new release or installation status is implied.

**Depends on:** none. **Source:** deeper review chapter 1; F01–F03.

### N02 — Turn audit probes into real regressions and state tests

- [ ] **Status: Planned**

**Work:** adopt D01–D08 and relevant F04/F07/F08/F09 as bounded regressions. Assert desired invariants, not continued existence of a defect. Make local red/green behavior visible; keep the final change coherent with its fix. Add action sequences: start, retry, change facts, revoke, crash and resume. Use the existing test infrastructure.

**Done when:** every relevant fix has a probe that detects the old defect and checks the desired result. The shared harness is ready; task-specific cases grow with implementation. Tests write only into their own temporary fixtures. A helper test is not counted as a real host test.

**Depends on:** N01. **Source:** D01–D08, I1–I8.

### N03 — Separate authority, verification strength and blocks

- [ ] **Status: Planned**

**Work:** fix D01 and D02. Bind actions to concrete targets and the current instruction; support explicitly bound multiple targets and permitted external actions. Compute risk profile, current blocking reasons and permitted actions separately. Restored authority requires valid rebinding; a changed boolean is not independent authority evidence. Reuse existing path primitives; harmonize new checks in N09.

**Done when:** answer-only tasks never allow writes; a stale lease causes only relevant revalidation; demonstrably resolved blocks disappear; scope expansion and revocation are handled correctly. Positive multi-target scenarios do not repeatedly request permission.

**Depends on:** N02. **Source:** D01–D02, F07; I1–I2, U1/U3/U4.

### N04 — Connect lightweight routes and make progress retry-safe

- [ ] **Status: Planned**

**Work, explicitly as one critical mutation chain:**

1. Bind each progress mutation to an operation ID, expected task, relevant parameters and expected revision.
2. Persist operation outcome and progress within the same proven local commit boundary.
3. The same ID and parameters return the previous result; the same ID with different parameters is rejected.
4. Separate the native result from later sync, presentation and diagnostic failures.
5. Connect ANSWER_ONLY, LIGHT_TASK and GOVERNED_FLOW to actual user routes, measuring real writes and output.
6. Fix D08: new relevant evidence and a different approach may be evaluated within the same already fully examined chain.

**Done when:** the D06 lost-response probe never completes the next task; retries after a crash resume the same operation; answer-only tasks cause zero project mutations; lightweight tasks do not require a full dossier. Retry layers share one bounded operation state. Recovery never increases authority or mandates additional tasks.

**Depends on:** N03. **Source:** D06/D08/D09, F13/F16; I1–I4.

### N05 — Bind sync to immutable bytes and its own delivery identity

- [ ] **Status: Planned**

**Work:** make the reviewed snapshot the delivery source. Check destination, source identity and privacy declaration with their correct meanings. A change between preview and delivery yields the same snapshot or a targeted drift report. Keep a small delivery intent and retry identity, not a second progress ledger. Do not build a daemon without a concrete requirement.

**Done when:** every delivered byte belongs to the reviewed manifest; the local sync-race regression passes; repeat delivery cannot silently change the snapshot or duplicate the logical operation. Unknown external outcomes are read back first or handled through supported idempotency.

**Depends on:** N04. Snapshot probes may be prepared after N02. **Source:** F04, D06; I3–I4.

### N06 — Bound external processes and optional failures

- [ ] **Status: Planned**

**Work:** bound Git/subprocess duration, output, retry count and relevant process trees on supported platforms. Distinguish local commit, delivery and error recording. An unavailable adapter must not create a global stop loop. Use a simple adapter pause after repeated failures only where needed. A “private repository” declaration is not independent provider evidence.

**Done when:** hanging fixture processes stop within the specified bound; double fault injection after commit preserves the native result; independent local work remains possible. An error that cannot itself be recorded is reported compactly, not retried indefinitely.

**Depends on:** N04–N05. **Source:** F05/F06, D06; I4, U1/U3.

### N07 — Validate target identity and update/sidecar overlap before writes

- [ ] **Status: Planned**

**Work:** make concrete target identity and scope overlap reusable. Handle equal paths, parent/child scope, patterns, candidate/active/backup overlap, case behavior, symlinks and Windows reparse points. Unresolved scope must not receive a proven-isolation label. Resolve it or return a targeted error rather than optimistic string comparison.

**Done when:** D03 and overlapping update components are detected before writes. Disjoint concrete targets remain permitted. Tests distinguish file paths, directory scopes, platform identity and targets that do not yet exist. Do not force case-insensitive behavior onto every platform.

**Depends on:** N02. **Source:** D03, F08/F11; I2/I8.

### N08 — Make capsules unique, strict and resource-bounded

- [ ] **Status: Planned**

**Work:** require unique normalized manifest paths and unique archive members, correct field types and an unambiguous mapping. Bound counts, manifest size, individual and total expanded bytes before and during reading. Stream hashing where appropriate. Separate archive integrity from valid imported project state.

**Done when:** the duplicate probe is rejected; unexpected members, invalid paths/types and limit overruns terminate safely; ordinary existing capsules remain readable under the compatibility agreement. Small fixtures establish boundary behavior without exhausting the machine.

**Depends on:** N02. **Source:** F09–F11.

### N09 — Harmonize critical primitives without a broad rewrite

- [ ] **Status: Planned**

**Work:** inventory only checks actually used by N03–N08 and the updater. Harmonize critical JSON, digest, path and write helpers in the existing lightweight utility layer. Separate domain errors from pure utilities. Retain temporary compatible re-exports where needed; do not silently change durable formats. Reduce D10 coupling on actual change paths.

**Done when:** changed routes apply the same intended validation, existing compatibility fixtures pass and no unwanted dependency cycles are introduced. Fewer private imports are supporting evidence, not a goal that may break behavior. Do not rewrite unrelated modules defensively.

**Depends on:** N03, N07, N08. **Source:** F11, D10.

## 6. Tasks N10–N12 — Clean update lifecycle

### N10 — Define one installation route, ownership and compatibility

- [ ] **Status: Planned**

**Work:** select one concrete installation route for the first update delivery. Define package-file ownership and use the appropriate channel adapter rather than mixing managers. Inventory installation ID, active executable/generation, owned registrations, user data and reader/writer compatibility. Describe data migration and rollback boundaries before building mutations.

**Done when:** the ownership manifest distinguishes managed files from unrelated and customized content; a new clone is not treated as evidence of a newly active installation; supported old formats and rollback limits are explicit. One channel is selected; unknown channels are not silently supported.

**Depends on:** N01, N07. **Source:** F12/F13, deeper review chapter 5; U5/I8.

### N11 — Implement a generation-based updater with repeatable transitions

- [ ] **Status: Planned**

**Work:** inventory → plan → prepare a complete candidate → verify → select one generation → confirm active state → ownership-bound cleanup. Build on existing staging/journal/receipt techniques. Each reader binds once to its generation. Existing readers may temporarily retain an old generation. Identical updates become genuine no-ops.

**Done when:** crash injection across phases produces consistent recovery; the same update is not applied twice; one reader never sees a mixed combination. Data rollback matches the formats used. Open Windows files cause explained deferred cleanup, not blind deletion. Claim atomicity and durability separately and only within proven filesystem boundaries.

**Depends on:** N04, N07, N09, N10. **Source:** F08/F12; I3/I8.

### N12 — Prove upgrade, rollback, uninstall and hook-remnant handling

- [ ] **Status: Planned**

**Work:** test fresh installation, repetition, upgrade with an active reader, crashes around selection, insufficient disk space, a missing candidate, changed owned configuration, unrelated entries, incompatible data, rollback and uninstall. Add a historical-hook fixture containing an owned registration pointing to a deleted version path. Test the intended Windows/Linux routes exclusively in isolation.

**Done when:** user data survive; removal touches only demonstrably owned, unused components; one selected rollback set and necessary reader generations are explained. No owned active registration is orphaned. “No clutter” means no unexplained state, not immediate destruction of necessary recovery evidence.

**Depends on:** N11. **Source:** historical recovery incident, U5/I8. **Boundary:** fixture execution does not install into an existing user environment.

## 7. Tasks N13–N17 — Simplicity, memory and measured efficiency

### N13 — Provide one read-only diagnostic entry point

- [ ] **Status: Planned**

**Work:** show instruction/scope, internal blocking reason, native result, optional deliveries, active runtime and relevant configuration origins compactly. Distinguish core corruption, stale views, unavailable adapters and missing authority. No system-wide scan or automatic global configuration reset.

**Done when:** diagnosis changes neither project nor host and does not create a missing store. D06 and D07 produce understandable partial successes, not misleading total failures. Each problem has one current explanation and the smallest next step. Extend installation fields when N10–N12 exist; never invent them.

**Depends on:** N04, N06. **Source:** V05, D02/D06/D07, U1/U3/U4.

### N14 — Preserve canonical memory and compact resume without information loss

- [ ] **Status: Planned**

**Work:** separate canonical decisions and obligations from Combo/connected presentation. Preserve stable IDs, source, scope and lifecycle; recency limits must not remove active decisions. Provide targeted details and controlled supersession. Build a small startup bundle with goal, scope, current task, open outcomes, blocks and next action.

**Done when:** D04 and D07 are fixed; the 33rd decision cannot displace still-current truth from search; explicit supersession remains possible. Large roadmaps fit through a compact root and checked detail references. Every original outcome remains reachable after a chat reset. Presentation failure does not block an already successful native mutation.

**Depends on:** N04, N09. **Source:** D04/D07, V07; I5–I6.

### N15 — Make search coverage, context budgets and verification caching explicit

- [ ] **Status: Planned**

**Work:** fix D05 with explicit completeness and a source-version-bound scan cursor. Look up exact record IDs directly where possible. Separate result limit, scan work and time budget. Select context for the current task and source references. A delta requires a known baseline; otherwise provide a complete compact startup bundle. Reuse checks by genuinely relevant dependencies, independently of authorization.

**Done when:** audit record Z is not implied absent after an interrupted scan; resumed queries never silently combine changed stores. Unchanged checks are reused; relevant changes invalidate them. Bytes, estimated tokens and actual host usage are clearly distinct measurements. No model call performs selection bookkeeping.

**Depends on:** N03, N09, N14. **Source:** D01/D05, V06; I1/I2/I7, U2.

### N16 — Compare friction and task results before and after changes

- [ ] **Status: Planned**

**Work:** begin baseline measurement with N01. Use fixed tasks covering answers, small changes, multiple targets, resume, revoked scope, adapter failure and bounded recovery. Measure actual writes, context/tool-output size, repeated checks, questions, retries, time and correctness. Add reliable host usage when available; no hidden external telemetry or complete prompt archives.

**Done when:** baseline and follow-up have comparable source/host conditions, outliers are visible and cost estimates are labeled. Never average away lost correctness or user data in exchange for speed. Resolve unexplained regressions in selected claims; without reliable usage, make no currency or percentage savings claim.

**Depends on:** measurement starts after N01; follow-up after changed routes, including N04/N14/N15 for broad simplicity claims. **Source:** U1–U4, F15.

### N17 — Align user routes and feature claims with code

- [ ] **Status: Planned**

**Work:** simplify quickstart and explanations for answers, small tasks, resume and updates. Bind claims to a concrete route and evidence level: contract present, locally connected, adapter proven or practice measured. Distinguish release, installation and activation status. A computed shard count does not demonstrate a connected storage route.

**Done when:** examples run on the selected candidate and each claimed benefit has appropriate evidence. Open roadmap work is never described as a delivered feature. Provide one short starting point with detail links, not repeated policy/history archives.

**Depends on:** N04, N13–N16; update claims also require N12. **Source:** D09, F02/F16.

## 8. Tasks N18–N21 — Optional expansion and practical evidence

### N18 — Prove one small real host adapter

- [ ] **Status: Planned — scope-dependent**

**Work:** select one available host and adapter contract. Connect only necessary capabilities to proven native routes. No global Stop hook by default. Test real authority, an answer without writes, a lightweight task, resume, revocation, adapter outage and operation retry. Without actual host access, describe fixtures only as fixtures.

**Done when:** the selected real adapter demonstrably works and its failure affects only that connection; the local core remains usable without it. Native host authority remains controlling. Do not infer provider-wide guarantees from one working host.

**Depends on:** N04, N06, N13–N15; N10 for managed registration. **Source:** F13/D09, U1/U4.

### N19 — Provide controlled one-way export to Obsidian

- [ ] **Status: Planned — scope-dependent**

**Work:** export derived readable information only to the selected directory. Bind export to source revision, target and operation ID; manage only owned generated files. Preserve human changes through a conflict status or separate conflict copy. Do not implicitly solve this by placing a live transactional machine store in a shared note directory.

**Done when:** repetition creates no duplicates, unrelated notes remain untouched, source changes are visible and unavailable export does not stop the core. No broad vault access, bidirectional sync or extra installed integration without concrete scope.

**Depends on:** N05–N07, N14. **Source:** V12, I3–I6.

### N20 — Optimize only demonstrated storage and dependency problems

- [ ] **Status: Planned**

**Work:** measure ledger reads/writes, Combo generations, index consistency and query work on fixed small and larger datasets. A changed search index remains derived from the correct canonical source. Investigate targeted impact maps and symbol selection only after a simple baseline comparison. Reduce D10 coupling on measured or error-prone paths.

**Done when:** each change addresses a measured bottleneck and shows repeatable improvement without semantic regression. Add no mandatory database, daemon or embeddings without necessity. When no relevant bottleneck exists, documented measurement and a “no change needed” decision are sufficient.

**Depends on:** N01 for measurement; N09/N14/N15 to evaluate those new routes. **Source:** D05/D10, F14.

### N21 — Run a practical pilot for broad usage claims

- [ ] **Status: Planned — required for broad adoption claims**

**Work:** retain the earlier pilot baseline: at least two weeks, 25 real tasks and three genuine restart/handoff events. Select representative tasks and define the host/efficiency claims in advance. Use N16 measurements, record failed and abandoned tasks too, and distinguish product, host and external causes.

**Done when:** the actual pilot meets the agreed size, claim-relevant problems are resolved or bounded as limitations and real results can be read back. Synthetic tasks test the harness but never count as pilot success. Insufficient practical evidence remains unknown, not green.

**Depends on:** N16–N17 and all claimed features; N18 for host claims, N12 for update claims. **Source:** F15, U1–U5.

## 9. Tasks N22–N24 — A release that demonstrates its contents

### N22 — Automate correct release provenance

- [ ] **Status: Planned**

**Work:** automate the chain from final source identity through tests and build to exactly bound tags/artifacts and verification. Start from the current four distribution files. Build from the final commit/tree, not an earlier PR head. Reuse successful checks only when their validity is demonstrated and repository rules permit; avoid unnecessary repeated full local runs.

**Done when:** source mismatch, wrong version and missing required final CI prevent candidate publication; build record and distribution refer to the same final source. Label unsigned provenance as unsigned. Signing/TUF may later strengthen the download chain; they are not mandatory extra infrastructure for the recovery core.

**Depends on:** N01. **Source:** F01–F03, V09.

### N23 — Evaluate delivered scope and the candidate

- [ ] **Status: Planned**

**Work:** prepare the fixed target version 1.7.2 from actual delivered work. Bind each release claim to implemented behavior, current tests and relevant measurement. Evaluate platform skips, compatibility, migration/rollback explanations and known limitations. Include only appropriate N tasks; the word Stable must not imply unproven benefits.

**Done when:** every task and criterion within the selected delivery scope is demonstrably complete, no known material defect contradicts a claimed behavior and undelivered work remains explicitly open. A narrow fix release may be ready without a broad pilot, but cannot claim proven general savings or host adoption.

**Depends on:** N22, relevant N17 documentation and all selected-scope tasks; broad practical claims require N21. **Source:** D09, U1–U5 as applicable.

### N24 — Publish and perform public readback when instructed

- [ ] **Status: Planned — not a current publication step**

**Work:** use the concrete publication instruction for the selected candidate. Publish exactly the verified tag and four assets; check latest/release status. Update the current README, changelog, roadmap, installation/release information and relevant public website source. Do not publish a private note directly: remove local paths and personal recovery context from its public derivative.

**Done when:** actual downloads have been checked byte-for-byte, commit/tree and metadata agree, and public claims have been read back. Do not claim a hosted website or wiki when only source exists. Publication does not mean local installation, hook activation or completion of optional roadmap tasks.

**Depends on:** N23 and a concrete publication instruction. **Source:** F01–F03, V09/V10.

## 10. Acceptance scenarios by delivery scope

| Scenario | Minimum expected outcome | Owning task |
|---|---|---|
| Answer plus expired lease | No writes; relevant revalidation only | N03–N04 |
| Resolve a block / revoke authority | Current reasons; valid rebinding or a block respectively | N03 |
| Multiple permitted targets | One bound scope; no artificial single-target refusal | N03 |
| Response lost after progress commit | Same task result returned; next task not completed | N04 |
| Sync and error recording both fail | Native result remains visible; bounded retry | N04/N06 |
| Full chain already examined, new evidence | New bounded approach without mandatory extra task coverage | N04 |
| Directory/pattern/alias beside active writer | Overlap resolved or rejected; never unproven ISOLATED | N07 |
| Duplicate capsule / exceeded limit | Targeted rejection before uncontrolled processing | N08 |
| 33rd current decision | Older current decision remains findable and replaceable | N14 |
| Large roadmap and a new chat | All outcomes reachable through compact root and details | N14 |
| Z outside the examined search portion | Partial coverage plus a safe continuation route | N15 |
| Irrelevant change versus authority change | Appropriate check reuse versus mandatory invalidation | N15 |
| Update with an old reader and a crash | One generation per reader; explained rollback/cleanup | N11–N12 |
| Broken owned hook beside unrelated configuration | Targeted diagnosis; unrelated material untouched | N12–N13 |
| Real host task and optional export failure | Core remains usable; fault stays within the adapter | N18–N19 |

Keep evidence levels separate: pure contract test, temporary native fixture, process/filesystem test, real adapter and practical pilot. No level automatically receives the claims of a higher level. N02 stateful sequences check I1–I8 across multiple steps.

## 11. Complete traceability

### New deeper review

| Finding | Tasks |
|---|---|
| D01 — Stale lease gives an answer task a write indication | N02–N04, N15 |
| D02 — Stale block persists | N02–N04, N13 |
| D03 — Sidecar compares strings only | N02, N07, N09 |
| D04 — Active Combo decision disappears from the query layer | N02, N14 |
| D05 — Search budget hides incompleteness | N02, N15, N20 |
| D06 — Retry can complete the next task | N02, explicit mutation chain N04, N05–N06 |
| D07 — Valid larger roadmap exceeds the current-view budget | N02, N04, N13–N14 |
| D08 — Recovery requires impossible mandatory expansion | N02, N04 |
| D09 — Contract versus connected user route | N04, N17–N18, N23 |
| D10 — General helpers coupled to product logic | N09, N20 |

### Earlier review — no silently dropped findings

| Findings | Tasks |
|---|---|
| F01 build/tag, F02 version claims, F03 CI/publication | N01, N17, N22–N24 |
| F04 sync bytes, F05 Git timeout, F06 privacy declaration | N05–N06 |
| F07 authority/targets | N03–N04 |
| F08 update-path overlap | N07, N11–N12 |
| F09 capsule duplicates, F10 resource bounds | N08 |
| F11 critical JSON/path validation | N07–N09 |
| F12 composite update/atomicity | N10–N12 |
| F13 host contract versus integration | N04, N13, N17–N18 |
| F14 ledger/storage growth | N20 |
| F15 unproven practical benefit | N16, N21, N23 |
| F16 heavyweight onboarding | N04, N13, N17 |
| Historical global-hook incident | N10–N13, N18 |

| Earlier proposal | Retained task scope |
|---|---|
| V01 authority and fewer questions | N03–N04, N18 |
| V02 reliable sync | N05–N06 |
| V03 clean update lifecycle | N07, N10–N12 |
| V04 capsule/input validation | N08–N09 |
| V05 diagnostics | N13 |
| V06 economical context | N15–N16 |
| V07 compact resume | N14 |
| V08 optional host | N18 |
| V09 release provenance | N01, N22–N24 |
| V10 explanations and feature status | N04, N17, N23–N24 |
| V11 storage optimization | N20 |
| V12 Obsidian export | N19 |

Expansion themes do not create a second backlog: effective-state explanations belong to N13; memory/context differences to N14–N15; local friction reporting to N16; health across generations to N10–N13; impact maps to N20. Old R01–R32 identifiers remain historical references in earlier analyses, not active task numbers.

## 12. Progress, decisions and resume

Statuses: **Planned**, **In progress**, **Blocked**, **Done**, **Deferred**. Only Done gets a checked box. A task is Done only when its selected acceptance criteria are actually proven; “the helper exists” or “the tests are green” cannot substantiate a broader claim.

For scope-dependent work, Deferred means outside this delivery, with a short reason. Never silently convert it into delivered work. A blocked task records its cause and the smallest needed change. Independently instructed work may continue.

Use this log for meaningful results and choices. Do not maintain a second live roadmap, separate status file or extensive decision dossier when a short log entry and existing evidence suffice.

| Date | Event | Result | Resume point |
|---|---|---|---|
| 2026-09-09 | Planning revision 3 from deeper 1.7.0/1.7.1 review | N01–N24 retained and expanded; D01–D10 and earlier F/V findings mapped; no implementation started | N01 when implementation is instructed |
| 2026-09-09 | Target version explicitly fixed | Next update is 1.7.2; published baseline remains 1.7.1 | N01 when implementation is instructed |
| 2026-09-09 | Public language alignment | Complete public plan and current navigation provided in English; planning scope unchanged | Implementation remains separate |

**Compact resume record:** current instruction and scope; active task; last verified result; relevant files/commit; remaining work; blocker if any; next concrete step. Then read only relevant analysis sections and evidence. The entire old chat, every policy and all analyses need not enter context again.

**No automatic model/cost claims:** this roadmap mandates no model and promises no number of hours or tokens. Model choice follows the current instruction/host. N16 demonstrates efficiency; profile names do not.

## 13. Sources and validity boundaries

- [Release 1.7.1](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.1) and [final CI](https://github.com/CNTX-PROJECT/OPENCNTX/actions/runs/34395546489) — published baseline, not proof that this roadmap is implemented.
- [Changes from 1.7.0 to 1.7.1](https://github.com/CNTX-PROJECT/OPENCNTX/compare/v1.7.0...v1.7.1) — runtime difference limited to the version number.
- [Governance](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/governance.py), [progress](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/continuity.py) and [recovery](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/recovery.py) — reviewed contracts and transitions.
- [Combo](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/combo.py), [adaptive storage](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/adaptive_storage.py) and [connected state](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/connected_state.py) — memory, search coverage and derived views.
- [Updater](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/transactional_update.py) and [sync](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.1/src/opencntx/continuity_sync.py) — existing implementation building blocks.
- [Known release limitations](release-1.7.0.md) and [1.7.1 scope](release-1.7.1.md) — earlier findings and publication boundaries.

The D findings originate in the underlying targeted review; N02 must incorporate their audit probes as public regression tests. Private notes and local evidence files are not published.

This publication supplies only the 1.7.2 roadmap. It supplies no new runtime functionality, release assets, installation or host activation. The currently published software remains 1.7.1.

