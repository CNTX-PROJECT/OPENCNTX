# Security Policy

## Choose the correct route

- **Possible vulnerability:** use GitHub's private **Report a vulnerability**
  route under the Security tab.
- **Question, installation problem, or ordinary bug:** use [SUPPORT.md](SUPPORT.md)
  or the appropriate issue form.
- Never put passwords, tokens, personal data, sensitive context, private source
  code, or non-public project files in a public issue.

This document is the canonical technical security boundary for OPENCNTX.

A hash makes changed bytes visible. It does not prove that content is true,
complete, safe, or approved by an OWNER.

## Core context packages

OPENCNTX processes local project files. Always review selected paths and read
`CONTEXT.md` before sharing a package because it may contain literal source
text.

The tool has no network functionality and requires no account or API key.
`pack` applies exclusions before reading source content, rejects binary or
unreadable input, and blocks path and symlink escape outside the project root.
Built-in sensitive exclusions remain active alongside user configuration.
They include common environment, key, local credential, SSH identity, package
registry, Docker, AWS, and application-default credential paths.

`pack --preview` runs the same selection, required-file, budget, UTF-8, and
secret-policy plan without creating or changing `.opencntx/`. Its output lists
paths, reasons, budgets, and safe finding metadata; it never prints matched
source text. A successful preview is information, not approval, and `pack`
always recalculates the plan from current bytes.

The dependency-free local scanner blocks a deliberately small set of
high-confidence credential structures before package publication and warns on
broader credential-like text. It has false positives and false negatives. It
does not prove that output is secret-free and does not replace inspection.

A high-confidence block can be overridden only with a current exact finding ID
from preview: `opencntx pack --allow-secret FINDING_ID_FROM_PREVIEW`. There is
no wildcard, directory, configuration, environment, or global scan bypass.
Each applied override is recorded as safe metadata in `manifest.json`; the
matched value and snippet are never recorded there.

Packages are written under `.opencntx/` by default. The supplied `.gitignore`
keeps that directory out of normal Git tracking. This does not prevent manual
copying or sharing. Treat `CONTEXT.md` and `manifest.json` as potentially
sensitive local output.

`verify` reads package and sources only for verification and must not modify a
source. A non-zero exit code means drift, incomplete proof, or invalid input;
do not ignore it before using the package.

## Optional workspace storage

`opencntx workspace capture` treats a supplied local file as untrusted bytes.
It does not execute the file, open an associated application, or extract its
content. Directories, symlinks, devices, missing files, and managed internal
paths are rejected.

New sources default to `PRIVATE`. A privacy label is a local classification,
not encryption or access control. Do not store passwords, tokens, API keys, or
other production secrets in a workspace. Protect the project directory and
backups separately.

The original file name is recorded as metadata, but the original absolute path
is not. Exact bytes are stored under an OPENCNTX source ID. SHA-256 and receipts
help with provenance and duplicate detection but do not prove safety or truth.

`CAPTURED` is reported only after the local copy, digest, and official record
exist. `DUPLICATE` points to an existing identical capture. `NOT_CAPTURED`
means the source was not accepted as official; resolve the error before
continuing.

The storage layer has no network, cloud, watcher, OCR, transcription, AI, or
agent function. Large files remain subject to hard local storage budgets and
are not automatically added to a context package.

## Media and derived text

`workspace media` starts no image, document, audio, video, OCR, transcription,
parser, AI, subprocess, network connection, or external service. `register`
accepts only one existing regular UTF-8 text file.

Kind, producer class, producer name, page, and time locators are user-supplied
metadata. OPENCNTX does not prove that they are correct.

Derived text stays under `.opencntx/derived/`, separate from the official
original. Its record binds source ID, original digest, source-record digest,
derived-content digest, and inherited privacy label.

- `QUARANTINED` sources are not processed.
- `RESTRICTED` remains `RESTRICTED`.
- No media command lowers a privacy label.
- Instructions inside derived text remain data and gain no task, roadmap, or
  OWNER authority.

`NOT_INVESTIGATED` means no derived text is known. `UNREVIEWED` is not yet
checked. `REVIEWED` means only that a reviewer found the exact bytes usable.
It does not mean true, complete, safe, or OWNER-approved. `REJECTED`, `STALE`,
and `REMOVED` content cannot be promoted.

Promotion requires an exact accepted review digest and reuses the normal
capture flow. The new source inherits privacy and exact provenance but remains
only `CAPTURED`; it is not automatically added to a chapter, task, or package.

Removal is an explicit destructive operation for one exact derived
`content.txt`. It requires source ID, derivation ID, record digest, content
digest, and a local OWNER declaration. The original, official source record,
other derivations, and promoted sources are not removed. A tombstone remains.

