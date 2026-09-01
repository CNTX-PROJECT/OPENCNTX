# Command reference

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

This navigation table documents 63 public CLI paths: five orientation and
version routes plus all 58 executable routes from the real parser. It does not invent options or grant
permission to run a workflow step. Use the exact nested `--help` output for
required arguments and repeatable options.

| # | Command path | Purpose |
|---:|---|---|
| 1 | `opencntx --help` | show top-level orientation without changing a project |
| 2 | `opencntx --version` | show the installed package version without requiring a subcommand |
| 3 | `opencntx workspace --help` | show workspace command groups |
| 4 | `opencntx workspace media --help` | show media routes |
| 5 | `opencntx workspace task --help` | show task lifecycle routes |
| 6 | `opencntx init` | create a readable core configuration |
| 7 | `opencntx pack` | build one bounded core context package |
| 8 | `opencntx verify` | verify a core package and its source drift |
| 9 | `opencntx workspace init` | create a new local project workspace |
| 10 | `opencntx workspace capture` | store one supplied source byte-for-byte |
| 11 | `opencntx workspace doctor` | diagnose active or interrupted writer transactions read-only |
| 12 | `opencntx workspace recover` | preview or apply one exact backup-first recovery |
| 13 | `opencntx workspace lifecycle status` | audit trust, permissions, privacy, storage, and formats read-only |
| 14 | `opencntx workspace lifecycle migrate` | preview or apply exact compatible-v1 registration |
| 15 | `opencntx workspace lifecycle cleanup` | preview or apply explicit checkpointed cleanup |
| 16 | `opencntx workspace lifecycle restore` | restore exact bytes from a verified cleanup checkpoint |
| 17 | `opencntx workspace control refresh` | refresh the derived current-roadmap snapshot |
| 18 | `opencntx workspace chapter create` | create one new draft chapter with source pins |
| 19 | `opencntx workspace catalog rebuild` | rebuild the derived local catalog and index |
| 20 | `opencntx workspace media register` | register supplied derived UTF-8 text |
| 21 | `opencntx workspace media review` | record review of one exact derived text object |
| 22 | `opencntx workspace media promote` | capture accepted derived text with provenance |
| 23 | `opencntx workspace media status` | report current derivation state read-only |
| 24 | `opencntx workspace media verify` | verify source, record, review, and text bindings |
| 25 | `opencntx workspace media remove` | remove exact active derived bytes with a tombstone |
| 26 | `opencntx workspace playbook register` | register a proposed playbook revision |
| 27 | `opencntx workspace playbook approve` | approve one exact playbook definition |
| 28 | `opencntx workspace playbook status` | report playbook state read-only |
| 29 | `opencntx workspace playbook verify` | verify playbook records and definition digests |
| 30 | `opencntx workspace role register` | register a proposed role revision |
| 31 | `opencntx workspace role approve` | approve one exact role definition |
| 32 | `opencntx workspace role status` | report role state read-only |
| 33 | `opencntx workspace role verify` | verify role records and definition digests |
| 34 | `opencntx workspace executor prepare` | bind task, context, playbook, and role |
| 35 | `opencntx workspace executor status` | report executor package state read-only |
| 36 | `opencntx workspace executor verify` | verify assignment and permission bindings |
| 37 | `opencntx workspace context build` | build one deterministic task-bound package |
| 38 | `opencntx workspace context verify` | verify live task and context bindings read-only |
| 39 | `opencntx workspace task propose` | append one exact task proposal |
| 40 | `opencntx workspace task approve` | append exact OWNER proposal approval |
| 41 | `opencntx workspace task begin` | move one approved task into execution |
| 42 | `opencntx workspace task submit-result` | append one result and evidence binding |
| 43 | `opencntx workspace task review-result` | append an ARCHITECT review |
| 44 | `opencntx workspace task accept-result` | append the exact OWNER result decision |
| 45 | `opencntx workspace task close` | close an accepted task |
| 46 | `opencntx workspace task status` | report current task state read-only |
| 47 | `opencntx workspace task record-attempt` | append one objective failed-attempt record |
| 48 | `opencntx workspace task cancel` | terminate a task explicitly as cancelled |
| 49 | `opencntx workspace task supersede` | terminate a task in favor of a named successor |
| 50 | `opencntx flow preview` | inspect only existing paths touched by a roadmap |
| 51 | `opencntx flow start` | bind one complete roadmap to one AUTO PILOT approval |
| 52 | `opencntx flow status` | rebuild the current pointer from hash-chained history |
| 53 | `opencntx flow advance` | record PASS or FAIL and trigger the next detail |
| 54 | `opencntx flow health` | verify local roadmap, state, detail and history |
| 55 | `opencntx flow capabilities` | discover local storage and Git capabilities read-only |
| 56 | `opencntx flow inspect` | use the file, Git, Markdown or JSON adapter read-only |
| 57 | `opencntx flow capsule export` | export a deterministic portable context capsule |
| 58 | `opencntx flow capsule verify` | independently verify capsule paths and bytes |
| 59 | `opencntx flow capsule import` | restore a capsule only into a new local store |
| 60 | `opencntx flow sync preview` | preview a filtered private Git replica without writes |
| 61 | `opencntx flow sync configure` | enable one optional automatic checkpoint replica |
| 62 | `opencntx flow sync apply` | non-force push one exact preview and read it back |
| 63 | `opencntx flow sync status` | report optional sync configuration and receipt |

