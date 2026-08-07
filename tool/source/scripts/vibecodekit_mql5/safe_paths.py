"""Filesystem safety helpers shared by build/codegen pipelines."""
from __future__ import annotations

import re
from pathlib import Path

_EA_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def validate_ea_name(name: str) -> str:
    """Return *name* when it is a safe MQL5/project identifier.

    Names are used in project paths, include namespaces and MQL5 identifiers.
    Reject separators, dot segments, drive prefixes, whitespace and punctuation
    instead of trying to sanitize them into a different project silently.
    """
    if not isinstance(name, str) or not _EA_NAME_RE.fullmatch(name):
        raise ValueError(
            "EA name must match ^[A-Za-z][A-Za-z0-9_]{0,63}$; "
            f"got {name!r}"
        )
    return name


def safe_join(root: Path, relative: str | Path) -> Path:
    """Resolve a path below *root* or raise ``ValueError``.

    The check is performed on resolved absolute paths and therefore blocks
    ``..`` traversal as well as absolute-path escapes.
    """
    root_resolved = root.resolve()
    rel = Path(relative)
    if rel.is_absolute():
        raise ValueError(f"absolute output path is not allowed: {relative}")
    candidate = (root_resolved / rel).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"output path escapes build root: {relative}") from exc
    return candidate
