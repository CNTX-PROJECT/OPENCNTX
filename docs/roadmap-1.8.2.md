# OPENCNTX 1.8.2 — English surface and compatibility roadmap

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

This roadmap records the bounded work for the 1.8.2 release. It is additive
to the 1.8.1 installation and integration work; it does not reopen the
resolved 1.8.0 knowledge-layer scope or silently close the real-project
`VISUAL_ARTIST` takeover gate.

## Objective

Make every OPENCNTX-owned GitHub surface consistently English while preserving
runtime and durable-format compatibility. The result must be reviewable from
the repository itself and enforceable in CI, not dependent on a one-time manual
search.

## Work packages

| ID | Work package | Acceptance evidence | Status |
|---|---|---|---|
| E01 | Inventory tracked public text, generated assets and runtime output | A bounded inventory identifies every changed surface and excludes only binary data | Complete |
| E02 | Translate active source, CLI, errors, footer and generated views | Reachable help, public output and legacy render paths contain English text | Complete |
| E03 | Preserve machine contracts during translation | AST identifiers, format IDs, paths, error codes and compatibility inputs remain intentional | Complete |
| E04 | Normalize retained R9 fixture prose and rebind frozen digests | Corpus runners pass with stable IDs, expected outcomes and verified current hashes | Complete |
| E05 | Enforce the public-language gate locally and in CI | `quality_gate.py language` fails closed on a blocked term and passes the tracked tree | Complete |
| E06 | Prove release and update behavior | Clean install, 1.8.0 update, rollback, reapply, build, smoke and GitHub read-back are green | In progress |

## Explicit non-goals

- No translation or rewrite of human-owned project files.
- No import of an old Obsidian backup into the product repository.
- No second `.opencntx` store in an Obsidian vault.
- No automatic owner, host, model, GitHub or Obsidian authorization.
- No removal of the 1.8.0, 1.8.1 or v1.7.6 recovery boundaries.
- No claim that English public text proves the `VISUAL_ARTIST` takeover gate.

## Release gate

The release is ready only when the exact source, package metadata, current
version surfaces, CI workflow, release assets, checksums and GitHub notes all
agree on 1.8.2. Any Dutch product wording, stale current-version claim,
changed machine identifier, digest mismatch, untested update path or public
release inconsistency keeps the gate closed.

## Evidence links

- [1.8.2 release scope](release-1.8.2.md)
- [1.8.1 integration roadmap](roadmap-1.8.1.md)
- [1.8.0 release roadmap](roadmap-1.8.0.md)
- [Current release status](releases.md)
- [Public artifact verification](release-artifacts.md)
