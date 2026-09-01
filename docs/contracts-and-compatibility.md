# Contracts and compatibility

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX publishes machine-readable contracts with the installed package. They
make the `1.0.0` Production/Stable boundary reviewable. Stable applies only to
the documented CLI, data-format, platform, and support boundaries; internal
Python implementation details are not a promised public library API.

## Maintenance after 1.0.0

- A `1.0.x` patch release may contain backward-compatible defect, security,
  and documentation corrections within the frozen 1.0 contract. It may not
  intentionally break that contract or automatically add a product feature.
- A future `1.x` minor release may add only backward-compatible behavior after
  a separate OWNER assignment. Existing Stable routes and supported durable
  format majors remain valid within that line.
- An intentional breaking change requires a separately approved proposal,
  migration and deprecation decision, and a new major line such as `2.0.0`.
- Support, deprecation, and end-of-life dates are published only through an
  explicit future decision. Version `1.0.0` does not promise unlimited support,
  a response-time SLA, certification, macOS, Python 3.15, or a public Python
  library API.
- Completing `1.0.0` does not automatically start `1.0.1`, maintenance work,
  or a new roadmap.

## Public surface catalog

The immutable `public-contract-v1.json` remains the v1.0.0 compatibility
baseline. Version 1.1.0 adds the `flow` family, three continuity schemas and a
runtime-maturity catalog without changing an accepted v1.0.0 route or durable
format. Existing v1.0.0 packages and workspaces remain readable.

Version 1.1.1 retains those additive contracts while correcting continuity
recovery, generated-detail language, and secret filtering. It also adds a
release-version drift gate without changing an accepted CLI or durable format.

Backward-compatible continuity maintenance may strengthen validation by using
digest fields already present in the v1 event ledger. Recovery counters describe
the active assignment, while historical failures remain in that ledger. This
does not introduce a new command, schema major or mandatory migration.

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

The Stable source supports Python 3.11, 3.12, 3.13, and 3.14 on Windows and
Ubuntu. Only a successful live run of all eight operating-system and Python
pairs on the exact commit proves that commit. The current GitHub ruleset is a
separate setting and is not changed by these source files.

[Documentation home](README.md)
