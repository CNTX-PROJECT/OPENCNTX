<div align="center">

# OPENCNTX

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/brand/opencntx-wordmark-dark.svg">
  <img src="assets/brand/opencntx-wordmark-light.svg" width="640" alt="OPENCNTX — OPEN in purple, CNTX in black or white">
</picture>

**Small context. Clear evidence. Any model.**

[Start here](docs/start-here.md) · [How it works](docs/how-it-works.md) · [Advanced / Alpha workspace](docs/workspace.md) · [Commands](docs/commands.md) · [Security](docs/security.md) · [All docs](docs/README.md)

</div>

OPENCNTX is a small local command-line tool. It turns only the files you choose
into a reviewable context package for one AI task. Paths, sizes, and SHA-256
hashes show what was included and whether those bytes changed later.

It works without an account, API key, cloud service, or built-in AI model. You
may use the reviewed text files with any AI tool that accepts text or files.
OPENCNTX never sends them for you.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/docs/opencntx-overview-dark.svg">
  <img src="assets/docs/opencntx-overview.svg" alt="Select local files, review and verify a small context package, then decide whether to share it">
</picture>

## Start in four steps

OPENCNTX requires Python 3.11 through 3.14. The package line is `v1.0.0` and is
Production/Stable. It is public only when both the live `v1.0.0` tag and the
`OPENCNTX v1.0.0` GitHub Release are present.

### 1. Install the Stable release after publication

With `pipx` and Git already installed, one pinned command creates an isolated
tool environment:

```powershell
pipx install "git+https://github.com/CNTX-PROJECT/OPENCNTX.git@v1.0.0"
opencntx --version
opencntx --help
```

The source-checkout route remains available:

```powershell
git clone --branch v1.0.0 --depth 1 https://github.com/CNTX-PROJECT/OPENCNTX.git
cd OPENCNTX
python -m pip install .
opencntx --version
opencntx --help
```

For contributor work on the current source:

```powershell
git clone --depth 1 https://github.com/CNTX-PROJECT/OPENCNTX.git
cd OPENCNTX
python -m pip install .
```

### 2. Create a configuration

Run this inside the project that contains the files you want to use:

```powershell
opencntx init
```

Open `opencntx.toml`. Set one clear goal and review the allowed file patterns
before continuing.

### 3. Preview, build, and inspect the package

```powershell
opencntx pack --preview
opencntx pack
```

Preview shows selected, required, excluded, and ignored paths, budgets, and
safe secret-signal metadata without writing a package. Then read
`.opencntx/latest/CONTEXT.md` yourself. Remove anything that does not belong in
the task.

### 4. Verify the exact bytes

```powershell
opencntx verify
```

A successful check proves that the recorded files still match. It does not
prove that the content is true, complete, safe, or approved.

The complete beginner route—including Windows, Ubuntu, removal, and common
errors—is on [Start here](docs/start-here.md). An explicit package path remains
available as `opencntx verify PATH`. Build and checksum details for contributors
are on [Release artifacts](docs/release-artifacts.md).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/docs/core-flow-dark.svg">
  <img src="assets/docs/core-flow.svg" alt="Initialize, preview and pack, inspect, verify, and only then decide whether to share">
</picture>

## Advanced / Alpha workspace

The core route above is complete; workspace concepts are not required for a
first context package. Longer projects can optionally use the existing Alpha
workspace for supplied sources, chapters, tasks, playbooks, roles, derived
text, and bounded executor packages. It remains advanced and may change within
the public Alpha contract.

Workspace writers are local single-writer transactions. `workspace doctor`
diagnoses interrupted work read-only; `workspace recover` previews an exact,
backup-first rollback and applies it only with the reported transaction ID and
intent digest.

`workspace lifecycle status` audits observed local permissions, privacy labels,
storage, and format compatibility without exposing source paths or content.
Migration and cleanup remain explicit digest-bound operations with external
checkpoints. Read [Privacy, storage, and format lifecycle](docs/privacy-storage-lifecycle.md).

Read [Advanced / Alpha workspace](docs/workspace.md) only when that extra
structure is useful. No workspace command starts an AI, agent, shell process,
OCR tool, transcription service, or external sync.

## Safety in one minute

- OPENCNTX reads only selected local UTF-8 text inside the project boundary.
- Known credential paths are excluded before reading. A small local scanner
  blocks narrow high-confidence signals and warns on broader signals, but it
  cannot prove that output is secret-free. Inspect every output file.
- Privacy labels classify content. They do not encrypt it or control access.
- Permission checks report observed local access; they do not create identities
  or replace operating-system and backup protection.
- A non-zero exit code means the requested operation was not fully proven.
- A hash proves byte identity, not truth, safety, completeness, or approval.
- Sharing is always your separate decision.

Read [Security in plain language](docs/security.md) first. The root
[Security Policy](SECURITY.md) is the canonical technical boundary. Report a
possible vulnerability privately through GitHub's **Report a vulnerability**
route, never in a public issue.

## Project status

| Item | Current public state |
|---|---|
| Release line | `v1.0.0` Production/Stable; public only after the live tag and GitHub Release exist |
| Package version | `1.0.0` |
| Python | 3.11, 3.12, 3.13, and 3.14 |
| Tested systems | Windows and Ubuntu |
| CI | `CI_ACTIVE`, eight Windows/Ubuntu and Python matrix jobs |
| Runtime dependencies | none |
| License | [Apache-2.0](LICENSE) |

The `v1.0.0` GitHub Release is complete only when it is live with exactly
`opencntx-1.0.0-py3-none-any.whl`, `opencntx-1.0.0.tar.gz`, `SHA256SUMS`,
and `BUILD-RECORD.json`. Until the live tag and Release both exist, all v1.0.0
builds are unpublished candidates. OPENCNTX is not published on PyPI or
TestPyPI. See [Release artifacts](docs/release-artifacts.md) for the exact
boundary.

Only a successful live CI run on the exact commit proves those eight jobs. The
live `main` ruleset remains a separate repository setting. See
the [changelog](CHANGELOG.md), [support routes](SUPPORT.md), and
[contribution guide](CONTRIBUTING.md) for project-specific details.
