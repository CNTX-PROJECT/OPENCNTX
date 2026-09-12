# Legacy recovery without resetting Codex

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

Development candidate documentation — not available in installed 1.7.4.
This page describes a staging tool, not a complete installer or a universal downgrade.

## What is fixed in this candidate?

The transactional updater can retire a completed receipt during rollback and
retry the same plan. Receipt history is archived, not deleted. A durable recovery
intent makes an interrupted rollback resumable before a later apply.

For an existing portable-v1 continuity store, `flow legacy-stage` prepares a
separate project copy without the newer coordination markers. It never deletes
locks from the original project, overwrites an existing destination or switches
the runtime. Actual 1.6.3 source has successfully written a checkpoint on this
copy in a Windows regression fixture; other versions and installation routes
still require qualification.

## Recovery journey

| Stage | Result |
|---|---|
| Identify current checkpoint and storage format | Name the source and exact state, without guessing version support. |
| Prepare an isolated copy under current writer locks | Original data and coordination paths stay in place. |
| Validate the actual intended older runtime against the copy | A staging success is not compatibility certification. |
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
| Newer storage envelope | Use a complete retained compatible snapshot; do not strip the format fence. |
| State changed | Refresh the current checkpoint and review the new state before retrying. |
| Destination exists | Keep it intact and select another new recovery destination. |
| Filesystem or host permission denied | Obtain only the required scoped access; do not disable platform safeguards. |
| Copy interrupted or inconsistent | Original remains available; any staging data is retained for diagnosis. Do not call it a completed recovery. |

Resetting Codex, deleting chat history, disabling antivirus or recreating all
projects is not an accepted remedy for these compatibility issues.

The original project must be quiesced with respect to unmanaged external writes.
Supported writers share the held locks; content digests detect observed changes,
but cannot make arbitrary external editors participate in the transaction.
