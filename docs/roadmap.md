# Roadmap for OPENCNTX 1.7.2

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

[Release scope](release-1.7.1.md) · [Full roadmap in English](roadmap-plan.md)

## Current status

Revision 3 targets **1.7.2** and is published as a plan, not implemented functionality.
It contains **six phases and 24 tasks (N01–N24)**. All tasks are planned;
none of these new implementation tasks is marked complete.

- Published Stable software release: **v1.7.1**, retaining the v1.7.0 runtime.
- Reviewed implementation baselines: **v1.7.0 and v1.7.1**, with identical runtime behavior.
- Source release target: `v1.7.2` (unreleased candidate; roadmap publication only).
- Package version: `1.7.2`.
- The next update is **1.7.2**. This publication does not create its software release.
- Source metadata reserves 1.7.2 under the repository's post-release version rule;
  runtime behavior remains unchanged. All 24 implementation tasks are planned.
- No installation, host activation or roadmap implementation is performed
  by publishing this documentation.

The [complete plan](roadmap-plan.md) contains the detailed work,
acceptance criteria, dependencies, five user requirements, evidence mapping
and restart instructions. This English page is an overview of that plan,
not an independently maintained task ledger.

The 1.7.1 distribution contains exactly
opencntx-1.7.1-py3-none-any.whl, opencntx-1.7.1.tar.gz, SHA256SUMS and
BUILD-RECORD.json. Earlier release tags and files remain unchanged.

## What the plan must achieve

| Requirement | Intended result |
|---|---|
| U1 — Fewer stops and approval requests | Continue within valid task scope; do not ask again for every file or phase |
| U2 — No unnecessary token spending | Compact relevant context, deterministic administration and measured overhead |
| U3 — Proportional product policies | One current decision route; optional failures do not disable the healthy core |
| U4 — No incorrect product refusals | Express concrete authorized actions and multiple targets correctly |
| U5 — Clean version transitions | Owned installation inventory, bounded cleanup, recoverability and preserved user data |

These requirements apply to OPENCNTX-controlled behavior. They do not override
provider policies, host capabilities, quotas or missing access. Valid authority
is reused, real scope changes remain visible, and an explicit user stop is respected.

## Six phases

| Phase | Tasks | Outcome |
|---|---|---|
| A — Baseline and evidence | N01–N02 | Known source and reproducible regression cases |
| B — Defects and friction | N03–N09 | Correct authority, useful routing, snapshot sync and strict input handling |
| C — Everyday usability | N13–N17; N20 as needed | Diagnosis, durable decisions, compact resume and measured overhead |
| D — Clean lifecycle | N10–N12 | Owned generations, reader consistency, data rollback and bounded cleanup |
| E — Selected extensions | N18–N21 | Optional host/export, scale evidence and broader pilot |
| F — Release | N22–N24 | Automated provenance, scoped readiness and verified publication when requested |

This is not a requirement to stop after each phase. Independent work can
proceed once its actual dependencies are satisfied. Release automation can
start early. Initial usability measurements do not wait for optional exports.

## Task index

| Task | Deliverable |
|---|---|
| N01 | Establish development source, reusable evidence and change scope |
| N02 | Turn new and retained audit cases into regression and state-sequence tests |
| N03 | Bind concrete actions, authority and multiple targets |
| N04 | Connect proportional routes, make progress retries idempotent and repair recovery scope rules |
| N05 | Bind sync preview and delivery to one immutable snapshot |
| N06 | Bound Git operations and distinguish declared from verified privacy |
| N07 | Resolve target identity and reject update/sidecar overlap before mutation |
| N08 | Enforce unique capsule records and resource-bounded verification |
| N09 | Harmonize critical JSON and filesystem checks |
| N10 | Define installation ownership and supported compatibility |
| N11 | Implement a journaled update state machine with recovery |
| N12 | Prove upgrade, uninstall, rollback and orphaned-hook behavior |
| N13 | Provide one read-only diagnosis with actionable explanations |
| N14 | Preserve canonical decisions and every open outcome behind compact resume views |
| N15 | Expose search coverage, budget context and reuse dependency-bound checks |
| N16 | Compare friction, cost and quality early on equivalent tasks |
| N17 | Simplify quickstart, upgrade guidance and capability status |
| N18 | Demonstrate one optional host adapter |
| N19 | Implement optional one-way Markdown/Obsidian export |
| N20 | Benchmark scale and optimize only demonstrated bottlenecks |
| N21 | Run the broader real-project pilot for broad adoption claims |
| N22 | Automate exact release provenance and publication order |
| N23 | Evaluate a concrete candidate against its actual scope |
| N24 | Publish and verify public surfaces when the next release is requested |

