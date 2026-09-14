# OPENCNTX 1.8.0

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX 1.8.0 adds a local knowledge layer for projects whose knowledge grows
from one main Markdown file into child and sub-child files. It keeps source
files authoritative and creates deterministic, digest-bound metadata only.

## Delivered

- Hierarchical Markdown/JSON/TOML/YAML/text source nodes with stable IDs,
  parent links, depth, privacy, freshness and SHA-256 digests.
- Typed local links and bounded exact-first search with score components,
  reason codes, loaded/referenced/skipped states and hard byte budgets.
- Evidence-bound technique cards with explicit preconditions, steps, risks,
  outputs, source digests and `PROVEN`/`STALE`/`PROPOSED` state.
- Read-only existing-project adoption manifests for controls, roadmaps, tasks,
  playbooks, roles, chapters and techniques. Writing the manifest never moves
  or rewrites those files.
- Provider-neutral footer contracts with complete fallbacks and an `exact`
  JSON profile for machine-readable output.
- Public documentation, examples, schemas and release metadata that describe
  the implemented behavior and its safety boundaries.

## Commands

```powershell
opencntx knowledge index build --root .
opencntx knowledge index search "current roadmap" --index .opencntx/index-v1.json
opencntx knowledge adopt --root .
opencntx knowledge footer --status "Ready" --now "Inspect results"
```

## Qualified boundaries

The release remains local-first and dependency-free. It does not call an AI,
upload sources, execute remembered techniques, infer OWNER authority, or use
OpenSpec, Zvec, embeddings or a remote semantic index. Search budgets describe
selected local bytes; they are not universal model-token savings. An index is a
derived projection and can be deleted and rebuilt from source files.

The existing 1.7.6 core pack, workspace, continuity, layout and installer
routes remain available and are covered by the regression suite. See the
[knowledge layer guide](knowledge-layer.md), [install guide](install-and-update.md)
and [release artifacts](release-artifacts.md) for exact commands and evidence.