## Chapters and local catalog

`workspace chapter create` writes a new `DRAFT` template and does not overwrite
an existing chapter. Chapter status, digest, or freshness never grants OWNER
approval or proves a summary true.

`workspace catalog rebuild` treats TOML front matter and Markdown as untrusted
data. IDs, fields, relations, paths, and fixed sections are validated. SQL
values are parameterized; chapter text is never executed as SQL or instruction.

`.opencntx/catalog.sqlite` is derived and replaceable. Official source records
and chapter files remain controlling. The index stores technical metadata and
relations, not full original source bytes, embeddings, or vectors.

Freshness means only:

- `CURRENT`: source and dependency pins match;
- `STALE`: a concrete source or dependency changed, disappeared, or differs;
- `INCOMPLETE`: the knowledge is draft or a relation cannot be confirmed;
- `ARCHIVED`: the chapter is intentionally historical.

Dependency cycles, symlinks, path escape, unknown schemas, or an unsafe index
stop the rebuild. A manually divergent index is not silently overwritten.

## Task records and OWNER gates

`workspace task` stores official decision events as append-only JSON under
`TASKS/<TASK-ID>/events/`. Each event has its own SHA-256 and the previous event
digest. The complete chain is verified before every transition.

Modification, removal, insertion, renumbering, unknown fields, or a skipped
state fails closed.

Task approval binds the exact task ID, revision, and proposal digest. Result
acceptance binds the exact result and review digests. A changed input, wrong
object, old revision, or different digest never inherits an earlier approval.
`CLOSED` is possible only after the required result, review, and OWNER decision.

An OWNER name is a local declaration, not cryptographic authentication of a
natural person. Protect workspace write access.

Only one non-terminal task is allowed at a time. OPENCNTX performs no automatic
retry. One failed attempt records one stable signature. After three equal
signatures, the task becomes `BLOCKED` and requires a new human decision.

## Task-bound context navigation

The navigator follows only explicit, allowed relations. It has no embedding,
vector search, knowledge graph, semantic ranking, automatic discovery, AI
summary, or network service.

`context build` works only for one valid task in `IN_EXECUTION`. It checks the
task chain, current control state, catalog freshness, accepted chapters,
playbook and role pins, source privacy, path safety, and budgets before atomic
publication.

The compact control snapshot is derived from one exact supported marker block.
The full roadmap digest remains pinned. The snapshot does not edit, interpret,
approve, or synchronize the roadmap.

`context verify` is read-only and intended while the task remains
`IN_EXECUTION`. After closure, use the preserved append-only chain and exact
recorded digests as historical evidence.

## Playbooks, roles, and executor packages

Playbooks and roles are proposed first and approved only by exact revision and
definition digest. Their names and metadata do not start or authenticate a
person, process, tool, model, or agent.

Allowed actions are the intersection of task, playbook, and role. A conflict or
forbidden action stops fail closed. No one layer can override the forbidden
set of another.

`workspace executor prepare` works only for one valid task in `IN_EXECUTION`
with exact context, playbook, role, and task bindings. At most one executor
package exists per task revision. It contains assignment metadata but does not
copy full context bytes or start execution.

When the task leaves `IN_EXECUTION`, executor status reports `TASK_FINISHED`.
The package gains no continuing authority.

## Candidate hardening checks

The existing eight Windows/Linux and Python 3.11-3.14 CI jobs also enforce a
zero-finding Ruff ratchet and type-check every runtime module. A pinned
development-only `pip-audit` check covers the build and quality requirements;
it adds no runtime dependency and is not a penetration test or certification.

The Python 3.14 Windows and Linux jobs run 25 deterministic contention rounds
for each of eight registered writer families, phase-bound crash/recovery
fixtures, duplicate clean builds, and an offline upgrade from the exact
SHA-256-bound v0.3.0 release wheel. The upgrade test verifies existing local
data before and after upgrade and uninstall. It does not publish a package.

Directory flush reporting remains platform-specific. `VERIFIED` means only
that the operating-system call succeeded. `UNSUPPORTED` remains an explicit
limitation, especially on Windows, and is never presented as a power-loss or
hardware durability guarantee.

These checks bind bytes and observed behavior. They do not prove identity,
authorship, truth, encryption, access control, or future safety.

## Reporting a vulnerability

Do not report vulnerabilities in a public issue. Use GitHub's private
**Report a vulnerability** route under the Security tab. Include the smallest
safe reproduction, affected version, impact, and suggested mitigation without
including unrelated private context.
