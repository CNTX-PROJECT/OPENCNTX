# Troubleshooting

[Overview](../README.md) · [Get started](start-here.md) · [How it works](how-it-works.md) · [Workspace](workspace.md) · [Commands](commands.md) · [Security](security.md) · [All guides](README.md)

Start with the smallest failing command. Read its complete output and keep the
first stable error message.

## `opencntx` is not found

Verify the installation environment:

```powershell
opencntx --version
python -m pip show opencntx
```

Activate the virtual environment where you installed the package, or reinstall
from the approved tag using [Start here](start-here.md).

If `pipx` installed the exact tag, inspect its isolated environment with
`pipx list`. Remove only that tool environment with `pipx uninstall opencntx`.

## A local candidate build refuses to start

The release helper requires a clean worktree, an exact expected commit and
tree, and an absent or empty output directory. Do not bypass those checks.
Inspect `git status`, verify the intended source, and choose a new empty output
directory. The helper never publishes or uploads the result.

If wheel reproduction, sdist content comparison, metadata, archive safety, or
checksums fail, preserve the first stable error and stop. Do not rename or
manually repair an artifact. See [Release artifacts](release-artifacts.md).

## `init` refuses to continue

An `opencntx.toml` probably already exists. OPENCNTX does not overwrite it.
Open and review the existing file instead of deleting it automatically.

## `pack` reports a missing required file

Check the path relative to the project root and the `required` list. File name
case can matter on Linux.

## A budget is exceeded

Do not increase the budget automatically. Narrow the task, remove unrelated
include patterns, or add a deliberate exclusion. The package must fit as a
complete set. A byte-budget error reports both the bytes required by that
complete selection and the configured allowed bytes.

## A state path is inaccessible

`managed_path_unsafe` can mean OPENCNTX could not safely inspect its local
`.opencntx` state. The operation stops before publication and does not treat
the unreadable path as absent. Check the project parent directory and its
normal Windows ACL or POSIX permissions. Do not blindly use `takeown`, grant
broad access, delete transaction evidence, or replace the state directory;
preserve the first error and investigate the exact path first.

## A disk-space preflight fails

The operation stopped before publishing its target because physical free space
was below the bounded estimate. Free space on the target volume, reduce only
unrelated data, and rerun the same approved operation. Do not bypass the check
or confuse the configured content budget with physical storage capacity.

## A file is rejected as binary or invalid UTF-8

The core accepts local UTF-8 text only. Convert the file outside OPENCNTX after
review, or use the media registration flow for already produced UTF-8 text.
OPENCNTX does not perform extraction itself.

## `verify` reports changed or missing sources

The package no longer matches the current project files. Decide whether the
old snapshot is still correct. If not, inspect the changed sources and rebuild
the package.

Running `opencntx verify` without a path checks only `.opencntx/latest` under
the current directory. It never searches a parent directory. Use an explicit
path when that default is not the intended package.

## A Windows terminal cannot display a path character

OPENCNTX keeps user paths and content as UTF-8. Fixed CLI text is ASCII-safe.
On a narrow console, an unsupported character is displayed as an escape rather
than causing a traceback. Use a UTF-8 terminal when you need the exact visible
character; stored path and artifact bytes are not rewritten.

## A workspace command reports a wrong digest

Do not copy a digest from an older revision. Run the relevant read-only status
or verify command, inspect the current official record, and use the exact value
required by the next approved step.

## A workspace writer is locked or requires recovery

Do not delete `.opencntx` lock, temporary, previous, or transaction files by
hand. First run:

```powershell
opencntx workspace doctor --root my-project
```

`ACTIVE` means a real writer still holds the local OS lock. Wait for that
bounded operation to finish. `RECOVERY_REQUIRED` supplies an exact transaction
ID and intent SHA-256. Use those values with `workspace recover` without
`--apply` first, inspect the preview, and apply only the exact reported plan.
Unknown state remains fail-closed and needs manual investigation; recovery does
not delete it.

## Lifecycle migration or cleanup refuses a plan

Recreate the read-only preview and compare its digest. A changed workspace,
changed plan file, wrong SHA-256, unknown record version, unsafe path, active
writer, or changed cleanup target intentionally makes an old plan stale.

For cleanup, the checkpoint must be new or empty, outside the workspace, and
observed as private. Never edit a checkpoint manifest or manually delete a
target after preview. If cleanup succeeded, use its reported checkpoint
SHA-256 with `workspace lifecycle restore` only while every destination is
still absent. See [Privacy, storage, and format lifecycle](privacy-storage-lifecycle.md).

## A chapter is `STALE` or `INCOMPLETE`

Check its source pins and dependencies. Create or accept the required revision,
then rebuild the catalog. Do not edit the SQLite database directly.

## Context cannot be built

Confirm that:

- the task is exactly `IN_EXECUTION`;
- required chapters are current and accepted;
- the catalog reflects the latest official files;
- source privacy is allowed;
- control and task digests match;
- the byte budget is sufficient for the complete selected set.

## A task becomes `BLOCKED`

Read `workspace task status` and keep the reported primary block reason:

- `SEMANTIC_REPEAT_LIMIT`: the same controller fingerprint occurred three
  times, even if other failures appeared between them;
- `TOTAL_ATTEMPT_LIMIT`: five total failed attempts were recorded;
- `CUMULATIVE_ACTION_LIMIT`: the task reached 25 recorded actions;
- `CUMULATIVE_TIME_LIMIT`: the task reached 1,800,000 recorded milliseconds.

Stop and preserve the evidence. There is no retry, reset, or budget override.
The OWNER may cancel the task or explicitly supersede it with one new task ID.
Do not edit task events, artifacts, the executor package, or context manifest.

If `record-attempt` reports `task_attempt_unchanged`, supply genuinely changed
relevant input bytes or one unique new-evidence file. A different description,
mtime, input order, result log, or a second copy of identical evidence is not a
new basis. A historical task containing free-text legacy attempts remains
readable but requires a new explicit task before objective attempt recording.

## Need more help?

Use [Support](../SUPPORT.md) for ordinary questions and reproducible bugs. Use
GitHub's private vulnerability route for security issues.

[Documentation home](README.md)
