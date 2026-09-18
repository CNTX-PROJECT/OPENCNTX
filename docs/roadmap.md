# Current work

[Project home](../README.md) · [Documentation](README.md) · [Published release](releases.md) · [History](history.md)

## Orientation

Current published release: **v1.8.6**. It hardens local scans and prevents index outputs from replacing source files, other indexes or protected managed data. The release retains the existing OCX v1 formats and does not complete the remaining product roadmap.

This page is the current development overview. Historical task lists are records, not active instructions. It does not authorize changes to private project files or installed runtimes.

## Delivered product

The regular 1.8.6 package and immutable artifacts are published. Fail-closed scans and output-collision protections are implemented; earlier compact search remains available. See [release status](releases.md) for artifact identities and qualification evidence.

## Repository maintenance

The 1.8.5 publication-maintenance work aligned public entry points, separated historical navigation and added publication/link checks. Its exact outcomes and preservation boundaries are recorded in [repository maintenance](repository-maintenance.md); the current release has its own scope and CI evidence.

## Remaining product work

| Priority | Outcome | Required evidence |
|---|---|---|
| 1 | Reduce measured no-op work without weakening path checks. | Fresh baseline/candidate measurements and race/negative tests. |
| 2 | Deliver the relevant passage, including diacritic matches. | Required text present inside bounded output, not only a matching filename. |
| 3 | Report missing mandatory context instead of false readiness. | Multi-source, long-task and insufficient-budget cases. |
| 4 | Improve visual and footer integration without breaking old consumers. | Explicit versioned contracts, preserved rollback and product-route tests. |

These are future implementation tasks, not missing publication checkboxes. Preserve and classify any unpublished local development before porting it. Do not reinstall a working runtime to hide a development mismatch.

## Outside the published scope

Automatic native chat hooks, universal live-host qualification and general provider-token savings are not established by this release.

## Historical planning

[History and maintenance](history.md) contains earlier release roadmaps and the historical reliability plan. Their original checks and measurements remain unchanged. New publication is not permission to mark old work retrospectively complete.
