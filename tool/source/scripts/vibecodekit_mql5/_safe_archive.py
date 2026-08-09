"""Safe ZIP extraction (defense against Zip Slip / symlink / zip-bomb).

:func:`zipfile.ZipFile.extractall` trusts archive member names. A crafted
zip can therefore (a) escape the destination via ``../`` or an absolute
path, (b) plant a symlink that later redirects writes, or (c) inflate to
an enormous size (zip bomb). EA source archives uploaded to
:mod:`vibecodekit_mql5.ea_intake` are *untrusted input*, so we extract
through :func:`safe_extract`, which validates every member before it
touches the filesystem.

The checks are intentionally strict and *fail closed*: any unsafe member
raises :class:`UnsafeArchiveError` and nothing further is written.
"""
from __future__ import annotations

import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

# Conservative ceilings that comfortably fit a real EA codebase while
# stopping a decompression bomb. Override per-call when needed.
DEFAULT_MAX_FILES = 20_000
DEFAULT_MAX_TOTAL_BYTES = 200 * 1024 * 1024  # 200 MiB uncompressed


class UnsafeArchiveError(Exception):
    """Raised when a zip member would be unsafe to extract."""


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    """True when the zip entry encodes a (unix) symlink."""
    mode = (info.external_attr >> 16) & 0xFFFF
    return bool(mode) and stat.S_ISLNK(mode)


def _looks_absolute_or_traversing(name: str) -> bool:
    """True when a member name is absolute, drive-anchored or uses ``..``."""
    if not name:
        return True
    # Normalise both posix and windows separators - a zip created on
    # Windows may carry backslashes or a drive letter.
    posix = PurePosixPath(name)
    win = PureWindowsPath(name)
    if posix.is_absolute() or win.is_absolute():
        return True
    if win.drive or name.startswith(("/", "\\")):
        return True
    parts = name.replace("\\", "/").split("/")
    return any(part == ".." for part in parts)


def iter_safe_members(
    zf: zipfile.ZipFile,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> list[zipfile.ZipInfo]:
    """Validate the archive and return the members that should be written.

    Raises :class:`UnsafeArchiveError` on the first violation. Directory
    entries are returned too so empty dirs are preserved.
    """
    infos = zf.infolist()
    if len(infos) > max_files:
        raise UnsafeArchiveError(
            f"archive has {len(infos)} entries (limit {max_files})"
        )
    total = 0
    for info in infos:
        name = info.filename
        if _looks_absolute_or_traversing(name):
            raise UnsafeArchiveError(f"unsafe member path: {name!r}")
        if _is_symlink(info):
            raise UnsafeArchiveError(f"symlink member not allowed: {name!r}")
        total += info.file_size
        if total > max_total_bytes:
            raise UnsafeArchiveError(
                f"uncompressed size exceeds {max_total_bytes} bytes"
            )
    return infos


def safe_extract(
    zf: zipfile.ZipFile,
    dest: str | Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> Path:
    """Extract ``zf`` into ``dest`` after validating every member.

    Every resolved target is asserted to live inside ``dest`` so a member
    cannot escape even if it slips past the name check (e.g. via a quirky
    separator). Returns the resolved destination directory.
    """
    dest_path = Path(dest).resolve()
    dest_path.mkdir(parents=True, exist_ok=True)
    infos = iter_safe_members(
        zf, max_files=max_files, max_total_bytes=max_total_bytes
    )
    for info in infos:
        target = (dest_path / info.filename).resolve()
        if target != dest_path and not target.is_relative_to(dest_path):
            raise UnsafeArchiveError(
                f"member escapes destination: {info.filename!r}"
            )
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            # Stream in chunks; sizes are already bounded by the checks above.
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    return dest_path
