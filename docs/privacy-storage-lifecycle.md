# Privacy, storage, and format lifecycle

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

This Stable workspace surface makes local trust, storage, compatibility, and
explicit cleanup inspectable. It does not encrypt files, create user
identities, grant authority, synchronize data, publish artifacts, or clean up
automatically.

## Read-only status

```powershell
opencntx workspace lifecycle status --trust-profile single-user-local --root my-project
```

Status validates the workspace and reports:

- observed owner-only POSIX mode bits or direct Windows ACL access;
- privacy-label counts and stable source aliases, without original paths or
  source content;
- byte totals for source content, derived content, official records,
  replaceable artifacts, transaction evidence, and recovery evidence;
- the configured content budget separately from evidence and replaceable
  storage;
- the packaged schema-bundle and compatibility-matrix digests;
- whether unchanged compatible version-1 records need registration.

`--json` returns the same privacy-safe evidence in structured form. Status
does not create a writer lock, plan, state file, or temporary artifact.

## Trust profiles and permission evidence

`single-user-local` is the supported trust profile. `shared-team` is an
explicit warning profile: OPENCNTX has no user directory, group membership,
authentication, or distributed locking, so it cannot prove a team access
policy.

Permission audit results mean:

- `SAFE_OBSERVED`: the local check observed owner-only access;
- `WARNING_BROAD_ACCESS`: the check observed access broader than that profile;
- `UNSUPPORTED`: the platform could not provide the required evidence;
- `UNSAFE_PATH`: the target or one of its parents is link-like or otherwise
  outside the safe local path contract.

These results are observations, not a promise about administrators, backups,
malware, physical access, full-disk encryption, or later permission changes.
OPENCNTX does not mutate an existing ACL to make an audit pass.

## Disk-space preflight

Workspace initialization, source capture, media registration, core package
creation, migration, cleanup checkpointing, and restore check physical free
space before staging or replacing official data. The estimate includes the
known source bytes and bounded overhead for the operation. A failed preflight
stops before publishing its target.

Free-space evidence can still change after the check, so writers retain their
transaction, compare-and-swap, and rollback behavior. A preflight is not a
storage reservation or hardware durability guarantee.

## Compatible formats and migration

The installed package contains JSON schemas and one compatibility matrix for
durable records. Existing recognized version-1 records remain authoritative.
A new workspace receives `.opencntx/lifecycle/state.json`; an older compatible
workspace remains readable without it.

Preview registration without writing:

```powershell
opencntx workspace lifecycle migrate --dry-run --root my-project
```

The plan binds the exact record inventory, schema bundle, compatibility
matrix, and target state. Save that JSON, review it, and supply its exact
SHA-256 to `--apply`. Apply first rebuilds the current plan; any changed record,
unknown schema version, changed plan, unsafe path, or concurrent writer stops
the migration. Successful registration adds only the lifecycle sidecar and
does not rewrite existing domain records.

There is no downgrade path for an unknown future format. Copying an old state
file over newer records is not a supported rollback.

## Explicit cleanup and restore

Cleanup accepts only these names:

- `latest-package` for a fully verified unbound `.opencntx/latest` package;
- `catalog-cache` for the validated replaceable SQLite catalog;
- `completed-transaction:TRANSACTION-ID` for one validated completed
  transaction directory;
- `recovery-backup:RECOVERY-ID` for one validated backup that has an exact
  recovery receipt.

Preview requires every target and one new or empty checkpoint directory outside
the workspace. It validates the target, estimates checkpoint space, and emits
a deterministic plan digest. Apply accepts only that saved plan and digest,
revalidates every target under the single-writer lock, copies and hash-checks
all bytes into the private checkpoint, records the platform's directory-flush
result, and only then removes the named targets.

No command expands a directory wildcard, follows a symlink or junction,
removes original sources, removes task/chapter/control authority, or selects a
target because it is old. Cleanup never runs on a timer, startup hook, watcher,
or storage threshold.

Restore requires the retained checkpoint manifest's exact SHA-256. It refuses
changed checkpoint bytes and any destination that already exists. Restored
targets are hash-checked, and a partial failure removes only bytes written by
that failed restore attempt. The checkpoint is retained after success for the
OWNER to handle separately.

## Durability boundary

Files are flushed before publication. Parent-directory flushing is attempted
and reported as `SYNCED` or `UNSUPPORTED`; a reported sync is evidence that
the operating-system call completed, not proof against every device cache or
power-loss scenario. Windows and Ubuntu CI exercise the actual platform paths.

## v1.3.0 adaptive storage and targets

The [v1.3.0 adaptive AI workflow](adaptive-ai-workflow.md) defines one
storage contract that can remain as compact files, add a local index, shard a
very large local index, or apply explicit team concurrency controls. Escalation
depends on measured need; no database becomes mandatory.

It also defines disabled-by-default contracts for project-isolated continuity
destinations such as a notes application or synchronized folder. Those
contracts do not bundle product-specific connectors or authorize network
writes. Stable v1.4.0 behavior remains the lifecycle and optional private
Git/GitHub routes documented today.

## Sharing boundary

All lifecycle operations are local. Status aliases and counts reduce accidental
path or content disclosure, but the workspace and checkpoints can still hold
sensitive bytes. Inspect and protect them with operating-system and backup
controls. Publication, upload, release, and OWNER approval remain separate
decisions.

## Related pages

- [Workspace](workspace.md)
- [Command reference](commands.md)
- [Security in plain language](security.md)
- [Troubleshooting](troubleshooting.md)

[Documentation home](README.md)
