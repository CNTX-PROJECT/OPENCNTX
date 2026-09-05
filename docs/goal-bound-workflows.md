# Goal-bound workflows in v1.5.0

[Overview](../README.md) · [Get started](start-here.md) · [All guides](README.md)

R15 connects what the user asked for, what a connected host may do, and what
the evidence actually proves. It preserves open questions across a long task
instead of allowing one successful command or an old completion label to close
the whole request.

## What changes for a connected workflow

| Need | Behavior | Boundary |
|---|---|---|
| Keep the original request | Bind trusted host provenance and exact revision | A hash does not authenticate its author |
| Choose appropriate planning | Short work stays small; larger work has linked plans and early source checks | The host still interprets human meaning |
| Work on the right files | Compare intended targets with retained scope and current state | Physical execution is a closed Windows reference fixture |
| Know what is still missing | Derive coverage from real sources; keep open outcomes and conflicting conclusions visible | Missing data is never a verified zero result |
| Continue after interruption | Retain progress and bounded failure history in native evidence; verify current state before ACK | An ACK is not a second execution or universal exactly-once guarantee |

The combined test starts with one original question, refuses an incorrect child
target, allows the exact approved parent target, preserves protected files and
open outcomes, restarts the process, and refuses a duplicate physical mutation.
It deliberately leaves analysis PARTIAL when the full requested answer is not
yet evidenced.

## Installation is not host activation

Install the published exact version using [Get started](start-here.md). The
package includes the new Python APIs and schemas with no runtime dependencies.
Existing commands continue to work. It does not install or trust a Codex hook,
modify a sandbox, register a background agent or enable the reference writer.

A host developer explicitly connects its trusted message registry, current
request, approved action scope and native project state. The supervisor retains
the expected binding independently of the client; never build that expectation
from the untrusted action request itself. Unknown or copied AI provenance is
not promoted to OWNER authority. Existing OWNER decisions remain authoritative.

The reference writer operates only on fixed synthetic parent/child/backup files.
It is a runnable proof of a bounded adapter, not a supported general file editor.
Unconnected shell/file tools remain outside its enforcement boundary.

## Compatibility and recovery

Legacy v1 schema and fixture bytes remain unchanged. New goal records are
explicit v2 envelopes, not silent extra fields inserted into old records.
The optional new storage envelope preserves the original roadmap bytes exactly;
old readers/writers reject it before mutation. Installation alone does not
upgrade a project's stored roadmap format.

Recovery checks all participating original, staged, retired and backup states
before restoring them. Later user work is preserved rather than overwritten.
New evidence survives downgrade as retained recovery material. No multi-file
power-loss atomicity or universal filesystem behavior is promised.

## Developer contracts and proof

- [Shared binding](GOAL_BINDING_CONTRACT.md)
- [Task assessment](TASK_ASSESSMENT_CONTRACT.md)
- [Linked progress](GOAL_PROGRESS_CONTRACT.md)
- [Source coverage](OUTCOME_COVERAGE_CONTRACT.md)
- [Followup and output](GOAL_FOLLOWUP_CONTRACT.md)
- [Handoff, version fence and recovery](GOAL_HANDOFF_CONTRACT.md)
- [Closed reference host](REFERENCE_FIXTURE_HOST.md)

The test suite includes positive and refusal routes, process restart, faults
after completed operations, compatibility, privacy and generic source oracles
at 10, 100, 1,000 and 4,001 records. [Platform guidance](platforms.md) distinguishes
actual CI evidence from declared support and explicit platform skips.
Check the matching GitHub Release for published availability: a local build,
source branch or green test alone is not a published release.
