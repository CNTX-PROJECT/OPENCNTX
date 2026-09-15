# OPENCNTX 1.8.1 — compatibility and integration roadmap

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

This is the roadmap for the published `1.8.1` release. The published
compatibility floor remains `v1.8.0`, with the
verified `v1.7.6` wheel retained as the normal offline rollback target.

## Why this release exists

The `v1.8.0` release was successful inside its bounded package scope, but its
own roadmap deliberately left existing-host adoption outside the release:

- the knowledge index and adoption manifest were delivered as derived,
  read-only projections;
- the visual contracts and layout planner did not mutate an existing tree;
- the provider-neutral footer rendered values supplied by a host, or explicit
  fallbacks when the host supplied none;
- package health did not prove that an existing project, host automation or
  presentation layer had been adopted successfully.

The `1.8.1` release therefore focuses on compatibility evidence and truthful
integration boundaries. It must not silently rewrite old project files, import
an old backup, or treat a green package probe as a green host installation.

## Compatibility matrix: v1.8.0 to v1.8.1

| Surface | v1.8.0 baseline | v1.8.1 release rule | Compatibility decision |
|---|---|---|---|
| Core pack, workspace and continuity | Existing `1.7.6` contracts retained and exercised | No format replacement; add only bounded checks and bug fixes | Compatible |
| Knowledge index | Deterministic derived index under `.opencntx/` | Keep node IDs, source digests, links and budgets stable; rebuild from source | Compatible |
| Existing-project adoption | Preview-first `BIND_READ_ONLY` manifest | Inventory must recognize `.opencntx/latest/manifest.json`; audit collisions, ordinals, links, cycles and link boundaries; any write route needs a digest-bound plan and receipt | Additive; adoption remains gated |
| Layout and visual system | Read-only audit and migration preview | Preserve numbering, names, anchors, parent/child links and archive boundaries before any apply | Additive; no blind move |
| Footer contract | Same fields and explicit fallbacks | Keep contract digest and profiles; use one separator convention; host values require exact session evidence | Compatible presentation fix |
| Managed installation | pipx/dedicated-venv routes, journaled rollback | Release update must retain the exact rollback, validate wheel records, serialize transitions and verify a fresh process | Compatible route, stronger acceptance |
| Publication status | `v1.8.0` is the compatibility baseline | `1.8.1` is published with an exact tag, assets and release evidence | Published |

## Additional hardening from the simulation round

The release now has three extra protections that are required for both a
fresh install and an upgrade over v1.8.0:

- managed transitions use an operating-system lock on the product-owned state
  root, so concurrent update/resume calls fail closed while a crashed process
  releases the lock automatically;
- staging validates wheel path safety and the complete `METADATA`, `WHEEL` and
  `RECORD` relationship before activation, not only the outer artifact digest;
- adoption previews return a deterministic audit and digest, and a write can
  proceed only when the reviewed digest still matches. The write remains inside
  `.opencntx` and never becomes permission to move human-owned files.

These protections strengthen package and workspace evidence; they do not close
the live VISUAL_ARTIST takeover gate.

## Required gates before claiming full operation

The release may report only the layers it has actually proven:

1. `PACKAGE_HEALTHY`: one managed owner, exact version, import/version/help,
   checkpoint, fresh-process resume and rollback evidence.
2. `WORKSPACE_HEALTHY`: the real existing root passes pack/verify, index build,
   bounded search, adoption inventory and manifest-location checks without
   changing user-owned source.
3. `HOST_INTEGRATION_HEALTHY`: the effective user, runtime, writer and host
   adapter are the same intended identity; a footer envelope is current,
   session-bound and either complete or explicitly unavailable.
4. `PRESENTATION_HEALTHY`: active notes, archive boundaries, numbering,
   navigation and links are coherent; historical material remains historical.

`FULLY_OPERATIONAL` is legal only when all four required layers are `PASS`.
A clean install cannot satisfy the existing-project, host or presentation
gates by itself.

## Footer host-envelope bridge

The release adds one additive, provider-neutral bridge for the footer values
that a host can measure. The host writes a bounded JSON object in the closed
`ocx-footer-host-envelope-v1` shape and binds `session_id` to
`source_session_id`. The envelope carries exact numeric telemetry, a source
SHA-256 and its own digest; `OK` requires complete chat/token/model telemetry,
while `UNAVAILABLE` carries null telemetry so the renderer cannot mix stale
and current values. The public CLI consumes it with:

```powershell
opencntx knowledge footer --from-host-envelope .\footer-envelope.json
```

