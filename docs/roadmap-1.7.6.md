# OPENCNTX 1.7.6 — delivery, clean upgrades and publication roadmap

Status: RELEASE_PUBLISHED_AND_INSTALLATION_HEALTHY
Date: 2026-09-12
Baseline: published v1.7.5, commit 685d3738782c1e0ef2ebc7398d1f76593fae54b8
Local installed baseline measured when planning: opencntx 1.7.4
Parent: [Product roadmap](roadmap.md)
Basis: post-release audit of v1.7.5, including runtime, context and cleanup fault probes.
Implementation milestones: 16/16 verified complete
Completion anchor: R176-16. Public assets, clean installation, managed upgrade and registered-project continuity are verified in the release receipt.

## Acceptance record

The exact release candidate passed 833 local tests on Windows, the complete
Windows/Ubuntu historical-writer matrix, managed installation on Python
3.11–3.14, static quality gates and the frozen installer corpus. Ten alternating
update/rollback transitions ended on 1.7.6 with ten retained terminal journals,
zero staging residue and preserved user-owned sentinels. The measured resume
corpus read 8,192 bytes at every scale and reduced loaded bytes by 86.2%, 98.4%
and 99.8% for 100, 1,000 and 10,000 checkpoints. Token savings remain unclaimed.

The publication receipt binds the annotated `v1.7.6` tag to the qualified tree
and exactly four verified assets: wheel, source archive, `SHA256SUMS` and
`BUILD-RECORD.json`. Public-download installation and the 1.7.5 managed-upgrade
route were repeated from downloaded assets. Routes listed as diagnosis-only in
the compatibility table remain diagnosis-only; completion does not broaden them.

## Scope and completion contract

Deliver one coherent 1.7.6 release that addresses every audit theme: existing-version compatibility, real executable health, bounded cleanup, mandatory historical regressions, connected execution, side-topic return, task recipes, coherent roadmap/Combo state, preserved mandatory knowledge, measured efficiency and reproducible publication/installation.

This roadmap tracks implementation work, not a claim that 1.7.6 exists or that implementation, live installation or publication occurred. Public version surfaces remain on the published release until an actual qualified candidate exists. Retain the original 1.7.5 acceptance records as history and map unfinished work below; do not mark old milestones complete merely by moving them.

Two related completion states must remain distinct: RELEASE_PUBLISHED (verified public artifacts/docs) and INSTALLATION_HEALTHY (verified intended executable plus migrated project continuity). Overall delivery requires both for the declared installation acceptance environment, while unrelated owner machines require their own evidence.

Clean means zero obsolete ACTIVE owned components, zero obsolete active generated rules/hooks, zero mixed active generations and zero orphan update-owned transient paths. Separately inventory retained recovery material and historical evidence. Preserve custom rules, user knowledge, credentials, history and later edits; never delete them merely because they mention an old version.

## Milestones and dependencies

| ID | Deliverable | Depends on | Prior acceptance / audit theme |
|---|---|---|---|
| R176-01 | Freeze scope, reproduction corpus and acceptance identities | none | E01/E12; every audit section |
| R176-02 | Inventory installation owners and explicit compatibility routes | 01 | E01/E03/E06; older lock/schema lineage |
| R176-03 | One managed update entry with staged activation | 02 | E02/E04; missing installed updater |
| R176-04 | Real runtime health, rollback and interrupted recovery | 03 | E02/E05; false green runtime |
| R176-05 | Clean active generation and bounded retained storage | 04 | E01/E04/E06; old rules and growing snapshots |
| R176-06 | Mandatory historical and fault regression CI | 02; full acceptance after 03–05 | E03/E06; source-gated skipped tests |
| R176-07 | One execution decision and exact scoped authority model | 01 | E07; divergent decisions and external approvals |
| R176-08 | Working host adapter and durable park/resume path | 07 | E07/E08; unconnected planner and missing anchors |
| R176-09 | Purpose-aware recipes and repeatable project bootstrap | 08 | E09; information/change and fresh-project gaps |
| R176-10 | One canonical progress revision, derived views and stable IDs | 08,09 | E08; stale statuses, numbering, Combo scale |
| R176-11 | Mandatory knowledge retention and session availability | 08,10 | E10; dropped decisions and assumed cache |
| R176-12 | Measured context, I/O and latency improvements | 05,10,11 | E11; byte/token confusion and full rereads |
| R176-13 | Installation and upgrade pilots on packaged candidate | 03–12 | E12; existing-project end-to-end proof |
| R176-14 | Installation UX, compatibility guide and release documentation | 02; acceptance after 13 | visual carry-over; truthful public claims |
| R176-15 | Exact candidate build, release readiness and public publication | 06,12,13,14 | E12; commit/assets/docs alignment |
| R176-16 | Verify public downloads, clean installation and handoff | 15 | release and installation closure |

