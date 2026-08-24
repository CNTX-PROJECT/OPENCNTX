# Changelog

All notable OPENCNTX changes are recorded here.

## Unreleased

### Added

- Added a machine-readable contract catalog for all 1,575 accepted public
  surfaces and explicit field, type, relationship, and major-version contracts
  for all 36 durable formats.
- Added immutable synthetic v0.3.0 compatibility fixtures and fail-closed tests
  for unknown format majors without changing the recorded input bytes.
- Expanded the Windows and Ubuntu candidate CI matrix to Python 3.11 through
  3.14, for eight exact jobs in total.
- Added a closed eight-family writer register, 25 deterministic contention
  rounds per family and operating system, and phase-indexed crash/recovery
  evidence in both Python 3.14 platform jobs.
- Added a pinned development-only static security and dependency audit,
  complete Ruff finding dispositions, and full-package type checking.
- Added a hash-bound v0.3.0 wheel upgrade, verification, smoke, and uninstall
  proof that preserves existing local user data without publishing artifacts.

### Changed

- Replaced the broad operating-system-independent package claim with the two
  operating-system families actually covered by live CI: Windows and Linux.
- Reduced the candidate Ruff ratchet to zero findings while preserving narrow,
  machine-registered technical exceptions for fixed trusted local tooling.

## 0.3.0 - 2026-08-20

### Added

- Added `opencntx --version` from the existing single package-version source.
- Added the safe `.opencntx/latest` default for `opencntx verify`, while
  preserving explicit package paths and existing exit-code meanings.
- Added Windows `cp1252` and UTF-8 terminal tests, Unicode-path coverage, and
  exact read-only compatibility checks for known Dutch v0.2.0 artifacts.
- Added `opencntx pack --preview` as a read-only view of included, required,
  excluded, and ignored paths, file and byte budgets, and safe secret-policy
  findings.
- Added a dependency-free local secret-signal policy that blocks narrow
  high-confidence credential structures before publication and warns on
  broader credential-like text.
- Added exact source-bound `--allow-secret` overrides with safe additive
  evidence in version-1 manifests, while retaining support for existing
  manifests without security metadata.
- Added a dependency-free release-candidate verifier for safe wheel/sdist
  metadata, SHA-256 checksums, an unsigned build record, and honest independent
  rebuild comparisons.
- Added isolated wheel and sdist install, core smoke, and uninstall proof to all
  six existing Windows/Ubuntu and Python 3.11/3.12/3.13 CI jobs.
- Added one exact-tag `pipx` install route and bounded release-artifact guidance
  without claiming PyPI publication or new release assets.
- Added local workspace and task writer locks, exact compare-and-swap checks,
  durable transaction journals, and real spawn-process conflict tests.
- Added read-only `workspace doctor` diagnosis and exact intent-bound,
  backup-first `workspace recover` preview/apply handling for interrupted work.
- Added shared symlink, Windows reparse/junction, containment, file-flush, and
  parent-directory-flush primitives without claiming hardware power-loss proof.
- Added objective failed-attempt evidence bound to the exact executor package,
  context manifest, allowed action, relevant input digests, and local result
  evidence.
- Added deterministic semantic fingerprints, digest-backed new-basis proof,
  and fixed task-wide attempt, action, and duration limits without adding an
  automatic retry controller.
- Added read-only lifecycle status for observed local permissions, privacy-safe
  source aliases, storage categories, and packaged format compatibility.
- Added owner-private creation defaults and physical disk-space preflights for
  bounded workspace, package, media, migration, cleanup, and restore writes.
- Added unchanged version-1 lifecycle registration plus explicit allowlisted
  cleanup with digest-bound plans, verified external checkpoints, exact
  restore, concurrency checks, and rollback on injected failure.

### Changed

- Split the stable CLI facade into six internal command families, decomposed
  the four functions that exceeded 180 lines, and centralized only
  byte-equivalent time, JSON, SHA-256, and write primitives without changing
  public commands, outputs, formats, error codes, or runtime dependencies.
- Added exact CLI goldens, deterministic path/pattern/manifest properties, a
  pinned development-only Ruff/Mypy/coverage/Hypothesis toolchain, and bounded
  quality ratchets inside the existing six CI jobs. These are lightweight
  static and package-hygiene checks, not a security audit or penetration test.
- Replaced new free-text attempt signatures and new-basis claims with a closed,
  controller-derived evidence contract while keeping historical text-attempt
  records read-only verifiable.

- Made fixed CLI help, errors, warnings, results, templates, and generated
  headings consistently English and ASCII-safe while preserving UTF-8 user
  content and paths.
- Put the complete `init → preview → pack → inspect → verify` route first and
  labeled the optional workspace consistently as `Advanced / Alpha`.
- Combined installation and first use into one ordered `Start here` guide.
- Put the six most-used documentation routes in one fixed order on every
  guide and simplified the README into a calm landing page.
