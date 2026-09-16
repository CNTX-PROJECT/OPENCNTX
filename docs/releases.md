# Releases and current status

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

Use this page to distinguish published software, development source and future
plans. [GitHub Releases](https://github.com/CNTX-PROJECT/OPENCNTX/releases)
is authoritative for available downloads.

Release verification is live in the public workflow (`CI_ACTIVE`).

## Published software — v1.8.3 Stable

[Download v1.8.3](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.3) ·
[Release scope and limitations](release-1.8.3.md) ·
[Installation and managed update](install-and-update.md)

Version 1.8.3 adds a local SQLite FTS5 full-text projection for Markdown and
JSON, exact identifier and JSON-path recall, incremental refresh, explicit
scope/freshness status, bounded snippets and hard byte/token budgets. It also
broadens existing-project adoption discovery while requiring `AUDIT_THEN_BIND`
for contextless projects. It retains the English public surface and managed
installation, session-bound host-footer, wheel `RECORD`, serialized transition
and fail-closed compatibility contracts from 1.8.2 and 1.8.1.

The former 1.6.x downgrade/reset path is repaired. A valid retained v1 snapshot
inside a v2 goal-storage envelope is restored only in a new staged copy; the
source remains unchanged. The actual 1.6.0, 1.6.1, 1.6.2 and 1.6.3 writers
passed the staged-copy checkpoint matrix.

The published distribution contains exactly:

- `opencntx-1.8.3-py3-none-any.whl`
- `opencntx-1.8.3.tar.gz`
- `SHA256SUMS`
- `BUILD-RECORD.json`

Read [Release artifacts](release-artifacts.md) for build records, checksums and
verification. There is no published PyPI/TestPyPI package.

Remaining work outside this bounded release stays on the [roadmap page](roadmap.md)
and is never implied by a version number.

The release scope distinguishes implemented behavior from deferred extensions;
a roadmap checkbox is never a substitute for release evidence.

## Previous published software — v1.8.2 Stable

[Download v1.8.2](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.2) ·
[Release scope and limitations](release-1.8.2.md)

Version 1.8.2 made the public repository surface English and added the
fail-closed language gate retained by 1.8.3.

## Earlier published software — v1.8.1 Stable

[Download v1.8.1](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.1) ·
[Release scope and limitations](release-1.8.1.md)

Version 1.8.1 introduced managed installation, host-footer and adoption
hardening. It was the exact rollback source for a 1.8.2 update and remains the
compatibility bridge from the 1.8.0 knowledge-layer release.

## Earlier published software — v1.8.0 Stable

[Download v1.8.0](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.0) ·
[Release scope and limitations](release-1.8.0.md)

Version 1.8.0 introduced the local knowledge layer. Its read-only adoption and
provider-neutral footer contracts remain compatible with this release.

Contributors who deliberately need the current source can use:

```powershell
git clone --depth 1 https://github.com/CNTX-PROJECT/OPENCNTX.git
```

For ordinary use, follow the immutable release instructions in
[Get started](start-here.md).

## Compatibility and verification

The exact v1.8.3 source, four release assets and managed installation route are
published together. The [1.8.3 roadmap](roadmap-1.8.3.md) records the full-text
and compatibility evidence; the [1.8.2 roadmap](roadmap-1.8.2.md) records the
English surface; the [1.8.1 roadmap](roadmap-1.8.1.md)
records the integration boundaries retained by this release. The [1.8.0
release](release-1.8.0.md) remains the knowledge-layer compatibility reference,
with v1.7.6 retained for the normal offline recovery route.

| Item | Current boundary |
|---|---|
| Python | 3.11, 3.12, 3.13 and 3.14 |
| Tested systems | Windows and Ubuntu |
| CI | Windows and Ubuntu; Python 3.11–3.14 plus immutable historical writers |
| Runtime dependencies | None |
| Distribution | Exact Git tag plus four verified GitHub Release assets |
| License | [Apache-2.0](../LICENSE) |

See [Platforms and CI](platforms.md) and [Contracts and compatibility](contracts-and-compatibility.md).
Green CI proves the checks it runs; it does not prove every roadmap target or
real-host cost claim.

## History

- [Changelog](../CHANGELOG.md) — dated release history and unreleased documentation changes.
- [1.7.6 scope](release-1.7.6.md) — managed delivery and recovery baseline retained by 1.8.0.
- [1.7.0 scope](release-1.7.0.md) — earlier runtime and publication limitations.
- [1.7.3 scope](release-1.7.3.md) — reliability work retained by 1.7.4 and 1.7.5.
- [Product roadmap](roadmap.md) — latest plan and earlier English plan snapshot.

The following diagram records historical foundation milestones.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/roadmap-dark.svg">
  <img src="../assets/docs/roadmap.svg" alt="Historical foundation milestones through version 1.0.0, not completion of the current roadmap">
</picture>

[Back to documentation](README.md)
