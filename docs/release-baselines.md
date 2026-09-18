# Release baselines

[Documentation](README.md) · [Release status](releases.md) · [History](history.md)

Publication listings and compatibility evidence are different resources. Removing an obsolete download must not remove the bytes used by a test.

## Original historical input

The original 0.3.0 wheel is retained as a test fixture with SHA-256 `6dee59d5255c73278400c05217abb298abb50a51f5998c7fb9d1c41e8e027cc6`. The R8 upgrade test reads these local bytes and still verifies the original hash. It no longer depends on a public pre-1.7.0 release URL.

## Rebuilt 1.7.6 input

The original 1.7.6 release download was absent before this cleanup. Its tag and source remain available. The original expected wheel hash is `b27d08f9851b9a8f1a30cb7fc71c3e94eedb579141cdce3609424b753071785f`.

A new test fixture was built from exact source `776f5dbf56c655ea52da61fae33123995e4d5d9d` with the repository's pinned build toolchain. Its SHA-256 is `b756083172adc0344f04a0579717d9806f77a31670d560140b07c85dffb4bfe2`. This is **SOURCE_REBUILT_NOT_ORIGINAL**: it is not a restored official artifact or a recommended rollback replacement for an existing installation.

The managed transition tests retain this source-version coverage with the new fixture's explicit identity. Current 1.8.4 upgrade tests use the unchanged original published wheel. Other retained 1.8.x baselines keep their published checksums.

## Manifest and safety

[Fixture manifest](../tests/fixtures/release-baselines/manifest.json) records the exact provenance and hashes. Fixtures are test inputs, not automatic user-installation targets. Historical writer tests retain their exact Git commit identities and the original data-format fixtures remain unchanged.
