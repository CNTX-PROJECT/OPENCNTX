<div align="center">

# OPENCNTX

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/opencntx-wordmark-dark.svg">
  <img src="assets/brand/opencntx-wordmark-light.svg" width="640" alt="OPENCNTX">
</picture>

**Give an AI the context it needs — small, reviewable, and backed by exact byte evidence.**

Local first · Any model · Zero runtime dependencies

[Get started](docs/start-here.md) · [Documentation](docs/README.md) · [Roadmap](docs/roadmap.md) · [Releases](docs/releases.md) · [Support](SUPPORT.md)

</div>

OPENCNTX turns selected local files into a compact context package. For longer
projects, optional workspace and continuity tools keep tasks and evidence
outside the chat. No account, API key or built-in AI model is required.

**Available now:** [v1.7.3 Stable release](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.3).
[Release scope](docs/release-1.7.3.md) · [Next roadmap](docs/roadmap.md)

## Start in minutes

With Python 3.11–3.14, Git and pipx available, install the published release:

```powershell
pipx install "git+https://github.com/CNTX-PROJECT/OPENCNTX.git@v1.7.3"
opencntx --version
```

Inside a small project:

```powershell
opencntx init
opencntx pack --preview
opencntx pack
opencntx verify
```

Choose files in `opencntx.toml`, preview the selection, then inspect
`.opencntx/latest/CONTEXT.md` before sharing it.
The [getting-started guide](docs/start-here.md) covers configuration,
Windows/Ubuntu installation, updates and removal.

## Choose your route

| You want to… | Start here |
|---|---|
| Understand what OPENCNTX does | [How it works](docs/how-it-works.md) |
| Create a small context package | [Get started](docs/start-here.md) |
| Organize a longer project | [Workspace](docs/workspace.md) |
| Resume a bounded task roadmap | [Workflow continuity](docs/continuity.md) |
| Find exact syntax or resolve an error | [Commands](docs/commands.md) · [Troubleshooting](docs/troubleshooting.md) |
| See what is planned next | [Product roadmap](docs/roadmap.md) |
| Check what has actually shipped | [Releases and current status](docs/releases.md) |

The product roadmap describes OPENCNTX development. Workflow continuity is the
separate feature for your own project tasks.

## Know the boundary

OPENCNTX does not run an AI or upload context for you. You control what is shared.
Verification proves matching bytes, not truth, completeness, safety or approval.
Installation does not activate host hooks.

Read [Security in plain language](docs/security.md) for exclusions and limits.
Report vulnerabilities privately through the [Security Policy](SECURITY.md),
not a public issue.

## Explore and contribute

[All guides](docs/README.md) · [Changelog](CHANGELOG.md) ·
[Contributing](CONTRIBUTING.md) · [Visual system](docs/visual-system.md) ·
[Apache-2.0 license](LICENSE)

Technical build details, source-candidate status and CI coverage live on the
[releases page](docs/releases.md), keeping this page focused on getting started.
