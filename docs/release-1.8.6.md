# OPENCNTX 1.8.6

This release hardens local scans and protects existing project data when an
index is written. The final tagged source commit and its GitHub Actions run are
the release qualification record; this page does not claim that a candidate is
published before a regular GitHub Release exists.

## Delivered scope

- Knowledge, adoption, search, managed-storage and lifecycle scans fail closed
  when a directory cannot be read, instead of reporting partial results as
  complete.
- Knowledge and search scans do not follow symbolic links or Windows reparse
  points into or out of the selected project scope.
- Configurable index outputs must not replace source files, hard-link aliases,
  another index output, unrelated project data or protected managed files.
- Existing OCX v1 index, search, adoption, installer and project formats remain
  unchanged. No project migration or native chat-host activation is introduced.

## Compatibility and boundaries

The managed-install acceptance matrix verifies direct updates and exact
rollback from the published 1.8.5 and 1.8.4 wheels on Windows and Ubuntu with
Python 3.12. Other supported Python versions run the source, packaging and
smoke-test matrix. The exact previous wheel remains the rollback input.

This release makes no provider-token savings or host-integration claims. The
scans remain local and bounded; an unreadable source is an error that requires
owner attention rather than a partial success.

## Artifacts

A regular release provides a wheel, source distribution, `SHA256SUMS` and
`BUILD-RECORD.json`. Once published, [publication identities](publication.json)
records their exact hashes, tag commit and rollback wheel.
