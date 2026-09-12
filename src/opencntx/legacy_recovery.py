"""Prepare a separate legacy-compatible copy without unlocking a live store.

This is a staging primitive, not an installer or an in-place lock migration.
Only portable v1 continuity stores are eligible. The caller must validate the
actual legacy runtime on the staged copy before switching any active path.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from .continuity import (
    ContinuityError,
    _fail,
    _value_digest,
    _writer_lock,
    execution_state_capsule,
)
from .continuity_version import FORMAT, _retained_legacy_bytes

LOCK_PATHS = (
    "CONTROL/continuity.lock",
    ".opencntx/continuity/.operation.lock",
    ".opencntx/combo/.writer.lock",
)
OS_MARKERS = {b"OPENCNTX_OS_LOCK_V2\n", b"OPENCNTX_OS_LOCK_V2\r\n"}


def _project_digest(root: Path) -> str:
    records = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x0400:
            raise _fail("legacy_recovery_path_invalid", "Project contains a link or reparse point.")
        if relative in LOCK_PATHS:
            continue
        if stat.S_ISDIR(info.st_mode):
            records.append([relative, "directory"])
        elif stat.S_ISREG(info.st_mode):
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            records.append([relative, digest])
        else:
            raise _fail("legacy_recovery_path_invalid", "Project contains a special file.")
    return _value_digest(records)


def stage_legacy_recovery(
    root: Path, *, destination: Path, expected_state_digest: str
) -> dict[str, Any]:
    """Preserve source bytes and prepare a new, explicitly selected destination.

    A failed staging directory is retained for diagnosis. Existing destinations
    are never overwritten. No source lock is deleted or renamed, so old open
    file descriptors cannot create a split-lock race on the original store.
    """
    if (
        root.is_symlink()
        or getattr(root.lstat(), "st_file_attributes", 0) & 0x0400
        or destination.is_symlink()
    ):
        raise _fail("legacy_recovery_path_invalid", "Recovery paths must not be symlinks.")
    source = root.resolve(strict=True)
    target = destination.absolute()
    parent = target.parent.resolve(strict=True)
    target = parent / target.name
    if (
        target.exists()
        or target == source
        or source.is_relative_to(target)
        or target.is_relative_to(source)
    ):
        raise _fail(
            "legacy_recovery_path_invalid", "Use a new destination outside the source project."
        )
    roadmap_path = source / ".opencntx/continuity/roadmaps/roadmap.json"
    roadmap_value = json.loads(roadmap_path.read_text(encoding="utf-8"))
    try:
        legacy_roadmap_bytes = _retained_legacy_bytes(roadmap_value)
    except ContinuityError as exc:
        if roadmap_value.get("format") == FORMAT:
            raise _fail(
                "legacy_recovery_snapshot_required",
                "Newer storage has no valid retained pre-upgrade snapshot; the original is unchanged.",
            ) from exc
        raise
    if roadmap_value.get("format") == FORMAT and legacy_roadmap_bytes is None:
        raise _fail(
            "legacy_recovery_snapshot_required",
            "Newer storage has no valid retained pre-upgrade snapshot; the original is unchanged.",
        )
    # Validate the complete tree before acquiring any lock or creating staging.
    _project_digest(source)
    locks = [source / relative for relative in LOCK_PATHS if (source / relative).exists()]
    for lock in locks:
        if lock.read_bytes() not in OS_MARKERS:
            raise _fail(
                "legacy_recovery_writer_unknown",
                "An old or unknown writer marker needs writer shutdown verification; no marker removed.",
            )
    with ExitStack() as stack:
        for lock in sorted(locks):
            stack.enter_context(
                _writer_lock(lock, reject_local_overlap=True, preserve_marker=True)
            )
        # Missing lock paths cannot be created as a side effect of this copy.
        # An absent operation lock is acceptable only for a quiesced initial store;
        # callers must first create a current-version checkpoint instead.
        if source / ".opencntx/continuity/.operation.lock" not in locks:
            raise _fail(
                "legacy_recovery_checkpoint_required",
                "Create a current-version checkpoint before preparing a legacy recovery copy.",
            )
        if execution_state_capsule(source)["state_digest"] != expected_state_digest:
            raise _fail("legacy_recovery_stale", "Project changed; refresh the recovery plan.")
        before = _project_digest(source)
        staging = Path(tempfile.mkdtemp(prefix="opencntx-legacy-stage-", dir=parent))
        copy = staging / "project"

        def ignore(directory, names):
            return [
                name
                for name in names
                if (Path(directory) / name).relative_to(source).as_posix() in LOCK_PATHS
            ]

        shutil.copytree(source, copy, ignore=ignore)
        if _project_digest(source) != before or _project_digest(copy) != before:
            raise _fail("legacy_recovery_drift", f"Project changed; staging retained at {staging}.")
        if legacy_roadmap_bytes is not None:
            # The retained bytes are the only deliberate difference in a copy
            # prepared for an older reader; all event and evidence bytes remain
            # bound to the same validated roadmap state.
            (copy / ".opencntx/continuity/roadmaps/roadmap.json").write_bytes(
                legacy_roadmap_bytes
            )
        removed = [lock.relative_to(source).as_posix() for lock in locks]
        if execution_state_capsule(copy)["state_digest"] != expected_state_digest:
            raise _fail(
                "legacy_recovery_drift", "Copied continuity state differs; staging retained."
            )
        # The target must still be absent. mkdir reserves it against a concurrent
        # preparation without replacing user data; only our child is moved in.
        target.mkdir()
        os.rename(copy, target / "project")
        staging.rmdir()
        return {
            "status": "STAGED_REQUIRES_LEGACY_VALIDATION",
            "source": str(source),
            "source_digest": before,
            "source_unchanged": _project_digest(source) == before,
            "staged_project": str(target / "project"),
            "removed_copy_markers": removed,
            "legacy_roadmap_restored": legacy_roadmap_bytes is not None,
            "state_digest": expected_state_digest,
            "runtime_switched": False,
        }
