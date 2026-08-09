"""PR-11 — recogniser tables + low-level match helpers for the prompt parser.

Carved out of :mod:`vibecodekit_mql5.spec_from_prompt` so the parser
module stays under the 400-LOC audit ceiling. Everything here is
deterministic / regex-only — no LLM call, no network.

Two layers:

* **Tables** — `_FX_MAJORS`, `_SYMBOLS`, `_TIMEFRAMES`, `_PRESET_KEYWORDS`,
  `_STACK_KEYWORDS`, `_SIGNAL_KEYWORDS`. The first hit in source-order
  wins so callers can short-circuit a generic "stdlib" mention with a
  more specific archetype keyword.
* **Helpers** — `match_preset`, `match_stack`, `match_symbol`,
  `match_timeframe`, `match_risk`, `match_signals`, `match_name`,
  `looked_up`. Each returns a value the schema validator accepts.
"""

from __future__ import annotations

import re


# ─────────────────────────────────────────────────────────────────────────────
# Recogniser tables
# ─────────────────────────────────────────────────────────────────────────────

# Trading pairs the kit's archetypes can target. We deliberately keep this
# explicit instead of a generic 6-letter regex because plain word boundaries
# would happily match prose tokens like ``"DOMAIN"`` or ``"BUFFER"``.
_FX_MAJORS = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD", "EURCHF", "GBPCHF",
)
_METALS_CRYPTO = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD")
_INDICES = ("US30", "US500", "NAS100", "GER40", "UK100", "JPN225")

SYMBOLS: tuple[str, ...] = _FX_MAJORS + _METALS_CRYPTO + _INDICES

# Strategy Tester timeframes accepted by MetaTrader 5.
TIMEFRAMES: tuple[str, ...] = (
    "M1", "M2", "M3", "M4", "M5", "M6", "M10", "M12", "M15", "M20", "M30",
    "H1", "H2", "H3", "H4", "H6", "H8", "H12",
    "D1", "W1", "MN1",
)

# Keyword → (preset, stack). First hit in source order wins.
PRESET_KEYWORDS: tuple[tuple[str, tuple[str, str]], ...] = (
    (r"\btrend(?:[\s-]?follow(?:ing)?)?\b",  ("trend", "netting")),
    (r"\bmean[\s-]?revers(?:ion|ing)\b",     ("mean-reversion", "hedging")),
    (r"\bbreak[\s-]?out\b",                  ("breakout", "netting")),
    (r"\bscalp(?:ing|er)?\b",                ("scalping", "hedging")),
    (r"\bhft\b",                             ("hft-async", "netting")),
    (r"\bnews(?:[\s-]?trad(?:ing|e))?\b",    ("news-trading", "netting")),
    (r"\barbitrage\b",                       ("arbitrage-stat", "python-bridge")),
    (r"\bgrid\b",                            ("grid", "hedging")),
    (r"\bdca\b",                             ("dca", "hedging")),
    (r"\bhedg(?:e|ing)[\s-]?multi\b",        ("hedging-multi", "hedging")),
    (r"\bml[\s-]?onnx\b|\bonnx\b|\bmachine[\s-]?learn(?:ing)?\b",
                                             ("ml-onnx", "python-bridge")),
    (r"\bllm\b|\bgpt\b|\bclaude\b|\bollama\b",
                                             ("service-llm-bridge", "cloud-api")),
    (r"\bservice\b|\bdaemon\b",              ("service", "standalone")),
    (r"\bportfolio(?:[\s-]?basket)?\b|\bbasket\b",
                                             ("portfolio-basket", "netting")),
    (r"\bwizard\b",                          ("wizard-composable", "netting")),
    (r"\bstdlib\b|\bstandard[\s-]?library\b",("stdlib", "netting")),
)

