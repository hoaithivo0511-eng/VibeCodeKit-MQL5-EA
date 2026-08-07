"""Structured deprecation notices for legacy console entrypoints.

The notice is written to *stderr* as a single JSON line so it never corrupts a
tool's stdout JSON envelope, and it is non-fatal (the shimmed command still
runs). Machine consumers can grep stderr for ``"deprecation"`` and migrate.
"""
from __future__ import annotations

import json
import sys
from typing import TextIO


def deprecation_payload(old: str, replacement: str, *, removed_in: str | None = None) -> dict:
    notice: dict = {
        "command": old,
        "status": "deprecated",
        "use_instead": replacement,
    }
    if removed_in:
        notice["removed_in"] = removed_in
    return {"deprecation": notice}


def warn_deprecated(
    old: str,
    replacement: str,
    *,
    removed_in: str | None = None,
    stream: TextIO | None = None,
) -> None:
    """Emit a one-line deprecation JSON to stderr (non-fatal)."""
    out = stream if stream is not None else sys.stderr
    out.write(json.dumps(deprecation_payload(old, replacement, removed_in=removed_in)) + "\n")
