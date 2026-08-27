# Contracts and compatibility

[Start here](start-here.md) · [How it works](how-it-works.md) · [Advanced / Alpha workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All docs](README.md)

OPENCNTX publishes machine-readable contracts with the installed package. They
make the current prerelease/RC boundary reviewable without turning it into a Stable
compatibility promise.

## Public surface catalog

`public-contract-v1.json` lists all 1,575 accepted public surfaces. The catalog
covers CLI routes and arguments, configuration fields, durable formats, error
and exit codes, machine output, public documentation claims, Python symbols,
schema or validator surfaces, and support claims.

The catalog is evidence, not executable input. Runtime code does not load it to
decide what a command may do.

## Durable format catalog

`durable-format-contracts-v1.json` defines all 36 durable formats. Every format
has:

- one exact format name and current major version;
- a deterministic `urn:uuid:` schema identifier;
- required and optional top-level fields with accepted JSON types;
- explicit constant relationships between the format and version fields;
- one immutable v0.3.0 compatibility fixture.

The shared compatibility matrix maps each format and supported major to that
same schema identifier. Package builds include all six JSON contract and schema
assets.

## Fail-closed major versions

Readers accept only a format and major pair listed in the compatibility matrix.
An unknown format or unknown major returns a bounded validation error. The
reader does not rewrite, migrate, delete, or partially accept the input.

This is intentional: a future major may change fields or meaning. Supporting it
requires a reviewed contract and a separate migration decision.

## v0.3.0 fixtures

The repository contains one synthetic, producer-shaped fixture for every
durable format under `tests/fixtures/v0.3.0/durable-records`. The gzip container
keeps the fixture bytes unchanged across Git checkouts on every tested system. Their manifest
binds each relative path, format, schema identifier, size, and SHA-256 digest.
Tests require all 36 files to stay byte-identical and read-only during
validation. Two composed examples bind the core-package and workspace members
needed to test relationships between records.

These fixtures contain no user workspace content. They prove the published
shape and version rules; they do not prove that historical user data is true,
complete, safe, or automatically migratable.

## Platform boundary

The candidate source supports Python 3.11, 3.12, 3.13, and 3.14 on Windows and
Ubuntu. Only a successful live run of all eight operating-system and Python
pairs on the exact commit counts as candidate proof. The current GitHub ruleset
is a separate setting and is not changed by these source files.

[Documentation home](README.md)
