# The OPENCNTX 1.8.2 knowledge layer

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX 1.8.2 retains the first-party, local index for projects that have one main
Markdown file with child files, nested child files, JSON records, roadmaps and
technical notes. It keeps the original files authoritative and creates only
digest-bound metadata under `.opencntx/`.

## What it does

1. **Builds a hierarchy.** Every supported Markdown, JSON, TOML, YAML or text
   file receives a stable `OCX-NODE-*` identity, relative path, parent, depth,
   SHA-256 digest, privacy label, title, headings and a short preview.
2. **Resolves typed links.** Markdown and wiki links become bounded records such
   as `contains`, `requires`, `supports`, `history_of`, `supersedes`,
   `verify_live` and `references`. Unresolved targets remain visible instead
   of being silently dropped.
3. **Searches exact-first.** Path, title and heading matches are preferred over
   the short preview. Every result includes its score components and reason
   codes. There is no embedding, vector database, remote index or hidden
   semantic score.
4. **Enforces a load budget.** Search returns `loaded`, `referenced` and
   `skipped` states with byte totals. A byte budget is evidence about local
   selection, not a promise about model tokens.
5. **Remembers proven techniques.** A technique card records its trigger,
   preconditions, steps, tools, risks, outputs, source digests and verification
   state. A card is recallable; OPENCNTX never executes its steps automatically.
6. **Audits existing work safely.** An adoption manifest inventories existing
   controls, roadmaps, tasks, playbooks, roles, chapters and technique cards,
   classifies active versus archive boundaries, and reports case collisions,
   duplicate ordinals, unresolved links, cycles and links/junctions. The
   proposed action is `BIND_READ_ONLY`; ownership is never inferred as
   permission to rewrite.
7. **Renders a universal footer.** The provider-neutral footer contract always
   emits a value or an explicit fallback (`no assignment note`, `unknown`,
   `not determined` or `not measured`). Exact JSON/CSV/code output can use the
   `exact` profile so the payload is never corrupted by Markdown.

## Build and search

From the project root:

```powershell
opencntx knowledge index build --root .
opencntx knowledge index search "current roadmap" --index .opencntx/index-v1.json
```

The build is deterministic and writes only the selected metadata file. It
refuses unsafe paths, invalid UTF-8, source escapes, duplicate identities,
unbounded depth, byte/file budget overflow and `contains` cycles. Run it again
after a source change; unchanged source bytes keep their identity and digest.

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

The preview returns `audit.status` and a deterministic `manifest_digest`. The
write command should receive that reviewed digest; it refuses source drift and
writes only the digest-bound `.opencntx/adoption-v1.json` manifest. It does not
move, rename, delete or rewrite project files. A `BLOCKED` audit remains an
explicit review outcome and cannot be mistaken for a successful visual
takeover.

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

The index is a local projection. It does not replace canonical project files,
does not automatically reorganize a notes vault, does not select an AI model,
does not grant authority, and does not upload data. OpenSpec, Zvec, embeddings
and external search services are not runtime dependencies.

[Security](security.md) · [Contracts and compatibility](contracts-and-compatibility.md) · [Releases](releases.md)
