# OPENCNTX 1.8.3 — full-text search and compatibility roadmap

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

This roadmap records the bounded 1.8.3 implementation. It is additive to the
1.8.0 knowledge layer and the 1.8.1–1.8.2 installation, adoption, rollback and
English-surface work. It does not silently close the real-project
`VISUAL_ARTIST` takeover gate.

## Objective

Make Markdown and JSON knowledge recall fast, compatible and economical on
small, large and mega projects while keeping source ownership, digest
freshness, upgrade safety and explicit adoption review intact.

## Work packages

| ID | Work package | Acceptance evidence | Status |
|---|---|---|---|
| S01 | Freeze the simulation-derived search contract | Small/large/mega and short/complex workloads are represented by bounded fixtures | Complete |
| S02 | Add capability-based SQLite FTS5 projection | `search-v2.sqlite` is local, versioned, external-content and falls back to v1 metadata search | Complete |
| S03 | Add full-text and structured recall | Body-only Markdown hits, JSON paths/values, identifiers and exact-first scores are tested | Complete |
| S04 | Add safe scope and encoding compatibility | Generated output is excluded; UTF-8/BOM/UTF-16 and raw JSON fallback states are visible | Complete |
| S05 | Add incremental and freshness controls | Unchanged fingerprints are reused, changed sources are refreshed, strict status finds drift, and failed publication preserves the previous database | Complete |
| S06 | Add bounded snippets and token-aware planning | Source bytes, snippet characters and estimated tokens are independently enforced | Complete |
| S07 | Broaden unmanaged-project discovery | Existing contextless trees report `EXISTING_UNMANAGED_PARTIAL` and require `AUDIT_THEN_BIND` | Complete |
| S08 | Qualify installation and release compatibility | Clean install, 1.8.0/1.8.1/1.8.2 update, rollback, reapply, lock, package and public-English gates pass | Complete |
| S09 | Real host visual takeover | A real owner project completes audit, digest-bound write, second-run zero-write and rollback evidence | Deferred owner gate |

## Explicit non-goals

- No translation or rewrite of human-owned project files.
- No automatic import of an Obsidian backup or a second `.opencntx` store in a
  vault.
- No vector database, embeddings, query expansion, remote index or hidden
  semantic reranker.
- No automatic owner, host, model, GitHub or Obsidian authorization.
- No claim that a clean temporary fixture proves a real-project visual takeover.

## Compatibility matrix

| Starting state | 1.8.3 behavior |
|---|---|
| Existing 1.8.0 knowledge project | Keep v1 metadata and adoption formats; add v2 search by explicit index build |
| Existing 1.8.1 managed installation | Use the managed update journal and exact rollback path; project files remain unchanged |
| Existing 1.8.2 installation | Perform a normal versioned update and retain the English surface and v1 search |
| Existing project without context management | Broad read-only audit, then `AUDIT_THEN_BIND` with a reviewed preview digest |
| Empty new project | Report `EMPTY_NEW_PROJECT`; bootstrap remains an explicit project action |
| Restricted SQLite runtime | Keep v1 metadata search and report `FALLBACK_METADATA` |

## Release gate

The 1.8.3 release is complete only when package metadata, current public
surfaces, source tree, tag, artifacts, CI, compatibility tests and release
notes agree on 1.8.3. A stale source, unsafe scope, unsupported encoding,
failed FTS capability fallback, token overflow, changed digest, dirty release
tree or public-language finding keeps the relevant gate closed. The deferred
`VISUAL_ARTIST` item remains visible and is not relabeled as complete by this
release.

## Evidence links

- [1.8.3 release scope](release-1.8.3.md)
- [Knowledge layer](knowledge-layer.md)
- [1.8.2 release roadmap](roadmap-1.8.2.md)
- [1.8.1 integration roadmap](roadmap-1.8.1.md)
- [Current release status](releases.md)
- [Public artifact verification](release-artifacts.md)
