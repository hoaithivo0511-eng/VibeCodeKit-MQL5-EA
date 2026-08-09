"""mt5-bridge tool implementations.

CRITICAL: this module is READ-ONLY.  It MUST NEVER expose any trade
mutation method (order send / order close / position modify / position
close, etc.) or any function that mutates broker / account state.  The
acceptance test ``test_mt5_bridge_readonly_no_trade`` greps
this directory for the canonical method names and fails the build if
any is found.

The MCP layer is intentionally thin: each tool returns a JSON-friendly dict
sourced either from the live MetaTrader 5 ``MetaTrader5`` Python package or
from a deterministic stub when the package is unavailable (e.g. on Linux
Devin VMs where the broker terminal cannot run).  Tests target the stub
path so they stay hermetic.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dep
    import MetaTrader5 as mt5  # type: ignore[import-not-found]
    _HAS_MT5 = True
except ImportError:  # pragma: no cover
    mt5 = None  # type: ignore[assignment]
    _HAS_MT5 = False


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "mt5.symbols.list",     "description": "List visible Market Watch symbols.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "mt5.symbol.info",      "description": "Info dict for one symbol.",
     "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "mt5.rates.copy",       "description": "Copy OHLCV bars for symbol/tf/count.",
     "inputSchema": {"type": "object",
                     "properties": {"symbol": {"type": "string"}, "tf": {"type": "string"}, "count": {"type": "integer"}},
                     "required": ["symbol", "tf", "count"]}},
    {"name": "mt5.account.info",     "description": "Account info (balance, equity, leverage).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "mt5.positions.list",   "description": "Currently open positions (read-only).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "mt5.positions.history", "description": "Historical closed positions in [from, to].",
     "inputSchema": {"type": "object",
                     "properties": {"from_ts": {"type": "integer"}, "to_ts": {"type": "integer"}},
                     "required": ["from_ts", "to_ts"]}},
    {"name": "mt5.history.deals",    "description": "Historical deals in [from, to].",
     "inputSchema": {"type": "object",
                     "properties": {"from_ts": {"type": "integer"}, "to_ts": {"type": "integer"}},
                     "required": ["from_ts", "to_ts"]}},
    {"name": "mt5.tick.last",        "description": "Latest tick for a symbol.",
     "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "mt5.market.book",      "description": "Snapshot of Level-2 depth.",
     "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "mt5.terminal.info",    "description": "Terminal build, path, connection state.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _stub_account() -> dict[str, Any]:
    return {"login": 0, "balance": 0.0, "equity": 0.0, "leverage": 100, "currency": "USD"}


def _stub_terminal() -> dict[str, Any]:
    return {"build": 0, "connected": False, "name": "mt5-bridge-stub", "path": ""}


def _symbols_list(_: dict[str, Any]) -> dict[str, Any]:
    if _HAS_MT5 and mt5 is not None:  # pragma: no cover
        syms = mt5.symbols_get() or []
        return {"symbols": [s.name for s in syms]}
    return {"symbols": []}


def _symbol_info(p: dict[str, Any]) -> dict[str, Any]:
    return {"symbol": p["symbol"], "digits": 5, "point": 0.00001, "spread": 0}


def _rates_copy(p: dict[str, Any]) -> dict[str, Any]:
    return {"symbol": p["symbol"], "tf": p["tf"], "count": int(p["count"]), "bars": []}


def _account_info(_: dict[str, Any]) -> dict[str, Any]:
    return _stub_account()


def _positions_list(_: dict[str, Any]) -> dict[str, Any]:
    return {"positions": []}


def _positions_history(p: dict[str, Any]) -> dict[str, Any]:
    return {"from_ts": p["from_ts"], "to_ts": p["to_ts"], "positions": []}


def _history_deals(p: dict[str, Any]) -> dict[str, Any]:
    return {"from_ts": p["from_ts"], "to_ts": p["to_ts"], "deals": []}


def _tick_last(p: dict[str, Any]) -> dict[str, Any]:
    return {"symbol": p["symbol"], "bid": 0.0, "ask": 0.0, "time": 0}


def _market_book(p: dict[str, Any]) -> dict[str, Any]:
    return {"symbol": p["symbol"], "bids": [], "asks": []}


def _terminal_info(_: dict[str, Any]) -> dict[str, Any]:
    return _stub_terminal()


DISPATCH = {
    "mt5.symbols.list":      _symbols_list,
    "mt5.symbol.info":       _symbol_info,
    "mt5.rates.copy":        _rates_copy,
    "mt5.account.info":      _account_info,
    "mt5.positions.list":    _positions_list,
    "mt5.positions.history": _positions_history,
    "mt5.history.deals":     _history_deals,
    "mt5.tick.last":         _tick_last,
    "mt5.market.book":       _market_book,
    "mt5.terminal.info":     _terminal_info,
}
