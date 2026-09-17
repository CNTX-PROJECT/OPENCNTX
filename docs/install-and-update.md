# Install and update OPENCNTX 1.8.5

[Project home](../README.md) · [Documentation](README.md) · [Release status](releases.md) · [Troubleshooting](troubleshooting.md)

Use the exact published wheel. Inspect an existing installation before updating; do not install a second copy over an unknown owner or custom wrapper. Python 3.11–3.14 is the source compatibility range. The original 1.8.5 artifact checks ran on Ubuntu/Python 3.12; see [platform evidence](platforms.md).

## 1. Acquire and inspect

The following PowerShell commands download the regular artifact, not the older same-version preview:

```powershell
$ErrorActionPreference = 'Stop'
$release = 'https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v1.8.5'
$wheel = 'opencntx-1.8.5-py3-none-any.whl'
$expected = '83f653461d8718a73451bce8769177b166b06f045eb49cd59fc9edebb16cb5ce'
Invoke-WebRequest "$release/$wheel" -OutFile $wheel
Invoke-WebRequest "$release/SHA256SUMS" -OutFile SHA256SUMS
Invoke-WebRequest "$release/BUILD-RECORD.json" -OutFile BUILD-RECORD.json
$actual = (Get-FileHash $wheel -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'OPENCNTX wheel checksum mismatch' }
pipx run --spec ".\$wheel" opencntx-install status
if ($LASTEXITCODE -ne 0) { throw 'Installation inspection failed' }
```

Inspect the executable, interpreter, owner and pending journals. `DIAGNOSIS_ONLY` is not permission to replace that installation. Pass repeatable `--project` arguments when checking project roots.

## 2. Update an existing managed 1.8.4 installation

Stage the exact previous wheel for offline rollback before activation:

```powershell
$oldWheel = 'opencntx-1.8.4-py3-none-any.whl'
$oldHash = 'b3fe658c5071b17e1835be65cc10df3c025dd03677c1be45c9b8aeb977d011d9'
Invoke-WebRequest "https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v1.8.4/$oldWheel" -OutFile $oldWheel
if ((Get-FileHash $oldWheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $oldHash) {
    throw 'Rollback wheel checksum mismatch'
}
pipx run --spec ".\$wheel" opencntx-install update `
  --artifact ".\$wheel" --sha256 $expected --version 1.8.5 `
  --rollback-artifact ".\$oldWheel" --rollback-sha256 $oldHash
if ($LASTEXITCODE -ne 0) { throw 'Managed update failed; inspect recovery status' }
opencntx --version
if ($LASTEXITCODE -ne 0) { throw 'Version readback failed' }
opencntx-install status
if ($LASTEXITCODE -ne 0) { throw 'Post-update inspection failed' }
```

The expected version is `opencntx 1.8.5`. The earlier preview used the same version string but different bytes; a preview installation requires explicit same-version artifact replacement and its exact active wheel as rollback input, not an assumed 1.8.4 rollback identity.

The installer retains the previous wheel and checks activation. This does not authorize rewriting human-owned documents or migrating project structure.

## 3. Dedicated virtual environment

Select the inspected interpreter explicitly:

```powershell
pipx run --spec ".\$wheel" opencntx-install `
  --python 'C:\path\to\venv\Scripts\python.exe' update `
  --artifact ".\$wheel" --sha256 $expected --version 1.8.5 `
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
pipx run --spec .\opencntx-1.8.5-py3-none-any.whl opencntx-install resume
```

Inspect `NEW_HEALTHY`, `OLD_RESTORED` or `RECOVERY_REQUIRED`. A journal or matching hash alone does not prove healthy activation. Package rollback and project-data restoration remain separate.

## 6. Check the new command

```text
opencntx knowledge index build --root "PROJECT_PATH"
opencntx preview-search "your query" --root "PROJECT_PATH" --compact --delivery-report
```

The ordinary search command remains available. This does not activate a chat host or execute the remaining development roadmap.
