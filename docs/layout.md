# Bounded workspace order

[Overview](../README.md) · [Commands](commands.md) · [Workspace](workspace.md) · [All guides](README.md)

OPENCNTX can audit a provider-neutral JSON order contract before any real file
move. The audit is local and read-only. It never creates, moves, renames, or
removes a path.

## Contract boundary

`opencntx-order-contract` version 1 records:

- a canonical root registry and a role for every root;
- exact required folder roles and their owners;
- regular-expression naming rules with explicit exemptions;
- path allowlist rules that assign every accepted path to one owner;
- content-duplicate detection with an explicit digest exception list;
- scan limits and the objective `ZERO_FINDINGS` stop rule.

Relative registered roots are resolved from `--base`. Absolute paths stay local
to the current host. The format does not name a cloud, Git provider, operating
system product, application, game, or hardware model.

The installed `order-contract-v1.schema.json` describes the closed JSON shape.
Runtime validation also rejects unknown fields, duplicate JSON keys, unknown
root references, unsafe relative role paths, duplicate identifiers, unsupported
versions, invalid patterns, and unbounded limits.

## Read-only routes

Audit and keep the findings as planning input:

```text
opencntx layout audit --contract order-contract.json --base . --json
```

Require the contract to be exactly green:

```text
opencntx layout verify --contract order-contract.json --base . --json
```

`audit` exits successfully when the contract can be inspected, even when it
reports disorder. `verify` exits with code 1 unless the result is `GREEN` with
zero findings. Invalid input exits with code 2. A reached scan bound returns
`STOPPED`, never partial success.

## BOUNDED PERFECTION

Perfection is objective here: the versioned policy has zero findings inside its
declared roots and scan boundary. When that predicate is green, work stops. New
subjective cleanup cycles are outside the contract and require a changed
revision. This keeps naming and structure strict without creating an endless
polishing loop.
