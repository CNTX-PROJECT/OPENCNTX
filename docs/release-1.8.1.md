# OPENCNTX 1.8.1

[Overview](../README.md) · [Get started](start-here.md) · [Install and update](install-and-update.md) · [Releases](releases.md)

OPENCNTX 1.8.1 is a compatibility and installation-hardening release. It
keeps the local-first knowledge contracts introduced in 1.8.0 and makes the
managed installation, host-footer boundary and existing-project audit more
explicit and recoverable.

## Delivered

- Align the owner-facing footer separator contract and add a closed,
  session-bound `ocx-footer-host-envelope-v1` input route.
- Recognize the active `.opencntx/latest/manifest.json` projection during
  installation inventory.
- Treat a changed same-version wheel as a real managed transition and retain
  the exact active wheel for rollback.
- Serialize managed update and resume operations with a product-owned
  operating-system lock.
- Validate wheel path safety and the complete `METADATA`, `WHEEL` and
  `RECORD` relationship before activation.
- Audit existing-project adoption for active/archive boundaries, case
  collisions, duplicate ordinals, links or junctions, invalid UTF-8,
  unresolved links and cycles.
- Require a reviewed adoption preview digest before writing the derived
  `.opencntx/adoption-v1.json` manifest.
- Keep adoption writes confined to `.opencntx`; existing source files are not
  moved, renamed, deleted or rewritten.
- Retain the 1.8.0 knowledge, pack, workspace, continuity, layout and managed
  rollback contracts.

## Verification

The release passed the full local suite with `845 passed`, `5
skipped` and `4,517` subtests. Ruff and mypy were clean; total branch coverage
was 80.04% and CLI coverage was 66.51%.

The bounded installation simulation passed both a fresh install and an update
from 1.8.0, including eight idempotent re-apply cycles, concurrent-writer
rejection, lock release after process termination, post-activation restoration
to 1.8.0 and fail-closed handling of an ambiguous visual adoption case.

The practical simulation also exercised 100 assignments, 200 process
restarts, 120 layout-chaos scenarios, recovery, concurrency and scale gates
through 4,509 projects without network requests or writes to real project
maps.

## Qualified boundaries

The release remains local-first and dependency-free. It does not call an AI,
upload sources, execute remembered techniques, infer OWNER authority, or use a
remote semantic index.

Adoption is still preview-first and read-only with respect to human-owned
source files. A blocked audit is an explicit review outcome, not a successful
visual takeover. The `VISUAL_ARTIST` gate for a real existing project remains
separate until a reviewed digest-bound apply, strict verification, zero-write
second run and rollback are proven on that project.

There is no PyPI or TestPyPI publication. The four GitHub Release assets are
the wheel, source distribution, checksum file and build record.

See the [1.8.1 compatibility and integration roadmap](roadmap-1.8.1.md),
[knowledge layer guide](knowledge-layer.md), and
[release artifact verification](release-artifacts.md) for the exact contracts.
