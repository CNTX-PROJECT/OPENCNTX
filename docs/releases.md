# Releases and current status

[Project home](../README.md) · [Documentation](README.md) · [Install or update](install-and-update.md) · [Current work](roadmap.md)

## Published package: v1.8.5

[Download v1.8.5](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.5) · [Release scope](release-1.8.5.md).

This is a regular, immutable GitHub release, not a prerelease. Publication status does not mean that every proposed optimization or platform test is complete.

### Implemented change

`opencntx preview-search QUERY --compact` emits the existing retrieval result without pretty-print whitespace. Result fields, snippets, states and digests are retained. `--delivery-report` uses the existing bounded delivery route. The ordinary `knowledge index search` command and underlying 1.8.4 engine, stored formats and managed installer are unchanged.

The `preview-search` spelling is retained for compatibility with the preceding test build.

### Exact artifact identity

| Item | Value |
|---|---|
| Tag | `v1.8.5` |
| Source commit | `734ad894e20a34013f155ba8e7d3172cedd24c2e` |
| Wheel | `opencntx-1.8.5-py3-none-any.whl` |
| Wheel SHA-256 | `83f653461d8718a73451bce8769177b166b06f045eb49cd59fc9edebb16cb5ce` |
| Source archive | `opencntx-1.8.5.tar.gz` |
| Verification records | `SHA256SUMS`, `BUILD-RECORD.json` |

The machine-readable [publication record](publication.json) pins these identities. A previous test wheel also reports 1.8.5, so a version string alone cannot distinguish it from this artifact.

### Evidence and remaining work

The original publication ran 45 targeted source tests, six compact-output tests against the installed wheel, and 11 managed installation transitions against the exact published 1.8.4 wheel on Ubuntu/Python 3.12. Its build record records the actual commands. The original release was not fully qualified across Windows, ARM64, live vaults or providers.

The live source workflow is `CI_ACTIVE`. Later full source-CI checks are attached to their own commits and do not retroactively rewrite the original artifact's build record or prove real-host operation.

Further no-op optimization, diacritic-aware passage repair, required-evidence planning and artifact-bound VISUAL_ARTIST work are not implemented by the compact-output release. Automatic native chat hooks remain outside its scope. Smaller JSON is not a measured billing or provider-token saving.

## Previous release and rollback source: 1.8.4

[Download 1.8.4](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.4) · [Historical release scope](release-1.8.4.md).

Retain the exact previous wheel before activating an update:

```text
b3fe658c5071b17e1835be65cc10df3c025dd03677c1be45c9b8aeb977d011d9
```

Use the [managed update route](install-and-update.md). Package rollback and restoring project documents are separate operations.

## Development source and earlier versions

Contributors can obtain the current maintenance source with:

```text
git clone --depth 1 https://github.com/CNTX-PROJECT/OPENCNTX.git
```

Use the release tag and wheel for exact release reproduction. [History](history.md) separates previous records from current instructions; [baseline maintenance](release-baselines.md) describes retained compatibility test inputs.
