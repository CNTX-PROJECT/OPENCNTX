# OPENCNTX documentation

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

You do not need to read every page. Choose what you want to do, follow the
smallest matching route, and open the technical reference only when you need
more detail.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/opencntx-overview-dark.svg">
  <img src="../assets/docs/opencntx-overview.svg" alt="Select local files, review and verify a small context package, then decide whether to share it">
</picture>

## Start with a goal

| I want to… | Best page |
|---|---|
| install OPENCNTX and build a first package | [Get started](start-here.md) |
| understand the product in five minutes | [How it works](how-it-works.md) |
| learn the three-command core | [Core commands](core.md) |
| organize a longer project | [Workspace](workspace.md) |
| audit roots, naming, ownership, and duplicates without writes | [Bounded workspace order](layout.md) |
| keep a complete roadmap moving with one approval | [Roadmap continuity](continuity.md) |
| look up an exact command | [Command reference](commands.md) |
| solve a failure | [Troubleshooting](troubleshooting.md) |
| understand what stays local | [Security in plain language](security.md) |

## Core package guides

The core route is the shortest path: choose files, preview, pack, inspect, and
verify.

- [Core commands](core.md) — exact behavior of `init`, `pack`, and `verify`.
- [Context packages](context-packets.md) — package files, limits, hashes, and
  source drift.
- [Contracts and compatibility](contracts-and-compatibility.md) — the frozen
  1.0 public surface and durable-format rules.

## Stable workspace guides

The workspace is optional. Use it when a project needs more structure than one
context package.

- [Workspace](workspace.md) — create the directory, capture sources, diagnose
  writes, and understand the normal project flow.
- [Chapters and catalog](chapters-and-catalog.md) — turn supplied sources into
  reviewed knowledge and rebuild the local index.
- [Context navigation](context-navigation.md) — include only the approved hot
  and warm context for one task.
- [Media and derived text](media.md) — register text that another tool already
  produced without confusing it with the original file.
- [Privacy, storage, and format lifecycle](privacy-storage-lifecycle.md) — audit
  local access, compatibility, migration, cleanup, and restore.
- [Bounded workspace order](layout.md) — verify registered roots, folder roles,
  naming, path ownership, duplicates, and the objective stop rule read-only.

## Universal roadmap continuity

- [Roadmap continuity and AUTO PILOT](continuity.md) — keep the roadmap,
  current detail, evidence and next trigger in a restart-safe local store;
  export a portable capsule and optionally mirror filtered records to private
  Git or GitHub.

## Decisions and bounded work

- [Playbooks and roles](playbooks-and-roles.md) — define a method and the
  actions an executor may use.
- [OWNER flow](owner-flow.md) — move from goal to proposal, approval, result,
  review, and closure without letting the tool approve itself.

## Project and technical reference

- [Platforms and CI](platforms.md) — supported Python versions, Windows/Ubuntu
  coverage, and what green CI really proves.
- [Release artifacts](release-artifacts.md) — wheel, sdist, checksums, build
  record, and the exact publication boundary.
- [Public roadmap](roadmap.md) — completed milestones and current state, with no
  promises about future features.
- [FAQ](faq.md) — short answers to common questions.
- [Glossary](glossary.md) — plain meanings of fixed project terms.
- [Brand guide](brand.md) — official colors, wordmarks, diagrams, and visual
  rules.

## Product boundary

OPENCNTX creates local, explicit, verifiable files. It does not call an AI
model, choose a provider, upload context, run an agent, execute supplied
content, or replace human review. **Any model** means that reviewed output can
be used with a tool that accepts text or files.

Use `opencntx --help` and the relevant nested `--help` route for exact command
options. Use the root [Security Policy](../SECURITY.md) as the canonical
technical safety boundary.

[Back to the project overview](../README.md)
