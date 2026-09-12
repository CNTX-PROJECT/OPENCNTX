# Documentation

[Project home](../README.md) · [Get started](start-here.md) · [Roadmap](roadmap.md) · [Releases](releases.md) · [Support](../SUPPORT.md)

Choose the smallest route that matches your task. You do not need to read
every guide.

The default route remains [Get started](start-here.md): initialize, preview,
pack, inspect and verify. Workspace and continuity are optional.

## Start here

| You need… | Read |
|---|---|
| Installation, a first package, updates or removal | [Get started](start-here.md) |
| A short explanation of the product | [How it works](how-it-works.md) |
| The latest development plan | [Roadmap](roadmap.md) — 1.7.5; [complete historical plan](roadmap-plan.md) |
| Published software versus future work | [Releases and current status](releases.md) |
| Help with a failure | [Troubleshooting](troubleshooting.md) · [Support](../SUPPORT.md) |

Current software: **v1.7.5**. See the [1.7.5 release scope](release-1.7.5.md)
for legacy-safe recovery, project-aware routing, context economy, and explicit
host boundaries.

## Core package guides

New to the workflow? Start with the [visual tour](visual-tour.md) for local
knowledge, an optional GitHub copy, readable notes and small-to-mega task planning.

For selecting local files and preparing reviewable context.

- [Core commands](core.md) — initialize, preview, pack and verify.
- [Context packages](context-packets.md) — files, budgets, hashes and source drift.
- [Security in plain language](security.md) — privacy, exclusions and limitations.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/opencntx-overview-dark.svg">
  <img src="../assets/docs/opencntx-overview.svg" alt="Select local files, review a small context package, verify exact bytes and choose whether to share">
</picture>

## Stable workspace guides

For longer projects that need more structure than one context package.

- [Workspace](workspace.md) — project structure, source capture and recovery.
- [Chapters and catalog](chapters-and-catalog.md) — reviewed knowledge and local indexing.
- [Context navigation](context-navigation.md) — relevant context for one task.
- [Media and derived text](media.md) — register externally produced text.
- [Privacy, storage and lifecycle](privacy-storage-lifecycle.md) — compatibility, cleanup and restore.
- [Bounded workspace order](layout.md) — read-only root, ownership and duplicate audits.

## Workflow and resumption

These guides describe your project workflow, not OPENCNTX's development roadmap.

- [Roadmap continuity and AUTO PILOT](continuity.md) — native task state, evidence and handoff.
- [Project roadmap routing](project-roadmaps.md) — small steps, child roadmaps, return anchors, and bounded context.
- [Goal-bound workflows](goal-bound-workflows.md) — request, action and outcome binding.
- [Adaptive AI workflow](adaptive-ai-workflow.md) — existing host contracts, storage and presentation boundaries.
- [Playbooks and roles](playbooks-and-roles.md) — methods and permitted actions.
- [OWNER flow](owner-flow.md) — proposal, authority, review and closure.

The routing rules are implemented as a provider-neutral Python API. They do not
imply that every host has connected that API to its own chat interface.

## Reference and maintenance

- [Commands](commands.md) — exact CLI syntax.
- [FAQ](faq.md) · [Glossary](glossary.md) — short answers and terminology.
- [Contracts and compatibility](contracts-and-compatibility.md) — public surface and durable formats.
- [Platforms and CI](platforms.md) — supported environments and evidence limits.
- [Release artifacts](release-artifacts.md) — builds, checksums and provenance.
- [Visual system](visual-system.md) · [Brand guide](brand.md) — accessible presentation and assets.
- [Contributing](../CONTRIBUTING.md) · [Changelog](../CHANGELOG.md) — development and history.

## Product boundary

[Legacy recovery without a Codex reset](legacy-recovery.md) describes the
published v1.7.5 staging route and its deliberate safety boundaries.

OPENCNTX creates local, explicit, verifiable files. It does not call an AI,
choose a provider, upload context or execute supplied content. Reviewed output
can be used with tools that accept text or files.

Use [Security Policy](../SECURITY.md) for the exact safety boundary and private
vulnerability reporting. Use [Support](../SUPPORT.md) for ordinary questions.

[Back to project home](../README.md)
