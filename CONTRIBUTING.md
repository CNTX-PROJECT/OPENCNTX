# Contributing to OPENCNTX

[Project overview](README.md) · [Documentation](docs/README.md) · [Support](SUPPORT.md) · [Security](SECURITY.md) · [Code of Conduct](CODE_OF_CONDUCT.md)

Thank you for helping improve a small, local, provider-neutral context tool.
The best contribution solves one clear problem, includes proof, and leaves
unrelated behavior untouched.

## Before you start

1. Read the [documentation home](docs/README.md) and [Security Policy](SECURITY.md).
2. Use [SUPPORT.md](SUPPORT.md) for questions and installation help.
3. Search existing issues before opening a new one.
4. Report possible vulnerabilities privately, never in a public issue.
5. Keep one pull request focused on one bounded problem.

| If you want to… | Start here |
|---|---|
| ask how something works | [Support](SUPPORT.md) |
| report a normal defect | the public bug form, with a small safe reproduction |
| suggest a change | the feature form, explaining the user problem first |
| report a vulnerability | GitHub's private **Report a vulnerability** route |
| change a public contract | describe compatibility and migration effects clearly |

## Local checks

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
python -W error::ResourceWarning -m unittest discover -s tests
python -m pip install --disable-pip-version-check -r requirements-quality.txt
python -m coverage run --branch --source=opencntx -m unittest discover -s tests
python -m coverage json -o coverage.json
python tools/quality_gate.py all --coverage-report coverage.json
python tools/render_brand.py --check
python -m pip install --disable-pip-version-check build==1.3.0 setuptools==83.0.0
$commit = git rev-parse HEAD
$tree = git rev-parse 'HEAD^{tree}'
python tools/release_artifacts.py build --repository . --output dist --expected-commit $commit --expected-tree $tree
```

The complete suite must remain green. Explain the actual commands and
platforms you used; zero automated checks is not green evidence. The candidate
build requires a clean worktree and an absent or empty `dist` directory. It
creates local unpublished files only. Read [Release artifacts](docs/release-artifacts.md)
before making any reproducibility or provenance claim.

The pinned quality packages are development tools only. The quality route
checks behavior goldens, bounded properties, lint/format ratchets, a selected
type boundary, branch coverage, and package hygiene. It is not a vulnerability
scan, security audit, privacy proof, or penetration test.

## Brand changes

Edit only an official source inside the approved scope and review it visually.
Then regenerate the shape-only PNG derivatives and refresh the manifest:

```powershell
python tools/render_brand.py --write
python tools/render_brand.py --check
```

The standard-font social preview PNG is a separately reviewed export because
system fonts can rasterize differently on Windows and Ubuntu. Replace it only
with explicitly reviewed bytes, then run `--write` to pin its new hash. Do not
edit generated avatar/icon PNGs or `SHA256SUMS` by hand.

## Pull request boundaries

- List every changed path and the user impact.
- Keep unrelated formatting or cleanup out of the same request.
- Add or update tests for changed behavior or quality contracts.
- Preserve local-first, explicit, model-neutral, fail-closed behavior.
- Do not add a dependency without a clear need and separate review.
- Never include secrets, personal data, private project material, or local
  private paths.
- Update documentation and the changelog when the public surface changes.

By contributing, you agree that your contribution is licensed under the
existing [Apache-2.0 License](LICENSE).
