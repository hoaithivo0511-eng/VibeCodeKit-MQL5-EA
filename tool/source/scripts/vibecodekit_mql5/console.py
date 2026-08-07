"""Console encoding helpers for CLI entrypoints."""
from __future__ import annotations

import sys


def ensure_utf8_stdio() -> None:
    """Prefer UTF-8 for stdout/stderr when supported by the host stream."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
