> Historical test-build note. The regular [1.8.5 release](releases.md) supersedes this preview. Its former `v1.8.5-preview.1` tag is no longer available on GitHub, and no separate preview release is currently listed. Statements below describe its original publication, not current status.

# OPENCNTX 1.8.5 — experimental owner preview 1

This is an installable **test build**, published at the owner's explicit request. It is **not the completed 1.8.5 roadmap and not a qualified stable release**. The latest stable release remains 1.8.4. Main and existing installations are not changed by this publication.

## What is actually implemented

- A new opt-in command: `opencntx preview-search QUERY --compact`.
- Compact JSON removes formatting whitespace while retaining the same result fields, snippets, states and digests as the existing 1.8.4 retrieval result.
- `--delivery-report` uses the existing complete-output limits and coverage report.
- The default preview output is pretty JSON. Existing `knowledge index search` commands are unchanged.
- The underlying search engine, safety checks, durable formats and install manager are retained from 1.8.4. No project migration is added.

This preview does not implement the local unpublished hardening, no-op speed fixes, diacritic snippet fix, artifact-bound VISUAL_ARTIST changes, required-evidence planner, new host integration or all other roadmap work. Smaller serialized output is not a measured provider-token or billing saving. Token estimation still comes from the underlying engine and is not a provider tokenizer.

## Try it on a copy of a project

After downloading and checking the wheel against SHA256SUMS, create an isolated environment rather than replacing your working installation:

```powershell
py -3.12 -m venv .opencntx-preview-env
.\.opencntx-preview-env\Scripts\python.exe -m pip install --no-index --no-deps .\opencntx-1.8.5-py3-none-any.whl
.\.opencntx-preview-env\Scripts\opencntx.exe --version
.\.opencntx-preview-env\Scripts\opencntx.exe knowledge index build --root .\project-copy
.\.opencntx-preview-env\Scripts\opencntx.exe preview-search "your query" --root .\project-copy --compact --delivery-report
```

Keep the environment outside the indexed project root. The corresponding Linux executables are under `bin/`. A version result of `1.8.5` identifies this wheel's package metadata, not stable qualification. At its original publication, the GitHub tag was `v1.8.5-preview.1` and its release was marked prerelease and not latest. Retain exact wheel hashes to distinguish that test build from the later regular 1.8.5 artifact.

## Validation boundary

Publication requires the six targeted preview tests, selected existing regression suites, a wheel installation smoke test and the existing managed-install acceptance tool against the exact published 1.8.4 rollback wheel on the Ubuntu/Python 3.12 runner. BUILD-RECORD.json records the exact checks executed and their outcomes; GitHub Actions contains the logs.

This is not full-suite, coverage, Windows, ARM64, multi-provider, real-vault or end-to-end roadmap qualification. No live user environment has been upgraded. Package rollback and project-data restoration remain separate operations. The install manager is unchanged, but this release does not certify every user's installation owner or custom wrapper.

## Publication contents

Wheel, source distribution, SHA256SUMS and an explicitly preview-scoped BUILD-RECORD.json. This preview uses a standard setuptools build, not the stable release reproducibility gate. The source commit is recorded without claiming independently reproduced artifacts. No PyPI publication and no native hooks.
