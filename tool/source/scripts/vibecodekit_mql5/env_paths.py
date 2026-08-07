"""Single source of truth for MetaEditor / MT5 terminal path resolution.

Historically different modules read different environment-variable names, which
could make ``mql5-doctor`` go green while ``capability`` reported a missing
backend (and vice-versa). Every component now resolves these two paths through
the SAME ordered union of accepted names defined here, so a single env var
works everywhere.

Accepted names (first non-empty wins):
  MetaEditor : METAEDITOR_PATH, METAEDITOR64
  Terminal   : MQL5_TERMINAL_PATH, MT5_TERMINAL_PATH, MT5_TERMINAL64
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

METAEDITOR_ENV_VARS: tuple[str, ...] = ("METAEDITOR_PATH", "METAEDITOR64")
TERMINAL_ENV_VARS: tuple[str, ...] = (
    "MQL5_TERMINAL_PATH",
    "MT5_TERMINAL_PATH",
    "MT5_TERMINAL64",
)


def _first_env(names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def resolve_metaeditor_path(override: Optional[str] = None) -> Optional[str]:
    """Return the MetaEditor path from ``override`` or any accepted env var."""
    return override or _first_env(METAEDITOR_ENV_VARS)


def resolve_terminal_path(override: Optional[str] = None) -> Optional[str]:
    """Return the MT5 terminal path from ``override`` or any accepted env var."""
    return override or _first_env(TERMINAL_ENV_VARS)


def metaeditor_env_present() -> bool:
    """True if any accepted MetaEditor env var is set and non-empty."""
    return _first_env(METAEDITOR_ENV_VARS) is not None


def terminal_env_present() -> bool:
    """True if any accepted MT5 terminal env var is set and non-empty."""
    return _first_env(TERMINAL_ENV_VARS) is not None
