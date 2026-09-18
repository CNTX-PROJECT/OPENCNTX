# Frequently asked questions

> Current download: **v1.8.6**. The release passed the full Windows/Ubuntu source and packaging matrix for Python 3.11–3.14 and managed update checks from v1.8.4 and v1.8.5 on Python 3.12. Native chat-host integration is outside the release scope.


[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

## Does OPENCNTX contain an AI model?

No. It selects, stores, packages, and verifies local files. It does not call an
AI service.

## What does “Any model” mean?

The output is ordinary text and JSON. You may provide reviewed output to any AI
tool that accepts that input. OPENCNTX does not guarantee every interface or
recommend a provider.

## Is OPENCNTX only for experienced developers?

No. New users can follow the short core route. Longer projects can use the
Stable workspace, tasks, playbooks, and roles. Those tools are optional, so you
can learn them only when you need them.

## What language does the CLI use?

Fixed help, errors, warnings, results, templates, and generated headings use
English. User content and paths remain UTF-8. Narrow Windows consoles escape
an unsupported display character instead of changing stored bytes or crashing.

## What does `opencntx verify` check without a path?

It checks exactly `.opencntx/latest` under the current directory. It does not
search parent directories. Supply `opencntx verify PATH` for an explicit path.

## Does it upload my files?

No. OPENCNTX has no network functionality. You decide if and where output is
shared.

## Does a hash make content safe?

No. A hash reveals changed bytes. It does not prove truth, safety, quality,
ownership, or approval.

## Are privacy labels encryption?

No. They are local classifications. Use operating-system permissions and
appropriate storage protection.

## Does a safe permission result make the workspace secure?

No. It reports owner-only access observed through POSIX mode bits or a Windows
ACL at that moment. It is not encryption, authentication, backup protection, or
a guarantee against administrators and later changes.

## Does OPENCNTX clean old files automatically?

No. Cleanup accepts only a fixed named allowlist, an exact reviewed plan and
digest, and a verified checkpoint outside the workspace. Age and storage
pressure never authorize deletion.

## Does lifecycle migration rewrite my existing records?

No. The supported migration registers unchanged compatible version-1 records
in a sidecar. Unknown future formats stop instead of being guessed or
downgraded.

## Can it read PDF, Office, image, audio, or video files?

The core accepts UTF-8 text. The media layer can register derived UTF-8 text
that was already created elsewhere, but OPENCNTX performs no extraction, OCR,
or transcription.

## Does it automatically find the best context?

Core selection still uses your patterns. The optional 1.8.5 knowledge layer
adds deterministic FTS5 search over an explicit local index; it searches source
bodies, identifiers and JSON paths and reports why each result matched, its
freshness and whether a bounded snippet was loaded, referenced or skipped.
There are no embeddings, ranking model or vector database, and a search result
never grants authority.

## Can one project have nested Markdown files?

Yes. `opencntx knowledge index build` records a main file, child files and
sub-child files as one digest-bound hierarchy. It does not silently move or
rename those files. See the [knowledge layer guide](knowledge-layer.md).

## Does OPENCNTX remember a technique I already proved?

Yes, when you store an evidence-bound technique card. It records the trigger,
preconditions, steps, tools, risks, outputs and source digests. `PROVEN` means
the procedure has evidence; it never means that OPENCNTX will execute it.

## Can it run an agent or executor?

No. An executor package records a bounded assignment and actions. It does not
start a person, process, tool, model, or agent.

## Why can one task be active at a time?

The bounded design keeps current authority, context, evidence, and failure
state unambiguous.

## Why are there separate OWNER approvals?

Proposal approval and result acceptance are different decisions. Keeping them
separate prevents the tool or executor from approving its own work.

## Is OPENCNTX on PyPI?

No. OPENCNTX is not published on PyPI. The current regular v1.8.6 release is
available from its GitHub Release wheel. Its qualification and boundaries are
described in the [release record](release-1.8.6.md). See
[Install and update](install-and-update.md) to verify the checksum before you
choose to install it.
A current 404 response from a package index is not proof that a name is owned
or reserved.

## Are wheel or sdist release assets available?

The immutable `v1.8.6` Release has
exactly `opencntx-1.8.6-py3-none-any.whl`,
`opencntx-1.8.6.tar.gz`, `SHA256SUMS`, and `BUILD-RECORD.json`. Locally built
files remain verification builds unless they match an attached Release
asset. See
[Release artifacts](release-artifacts.md) for
checksums, build records, reproducibility limits, and the separate publication
gate.

## Where should I start?

For completed and planned work, read the [roadmap overview](roadmap.md),
[1.8.6 release scope](release-1.8.6.md), [1.8.5 release scope](release-1.8.5.md),
and [1.8.1 release scope](release-1.8.1.md).

Use [Start here](start-here.md) for installation and your first package.

[Documentation home](README.md)
