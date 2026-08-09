"""Structured graph analysis for MQL5 EA source (v2.5 hardening, #6).

Upgrades the regex-only scanner with graph-grounded analysis built on the
Stage-0 symbol graph (:mod:`mq5_symbols`). Four graphs:

  call_graph        function def<->call edges; functions unreachable from any
                    terminal event handler.
  input_usage       input declaration -> use sites; inputs never used.
  order_lifecycle   OrderSend / CTrade.Buy|Sell -> retcode check ->
                    OnTradeTransaction reconciliation.
  risk_invariant    stop-loss / drawdown-cap / max-level / lot-scaling caps.

Each graph contributes evidence-bearing findings (same dict shape used across
the senior review) so they fold into reports without changing any contract.
The regex heuristics in ``scan_ea`` / ``lint`` stay as a fallback; the graphs
only *add precision* -- they reason over stripped code (no string/comment
false hits) and require a positive cap edge before clearing a risk smell.

Deliberately heuristic and dependency-free: every finding is advisory and
never asserts PASS/READY on its own.
"""
from __future__ import annotations

import re
from typing import Any

from .mq5_symbols import (
    EVENT_HANDLERS,
    SymbolGraph,
    build_symbol_graph,
    merge_sources,
    strip_comments_and_strings,
)

_CALL = re.compile(r"([A-Za-z_]\w*)\s*\(")


def _finding(severity: str, category: str, title: str, evidence: str,
             recommendation: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "title": title,
        "evidence": evidence,
        "recommendation": recommendation,
        "source": "graph",
    }


# --- call graph ------------------------------------------------------------
def build_call_graph(graph: SymbolGraph) -> dict[str, Any]:
    """def<->call edges + functions unreachable from any event handler.

    A user function reachable only through a chain that never starts at a
    terminal entry point (OnInit/OnTick/...) is structurally dead even if its
    name appears in source, which a flat ``reference_count`` cannot prove.
    """
    names = graph.function_names()
    edges: dict[str, list[str]] = {}
    for fn in graph.functions:
        body = strip_comments_and_strings(fn.body)
        callees = {
            m.group(1)
            for m in _CALL.finditer(body)
            if m.group(1) in names and m.group(1) != fn.name
        }
        edges[fn.name] = sorted(callees)

    reachable: set[str] = set()
    stack = [fn.name for fn in graph.functions if fn.name in EVENT_HANDLERS]
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        stack.extend(c for c in edges.get(node, []) if c not in reachable)

    unreachable = sorted(
        n for n in names if n not in reachable and n not in EVENT_HANDLERS
    )
    return {"edges": edges, "reachable": sorted(reachable), "unreachable": unreachable}


# --- input-usage graph -----------------------------------------------------
def build_input_usage(graph: SymbolGraph, text: str) -> dict[str, Any]:
    code = strip_comments_and_strings(text)
    usage: dict[str, int] = {}
    unused: list[str] = []
    for name in graph.inputs:
        # occurrences minus the single declaration site
        n = len(re.findall(r"\b" + re.escape(name) + r"\b", code))
        uses = max(0, n - 1)
        usage[name] = uses
        if uses == 0:
            unused.append(name)
    return {"usage": usage, "unused": sorted(unused)}


# --- order-lifecycle graph -------------------------------------------------
_RAW_ORDERSEND = re.compile(r"(?<![.\w])OrderSend\s*\(")
_ASYNC = re.compile(r"OrderSendAsync\s*\(|SetAsyncMode\s*\(\s*true\s*\)", re.I)
_CTRADE_OP = re.compile(r"\.\s*(?:Buy|Sell|PositionClose|PositionModify)\s*\(")
_RETCODE = re.compile(
    r"\.retcode\b|ResultRetcode\s*\(|MqlTradeResult|TRADE_RETCODE|retcode\s*==",
    re.I,
)


