"""mt5-bridge MCP server (READ-ONLY).

JSON-RPC 2.0 over stdio.  See ``mcp/metaeditor-bridge/server.py`` for the
shared shape.  The trade-method enforcement lives in ``tools.py`` — this
file is intentionally trade-method-free.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[1] / "scripts"))
sys.path.insert(0, str(_HERE))

from mt5_tools import DISPATCH, TOOL_SCHEMAS  # noqa: E402

SERVER_NAME = "mt5-bridge"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

_REQUIRED_BY_TOOL: dict[str, list[str]] = {
    schema["name"]: list(schema.get("inputSchema", {}).get("required", []))
    for schema in TOOL_SCHEMAS
}


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
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
        if not isinstance(args, dict):
            return _err(rid, -32602, f"tool {name}: arguments must be an object")
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
    return [key for key in _REQUIRED_BY_TOOL.get(tool_name, []) if args.get(key) is None]


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
