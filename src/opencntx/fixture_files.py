"""Windows physical primitives for a closed, supervisor-bound reference fixture.

No standalone CLI or client policy writer. Unsupported platforms refuse writes.
Derived from the preserved R15-01 staged-writer proof, not the retired copy pilot.
"""

from __future__ import annotations

import ctypes as c
import hashlib
import sys
from contextlib import ExitStack
from ctypes import wintypes as w
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

_CTYPES: dict[str, Any] = vars(c)
MAX_FILE = 1024 * 1024
MAX_REQUEST = 65536
IO_BYTES = {"file_read": 0, "file_written": 0, "request_read": 0}
NAMES = ("parent/00.txt", "parent/90.txt", "parent/99.txt")
STAGED = tuple(n.replace("parent/", "staging/") for n in NAMES)
RETAINED = tuple(n.replace("parent/", "retained/") for n in NAMES)
WATCHED = (
    NAMES
    + tuple(n.replace("parent/", "parent/child/") for n in NAMES)
    + tuple("backup/" + n for n in NAMES)
)


class Refused(Exception):
    pass


class RecoveryRequired(Refused):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Info(c.Structure):
    _fields_ = [
        ("attrs", w.DWORD),
        ("created", w.FILETIME),
        ("accessed", w.FILETIME),
        ("written", w.FILETIME),
        ("volume", w.DWORD),
        ("size_hi", w.DWORD),
        ("size_lo", w.DWORD),
        ("links", w.DWORD),
        ("id_hi", w.DWORD),
        ("id_lo", w.DWORD),
    ]


