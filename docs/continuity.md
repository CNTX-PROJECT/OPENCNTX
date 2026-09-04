# Roadmap continuity and AUTO PILOT

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

The additive `flow` route keeps one roadmap, one current assignment detail and
one hash-chained history outside the chat. It is local-first, model-free and
provider-neutral. Existing `init`, `pack`, `verify` and `workspace` commands
remain available.

## Fast route

The commands in this guide describe Stable v1.2.1. The
[unreleased adaptive-workflow candidate](adaptive-ai-workflow.md) defines how
different AI hosts may present a current-assignment or remaining-roadmap choice
without changing authority. It does not add a released CLI command.

Use [the existing example roadmap](../examples/continuity-roadmap.json) for one
complete loop. Run these steps in order from an OPENCNTX source checkout.

1. Preview only the existing paths the example tasks touch:

```powershell
opencntx flow preview examples/continuity-roadmap.json --json
```

2. Start the bounded roadmap with one approval:

```powershell
opencntx flow start examples/continuity-roadmap.json --approval "AUTO PILOT"
```

OPENCNTX creates `.opencntx/continuity/` automatically. The canonical local
store separates roadmaps, details, handoffs, information, documentation,
context, receipts, history and optional sync state. The first short assignment
detail is immediately selected.

3. Read that exact generated detail before doing the task:

```powershell
Get-Content .opencntx\continuity\details\TASK-1.md
```

One writer lock and a compare-before-commit event head protect every lifecycle
transition. Its events are committed as one atomic batch, so a restart sees
either the previous assignment or the complete next state.

4. After the host finishes that assignment, bind one or more local evidence
files with exactly one outcome. Use PASS when the declared checks are green:

```powershell
opencntx flow advance --outcome PASS --evidence reports/task-1.json
```

Or use FAIL for a bounded failed attempt:

```powershell
opencntx flow advance --outcome FAIL `
  --evidence reports/task-1-failure.json `
  --reason "The declared check did not pass"
```

The same approval remains active. OPENCNTX writes the receipt, returns to the
roadmap and immediately selects the next dependency-ready detail. No new
approval is requested inside the same roadmap.

5. Read the returned status. After PASS, it points to TASK-2; read that next
detail before continuing the same loop:

```powershell
opencntx flow status --json
Get-Content .opencntx\continuity\details\TASK-2.md
```

After FAIL, status still points to TASK-1 and the recovery counter is visible;
reread the TASK-1 detail before the next bounded recovery attempt.

For a richer durable handoff, supply one bounded relative JSON file:

```powershell
opencntx flow advance --outcome PASS `
  --evidence reports/task-1.json `
  --handoff reports/task-1-handoff.json
```

The handoff input has exactly five fields: `decisions`, `result`,
`changed_paths`, `evidence_explanation`, and `risks`. OPENCNTX derives the
assignment, dependencies, evidence hashes, receipt binding and next assignment.
If `--handoff` is omitted, it still creates a truthful minimal handoff with no
declared decisions, changed paths, or risks.

The same standalone FAIL form is:

```powershell
opencntx flow advance --outcome FAIL `
  --evidence reports/failure-1.json `
  --reason "Relevant input changed after the failed check"
```

The flow allows at most three recovery rounds for the current assignment. The
counter and its failure fingerprints reset only when that assignment
passes and the roadmap selects the next one; earlier failures remain in the
append-only ledger for audit. It blocks the third failure in one assignment,
blocks the third repeat of the same strategy sooner, and never retries an
external action itself.

## Short existing check

Every assignment declares `touches` and one conflict class:

- `NO_CONFLICT` — no existing behavior is changed;
- `EXTEND` — new behavior is additive;
- `SUPERSEDE` — the roadmap behavior replaces an old route;
- `MIGRATE` — existing data or behavior needs an explicit migration;
- `REMOVE` — an obsolete route is deliberately removed.

Before each detail is created, OPENCNTX hashes only the matching existing
files, with a fixed 200-file bound. It does not rescan the complete repository.
The selected roadmap result wins; migration and regression evidence remain
explicit.

## Restart and health

```powershell
opencntx flow status
opencntx flow health --json
```

Status is rebuilt from the hash-chained event ledger. It always reports the
current assignment, progress, next action and minimum action. Every read binds
the stored roadmap back to the digest in `FLOW_STARTED`. It also reconstructs
every generated detail from the bound roadmap and existing-check receipt, and
binds the current context to its selection event. Every new completion handoff
is bound to its receipt, previous event head, completion event and next trigger.
Roadmap, detail, handoff or context drift therefore stops status, advance,
health, export and sync fail-closed.
Health additionally checks the derived state cache and required directories.

