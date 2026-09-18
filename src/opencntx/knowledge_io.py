"""Shared bounded filesystem and delivery primitives for local knowledge."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable, Iterator
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


def paths_alias(left: Path, right: Path) -> bool:
    """Return whether two paths address the same filesystem object or location."""
    first = left.expanduser().absolute()
    second = right.expanduser().absolute()
    try:
        if os.path.samefile(first, second):
            return True
    except (OSError, RuntimeError, ValueError):
        pass
    try:
        normalized_first = first.resolve(strict=False)
        normalized_second = second.resolve(strict=False)
    except (OSError, RuntimeError):
        normalized_first = first
        normalized_second = second
    return os.path.normcase(os.path.normpath(os.fspath(normalized_first))) == os.path.normcase(
        os.path.normpath(os.fspath(normalized_second))
    )


def validate_output_paths(
    root: Path,
    outputs: Iterable[Path],
    *,
    source_paths: Iterable[Path] = (),
    replaceable_paths: Iterable[Path] = (),
    reserved_paths: Iterable[Path] = (),
) -> list[Path]:
    """Reject output collisions before an index projection can replace a file."""
    selected_root = root.resolve(strict=True)
    destinations = [safe_output(path) for path in outputs]
    sources = tuple(source_paths)
    replaceable = tuple(replaceable_paths)
    reserved = tuple(reserved_paths)
    for index, destination in enumerate(destinations):
        for other in destinations[index + 1 :]:
            if paths_alias(destination, other):
                raise KnowledgeError("Index outputs must not alias one another.")
        for source in sources:
            if paths_alias(destination, source):
                raise KnowledgeError("Index output must not replace a project source file.")
        for protected in reserved:
            if paths_alias(destination, protected):
                raise KnowledgeError("Index output conflicts with another managed product file.")

        try:
            relative = destination.relative_to(selected_root)
        except ValueError:
            relative = None
        if relative is not None:
            if len(relative.parts) < 2 or relative.parts[0].casefold() != ".opencntx":
                raise KnowledgeError("Index output must not replace project-owned data.")
            if len(relative.parts) > 1 and relative.parts[1].casefold() in {
                "derived",
                "executors",
                "latest",
                "lifecycle",
                "receipts",
                "recovery",
                "transactions",
            }:
                raise KnowledgeError("Index output must not replace managed owner data.")

        try:
            info = destination.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise KnowledgeError("Index output metadata is unavailable.") from exc
        if not stat.S_ISREG(info.st_mode):
            raise KnowledgeError("Index output must be a regular file.")
        if info.st_nlink > 1:
            raise KnowledgeError("Index output must not be a hard link.")

        if relative is None:
            continue
        if not any(paths_alias(destination, allowed) for allowed in replaceable):
            raise KnowledgeError("Index output must not replace an unrelated product file.")
    return destinations


def raise_walk_error(error: OSError) -> None:
    """Turn os.walk scan failures into fail-closed knowledge errors."""
    filename = error.filename
    if filename is None:
        raise KnowledgeError("Source enumeration failed because a directory could not be read.") from error
    try:
        display_path = os.fsdecode(filename)
    except (TypeError, ValueError):
        display_path = "an unreadable directory"
    raise KnowledgeError(f"Source enumeration failed for {display_path}.") from error


def is_link_or_reparse(path: Path) -> bool:
    """Recognize symbolic links and Windows junctions without following them."""
    try:
        info = path.lstat()
    except OSError as exc:
        raise KnowledgeError(f"Source path metadata is unavailable: {path}.") from exc
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x0400)


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
