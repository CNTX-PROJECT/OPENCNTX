# Context packages

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

A context package is a small, reviewable snapshot for one task. It contains
selected text plus enough metadata to detect later changes.

## Package contents

The core package directory contains:

```text
.opencntx/latest/
├── CONTEXT.md
└── manifest.json
```

`CONTEXT.md` is designed for human review and optional use with an AI tool.
`manifest.json` is designed for deterministic verification.

## Selection is explicit

Files enter through configured `include` patterns. `exclude` patterns and
built-in sensitive exclusions are applied before content is read. Required
files must be present.

OPENCNTX does not guess which files are important. This keeps the choice
visible and reproducible.

## Budgets fail closed

`max_files` and `max_bytes` are hard limits. If the complete selected set does
not fit, `pack` stops. It does not silently truncate a source or publish a
partial package.

Reduce the scope by improving the task goal or file patterns. Do not increase
budgets automatically just to make an error disappear.

## Review before sharing

Check at least:

1. Is the goal correct and narrow?
2. Does every source help with that goal?
3. Is private or sensitive information absent?
4. Is the package small enough to understand?
5. Does verification still pass?

## What a digest proves

A SHA-256 digest identifies exact bytes with extremely high confidence. It can
show that bytes changed or that two recorded objects match.

It does not prove:

- truth;
- completeness;
- safety;
- ownership;
- human identity;
- approval;
- answer quality.

## Drift and rebuilds

If a source changes after packing, `opencntx verify` reports drift from the
exact default `.opencntx/latest` under the current directory. An explicit
`opencntx verify PATH` checks only that supplied path. Decide whether the
old snapshot is still the correct task input. If not, review the new source and
run `pack` again to create a new complete snapshot.

## Core packages and workspace context

Core packages follow `opencntx.toml` patterns directly. Workspace context
packages follow an approved task and its explicit relationships. They share
the same principle—small, deterministic, reviewable context—but use different
inputs and records.

## Related pages

- [Core commands](core.md)
- [Context navigation](context-navigation.md)
- [Security](security.md)
- [Troubleshooting](troubleshooting.md)

[Documentation home](README.md)