# Stack overrides spotted after the preset has been chosen.
STACK_KEYWORDS: tuple[tuple[str, str], ...] = (
    (r"\bnetting\b",            "netting"),
    (r"\bhedg(?:e|ing)\b",      "hedging"),
    (r"\bpython[\s-]?bridge\b", "python-bridge"),
    (r"\bself[\s-]?hosted\b|\bollama\b",         "self-hosted-ollama"),
    (r"\bembedded\b|\bembedded[\s-]?onnx\b",     "embedded-onnx-llm"),
    (r"\bcloud(?:[\s-]?api)?\b|\bopenai\b|\bclaude\b",
                                                 "cloud-api"),
    (r"\bstandalone\b",         "standalone"),
)

# Indicator keywords used by the ``signals:`` block. Maps free-text to the
# canonical ``kind`` accepted by ``spec_schema.VALID_SIGNAL_KINDS``.
SIGNAL_KEYWORDS: tuple[tuple[str, str], ...] = (
    (r"\bmacd\b",                            "macd"),
    (r"\bsar\b|\bparabolic\b",               "sar"),
    (r"\brsi\b",                             "rsi"),
    (r"\bema[\s-]?cross\b|\bma[\s-]?cross\b","ema_cross"),
    (r"\bbb\b|\bbollinger\b|\bbbands\b",     "bbands"),
    (r"\batr[\s-]?break\b|\batr\b",          "atr_break"),
)

# Precompiled patterns kept here so the recogniser tables stay readable.
PRESET_KEYWORDS_PATTERNS = tuple((pat, *_) for pat, *_ in PRESET_KEYWORDS)


# ─────────────────────────────────────────────────────────────────────────────
# Low-level match helpers
# ─────────────────────────────────────────────────────────────────────────────

def looked_up(text: str, table) -> bool:
    """True iff *any* pattern in ``table`` matches ``text``."""
    return any(re.search(pat, text, re.IGNORECASE) for pat, *_ in table)


def match_preset(text: str) -> tuple[str, str]:
    for pat, (preset, stack) in PRESET_KEYWORDS:
        if re.search(pat, text, re.IGNORECASE):
            return preset, stack
    return "stdlib", "netting"


def match_stack(text: str, fallback: str) -> str:
    """Prefer explicit stack mentions over the preset default."""
    for pat, stack in STACK_KEYWORDS:
        if re.search(pat, text, re.IGNORECASE):
            return stack
    return fallback


def match_symbol(text: str) -> str:
    """Pick the first known trading symbol in the prompt; default EURUSD."""
    up = text.upper()
    for sym in SYMBOLS:
        # Word-boundary matching so ``EURUSDH1`` (without space) still parses.
        if re.search(rf"\b{sym}\b", up):
            return sym
    # Also accept slash forms like ``EUR/USD``.
    m = re.search(r"\b([A-Z]{3})\s*/\s*([A-Z]{3})\b", up)
    if m:
        joined = m.group(1) + m.group(2)
        if joined in SYMBOLS:
            return joined
    return "EURUSD"


def match_symbols(text: str) -> list[str]:
    """Return every known trading symbol mentioned, in textual order.

    The single-symbol :func:`match_symbol` only returns the first hit; a
    multi-symbol / portfolio prompt (e.g. "XAUUSD EURUSD GBPUSD") used to be
    silently collapsed to one symbol. Surfacing the full set lets the parser
    warn instead of dropping the requirement (v2.5.0 QA review, blocker #1).
    """
    up = text.upper()
    found: list[str] = []
    for sym in SYMBOLS:
        if re.search(rf"\b{sym}\b", up) and sym not in found:
            found.append(sym)
    for m in re.finditer(r"\b([A-Z]{3})\s*/\s*([A-Z]{3})\b", up):
        joined = m.group(1) + m.group(2)
        if joined in SYMBOLS and joined not in found:
            found.append(joined)
    found.sort(key=lambda s: up.find(s) if up.find(s) >= 0 else 10 ** 9)
    return found


def match_timeframe(text: str) -> str:
    up = text.upper()
    for tf in TIMEFRAMES:
        if re.search(rf"\b{tf}\b", up):
            return tf
    return "H1"


