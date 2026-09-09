# OPENCNTX 1.7.3 — Reliability release

[Overview](../README.md) · [Install](start-here.md) · [Releases](releases.md) · [Roadmap](roadmap.md)

Version 1.7.3 converts the highest-priority failures found by the 1.7.2
stress assessment into tested runtime behavior. The authoritative distribution
is the immutable `v1.7.3` GitHub Release and its four attached assets.

## Delivered behavior

- Local writer exclusion uses an operating-system lock on a stable coordination
  file. A dead process releases ownership; an active writer remains protected.
- A committed native flow result is retained across optional sync or diagnostic
  failure, and an identical retry returns that result instead of advancing work.
- Stale answer-only verification never enables writes. Restored authority can
  repair a previously blocked governed decision, and valid multi-target local
  work is promoted rather than artificially refused.
- Sidecar and update targets use conservative parent, child, wildcard and case
  overlap checks. Transactional update previews reject path aliases and overlap.
- Combo keeps 1,000 canonical decisions while rendering at most 32 inline.
  Exact adaptive-storage identifiers are read directly before bounded search.
- Sync verifies the exact bytes again during materialization and stops on preview
  drift before commit or push. Capsule verification rejects duplicate manifest
  paths.
- Connected current views retain compact progress and revision-bound references
  instead of copying an unbounded Definition of Done.
- `read_update_generation` is the coherent access point for a declared
  multi-component update. It pins the shared lock for one complete observation
  and refuses a mixed or unknown generation.

## Update boundary

The managed reader and `apply_update_plan` form the proven local update channel.
Code that reads separate active component paths directly during cutover is a
legacy, unmanaged route and cannot receive a cross-directory atomicity promise
from the operating system. Migrate such readers to `read_update_generation`
before relying on the coherent-generation guarantee.

Backup, retired generations and recovery snapshots are explained retained data,
not active old installations. Cleanup remains ownership-bound; unrelated user
data is never treated as release residue.

## Evidence boundary

The release regression set covers the twelve targeted 1.7.2 findings, three
hard-exit cutover phases, a concurrent managed reader, the existing long-flow
simulation and the full Windows/Ubuntu Python 3.11–3.14 CI matrix. Green checks
prove those routes only. They do not prove every host integration, external
provider policy, cost saving or arbitrary filesystem.

## Explicitly not included

- No PyPI or TestPyPI publication.
- No automatic installation or host activation.
- No global Git hooks or replacement of Codex/ChatGPT policy.
- No claim that a boolean alone authorizes an external write.
- No broad real-project efficiency claim; that remains a separate pilot.
- No automatic notes application export or universal host adapter.

See [Release artifacts](release-artifacts.md) for the exact wheel, sdist,
checksums and source-bound build record.
