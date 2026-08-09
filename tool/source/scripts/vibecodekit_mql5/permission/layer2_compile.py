"""Permission Layer 2 — COMPILE-GATE.

Invokes `mql5-compile` (`vibecodekit_mql5.compile`) and asserts 0 errors.
Warnings are tolerated. If `--no-compile` is passed (or `MQL5_COMPILE`
is unavailable), the layer reads a pre-existing compile log JSON
instead so the layer remains usable on CI runners without MetaEditor.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_log_json(log_json: Path) -> dict[str, Any]:
    with log_json.open("r", encoding="utf-8") as f:
        return json.load(f)


def _run_compile(source: Path) -> dict[str, Any]:
    # Lazy import so tests can patch the wrapper without needing wine.
    from vibecodekit_mql5 import compile as compile_mod

    result = compile_mod.compile_mq5(source)
    # `compile_mq5` returns a `CompileResult` dataclass, not a dict. Convert
    # via the dataclass's `to_dict()` so this layer keeps a uniform dict
    # contract regardless of whether the result came from the live
    # compiler (dataclass) or a pre-existing log JSON (dict).
    data: dict[str, Any] = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    return {
        "success": bool(data.get("success", False)),
        "errors": list(data.get("errors") or []),
        "warnings": list(data.get("warnings") or []),
        "ex5_path": str(data.get("ex5_path") or ""),
    }


def gate(source: Path, log_json: Path | None = None) -> dict[str, Any]:
    if log_json:
        compile_result = _load_log_json(log_json)
    else:
        compile_result = _run_compile(source)
    err_count = len(compile_result.get("errors", []))
    ok = err_count == 0
    return {
        "ok": ok,
        "errors": compile_result.get("errors", []),
        "warnings": compile_result.get("warnings", []),
        "ex5_path": compile_result.get("ex5_path", ""),
        "path": str(source),
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="mql5-permission-layer2")
    ap.add_argument("source", type=Path)
    ap.add_argument("--log-json", type=Path, default=None,
                    help="path to a pre-existing compile log JSON")
    args = ap.parse_args()
    result = gate(args.source, args.log_json)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