def analyze_order_lifecycle(text: str) -> dict[str, Any]:
    code = strip_comments_and_strings(text)
    has_raw = bool(_RAW_ORDERSEND.search(code))
    has_async = bool(_ASYNC.search(code))
    has_ctrade = bool(_CTRADE_OP.search(code))
    has_hook = "OnTradeTransaction" in code
    has_retcode = bool(_RETCODE.search(code))
    sent = has_raw or has_async or has_ctrade

    stages = {
        "send_detected": sent,
        "async": has_async,
        "retcode_checked": has_retcode,
        "transaction_hook": has_hook,
    }
    issues: list[dict[str, Any]] = []
    if has_async and not has_hook:
        issues.append(_finding(
            "critical", "execution",
            "Async order send without OnTradeTransaction hook",
            "order-lifecycle graph: OrderSendAsync/SetAsyncMode(true) present "
            "but no OnTradeTransaction handler -- async fills/cancels are never "
            "reconciled.",
            "Add OnTradeTransaction and forward it to the async executor to "
            "track DEAL_ADD / position closure.",
        ))
    if (has_raw or has_async) and not has_retcode:
        issues.append(_finding(
            "error", "execution",
            "Order send without return-code check",
            "order-lifecycle graph: OrderSend/OrderSendAsync called but no "
            "MqlTradeResult.retcode / ResultRetcode() inspection found.",
            "Inspect result.retcode (10004 requote, 10016 invalid stops, "
            "10019 no money, 10027 autotrading off) and handle/retry.",
        ))
    return {"stages": stages, "issues": issues}


# --- risk-invariant graph --------------------------------------------------
_LOT_SCALE = re.compile(
    r"(?:lot|lots|volume)\w*\s*\*?=\s*[^;]*?\b(?:[2-9]|1\.[5-9])\b"
    r"|(?:lot|lots|volume)\w*\s*\*\s*(?:lot|lots|volume|mult|factor|coef)"
    r"|lotmultiplier|martingale",
    re.I,
)
_LEVEL_CAP = re.compile(
    # Recognise input-named caps like InpMaxGridLevels / MaxGridLevels and
    # guard counters, not just the literal "MaxLevels" token. A real
    # InpMaxGridLevels cap was previously ignored, producing a spurious
    # "Lot scaling without a hard cap" critical (v2.5.0 QA review).
    r"max\w*levels?|levels?\w*(?:allowed|cap|limit|max)|levelallowed|"
    r"max_?levels?|maxtrades|max_?positions|maxorders|grid\w*levels?|"
    r"max_?grid",
    re.I,
)
_VOL_CLAMP = re.compile(
    r"symbol_volume_max|symbol_volume_min|volume_max|volume_step|"
    r"mathmin\s*\(|normalizevolume|checkvolume|clamp",
    re.I,
)
_DD_STOP = re.compile(
    r"maxdd|max_dd|drawdown|muststop|hardstop|hard_stop|equity_?stop|"
    r"account_equity|accountinfodouble\s*\(\s*account_equity",
    re.I,
)
_SL = re.compile(r"\bsl\b|stoploss|stop_loss|setsl|sl\s*=|request\.sl", re.I)


def analyze_risk_invariants(text: str) -> dict[str, Any]:
    code = strip_comments_and_strings(text)
    lot_scaling = bool(_LOT_SCALE.search(code))
    level_cap = bool(_LEVEL_CAP.search(code))
    vol_clamp = bool(_VOL_CLAMP.search(code))
    dd_stop = bool(_DD_STOP.search(code))
    has_sl = bool(_SL.search(code))

    invariants = {
        "lot_scaling_detected": lot_scaling,
        "level_cap": level_cap,
        "volume_clamp": vol_clamp,
        "drawdown_stop": dd_stop,
        "stop_loss": has_sl,
    }
    issues: list[dict[str, Any]] = []
    if lot_scaling and not (level_cap or vol_clamp):
        issues.append(_finding(
            "critical", "risk",
            "Lot scaling without a hard cap",
            "risk-invariant graph: martingale/multiplier sizing detected with "
            "no MaxLevels/LevelAllowed and no broker volume clamp -- exposure "
            "is unbounded.",
            "Cap ladder levels AND clamp volume to SYMBOL_VOLUME_MIN/MAX/STEP "
            "before every send.",
        ))
    if lot_scaling and not dd_stop:
        issues.append(_finding(
            "error", "risk",
            "Lot scaling without account drawdown stop",
            "risk-invariant graph: scaling sizing present but no equity / "
            "max-drawdown hard stop found.",
            "Add an account-level max-drawdown stop that freezes new exposure "
            "and flattens the basket.",
        ))
    return {"invariants": invariants, "issues": issues}


