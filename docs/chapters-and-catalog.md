# Chapters and catalog

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

> **Stable and optional:** chapters and the local catalog help longer projects.
> You do not need them for a first core context package.

Chapters turn captured sources into small reviewed knowledge units. The local
catalog makes those units easy to find without replacing their official files.

## Create a draft chapter

Use the exact source ID returned by capture. The workspace resolves and pins
the stored source and record digests itself:

```powershell
opencntx workspace chapter create CH-PROJECT-OVERVIEW `
  --root my-project `
  --title "Project overview" `
  --scope "One bounded project overview" `
  --source SRC-EXAMPLE-0001
```

This creates a new `DRAFT` chapter template. It never overwrites an existing
chapter.

## Chapter revisions

Each official revision records:

- chapter ID and revision number;
- title and status;
- exact source pins;
- optional chapter dependencies;
- fixed Markdown sections;
- a digest of the complete official bytes.

Changing accepted content creates a new revision. Do not edit history as if it
never existed.

## Freshness states

| State | Technical meaning |
|---|---|
| `CURRENT` | Recorded source and dependency pins still match |
| `STALE` | A concrete source or dependency changed or disappeared |
| `INCOMPLETE` | The chapter is draft or a relation cannot be confirmed |
| `ARCHIVED` | The chapter is intentionally historical |

Freshness is technical evidence. It does not prove that a summary is true.

## Rebuild the catalog

```powershell
opencntx workspace catalog rebuild --root my-project
```

The command validates official source and chapter files, rejects unsafe paths
or dependency cycles, and rebuilds:

- `.opencntx/catalog.sqlite`;
- `CHAPTERS/INDEX.md`.

The SQLite database is derived and replaceable. Official source records and
chapter files remain authoritative.

## Why chapters help context size

A task can pin an accepted chapter instead of loading all project history. The
navigator then follows only the chapter's explicit current dependencies and
sources.

## Related pages

- [Workspace](workspace.md)
- [Context navigation](context-navigation.md)
- [OWNER flow](owner-flow.md)
- [Glossary](glossary.md)

[Documentation home](README.md)