Task fields may still be supplied on the command line. Metric flags are
intentionally rejected together with an envelope. The local Codex adapter can
emit the same shape with its private `footer_status.py --opencntx-envelope`
bridge. This supplies evidence for the host-integration gate; it does not
grant permission to rewrite a project or claim that visual adoption succeeded.

## VISUAL_ARTIST takeover gate

`VISUAL_ARTIST` is an integration capability, not a cosmetic homepage check.
For an existing project it must read the current tree, preserve human-owned
content, and produce a deterministic, reviewable route before any write is
allowed. The release must prove all of the following:

1. inventory existing numbering, names, case rules, parent/child links,
   anchors, IDs, source digests and navigation targets;
2. classify active material separately from `ARCHIVE`, `BACKUP`, `HISTORICAL`,
   orphaned, duplicated and ambiguous material;
3. detect broken links, duplicate ordinals, cycles and unresolved ownership
   without silently repairing or moving anything;
4. generate a digest-bound layout/adoption plan with an exact approved write
   set and an owner-review outcome for every ambiguity;
5. apply only that write set, keeping human text outside managed blocks and
   never creating a second `.opencntx` store in Obsidian;
6. run strict verification, emit a receipt, and repeat the operation with
   zero unplanned writes;
7. prove rollback from the exact pre-apply snapshot without deleting
   historical material.

The gate remains `OPEN` until a real v1.7.6-or-older project completes this
sequence. A clean install, a valid visual schema, a tidy-looking homepage or
an index build cannot close it. Stop immediately on ambiguous ownership,
changed source digests, an out-of-scope write target, a broken archive
boundary, or any change to human-owned text outside the approved write set.
This is the specific acceptance route for the earlier v1.8.0 failure in
structure, numbering, sorting, naming and visual perfection.

## Chapter-5 acceptance matrix

| Scenario | Mandatory evidence | Stop condition |
|---|---|---|
| Fresh install | Package, workspace, footer, visual contract and rollback checks | Any layer is inferred instead of measured |
| Upgrade over v1.7.6 or v1.8.0 | Read-only inventory, digest-bound adoption/layout plan, controlled apply, strict verify, second-run zero writes and rollback | Existing IDs, anchors or human text are changed outside the approved write-set |
| Legacy or untidy layout | Numbering, sorting, naming, archive/backup classification, orphan/duplicate/cycle and broken-link report | Ambiguity is silently resolved or history is moved into the active route |
| Resume after interruption | Same owner, runtime, source digests, writer lock and journal identity | A second writer or hidden state change is observed |

## Verification snapshot — 15 September 2026

The release was exercised against the exact wheel built from this
working tree (`opencntx-1.8.1-py3-none-any.whl`, SHA-256
`8510188403ad06a4564b469903f9ee732c37f9b281319957b97624ef54d9e7c9`,
572,701 bytes):

- the R12 installation simulator passed a disposable fresh install, an
  upgrade from v1.8.0, eight same-version re-apply cycles, a concurrent-lock
  probe, a post-activation failure with restoration to v1.8.0, and a blocked
  visual-adoption case with `DUPLICATE_ORDINAL` and `UNRESOLVED_LINK`;
- both fresh install and upgrade left human-owned source bytes unchanged,
  returned `READY` with zero adoption findings for the healthy fixture, and
  produced the final footer field;
- the R11 practical simulation passed 100 assignments, 200 process restarts,
  10 host claims, 120 layout-chaos scenarios, eight concurrent writers,
  five recovery rounds, scale gates through 4,509 projects, and zero network
  requests or writes to real project maps;
- the full regression suite passed with `845 passed`, `5 skipped` and `4,505`
  subtests. The quality ratchet remained green at 80.04% total branch
  coverage and 66.51% CLI coverage, with Ruff and mypy clean;
- the managed local PIPX route is now active on v1.8.1 with the exact wheel
  digest above, 217 installed-record entries, no pending journals and an
  exact active rollback wheel retained by the installer.

This proves the package and managed transition layers, not a completed
VISUAL_ARTIST takeover. The ambiguous adoption case is intentionally blocked;
the real existing-project presentation gate remains open until a reviewed,
digest-bound apply and rollback are proven on the intended project.

## Deliberate non-claims

The release does not claim that a public package can discover Codex internals,
select an owner, move an Obsidian vault, or execute remembered techniques. A
host-specific adapter may provide exact footer values through a versioned,
session-bound envelope, but missing or stale telemetry must remain visible as a
fallback. The release is complete only when its evidence says exactly
which layer is green and which integration boundary is still open.
