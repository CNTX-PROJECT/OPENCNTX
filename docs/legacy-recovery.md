# Legacy recovery without resetting Codex

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

This recovery route is available in the installed v1.7.5 release. It prepares an
isolated copy for a legacy writer; it is not an in-place downgrade or a complete
installer migration.

## What v1.7.5 fixes

The transactional updater can retire a completed receipt during rollback and
retry the same plan. Receipt history is archived, not deleted. A durable recovery
intent makes an interrupted rollback resumable before a later apply.

For an existing portable-v1 continuity store, `flow legacy-stage` prepares a
separate project copy without the newer coordination markers. It never deletes
locks from the original project, overwrites an existing destination or switches
the runtime. When a v2 goal-storage envelope is present, the complete retained
v1 roadmap snapshot is validated and restored only in the staged copy. The
source remains byte-for-byte unchanged.

The actual 1.6.0, 1.6.1, 1.6.2 and 1.6.3 source trees each wrote a checkpoint on
both an original v1 copy and a v1-compatible copy staged from the v2 envelope.
This matrix qualifies the legacy recovery route for those four releases. It
does not claim that an old writer may enter the active v2 store directly.

## Recovery journey

| Stage | Result |
|---|---|
| Identify current checkpoint and storage format | Name the source and exact state, without guessing version support. |
| Prepare an isolated copy under current writer locks | Original data and coordination paths stay in place. |
| Validate the actual intended older runtime against the copy | The v1.7.5 matrix covers 1.6.0 through 1.6.3; other runtimes still need their own evidence. |
| Plan a controlled runtime/project switch | Not performed by this staging command; retain the original and reconcile later edits. |

Use the exact `state_digest` from the current checkpoint/status. The destination
must not exist and its parent must exist outside the original project:

```text
opencntx flow status --root PATH_TO_PROJECT --json
opencntx flow legacy-stage --root PATH_TO_PROJECT --destination NEW_RECOVERY_DIRECTORY --expected-state EXACT_STATE_DIGEST
```

The result names `staged_project` and explicitly reports
`STAGED_REQUIRES_LEGACY_VALIDATION` and `runtime_switched: false`.
Do not continue writing to both copies as if they were the same active project.
This is not an automatic merge mechanism.

## Targeted diagnosis

| Condition | Next step |
|---|---|
| Active current writer | Let that scoped operation finish/checkpoint, then retry. Never delete its lock. |
| Unknown or old marker | Verify the writer's shutdown and select a qualified migration route; this tool does not guess liveness. |
| Newer storage envelope | `legacy-stage` validates and restores its complete retained compatible snapshot in the isolated copy; do not strip the format fence. |
| State changed | Refresh the current checkpoint and review the new state before retrying. |
| Destination exists | Keep it intact and select another new recovery destination. |
| Filesystem or host permission denied | Obtain only the required scoped access; do not disable platform safeguards. |
| Copy interrupted or inconsistent | Original remains available; any staging data is retained for diagnosis. Do not call it a completed recovery. |

The 1.6.x compatibility path no longer requires a Codex reset. Resetting Codex,
deleting chat history, disabling antivirus or recreating all projects is not an
accepted remedy for these issues.

The remaining stops are deliberate safety boundaries, not legacy-version
blocks: a live or unknown writer, changed bytes, a missing or invalid retained
snapshot, an occupied destination, an unsafe path, or missing operating-system
permission must still be resolved with the exact scoped evidence. v1.7.5 does
not silently unlock a live store or bypass those checks.

The original project must be quiesced with respect to unmanaged external writes.
Supported writers share the held locks; content digests detect observed changes,
but cannot make arbitrary external editors participate in the transaction.
