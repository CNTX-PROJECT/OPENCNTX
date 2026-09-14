# Releases and current status

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

Use this page to distinguish published software, development source and future
plans. [GitHub Releases](https://github.com/CNTX-PROJECT/OPENCNTX/releases)
is authoritative for available downloads.

Release verification is live in the public workflow (`CI_ACTIVE`).

## Published software — v1.8.0 Stable

[Download v1.8.0](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.0) ·
[Release scope and limitations](release-1.8.0.md) ·
[Installation and managed update](install-and-update.md)

Version 1.8.0 adds the local knowledge layer: hierarchical source nodes,
typed links, exact-first search with byte budgets, evidence-bound technique
cards, read-only project adoption and a provider-neutral footer. The managed
installer, semantic runtime health, offline rollback, continuity, task recipes,
visual guide and project-aware routing from 1.7.6 remain included.

The former 1.6.x downgrade/reset path is repaired. A valid retained v1 snapshot
inside a v2 goal-storage envelope is restored only in a new staged copy; the
source remains unchanged. The actual 1.6.0, 1.6.1, 1.6.2 and 1.6.3 writers
passed the staged-copy checkpoint matrix.

The published distribution contains exactly:

- `opencntx-1.8.0-py3-none-any.whl`
- `opencntx-1.8.0.tar.gz`
- `SHA256SUMS`
- `BUILD-RECORD.json`

Read [Release artifacts](release-artifacts.md) for build records, checksums and
verification. There is no published PyPI/TestPyPI package.

Remaining work outside this bounded release stays on the [roadmap page](roadmap.md)
and is never implied by a version number.

The release scope distinguishes implemented behavior from deferred extensions;
a roadmap checkbox is never a substitute for release evidence.

Contributors who deliberately need current, unreleased source can use:

```powershell
git clone --depth 1 https://github.com/CNTX-PROJECT/OPENCNTX.git
```

For ordinary use, follow the immutable release instructions in
[Get started](start-here.md).

## Compatibility and verification

The exact v1.8.0 source, four release assets and managed installation route are
published together. The [1.8.0 roadmap](roadmap-1.8.0.md) records the accepted
release evidence and explicit diagnosis-only boundaries; the [1.7.6 scope](release-1.7.6.md)
remains the rollback reference.

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