class Handle:
    def __init__(
        self,
        path: Path,
        *,
        directory: bool = False,
        movable: bool = False,
        create: bool = False,
    ):
        if sys.platform != "win32":
            raise Refused("unsupported_platform")
        # These ctypes names exist only on Windows. Resolve them dynamically so
        # the closed Windows fixture remains type-checkable on Linux CI.
        self.k: Any = _CTYPES["WinDLL"]("kernel32", use_last_error=True)
        signatures = {
            "CreateFileW": (
                [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE],
                w.HANDLE,
            ),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "GetFileInformationByHandle": ([w.HANDLE, c.POINTER(Info)], w.BOOL),
            "GetFinalPathNameByHandleW": ([w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD], w.DWORD),
            "SetFilePointerEx": (
                [w.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), w.DWORD],
                w.BOOL,
            ),
            "ReadFile": (
                [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p],
                w.BOOL,
            ),
            "WriteFile": (
                [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p],
                w.BOOL,
            ),
            "SetEndOfFile": ([w.HANDLE], w.BOOL),
            "FlushFileBuffers": ([w.HANDLE], w.BOOL),
            "SetFileInformationByHandle": (
                [w.HANDLE, c.c_int, c.c_void_p, w.DWORD],
                w.BOOL,
            ),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.k, name)
            fn.argtypes, fn.restype = args, result
        self.path: Path = path
        self.new: bool = create
        self.sealed: bool = not create
        access = (
            0x80
            if directory
            else (0xC0010000 if create else 0x80000000 | (0x10000 if movable else 0))
        )
        flags = 0x00200000 | (0x02000000 if directory else 0)
        # Directory handles deny write and delete opens, including reparse mutation.
        self.h: Any = self.k.CreateFileW(
            str(path),
            access,
            1 if directory else 0,
            None,
            1 if create else 3,
            flags,
            None,
        )
        if self.h == c.c_void_p(-1).value:
            raise Refused(f"open_denied_{_CTYPES['get_last_error']()}")
        try:
            # Only a newly created empty staging object is marked delete-pending.
            # Unlike FILE_FLAG_DELETE_ON_CLOSE, explicit disposition blocks links.
            # A link won before this point is caught before the first data write.
            if create:
                self.pending(True)
            self.info: Info = Info()
            self.check(self.k.GetFileInformationByHandle(self.h, c.byref(self.info)))
            if self.info.attrs & 0x400:
                raise Refused("reparse_point")
            if bool(self.info.attrs & 0x10) != directory:
                raise Refused("wrong_file_kind")
            # Windows excludes the delete-pending staging name from link count.
            if not directory and (self.info.links != (0 if create else 1) or self.size > MAX_FILE):
                raise Refused("hardlink_or_oversize")
        except BaseException:
            self.k.CloseHandle(self.h)
            raise

    @property
    def identity(self) -> tuple[int, int, int]:
        return self.info.volume, self.info.id_hi, self.info.id_lo

    @property
    def size(self) -> int:
        return (self.info.size_hi << 32) | self.info.size_lo

    def check(self, ok: Any) -> None:
        if not ok:
            raise Refused(f"io_error_{_CTYPES['get_last_error']()}")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.k.CloseHandle(self.h)

    def read(self) -> bytes:
        self.check(self.k.SetFilePointerEx(self.h, 0, None, 0))
        buf = c.create_string_buffer(MAX_FILE + 1)
        count = w.DWORD()
        self.check(self.k.ReadFile(self.h, buf, MAX_FILE + 1, c.byref(count), None))
        IO_BYTES["file_read"] += count.value
        if count.value > MAX_FILE:
            raise Refused("oversize")
        return buf.raw[: count.value]

    def current_path(self) -> Path:
        """Read the held object's OS position, not an interrupted Python update."""
        buffer = c.create_unicode_buffer(32768)
        length = self.k.GetFinalPathNameByHandleW(self.h, buffer, len(buffer), 0)
        if not 0 < length < len(buffer):
            raise Refused("held_path_unavailable")
        value = buffer.value
        if not value.startswith("\\\\?\\") or value.startswith("\\\\?\\UNC\\"):
            raise Refused("held_path_not_local_dos")
        return Path(value[4:])

    def replace(self, data: bytes) -> None:
        if not self.new or self.sealed:
            raise Refused("in_place_write_forbidden")
        if len(data) > MAX_FILE:
            raise Refused("oversize")
        self.check(self.k.SetFilePointerEx(self.h, 0, None, 0))
        count = w.DWORD()
        buf = c.create_string_buffer(data)
        self.check(self.k.WriteFile(self.h, buf, len(data), c.byref(count), None))
        IO_BYTES["file_written"] += count.value
        if count.value != len(data):
            raise Refused("short_write")
        self.check(self.k.SetEndOfFile(self.h))
        self.check(self.k.FlushFileBuffers(self.h))
        if self.read() != data:
            raise Refused("write_readback_mismatch")

    def pending(self, value: bool) -> None:
        flag = w.BOOL(value)
        self.check(self.k.SetFileInformationByHandle(self.h, 4, c.byref(flag), c.sizeof(flag)))

    def seal(self) -> None:
        # No byte mutation is ever allowed after other names can be created.
        self.sealed = True
        self.pending(False)

    def rename(self, target: Path) -> None:
        class Rename(c.Structure):
            _fields_ = [
                ("flags", w.DWORD),
                ("root", w.HANDLE),
                ("length", w.DWORD),
                ("name", w.WCHAR * 1),
            ]

        name = str(target).encode("utf-16-le")
        buf = c.create_string_buffer(max(c.sizeof(Rename), Rename.name.offset + len(name) + 2))
        info = Rename.from_buffer(buf)
        info.flags, info.root, info.length = 0, None, len(name)
        c.memmove(c.addressof(buf) + Rename.name.offset, name, len(name))
        self.check(self.k.SetFileInformationByHandle(self.h, 3, buf, len(buf)))
        self.path = target


