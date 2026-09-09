---
title: OPENCNTX 1.7.3 — Reliable progress, memory and updates
project: OPENCNTX
type: roadmap
status: planned
created: 2026-09-09
updated: 2026-09-09
planning_revision: 4
source_versions: ["1.7.0", "1.7.1", "1.7.2 local-candidate"]
source_commit: f6edbbf6d9d81310c37a55036f7d9794e38e109b
source_tree: 4ab2857f55861247c326694940518c25204b1675
published_baseline: 1.7.1
target_version: 1.7.3
publication_scope: roadmap-only
---

# OPENCNTX 1.7.3 — Reliable progress, memory and updates

[Roadmap home](roadmap.md) · [Documentation](README.md) · [Releases](releases.md) · [Project home](../README.md)

**Revision 4 · Target: 1.7.3 · Published software: v1.7.1.**

This publishes the plan, **not software release 1.7.3**. No new runtime
functionality, installation or host activation is delivered by this document.
The source package remains the unreleased 1.7.2 candidate until implementation
prepares an actual new candidate.

## Contents

- [Direction and evidence](#1-direction-and-evidence)
- [Base scope and deferred extensions](#2-base-scope-and-deferred-extensions)
- [User outcomes and invariants](#3-user-outcomes-and-invariants)
- [Execution order](#4-execution-order)
- [Core work: N01–N09](#5-core-work-n01n09)
- [Updates, memory and usability: N10–N17](#6-updates-memory-and-usability-n10n17)
- [Extensions and optimization: N18–N21](#7-extensions-and-optimization-n18n21)
- [Candidate and publication: N22–N24](#8-candidate-and-publication-n22n24)
- [Acceptance scenarios](#9-acceptance-scenarios)
- [Traceability](#10-traceability)
- [Working rules](#11-working-rules)
- [Status and next step](#12-status-and-next-step)
- [Evidence and design references](#13-evidence-and-design-references)

## 1. Direction and evidence

**Make existing useful techniques work reliably together.** The core goals are
fewer unnecessary stops and questions, no duplicate task progress after retries,
reachable project memory, compact resumption, and coherent updates.

This revision replaces the earlier plan while retaining **N01–N24**. It
incorporates the 1.7.0/1.7.1 review, the 1.7.2 candidate stress assessment,
related-system research and design proposals T01–T12. This document is the
single implementation backlog; the roadmap home is its summary.

| Item | Evidence snapshot on September 9, 2026 |
|---|---|
| Published baseline | v1.7.1; publishing documentation did not implement the planned runtime work |
| Reviewed candidate | 1.7.2 at commit `f6edbbf6d9d81310c37a55036f7d9794e38e109b` |
| Next implementation target | 1.7.3; historical test results are not relabeled as 1.7.3 results |
| Long simulations | Two routes each completed 100 tasks |
| Targeted shortcomings | Twelve unmet criteria in separate fault probes |
| Additional update evidence | Mixed-generation reads and recovery blocked after hard process termination |
| Current implementation status | Base tasks planned; N18, N19 and N21 explicitly deferred |

**This is not an 88/100 result.** The twelve targeted criteria are not twelve
failed tasks from one hundred. Long-route completion, fault probes and update
tests remain separate evidence categories.

Preserve native progress, dependency planning, receipts, process handoff,
capsules, writer exclusion, staging, backups and reachable exception rollback.
Fix their transition contracts rather than adding another broad policy layer.
Do not introduce global stop hooks or reset unrelated host configuration.

## 2. Base scope and deferred extensions

The proposed base release covers native correctness and resumption, project
memory, bounded optional synchronization, and **one managed local update
channel with a proven lifecycle**. It is a substantive recovery release, not a
version-only publication.

| Required base scope | Retained but outside the base |
|---|---|
| Correct the twelve criteria through actual product routes | N18: one additional real host adapter |
| S01: restore recovery after hard process termination | N19: optional one-way Obsidian export |
| F12: consistent generation per reader | N21: broad real-project pilot and efficiency claims |
| Canonical decisions, compact resume and honest search coverage | Multiple installation channels and untested filesystems |
| Concrete authority, path and capsule validation | New vector backend, cloud platform or multi-agent architecture |
| Measured overhead and source-bound release evidence | Additional signing/distribution infrastructure |

N18, N19 and N21 do not block the scoped native recovery release. Their benefits
must not be claimed without implementation and evidence. A later deliberate
scope reduction must update N01, open criteria and release claims; it cannot
administratively turn an unresolved core defect into completed work.

N10 fixes the exact managed update channel. The preferred design uses
versioned directories, a stable entry point and separate user data. Publishing
this plan does not select an installation location or modify a host.

## 3. User outcomes and invariants

| Outcome | Concrete interpretation |
|---|---|
| U1 — Fewer stops and questions | Reuse valid scope; ask only for a genuinely missing decision |
| U2 — Less wasted cost | Avoid duplicate effects, context dumps, endless retries and mandatory extra model reviewers |
| U3 — Proportional protection | Distinguish answers, local writes and external effects |
| U4 — No unjustified internal refusals | Use current reasons, valid rebinding and no self-created stop loops |
| U5 — Clean updates | One explained active installation, coherent readers, safe recovery and ownership-bound cleanup |

These are OPENCNTX-controlled outcomes, not a promise that an AI will never
refuse. Host policies, missing access, legitimate safety boundaries and explicit
user stops still apply. Content verification is not authority.

The following are testable software contracts, not additional approval screens:

1. **I1:** an answer route neither grants nor uses write authority.
2. **I2:** revocation or changed authority cannot be bypassed by an old cache.
3. **I3:** one operation cannot complete two different assignments.
4. **I4:** an optional failure cannot hide or repeat a committed core result.
5. **I5:** open obligations remain reachable across compaction and handoff.
6. **I6:** valid decisions remain discoverable and explicitly supersedable.
7. **I7:** incomplete search cannot be represented as definitive absence.
8. **I8:** readers use a compatible generation; cleanup touches only proven owned content.
9. **I9:** hard process termination permits recovery without defeating live-writer exclusion.

## 4. Execution order

| Phase | Work | Required outcome |
|---|---|---|
| A — Baseline and regressions | N01, N02, N09A; baseline N16/N20 | Fixed source, independent criteria and preserved old evidence |
| B — Reliable core | N07, N08, N06A, N03, N04, N05, N06B, N09B | No advancing retry, abandoned-lock deadlock or stale authority block |
| C — Memory and resumption | N14, N15; initial N13 | Complete reachability with small current context |
| D — Managed updates | N10 starts early; then N11, N12 and final N13 | Reader consistency, crash recovery, rollback and explained cleanup |
| E — Measurement and guidance | Final N16/N20, N17 | Demonstrated native behavior and bounded claims |
| F — Candidate and release | N22, N23; N24 only when publication is requested | Exact source, matching artifacts and verified public state |

N06A deliberately starts before the complete sync implementation. N09A provides
only the minimal shared contracts; N09B consolidates their consumers later.
This avoids circular dependencies.

Task numbers are stable identifiers, not a mandatory numerical execution order.
Independent preparation can proceed when its actual dependencies are satisfied.
The number of tasks is not a calendar estimate.

## 5. Core work: N01–N09

### N01 — Fix scope, source and evidence baseline

- [ ] **Status: Planned**

**Work:** at implementation start, compare the current source with the fixed
stress-test commit. Preserve original results. Give each new candidate its own
commit/tree, environment, date and evidence identity. Record base scope and
excluded claims.

**Done when:** every criterion has an owning task; old and new measurements
cannot be overwritten or mixed; intervening source changes are understood.
Only an actual candidate receives the implementation version change.

**Depends on:** none. **Sources:** F01–F03, T12.

### N02 — Preserve regressions and add state sequences

- [ ] **Status: Planned**

**Work:** retain both 100-task routes and targeted fixtures. Define independent
desired outcomes for the twelve criteria, F12 and S01. Exercise actual
CLI/native call chains, not only helpers. Add commit, response-loss, retry,
revocation, crash and resume sequences.

**Done when:** the old source demonstrates the known shortcoming and the new
source satisfies the intended contract. Hard-crash tests use child processes
that do not run normal cleanup. The harness must not repair the lock before
calling recovery.

**Depends on:** N01. **Sources:** D01–D08, F04/F07–F12, S01, T11.

### N03 — Separate intent, authority and verification evidence

- [ ] **Status: Planned**

**Work:** bind write authority to a concrete action and normalized targets.
Keep answer intent, verification lease and authority separate. Recompute
current blocking reasons from current facts; retain history for explanation.

**Done when:** D01 does not promote an answer to a write route; D02 resumes
after genuinely valid rebinding; revocation takes effect; F07 supports multiple
actually authorized targets. A boolean alone is not proof of authority.
Independent authorized work remains possible.

**Depends on:** N02, N07, N09A. **Sources:** D01/D02, F07, T04; I1/I2.

### N04 — Bind progress to operations and connect lightweight routes

- [ ] **Status: Planned**

**Work:** persist a stable operation ID before the first mutation, bound to
assignment, input digest and expected revision. Commit the result and progress
together. Repeated delivery of that operation returns its earlier result.
Separate core outcome from presentation and optional delivery.

Connect the contract to real native/CLI routes. Recovery may use new evidence
inside the same scope; wider scope is not inherently progress. Answer-only and
local routes do not require onboarding for unrelated external features.

**Done when:** the D06 retry does not touch assignment 2; different input under
one operation ID produces a specific conflict; core success survives sync,
render and logging failures; D08 permits a meaningful new approach within the
same scope. Legacy calls receive no unsupported idempotency guarantee.

**Depends on:** N03, N06A, N09A. **Sources:** D06–D09, F13/F16, T01/T02/T06/T10.

### N05 — Use immutable sync objects and delivery identity

- [ ] **Status: Planned**

**Work:** create an immutable object before preview and delivery. Bind digest,
operation and delivery ID to those exact bytes. Commit required delivery intent
with native state. Use deduplication or appropriate external readback when the
outcome is uncertain.

**Done when:** F04 cannot report `SYNCED` for bytes other than the reviewed
snapshot; retries recognize the delivery; failures do not repeat progress.
An external recipient without adequate guarantees receives an explicit uncertain
status, not an unsupported exactly-once claim.

**Depends on:** N04; snapshot fixtures may start after N02.
**Sources:** F04, D06, T02.

### N06 — Make exclusion crash-safe and bound optional processes

- [ ] **Status: Planned**

**N06A — early:** replace vulnerable marker lifetime with a tested local
OS-lock contract. Manage handles and inheritance explicitly. Keep the lock
object stable. Migrate the old protocol without allowing old/new simultaneous
writers. PID, process-start identity and owner metadata explain ownership;
they do not authorize blind lock stealing.

**N06B — later:** apply subprocess deadlines and a shared retry budget across
nested layers. Preserve core success when optional work fails. A local privacy
boolean is not verified provider or repository privacy.

**Done when:** all three S01 hard-exit phases recover without manual lock
removal; competing recovery processes never both write; a live writer remains
protected; hanging Git, sync failures and logging failures produce bounded,
clear outcomes.

**Depends on:** A: N02/N09A; B: N04/N05.
**Sources:** S01, F05/F06, D06, T02/T03/T10.

### N07 — Resolve concrete target identity and overlap

- [ ] **Status: Planned**

**Work:** normalize targets using supported platform semantics. Account for
parent/child relationships, patterns, relative paths, case and link aliases
where applicable. Unknown overlap is not isolation. Reuse the same identity
for authority, sidecars and updates.

**Done when:** D03 cannot return unproven `ISOLATED`; F08 rejects duplicate
or overlapping active targets before activation; tests exercise real resolution
and platform differences. Keep validation tied to use so a changed target
cannot escape the original check.

**Depends on:** N02/N09A. **Sources:** D03, F08/F11, T04/T11.

### N08 — Validate capsules as bounded domain objects

- [ ] **Status: Planned**

**Work:** validate unique normalized manifest paths, actual members, counts,
hashes and extraction targets. Bound archive bytes, expanded bytes, file count
and processing. Enforce limits during reading as well as on declared lengths.

**Done when:** F09 rejects duplicates before `VERIFIED`; mismatched member
sets, path escapes and resource overruns cannot trigger uncontrolled processing;
valid export/import fixtures still work. Native recovery is not described as a
complete project-and-host backup.

**Depends on:** N02/N07/N09A. **Sources:** F09–F11, T11.

### N09 — Share small primitives without rewriting the product

- [ ] **Status: Planned**

**N09A:** after N02, inventory and define minimal revision, receipt, path
identity and exclusion contracts. Make them usable by early consumers without
introducing imports between product layers.

**N09B:** after N03/N04/N07/N08, consolidate genuinely overlapping
implementations. Move code only where it reduces duplicated validation or
failure boundaries; preserve public compatibility where possible.

**Done when:** critical validation has one clear owner; no new import cycle is
required; an old and a new implementation do not become competing sources of
truth. Historical coupling counts are a baseline, not a module-removal quota.

**Depends on:** A: N02; B: N03/N04/N07/N08. **Sources:** D10, F11, T01/T11.

## 6. Updates, memory and usability: N10–N17

### N10 — Define one managed installation and migration contract

- [ ] **Status: Planned**

**Work:** specify versioned generations, a stable entry point, ownership
manifest, user data and configuration boundaries. Proposed proof environments
are Windows with local NTFS and Linux with local ext4. Other environments remain
explicitly unproven.

Define data-schema and lock-protocol compatibility with 1.7.1 and the 1.7.2
candidate. Old writers cannot bypass the new exclusion or operation protocol.
Where necessary, use a short controlled offline migration for the managed
channel, not a host-wide configuration reset.

**Done when:** upgrade, rollback and uninstall have exact owned targets and
retention obligations; incompatible old writers can demonstrably be excluded.
Unmanaged installations have an honest migration route or explicit limitation.

**Depends on:** N01/N07; final protocol with N06A.
**Sources:** F12/F13, S01, T03/T08/T09.

### N11 — Activate coherent generations with pinned readers

- [ ] **Status: Planned**

**Work:** stage and validate a complete generation. Readers select and retain
one generation through the stable entry point. Coordinate selection,
registration and cleanup without a race between them. Keep mutable data outside
a blind directory-rollback model.

**Done when:** F12 never exposes new runtime/old project component to one
operation; old readers finish safely and new readers use a verified generation.
A replayed update returns its receipt. Schema incompatibility triggers controlled
migration rather than mixed writes.

**Depends on:** N04/N06A/N07/N08/N09B/N10.
**Sources:** F08/F12, S01, T08/T09; I8/I9.

### N12 — Prove the complete lifecycle under faults

- [ ] **Status: Planned**

**Work:** test clean install, supported upgrades, repeated upgrade, rollback,
uninstall and deferred cleanup in temporary fixtures. Add ordinary exceptions,
hard exits, concurrent readers, competing recoverers and busy files.

Preserve user changes through ownership checks and three-way configuration
comparison. Test a broken owned hook beside unrelated host configuration,
without activating global hooks.

**Done when:** all S01 phases recover without manual lock work; F12 holds during
transitions, not just at the end; user fixtures survive unchanged or according
to explicit migration. The inventory explains retained generations and has zero
unknown active old components. Rollback does not overwrite newer user work with
old user data.

**Depends on:** N11/N06B. **Sources:** F12, S01, T03/T08/T09/T11.

### N13 — Provide read-only diagnosis and a specific recovery route

- [ ] **Status: Planned**

**Work:** expose source version, active generation, native progress, current
operation, current authority reason, lock state, delivery status and uncertainty.
Separate historical failures from active blockers. Explain what is preserved
and the smallest useful next step.

**Done when:** diagnosis neither repairs nor activates without an appropriate
change request; S01 is recognizable as an owner/protocol problem; optional
failure does not imply total failure; rendering errors retain minimal core status.

**Depends on:** initial N04/N06A; final N06B/N12/N14.
**Sources:** D02/D07, F13/F16, S01, T02/T03/T10.

### N14 — Preserve canonical memory behind compact resume views

- [ ] **Status: Planned**

**Work:** separate complete decision/outcome storage from the bounded Combo.
Provide stable identity, provenance, status and supersession. Make derived
indexes rebuildable. Migrate only evidenced existing records; identify unknown
history instead of inventing it.

Build a deterministic resume root, at most 20 KiB, linking complete requirements,
decisions and evidence. Open obligations remain open; compaction never decides
that they are complete.

**Done when:** more than 32 active decisions remain findable and supersedable;
40/100/1,000-record fixtures pass; all ten views of the existing 100-long-DoD
fixture fit the budget. Every detail remains reachable and revision-bound.

**Depends on:** N04/N09A. **Sources:** D04/D07, T05/T06; I5/I6.

### N15 — Expose search coverage and dependency-bound reuse

- [ ] **Status: Planned**

**Work:** use direct lookup for known IDs. Return matches, scanned range,
`COMPLETE/PARTIAL` and safe continuation for scans. Bind cursors to query and
data revision. Cache content only with adequate source identity and invalidate
authority separately.

**Done when:** D05 finds Z directly or reports partial coverage with a working
continuation. An empty page is not a false definitive negative. Irrelevant
changes do not trigger global rechecks; relevant revocation or scope changes
are never skipped.

**Depends on:** N03/N14. **Sources:** D01/D05, T04/T07; I2/I7.

### N16 — Measure correctness, friction and cost separately

- [ ] **Status: Planned**

**Work:** measure a source-bound baseline before changes and equivalent routes
afterward. Count questions/stops, results, duplicate mutations, retries,
tool calls, subprocesses, context bytes and duration. Repeat performance
measurements at least three times; report median and spread.

**Done when:** targeted fixtures show zero unjustified authority questions and
zero duplicate core mutations while protecting real revocation; the resume
root fits its byte budget; no unexplained regression exceeds the predeclared
measurement budget.

Set that budget from baseline variability before the comparison, not afterward
to make a result pass. Without real host measurements, do not claim token
amounts, monetary savings or guaranteed refusal-reduction percentages.

**Depends on:** baseline N01; comparison N04–N06/N12/N14/N15.
**Sources:** F15, U1–U4, T12.

### N17 — Keep onboarding short and feature status honest

- [ ] **Status: Planned**

**Work:** document the shortest native start, optional sync, compact resume and
supported update channel. Distinguish implemented/tested, experimental and
planned capabilities. Explain when a real question remains necessary.

**Done when:** examples use actual product routes; helper contracts are not
marketed as real host integration; native users need no unrelated external
setup. Public documentation remains English and contains no private notes.

**Depends on:** N04/N12–N16/N20. **Sources:** D09, F02/F13/F16, T06/T12.

## 7. Extensions and optimization: N18–N21

### N18 — Demonstrate one real host adapter

- [ ] **Status: Deferred outside the 1.7.3 base scope**

**Work:** following a separate extension request, select one host and connect
its actual calls to native contracts. Ten host-shaped fixtures do not represent
ten working integrations.

**Done when:** real execution, authority, interruption and resumption in that
host are evidenced; adapter failure does not disable native work. Installation
and registration stay within requested scope, without a broad stop hook.

**Depends on:** N04/N06/N13–N15; N10 for managed registration.
**Sources:** D09, F13, V08.

### N19 — Add optional one-way Obsidian export

- [ ] **Status: Deferred outside the 1.7.3 base scope**

**Work:** export selected native state into readable Markdown. OPENCNTX remains
canonical; the exported view creates neither a second planner nor implicit
instruction import.

**Done when:** repeated export is predictable, user notes are preserved, and
export failures do not roll back native progress. Producing a research document
does not prove this product feature exists.

**Depends on:** N06B/N14/N15 and a separate extension request.
**Sources:** V12, T02/T05.

### N20 — Measure storage and optimize proven bottlenecks only

- [ ] **Status: Planned**

**Work:** measure fixed 10/100/1,000-task and decision fixtures: file count,
retained bytes, actual written bytes where measurable, duration and repeated
reads. Distinguish canonical evidence, rollback data and rebuildable caches.

**Done when:** growth is explained; demonstrated unnecessary full rewrites or
scans are corrected; cleanup preserves valid memory and recovery roots.
A large database or dependency migration first needs demonstrated necessity.

A result of “no optimization needed” is valid when supported; it is not an
unbounded scalability claim. The historical 437 files and approximately
1.99 MiB after 100 tasks are storage snapshots, not total written I/O.

**Depends on:** baseline N01; assessment N09B/N14/N15/N12.
**Sources:** F14, D05/D10, T05/T09/T12.

### N21 — Run the pilot required for broad practice claims

- [ ] **Status: Deferred outside the 1.7.3 base scope**

**Work:** the local R17 implementation is historical groundwork, not proof of
the new improvements. A broad pilot remains a separate decision for one exact
non-production-critical project, with reversible scope and a comparable baseline.
Before broad cost, interruption or host-handoff claims, run at least two weeks
and 25 real tasks, including at least three genuine restart or handoff events.

Synthetic tasks may test the harness but never count as pilot success.
Rollback restores the project's selected prior route and preserves evidence.
Measurement completion grants no publication, installation, or adoption authority.

**Done when:** real outcomes, missing data and limitations are reported.
New CLI processes do not automatically count as chats or host handoffs.

**Depends on:** N16/N17 and every claimed capability; N18 for host claims.
**Sources:** F15, T12.

## 8. Candidate and publication: N22–N24

### N22 — Bind final source to tests and distribution

- [ ] **Status: Planned**

**Work:** automate final commit/tree, required full CI, build and distribution
provenance. Retain the four current distribution artifacts as the starting
contract; record their exact names and hashes in the build manifest.

**Done when:** build/tag mismatch, wrong version or missing required final CI
rejects the candidate. The required matrix applies to the final source and
explains skips. Reuse unchanged evidence only when its validity is demonstrated.
Unsigned provenance must not be described as signed.

**Depends on:** infrastructure may start after N01; final evidence follows
all base-scope changes. **Sources:** F01–F03, V09, T11/T12.

### N23 — Accept the actual 1.7.3 candidate

- [ ] **Status: Planned**

**Work:** bind every release claim to implemented behavior, regression outcomes
and relevant measurements. Review compatibility, migration, rollback, platform
boundaries and known limitations. Separate defect correction from extensions.

**Done when:** all required tasks and section 9 criteria are evidenced; no
known material defect contradicts a claimed capability; N18/N19/N21 remain
visibly deferred unless executed. A completed plan is not completed software.

**Depends on:** N01–N17, N20 and N22. **Sources:** all base findings, T12.

### N24 — Publish and read back only when release is requested

- [ ] **Status: Planned**

**Work:** following an explicit software-publication request, publish the
accepted 1.7.3 tag and four verified artifacts. Check release/latest state and
update applicable README, changelog, roadmap, installation/release pages and
website source.

**Done when:** actual downloads match recorded hashes, source and metadata
agree, and public text has been read back. Public content is English and
excludes private paths and personal notes. A website source change is not proof
of a hosted deployment.

Roadmap publication alone does not execute this task. Software publication
does not install or activate OPENCNTX on a local host.

**Depends on:** N23 and an explicit release request.
**Sources:** F01–F03, V09/V10.

## 9. Acceptance scenarios

### The twelve retained criteria

| Finding | Required result | Tasks |
|---|---|---|
| D01 — Answer with expired lease | Preserve read-only intent; do not grant writes | N03/N04 |
| D02 — Historical authority block | Recover after valid current rebinding, not merely a boolean change | N03/N13 |
| D03 — Alias, parent or pattern | Resolve overlap; unknown does not mean isolated | N07 |
| D04 — More than 32 decisions | Oldest valid record remains findable and supersedable | N14 |
| D05 — Z beyond scan budget | Find directly or expose partial coverage and safe continuation | N15 |
| D06 — Failure after core commit | Replay assignment 1 result without touching assignment 2 | N04/N06 |
| D07 — Large valid roadmap | All ten resume roots at most 20 KiB; complete details reachable | N14 |
| D08 — Same scope, new recovery evidence | Permit a bounded changed approach without artificial scope widening | N04/N06B |
| F04 — Source changes after preview | Deliver exactly the reviewed immutable bytes | N05 |
| F07 — Multiple targets | Support valid concrete authority without artificial single-target refusal | N03 |
| F08 — Duplicate active update path | Reject before mutation using normalized identity | N07/N11 |
| F09 — Duplicate capsule entry | Do not verify an invalid duplicate manifest | N08 |

### Additional mandatory proofs

- **S01:** hard exit after retire, first activation and second activation;
  recovery works without manual lock deletion.
- **Writer exclusion:** protect a live writer and serialize competing recovery.
- **F12:** independent readers at controlled transition points see one compatible
  generation; a green final state alone is insufficient.
- **Lifecycle:** upgrade, replay, rollback and uninstall preserve user data.
  Explained retained recovery data is not unexplained installation debris.
- **Memory:** 40/100/1,000 valid records, supersession and derived-index rebuild.
- **Input limits:** critical JSON, paths and capsules reject invalid input before
  uncontrolled mutation or processing.
- **Process behavior:** transient, permanent and uncertain outcomes have distinct
  bounded recovery paths.
- **Full CI:** all required jobs on final source; tests, skips and limitations
  are reported separately.

### Long compound assignment

Repeat the original 100-task route with the same independent content oracle,
ten work lanes, dependencies and process handoffs. Preserve the original
baseline. Combine more than 32 valid decisions, long requirements, optional
sync failure and controlled interruptions.

The candidate must deliver 100/100 correct task results, no duplicate completion
and reachable open obligations at every handoff. Report the twelve criteria
separately. The 1,000-item scale fixture does not replace the comparable 100-task
measurement.

A real AI-host pilot is a different evidence level. Native process handoff is
not automatically a conversation or demonstrated cross-host integration.

## 10. Traceability

### Review and stress findings

| Finding | Tasks |
|---|---|
| D01 / D02 | N02/N03/N04/N13/N15 |
| D03 | N02/N07/N09 |
| D04 | N02/N14/N20 |
| D05 | N02/N15/N20 |
| D06 | N02/N04/N05/N06 |
| D07 | N02/N04/N13/N14 |
| D08 | N02/N04/N06 |
| D09 — Contract versus product route | N04/N17/N23; additional host N18 deferred |
| D10 — Coupling and helpers | N09/N20 |
| S01 — Abandoned lock after hard exit | N02/N06A/N10–N13 |
| Strengthened F12 — Mixed reader generation | N10–N12 |

### Earlier findings and proposals

| Finding or proposal | Tasks |
|---|---|
| F01 build/tag, F02 version claims, F03 CI/publication | N01/N17/N22–N24 |
| F04 sync bytes, F05 subprocess timeout, F06 privacy claims | N05/N06 |
| F07 concrete authority | N03/N04 |
| F08 update overlap | N07/N11/N12 |
| F09 capsule duplicates, F10 resource bounds | N08 |
| F11 critical validation | N07–N09 |
| F12 update atomicity | N10–N12 |
| F13 host contract/integration | N04/N13/N17; additional adapter N18 deferred |
| F14 storage growth | N20 |
| F15 unproven practice benefits | N16/N23; broad pilot N21 deferred |
| F16 heavy onboarding | N04/N13/N17 |
| V01 authority/friction | N03/N04; host follow-up N18 |
| V02 sync | N05/N06 |
| V03 updates | N07/N10–N12 |
| V04 capsules | N08/N09 |
| V05 diagnosis | N13 |
| V06 context | N15/N16 |
| V07 resumption | N14 |
| V08 host adapter | N18, deferred |
| V09 release provenance | N01/N22–N24 |
| V10 guidance/status | N04/N17/N23/N24 |
| V11 storage | N20 |
| V12 Obsidian export | N19, deferred |
| Global hook conflict prevention | N10–N13; no new host-wide stop hook |

### Design proposals

These are OPENCNTX-specific applications of established principles, not claims
that the principles were invented here or are already implemented.

| Proposal | Design and execution |
|---|---|
| T01 — Operation identity | Persist caller intent, expected assignment/revision and result atomically; preserve deduplication knowledge after detailed receipt cleanup. N02/N04/N09 |
| T02 — Separate core/delivery/view | Commit required delivery intent with native state; deliver immutable bytes and preserve core success during optional failure. N04–N06/N13 |
| T03 — Owner-bound lock lifetime | OS-backed exclusion, controlled handle inheritance and safe legacy migration; age or PID alone cannot authorize stealing. N06A/N10–N13 |
| T04 — Current authority | Bind action and concrete targets; recompute current reasons and invalidate revoked authority. N03/N04/N07/N15 |
| T05 — Canonical memory | Stable records with provenance and supersession; bounded views never define what exists. N14/N15/N20 |
| T06 — Compact resume root | Deterministic bounded root with revision-bound details; unresolved obligations remain open. N04/N14–N16 |
| T07 — Honest search coverage | Direct ID lookup or partial results with query/revision-bound continuation. N15/N16 |
| T08 — Reader-pinned generation | Coordinate selection, reader registration and cleanup; handle mutable data compatibility explicitly. N10–N12 |
| T09 — Ownership-bound cleanup | Retain active readers, recovery and a valid rollback; merge old defaults, user changes and new defaults. N10–N13/N20 |
| T10 — Shared recovery budget | Bound time and attempts across layers; new facts or a changed approach can justify same-scope recovery. N04/N06B/N13/N16 |
| T11 — Independent transition tests | Compare public routes with a small reference model; inject real process death and observe intermediate states. N02/N07–N09/N12/N22 |
| T12 — Evidence and cost accounting | Separate correctness, bytes, calls, elapsed time and real host usage; never equate unknown costs with zero. N01/N16/N20–N24 |

## 11. Working rules

A task is complete when its criteria have source-bound evidence. Record only
the relevant change, test outcome, limitation and next step. Do not require
long model reflections after every small edit.

Use focused checks during development and full required CI for candidate
acceptance. Ordinary reversible implementation steps inside the request do not
need repeated roadmap approval. Ask once, specifically, when genuine authority
or a material user choice is missing.

An authority failure blocks the affected write, not automatically reading,
reporting or independent authorized work. Optional components do not silently
become prerequisites for the native core. A new tool must solve a demonstrated
problem without becoming a second planner, memory authority or policy engine.

Retain old generations only with an explained purpose and cleanup criterion.
Clean means controlled and coherent, not indiscriminate deletion. An upgrade
must not require a fresh start.

## 12. Status and next step

| Revision | Record | Implementation |
|---|---|---|
| 3 — Historical | 1.7.0/1.7.1 deep review; target 1.7.2 | Not evidence that the planned runtime work shipped |
| 4 — Current | Candidate stress findings, research and T01–T12; target 1.7.3 | Plan only; base tasks remain planned and three extensions are deferred |

When implementation is requested, start N01, then N02/N09A. Follow early with
N06A and N07 so crash recovery and concrete identity support later changes.
No software release or local installation is created by this publication.

## 13. Evidence and design references

The candidate observations above are reported bounded local measurements, not
independently replicated community results. The private test artifacts are not
published by this roadmap. External references support design principles;
they do not prove that OPENCNTX implements them.

- [Fixed reviewed source](https://github.com/CNTX-PROJECT/OPENCNTX/commit/f6edbbf6d9d81310c37a55036f7d9794e38e109b) and [CI for that source](https://github.com/CNTX-PROJECT/OPENCNTX/actions/runs/34404307842).
- [Current release scope](release-1.7.1.md) and [earlier limitations](release-1.7.0.md).
- [AWS: Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) — caller intent and retry identity.
- [LangGraph: Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) — resumed execution and idempotent side effects.
- [Microsoft: Transactional Outbox](https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-out-box-cosmos) — commit state and delivery intent together.
- [Microsoft: LockFileEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex) and [Linux: flock](https://www.man7.org/linux/man-pages/man2/flock.2.html) — platform-specific lock lifetime.
- [filelock PR 660](https://github.com/tox-dev/filelock/pull/660) — reused PID detection using process-start identity.
- [OSTree: Atomic Upgrades](https://ostreedev.github.io/ostree/atomic-upgrades/) and [Nix: Profiles](https://nix.dev/manual/nix/2.28/package-management/profiles.html) — generation-oriented deployment precedents.
- [Aider: Repository map](https://aider.chat/docs/repomap.html) — bounded context selection.
- [DynamoDB: Scan](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Scan.html) — scanned range differs from matching results.
- [Hypothesis: Stateful tests](https://hypothesis.readthedocs.io/en/latest/stateful.html) — generated action sequences and reference-model comparison.

[Back to the roadmap](roadmap.md) · [Documentation home](README.md)

