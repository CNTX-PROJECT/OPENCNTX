<div align="center">

<picture><source media="(prefers-color-scheme: dark)" srcset="assets/brand/opencntx-wordmark-dark.svg"><img src="assets/brand/opencntx-wordmark-light.svg" width="640" alt="OPENCNTX"></picture>

**Keep your project knowledge. Give AI just what it needs.**

Local first · Provider-neutral · Explicit, verifiable context

**[Download v1.8.5](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.5)** · [Install or update](docs/install-and-update.md) · [Documentation](docs/README.md) · [Current work](docs/roadmap.md)

</div>

OPENCNTX creates small context packages from local project files. Keep source knowledge, review what a task needs, verify selected bytes and retain a clear place to resume.

## What is available

The published **1.8.5** package retains the core, workspace, continuity, search and managed-install routes. Its additional command, `preview-search --compact`, emits the existing search result as compact JSON. The command spelling comes from the earlier test build; the current download is a regular release.

The release does not implement the entire proposed optimization roadmap. Its original artifact evidence covers targeted product tests, installed-wheel checks and managed 1.8.4 update/rollback checks on Ubuntu with Python 3.12. [Release status and limitations](docs/releases.md) distinguishes that evidence from later source-CI results.

## Start with one task

Follow the [installation guide](docs/install-and-update.md). Inside a small project:

```text
opencntx init
opencntx pack --preview
opencntx pack
opencntx verify
```

Choose files in `opencntx.toml` and inspect `.opencntx/latest/CONTEXT.md` before sharing. [Core commands](docs/core.md) explains this route.

For optional indexed search:

```text
opencntx knowledge index build --root .
opencntx preview-search "your query" --root . --compact --delivery-report
```

The ordinary `knowledge index search` route remains available. Compact JSON preserves the result fields; smaller output is not a measured provider-token or billing guarantee.

## Read only what you need

| Goal | Guide |
|---|---|
| Install, update or recover | [Install and update](docs/install-and-update.md) |
| Understand context selection | [How it works](docs/how-it-works.md) |
| Use optional project features | [Documentation](docs/README.md) · [Commands](docs/commands.md) |
| See delivered behavior and remaining work | [Releases](docs/releases.md) · [Current work](docs/roadmap.md) |
| Investigate earlier versions | [History and maintenance](docs/history.md) |

## Boundaries

OPENCNTX does not contain or run an AI model. It does not automatically activate chat hooks, synchronize a notes app or send project files to a provider. Optional integrations need separate configuration and authorization. Verification proves matching bytes, not truth or task success.

The exact downloadable source is tagged `v1.8.5`. Maintenance on `main` may update documentation and verification tooling without changing the released runtime or replacing its immutable artifacts.

[Security](docs/security.md) · [Support](SUPPORT.md) · [Contributing](CONTRIBUTING.md) · [License](LICENSE)
