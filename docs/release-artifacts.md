# Release artifacts

[Documentation](README.md) · [Current release](releases.md) · [Install or update](install-and-update.md)

> Current download: **v1.8.6**. Its full source and packaging matrix covers Windows and Ubuntu with Python 3.11–3.14; managed updates from v1.8.4 and v1.8.5 were checked on both systems with Python 3.12.

## Exact published files

The immutable [v1.8.6 release](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.6) contains:

- `opencntx-1.8.6-py3-none-any.whl`
- `opencntx-1.8.6.tar.gz`
- `SHA256SUMS`
- `BUILD-RECORD.json`

[publication.json](publication.json) records all four SHA-256 values, release ID, source commit and exact v1.8.5 rollback wheel. Compare the downloaded files with those values before installation. A checksum proves identity, not software correctness or publisher identity by itself.

The v1.8.6 release record is unsigned and does not establish publisher identity. Its wheel bytes reproduced in independent builds; source contents reproduced, but raw source-archive bytes did not. The earlier v1.8.5 artifact retains its original targeted Ubuntu/Python 3.12 qualification and distinct build record.

The prior preview wheel also identifies itself as 1.8.5. Use exact hashes, not only filenames or `--version`, to distinguish the regular release. See [installation and replacement](install-and-update.md).

## Distribution boundary

PyPI and TestPyPI remain outside the current distribution route. A materially changed publication destination requires a new exact OWNER decision; this repository cleanup does not authorize a package-index upload.

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
python tools/release_artifacts.py verify --directory dist --expected-version 1.8.6 --expected-commit $commit --expected-tree $tree
```

Linux:

```sh
python3 -m pip install --disable-pip-version-check build==1.3.0 setuptools==83.0.0
commit="$(git rev-parse HEAD)"
tree="$(git rev-parse 'HEAD^{tree}')"
python3 tools/release_artifacts.py build --repository . --output dist --expected-commit "$commit" --expected-tree "$tree"
python3 tools/release_artifacts.py verify --directory dist --expected-version 1.8.6 --expected-commit "$commit" --expected-tree "$tree"
```

These commands verify a local build against its exact source commit and tree. They do not upload files or replace an immutable GitHub Release; compare any release download with the exact hashes in `publication.json`.

## Installation smoke checks

```text
python tools/release_artifacts.py smoke --artifact dist/opencntx-1.8.6-py3-none-any.whl --expected-version 1.8.6
python tools/release_artifacts.py smoke --artifact dist/opencntx-1.8.6.tar.gz --expected-version 1.8.6
```

A smoke check is not full platform, recovery, live-vault or provider qualification. The source CI tests and original release checks have separate commit and artifact identities.

## Retention and history

Do not discard an exact active rollback wheel when replacing a package. The [baseline guide](release-baselines.md) distinguishes preserved original compatibility inputs from rebuilt test fixtures. [History](history.md) contains the before-cleanup archive and earlier records.
