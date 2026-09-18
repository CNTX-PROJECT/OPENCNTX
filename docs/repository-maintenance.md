# Repository maintenance

[Documentation](README.md) · [Current release](releases.md) · [History](history.md)

## Approved scope

Reconcile the 1.8.5 runtime with the default development line; update public navigation and current installation instructions; separate historical records; preserve compatibility inputs before retiring pre-1.7.0 download listings. The actual merge and validation outcome are recorded in the associated pull request and CI, not inferred from this document.

The original 1.8.5 source/runtime and packaging identity are retained. Published wheels, checksums and tags are not replaced. This maintenance does not implement outstanding product optimizations or modify user installations.

## Preservation

The [before-cleanup backup](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/archive-20260918) contains the complete Git bundle, 17 release records, 29 tag records and 60 downloaded assets. Archive SHA-256: `3a4e71dc4e4d9eee562aa128e52e5888cf25c85665d6d7ea744fdab10bdf2c6e`. Remote downloaded bytes were compared before any planned release deletion. The original 1.7.6 wheel was already missing and is not falsely claimed as recovered.

## Lasting controls

The publication record pins the regular release, source commit and exact artifact hashes. Twelve declared current-version surfaces are checked separately from history. Offline Markdown/HTML path and anchor checks cover the public documentation. The maintenance gate requires unchanged runtime, schema, package metadata, dependencies and license, and limits other changes to documentation and named verification paths. Full required CI remains protected by the repository ruleset.

Historical writer tests and stored-data fixtures remain intact. The old 0.3.0 wheel is retained locally with its original hash; the rebuilt 1.7.6 fixture has a distinct disclosed identity. Both are verified before use.

## Closing a publication

A publication is complete only after the intended source changes are merged through required checks, public instructions match the actual release, artifact identities are verified, remaining product work is described truthfully, and the publication's temporary branches and pull requests are resolved. Never check off unimplemented product work to make the page look complete.

## Transition-fixture compatibility

The retained historical simulator created a PROVEN card with no evidence, which older writers permitted and 1.8.4 correctly rejects. The 1.8.4+ fixture now creates a real temporary source, records its digest, saves the card and retires that source before the upgrade snapshot. The unchanged post-upgrade checks still require STALE recall and byte-identical stored card data. Older-writer empty-evidence cases remain tested. Runtime validation was not weakened.
