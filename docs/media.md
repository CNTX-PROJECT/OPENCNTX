# Media and derived text

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

> **Stable and optional:** derived-media registration belongs to the workspace
> route and is not part of the beginner core flow.

OPENCNTX does not perform OCR, transcription, image analysis, document
parsing, or video processing. It can safely register UTF-8 text that was
already produced elsewhere from a captured source.

## Why the separation matters

An original file and a derived description are different evidence. The
workspace keeps them separate so a transcript or OCR result cannot silently
replace the original.

## Register supplied derived text

```powershell
opencntx workspace media register SRC-EXAMPLE-0001 `
  --text transcript.txt `
  --root my-project `
  --kind TRANSCRIPT `
  --producer-class HUMAN `
  --producer "Named reviewer"
```

The command accepts one existing regular UTF-8 text file. It records the source
ID, original source digest, source-record digest, derived content digest,
producer metadata, and inherited privacy label.

## Review states

| State | Meaning |
|---|---|
| `NOT_INVESTIGATED` | No derived text is known |
| `UNREVIEWED` | Text is registered but not reviewed |
| `REVIEWED` | A reviewer accepted the exact bytes as usable |
| `REJECTED` | The exact text must not be promoted |
| `STALE` | The source or recorded relation changed |
| `REMOVED` | Active derived bytes were explicitly removed |

`REVIEWED` does not mean true, complete, safe, or OWNER-approved.

## Promote reviewed text

Promotion requires the exact accepted review digest. It reuses the normal
capture flow and creates a new text source with inherited privacy and explicit
provenance.

The promoted source is still only `CAPTURED`. It is not automatically added to
a chapter, task, or context package.

## Remove active derived bytes

Removal is an explicit destructive operation bound to the exact source,
derivation, record, and content digests plus a local OWNER statement. A small
tombstone remains. The original source and already promoted sources are not
deleted.

Never automate removal through a watcher.

## Related pages

- [Workspace](workspace.md)
- [Security](security.md)
- [Command reference](commands.md)
- [Glossary](glossary.md)

[Documentation home](README.md)
