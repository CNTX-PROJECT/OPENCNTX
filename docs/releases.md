# Releases and current status

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

Use this page to distinguish published software, development source and future
plans. [GitHub Releases](https://github.com/CNTX-PROJECT/OPENCNTX/releases)
is authoritative for available downloads.

## Published software — v1.7.1 Stable

[Download v1.7.1](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.1) ·
[Release scope and limitations](release-1.7.1.md) ·
[Installation and removal](start-here.md)

Version 1.7.1 published the earlier roadmap and aligned documentation.
Runtime behavior is retained from 1.7.0 and 1.6.3. The proposed progress,
memory, friction and clean-update improvements are not implemented by that
documentation release.

The published distribution contains exactly:

- `opencntx-1.7.1-py3-none-any.whl`
- `opencntx-1.7.1.tar.gz`
- `SHA256SUMS`
- `BUILD-RECORD.json`

Read [Release artifacts](release-artifacts.md) for build records, checksums and
verification. There is no published PyPI/TestPyPI package.

## Development source and next plan

- Local candidate: v1.7.2.
- Source candidate: `v1.7.2`.
- Package version: `1.7.2`.
- Next implementation target: **1.7.3**, described on the [roadmap page](roadmap.md).

The source version and the planning target are different on purpose: publishing
a plan does not claim that its runtime changes exist. No software release
1.7.2 or 1.7.3 is created by this roadmap publication.

Contributors who deliberately need current, unreleased source can use:

```powershell
git clone --depth 1 https://github.com/CNTX-PROJECT/OPENCNTX.git
```

For ordinary use, follow the immutable release instructions in
[Get started](start-here.md).

## Compatibility and verification

| Item | Current boundary |
|---|---|
| Python | 3.11, 3.12, 3.13 and 3.14 |
| Tested systems | Windows and Ubuntu |
| CI | `CI_ACTIVE`; eight live Windows/Ubuntu and Python jobs |
| Runtime dependencies | None |
| Distribution | Exact Git tag plus four verified GitHub Release assets |
| License | [Apache-2.0](../LICENSE) |

See [Platforms and CI](platforms.md) and [Contracts and compatibility](contracts-and-compatibility.md).
Green CI proves the checks it runs; it does not prove every roadmap target or
real-host cost claim.

## History

- [Changelog](../CHANGELOG.md) — dated release history and unreleased documentation changes.
- [1.7.0 scope](release-1.7.0.md) — earlier runtime and publication limitations.
- [Product roadmap](roadmap.md) — latest plan and earlier English plan snapshot.

The following diagram records historical foundation milestones, not completion
of the current N01–N24 work.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/roadmap-dark.svg">
  <img src="../assets/docs/roadmap.svg" alt="Historical foundation milestones through version 1.0.0, not completion of the current roadmap">
</picture>

[Back to documentation](README.md)
