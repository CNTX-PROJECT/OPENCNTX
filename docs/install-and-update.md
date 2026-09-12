# Install and update OPENCNTX 1.7.6

OPENCNTX 1.7.6 supports Python 3.11 through 3.14. The qualified persistent
installation routes are pipx and a dedicated pip virtual environment. A shared
Python, editable checkout, unknown package owner, synchronized state directory,
or custom wrapper is diagnosis-only until separately qualified.

## First inspect what already exists

Do not install a second copy over an unknown installation. Download the 1.7.6
wheel and `SHA256SUMS` from the [1.7.6 release], verify the published checksum,
and run the independent manager from that wheel:

```powershell
$release = "https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v1.7.6"
Invoke-WebRequest "$release/SHA256SUMS" -OutFile SHA256SUMS
Invoke-WebRequest "$release/opencntx-1.7.6-py3-none-any.whl" -OutFile opencntx-1.7.6-py3-none-any.whl
$expected = ((Get-Content SHA256SUMS | Where-Object { $_ -match 'opencntx-1.7.6-py3-none-any.whl$' }) -split '\s+')[0]
$actual = (Get-FileHash opencntx-1.7.6-py3-none-any.whl -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "OPENCNTX wheel checksum mismatch" }
pipx run --spec .\opencntx-1.7.6-py3-none-any.whl opencntx-install status
```

`status` is read-only. It reports the package owner, executable and interpreter,
project state supplied with repeatable `--project`, pending update journals,
storage boundary, ownership classes and the proposed write set. `DIAGNOSIS_ONLY`
means stop and reconcile that installation; it is not permission to replace it.

## Fresh pipx installation

After the checksum check above reports no existing installation:

```powershell
pipx install .\opencntx-1.7.6-py3-none-any.whl
opencntx --version
opencntx-install status
```

The expected version output is `opencntx 1.7.6`.

## Update a pipx installation from 1.7.5

Keep the verified 1.7.5 wheel available for offline rollback:

```powershell
$oldRelease = "https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v1.7.5"
Invoke-WebRequest "$oldRelease/opencntx-1.7.5-py3-none-any.whl" -OutFile opencntx-1.7.5-py3-none-any.whl
$oldHash = "8494439d1b3422d8a3afcb0fb385f1e499253d4932232338fada8fd04713fca0"
if ((Get-FileHash opencntx-1.7.5-py3-none-any.whl -Algorithm SHA256).Hash.ToLowerInvariant() -ne $oldHash) { throw "Rollback wheel checksum mismatch" }
pipx run --spec .\opencntx-1.7.6-py3-none-any.whl opencntx-install update `
  --artifact .\opencntx-1.7.6-py3-none-any.whl --sha256 $expected --version 1.7.6 `
  --rollback-artifact .\opencntx-1.7.5-py3-none-any.whl --rollback-sha256 $oldHash
opencntx --version
opencntx-install status
```

Activation is accepted only after package metadata, import/version, help, a real
checkpoint, and fresh-process resume all pass. A failed candidate is restored
from the already staged rollback wheel without importing the candidate.

## Dedicated virtual environment

Pass the environment's Python explicitly. The manager will keep using that
interpreter after activation and during rollback:

```powershell
pipx run --spec .\opencntx-1.7.6-py3-none-any.whl opencntx-install `
  --python C:\path\to\venv\Scripts\python.exe update `
  --artifact .\opencntx-1.7.6-py3-none-any.whl --sha256 $expected --version 1.7.6 `
  --rollback-artifact .\opencntx-1.7.5-py3-none-any.whl --rollback-sha256 $oldHash
```

On Linux, use the virtual environment's `bin/python` path.

## Resume or targeted repair

An interrupted operation is journaled before activation. Resume the newest
operation from a fresh shell with:

```powershell
pipx run --spec .\opencntx-1.7.6-py3-none-any.whl opencntx-install resume
```

Use `repair --plan-id PLAN_ID` only for a specific journal reported by status.
Both commands either prove `NEW_HEALTHY`, prove `OLD_RESTORED`, or return
`RECOVERY_REQUIRED` with retained data. They never infer health from hashes.

The default manager state is `%LOCALAPPDATA%\OPENCNTX\install-manager` on
Windows and `$XDG_STATE_HOME/opencntx/install-manager` (or
`~/.local/state/opencntx/install-manager`) on Linux. OPENCNTX removes only
marker-bound staging and superseded candidate caches. It retains the current
candidate, the offline rollback wheel and at most ten terminal journals. Unknown
files, user projects, custom rules, credentials and history are not cleanup
targets.

[1.7.6 release]: https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/v1.7.6