- Replaced hand-built wordmark letters with centered standard sans-serif text
  and one symmetric context-frame avatar symbol.
- Added matching light- and dark-screen variants for all seven documentation
  diagrams, with equal cards, margins, spacing, baselines, and arrow anchors.
- Clarified the exact, dependency-free boundary between deterministic
  shape-only PNGs and the hash-pinned standard-font social preview export.
- Corrected six public command examples so the real parser accepts every
  published PowerShell and Bash `opencntx` invocation.
- Made the command reference follow all 38 executable parser routes and added
  automated parser checks for the reference and shell examples.
- Aligned the public `v0.2.0` wording with the package's Alpha classifier and
  removed the duplicated literal release version from the CI smoke test.
- Expanded pre-read defaults for known local credential, SSH identity, package
  registry, Docker, AWS, and application-default credential paths.
- Routed official workspace writers through the shared local integrity layer
  while preserving existing domain formats, OWNER gates, and read-only legacy
  verification.

### Fixed

- Kept POSIX integrity directories owner-private while allowing new Windows
  integrity directories to inherit the usable parent ACL, avoiding a protected
  `0o700` DACL that can lock out a later local launch context.
- Converted inaccessible transaction-state paths into one stable fail-closed
  CLI error without a Python traceback, and made byte-budget failures report
  the exact required and allowed byte counts.

The package remains Alpha with no runtime dependency or product network-boundary
change. Distribution is limited to an exact Git tag and GitHub Release with the
verified release assets; there is no PyPI or TestPyPI publication. CI uses pinned
build- and quality-only toolchains and compares artifact and installed metadata
with the single package version instead of duplicating that version in the
workflow.

## 0.2.0 - 2026-08-18

### Added

- A local workspace storage foundation that records supplied files byte-for-
  byte with privacy label, origin, SHA-256, and receipt.
- Immutable chapter revisions and a fully rebuildable local catalog for
  sources, dependencies, freshness, and `CURRENT` state.
- Append-only task records with separate exact OWNER approval for proposal and
  result, closure only after acceptance, and a bounded anti-deadloop stop.
- A deterministic task-bound context navigator that follows only explicitly
  pinned control, task, chapter, playbook, role, and source relationships.
- An automatic compact control snapshot from one exactly marked current
  roadmap block while retaining the full roadmap digest.
- Safe registration, review, promotion, and removal of already supplied
  derived UTF-8 text without performing OCR, transcription, or AI processing.
- Proposed and exactly approved playbooks and roles, with at most one local
  executor package that does not start a person, process, tool, AI, or agent.
- Public documentation, community files, deterministic brand assets, and a
  bounded six-job CI matrix.

### Validated

- The release candidate passed exactly 159 tests on Windows and Ubuntu with
  `ResourceWarning` treated as an error.
- Six live CI matrix jobs are evidence only on the exact candidate or merge
  commit.
- A private practical test confirmed that task context remained small,
  findable, traceable, and useful, and that one deliberate failure stopped
  without retry or partial execution.

### Known limitations

- OPENCNTX performs no AI call, automatic summary, OCR, transcription,
  embedding, vector search, knowledge graph, agent start, or process execution.
- The control snapshot does not synchronize Obsidian, GitHub, or another
  external store and does not interpret the official roadmap.
- There is no cloud service, external database, watcher, GUI, MCP server, or
  PyPI publication.
- Live task context is verified while the task is `IN_EXECUTION`; after
  closure, the append-only chain, digests, result, evidence, and executor state
  form the historical completion proof.
- CI is `CI_ACTIVE` and bounded to Windows and Ubuntu with Python 3.11, 3.12,
  and 3.13. Only the live run on the exact commit counts as proof.

## 0.1.0 - 2026-08-16

The first public release of the local, provider-neutral OPENCNTX core.

### Added

- `opencntx init` for a small readable configuration template without
  overwriting an existing file.
- `opencntx pack` for deterministic selection and atomic publication of
  `CONTEXT.md` and `manifest.json`.
- `opencntx verify` for separate reporting of unchanged, changed, missing, and
  unexpected sources.
- Explicit include, required, and exclude patterns plus file and byte budgets.
- Relative source paths, byte sizes, and SHA-256 hashes in the manifest.
- Default exclusion of Git metadata, generated packages, environment paths,
  and common key files.
- Rejection of binary or unreadable input, path traversal, and symlink escape
  outside the project root.
- Local Windows and Ubuntu tests for the complete core flow.

### Known limitations

- Only local UTF-8 text files are supported.
- No PDF, Office, image, audio, or binary extraction.
- No automatic selection, summary, embedding, or ranking.
- No AI provider, agent, MCP server, GUI, cloud service, database, or hosting.
- The user must inspect the generated context package before sharing it.