## Roadmap flow

The shortest complete route is:

```powershell
opencntx flow preview roadmap.json --json
opencntx flow start roadmap.json --approval "AUTO PILOT"
opencntx flow status
opencntx flow advance --outcome PASS --evidence reports/task.json
```

Each successful `advance` stores a receipt, returns to the roadmap and selects
the next dependency-ready detail. The approval is not requested again. Read
[Roadmap continuity and AUTO PILOT](continuity.md) for the roadmap format,
portable capsule, four read-only adapters and optional Git/GitHub replica.

## Core pack options

Confirm the installed version without a subcommand:

```powershell
opencntx --version
```

Run the complete read-only selection, budget, and local secret-policy plan:

```powershell
opencntx pack --preview
```

Override only one exact current high-confidence finding reported by preview:

```powershell
opencntx pack --allow-secret FINDING_ID_FROM_PREVIEW
```

Repeat `--allow-secret` only when preview reports multiple exact findings that
you have separately reviewed. Unknown, duplicate, warning-only, or stale IDs
fail. Preview writes nothing and never grants persistent permission.

Verify the default package under the current directory:

```powershell
opencntx verify
```

This checks exactly `.opencntx/latest` and never searches upward. An explicit
`opencntx verify PATH` keeps the existing path-bound behavior.

## Public language and terminal contract

OPENCNTX uses English for fixed CLI help, errors, warnings, results, templates,
and generated headings. User-provided content and paths remain UTF-8. Fixed
tool text is ASCII-safe; when a narrow Windows console cannot represent a user
character, the CLI escapes that character instead of crashing or changing the
stored bytes.

## Workspace: compact current roadmap control

Refresh a supported marked current block with:

```powershell
opencntx workspace control refresh --root my-project
```

The snapshot is derived. It does not edit, interpret, approve, or synchronize
the official roadmap.

## Workspace: transaction diagnosis and recovery

Diagnose without writing, creating a lock, or repairing anything:

```powershell
opencntx workspace doctor --root my-project
```

If doctor reports `RECOVERY_REQUIRED`, copy its exact transaction ID and intent
SHA-256 into a preview:

```powershell
opencntx workspace recover --root my-project --transaction TXN-ID --intent-sha256 SHA256
```

The preview changes nothing. Apply only after inspecting the exact action:

```powershell
opencntx workspace recover --root my-project --transaction TXN-ID --intent-sha256 SHA256 --apply
```

