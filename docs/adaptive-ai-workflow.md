# Adaptive AI workflow

[Overview](../README.md) · [Get started](start-here.md) · [Roadmap continuity](continuity.md) · [Security](security.md) · [All guides](README.md)

> **Stable in v1.3.0:** this page describes the released R11 contracts. The R12
> visual presentation extension is part of the unpublished v1.4.0 candidate.

This workflow helps an AI-assisted project stay understandable and on track
without assuming one AI provider, user interface, storage product, project
size, or technical skill level. OPENCNTX remains model-free: a compatible AI
host interprets the human request, while OPENCNTX records and verifies the
bounded state.

## Ordinary language by default

A person may describe a goal, problem, preference, or decision in ordinary
language. A compatible host translates that intent into bounded technical
contracts, tasks, tests and evidence. The normal answer returns to plain,
compact language.

A technical user may deliberately select detailed output. That changes only
the presentation. It never changes the approved scope, durable state, evidence
or release authority.

## Visual presentation

A compatible visual host can pair `VISUAL_ARTIST` with `BOUNDED_PERFECTION` to
turn the same governed state into a clear human-facing surface. The visual
intent binds audience, primary task, hierarchy, responsive behavior,
accessibility, evidence, and forbidden presentation patterns. The paired
review checks design quality and bounded implementation together.

Text-only hosts remain first-class. They preserve the same task order, named
states, evidence, and stop conditions without depending on color or graphical
controls. See the [visual system](visual-system.md) for the canonical tokens,
components, fallbacks, and ownership boundary.

## Choose how much to start

Before work starts, the host presents exactly two choices:

1. **Current assignment only** — stop after the current roadmap assignment is
   proven or blocked.
2. **Remaining roadmap** — continue through the bounded remaining assignments,
   stopping for a material scope or risk change, a real external action, or the
   declared recovery limit.

A graphical host may show two clickable controls when it can bind the exact
selection. A CLI or text-only host shows equivalent copyable commands:

```text
START <current-assignment-id>
```

```text
AUTO PILOT <roadmap-id>
```

The controls and commands resolve to the same authority digest. Merely showing
a choice grants no authority. `AUTO PILOT` remains the direct expert route.
Important exact decisions, such as publication or a changed risk boundary,
still use one explicit copyable command.

These are host-integration contracts, not new v1.3.0 CLI commands. The current
released flow continues to use its documented
`opencntx flow start ... --approval "AUTO PILOT"` route.

## Durable state, not chat memory

The state capsule binds the roadmap revision, current assignment,
current internal task, status, next action, next assignment, authority,
continuation mode, recovery round and latest evidence digest.

A visible footer or progress message is compiled from that durable state. It
is never treated as the source of truth. Before a substantive answer, the host
rereads the live roadmap, task checklist, authority and latest receipt. If
they disagree, work stops for reconciliation instead of guessing.

An active approved assignment with a safe next internal action keeps running.
A completed assignment is clearly distinguished from a completed roadmap. A
later roadmap assignment is never started merely because it was displayed.

## Restart and session rollover

Compact, digest-bound checkpoints preserve the human goal, technical
interpretation, decisions, changed paths, evidence meaning, risks and exact
next action. A new session can resume from that capsule without reconstructing
authority from an old answer.

Hosts can prepare a rollover before their own practical chat limit. The
contract does not assume one provider's context window or token counter. A
provider may supply exact metrics; unavailable metrics stay explicitly
unavailable rather than estimated.

## Adaptive local storage

One data contract supports four profiles:

| Need | Candidate profile |
|---|---|
| small local project | compact files, no database required |
| repeated local lookup | local incremental index |
| very large local project | sharded index plus content-addressed large bytes |
| shared team project | identity, roles, audit, locking and compare-and-swap |

The system escalates only after measured need. It deduplicates exact bytes,
keeps queries bounded and preserves provenance. A database is not a universal
requirement, and external storage is not the canonical authority.

## Safe updates

An update first detects the installed and target formats, previews the exact
plan, checks compatibility and free space, and creates a byte-verified backup.
It stages and validates the new version before one atomic cutover. Failure
restores the previous active state. A successful cutover proves that no old
active residue remains; historical evidence may remain separately labelled.

The old active installation is therefore never partly overwritten or deleted
before the replacement is ready and recoverable.

## Large workloads

A large target begins with a representative pilot. Identity, request classes,
quotas, queues, retry limits and checkpoints connect that pilot to the complete
target. Scale gates make the jump from a few items to thousands explicit.

Assurance scales with risk:

- **Light** for repeatable low-risk work;
- **Standard** for normal project changes;
- **Critical** for high-impact or irreversible boundaries.

Evidence is reused only when its exact inputs, policy, implementation and
environment bindings still match.

## Optional specification companion

A specification companion can refine a substantial approved change into
requirements, design and testable tasks. It does not approve, execute, accept
or publish work.

[OpenSpec](https://github.com/Fission-AI/OpenSpec) is an optional recommended
companion supported by this design. The onboarding contract first detects
whether a compatible installation already exists:

- compatible: reuse it without reinstalling;
- absent or outdated: show an exact install or update preview;
- damaged or ambiguous: stop and explain the minimum recovery.

Installation or update always needs explicit user approval. The host may then
follow the official [OpenSpec installation guidance](https://github.com/Fission-AI/OpenSpec#installation)
and initialize only the selected projects and AI tools. OPENCNTX remains fully
usable without OpenSpec and never silently installs it as a runtime dependency.

## Optional continuity destinations

A user may opt in to a notes application, synchronized folder, private
repository or comparable destination. The first setup asks whether it applies
only to the current project or to all explicitly registered projects, and
whether an existing naming and storage method must be preserved.

Each target remains project-isolated, filtered and disabled by default. Local
durable state stays canonical. Offline or conflicting targets are latched and
reported; they do not erase or rewrite local truth.

The v1.3.0 release provides the neutral target and batch contracts. It does not
bundle a connector for every external product and does not authorize network
writes. The Stable v1.3.0 private Git/GitHub replica remains the only released
optional remote continuity route described in [Roadmap continuity](continuity.md).

## Release boundary

Local tests, a wheel build, a commit, or a green candidate report prove only
technical readiness. Merge, push, tag, release creation and package-index
publication remain separate explicit decisions. v1.3.0 remains the public
Stable release until a later candidate completes those publication gates.

## Related pages

- [OWNER flow](owner-flow.md)
- [Roadmap continuity](continuity.md)
- [Privacy, storage, and format lifecycle](privacy-storage-lifecycle.md)
- [Public roadmap](roadmap.md)

[Documentation home](README.md)
