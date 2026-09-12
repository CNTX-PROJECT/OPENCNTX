# OPENCNTX 1.7.6

OPENCNTX 1.7.6 makes installation recovery and connected task continuation
testable product behavior instead of host assumptions.

## Delivered

- An independent `opencntx-install` entry point for read-only status, fresh
  install, update, interrupted-operation resume and targeted repair.
- Hash- and version-bound candidate staging, semantic runtime health, offline
  rollback, product-owned cleanup and ten-journal retention.
- Mandatory historical writer checks from 1.1.0 through 1.7.5 on Windows and
  Linux, including the immutable 1.6.2 candidate lineage.
- Durable nested host-input anchors and acknowledgements that preserve the exact
  task, step, roadmap revision, authority and open outcomes.
- Configurable decimal-byte session rollover with the 35,000,000-byte policy
  tested exactly.
- Reproducible 0/100/1,000/10,000-checkpoint context measurements with required
  knowledge retained and cache availability proven before references are used.

## Qualified scope

The release CI qualifies clean and 1.7.5-managed transitions on Windows and
Linux with Python 3.11, 3.12, 3.13 and 3.14. pipx and dedicated pip virtual
environments are supported persistent owners. Older immutable releases receive
mandatory data/writer transition coverage; the published managed installation
walkthrough uses 1.7.5 as its fully packaged rollback/reapply route.

Shared or editable runtimes, unknown/custom installers, cloud-synchronized
state, junction-based state and unrelated owner machines remain diagnosis-only.
OPENCNTX does not run an AI, grant external authority, or mutate a user project
while inventorying an installation.

See [Install and update OPENCNTX 1.7.6](install-and-update.md) for the exact
download, checksum, update, resume and repair commands.
