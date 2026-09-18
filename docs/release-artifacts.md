# Release artifacts

[Documentation](README.md) · [Current release](releases.md) · [Install or update](install-and-update.md)

> Current download: **v1.8.5**. The original artifact evidence is the limited set described below, not a full new Stable-platform certification.

## Exact published files

The immutable [v1.8.5 release](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.5) contains:

- `opencntx-1.8.5-py3-none-any.whl`
- `opencntx-1.8.5.tar.gz`
- `SHA256SUMS`
- `BUILD-RECORD.json`

[publication.json](publication.json) records all four SHA-256 values and the exact source commit. Compare the downloaded files with those values before installation. A checksum proves identity, not software correctness or publisher identity by itself.

The original 1.8.5 build used a standard setuptools build with targeted tests, installed-wheel checks and managed 1.8.4 transitions on Ubuntu/Python 3.12. Its build record is not the standard reproducible-builder record. Do not claim the standard verifier qualified these original artifacts or replace them when their record format differs.

The prior preview wheel also identifies itself as 1.8.5. Use exact hashes, not only filenames or `--version`, to distinguish the regular release. See [installation and replacement](install-and-update.md).

## New local candidate builds

The existing reproducible builder remains a development tool. It requires a clean checkout and an absent or empty output directory. It creates unpublished local candidates; it does not upload, overwrite an immutable release, or prove that every proposed feature is implemented.

Pinned toolchain:

```text
python -m pip install --disable-pip-version-check build==1.3.0 setuptools==83.0.0
```

PowerShell:

```powershell
$commit = git rev-parse HEAD
$tree = git rev-parse 'HEAD^{tree}'
python tools/release_artifacts.py build --repository . --output dist --expected-commit $commit --expected-tree $tree
python tools/release_artifacts.py verify --directory dist --expected-version 1.8.5 --expected-commit $commit --expected-tree $tree
```

Linux:

```sh
python3 -m pip install --disable-pip-version-check build==1.3.0 setuptools==83.0.0
commit="$(git rev-parse HEAD)"
tree="$(git rev-parse 'HEAD^{tree}')"
python3 tools/release_artifacts.py build --repository . --output dist --expected-commit "$commit" --expected-tree "$tree"
python3 tools/release_artifacts.py verify --directory dist --expected-version 1.8.5 --expected-commit "$commit" --expected-tree "$tree"
```

These verification commands apply to the standard builder's local records, not the differently scoped original 1.8.5 publication record.

## Installation smoke checks

```text
python tools/release_artifacts.py smoke --artifact dist/opencntx-1.8.5-py3-none-any.whl --expected-version 1.8.5
python tools/release_artifacts.py smoke --artifact dist/opencntx-1.8.5.tar.gz --expected-version 1.8.5
```

A smoke check is not full platform, recovery, live-vault or provider qualification. The source CI tests and original release checks have separate commit and artifact identities.

## Retention and history

Do not discard an exact active rollback wheel when replacing a package. The [baseline guide](release-baselines.md) distinguishes preserved original compatibility inputs from rebuilt test fixtures. [History](history.md) contains the before-cleanup archive and earlier records.
