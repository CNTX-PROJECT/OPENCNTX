# Install and update OPENCNTX 1.8.6

[Project home](../README.md) · [Documentation](README.md) · [Release status](releases.md) · [Troubleshooting](troubleshooting.md)

Use the exact published wheel. Inspect an existing installation before updating; do not install a second copy over an unknown owner or custom wrapper. Python 3.11–3.14 is the source compatibility range. The v1.8.6 source and packaging matrix passed on Windows and Ubuntu; managed updates from exact v1.8.4 and v1.8.5 wheels were tested on both systems with Python 3.12. See [platform evidence](platforms.md) and the [v1.8.6 release record](release-1.8.6.md).

## 1. Acquire and inspect

The following PowerShell commands download and verify the regular v1.8.6 artifact:

```powershell
$ErrorActionPreference = 'Stop'
$release = 'https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v1.8.6'
$wheel = 'opencntx-1.8.6-py3-none-any.whl'
$expected = '47c96b399373a6ac7f16f3af9bff92a2546a8749376c88cced2b0e8c86e61633'
Invoke-WebRequest "$release/$wheel" -OutFile $wheel
Invoke-WebRequest "$release/SHA256SUMS" -OutFile SHA256SUMS
Invoke-WebRequest "$release/BUILD-RECORD.json" -OutFile BUILD-RECORD.json
$actual = (Get-FileHash $wheel -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'OPENCNTX wheel checksum mismatch' }
pipx run --spec ".\$wheel" opencntx-install status
if ($LASTEXITCODE -ne 0) { throw 'Installation inspection failed' }
```

Inspect the executable, interpreter, owner and pending journals. `DIAGNOSIS_ONLY` is not permission to replace that installation. Pass repeatable `--project` arguments when checking project roots.

## 2. Update an existing managed 1.8.5 installation

Stage the exact previous wheel for offline rollback before activation:

```powershell
$oldWheel = 'opencntx-1.8.5-py3-none-any.whl'
$oldHash = '83f653461d8718a73451bce8769177b166b06f045eb49cd59fc9edebb16cb5ce'
Invoke-WebRequest "https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v1.8.5/$oldWheel" -OutFile $oldWheel
if ((Get-FileHash $oldWheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $oldHash) {
    throw 'Rollback wheel checksum mismatch'
}
pipx run --spec ".\$wheel" opencntx-install update `
  --artifact ".\$wheel" --sha256 $expected --version 1.8.6 `
  --rollback-artifact ".\$oldWheel" --rollback-sha256 $oldHash
if ($LASTEXITCODE -ne 0) { throw 'Managed update failed; inspect recovery status' }
opencntx --version
if ($LASTEXITCODE -ne 0) { throw 'Version readback failed' }
opencntx-install status
if ($LASTEXITCODE -ne 0) { throw 'Post-update inspection failed' }
```

The expected version is `opencntx 1.8.6`. This example stages the exact v1.8.5 wheel as rollback. Direct updates from v1.8.4 were also tested; when updating from that version, use its exact published wheel and SHA-256 as the rollback input. A historical v1.8.5 preview had different bytes from the regular v1.8.5 release, so identify an existing installation by its artifact hash, not just its version string.

The installer retains the previous wheel and checks activation. This does not authorize rewriting human-owned documents or migrating project structure.

## 3. Dedicated virtual environment

Select the inspected interpreter explicitly:

```powershell
pipx run --spec ".\$wheel" opencntx-install `
  --python 'C:\path\to\venv\Scripts\python.exe' update `
  --artifact ".\$wheel" --sha256 $expected --version 1.8.6 `
  --rollback-artifact ".\$oldWheel" --rollback-sha256 $oldHash
```

On Linux use the environment's `bin/python`. Do not infer package ownership only from a directory name.

## 4. New installation

Only after inspection confirms there is no installation to preserve:

```powershell
pipx install ".\$wheel"
if ($LASTEXITCODE -ne 0) { throw 'Installation failed' }
opencntx --version
opencntx-install status
```

Then follow [Start here](start-here.md) or [Core commands](core.md).

## 5. Interrupted update

From a fresh shell, use the independent manager from the verified wheel:

```powershell
pipx run --spec .\opencntx-1.8.6-py3-none-any.whl opencntx-install resume
```

Inspect `NEW_HEALTHY`, `OLD_RESTORED` or `RECOVERY_REQUIRED`. A journal or matching hash alone does not prove healthy activation. Package rollback and project-data restoration remain separate.

## 6. Check the new command

```text
opencntx knowledge index build --root "PROJECT_PATH"
opencntx preview-search "your query" --root "PROJECT_PATH" --compact --delivery-report
```

The ordinary search command remains available. This does not activate a chat host or execute the remaining development roadmap.
