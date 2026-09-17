# Releases and current status

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

Use this page to distinguish published software, development source and future
plans. [GitHub Releases](https://github.com/CNTX-PROJECT/OPENCNTX/releases)
is authoritative for available downloads.
The release scope distinguishes shipped behavior from remaining work; a
roadmap checkbox is never a substitute for release evidence.

Release verification is live in the public workflow (`CI_ACTIVE`).

## Published software — v1.8.4 Stable

[Download v1.8.4](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.4) ·
[Release scope and limitations](release-1.8.4.md) ·
[Installation and managed update](install-and-update.md)

Version 1.8.4 hardens bounded knowledge I/O, conditional updates, current
evidence, index publication, FTS integrity and retrieval. Shared snapshots
avoid unnecessary indexing work. It adds opt-in delivery reports, partial
footer metrics and reviewed, reversible visual text integration while retaining
existing v1 contracts. Automatic native chat-host integration is excluded;
native hook trust and live host qualification remain follow-up work.

The published distribution contains exactly:

- `opencntx-1.8.4-py3-none-any.whl`
- `opencntx-1.8.4.tar.gz`
- `SHA256SUMS`
- `BUILD-RECORD.json`

Read [Release artifacts](release-artifacts.md) for build records, checksums and
verification. There is no published PyPI/TestPyPI package. The
[qualification roadmap](roadmap-1.8.4.md) records evidence and scope boundaries.

## Previous published software — v1.8.3 Stable

[Download v1.8.3](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.3) ·
[Release scope and limitations](release-1.8.3.md)

Version 1.8.3 introduced the local SQLite FTS5 full-text projection and
broader adoption discovery, retaining managed installation and earlier
compatibility contracts. Its staged-copy legacy recovery evidence remains
part of the historical compatibility record.

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

The exact v1.8.4 source, four release assets and managed installation route are
published together. The [1.8.4 roadmap](roadmap-1.8.4.md) records audit,
upgrade and presentation qualification. The [1.8.3 roadmap](roadmap-1.8.3.md) records the full-text
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