Independent design/test preparation can proceed in parallel after its prerequisites. Mutations affecting the same store or activation identity are serialized. No automatic model escalation is part of the plan.

## Phase A — Reliable updates before feature expansion

- [x] R176-01 Freeze the audit regression corpus and scope.
  - Reproduce the historical lock conflict, false-positive byte-only postflight, 2/6/10 recovery-directory growth, missing decision under a 2,000-byte budget, unverified cached reference, absent return anchor, numbering gap and authority-route ambiguity.
  - Preserve exact v1.7.5 baseline and artifact hashes; inventory where old 1.7.5 roadmap acceptance is still open.
  - Define golden tasks: empty start, adopted project, nested side questions, fresh/compacted session, failed update, interrupted cleanup and full release/install.
  - Exit: versioned case IDs, explicit expected behavior and retained failure evidence. Existing unaffected green checks need not be repeated without a reason.

- [x] R176-02 Inventory owners and qualify each route.
  - Resolve executable/PATH, pipx or other package ownership, Python, per-project state format, live writers, shared runtime, config/instruction/hook provenance, pending receipts and disk requirements.
  - Distinguish active product-owned, generated-owned, transient-owned, rollback, historical and user-owned items.
  - Freeze direct/bridge/diagnosis-only routes before implementation acceptance. Missing support is explicit, not an instruction to reset Codex.
  - Exit: read-only machine-readable inventory plus concise proposed write set; no inferred authority or mutation during diagnosis.

- [x] R176-03 Implement one managed updater.
  - Specify one user-facing entry for fresh install, update, status, resume and repair. Choose actual command names during implementation; do not document invented commands as working.
  - Bootstrap updates for old installations that do not yet contain this updater using an independently available, verified package/tool entry.
  - Stage the exact target and retain the prior working runtime/state locally; reuse the existing package manager where supported.
  - Bind plan, source generation, candidate hash and affected project identities; detect drift and overlapping writers, then journal activation.
  - Exit: named existing-installation fixture reaches one coherent target generation; repeats do not reinstall or duplicate state unnecessarily.

- [x] R176-04 Require semantic health and independent rollback.
  - Run actual candidate import/version/help and read/checkpoint/resume probes on disposable state; validate the resolved executable and affected real state after activation.
  - Treat a correctly hashed but non-starting executable as failed activation.
  - Recover after process termination, offline and from a fresh shell even if the new package cannot import. Preserve later user edits through explicit reconciliation.
  - Exit: NEW_HEALTHY, verified OLD_RESTORED or actionable RECOVERY_REQUIRED with retained data. Never report new health from hashes alone.

- [x] R176-05 Complete cleanup as part of the update lifecycle.
  - Migrate or retire only proven obsolete generated rules and hooks; replace active version references and project profiles atomically or with journaled recovery.
  - Produce a provenance-bound manifest for update-owned temporary, candidate, cache and retired files. Unknown ownership remains untouched and is reported.
  - Retain one verified last-known-good generation by default; permit necessary unresolved-recovery material separately with explicit size/lifetime policy. Never evict the last required recovery state to satisfy a quota.
  - Use reference-aware cleanup after successful health verification; make cleanup resumable after interruption and idempotent.
  - Exclude rollback/archive material from normal prompt and roadmap discovery.
  - Exit: no obsolete active components/rules, no orphan owned temporary paths, unchanged user sentinels, listed rollback evidence, and bounded retained storage across ten successful update/rollback/reapply cycles after retention processing. Incident retention must have a concrete disposition.

- [x] R176-06 Make historical compatibility and failure injection mandatory.
  - Fetch/cache immutable named historical artifacts or source snapshots and verify provenance before executing tests; no live branch heads.
  - Cover old write → update → new write → supported rollback/bridge → old write → re-update → new write.
  - Exercise lock contention, crashes at durable boundaries, short/disk-full writes, permission denial, bad download/hash, correct hash with failed startup, offline recovery, cleanup interruption and user edits.
  - Explicitly test writer-protocol ancestry before 1.6, not only current fresh installs.
  - Exit: zero failed or silently skipped mandatory cells. Platform-inapplicable cases are named and separately supported elsewhere; unsupported routes cannot be advertised as supported.

### Compatibility qualification table

Every row starts NOT_TESTED_FOR_1.7.6. Prior 1.7.5 evidence is a baseline, never a replacement for target-version qualification.

