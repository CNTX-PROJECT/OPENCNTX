# How OPENCNTX works

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

OPENCNTX solves one practical problem: large or mixed project history makes it
hard to give an AI tool only the information needed for the current task.

## The simple idea

1. You initialize one narrow goal and allowed file set.
2. You preview the exact selection and local secret decision.
3. You pack a bounded text package.
4. You inspect the generated `CONTEXT.md` yourself.
5. You verify the recorded bytes.
6. You decide whether to share anything.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../assets/docs/opencntx-overview-dark.svg">
  <img src="../assets/docs/opencntx-overview.svg" alt="Select local files, review and verify a small context package, then decide whether to share it">
</picture>

## What “any model” means

OPENCNTX produces ordinary text and JSON files. You may use those files with
ChatGPT, Claude, Gemini, a local model, another provider, or no AI tool at all,
as long as the chosen tool accepts the input format.

It does **not** mean that OPENCNTX:

- calls every model;
- guarantees compatibility with every interface;
- chooses the best provider;
- sends files over the network;
- verifies an AI answer.

## Two layers

### Core layer

`init`, `pack --preview`, `pack`, inspection, and `verify` create and check one
context package directly from a project directory.

### Stable workspace layer

The optional Stable workspace stores supplied sources, chapters,
tasks, playbooks, roles, approvals, and evidence as readable local records. It
can select a small context set for one approved task, but none of these
concepts is required for the core route.

Official workspace writers use local workspace/task locks and exact state
comparisons. Each mutation leaves a transaction journal. A hard process crash
therefore leaves the previous valid state or exact local evidence for read-only
diagnosis and explicit backup-first recovery.

Failed execution attempts are also recorded as local evidence, not as prose
claims. OPENCNTX derives a stable fingerprint from the command type, target,
relevant input digests, exit status, and one fixed error class. It binds that
record to the exact executor package, context manifest, allowed action, and
copied result evidence. Fixed task-wide limits stop repeated or alternating
failure loops; OPENCNTX never executes or retries the command itself.

## Three kinds of evidence

- **Bytes:** the exact stored or selected content.
- **Digests:** SHA-256 values that reveal changed bytes.
- **Decisions:** explicit OWNER approvals bound to exact objects.

None of these proves that a statement is true. They make the process easier to
inspect and reproduce.

## Why it stays local

Local-first behavior keeps selection and review under your control. OPENCNTX
has no network client, account system, cloud database, or provider SDK. The
boundary changes only when you deliberately move output elsewhere.

## Next pages

- [Start here](start-here.md)
- [Context packages](context-packets.md)
- [Workspace](workspace.md)
- [OWNER flow](owner-flow.md)
- [Security](security.md)

[Documentation home](README.md)
