# Playbooks and roles

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

> **Stable and optional:** playbooks, roles, and executor packages belong to
> the workspace route. They are not required for a core context package.

Playbooks and roles describe a bounded method and a bounded set of actions.
They do not start a person, process, tool, model, or agent.

## Playbook

A playbook revision can state:

- purpose;
- required inputs;
- ordered procedure;
- expected output;
- required evidence;
- stop conditions.

Register first, inspect the definition digest, and approve that exact revision
separately.

## Role

A role revision contains allowed and forbidden action tokens. It also follows
register → inspect → exact approval.

A role name is not an operating-system account, cryptographic identity, or
automatic permission grant.

## Effective actions are an intersection

An action is effective only when it is allowed by all three:

1. the approved task;
2. the approved playbook;
3. the approved role.

Any conflict stops fail closed. Forbidden actions cannot be cancelled out by a
broader allowed list.

## Prepare one executor package

```powershell
opencntx workspace executor prepare TASK-EXAMPLE-0001 `
  --revision 1 `
  --proposal-digest PROPOSAL_DIGEST_HERE `
  --playbook-id PB-EXAMPLE-0001 `
  --playbook-revision 1 `
  --playbook-digest PLAYBOOK_DIGEST_HERE `
  --role-id ROLE-EXAMPLE-0001 `
  --role-revision 1 `
  --role-digest ROLE_DIGEST_HERE `
  --context-manifest-digest CONTEXT_MANIFEST_DIGEST_HERE `
  --executor EXECUTOR-EXAMPLE-0001 `
  --root my-project
```

The exact command requires the task, context, playbook, and role digests shown
by prior steps. At most one executor package exists per task revision.

The package contains assignment metadata and allowed actions. It does not copy
the full context bytes and does not launch execution.

## Bind a failed attempt

An objective failed-attempt record requires the exact executor ID and one
action from this package. OPENCNTX verifies the package, task, approved
definitions, original context-manifest bytes, and effective action before it
writes evidence. The attempt stores the executor record digest and context
manifest digest. The executor name and actor string are not a login, signature,
cryptographic identity, or OWNER grant.

Task progress changes the generated `TASK.md`, so a later attempt verifies the
original immutable context package bytes named by the executor package instead
of pretending that the pre-attempt live route is unchanged. Any change to the
stored `CONTEXT.md` or `manifest.json` still fails closed.

## Status after task completion

When the task leaves `IN_EXECUTION`, the package reports `TASK_FINISHED`. It
must not remain an apparently active authority after the task ends.

## Related pages

- [OWNER flow](owner-flow.md)
- [Context navigation](context-navigation.md)
- [Command reference](commands.md)
- [Security](security.md)

[Documentation home](README.md)
