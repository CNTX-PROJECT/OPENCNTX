# OPENCNTX 1.7.1 — Documentation release

[Overview](../README.md) · [Public roadmap](roadmap.md) · [Full Dutch plan](roadmap-plan.nl.md) · [Changelog](../CHANGELOG.md)

## What changed

This release packages the new public roadmap: six phases, 24 planned tasks,
dependencies and acceptance criteria. It includes the complete Dutch plan,
an English overview and aligned README, documentation and website references.
Private note references and local filesystem paths are not published.

The current release metadata, installation examples and artifact names target
1.7.1. Published availability is established by the matching
[GitHub Release](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.1).

## What did not change

Runtime behavior and data formats are retained from 1.7.0, which retained the
1.6.3 runtime. The new roadmap is **planned work, not implemented features**.
This release does not deliver the proposed approval/friction reductions,
token-saving measurements, clean-update algorithm or broad host integration.
All 24 new implementation tasks remain planned.

The [known runtime limitations documented for 1.7.0](release-1.7.0.md#known-limitations-retained-from-the-reviewed-runtime)
still apply. In particular, the reviewed sync, authority/target, update-path,
capsule and broader host/pilot limitations are not repaired by this release.
The original release tags and assets remain unchanged.

## Distribution and evidence

The four release assets are opencntx-1.7.1-py3-none-any.whl,
opencntx-1.7.1.tar.gz, SHA256SUMS and BUILD-RECORD.json.
The publication process binds them to the final source commit/tree and verifies
downloaded bytes. The unsigned build record is not proof of publisher identity.
CI and package checks are not a substitute for the outstanding product pilot.

There is no PyPI/TestPyPI publication or new hosting service. Publishing this
release does not install software or activate hooks in existing user environments.