| Starting family | Required 1.7.6 evidence |
|---|---|
| 1.7.5 and locally installed 1.7.4 | Full packaged upgrade, real follow-up task, rollback/reapply and active cleanup; priority Windows/pipx and Linux/pipx. |
| 1.7.3, 1.7.1, 1.7.0 | Exact tagged format/lock inventory; full direct route or named tested bridge. |
| 1.7.2 | Determine whether an authentic distributable exists; otherwise label exact candidate commit and its limited evidence. |
| 1.6.3, 1.6.1, 1.6.0 | Mandatory historical writer tests and end-to-end supported migration/recovery route. |
| 1.6.2 | Exact candidate 01c34fc5aab556a2e5e0447af2a83bbb46f48ef1; never invent a public tag. |
| 1.5.0 and 1.4.0 | Historical writer/format transition and tested bridge; retained marker failure must not recur. |
| 1.1.0, 1.1.1, 1.2.0, 1.2.1, 1.3.0 | Exact continuity-format inventory and migration proof for any advertised supported route. |
| 0.3.0 | Existing data-preserving upgrade proof repeated against target artifacts. |
| 1.0.0, other 0.x, unknown/custom | Inventory and preservation first; implement a named migration for support. Diagnostic-only means not installation-qualified and must be visible before mutation. |
| pip/venv, shared runtimes, cloud-synchronized/network/junction paths | Qualify separately from pipx/local filesystem. Never extrapolate Windows/pipx evidence. |

Do not silently shrink mandatory scope to make a failing release green. Any substantive scope change is recorded explicitly rather than silently declaring the row unsupported.

## Phase B — Connected execution and continuity

- [x] R176-07 Unify decision and authorization contracts.
  - Align planning, native finalization, recovery and the connected view on continue/wait/complete/choice/recovery/handoff.
  - Completion never grants extra mutation; missing readiness is distinct from corrupt state.
  - Bind explicit external approval to the exact target/action/revision; reuse valid existing authorization without repetitive prompting.
  - Renew a bounded recovery episode only on changed evidence/conditions; preserve all attempts.
  - Exit: exhaustive feasible decision-table cases and no generic compatibility refusal substituted for a diagnosed cause.

- [x] R176-08 Connect the real host and resumable side-topic handling.
  - Route planner results through an actual supported host adapter into durable task actions, not merely isolated Python return values.
  - Persist nested return anchors with task, step, revision, open outcomes and authority; classify feedback/correction/extension/side topic/replacement.
  - On resume, verify state, select the same or correctly revised next step and acknowledge execution; duplicate delivery cannot duplicate an action.
  - Prove pause/wait/restart/compaction behavior; expose unsupported host capabilities honestly. No permission/Stop hook or forced infinite loop.
  - Exit: golden task resumes after three nested side inputs and a fresh session without losing obligations or repeating completed writes.

- [x] R176-09 Deliver real project recipes and bootstrap.
  - Separate answer/review/analysis from change tasks; SHORT/MEDIUM/LARGE/MEGA determines planning depth, not automatic write authority.
  - Empty-folder start and existing-project adoption reuse one master, focused children and one Combo.
  - Repeated setup produces no duplicate roadmap or overwritten custom instruction. Recipe versions have migration provenance.
  - Exit: all four sizes tested in new/existing projects, including an information-only request that performs no product mutation.

- [x] R176-10 Make progress coherent and scale navigation.
  - Commit canonical task/roadmap/current-step/evidence/return anchors together; derive owner views and publication status from a bound revision.
  - Reserve persistent IDs including gaps and retired numbers. Do not use list length as a permanent identifier.
  - Keep active obligations visible beyond the twelve-roadmap projection boundary; use bounded hierarchical navigation instead of silent loss.
  - Use historical shards/indexes so compact output is also efficient to retrieve.
  - Exit: stale/mismatched views detected; interrupted projection rebuild is idempotent; display/sync failure does not undo completed native work.

## Phase C — Preserve knowledge while reducing cost

- [x] R176-11 Protect mandatory knowledge.
  - Make current goal, owner decisions, exclusions, active step, return anchor and unresolved outcomes non-droppable.
  - Default unknown cache availability to unavailable. Require current-session/revision-bound read evidence, invalidated after rollover/compaction.
  - If mandatory information exceeds a budget, provide a verified bounded capsule or explicit additional load; no false savings from lost decisions.
  - Make decimal-byte rollover policy configurable; test the owner's exact 35,000,000-byte threshold.
  - Exit: zero lost required obligations across cold/warm/compacted golden tasks; omitted/reference/loaded metrics remain distinct.