Apply refuses an active writer, changed intent, unsafe link, unknown transaction
data, or changed target. It creates and verifies a retained local backup before
rolling the named transaction back and writes a recovery receipt.

## Workspace: privacy, storage, and format lifecycle

Audit one workspace without changing it:

```powershell
opencntx workspace lifecycle status --trust-profile single-user-local --root my-project
```

The status uses stable source aliases instead of original paths or content. It
reports observed POSIX mode bits or Windows ACL access, privacy-label counts,
storage categories, schema compatibility, and migration state. The
`shared-team` profile always warns because OPENCNTX has no identity or group
model.

Preview registration of unchanged compatible version-1 records:

```powershell
opencntx workspace lifecycle migrate --dry-run --root my-project
```

Apply requires the saved exact plan file and its SHA-256. Cleanup has the same
two-step rule. Preview names only an allowlisted target and a checkpoint
outside the workspace:

```powershell
opencntx workspace lifecycle cleanup --target latest-package --checkpoint C:/safe/opencntx-checkpoint --write-plan C:/safe/cleanup-plan.json --root my-project
```

Then apply only the reviewed plan:

```powershell
opencntx workspace lifecycle cleanup --apply --plan C:/safe/cleanup-plan.json --plan-sha256 SHA256 --root my-project
```

Restore verifies the retained checkpoint before copying exact bytes back:

```powershell
opencntx workspace lifecycle restore --checkpoint C:/safe/opencntx-checkpoint --checkpoint-sha256 SHA256 --root my-project
```

No cleanup is automatic. Migration does not rewrite existing version-1 domain
records, and unknown future formats stop fail-closed. See [Privacy, storage,
and format lifecycle](privacy-storage-lifecycle.md).

## Workspace: objective failed-attempt evidence

Record facts about one failed external action without executing or retrying it:

```powershell
opencntx workspace task record-attempt TASK-EXAMPLE-0001 `
  --executor-id EXEC-20260820-0123456789ab `
  --action inspect-source `
  --command-type inspect-file `
  --target SOURCES/attempt-input.txt `
  --input SOURCES/attempt-input.txt `
  --exit-status 2 `
  --error-class invalid-input `
  --actions-used 1 `
  --duration-ms 250 `
  --result-evidence attempt-result.txt `
  --root my-project
```

Repeat `--input` for every relevant regular workspace file. After the first
attempt, use genuinely changed input bytes or add
`--new-evidence NEW-EVIDENCE-FILE`. A new filename, changed wording, mtime,
argument order, or identical evidence bytes is not a new basis.

The fixed error classes are `invalid-input`, `missing-input`,
`permission-denied`, `not-found`, `timeout`, `conflict`,
`resource-exhausted`, `dependency-failure`, `tool-failure`, and `unexpected`.
Status reports digests and budgets but never prints the evidence contents.

Three equal task-wide fingerprints, five total attempts, 25 cumulative actions,
or 1,800,000 cumulative milliseconds block the task. No option resets or
widens these limits. The OWNER may cancel the blocked task or supersede it with
one explicit new task ID.

## Find exact options

Add `--help` to the specific route, for example:

```powershell
opencntx workspace context build --help
opencntx workspace playbook register --help
```

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | The requested operation completed and its checks passed |
| `1` | A read-only verification or status check found drift or invalid bindings |
| `2` | Arguments, input, configuration, paths, budgets, secret policy, or stored structure were invalid |

Treat every non-zero exit as a stop until you understand the reported result.
The core contract is explained in [Core commands](core.md#exit-codes).

## Important boundary

A documented command is not authority to approve a task, delete content,
publish a result, or bypass an OWNER gate. The active task records and exact
digests remain controlling.

## Related pages

- [Core commands](core.md)
- [Workspace](workspace.md)
- [OWNER flow](owner-flow.md)
- [Privacy, storage, and format lifecycle](privacy-storage-lifecycle.md)
- [Troubleshooting](troubleshooting.md)

[Documentation home](README.md)
