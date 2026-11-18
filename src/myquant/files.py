"""Atomic single-writer file primitives for immutable research artifacts.

All writers flush and fsync file contents before linking or renaming, and
fsync the parent directory afterwards so the new name itself survives a
power loss. These are local single-writer primitives, not a distributed
transaction protocol.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _fsync_directory(directory: Path) -> None:
    """Flush a directory entry so a newly linked name survives power loss."""
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_temp_file(directory: Path, content: bytes, *, prefix: str) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(dir=directory, prefix=prefix)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def write_new_file(target: Path, content: bytes) -> None:
    """Atomically create a file; identical existing bytes are idempotent."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() == content:
            return
        raise FileExistsError(
            f"immutable path already contains different bytes: {target}"
        )

    temporary = _write_temp_file(target.parent, content, prefix=".tmp-")
    try:
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != content:
                raise
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)


def create_immutable_file(target: Path, content: bytes) -> None:
    """Atomically create a file that must not already exist."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _write_temp_file(target.parent, content, prefix=".immutable-")
    try:
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise FileExistsError(
                f"immutable file already exists: {target}"
            ) from exc
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_replace(target: Path, content: bytes) -> None:
    """Atomically replace a file's contents via rename.

    Unlike the immutable writers above, this intentionally overwrites: it
    is for small mutable pointers such as ledger anchors, never for
    research records themselves.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _write_temp_file(target.parent, content, prefix=".replace-")
    try:
        os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)