- [x] R176-12 Benchmark and remove demonstrated overhead.
  - Freeze representative 1.7.5 comparison fixtures before optimizing: 0/100/1,000/10,000 checkpoints, growing Combo history and mixed small/large recovery files.
  - Measure median/p95 latency, file bytes/read count, peak memory, loaded context bytes, calls/retries, and actual input/output tokens when telemetry exists.
  - Stream file hashes, bound recovery copy cost, reuse integrity evidence only with valid input/environment bindings, and batch safe calls.
  - Target at least 30% median loaded-context reduction on the agreed resume corpus with zero missing obligations. Measure real tokens separately; missing provider telemetry cannot be advertised as token savings.
  - Require no unexplained >10% p95 regression on matched baseline routes; confirm noisy results with a fixed repeat protocol before accepting a regression.
  - Exit: reproducible comparative report, unchanged correctness/fault outcomes and explicit environment/sample counts. Numeric targets are acceptance targets, not achieved claims.

## Phase D — Installation-ready release, then verified publication

- [x] R176-13 Pilot the exact packaged candidate.
  - Test clean install and old-project update independently in fresh Windows/Linux environments; cover pipx, declared Python 3.11–3.14 compatibility and separately qualified install methods.
  - Start with disposable project copies; then perform a scoped local registered-project pilot with retained recovery and applicable authorization.
  - Continue a real existing task after upgrade, side question and fresh-session resume; test offline failed-update recovery and cleanup.
  - Exit: installation route matrix with executable identity, old/new versions, before/after state, preserved owner sentinel hashes and a clean-generation receipt.

- [x] R176-14 Prepare plain installation and migration guidance.
  - Publish English documentation with separate fresh-install, existing-install update, resume and targeted repair paths.
  - Detect existing package ownership; instructions must not recommend a second installation over an existing one.
  - Include exact supported routes, retained recovery locations, removal policy and known host boundaries.
  - Reconcile old issues/roadmaps/version surfaces with the actual scoped implementation; preserve historical records and carry-over IDs. Reuse the 1.7.5 visual system; no unrelated redesign.
  - Exit: novice walkthrough from the built package completes without missing/manual undocumented steps; commands and links verified.

- [x] R176-15 Publish the qualified exact release.
  - Freeze candidate commit/tree and version; run required quality, security, compatibility, fault, semantic-health and installation checks against that same candidate.
  - Build and verify wheel/sdist plus SHA256SUMS and BUILD-RECORD.json; bind all four to the release source. Rebuild after any candidate change.
  - Prepare a reviewable release manifest containing milestone evidence, supported routes, commands, hashes and remaining explicitly out-of-scope limitations.
  - Inspect existing publication authorization at execution time; do not repeatedly ask within an already authorized scope, and never infer a new publication from this roadmap-creation request alone.
  - Merge, create the tag and upload release/assets through an idempotent publication operation. Do not create a premature tag that invalidates candidate gates.
  - Exit: actual public release and correct tag/commit/assets visible; no release label based solely on local green tests.

- [x] R176-16 Verify downloads and close installation delivery.
  - Download the public assets and verify their hashes/build identity; install using the public documented route in a clean environment.
  - Upgrade at least the qualified previous release through the public route, continue its task and verify cleanup/rollback availability.
  - Verify any authorized local deployment separately: actual resolved executable must print 1.7.6 and registered project continuity must be healthy before changing persistent local version expectations.
  - Reconcile release, task, roadmap, Combo and Obsidian status; publish only verified scope and retain reproducible evidence.
  - Exit: RELEASE_PUBLISHED plus INSTALLATION_HEALTHY evidence, 16/16 accepted milestones, no unresolved mandatory case. If a public release succeeds but a deployment fails, retain the real publication state and continue the deployment repair without falsely calling delivery complete.

## Evidence, automation and operating rules

Each milestone receipt records ID/status, baseline and candidate commit/artifact hashes, OS/runtime/install method, cases and skips, expected/observed behavior, preservation proof, exact next action and retained recovery paths. Initially all receipts are NOT_STARTED. A parent checkbox changes only after its own acceptance condition is met.

Planned automation: deterministic release-readiness report, required compatibility matrix, semantic-health probes, owned-residue inventory, idempotent publication resume and bounded installer verification. None is claimed installed by this document.

One active execution anchor; compact checkpoints at durable outcomes or interruptions. Reuse unchanged green evidence, run focused checks after each change, and broaden at phase/candidate gates. Continue independent authorized work when one route has a real external blocker. Optional footer or presentation telemetry cannot stall the engineering task.

Expected phase gates:
A: R176-01–06 accepted → existing-version update foundation.
B: R176-07–10 accepted → connected continuity.
C: R176-11–12 accepted → preserved knowledge and measured efficiency.
D: R176-13–16 accepted → verified installation and public release.

No date estimate is asserted before the failing-case inventory is frozen. Scope reductions, failed mandatory cases and unsupported routes remain visible. No full Codex reset, history deletion, blanket policy removal, force-push or unowned cleanup belongs to this roadmap.
