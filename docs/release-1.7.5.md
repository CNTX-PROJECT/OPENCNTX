# OPENCNTX 1.7.5 — engine and visual release candidate

[Overview](../README.md) · [Get started](start-here.md) · [Releases](releases.md) · [Roadmap](roadmap.md)

This page is the bounded release scope for the local `1.7.5` candidate. The
candidate keeps the public 1.7.4 release untouched until the exact commit,
artifacts, CI result, tag and GitHub Release have all been verified.

## Engine roadmap outcome

The [engine roadmap, issue #225](https://github.com/CNTX-PROJECT/OPENCNTX/issues/225)
is implemented in the candidate through these additive contracts:

- deterministic `SHORT`, `MEDIUM`, `LARGE` and `MEGA` task recipes with stable
  method steps;
- byte-budgeted context planning that reports loaded, verified referenced and
  genuinely omitted bytes, and never treats an unavailable digest as loaded;
- explicit `WAIT_FOR_SAFE_ACTION` when no safe action is ready, so a planning
  result cannot silently authorize a technical mutation;
- durable rollback intent and archived receipts so an interrupted update can be
  resumed without repeating a completed transition;
- `opencntx flow legacy-stage`, which copies a portable-v1 store to a new
  destination under writer exclusion without deleting source locks or changing
  the active runtime.

The isolated writer matrix exercised the actual 1.6.0, 1.6.1, 1.6.2 and 1.6.3
source trees. Each wrote a checkpoint on its staged copy. This is a qualified
compatibility route, not an in-place downgrade and not permission to disable
security controls. Newer storage envelopes require their retained compatible
snapshot.

## Visual roadmap outcome

The [visual roadmap, issue #226](https://github.com/CNTX-PROJECT/OPENCNTX/issues/226)
is represented by the responsive English site and documentation tour:

- one clear logo-led entry point with no duplicate product heading;
- diagrams for local canonical storage, optional private GitHub backup and a
  readable notes-app view;
- small, medium, large and mega work shown as one master roadmap with focused
  child outcomes;
- accessible semantic HTML, dark mode, reduced-motion and forced-colour modes,
  zero JavaScript and zero remote runtime requests;
- desktop and narrow viewport renders checked for overflow, broken assets and
  text clipping.

The illustrations are explanatory documentation, not a claim that OPENCNTX
ships an Obsidian clone or automatically configures GitHub synchronization.

## Compatibility and boundaries

Existing v1 durable reads, the public CLI and the v1.7.4 installation route are
preserved. The new route is additive and fail-closed. It does not erase old
projects, bypass OS permissions, unlock a live writer, run an AI, or promise a
universal host integration. Optional GitHub and notes-app integrations remain
explicit owner-controlled steps.

## Candidate verification

The release gate binds package version, current-version surfaces, exact source
tree and four assets. CI covers Windows and Ubuntu on Python 3.11–3.14. The
release is not considered published until the immutable `v1.7.5` tag and its
wheel, sdist, `SHA256SUMS` and `BUILD-RECORD.json` are readable from GitHub.

## After publication

Install the exact tag with:

```powershell
pipx install "git+https://github.com/CNTX-PROJECT/OPENCNTX.git@v1.7.5"
opencntx --version
```

The command must print `opencntx 1.7.5`. A source branch, local candidate or
green CI run alone is not a published release.

[Release artifacts](release-artifacts.md) · [Legacy recovery guide](legacy-recovery.md) · [Visual tour](visual-tour.md)
