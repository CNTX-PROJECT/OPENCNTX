"""Deterministic compact control snapshots for OPENCNTX workspaces."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .integrity import writer_transaction
from .primitives import (
    pretty_json_bytes as _json_bytes,
)
from .primitives import (
    sha256_bytes as _digest,
)
from .primitives import (
    timestamp_microseconds as _timestamp,
)
from .workspace import WorkspaceError, validate_workspace

CONTROL_START = b"<!-- OPENCNTX:CONTROL:START -->"
CONTROL_END = b"<!-- OPENCNTX:CONTROL:END -->"
CONTROL_BLOCK_MAX_BYTES = 16_384
CONTROL_SNAPSHOT_PATH = ".opencntx/control-snapshot.md"
CONTROL_SNAPSHOT_HEADER = b"<!-- OPENCNTX:MANAGED-CONTROL-SNAPSHOT -->\n"
CONTROL_SNAPSHOT_FORMAT = "opencntx-control-snapshot"
CONTROL_SNAPSHOT_VERSION = 1
CONTROL_RECEIPT_FORMAT = "opencntx-control-receipt"
CONTROL_RECEIPT_VERSION = 1


class ControlError(WorkspaceError):
    """A stable fail-closed error for compact control handling."""


@dataclass(frozen=True)
class ControlState:
    root: Path
    mode: str
    owner_sha256: str
    roadmap_sha256: str
    current_sha256: str
    block_sha256: str | None
    block_bytes: int | None
    snapshot_sha256: str | None
    snapshot_bytes: bytes | None

    @property
    def fingerprint(self) -> tuple[object, ...]:
        return (
            self.mode,
            self.owner_sha256,
            self.roadmap_sha256,
            self.current_sha256,
            self.block_sha256,
            self.block_bytes,
            self.snapshot_sha256,
        )


@dataclass(frozen=True)
class ControlRefreshResult:
    status: str
    mode: str
    roadmap_sha256: str
    block_sha256: str | None
    snapshot_sha256: str | None
    block_bytes: int | None
    snapshot_path: Path | None
    receipt_path: Path | None


def _read_control_file(root: Path, relative: str) -> bytes:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ControlError(
            f"Controlbestand ontbreekt of is onveilig: {relative}.",
            code="control_file_invalid",
        )
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ControlError(
                f"Controlbestand verlaat de werkruimte: {relative}.",
                code="control_file_invalid",
            )
        content = path.read_bytes()
    except ControlError:
        raise
    except OSError as exc:
        raise ControlError(
            f"Controlbestand kan niet veilig worden gelezen: {relative}.",
            code="control_file_unavailable",
        ) from exc
    if b"\x00" in content or any(byte < 32 and byte not in (9, 10, 13) for byte in content):
        raise ControlError(
            f"Controlbestand bevat onveilige controltekens: {relative}.",
            code="control_file_invalid",
        )
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ControlError(
            f"Controlbestand is geen geldige UTF-8: {relative}.",
            code="control_file_invalid",
        ) from exc
    return content


def _extract_block(roadmap: bytes) -> bytes | None:
    starts = roadmap.count(CONTROL_START)
    ends = roadmap.count(CONTROL_END)
    if starts == 0 and ends == 0:
        return None
    if starts != 1 or ends != 1:
        raise ControlError(
            "CONTROL/ROADMAP.md moet exact één volledig control-markerpair bevatten.",
            code="control_markers_invalid",
        )
    start = roadmap.find(CONTROL_START)
    end = roadmap.find(CONTROL_END)
    if start < 0 or end < start + len(CONTROL_START):
        raise ControlError(
            "De control-markers in CONTROL/ROADMAP.md staan in ongeldige volgorde.",
            code="control_markers_invalid",
        )
    block = roadmap[start : end + len(CONTROL_END)]
    if len(block) > CONTROL_BLOCK_MAX_BYTES:
        raise ControlError(
            "Het actuele roadmapblock is te groot: "
            f"{len(block)} > {CONTROL_BLOCK_MAX_BYTES} bytes.",
            code="control_block_too_large",
        )
    return block


def _render_snapshot(
    *, owner: bytes, roadmap: bytes, current: bytes, block: bytes, legacy: bool = False
) -> bytes:
    block_text = block.decode("utf-8")
    metadata = [
        CONTROL_SNAPSHOT_HEADER.decode("ascii").rstrip("\n"),
        "---",
        f"format: {CONTROL_SNAPSHOT_FORMAT}",
        f"format_version: {CONTROL_SNAPSHOT_VERSION}",
        "mode: COMPACT_MARKED",
        f"owner_sha256: {_digest(owner)}",
        f"roadmap_sha256: {_digest(roadmap)}",
        f"current_sha256: {_digest(current)}",
        f"block_sha256: {_digest(block)}",
        f"block_bytes: {len(block)}",
        "---",
        "",
        "# OPENCNTX control snapshot",
        "",
        (
            "> Afgeleid en vervangbaar. Dit document verleent geen OWNER-bevoegdheid."
            if legacy
            else "> Derived and replaceable. This document grants no OWNER authority."
        ),
        "",
        "## Actuele roadmapsturing" if legacy else "## Current roadmap control",
        "",
    ]
    return ("\n".join(metadata) + block_text + "\n").encode("utf-8")


def inspect_control(project_root: Path, *, require_snapshot: bool = False) -> ControlState:
    """Inspect official control bytes without modifying the workspace."""
    root = validate_workspace(project_root)
    owner = _read_control_file(root, "CONTROL/OWNER.md")
    roadmap = _read_control_file(root, "CONTROL/ROADMAP.md")
    current = _read_control_file(root, "CONTROL/CURRENT.md")
    block = _extract_block(roadmap)
    if block is None:
        return ControlState(
            root=root,
            mode="LEGACY_FULL_ROADMAP",
            owner_sha256=_digest(owner),
            roadmap_sha256=_digest(roadmap),
            current_sha256=_digest(current),
            block_sha256=None,
            block_bytes=None,
            snapshot_sha256=None,
            snapshot_bytes=None,
        )
    snapshot = _render_snapshot(owner=owner, roadmap=roadmap, current=current, block=block)
    state = ControlState(
        root=root,
        mode="COMPACT_MARKED",
        owner_sha256=_digest(owner),
        roadmap_sha256=_digest(roadmap),
        current_sha256=_digest(current),
        block_sha256=_digest(block),
        block_bytes=len(block),
        snapshot_sha256=_digest(snapshot),
        snapshot_bytes=snapshot,
    )
    if require_snapshot:
        path = root / CONTROL_SNAPSHOT_PATH
        if path.is_symlink() or not path.is_file():
            raise ControlError(
                "De beheerde control-snapshot ontbreekt of is onveilig; refresh vereist.",
                code="control_snapshot_stale",
            )
        try:
            actual = path.read_bytes()
        except OSError as exc:
            raise ControlError(
                "De beheerde control-snapshot kan niet worden gelezen.",
                code="control_snapshot_unavailable",
            ) from exc
        legacy_snapshot = _render_snapshot(
            owner=owner,
            roadmap=roadmap,
            current=current,
            block=block,
            legacy=True,
        )
        if actual not in {snapshot, legacy_snapshot}:
            raise ControlError(
                "De beheerde control-snapshot wijkt af van de officiële controlbytes.",
                code="control_snapshot_stale",
            )
        if actual == legacy_snapshot:
            state = ControlState(
                root=root,
                mode=state.mode,
                owner_sha256=state.owner_sha256,
                roadmap_sha256=state.roadmap_sha256,
                current_sha256=state.current_sha256,
                block_sha256=state.block_sha256,
                block_bytes=state.block_bytes,
                snapshot_sha256=_digest(actual),
                snapshot_bytes=actual,
            )
    return state


def _snapshot_target(root: Path) -> Path:
    path = root / CONTROL_SNAPSHOT_PATH
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ControlError(
            "Het beheerde control-snapshotpad is geen veilig regulier bestand.",
            code="control_snapshot_unmanaged",
        )
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise ControlError(
                "De bestaande control-snapshot kan niet veilig worden gelezen.",
                code="control_snapshot_unavailable",
            ) from exc
        if not existing.startswith(CONTROL_SNAPSHOT_HEADER):
            raise ControlError(
                "Het control-snapshotpad bevat onbekende bytes; niets overschreven.",
                code="control_snapshot_unmanaged",
            )
    return path


def _atomic_snapshot(path: Path, content: bytes) -> None:
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ControlError(
            "De control-snapshot kon niet atomair worden gepubliceerd.",
            code="control_snapshot_write_failed",
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _receipt_path(root: Path, attempt_id: str) -> Path:
    return root / ".opencntx" / "receipts" / f"{attempt_id}.json"


def _write_receipt(
    root: Path,
    *,
    attempt_id: str,
    created_at: datetime,
    status: str,
    state: ControlState | None,
    error: ControlError | None = None,
) -> Path:
    path = _receipt_path(root, attempt_id)
    value = {
        "attempt_id": attempt_id,
        "block_bytes": state.block_bytes if state else None,
        "block_sha256": state.block_sha256 if state else None,
        "created_at": _timestamp(created_at),
        "error": f"Control refresh failed: {error.code}." if error else None,
        "error_code": error.code if error else None,
        "format": CONTROL_RECEIPT_FORMAT,
        "format_version": CONTROL_RECEIPT_VERSION,
        "mode": state.mode if state else None,
        "next_action": (
            "Use the compact snapshot in an approved task context."
            if status == "CONTROL_SNAPSHOT_REFRESHED"
            else (
                "Deliberately add one valid marker block to activate compact mode."
                if status == "CONTROL_LEGACY_CONFIRMED"
                else "Fix the reported control error and request an OWNER decision if needed."
            )
        ),
        "roadmap_sha256": state.roadmap_sha256 if state else None,
        "snapshot_path": CONTROL_SNAPSHOT_PATH if state and state.snapshot_bytes else None,
        "snapshot_sha256": state.snapshot_sha256 if state else None,
        "status": status,
    }
    try:
        with path.open("xb") as output:
            output.write(_json_bytes(value))
            output.flush()
            os.fsync(output.fileno())
    except OSError as exc:
        raise ControlError(
            "Het control-ontvangstbewijs kon niet worden geschreven.",
            code="control_receipt_write_failed",
        ) from exc
    return path


def _refresh_control_snapshot_unlocked(
    project_root: Path, *, write_receipt: bool = True
) -> ControlRefreshResult:
    """Refresh the managed snapshot, or explicitly confirm legacy mode."""
    created_at = datetime.now(UTC)
    attempt_id = f"CONTROL-{created_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
    root = project_root
    state: ControlState | None = None
    try:
        state = inspect_control(root)
        root = state.root
        snapshot_path: Path | None = None
        if state.mode == "COMPACT_MARKED":
            target = _snapshot_target(root)
            if state.snapshot_bytes is None:
                raise ControlError(
                    "De officiële controlbytes zijn intern onvolledig.",
                    code="control_file_invalid",
                )
            _atomic_snapshot(target, state.snapshot_bytes)
            confirmed = inspect_control(root, require_snapshot=True)
            if confirmed.fingerprint != state.fingerprint:
                raise ControlError(
                    "De officiële controlbytes veranderden tijdens refresh.",
                    code="control_state_changed",
                )
            state = confirmed
            snapshot_path = target
            status = "CONTROL_SNAPSHOT_REFRESHED"
        else:
            status = "CONTROL_LEGACY_CONFIRMED"
        receipt = (
            _write_receipt(
                root,
                attempt_id=attempt_id,
                created_at=created_at,
                status=status,
                state=state,
            )
            if write_receipt
            else None
        )
        return ControlRefreshResult(
            status=status,
            mode=state.mode,
            roadmap_sha256=state.roadmap_sha256,
            block_sha256=state.block_sha256,
            snapshot_sha256=state.snapshot_sha256,
            block_bytes=state.block_bytes,
            snapshot_path=snapshot_path,
            receipt_path=receipt,
        )
    except ControlError as exc:
        try:
            resolved = validate_workspace(root)
            if write_receipt:
                _write_receipt(
                    resolved,
                    attempt_id=attempt_id,
                    created_at=created_at,
                    status="CONTROL_NOT_REFRESHED",
                    state=state,
                    error=exc,
                )
        except WorkspaceError:
            pass
        raise


def refresh_control_snapshot(
    project_root: Path, *, write_receipt: bool = True
) -> ControlRefreshResult:
    root = validate_workspace(project_root)
    with writer_transaction(root, "control-refresh"):
        return _refresh_control_snapshot_unlocked(root, write_receipt=write_receipt)
