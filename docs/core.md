# Core commands: init, pack, and verify

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

The core flow creates one bounded context package from local UTF-8 text. It is
the shortest OPENCNTX path and does not require a workspace.

Confirm the installed package with `opencntx --version`. Fixed CLI text is
English and ASCII-safe; user content and paths remain UTF-8.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/core-flow-dark.svg">
  <img src="../assets/docs/core-flow.svg" alt="Initialize, preview and pack, inspect, verify, and only then decide whether to share">
</picture>

## 1. Create a configuration

Run inside your project directory:

```powershell
opencntx init
```

The command creates `opencntx.toml`. It fails instead of overwriting an
existing configuration.

```toml
[task]
goal = "Explain the one concrete task"

[context]
include = ["README.md", "src/**/*.py", "tests/**/*.py"]
required = ["README.md"]
exclude = [".git/**", ".opencntx/**", ".env*", "**/*.key", "**/*.pem"]
max_files = 25
max_bytes = 100000
```

### Important fields

| Field | Meaning |
|---|---|
| `goal` | One human-readable task |
| `include` | File patterns that may enter the package |
| `required` | Files that must be present |
| `exclude` | Extra patterns that must stay out |
| `max_files` | Hard file-count budget |
| `max_bytes` | Hard total-byte budget |

Built-in sensitive exclusions remain active even when your own list is short.

## 2. Preview the package

```powershell
opencntx pack --preview
```

Preview performs the same bounded selection, reading, budget, and local
secret-policy checks as `pack`. It lists included, required, excluded, and
ignored paths with reasons, plus file and byte budgets. It does not create or
change `.opencntx/`, source files, a manifest, or temporary publication state.

A preview returns `PACK_WOULD_SUCCEED` with exit code `0` when the same current
bytes may be packed. It returns `PACK_WOULD_BE_BLOCKED` with exit code `2` for a
high-confidence secret signal or another invalid input. Lower-confidence
signals are warnings and do not change a successful exit code.

Finding output contains only a deterministic ID, relative path, rule,
confidence, line, and column. It never contains the matched value or snippet.

## 3. Build the package

```powershell
opencntx pack
```

The command:

1. validates the configuration;
2. resolves candidate paths inside the project root;
3. applies exclusions before reading content;
4. rejects binary, unreadable, unsafe, or escaping paths;
5. enforces file and byte budgets;
6. scans selected UTF-8 text locally for bounded secret signals;
7. blocks unapproved high-confidence findings before publication;
8. writes a complete package atomically.

The default output is `.opencntx/latest/`.

### Exact override

If preview reports a high-confidence false positive, override only that exact
current finding:

```powershell
opencntx pack --allow-secret FINDING_ID_FROM_PREVIEW
```

The ID is bound to the rule, relative path, location, policy version, and full
source-file digest. Source drift invalidates it. Unknown, duplicate,
warning-only, or stale IDs fail. There is no global scan-disable option.

## 4. Inspect the output

Read both files:

- `CONTEXT.md` — the task goal and selected source text;
- `manifest.json` — package metadata, paths, sizes, and SHA-256 hashes.

New manifests include an optional `security` section with safe warning and
override metadata. Existing valid version-1 manifests without that section
remain supported. The manifest is evidence about bytes and decisions. It is
not a statement that the content is true, complete, secret-free, safe, or
approved.

## 5. Verify the package

```powershell
opencntx verify
```

Verification reports source state separately:

- `unchanged` — the source exists and its recorded bytes match;
- `changed` — the source exists but its bytes differ;
- `missing` — a recorded source no longer exists;
- `unexpected` — the package contains an unrecorded file or structure.

Verification is read-only. It does not repair sources or rebuild the package.
Without a path it checks exactly `.opencntx/latest` under the current
directory and never searches upward. `opencntx verify PATH` preserves explicit
path selection.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | The requested operation completed and its checks passed |
| `1` | The request was valid but verification found drift |
| `2` | Input, configuration, path, budget, secret policy, or package structure was invalid |

Treat every non-zero code as a stop until you understand the output.

## What the core does not do

- no automatic file ranking or summarization;
- no embeddings or vector search;
- no PDF, Office, image, audio, or video extraction;
- no AI, agent, network, or cloud operation;
- no automatic upload or answer verification.

## Related pages

- [Start here](start-here.md)
- [Context packages](context-packets.md)
- [Command reference](commands.md)
- [Security](security.md)

[Documentation home](README.md)
