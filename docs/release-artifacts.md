# Release artifacts

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

This page defines the four files for the `v1.7.5` GitHub Release and
explains how contributors reproduce the exact local build. It does not grant
authority to publish a new release or package-index upload.

## Current public distribution

The Stable release target is `v1.7.5`; published availability is established only by its
[GitHub Release](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.5).
After publication, install it from
the exact public Git tag as described in [Get started](start-here.md):
`pipx install "git+https://github.com/CNTX-PROJECT/OPENCNTX.git@v1.7.5"`.

- OPENCNTX is not published on PyPI or TestPyPI.
- The historical `v0.2.0` GitHub Release has no wheel, sdist, checksum, or
  build record attached to it.
- The v1.7.5 GitHub Release must contain exactly the four files named below.

Its published artifacts are `opencntx-1.7.5-py3-none-any.whl`,
`opencntx-1.7.5.tar.gz`, `SHA256SUMS`, and `BUILD-RECORD.json`.

Any file built locally is a verification build until it is one of the
four exact assets attached to the immutable GitHub Release.

## Reproducible local v1.7.5 output

The local release helper emits exactly four v1.7.5 files:

1. `opencntx-1.7.5-py3-none-any.whl`;
2. `opencntx-1.7.5.tar.gz`;
3. `SHA256SUMS` for those two artifacts;
4. `BUILD-RECORD.json`.

The build record binds the source commit, source tree, source timestamp,
Python version, pinned build frontend and backend, artifact names, sizes, and hashes. It is
an unsigned technical record. It is not a cryptographic attestation and does
not prove publisher identity, safety, approval, or publication origin.

## Build twice from a clean commit

Contributor builds require a clean checkout and the pinned build frontend.
The output directory must be absent or empty.

PowerShell:

```powershell
python -m pip install --disable-pip-version-check build==1.3.0 setuptools==83.0.0
$commit = git rev-parse HEAD
$tree = git rev-parse 'HEAD^{tree}'
python tools/release_artifacts.py build --repository . --output dist --expected-commit $commit --expected-tree $tree
python tools/release_artifacts.py verify --directory dist --expected-version 1.7.5 --expected-commit $commit --expected-tree $tree
```

Ubuntu:

```bash
python3 -m pip install --disable-pip-version-check build==1.3.0 setuptools==83.0.0
commit=$(git rev-parse HEAD)
tree=$(git rev-parse 'HEAD^{tree}')
python3 tools/release_artifacts.py build --repository . --output dist --expected-commit "$commit" --expected-tree "$tree"
python3 tools/release_artifacts.py verify --directory dist --expected-version 1.7.5 --expected-commit "$commit" --expected-tree "$tree"
```

The helper exports the exact Git tree to two independent temporary source
directories and runs the normal PEP 517 build in each. It refuses a dirty
worktree, a mismatched commit or tree, unsafe archive members, ambiguous
metadata, missing files, unexpected output, or a checksum mismatch.

Nothing in this command uploads an artifact or contacts a package index. The
build frontend may install its declared build requirements through normal
Python packaging behavior if they are not already present.

## Reproducibility claims

The verification separates three facts:

- the two wheels must be byte-identical;
- the two sdists must contain identical paths and file bytes;
- raw sdist byte identity is reported separately.

Tar and gzip metadata can make two logically equal sdists differ as raw
compressed bytes. OPENCNTX does not call all artifacts byte-reproducible unless
both files actually meet that stronger test.

## Installation and removal smoke

Each of the eight Windows/Ubuntu and Python 3.11/3.12/3.13/3.14 CI jobs builds twice,
then tests both the wheel and sdist from an isolated environment. Each artifact
must support:

- installation without runtime dependencies;
- `opencntx --version` and `opencntx --help`;
- `init`, `pack --preview`, `pack`, and `verify` outside the checkout;
- uninstall with no remaining distribution metadata or console entrypoint.

Run the same bounded smoke for both local artifacts:

```powershell
python tools/release_artifacts.py smoke --artifact dist\opencntx-1.7.5-py3-none-any.whl --expected-version 1.7.5
python tools/release_artifacts.py smoke --artifact dist\opencntx-1.7.5.tar.gz --expected-version 1.7.5
```

This tests a local verification build. It is not proof that an external package-index
installation works.

## Separate publication gate

A public release needs a separate exact decision and fresh evidence. Before
publication, the release owner must:

1. bind package version, exact tag, commit, tree, and artifact version;
2. build from the exact clean commit and tree;
3. verify checksums, the build record, both installation routes, uninstall,
   and all eight CI jobs;
4. check the package-index namespace again at that time;
5. approve the exact GitHub Release mutation separately;
6. verify the bytes downloaded from the real publication channel.

A PyPI 404 at one moment is not ownership or reservation evidence. This
repository contains no PyPI token, trusted-publishing configuration, OIDC
permission, or publication command. PyPI and TestPyPI remain outside the
current distribution route. Adding either one requires a materially changed
situation and a new exact OWNER decision; a local build or green test cannot
grant that authority.

Every post-release change requires a newer package version before GitHub review,
including documentation, metadata, tests, gate code, deletions and release
material. A stable tag is immutable; a newer version permits review but still
does not grant a release decision.

## Related pages

- [Start here](start-here.md)
- [Platforms and CI](platforms.md)
- [Troubleshooting](troubleshooting.md)
- [Security](security.md)
- [Contribution guide](../CONTRIBUTING.md)

[Documentation home](README.md)
