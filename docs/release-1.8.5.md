# OPENCNTX 1.8.5

A regular, permanent GitHub release, published at the owner's explicit request. This release is not a draft or prerelease and is designated Latest. It contains the complete installable OPENCNTX package, not only a roadmap or patch.

## Implemented changes

- Optional compact JSON search output through `opencntx preview-search QUERY --compact`.
- The existing `preview-search` command spelling is retained for compatibility with the preceding test build; it is available in this regular release.
- All search fields, snippets, states and digests are preserved when removing formatting whitespace.
- `--delivery-report` retains the existing full-output limits and coverage reporting.
- Existing `knowledge index search` behavior, the 1.8.4 engine, stored formats, safety checks and managed installer are unchanged.
- Package metadata and the download channel now identify the regular 1.8.5 release. There is no automatic project migration or native-hook activation.

## Scope and remaining work

This publication is **not completion of the entire proposed 1.8.5 roadmap**. Local unpublished hardening, further no-op performance work, diacritic snippet repair, required-evidence planning, artifact-bound VISUAL_ARTIST changes and native host integration are not implemented by this release. Their status remains open.

Publication and complete roadmap qualification are different decisions. The owner explicitly requested regular publication of the available implementation despite the limited qualification scope. No full-suite, coverage, Windows, ARM64, live-vault or multi-provider qualification is claimed. Smaller output bytes are not a measured provider-token or billing saving.

## Installation and upgrade

Download the wheel, `SHA256SUMS` and `BUILD-RECORD.json` from this release and verify the checksums. For an existing managed 1.8.4 installation, retain the exact published 1.8.4 wheel for offline rollback and use the existing managed installer rather than creating an overlapping installation.

Published 1.8.4 rollback wheel SHA-256:

```text
b3fe658c5071b17e1835be65cc10df3c025dd03677c1be45c9b8aeb977d011d9
```

The package version is `1.8.5`. The earlier preview also used that package version, so distinguish artifacts by SHA-256, not version alone. A preview installation requires explicit same-version artifact replacement through the existing managed route; do not assume an ordinary version-only upgrade replaces it.

Example after installation:

```text
opencntx --version
opencntx preview-search "your query" --root "PROJECT_PATH" --compact --delivery-report
```

Publishing this release does not install it on the owner's computer and does not rewrite project documents. Software rollback and restoring project data remain separate operations.

## Validation actually required for these artifacts

The publication job reruns the existing six compact-output tests, selected 1.8.4 regression/search/presentation/visual suites, an isolated wheel installation with the six compact-output tests, and managed 1.8.4 upgrade/rollback/reapply/resume acceptance. The build record contains the exact commands, outcomes, source commit, tree and artifact checksums.

These checks run on Ubuntu with Python 3.12. This is a standard setuptools build with limited product checks, not the comprehensive stable reproducibility and platform qualification gate. The original gate is not changed or represented as passed.

## Release contents and source

- `opencntx-1.8.5-py3-none-any.whl`
- `opencntx-1.8.5.tar.gz`
- `SHA256SUMS`
- `BUILD-RECORD.json`

The source is permanently identified by tag `v1.8.5` on the dedicated release branch. The older `v1.8.4` and `v1.8.5-preview.1` releases remain intact. This release does not claim that the default branch or every historical documentation page has been updated.