def match_risk(text: str) -> dict[str, float | int]:
    """Extract overrides for the risk block, if any are mentioned."""
    out: dict[str, float | int] = {}

    # ``risk 0.5%`` / ``0.5% risk`` / ``risk_per_trade 0.5``
    m = re.search(
        r"(?:risk(?:[\s_]*per[\s_]*trade)?\s*[:=]?\s*([\d.]+)\s*%?"
        r"|([\d.]+)\s*%\s*risk)",
        text, re.IGNORECASE,
    )
    if m:
        out["per_trade_pct"] = float(m.group(1) or m.group(2))

    m = re.search(
        r"\bdaily[\s_]*loss(?:[\s_]*(?:limit|cap|of|stop|threshold))?"
        r"\s*[:=]?\s*([\d.]+)\s*(?:%|percent|pct)?",
        text, re.IGNORECASE,
    )
    if m:
        out["daily_loss_pct"] = float(m.group(1))

    m = re.search(
        r"\b(?:sl|stop[\s-]?loss)\s*[:=]?\s*([\d]+)\s*(?:pips?)?",
        text, re.IGNORECASE,
    )
    if m:
        out["sl_pips"] = int(m.group(1))

    m = re.search(
        r"\b(?:tp|take[\s-]?profit)\s*[:=]?\s*([\d]+)\s*(?:pips?)?",
        text, re.IGNORECASE,
    )
    if m:
        out["tp_pips"] = int(m.group(1))

    m = re.search(
        r"\b(?:max[\s_]*spread|spread[\s_]*cap)\s*[:=]?\s*([\d.]+)\s*(?:pips?)?",
        text, re.IGNORECASE,
    )
    if m:
        out["max_spread_pips"] = float(m.group(1))

    m = re.search(
        r"\b(?:max[\s_]*(?:open[\s_]*)?positions?|up[\s_]*to)\s*([\d]+)\s*(?:positions?|trades?)?",
        text, re.IGNORECASE,
    )
    if m:
        out["max_open_positions"] = int(m.group(1))

    # Grid / DCA "max N levels" — each ladder level is an open position, so
    # map the requested cap onto max_open_positions when no explicit positions
    # count was given. Stops the parser silently dropping a "max 7 grid levels"
    # safety requirement (v2.5.0 QA review, blocker #1).
    if "max_open_positions" not in out:
        gm = (
            re.search(r"\bmax(?:imum)?[\s_]*(?:grid[\s_]*)?levels?\s*[:=]?\s*([\d]+)", text, re.IGNORECASE)
            or re.search(r"\bmax(?:imum)?[\s_]*([\d]+)[\s_]*(?:grid[\s_]*)?levels?\b", text, re.IGNORECASE)
            or re.search(r"\b([\d]+)[\s_]*(?:grid[\s_]*)?levels?\b", text, re.IGNORECASE)
        )
        if gm:
            out["max_open_positions"] = int(gm.group(1))
    return out


def match_signals(text: str) -> dict[str, object] | None:
    """Return a ``signals`` block matching the schema's mapping shorthand."""
    found: list[str] = []
    for pat, kind in SIGNAL_KEYWORDS:
        if re.search(pat, text, re.IGNORECASE) and kind not in found:
            found.append(kind)
    if not found:
        return None
    logic = "OR" if re.search(r"\bor\b", text, re.IGNORECASE) else "AND"
    return {
        "logic": logic,
        "list": [{"kind": k} for k in found],
    }


def match_name(
    text: str, *, preset: str, symbol: str, timeframe: str,
) -> str:
    """Extract a user-supplied name or synthesise one from preset+symbol+tf."""
    m = re.search(
        r"\b(?:name(?:d)?(?:\s+as)?|call(?:ed)?)\s*[:=]?\s*([A-Za-z0-9_]+)\b",
        text,
    )
    if m:
        return m.group(1)
    return f"{preset.replace('-', '_').title().replace('_', '')}{symbol}{timeframe}"
