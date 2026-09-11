# OPENCNTX 1.7.4 — Project roadmap routing

[Overview](../README.md) · [Get started](start-here.md) · [Project roadmaps](project-roadmaps.md) · [Releases](releases.md) · [Roadmap](roadmap.md)

Version 1.7.4 adds a small provider-neutral planning layer for routing project
work without losing continuity. Its publication boundary is the immutable
`v1.7.4` GitHub Release and the four attached release assets.

## Included

- Project-aware routing under one master roadmap.
- Immediate step attachment for short related project work.
- A new child roadmap for each distinct large outcome.
- Exact roadmap and step return anchors for side topics and rollover.
- A continuation decision that favors safe authorized progress while work
  remains and requires evidence before completion.
- A deterministic byte-budgeted context plan that references unchanged sources
  by SHA-256 and reports measured loaded-byte reduction.
- Regression cases for projectless information, short work, extensions,
  independent outcomes, side topics, rollover, completion, and context bounds.

## Explicit boundaries

- The host supplies project relationship and task size; OPENCNTX does not claim
  natural-language intent classification.
- The API returns decisions but does not create files, mutate a host roadmap,
  start an AI, or grant authority.
- Installation does not activate a Codex, editor, or chat hook.
- Loaded-byte reduction is measured against the supplied source metadata. It is
  not a universal token, latency, or monetary-cost guarantee.
- Existing CLI routes and durable version-1 formats remain unchanged.

## Distribution

The GitHub Release contains exactly:

- `opencntx-1.7.4-py3-none-any.whl`;
- `opencntx-1.7.4.tar.gz`;
- `SHA256SUMS`;
- `BUILD-RECORD.json`.

OPENCNTX is not published on PyPI or TestPyPI. Install the exact Git tag with
the command in [Get started](start-here.md).

[Project roadmap guide](project-roadmaps.md) · [Release artifacts](release-artifacts.md) · [Documentation home](README.md)
