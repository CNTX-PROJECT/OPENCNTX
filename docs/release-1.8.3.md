# OPENCNTX 1.8.3 — full-text search and compatibility

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX 1.8.3 is the local search and compatibility release. It keeps the
1.8.0 knowledge contracts, the 1.8.1 managed installation and adoption
boundaries, and the 1.8.2 English public surface. It adds a faster full-text
projection without changing the authority of project files.

## Delivered

- Add a versioned `search-v2.sqlite` projection using the Python runtime's
  local SQLite FTS5 capability when available.
- Search Markdown and JSON bodies, paths, titles, headings, identifiers, JSON
  paths and JSON values with deterministic lexical scoring and explainable
  reason codes.
- Keep the existing `index-v1.json` format and metadata search available for
  old projects, restricted runtimes and explicit compatibility workflows.
- Exclude generated directories and common build/cache output from the new
  default search scope, while recording the exact scope in the index metadata.
- Decode UTF-8, UTF-8 BOM and UTF-16 BOM text without rewriting source bytes.
  Valid JSON receives structured fields; malformed JSON, JSONL and duplicate-key
  input remain searchable through a raw-text fallback.
- Reuse unchanged source fingerprints during refresh, rehash changed files,
  expose strict and fast freshness checks, and publish a replacement database
  atomically only after SQLite integrity verification.
- Return digest-checked, heading-aware snippets with independent byte and
  estimated-token limits. Source drift is reported as `STALE` or
  `stale_source`, never silently presented as current.
- Broaden existing-project adoption discovery to the full supported-text scope.
  A contextless tree is `EXISTING_UNMANAGED_PARTIAL` and requires a reviewed
  `AUDIT_THEN_BIND` preview digest before its manifest can be written.
- Add an optional hard token budget to context-load planning while preserving
  the byte-budget and digest-reference behavior of the v1 route.

## Compatibility and safety

The source tree remains authoritative. `index-v1.json`, adoption manifests,
project files, Obsidian vaults and human-owned notes are not replaced by the
search database. OPENCNTX does not move, rename, delete or rewrite a project
file during indexing or search. The new database is a rebuildable local cache
under `.opencntx/` and is never uploaded.

An update from 1.8.0, 1.8.1 or 1.8.2 keeps the managed installation journal,
exact rollback artifact, existing v1 stores and public command paths. A new
installation on an existing tree first inventories the broad supported-text
scope. It does not infer ownership or permission from the presence of files.
The `AUDIT_THEN_BIND` boundary remains separate from package health and from
the owner-reviewed `VISUAL_ARTIST` takeover gate.

If SQLite FTS5 is unavailable, the release reports a metadata fallback and the
compatible v1 index remains usable. No external dependency, embedding model,
vector database, network service or package-index upload is required.

## Verification requirements

The exact release commit is qualified by:

1. the complete Python regression and historical compatibility suite;
2. compile, lint, type, schema, diagram, public-English and version gates;
3. body-search, JSON-field, encoding, scope, freshness, incremental, restart,
   atomic-publication and token-budget tests;
4. clean install, update from the prior knowledge-layer releases, rollback,
   reapply, lock and cleanup simulations;
5. two reproducible distribution builds, artifact verification, installation
   smoke tests and uninstall checks; and
6. GitHub read-back of the immutable tag, four assets and English release notes.

## Distribution

The GitHub Release contains exactly:

- `opencntx-1.8.3-py3-none-any.whl`;
- `opencntx-1.8.3.tar.gz`;
- `SHA256SUMS`; and
- `BUILD-RECORD.json`.

There is no PyPI or TestPyPI publication. Use [Install and update](install-and-update.md)
for checksum verification and the controlled managed route.

See the [1.8.3 roadmap](roadmap-1.8.3.md), [knowledge layer](knowledge-layer.md),
[contracts and compatibility](contracts-and-compatibility.md) and [security guide](security.md)
for the surrounding boundaries.
