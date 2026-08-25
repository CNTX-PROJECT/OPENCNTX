# Platforms and CI

[Start here](start-here.md) · [How it works](how-it-works.md) · [Advanced / Alpha workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All docs](README.md)

OPENCNTX requires Python 3.11 or newer and has no runtime dependencies.

Fixed CLI text is ASCII-safe English. User content and paths remain UTF-8.
Windows `cp1252` and UTF-8 console routes are tested so an unsupported display
character is escaped safely instead of raising `UnicodeEncodeError`; stored
source and artifact bytes are never changed by that display fallback.

## Supported Python versions

- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14

## Fully tested operating systems

- Windows
- Ubuntu Linux

The code may work elsewhere, but the project does not claim live CI proof for
an operating system outside this matrix.

New integrity directories use owner-private mode `0700` on POSIX. On Windows,
they inherit the parent directory's ACL so the same local project remains
usable across normal launch contexts. That inheritance is not an owner-only
guarantee: inspect and protect the parent directory with operating-system
controls appropriate to the data.

## Active CI matrix

Status label: `CI_ACTIVE`

Every pull request and push to `main` runs eight jobs:

| Operating system | Python 3.11 | Python 3.12 | Python 3.13 | Python 3.14 |
|---|:---:|:---:|:---:|:---:|
| Ubuntu | yes | yes | yes | yes |
| Windows | yes | yes | yes | yes |

Each job:

1. checks out the exact commit;
2. sets up the selected Python version;
3. installs the pinned `build==1.3.0` and `setuptools==83.0.0` build toolchain;
4. runs the complete test suite with `ResourceWarning` treated as an error;
5. exports the exact clean Git tree twice and builds one wheel and one sdist
   from each independent source directory;
6. requires byte-identical wheels and content-identical sdists, while reporting
   raw sdist byte identity separately;
7. verifies metadata, safe archive paths, SHA-256 checksums, and the unsigned
   build record;
8. installs, exercises, and uninstalls both selected artifacts outside the
   checkout.

The eight job names are the operating-system and Python-version pairs. CI does not upload the
temporary candidates or publish them to a release or package index.

## What counts as proof

Only a completed successful live run on the exact candidate or main commit is
green CI evidence. A workflow file, local run, or empty check list is not live
CI proof.

The live `main` ruleset is a separate repository setting. Expanding its required
checks is not performed by this source change and needs its own approval after
integration. The candidate is green only when all eight jobs on its exact commit
are successful.

Workspace transactions flush file bytes and then request a parent-directory
flush. Ubuntu uses a directory file descriptor and `fsync`; Windows uses a
directory handle and `FlushFileBuffers`. The transaction evidence records
`SYNCED`, `UNSUPPORTED`, or `FAILED`. This supports tested process-crash
recovery; it is not a promise against power loss, kernel, controller, hardware,
network-share, or distributed-filesystem failure.

## Run tests locally

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
python -W error::ResourceWarning -m unittest discover -s tests
python tools/render_brand.py --check
```

Ubuntu:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python3 tools/render_brand.py --check
```

## Related pages

- [Start here](start-here.md)
- [Troubleshooting](troubleshooting.md)
- [Release artifacts](release-artifacts.md)
- [Contracts and compatibility](contracts-and-compatibility.md)
- [Public roadmap](roadmap.md)
- [Contribution guide](../CONTRIBUTING.md)

[Documentation home](README.md)