def lock_directories(root: Path, stack: ExitStack) -> tuple[tuple[int, int, int], ...]:
    # Lock every path component from the volume anchor before opening its child.
    paths = list(reversed(root.parents)) + [
        root,
        root / "parent",
        root / "parent/child",
        root / "backup",
        root / "backup/parent",
        root / "staging",
        root / "retained",
    ]
    return tuple(stack.enter_context(Handle(p, directory=True)).identity for p in paths)


@dataclass(frozen=True)
class Binding:
    root: Path
    identities: tuple[tuple[int, int, int], ...]
    directories: tuple[tuple[int, int, int], ...]
    originals: tuple[bytes, ...]
    replacements: tuple[bytes, ...]


def bind(root: Path, *, allowed_root: Path) -> Binding:
    """Trusted supervisor fixture setup only; never a client protocol operation."""
    root = root.absolute()
    if ".." in root.parts or not root.drive or str(root).startswith("\\\\"):
        raise Refused("noncanonical_root")
    # Only the supervisor's explicit project subtree can contain this fixture.
    try:
        relative = root.relative_to(allowed_root.absolute())
        if not relative.parts:
            raise ValueError("fixture root must be a child")
    except ValueError as exc:
        raise Refused("outside_supervisor_scope") from exc
    with ExitStack() as stack:
        directories = lock_directories(root, stack)
        if any((root / n).exists() for n in STAGED + RETAINED):
            raise Refused("recovery_destination_exists")
        handles = [stack.enter_context(Handle(root / name)) for name in WATCHED]
        originals = tuple(handle.read() for handle in handles)
        replacements = tuple(b"R15 parent replacement " + str(i).encode() + b"\n" for i in range(3))
        # Durable copies are prepared by the trusted fixture supervisor, not here.
        for data, backup in zip(originals[:3], originals[6:]):
            if backup != data:
                raise Refused("backup_mismatch")
        return Binding(
            root,
            tuple(h.identity for h in handles),
            directories,
            originals,
            replacements,
        )


def execute(binding: Binding) -> None:
    b = binding
    with ExitStack() as stack:
        if lock_directories(b.root, stack) != b.directories:
            raise Refused("directory_identity_drift")
        handles = [
            stack.enter_context(Handle(b.root / n, movable=i < 3)) for i, n in enumerate(WATCHED)
        ]
        for handle, identity, original in zip(handles, b.identities, b.originals):
            if handle.identity != identity or handle.read() != original:
                raise Refused("target_identity_or_content_drift")
        if any((b.root / n).exists() for n in STAGED + RETAINED):
            raise Refused("recovery_destination_exists")
        staged = [stack.enter_context(Handle(b.root / n, create=True)) for n in STAGED]
        # All replacement bytes are prepared before any original name moves.
        for handle, replacement in zip(staged, b.replacements):
            handle.replace(replacement)
        try:
            for i in range(3):
                handles[i].rename(b.root / RETAINED[i])
                staged[i].seal()
                staged[i].rename(b.root / NAMES[i])
        except BaseException:
            # Recovery never overwrites a competing new destination. Original
            # file objects, including aliases created during the operation,
            # retain their original bytes. Power-loss atomicity is not claimed.
            try:
                for i in reversed(range(3)):
                    position = handles[i].current_path()
                    if position == b.root / NAMES[i]:
                        continue
                    if position != b.root / RETAINED[i]:
                        raise Refused("unexpected_original_position")
                    staged_position = staged[i].current_path()
                    if staged_position == b.root / NAMES[i]:
                        staged[i].rename(b.root / STAGED[i])
                    elif staged_position != b.root / STAGED[i]:
                        raise Refused("unexpected_staged_position")
                    handles[i].rename(b.root / NAMES[i])
                if any(
                    handles[i].current_path() != b.root / NAMES[i]
                    or handles[i].read() != b.originals[i]
                    for i in range(3)
                ):
                    raise Refused("rollback_readback_failed")
            except BaseException as rollback_failure:
                raise RecoveryRequired("rollback_failed_backups_retained") from rollback_failure
            raise