# --- basket-integrity graph (netting/hedging hazard) -----------------------
_POS_LOOP = re.compile(r"PositionsTotal\s*\(", re.I)
_POS_CLOSE = re.compile(r"PositionClose\w*\s*\(|CloseBasket|CloseAll|ClosePositionAll", re.I)
_POS_SYMBOL = re.compile(r"PositionGetSymbol\s*\(|==\s*_Symbol|Symbol\s*\(\s*\)\s*==", re.I)
_POS_MAGIC = re.compile(
    r"Magic\s*\(\s*\)\s*==|\bm_magic\b|POSITION_MAGIC|PositionGetInteger\s*\([^)]*MAGIC",
    re.I,
)


def analyze_basket_integrity(text: str) -> dict[str, Any]:
    """Detect a basket/position loop that closes by symbol but not by magic.

    On a shared or netting account, closing every position that merely matches
    the symbol will silently flatten OTHER EAs' (or manual) trades. A correct
    basket operation must additionally filter by the EA's magic number. This
    is the netting/hedging mismatch hazard the regex scanner missed.
    """
    code = strip_comments_and_strings(text)
    has_loop = bool(_POS_LOOP.search(code))
    closes = bool(_POS_CLOSE.search(code))
    symbol_filter = bool(_POS_SYMBOL.search(code))
    magic_filter = bool(_POS_MAGIC.search(code))
    basket_close = has_loop and closes

    invariants = {
        "basket_close_loop": basket_close,
        "symbol_filter": symbol_filter,
        "magic_filter": magic_filter,
    }
    issues: list[dict[str, Any]] = []
    if basket_close and symbol_filter and not magic_filter:
        issues.append(_finding(
            "error", "risk",
            "Basket close without magic filter (netting/hedging hazard)",
            "basket-integrity graph: a PositionsTotal() loop closes positions "
            "matched by symbol only, with no magic-number filter -- on a "
            "shared/netting account this flattens other EAs' or manual trades.",
            "Filter the loop by PositionGetInteger(POSITION_MAGIC)==InpMagic "
            "(and SelectByIndex before reading Magic) before closing.",
        ))
    return {"invariants": invariants, "issues": issues}


# --- aggregate -------------------------------------------------------------
def analyze_graphs(files: dict[str, str]) -> dict[str, Any]:
    """Run all four graphs over a whole project (dict of rel-path -> source)."""
    merged = merge_sources(files) if files else ""
    graph = build_symbol_graph(merged, source="<project>")
    call_graph = build_call_graph(graph)
    input_usage = build_input_usage(graph, merged)
    lifecycle = analyze_order_lifecycle(merged)
    risk = analyze_risk_invariants(merged)
    basket = analyze_basket_integrity(merged)

    issues: list[dict[str, Any]] = []
    issues.extend(lifecycle["issues"])
    issues.extend(risk["issues"])
    issues.extend(basket["issues"])
    for name in input_usage["unused"]:
        issues.append(_finding(
            "warn", "input", f"Input never used: {name}",
            "input-usage graph: 0 use sites outside the declaration.",
            "Wire the input into logic/docs or remove it.",
        ))
    for name in call_graph["unreachable"]:
        issues.append(_finding(
            "info", "code_quality", f"Function unreachable from any event handler: {name}",
            "call graph: no path from OnInit/OnTick/... reaches this function.",
            "Wire it into the call graph or remove it.",
        ))

    return {
        "call_graph": {
            "function_count": len(graph.functions),
            "edges": call_graph["edges"],
            "unreachable": call_graph["unreachable"],
        },
        "input_usage": input_usage,
        "order_lifecycle": lifecycle,
        "risk_invariant": risk,
        "basket_integrity": basket,
        "issues": issues,
    }


def analyze_source_graphs(text: str, *, source: str = "<text>") -> dict[str, Any]:
    """Convenience wrapper for a single source buffer."""
    return analyze_graphs({source: text})


__all__ = [
    "build_call_graph",
    "build_input_usage",
    "analyze_order_lifecycle",
    "analyze_risk_invariants",
    "analyze_basket_integrity",
    "analyze_graphs",
    "analyze_source_graphs",
]
