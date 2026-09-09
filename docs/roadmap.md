# Product roadmap

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

This page always points to the latest OPENCNTX development plan.
Looking for the feature that manages your own project tasks?
Use [Workflow continuity](continuity.md) instead.

## Latest roadmap — 1.7.3

**Revision 4 · Planned · Published software remains v1.7.1 Stable.**

**[Read the complete 1.7.3 roadmap →](roadmap-plan.md)**

The plan retains 24 tasks (N01–N24). Twenty-one remain planned for the base
delivery and release process; three extensions are explicitly deferred.
Publishing the roadmap does not implement it or create a software release.

## What 1.7.3 is intended to improve

| Priority | Intended result |
|---|---|
| Reliable progress | Retrying one operation cannot complete a different task |
| Fewer unnecessary stops | Current, concrete authority; optional failures stay separate from core success |
| Durable memory | Valid decisions and unfinished work remain reachable beyond compact view limits |
| Compact resumption | Small current context with complete, revision-bound detail references |
| Crash-safe updates | Recover after process death; each reader sees a compatible generation |
| Measured overhead | Separate real outcomes, context bytes, retries and actual host costs |

These are targets, not delivered capabilities. Host policies, legitimate safety
boundaries, missing access and explicit user stops continue to apply.

## Delivery sequence

| Phase | Work |
|---|---|
| A — Baseline | Preserve source-bound evidence and regression cases |
| B — Core reliability | Fix operation identity, lock lifetime, authority, sync and input handling |
| C — Memory | Preserve canonical records and provide compact, complete resumption |
| D — Updates | Prove one managed local channel, reader consistency and lifecycle recovery |
| E — Measurement | Compare equivalent workloads and keep feature claims honest |
| F — Release | Verify final source, CI and artifacts; publish software only when requested |

Extra host integration (N18), one-way Obsidian export (N19) and the broad
real-project pilot (N21) remain outside the base scope. Broad savings and host
claims still require the corresponding evidence.

## Why the plan changed

The 1.7.2 candidate assessment completed two long routes of 100 tasks each, but
separate fault probes exposed twelve unmet criteria. Additional update probes
showed mixed-generation reads and a stale lock preventing recovery after hard
process termination.

This is **not** twelve failed tasks out of one hundred. The full plan keeps
those measurements separate and gives each defect a specific acceptance test.
It preserves useful existing techniques and fixes their transitions rather
than adding global policy layers.

## Earlier plans and releases

| Record | Where to read it |
|---|---|
| Current 1.7.3 plan, revision 4 | [Complete roadmap](roadmap-plan.md) |
| Previous 1.7.2 plan, revision 3 | [Fixed historical English snapshot](https://github.com/CNTX-PROJECT/OPENCNTX/blob/f6edbbf6d9d81310c37a55036f7d9794e38e109b/docs/roadmap-plan.md) |
| Shipped software and known limitations | [Releases](releases.md) |
| Change history | [Changelog](../CHANGELOG.md) |

Historical plans are records of intent at that time, not proof of completed
features. The complete current plan is the only active implementation backlog.

[Read the complete roadmap](roadmap-plan.md) · [Documentation home](README.md)
