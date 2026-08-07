"""Single source of truth for the kit version.

Resolution order:
  1. ``[project].version`` in pyproject.toml (the declared root).
  2. Installed package metadata (when pip-installed without source).
  3. ``"0+unknown"`` fallback.
"""
from __future__ import annotations

import re
from pathlib import Path

_DIST_NAME = "vibecodekit-mql5-ea"


def _from_pyproject() -> str | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        pp = parent / "pyproject.toml"
        if pp.exists():
            m = re.search(
                r'^version\s*=\s*"([^"]+)"', pp.read_text(encoding="utf-8"), re.M
            )
            if m:
                return m.group(1)
            return None
    return None


def _from_metadata() -> str | None:
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version(_DIST_NAME)
        except PackageNotFoundError:
            return None
    except Exception:
        return None


def get_version() -> str:
    """Return the canonical kit version string."""
    return _from_pyproject() or _from_metadata() or "0+unknown"