After the first completion, `minimum_action` explicitly routes a fresh session
through the previous handoff and then the new assignment detail. The chat is no
longer the only place that holds decisions, results, changed paths, evidence
meaning, remaining risks and the next route.

## Provider-neutral host trigger protocol

A host can receive the current detail without executing it:

```powershell
opencntx flow host status --host HOST-A
```

The response contains exactly one `current_assignment`, its detail path and
digest, the previous handoff when one exists, the roadmap-bound `AUTO PILOT`
authority, and `execution: NOT_PERFORMED`. Bind that exact delivery once:

```powershell
opencntx flow host claim `
  --host HOST-A `
  --delivery-digest SHA256
```

Repeating the same host, delivery digest, and assignment returns the same claim
without adding another event. A competing host or concurrent writer stops
fail-closed. Resume is also read-only:

```powershell
opencntx flow host resume `
  --host HOST-A `
  --claim-digest SHA256
```

While active, resume returns `EXECUTE`. After a claim-bound PASS, it returns
`NEXT` and routes the host back to `status` for the new assignment. Bind the
claim when recording PASS or FAIL:

```powershell
opencntx flow advance --outcome PASS `
  --evidence reports/task.json `
  --host HOST-A `
  --claim-digest SHA256
```

Once an assignment is claimed, an unclaimed or differently claimed `advance`
is rejected. The protocol only records and verifies transitions; it imports no
AI SDK, starts no model, executes no detail, and exposes no arbitrary shell
route.

## Portable capsule

```powershell
opencntx flow capsule export project.ocx
opencntx flow capsule verify project.ocx
opencntx flow capsule import project.ocx --root restored-project
```

The ZIP-based capsule uses safe relative names, exact byte counts and SHA-256
for every file. Export is deterministic. Import refuses an existing store and
then runs the normal health verification. Machine-specific sync configuration
and sync errors are excluded. Bound handoffs are included and verified exactly.

## Read-only adapters

```powershell
opencntx flow inspect file README.md --json
opencntx flow inspect git --json
opencntx flow inspect markdown docs --json
opencntx flow inspect json roadmap.json --json
```

The four adapters return bounded local facts and `writes: []`. They never
execute file contents or change their target.

## Optional private Git or GitHub replica

Local storage is always canonical. A Git remote is optional. First use a
dedicated clean checkout whose `origin` points to the private destination:

```powershell
opencntx flow sync preview private-context-repo `
  --branch main `
  --private-repository
```

The preview filters to UTF-8 Markdown and JSON, runs the same local secret
policy used by pack, handoffs, information, documentation, and capsules, binds
the current remote head and writes nothing. Safe handoff JSON is included; a
secret signal in handoff input, capsule content, or generated sync content
stops fail-closed without retaining or printing the matched value.
Apply its exact digest once:

```powershell
opencntx flow sync apply private-context-repo `
  --branch main `
  --private-repository `
  --preview-digest SHA256
```

Apply uses a disposable clone, a non-force push and remote-head readback. A
dirty checkout, changed preview, credential-bearing URL, content finding,
push conflict or ambiguous readback stops sync.

To attempt sync after every later local checkpoint:

```powershell
opencntx flow sync configure private-context-repo `
  --branch main `
  --private-repository
```

An automatic sync failure is recorded once and latches automatic sync in
`SYNC_BLOCKED` with `retry: NOT_AUTOMATIC`. Later assignment checkpoints do not
retry or rewrite that error. The local roadmap continues to work offline. A
successful explicit `sync apply`, or an explicit green `sync configure`, clears
the latch and re-enables later automatic checkpoints.

The single policy name is `EVERY_CHECKPOINT`. It means exactly one optional
sync attempt after each locally committed `PASS`, `FAIL`, or `BLOCKED`
transition. The checkpoint record binds requested outcome, resulting flow
status, current assignment, completed assignments and state digest. Successful
sync receipts and the first latched error include that exact record. A legacy
valid config without the field is interpreted read-only as
`EVERY_CHECKPOINT`, then rewritten once with migration marker
`LEGACY_IMPLICIT_EVERY_CHECKPOINT` at the next configured checkpoint. No remote
availability is required for the local transition to succeed.

## Exact boundary

`flow` does not start an AI, agent, shell command or assignment. The host uses
the returned detail and `NEXT_ACTION`. A PASS receipt records the host's
bounded technical assertion and evidence hashes; it does not invent truth or
OWNER acceptance. Publication, credentials, repository settings and unrelated
projects remain outside this product route.
