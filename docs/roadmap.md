# Public roadmap

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

[Release scope](release-1.7.0.md) · [Full roadmap in Dutch](roadmap-plan.nl.md)

## Current status

The new roadmap is published as a plan, not as implemented functionality.
It contains **six phases and 24 tasks (N01–N24)**. All tasks are planned;
none of these new implementation tasks is marked complete.

- Published Stable software baseline: **v1.7.0**.
- Source release target: `v1.7.1` (unpublished documentation candidate only).
- Package version: `1.7.1`.
- The version increment is required by the existing repository rule for
  post-release documentation changes. It is not a new GitHub Release.
- The implementation release/version for the roadmap remains undecided.
- No installation, host activation or roadmap implementation is performed
  by publishing this documentation.

The [complete Dutch plan](roadmap-plan.nl.md) contains the detailed work,
acceptance criteria, dependencies, five user requirements, evidence mapping
and restart instructions. This English page is an overview of that plan,
not an independently maintained task ledger.

The existing 1.7.0 distribution contains exactly
opencntx-1.7.0-py3-none-any.whl, opencntx-1.7.0.tar.gz, SHA256SUMS and
BUILD-RECORD.json. Those release files are not replaced by this roadmap publication.

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
| C — Installation and diagnosis | N10–N13 | Owned, recoverable updates and one read-only diagnosis |
| D — Context and usability | N14–N17 | Compact resume context, measurements and a clear quickstart |
| E — Selected extensions | N18–N21 | Optional host/export, scale evidence and broader pilot |
| F — Release | N22–N24 | Automated provenance, scoped readiness and verified publication when requested |

This is not a requirement to stop after each phase. Independent work can
proceed once its actual dependencies are satisfied. Release automation can
start early. Initial usability measurements do not wait for optional exports.

## Task index

| Task | Deliverable |
|---|---|
| N01 | Establish development source, reusable evidence and change scope |
| N02 | Turn the four reproduced defects into official regression tests |
| N03 | Bind concrete actions, authority and multiple targets |
| N04 | Connect ANSWER_ONLY, LIGHT_TASK and GOVERNED_FLOW to real routes |
| N05 | Bind sync preview and delivery to one immutable snapshot |
| N06 | Bound Git operations and distinguish declared from verified privacy |
| N07 | Reject cross-component update-path overlap before mutation |
| N08 | Enforce unique capsule records and resource-bounded verification |
| N09 | Harmonize critical JSON and filesystem checks |
| N10 | Define installation ownership and supported compatibility |
| N11 | Implement a journaled update state machine with recovery |
| N12 | Prove upgrade, uninstall, rollback and orphaned-hook behavior |
| N13 | Provide one read-only diagnosis with actionable explanations |
| N14 | Deliver one compact, source-bound resume package |
| N15 | Measure and budget actual context without bookkeeping model calls |
| N16 | Compare friction, cost and quality early on equivalent tasks |
| N17 | Simplify quickstart, upgrade guidance and capability status |
| N18 | Demonstrate one optional host adapter |
| N19 | Implement optional one-way Markdown/Obsidian export |
| N20 | Benchmark scale and optimize only demonstrated bottlenecks |
| N21 | Run the broader real-project pilot for broad adoption claims |
| N22 | Automate exact release provenance and publication order |
| N23 | Evaluate a concrete candidate against its actual scope |
| N24 | Publish and verify public surfaces when the next release is requested |

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

- [Full roadmap — Dutch](roadmap-plan.nl.md)
- [Release v1.7.0](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.0)
- [CI for the 1.7.0 release commit](https://github.com/CNTX-PROJECT/OPENCNTX/actions/runs/34386717966)
- [Historical roadmap as shipped with 1.7.0](https://github.com/CNTX-PROJECT/OPENCNTX/blob/v1.7.0/docs/roadmap.md)
- [Changelog](../CHANGELOG.md)
