# Roadmap continuity and AUTO PILOT

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

The additive `flow` route keeps one roadmap, one current assignment detail and
one hash-chained history outside the chat. It is local-first, model-free and
provider-neutral. Existing `init`, `pack`, `verify` and `workspace` commands
remain available.

## Fast route

Copy [the example roadmap](../examples/continuity-roadmap.json), edit its
generic tasks, and preview only the existing paths those tasks touch:

```powershell
opencntx flow preview roadmap.json --json
```

Start the complete bounded roadmap with one approval:

```powershell
opencntx flow start roadmap.json --approval "AUTO PILOT"
```

OPENCNTX creates `.opencntx/continuity/` automatically. The canonical local
store separates roadmaps, details, information, documentation, context,
receipts, history and optional sync state. The first short assignment detail
is immediately selected.

One writer lock and a compare-before-commit event head protect every lifecycle
transition. Its events are committed as one atomic batch, so a restart sees
either the previous assignment or the complete next state.

After the host finishes that assignment, bind one or more local evidence files:

```powershell
opencntx flow advance --outcome PASS --evidence reports/task-1.json
```

The same approval remains active. OPENCNTX writes the receipt, returns to the
roadmap and immediately selects the next dependency-ready detail. No new
approval is requested inside the same roadmap.

For a failed attempt:

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
binds the current context to its selection event. Roadmap, detail or context
drift therefore stops status, advance, health, export and sync fail-closed.
Health additionally checks the derived state cache and required directories.

## Portable capsule

```powershell
opencntx flow capsule export project.ocx
opencntx flow capsule verify project.ocx
opencntx flow capsule import project.ocx --root restored-project
```

The ZIP-based capsule uses safe relative names, exact byte counts and SHA-256
for every file. Export is deterministic. Import refuses an existing store and
then runs the normal health verification. Machine-specific sync configuration
and sync errors are excluded.

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

The preview filters to UTF-8 Markdown and JSON, runs the local secret filter,
binds the current remote head and writes nothing. Apply its exact digest once:

```powershell
opencntx flow sync apply private-context-repo `
  --branch main `
  --private-repository `
  --preview-digest SHA256
```

Apply uses a disposable clone, a non-force push and remote-head readback. A
dirty checkout, changed preview, credential-bearing URL, content finding,
push conflict or ambiguous readback stops sync.

To attempt sync automatically after later successful assignment checkpoints:

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

## Exact boundary

`flow` does not start an AI, agent, shell command or assignment. The host uses
the returned detail and `NEXT_ACTION`. A PASS receipt records the host's
bounded technical assertion and evidence hashes; it does not invent truth or
OWNER acceptance. Publication, credentials, repository settings and unrelated
projects remain outside this product route.
