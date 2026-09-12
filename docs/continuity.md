# Roadmap continuity and AUTO PILOT

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

The additive `flow` route keeps one roadmap, one current assignment detail and
one hash-chained history outside the chat. It is local-first, model-free and
provider-neutral. Existing `init`, `pack`, `verify` and `workspace` commands
remain available.

For one host, use the fast route below directly; no host claim is needed. Use
the concurrent-host protocol only when more than one process could act on the
same roadmap. Both routes keep the same single writer, authority, target,
privacy, integrity, and evidence checks.

## Fast route

The commands in this guide remain Stable in the current v1.7.6 release. The
[adaptive AI workflow](adaptive-ai-workflow.md) defines how
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

Roadmaps that preclassify every detail with `CHAIN.` or `STANDALONE.` use four
fixed stages: `STANDARD_ATTEMPT_1`, `STANDARD_RETRY_2`,
`GLOBAL_RECOVERY_1`, and `GLOBAL_RECOVERY_2`. A global stage must bind the
complete relevant chain, the failure layer, prior evidence, and a materially
changed approach. The second global stage also needs new evidence and strictly
wider coverage. An exhausted chain stops with a detailed report. An exhausted
standalone assignment may be skipped only to a proven independent assignment;
that required skip still prevents full-roadmap success.

Older roadmaps without either classification retain their v1 three-round
behavior and stored bytes. No migration silently changes historical evidence.

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

## Connected current views

For project-aware step and child-roadmap routing delivered in 1.7.4 and retained
in 1.7.5, see the [project roadmap guide](project-roadmaps.md) and
[release scope](release-1.7.5.md).
Broader host integration and measurement work remains on the [roadmap](roadmap.md).

These existing features are retained in v1.7.5 from the v1.6.x line.
The matching GitHub Release establishes published availability;
installation never activates a host hook. Project-routing behavior is
implemented only where stated in the [1.7.5 release scope](release-1.7.5.md).

`flow start --connected` opts into a revision-bound current view. `flow current`
reads status without creating a missing flow. `flow current --publish` needs
`--expected-state` with the exact native state digest. An optional `--goal` must
come from the host's current supervisor binding. `--synthesis` names native-bound
final evidence. A supplied goal document never grants authority.

CONFIGURED_ONLY means no continuity store; BINDING_REQUIRED means no current view.
CURRENT and STALE compare native source and Combo digests. FLOW_CONNECTED retains
assignments but cannot prove semantic completion. GOAL_CONNECTED additionally uses
original outcomes and synthesis. Host enforcement remains UNPROVEN; only the closed
Windows reference fixture demonstrates actual dispatch.

Each generation contains state.json, ROADMAP.md, FOOTER.json and a hash receipt.
CURRENT changes last. An interrupted generation retains history; source or Combo
drift makes the old view STALE. Native writer lock and Combo CAS reject competing
updates. Open outcomes, authority and evidence remain visible. An oversized view
fails instead of truncating obligations.

CLI advance refreshes an existing FLOW_CONNECTED view. GOAL_CONNECTED requires
supervisor rebinding after native mutation and never silently downgrades. API hosts
must rebind and publish after checkpoints. No universal Codex hook is installed.

`begin_recovery` preserves parent outcomes and return steps. Temporary test-only
repair uses a BLOCKED execution node while retaining original intent. The supervisor
can finish repair with test evidence, making the original resume step ready without
widening exclusions. The helper bounds retained repair splits to three and respects
an exhausted native budget; native failure recording owns its ledger counter.
It does not execute arbitrary test commands.

An authorized host calls `record_export_delivery` before and after copying current
Markdown. This records idempotent SYNC_PENDING or CURRENT receipts in the local
views/deliveries directory without writing the destination. `export_status` remains
read-only. Export is optional; there is no notes-application dependency.

Update plan v2 binds exact project state and a managed candidate JSON profile's
runtime_version. Active flows need UPDATE_CHECKPOINT. Active writers and profile
drift block cutover. Existing v1 plans remain readable; v1 readers must reject v2.
Backup/journal recovery preserves later user data. These checks neither install
software nor invent a connected workflow in a context-only project.
