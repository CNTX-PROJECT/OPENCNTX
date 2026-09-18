# Knowledge and search

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX 1.8.3 retains the first-party, local index for projects that have one main
Markdown file with child files, nested child files, JSON records, roadmaps and
technical notes. It keeps the original files authoritative and creates only
digest-bound projections under `.opencntx/`.

## What it does

1. **Builds a hierarchy.** Every supported Markdown, JSON, TOML, YAML or text
   file receives a stable `OCX-NODE-*` identity, relative path, parent, depth,
   SHA-256 digest, privacy label, title, headings and a short preview. UTF-8,
   UTF-8 BOM and UTF-16 BOM sources are decoded without changing their source
   bytes.
2. **Resolves typed links.** Markdown and wiki links become bounded records such
   as `contains`, `requires`, `supports`, `history_of`, `supersedes`,
   `verify_live` and `references`. Unresolved targets remain visible instead
   of being silently dropped.
3. **Searches full text locally.** The compatible `index-v1.json` remains
   available while `search-v2.sqlite` uses capability-detected SQLite FTS5 for
   Markdown and JSON bodies, identifiers, headings, paths and JSON paths. A
   missing FTS5 capability falls back to the v1 metadata search.
4. **Enforces freshness and load budgets.** Search status distinguishes
   `CURRENT`, `STALE`, `PARTIAL`, `NEEDS_BUILD` and `INVALID`. Results return
   `loaded`, `referenced`, `skipped` and `stale_source` states with exact byte
   totals, bounded heading-aware snippets and an explicit token estimate.
5. **Remembers proven techniques.** A technique card records its trigger,
   preconditions, steps, tools, risks, outputs, source digests and verification
   state. A card is recallable; OPENCNTX never executes its steps automatically.
6. **Audits existing work safely.** An adoption manifest inventories the full
   supported-text scope, classifies active versus archive boundaries, and
   reports case collisions, duplicate ordinals, unresolved links, cycles and
   links/junctions. A contextless existing project is explicitly
   `EXISTING_UNMANAGED_PARTIAL` and requires `AUDIT_THEN_BIND` with a reviewed
   preview digest; ownership is never inferred as permission to rewrite.
7. **Renders a universal footer.** The provider-neutral footer contract always
   emits a value or an explicit fallback (`no assignment note`, `unknown`,
   `not determined` or `not measured`). Exact JSON/CSV/code output can use the
   `exact` profile so the payload is never corrupted by Markdown.

## Build and search

From the project root:

```powershell
opencntx knowledge index build --root .
opencntx knowledge index status --root .
opencntx knowledge index search "current roadmap" --root .
```

The build writes the compatible `index-v1.json` and, when SQLite FTS5 is
available, an atomically published `search-v2.sqlite`. Generated directories
such as `build`, `dist`, `site` and common tool caches are excluded by default.
The v2 builder reuses unchanged size/mtime fingerprints and hashes changed
files; pass `--strict` when every source must be rehashed. The status command is
read-only and performs a strict digest check by default; `--fast` performs a
quick fingerprint check. A failed refresh leaves the previous search database
untouched.

Search accepts `--max-bytes`, `--max-tokens` and `--max-snippet-chars`. The
index stores normalized searchable fields as a local cache, but source files
remain authoritative and matched sources are digest-checked before snippets
are loaded. There is no embedding, vector database, remote index or hidden
semantic score.

## Technique cards

Create a JSON card that follows `ocx-technique-card-v1`, validate and store it:

```powershell
opencntx knowledge technique add --root . --input .\technique-card.json
opencntx knowledge technique list --root .
```

Cards live in `.opencntx/techniques/` and are local derived memory. Their source
digests make stale knowledge visible; `PROVEN` is evidence of a past check, not
an instruction to run a tool.

## Existing-project adoption

Preview first. The default command is read-only:

```powershell
opencntx knowledge adopt --root .
opencntx knowledge adopt --root . --write \
  --expected-manifest-digest REVIEWED_PREVIEW_DIGEST
```

The preview returns `audit.project_state`, `audit.status` and a deterministic
`manifest_digest`. A new empty root is `EMPTY_NEW_PROJECT`. A project without
context-management markers is `EXISTING_UNMANAGED_PARTIAL`; its write command
must receive the reviewed preview digest. The command refuses source drift and
writes only the digest-bound `.opencntx/adoption-v1.json` manifest. It does not
move, rename, delete or rewrite project files. A `BLOCKED` or `PARTIAL` audit
remains an explicit review outcome and cannot be mistaken for a successful
visual takeover.

## Footer profiles

```powershell
opencntx knowledge footer --status "Ready" --now "R180-01" --thereafter "Run the tests"
opencntx knowledge footer --profile exact
```

`commonmark` is the normal human view; `portable` is suitable for hosts that
only preserve plain text; `plain` removes Markdown emphasis; `exact` returns
the closed JSON contract and its digest. Missing telemetry is explicit and
never blocks the result.

A host that has exact, current telemetry may pass a session-bound
`ocx-footer-host-envelope-v1` JSON object:

```powershell
opencntx knowledge footer --from-host-envelope .\footer-envelope.json
```

The package verifies the closed fields, matching session identities, source
digest and envelope digest before rendering. Complete `OK` telemetry is
formatted for the Dutch owner footer; `UNAVAILABLE` produces explicit
fallbacks. It never accepts partial metrics and never reads raw host or
transcript content.

## Boundaries

The indexes are local projections. They do not replace canonical project files,
do not automatically reorganize a notes vault, do not select an AI model, do
not grant authority, and do not upload data. OpenSpec, Zvec, embeddings and
external search services are not runtime dependencies. SQLite FTS5 is used
only when the Python runtime exposes that local capability.

[Security](security.md) · [Contracts and compatibility](contracts-and-compatibility.md) · [Releases](releases.md)

## Compact output in 1.8.5

`opencntx preview-search "query" --root . --compact --delivery-report` preserves the existing result while removing formatting whitespace. The ordinary index search is unchanged. See [release status](releases.md) for limits and [commands](commands.md) for syntax.
