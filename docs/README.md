# OPENCNTX documentation

[Start here](start-here.md) · [How it works](how-it-works.md) · [Advanced / Alpha workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All docs](README.md)

Use this page as the complete index. You do not need to read everything. Pick
the smallest route that matches your current goal.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/opencntx-overview-dark.svg">
  <img src="../assets/docs/opencntx-overview.svg" alt="Select local files, review and verify a small context package, then decide whether to share it">
</picture>

## First visit

1. [Start here](start-here.md) — install OPENCNTX and create your first package
   in one continuous guide.
2. [How it works](how-it-works.md) — understand the product before using more
   advanced workspace features.
3. [Troubleshooting](troubleshooting.md) — solve a specific failure without
   reading unrelated pages.
4. [FAQ](faq.md) — get short answers to common questions.

## Core context packages

- [Core commands](core.md) — exact behavior of `init`, `pack`, and `verify`.
- [Context packages](context-packets.md) — package files, budgets, hashes,
  inspection, and source drift.
- [Contracts and compatibility](contracts-and-compatibility.md) — the public
  surface catalog, 36 durable formats, fixtures, and fail-closed version rules.
- [Command reference](commands.md) — all 49 documented CLI paths.

## Advanced / Alpha workspace

- [Advanced / Alpha workspace](workspace.md) — directory structure, control snapshot, and exact
  source capture.
- [Chapters and catalog](chapters-and-catalog.md) — reviewed revisions,
  dependencies, freshness, and the replaceable catalog.
- [Context navigation](context-navigation.md) — small hot, warm, and cold task
  context.
- [Media and derived text](media.md) — safely register UTF-8 text that another
  tool already produced.
- [Privacy, storage, and format lifecycle](privacy-storage-lifecycle.md) —
  audit local trust, storage, compatibility, migration, and explicit cleanup.

## Approval and bounded work

- [Playbooks and roles](playbooks-and-roles.md) — methods, allowed actions, and
  executor-package limits.
- [OWNER flow](owner-flow.md) — explicit proposal approval, bounded work,
  review, result decision, and closure.

## Safety and project reference

- [Security in plain language](security.md) — local trust boundary and safe
  handling.
- [Platforms and CI](platforms.md) — supported Python versions and live test
  evidence.
- [Release artifacts](release-artifacts.md) — clean candidate builds,
  checksums, reproducibility limits, installation smoke, and publication gate.
- [Public roadmap](roadmap.md) — completed milestones without unapproved
  promises.
- [Glossary](glossary.md) — fixed meanings of project terms.
- [Brand guide](brand.md) — official colors, wordmarks, avatar, diagrams, and
  reproduction rules.

## Product boundary

OPENCNTX creates local, explicit, verifiable files. It does not call an AI
model, choose a provider, upload context, run an agent, execute supplied
content, or replace human review. **Any model** means that you may use reviewed
output with a tool that accepts text or files.

Use `opencntx --help` and the relevant nested `--help` route as the exact
source for command options. Use the root [Security Policy](../SECURITY.md) as
the canonical technical safety boundary.

[Back to the project README](../README.md)
