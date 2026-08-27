# Glossary

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

## ARCHITECT

The role that analyzes a goal, proposes bounded work, prepares context, and
reviews a result. The label does not automatically grant system permissions.

## Bounded executor

A person or tool working only inside an approved task, playbook, role, and
context package. OPENCNTX does not start it.

## Capture

Byte-exact local storage of one supplied regular file plus origin, privacy,
size, digest, and receipt.

## Chapter

A versioned local knowledge document with exact source and dependency pins.

## Context package

A small set of selected text plus metadata for one task.

## Control snapshot

A deterministic copy of one exactly marked current roadmap block. It reduces
hot context without rewriting the full roadmap.

## Digest

A SHA-256 value calculated from exact bytes. It detects changes but does not
prove truth or approval.

## Fail closed

Stop without partial success when required evidence or validation is missing.

## Freshness

Technical state showing whether chapter source and dependency pins still
match. `CURRENT` does not mean factually correct.

## Manifest

A machine-readable record of package files, sizes, paths, and digests.

## OWNER

The human final authority who states goals and makes exact approval and result
decisions.

## Pin

An exact reference to an object, revision, path, or digest that must match.

## Playbook

A proposed or approved bounded method: purpose, inputs, procedure, output,
evidence, and stop conditions.

## Privacy label

A local classification such as `PRIVATE` or `RESTRICTED`. It is not encryption
or access control.

## Provenance

Recorded information about where an object came from and which exact earlier
objects it depends on.

## Role

A proposed or approved list of allowed and forbidden action tokens.

## Task chain

Append-only events linked by sequence and previous-event digest.

## Workspace

An optional Stable local directory that separates control, sources,
chapters, tasks, playbooks, roles, derived text, and replaceable indexes. It is
not required for a core context package.

[Documentation home](README.md)
