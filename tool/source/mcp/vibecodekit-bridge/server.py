"""vibecodekit-bridge MCP server.

JSON-RPC 2.0 over stdio. Same skeleton as ``mcp/metaeditor-bridge/server.py``.

This bridge wraps the kit's high-level CLI surface (``spec_from_prompt``,
``spec_schema``, ``auto_build`` pipeline, ``permission.orchestrator``) so
AI coding agents (Codex CLI, Claude Code, Cursor, Devin) can drive the
full build-verify loop through ``tools/call``. Each tool stays a thin
shim — all real work happens in ``vibecodekit_mql5``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[1] / "scripts"))
sys.path.insert(0, str(_HERE))

from bridge_tools import DISPATCH, TOOL_SCHEMAS  # noqa: E402

SERVER_NAME = "vibecodekit-bridge"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"


# Pre-built lookup of ``tool name → list of required argument keys`` so the
# JSON-RPC dispatcher can enforce ``inputSchema.required`` *before* the
# tool function is called. Smoke-test gap G2 in
# ``/home/ubuntu/work/smoke-test/REPORT.md`` flagged that the server
# previously let calls through with missing required keys, leaving each
# tool to fail gracefully on its own — inconsistent across the 29-tool
# surface and not what the MCP / JSON-RPC 2.0 spec calls for.
_REQUIRED_BY_TOOL: dict[str, list[str]] = {
    schema["name"]: list(schema.get("inputSchema", {}).get("required", []))
    for schema in TOOL_SCHEMAS
}


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    """Return a JSON-RPC response dict (or None for notifications)."""
    rid = request.get("id")
    method = request.get("method", "")
    params = request.get("params") or {}

    if method == "initialize":
        return _ok(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "tools/list":
        return _ok(rid, {"tools": TOOL_SCHEMAS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = DISPATCH.get(name)
        if fn is None:
            return _err(rid, -32601, f"unknown tool: {name}")
        # PR-13 (gap G2): enforce ``inputSchema.required`` here so every
        # tool gets a uniform JSON-RPC error envelope when the caller
        # forgets a required key, instead of relying on each handler to
        # check for ``None`` and return a tool-local error string.
        missing = _missing_required(name, args)
        if missing:
            return _err(
                rid, -32602,
                f"tool {name}: missing required arguments: {missing}",
            )
        try:
            result = fn(args)
        except Exception as exc:  # noqa: BLE001
            return _err(rid, -32000, f"tool {name} failed: {exc}")
        return _ok(rid, {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "isError": False,
        })
    if method.startswith("notifications/"):
        return None
    return _err(rid, -32601, f"method not found: {method}")


def _ok(rid: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _missing_required(tool_name: str, args: dict[str, Any]) -> list[str]:
    """Return the subset of required keys absent from ``args``.

    A key is considered "missing" when it is not in ``args`` at all, or
    when its value is ``None``. We deliberately do not treat empty
    strings / 0 / empty lists as missing — those are valid intentional
    inputs for some tools (e.g. an empty ``extra_args`` list).
    """
    required = _REQUIRED_BY_TOOL.get(tool_name, [])
    return [k for k in required if args.get(k) is None]


def serve(stdin: Any = sys.stdin, stdout: Any = sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is None:
            continue
        stdout.write(json.dumps(resp) + "\n")
        stdout.flush()


if __name__ == "__main__":
    serve()
