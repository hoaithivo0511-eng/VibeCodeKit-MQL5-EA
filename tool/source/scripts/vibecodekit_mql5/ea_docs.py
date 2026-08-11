"""Compatibility metadata helpers for the public EA documentation renderer.

The MCP bridge historically imported this module, while the renderer data
model moved to :mod:`vibecodekit_mql5.ea_docs_render`.  Keep the small metadata
contract separate so older bridge clients remain importable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ._version import get_version


def _kit_version() -> str:
    """Return the single-source package version."""

    return get_version()


@dataclass(frozen=True)
class BuildMeta:
    """Deterministic metadata passed to the EA documentation renderer."""

    ea_version: str
    kit_version: str
    built_from: str
    built_at_utc: str

    @classmethod
    def now(
        cls,
        *,
        ea_version: str,
        kit_version: str,
        built_from: str,
    ) -> BuildMeta:
        return cls(
            ea_version=ea_version,
            kit_version=kit_version,
            built_from=built_from,
            built_at_utc=datetime.now(timezone.utc).isoformat(),
        )
