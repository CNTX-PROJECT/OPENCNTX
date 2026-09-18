# OPENCNTX 1.8.6

The regular [GitHub Release v1.8.6](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.8.6)
was published from immutable tag `v1.8.6`, source commit
`e3dc787e23402697e5659c92e070a204539e61f5`, tree
`2295087f4b89f0d125cd451485163b6d01e8375b`. Pull request #240 and the
[post-merge CI run](https://github.com/CNTX-PROJECT/OPENCNTX/actions/runs/35359277231)
completed successfully; all 60 jobs in the main run passed.

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

The full source, packaging and smoke-test matrix covers Windows and Ubuntu
with Python 3.11–3.14. Managed-install acceptance verifies direct updates,
rollback, reapply, resume and cleanup from the exact published 1.8.5 and 1.8.4
wheels on Windows and Ubuntu with Python 3.12. The final release wheel also
passed 11 managed transitions from each exact baseline on Windows/Python
3.12.10. The exact previous wheel remains the rollback input.

This release makes no provider-token savings or host-integration claims. The
scans remain local and bounded; an unreadable source is an error that requires
owner attention rather than a partial success.

## Artifacts

The regular release provides a wheel, source distribution, `SHA256SUMS` and
`BUILD-RECORD.json`. The [publication record](publication.json) pins all four
hashes, the release ID, tag commit and exact v1.8.5 rollback wheel. The wheel
SHA-256 is
`47c96b399373a6ac7f16f3af9bff92a2546a8749376c88cced2b0e8c86e61633`.

The build record is an unsigned local record, not a signed publisher identity.
The wheel bytes reproduced in independent builds. The source distribution's
contents reproduced, but byte-for-byte identity of its compressed archive is
not claimed.
