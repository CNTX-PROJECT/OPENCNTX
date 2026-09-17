"""Shared bounded filesystem and delivery primitives for local knowledge."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MAX_SCAN_ENTRIES = 1_000_000


class KnowledgeError(ValueError):
    """A fail-closed knowledge contract error."""


def safe_path(root: Path, relative: str, *, directory: bool = False) -> Path:
    """Use the existing link/reparse-aware project boundary."""
    from .integrity import IntegrityError, safe_managed_path

    try:
        return safe_managed_path(root, relative, kind="directory" if directory else "file")
    except IntegrityError as exc:
        raise KnowledgeError("Knowledge path is outside its safe project boundary.") from exc


def bounded_read(root: Path, relative: str, maximum: int) -> bytes:
    """Never read more than maximum bytes; reject drift and unsafe handles."""
    if maximum < 0:
        raise KnowledgeError("Source read budget is exhausted.")
    path = safe_path(root, relative)
    descriptor: int | None = None
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise KnowledgeError("Source is not regular or exceeds its byte budget.")
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        )
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise KnowledgeError("Source identity changed while opening.")
            safe_path(root, relative)
            if opened.st_size > maximum:
                raise KnowledgeError("Source grew beyond its byte budget.")
            data = stream.read(maximum)
            after = os.fstat(stream.fileno())
            if (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
                raise KnowledgeError("Source changed while reading.")
            if len(data) != after.st_size:
                raise KnowledgeError("Source read was incomplete.")
            return data
    except OSError as exc:
        raise KnowledgeError("Source is unavailable for a bounded read.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def safe_output(path: Path) -> Path:
    """Validate all ancestors of an explicitly selected cache output."""
    selected = path.expanduser().absolute()
    anchor = Path(selected.anchor)
    relative = selected.relative_to(anchor)
    if any(part in {".", ".."} or ":" in part for part in relative.parts):
        raise KnowledgeError("Cache output must have an exact safe path.")
    existing = selected
    while not existing.exists() and not existing.is_symlink():
        existing = existing.parent
    if existing != anchor:
        safe_path(anchor, existing.relative_to(anchor).as_posix(), directory=existing != selected)
    return selected


def check_delivery(relative: str, text: str, digest: str) -> None:
    """Reject deterministic secret signals before model-facing delivery."""
    from .security import CONFIDENCE_HIGH, CONFIDENCE_WARNING, scan_text

    findings = scan_text(path=relative, text=text, source_sha256=digest)
    # Retrieval also withholds opaque provider-prefixed values, including
    # synthetic canaries containing separators that are not live key syntax.
    opaque_provider_value = re.search(r"\bsk_live_[A-Za-z0-9_-]{20,}\b", text)
    if opaque_provider_value or any(
        item.confidence in {CONFIDENCE_HIGH, CONFIDENCE_WARNING} for item in findings
    ):
        raise KnowledgeError("Source delivery blocked by the local secret policy.")


@contextmanager
def publication_lock(destination: Path) -> Iterator[None]:
    """Keep a stable OS-locked inode; never unlink a lock held by a contender."""
    from .integrity import IntegrityError, _FileLock

    lock_path = destination.with_name(destination.name + ".lock")
    try:
        safe_path(destination.parent, lock_path.name)
        descriptor = os.open(
            lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        with os.fdopen(descriptor, "r+b") as handle:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"0")
                handle.flush()
            _FileLock._lock(handle)
            try:
                yield
            finally:
                _FileLock._unlock(handle)
    except (OSError, IntegrityError) as exc:
        raise KnowledgeError("Search index publication is locked or unavailable.") from exc
