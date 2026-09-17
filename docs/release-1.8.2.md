# OPENCNTX 1.8.2

> Historical version record, not the active backlog. [Current release](releases.md) · [Current work](roadmap.md) · [History](history.md).

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX 1.8.2 is the English public-surface and compatibility-hardening
release. It keeps the 1.8.1 installation, adoption, footer and rollback
contracts while removing accidental Dutch product text from the source,
documentation, examples, tests and published guidance.

## Delivered

- Make active CLI errors, help text, generated views, footer labels, legacy
  render paths and public documentation English.
- Keep machine identifiers, file paths, schema names, format IDs, error codes,
  language codes and compatibility boundaries unchanged unless a change is
  explicitly required by the existing contract.
- Accept the historical `nl` presentation profile as an input compatibility
  value while rendering the same English public labels as every other supported
  profile.
- Add a fail-closed public-language gate that scans every tracked text file and
  reports the exact path, line and blocked term.
- Run the public-language gate from the quality command and the required CI
  quality sequence.
- Normalize retained R9 fixture prose to English while preserving scenario IDs,
  input meaning, expected outcomes, table bindings and digest verification.
- Rebind the affected frozen fixture digests and manifests so compatibility
  tests continue to prove the bytes that are actually shipped.

## Compatibility and safety

The release does not replace the v1 durable formats, the `.opencntx` store, the
managed installation journal, the adoption write boundary, the footer envelope,
or the v1.7.6 offline rollback route. Existing project source files are not
rewritten merely because the package is updated.

The language change applies to OPENCNTX-owned public output. It does not
translate or mutate a user's source files, task text, knowledge notes or
external Obsidian vault. Historical compatibility inputs remain read-only test
fixtures; they are not current product templates.

The release still does not claim that a clean install proves a real-project
visual takeover, host integration, Obsidian synchronization or owner
authorization. Those boundaries remain governed by the 1.8.1 integration
roadmap and the existing adoption gates.

## Verification requirements

Before publication, the exact clean release commit must pass:

1. the full Python test matrix and required historical compatibility tests;
2. compile, lint, type, schema, diagram, public-language and release-version
   gates;
3. fresh-install, update-from-1.8.0, rollback, reapply, lock and cleanup
   simulations;
4. two independent reproducible distribution builds, artifact verification,
   installation smoke tests and uninstall checks;
5. a GitHub read-back confirming that the tag, source commit, four assets and
   release notes are English and mutually consistent.

## Distribution

The published release contains exactly:

- `opencntx-1.8.2-py3-none-any.whl`;
- `opencntx-1.8.2.tar.gz`;
- `SHA256SUMS`;
- `BUILD-RECORD.json`.

There is no PyPI or TestPyPI publication. Use [Install and update](install-and-update.md)
for checksum verification and for the controlled update route from 1.8.0 or
1.8.1.

See the [1.8.2 roadmap](roadmap-1.8.2.md), [release artifact contract](release-artifacts.md),
[contracts and compatibility](contracts-and-compatibility.md) and
[security guide](security.md) for the surrounding boundaries.
