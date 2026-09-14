# OPENCNTX 1.8.0 — implementation and release roadmap

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

The 1.8.0 release is the additive knowledge-layer release. It keeps the 1.7.6
contracts and adds one bounded route at a time. A checkbox is accepted only
when its source, tests and public wording agree.

| Gate | Result in v1.8.0 |
|---|---|
| Reproducible 1.7.6 baseline | Preserved by the release branch and regression suite. |
| Versioned knowledge contracts | `ocx-source-node-v1`, `ocx-link-manifest-v1`, `ocx-search-result-v1`, `ocx-technique-card-v1`, `ocx-project-adoption-v1` and `ocx-footer-contract-v1`. |
| Hierarchical source index | Delivered; deterministic IDs, parent/child depth, digests, privacy and freshness. |
| Own bounded search | Delivered; exact-first scoring, reason codes and load states. |
| Chapter/context integration | Existing 1.7.6 catalog and context routes remain authoritative; the index is a rebuildable projection. |
| Visual and file-order safety | Existing read-only layout audit/plan remains the write boundary; the new index never silently moves files. |
| Technique memory | Delivered as digest-bound cards; recall never executes a card. |
| Existing-project adoption | Delivered as preview-first `BIND_READ_ONLY` manifests. |
| Universal footer | Delivered with explicit fallbacks and `exact` output. |
| Qualification and publication | Full tests, package reproducibility, tag, release assets and public-download verification are required. |

## Stop rules

The release stops on an unsafe path, invalid digest, ambiguous link, cycle in a
`contains` graph, privacy boundary violation, changed release tree, failing
regression, non-reproducible artifact or disagreement between package,
documentation and tag. OpenSpec, Zvec, an embedding service or a new cloud
dependency is not a valid shortcut.

## What remains deliberately outside

OPENCNTX does not become an AI provider, notes-vault synchronizer, automatic
file mover, task executor or authority system. A host may connect the generated
metadata to its own workflow, but the package remains a local, reviewable and
provider-neutral source of context.
