# Goal-bound handoff and storage compatibility (development candidate)

## One existing state channel

`prepare_goal_handoff` validates the actual current goal, loads native-bound
progress and followup, and compiles the real output context. Its bounded v2
snapshot binds request, hierarchy positions, open outcomes, source/evidence and
native progress digest. It uses the existing compressed evidence-object store
and v1 session handoff, not a second scheduling database or a full transcript.

`accept_goal_handoff` validates the portable handoff identifier before reading,
requires exactly the expected snapshot evidence, and compares its complete
canonical bytes against a fresh current snapshot. Resume must still be CONTINUE.
The existing writer lock and expected-state-digest check guard preparation and
ACK writes. Missing, changed, stale or foreign-request evidence is refused.

An ACK is an acknowledgement, always NOT_PERFORMED. Duplicate/lost ACKs do not
repeat the closed physical mutation. This does not grant exactly-once execution
to an arbitrary external service or make multi-file updates power-loss atomic.
Tests cover an actual process exit after preparation, restart, replay and stale
state, plus the connected original-question/action/handoff route.

## Explicit version fence

`upgrade_goal_storage` requires exact state and the explicit approval phrase
`UPGRADE GOAL STORAGE <digest>`. It wraps the original v1 roadmap bytes in a
separate `opencntx-goal-storage-envelope` version 2 with base64 content and exact
digests. The new reader validates and unwraps it; an actual old v1 reader/writer
rejects the unknown outer format before mutation. Existing v1 schemas, golden
fixtures, historical events and embedded original bytes remain unchanged.

This is a staging API, not an automatic installed-runtime migration. The caller
must stage and back up the existing transactional update. Never strip the new
version fence merely to let an old writer enter the current new store. A downgrade
restores an exact old snapshot while retaining newer evidence separately.

## Conservative recovery

Transactional recovery checks the complete active/staged/retired/backup set
before moving anything. Changed later user work blocks rollback and is retained.
Replaced trees and recovery snapshots are preserved outside active locations,
not recursively deleted as cleanup. Original bytes and new evidence remain
available for review; retained snapshots need a separate deliberate retention
decision, not silent automatic destruction.

Portable state/handoff behavior is tested on Windows and Linux. The physical
reference writer is Windows-only. Local test results do not prove remote CI,
arbitrary Codex host interception, universal semantics or sudden power-loss
durability. No active installation or publication is implied by this candidate.
