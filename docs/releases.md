# Releases and current status

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

Use this page to distinguish published software, development source and future
plans. [GitHub Releases](https://github.com/CNTX-PROJECT/OPENCNTX/releases)
is authoritative for available downloads.

## Published software — v1.7.4 Stable

[Download v1.7.4](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.4) ·
[Release scope and limitations](release-1.7.4.md) ·
[Installation and removal](start-here.md)

Version 1.7.4 adds deterministic project-aware routing: small related work is
attached as a step, related large work extends the current child roadmap, and a
distinct large outcome creates a new child roadmap under one master. Exact
return anchors survive side topics and rollover. A byte-budgeted context plan
references unchanged sources by digest, and safe authorized work continues
until evidence is complete or an explicit stop condition is reached.

The published distribution contains exactly:

- `opencntx-1.7.4-py3-none-any.whl`
- `opencntx-1.7.4.tar.gz`
- `SHA256SUMS`
- `BUILD-RECORD.json`

Read [Release artifacts](release-artifacts.md) for build records, checksums and
verification. There is no published PyPI/TestPyPI package.

## Local v1.7.5 release candidate

- Local candidate: v1.7.5.
- Source candidate: `v1.7.5`.
- Package version: `1.7.5`.
- Candidate scope: [engine and visual release plan](release-1.7.5.md).
- Publication, tag and release-assets are intentionally still a separate step.

Remaining work outside this bounded candidate stays on the [roadmap page](roadmap.md)
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
- [1.7.3 scope](release-1.7.3.md) — reliability work retained by 1.7.4.
- [Product roadmap](roadmap.md) — latest plan and earlier English plan snapshot.

The following diagram records historical foundation milestones.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/roadmap-dark.svg">
  <img src="../assets/docs/roadmap.svg" alt="Historical foundation milestones through version 1.0.0, not completion of the current roadmap">
</picture>

[Back to documentation](README.md)
