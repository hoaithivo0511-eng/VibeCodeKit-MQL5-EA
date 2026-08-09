"""mql5-mt5-python — live-environment evidence worker via the MetaTrader5
Python package.

The official ``MetaTrader5`` PyPI package connects to a *running* MT5 terminal
on the same machine and exposes account/symbol/history/order_check/order_send.
This worker uses it to capture **real, hashed environment evidence** and to run
**real broker-side order validation** (``order_check``) that no static analysis
can provide.

Honesty contract (kit rule, enforced everywhere):

* The ``MetaTrader5`` package is import-guarded. If it is missing OR no
  terminal connection can be established (the normal case on this Linux build
  / CI), every command returns **UNTESTABLE** with a non-zero exit code and an
  ``ok=False`` envelope. It NEVER fabricates account/symbol data.
* Scope is honest: the package can read account/symbol/history and validate or
  send orders. It CANNOT drive the Strategy Tester programmatically, so this
  worker makes no backtest claims — backtests stay with ``mql5-tester-run`` /
  the Windows worker. This is live-environment evidence + order pre-flight
  only.

Commands::

    python -m vibecodekit_mql5.mt5_python_worker probe
    python -m vibecodekit_mql5.mt5_python_worker capture --project-dir . [--symbol XAUUSD]
    python -m vibecodekit_mql5.mt5_python_worker order-check --symbol XAUUSD --volume 0.10 --price 2400.0

Exit codes::

    0 — command succeeded against a live terminal
    3 — UNTESTABLE: MetaTrader5 package or live terminal unavailable
    2 — invocation error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TOOL = "mql5-mt5-python"
EXIT_UNTESTABLE = 3


def _import_mt5():
    """Return the imported MetaTrader5 module, or ``None`` if unavailable."""
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception:  # noqa: BLE001 — ImportError or platform load failure
        return None
    return mt5


def probe_environment() -> dict[str, Any]:
    """Best-effort probe. Always honest: returns available=False when the
    package is missing or no terminal can be initialised."""
    mt5 = _import_mt5()
    if mt5 is None:
        return {"available": False, "reason": "MetaTrader5 package not importable",
                "status": "UNTESTABLE"}
    try:
        ok = bool(mt5.initialize())
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"initialize() raised: {exc}",
                "status": "UNTESTABLE"}
    if not ok:
        err = None
        try:
            err = mt5.last_error()
        except Exception:  # noqa: BLE001
            pass
        return {"available": False, "reason": f"terminal not connected: {err}",
                "status": "UNTESTABLE"}
    info: dict[str, Any] = {"available": True, "status": "PASS"}
    try:
        info["version"] = list(mt5.version())
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            mt5.shutdown()
        except Exception:  # noqa: BLE001
            pass
    return info


def _as_dict(obj: Any) -> Any:
    """Convert a MetaTrader5 named-tuple-ish struct to a plain dict."""
    if obj is None:
        return None
    if hasattr(obj, "_asdict"):
        return dict(obj._asdict())
    return obj


def capture_environment_evidence(project_dir: Path, symbol: str | None = None) -> dict[str, Any]:
    """Write real terminal/account/version evidence under
    ``<project_dir>/evidence/mt5-python/``. UNTESTABLE if no live terminal."""
    mt5 = _import_mt5()
    if mt5 is None:
        return {"status": "UNTESTABLE", "reason": "MetaTrader5 package not importable"}
    try:
        if not mt5.initialize():
            return {"status": "UNTESTABLE",
                    "reason": f"terminal not connected: {mt5.last_error()}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNTESTABLE", "reason": f"initialize() raised: {exc}"}

    out_dir = Path(project_dir) / "evidence" / "mt5-python"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    try:
        payloads = {
            "version.json": list(mt5.version()),
            "terminal_info.json": _as_dict(mt5.terminal_info()),
            "account_info.json": _as_dict(mt5.account_info()),
        }
        if symbol:
            payloads[f"symbol_{symbol}.json"] = _as_dict(mt5.symbol_info(symbol))
        for name, data in payloads.items():
            path = out_dir / name
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            written.append(str(path))
    finally:
        try:
            mt5.shutdown()
        except Exception:  # noqa: BLE001
            pass
    return {"status": "PASS", "evidence": written}


def order_check_normalization(symbol: str, volume: float, price: float) -> dict[str, Any]:
    """Real broker-side pre-flight using ``mt5.symbol_info`` (volume/price
    normalization) and ``mt5.order_check`` (margin/stops validation).
    UNTESTABLE if no live terminal."""
    mt5 = _import_mt5()
    if mt5 is None:
        return {"status": "UNTESTABLE", "reason": "MetaTrader5 package not importable"}
    try:
        if not mt5.initialize():
            return {"status": "UNTESTABLE",
                    "reason": f"terminal not connected: {mt5.last_error()}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNTESTABLE", "reason": f"initialize() raised: {exc}"}
    try:
        si = mt5.symbol_info(symbol)
        if si is None:
            return {"status": "UNTESTABLE", "reason": f"symbol not found: {symbol}"}
        step = getattr(si, "volume_step", 0.0) or 0.0
        vmin = getattr(si, "volume_min", 0.0) or 0.0
        vmax = getattr(si, "volume_max", 0.0) or 0.0
        digits = getattr(si, "digits", 0) or 0
        norm_vol = volume
        if step > 0:
            norm_vol = round(round(volume / step) * step, 8)
        if vmin:
            norm_vol = max(norm_vol, vmin)
        if vmax:
            norm_vol = min(norm_vol, vmax)
        norm_price = round(price, digits) if digits else price
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(norm_vol),
            "type": mt5.ORDER_TYPE_BUY,
            "price": float(norm_price),
        }
        check = _as_dict(mt5.order_check(request))
        return {"status": "PASS", "normalized": {"volume": norm_vol, "price": norm_price,
                                                 "digits": digits, "volume_step": step},
                "order_check": check}
    finally:
        try:
            mt5.shutdown()
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    common = argparse.ArgumentParser(add_help=False)
    _agent_io.add_json_flag(common)
    ap = argparse.ArgumentParser(prog=TOOL, description=__doc__.splitlines()[0],
                                 parents=[common])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("probe", parents=[common],
                   help="Probe MetaTrader5 package + terminal availability.")
    cap = sub.add_parser("capture", parents=[common],
                         help="Capture live terminal/account evidence.")
    cap.add_argument("--project-dir", type=Path, default=Path("."))
    cap.add_argument("--symbol", default=None)
    oc = sub.add_parser("order-check", parents=[common],
                        help="Validate+normalize an order via the broker.")
    oc.add_argument("--symbol", required=True)
    oc.add_argument("--volume", type=float, required=True)
    oc.add_argument("--price", type=float, required=True)
    args = ap.parse_args(argv)

    if args.command == "probe":
        data = probe_environment()
    elif args.command == "capture":
        data = capture_environment_evidence(args.project_dir, args.symbol)
    elif args.command == "order-check":
        data = order_check_normalization(args.symbol, args.volume, args.price)
    else:  # pragma: no cover
        ap.error("unknown command")
        return 2

    untestable = data.get("status") == "UNTESTABLE"
    ok = data.get("status") == "PASS"
    exit_code = 0 if ok else (EXIT_UNTESTABLE if untestable else 1)
    env = _agent_io.Envelope(
        tool=TOOL, ok=ok, exit_code=exit_code,
        summary=(f"{args.command}: {data.get('status')}"
                 + (f" — {data.get('reason')}" if data.get("reason") else "")),
        data=data,
        evidence=data.get("evidence", []) if isinstance(data.get("evidence"), list) else [],
        matrix_dim="d_operations", matrix_axis="static",
        matrix_status="PASS" if ok else ("N/A" if untestable else "FAIL"),
    )
    if getattr(args, "emit_json", False):
        _agent_io.emit(env)
    else:
        if untestable:
            _agent_io.diag(f"[{TOOL}] UNTESTABLE: {data.get('reason')}")
        sys.stdout.write(json.dumps(data, indent=2, default=str) + "\n")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
