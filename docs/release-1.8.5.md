# OPENCNTX 1.8.5

[Download](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.5) · [Current status](releases.md) · [Install or update](install-and-update.md)

## Delivered

Optional compact JSON output through `opencntx preview-search QUERY --compact`. The command retains its earlier spelling for compatibility. Compact serialization preserves the existing search result fields, snippets, states and digests; the ordinary `knowledge index search` route is unchanged. `--delivery-report` retains the existing output limits and coverage report.

The underlying 1.8.4 engine, managed installer and durable formats are retained. No project migration or automatic native-hook activation is introduced.

## Artifact and validation scope

The regular immutable release is tagged `v1.8.5` at commit `734ad894e20a34013f155ba8e7d3172cedd24c2e`. It provides a wheel, source distribution, SHA256SUMS and BUILD-RECORD.json. [Publication identities](publication.json) pins their hashes.

The original build ran 45 targeted source tests, six installed-wheel checks and 11 managed transitions against the original 1.8.4 wheel on Ubuntu/Python 3.12. Full cross-platform qualification, live-vault operation and provider-token savings were not established by that build. Later maintenance CI describes its own source commit, not a replacement of the released artifacts.

## Not delivered by this release

Further no-op optimization, diacritic-aware passage selection, mandatory-evidence planning and artifact-bound VISUAL_ARTIST improvements remain future development. Publishing 1.8.5 did not implement the whole earlier proposal. See [current work](roadmap.md).

## Upgrade

Use the [managed update instructions](install-and-update.md), retain the exact active rollback wheel, and check the regular artifact's SHA-256. The earlier preview used the same package version with different bytes, so version-only upgrades do not identify the desired replacement. Publishing a release does not install it on a user's computer.
