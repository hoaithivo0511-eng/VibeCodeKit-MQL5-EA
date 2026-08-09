"""metaeditor-bridge tool implementations.

These are the Python functions invoked by ``server.py`` to satisfy MCP
``tools/call`` requests.  Each tool is a thin shim over the kit's existing
modules so the MCP layer stays < 200 LOC.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import re

from vibecodekit_mql5 import compile as vck_compile  # noqa: A004

_RE_INCLUDE = re.compile(r'#include\s+["<]([^">]+)[">]')

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "metaeditor.compile",
        "description": "Compile an .mq5/.mqh via MetaEditor; returns success + errors/warnings.",
        "inputSchema": {
            "type": "object",
            "properties": {"mq5_path": {"type": "string"}},
            "required": ["mq5_path"],
        },
    },
    {
        "name": "metaeditor.parse_log",
        "description": "Parse a MetaEditor build log; returns structured errors/warnings.",
        "inputSchema": {
            "type": "object",
            "properties": {"log_path": {"type": "string"}},
            "required": ["log_path"],
        },
    },
    {
        "name": "metaeditor.includes_resolve",
        "description": "List #include directives transitively reachable from an .mq5.",
        "inputSchema": {
            "type": "object",
            "properties": {"mq5_path": {"type": "string"}},
            "required": ["mq5_path"],
        },
    },
]


def compile_mq5(mq5_path: str) -> dict[str, Any]:
    rep = vck_compile.compile_mq5(Path(mq5_path))
    return {
        "success": rep.success,
        "errors": list(rep.errors),
        "warnings": list(rep.warnings),
        "ex5_path": rep.ex5_path,
    }


def parse_log(log_path: str) -> dict[str, Any]:
    text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    rep = vck_compile.parse_log(text)
    return {
        "success": rep.success,
        "errors": list(rep.errors),
        "warnings": list(rep.warnings),
    }


def includes_resolve(mq5_path: str) -> dict[str, Any]:
    """Best-effort transitive #include walk; depth-bounded to avoid cycles."""
    seen: set[str] = set()
    root = Path(mq5_path).resolve()

    def walk(path: Path) -> None:
        if str(path) in seen or not path.exists():
            return
        seen.add(str(path))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for inc in _RE_INCLUDE.findall(text):
            child = (path.parent / inc).resolve()
            walk(child)

    walk(root)
    # Drop the root itself from the resolved list.
    return {"includes": sorted(s for s in seen if Path(s) != root)}


DISPATCH = {
    "metaeditor.compile":          lambda p: compile_mq5(p["mq5_path"]),
    "metaeditor.parse_log":        lambda p: parse_log(p["log_path"]),
    "metaeditor.includes_resolve": lambda p: includes_resolve(p["mq5_path"]),
}
