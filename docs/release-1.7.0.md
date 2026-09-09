# OPENCNTX 1.7.0 — Release scope and known limitations

[Overview](../README.md) · [Public roadmap](roadmap.md) · [Changelog](../CHANGELOG.md)

## What this release changes

Version 1.7.0 aligns package identity, installation examples, release links and
public documentation. Runtime behavior is retained from v1.6.3; this is not
the implementation of the newly proposed improvement roadmap. Existing data
formats remain unchanged. Publication is a GitHub operation, not an instruction
to install or activate software in any existing user environment.

The owner explicitly requested immediate publication rather than waiting for
the proposed implementation and two-week/25-task field pilot. This changes the
release scope; it does not turn unperformed work into completed work. The version
number and Stable distribution label do not certify those new acceptance criteria.

## Planned, not delivered in 1.7.0

The current [public roadmap](roadmap.md) now provides six phases and 24 tasks,
with a [full Dutch implementation plan](roadmap-plan.nl.md). This living link
does not change the contents or claims of the immutable 1.7.0 tag and artifacts.

- Fewer unnecessary approvals and stops through precise reusable authorization.
- Measured context/token budgets and reduced duplicate context or model calls.
- Simplified product policies without overriding provider or host boundaries.
- Owned, idempotent upgrade cleanup with interruption recovery and explicit
  handling of modified files, old hooks, rollback generations and user data.
- Improved sync snapshots/timeouts, capsule validation, compact handoff and
  optional one-way Markdown export.
- A representative field pilot and evidence of actual usability/cost gains.

## Known limitations retained from the reviewed runtime

Sync can copy changed bytes after preview and Git subprocesses can wait without
a timeout. A declared private destination is not provider-verified privacy.
Some otherwise authorized external or multi-target actions cannot be expressed
correctly by the governance classifier. Update planning does not fully reject
cross-component path overlap, and multiple directory replacements are not one
global atomic transaction. Capsule standalone verification can accept duplicate
manifest records and does not fully bound decompression before reading.
Critical JSON/path checks are not uniform across routes.

General live host enforcement is not demonstrated by the closed reference-host
fixtures. Installation must not be assumed to remove old manually installed
global hooks. Ledger rewrite growth and overall token savings lack the new
representative benchmark/pilot evidence. These are documented limitations,
not fixed issues in this release. Use the local core independently where
appropriate; avoid relying on unproven advanced guarantees.

## Verification and distribution

The publication procedure binds the final source commit/tree to wheel, sdist,
SHA256SUMS and BUILD-RECORD.json, checks CI for that exact commit, then verifies
downloaded release assets. CI/package checks are not substitutes for the
outstanding field pilot or proof that the limitations above were repaired.

Published availability and execution evidence belong to the matching
[GitHub Release](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.0).
The repository website source is maintained under `site/`; GitHub Pages is not
currently enabled. This release does not enable a new hosting service.