## New review findings and priorities

The deeper review reports eight bounded reproduced behaviors (D01–D08) and two
source/architecture findings (D09–D10). The full plan records their evidence
limits and maps them into the retained N01–N24 tasks. They are not repaired by
publishing the plan.

| Finding | Planned response |
|---|---|
| D01 — Stale lease marks an answer route as write-capable | Separate action authority from evidence profile |
| D02 — Old block survives changed facts | Rebind valid authority and recompute current reasons |
| D03 — Sidecar isolation uses string equality | Resolve concrete targets, aliases and scope overlap |
| D04 — Active decision leaves the searchable Combo view | Separate canonical decisions from presentation limits |
| D05 — Bounded search hides incomplete coverage | Expose coverage and a version-bound continuation cursor |
| D06 — Retry after a post-commit failure can advance the next task | Bind operation ID, expected assignment, revision and durable result |
| D07 — Large valid roadmap exceeds the current-view budget | Compact root with all obligations reachable through detail references |
| D08 — Recovery requires wider scope even after full coverage | Allow new evidence and a changed approach within valid existing scope |
| D09 — Callable contracts are not necessarily connected routes | Match feature claims to actual end-to-end evidence |
| D10 — Shared helpers and product logic are tightly coupled | Incremental refactoring of relevant boundaries, not a full rewrite |

Start with N01/N02, then N03 and the explicit mutation/retry chain in N04.
Collect the initial baseline before changing measured behavior. Optional features
must not block a scoped defect-fix release; broad efficiency and adoption claims
still need their corresponding evidence. Existing useful techniques remain.

## Evidence and remaining work

Release 1.7.0 has a matching tag/build-record commit, verified download assets,
and eight successful CI jobs before publication. Runtime behavior remains
that of 1.6.3 apart from the version string. These release facts are a baseline,
not evidence that the roadmap improvements are complete.

The review retained findings about sync snapshot drift, unbounded Git waits,
declaration-only privacy, coarse authority/target classification, update-path
overlap, capsule validation/resource limits, multi-component cutover semantics
and unproven broad host/usability claims. The
[release limitations](release-1.7.0.md) and full plan explain their boundaries.

## Updates, context and practical acceptance

The proposed updater inventories owned components, plans differences, checks
paths/compatibility/locks, stages a candidate, tests it, activates under an
explicit reader contract, reads back the active runtime and performs bounded
cleanup. Unknown or user-modified content is preserved, not guessed away.
A named rollback generation is not unexplained installation debris.

Context measurements distinguish useful source material, product instructions,
history, tool output and repeated content. Token estimates are labelled;
unknown usage is not zero. No extra model call is required merely to count,
format status or check mechanical authority. Quality must remain comparable
when reporting savings.

The full plan preserves a broad pilot of at least two full weeks **and**
25 real tasks, including at least three genuine restarts/handoffs. This is
required for the corresponding broad practice claims, not an automatic
calendar gate for every narrowly scoped technical bugfix release. Optional
host and export work is required only when that functionality is being delivered
or claimed.

## Scope boundaries

No full rewrite, mandatory cloud/vector service, global stop guard,
unlimited-authority mode, system-wide cleanup or automatic broad vault
integration is part of this plan. Extensions reuse existing data and small
interfaces rather than adding another general policy or agent layer.

A plan, implemented functionality, release readiness, publication,
installation and broad adoption are different statuses. Open or deferred work
must never be reported as delivered.

## Historical releases and references

The diagram below describes the historical foundation milestones, not completion
of the new N01–N24 plan.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/roadmap-dark.svg">
  <img src="../assets/docs/roadmap.svg" alt="Historical foundation milestones through version 1.0.0, not the new planned tasks">
</picture>

### Preserved broad-pilot safeguards

The local R17 implementation is historical runtime groundwork, not proof of the
new N-task improvements. A broad pilot remains a separate decision for one exact
non-production-critical project, with a recorded baseline and reversible scope.
It runs for at least two weeks and 25 real tasks, with at least
three genuine restart or handoff events. Synthetic tasks may test the harness
but never count as pilot success. Rollback restores the project's selected prior
route and preserves evidence. Measurement completion grants no publication,
installation, or adoption authority. These safeguards apply to N21 and its broad
claims, not automatically to every narrowly scoped bugfix release.

- [Full roadmap — English](roadmap-plan.md)
- [Release v1.7.0](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.0)
- [CI for the 1.7.0 release commit](https://github.com/CNTX-PROJECT/OPENCNTX/actions/runs/34386717966)
- [Historical roadmap as shipped with 1.7.0](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.0/docs/roadmap.md)
- [Changelog](../CHANGELOG.md)
