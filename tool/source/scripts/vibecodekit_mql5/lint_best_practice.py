"""mql5-lint best-practice anti-pattern detectors (WARN-only).

the kit spec §7 splits the 22 anti-patterns into 8 critical (gate, ERROR) and
13 best-practice (warn, do-not-gate). The 8 critical
detectors live in :mod:`vibecodekit_mql5.lint`. This module supplies the 13
best-practice detectors. ``lint.py`` imports :data:`BEST_PRACTICE_DETECTORS`
and adds them to its detector list, so the existing CLI surface stays the
same.

AP-6 (curve-fitted) and AP-19 (ONNX no tester validation) need backtest
artefacts that a pure source-only linter cannot see, so their static
heuristics are intentionally minimal and surfaced only when the source
text gives away a clear smell (e.g. ``OnnxRun`` without any ``OnTester``).
"""

from __future__ import annotations

import re
from typing import Callable

from .lint import Finding, _line_col

# ─── AP-2 SL-too-tight ───────────────────────────────────────────────────────
_SL_TOO_TIGHT = re.compile(r"\b(?:sl_pips|stop_loss_pips|stop_pips)\s*=\s*([1-5])\b")


def detect_ap2(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _SL_TOO_TIGHT.finditer(src):
        line, col = _line_col(src, m.start())
        out.append(Finding(path, line, col, "WARN", "AP-2",
                           f"SL too tight ({m.group(1)} pips) — validate against broker stops_level"))
    return out


# ─── AP-4 Martingale without cap ─────────────────────────────────────────────
_LOT_DOUBLING = re.compile(r"\blot\w*\s*(?:\*=\s*2|=\s*\w+\s*\*\s*2)\b")


def detect_ap4(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _LOT_DOUBLING.finditer(src):
        if "max_lot" not in src.lower() and "lot_cap" not in src.lower():
            line, col = _line_col(src, m.start())
            out.append(Finding(path, line, col, "WARN", "AP-4",
                               "Martingale lot doubling without max-lot cap"))
            break  # one warning per file is enough
    return out


# ─── AP-6 Curve-fitted (static smell only) ───────────────────────────────────
_OPT_HINT = re.compile(r"//\s*walk-forward\s*:\s*disabled|tester_set_passes\s*>\s*100000", re.I)


def detect_ap6(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    m = _OPT_HINT.search(raw)
    if m:
        line, col = _line_col(raw, m.start())
        out.append(Finding(path, line, col, "WARN", "AP-6",
                           "Walk-forward disabled or high optimisation pass count — curve-fit risk"))
    return out


# ─── AP-7 Hardcoded-magic ────────────────────────────────────────────────────
_HARDCODED_MAGIC = re.compile(r"\bmagic\w*\s*=\s*(\d{2,})\b")


def detect_ap7(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _HARDCODED_MAGIC.finditer(src):
        if "MagicRegistry" in src:
            continue  # someone reserves the number via the registry
        line, col = _line_col(src, m.start())
        out.append(Finding(path, line, col, "WARN", "AP-7",
                           f"Hardcoded magic {m.group(1)} — use CMagicRegistry.Reserve()"))
    return out


# ─── AP-8 No-spread-guard ────────────────────────────────────────────────────
def detect_ap8(path: str, raw: str, src: str) -> list[Finding]:
    # Accept either the native SYMBOL_SPREAD API, a dedicated guard class, or
    # an explicit tick ask/bid spread calculation. Generated EAs use the last
    # form so the check remains pip-aware across 3/5-digit symbols.
    spread_guard = re.search(
        r"SymbolInfoInteger\s*\([^)]*SYMBOL_SPREAD|CSpreadGuard\b|"
        r"(?:\b\w+\.)?ask\s*-\s*(?:\b\w+\.)?bid",
        src,
        re.IGNORECASE,
    )
    if re.search(r"\bOrderSend\b|\bCTrade\b", src) and not spread_guard:
        return [Finding(path, 1, 1, "WARN", "AP-8",
                        "Trade send without spread guard — add CSpreadGuard / SYMBOL_SPREAD check")]
    return []


# ─── AP-9 Multi-entry-same-bar ───────────────────────────────────────────────
def detect_ap9(path: str, raw: str, src: str) -> list[Finding]:
    # A literal Bars() guard is one valid policy, but recovery/grid EAs often
    # use an explicit entry-delay/new-bar policy plus an intent ledger. Do not
    # report those designs as unguarded merely because they permit selected DCA
    # modes to operate more than once per candle.
    entry_guard = re.search(
        r"\bBars\s*\(|\bNewBar\s*\(|\bEntryDelayPassed\s*\(", src
    )
    if re.search(r"\bOrderSend\b|\bCTrade\b", src) and not entry_guard:
        return [Finding(path, 1, 1, "WARN", "AP-9",
                        "No same-bar entry guard — track Bars(_Symbol,_Period) to avoid duplicate entries")]
    return []


# ─── AP-10 OrderSend-no-check ────────────────────────────────────────────────
_ORDERSEND_NO_CHECK = re.compile(r"\bOrderSend\s*\(")


def detect_ap10(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _ORDERSEND_NO_CHECK.finditer(src):
        # cheap heuristic: look 200 chars ahead for retcode check
        tail = src[m.end():m.end() + 200]
        if "retcode" not in tail.lower() and "result" not in tail.lower():
            line, col = _line_col(src, m.start())
            out.append(Finding(path, line, col, "WARN", "AP-10",
                               "OrderSend without retcode check"))
            break
    return out


# ─── AP-23 CTrade-no-retcode ─────────────────────────────────────────────────
_CTRADE_NO_RETCODE = re.compile(r"\b\w+\.(?:Buy|Sell)\s*\(")


def detect_ap23(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    if "CSafeTradeManager" in src or "CAsyncTradeManager" in src:
        return out
    for m in _CTRADE_NO_RETCODE.finditer(src):
        head = src[max(0, m.start() - 120):m.start()].lower()
        tail = src[m.end():m.end() + 300].lower()
        if "resultretcode" not in head + tail and "retcode" not in head + tail:
            line, col = _line_col(src, m.start())
            out.append(Finding(path, line, col, "WARN", "AP-23",
                               "CTrade.Buy/Sell without ResultRetcode check"))
            break
    return out


# ─── AP-24 History-not-synchronized ──────────────────────────────────────────
_HISTORY_READ = re.compile(
    r"\b(?:CopyBuffer|CopyRates|CopyTime|iOpen|iHigh|iLow|iClose|iTime)\s*\("
)


def detect_ap24(path: str, raw: str, src: str) -> list[Finding]:
    """Flag unguarded data reads, not indicator-handle construction.

    MQL5 ``iMA/iRSI/iATR/iCustom`` calls create handles; synchronization is
    required when reading them via ``CopyBuffer``.  A class-local
    ``BarsCalculated`` guard is therefore a valid synchronization contract.
    ``iTime`` is also accepted when the returned zero sentinel is checked in
    the same statement block.
    """
    m = _HISTORY_READ.search(src)
    if not m:
        return []
    if re.search(r"\b(?:CHistorySync|SeriesInfoInteger|SERIES_SYNCHRONIZED|BarsCalculated)\b", src):
        return []
    call = m.group(0).lower()
    if call.startswith("itime"):
        window = src[max(0, m.start() - 80):m.end() + 220]
        assigned = re.search(r"\b([A-Za-z_]\w*)\s*=\s*iTime\s*\(", window)
        if assigned and re.search(rf"\b{re.escape(assigned.group(1))}\s*==\s*0\b", window):
            return []
    line, col = _line_col(src, m.start())
    return [Finding(path, line, col, "WARN", "AP-24",
                    "History/indicator access without synchronization guard")]


# ─── AP-25 Raw-delete-no-guard ────────────────────────────────────────────────
_RAW_DELETE = re.compile(r"(?<!SAFE_)\bdelete\s+\w+\s*;")


def detect_ap25(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _RAW_DELETE.finditer(src):
        head = src[max(0, m.start() - 160):m.start()]
        if "SAFE_DELETE" in head or "CheckPointer" in head or "POINTER_DYNAMIC" in head:
            continue
        line, col = _line_col(src, m.start())
        out.append(Finding(path, line, col, "WARN", "AP-25",
                           "Raw delete without CheckPointer/SAFE_DELETE guard"))
        break
    return out


# ─── AP-11 Mode-blind (netting/hedging) ──────────────────────────────────────
def detect_ap11(path: str, raw: str, src: str) -> list[Finding]:
    if re.search(r"\bPositionSelect\b|\bOrderSend\b", src) and not re.search(
        r"SYMBOL_TRADE_MODE|ACCOUNT_MARGIN_MODE|MARKET_INFO", src
    ):
        return [Finding(path, 1, 1, "WARN", "AP-11",
                        "Netting vs hedging mode not interrogated — check ACCOUNT_MARGIN_MODE")]
    return []


# ─── AP-12 Leak-handle ───────────────────────────────────────────────────────
_HANDLE_CREATE = re.compile(r"\b(iMA|iCustom|iRSI|iATR)\s*\(")


def detect_ap12(path: str, raw: str, src: str) -> list[Finding]:
    if _HANDLE_CREATE.search(src) and "IndicatorRelease" not in src:
        m = _HANDLE_CREATE.search(src)
        line, col = _line_col(src, m.start())
        return [Finding(path, line, col, "WARN", "AP-12",
                        "Indicator handle created but IndicatorRelease never called")]
    return []


# ─── AP-13 Broker-coupled (hardcoded broker name) ────────────────────────────
_BROKER_NAMES = ("FxPro", "Exness", "ICMarkets", "Pepperstone", "Alpari", "RoboForex")


def detect_ap13(path: str, raw: str, src: str) -> list[Finding]:
    pattern = re.compile(r'"(' + "|".join(_BROKER_NAMES) + r')"', re.I)
    out: list[Finding] = []
    for m in pattern.finditer(src):
        line, col = _line_col(src, m.start())
        out.append(Finding(path, line, col, "WARN", "AP-13",
                           f"Hardcoded broker name {m.group(1)!r} — use AccountInfoString(ACCOUNT_COMPANY) at runtime"))
    return out


# ─── AP-14 No-MFE-MAE ────────────────────────────────────────────────────────
def detect_ap14(path: str, raw: str, src: str) -> list[Finding]:
    if re.search(r"\bOrderSend\b|\bCTrade\b", src) and "CMfeMaeLogger" not in src and "MfeMae" not in src:
        return [Finding(path, 1, 1, "WARN", "AP-14",
                        "EA places trades but no MFE/MAE logger wired — include CMfeMaeLogger.mqh")]
    return []


# ─── AP-16 Reinvent-stdlib ───────────────────────────────────────────────────
_CUSTOM_TRADE_CLASS = re.compile(r"class\s+C\w*Trade\w*\s*\{", re.I)


def detect_ap16(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _CUSTOM_TRADE_CLASS.finditer(src):
        # A composition wrapper around the standard CTrade class is not a
        # reinvention.  It is the recommended place for retcode, margin,
        # volume and broker-level normalization policy.
        body_window = src[m.start():m.start() + 4000]
        # Utility types such as CTradeIntentLedger/CTradeEventReducer contain
        # "Trade" in their domain name but do not implement execution. Only
        # classify a custom class when it actually exposes trade-send behavior.
        if not re.search(r"\b(?:Buy|Sell|Open|OrderSend|PositionClose)\s*\(", body_window):
            continue
        if re.search(r"\bCTrade\s+[A-Za-z_]\w*\s*;", body_window):
            continue
        line, col = _line_col(src, m.start())
        out.append(Finding(path, line, col, "WARN", "AP-16",
                           "Custom CTrade-like class — prefer <Trade/Trade.mqh> stdlib"))
    return out


# ─── AP-19 ONNX without tester validation ────────────────────────────────────
def detect_ap19(path: str, raw: str, src: str) -> list[Finding]:
    if "OnnxRun" in src and "OnTester" not in src:
        return [Finding(path, 1, 1, "WARN", "AP-19",
                        "ONNX inference used but no OnTester() validation — gate model in Strategy Tester first")]
    return []


# ─── AP-22 Signal-placeholder ────────────────────────────────────────────────
# An EA declares OnTick but the body never reaches any order-placing call.
# We warn (don't error) because the kit ships several deliberate "infra-only"
# scaffolds (library / indicator-only / stdlib) and we don't want them to
# break builds — only to flag them so a downstream operator knows the
# scaffold still needs a strategy plugged in.
_ONTICK_HEAD = re.compile(r"\bvoid\s+OnTick\s*\([^)]*\)\s*\{")
_SEND_CALL = re.compile(
    r"\b(?:[A-Za-z_]\w*\.(?:Buy|Sell|Open)|OrderSend(?:Async)?|Send(?:Buy|Sell)Async)\s*\(",
    re.IGNORECASE,
)



_FUNCTION_HEAD = re.compile(
    r"\b(?:void|bool|int|long|ulong|double|float|string|datetime|uint|char|short|"
    r"ENUM_[A-Z0-9_]+|[A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
)
_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_CALL_KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "Print", "MathMax", "MathMin"}


def _balanced_body(src: str, open_brace: int) -> str | None:
    depth = 1
    i = open_brace + 1
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace + 1:i]
        i += 1
    return None


def _function_bodies(src: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _FUNCTION_HEAD.finditer(src):
        body = _balanced_body(src, m.end() - 1)
        if body is not None:
            out[m.group(1)] = body
    return out


def _body_reaches_send(body: str, bodies: dict[str, str], seen: set[str]) -> bool:
    if _SEND_CALL.search(body):
        return True
    for called in _CALL_RE.findall(body):
        if called in _CALL_KEYWORDS or called in seen or called not in bodies:
            continue
        seen.add(called)
        if _body_reaches_send(bodies[called], bodies, seen):
            return True
    return False

def _ontick_body(src: str) -> tuple[int, str] | None:
    """Extract OnTick's body via brace balancing.

    Returns (start_index, body) or ``None``. The header regex finds the
    opening ``{``; we then scan forward, tracking the depth, until we hit
    the matching ``}``. A naive ``.*?\\n\\s*\\}`` regex closes on the first
    inner brace and misclassifies anything with nested ``if`` blocks.
    """
    m = _ONTICK_HEAD.search(src)
    if not m:
        return None
    i = m.end()  # one past the opening `{`
    depth = 1
    while i < len(src) and depth > 0:
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return m.start(), src[m.end(): i]
        i += 1
    return None


def detect_ap22(path: str, raw: str, src: str) -> list[Finding]:
    # Service programs use OnStart, not OnTick — they're out of scope.
    if re.search(r"#\s*property\s+service\b", raw):
        return []
    extracted = _ontick_body(src)
    if extracted is None:
        return []
    start, body = extracted
    if _body_reaches_send(body, _function_bodies(src), {"OnTick"}):
        return []
    line, col = _line_col(src, start)
    return [Finding(path, line, col, "WARN", "AP-22",
                    "OnTick reaches no order-placing call — signal logic is "
                    "placeholder-only; wire trade.Buy/Sell or *Async before ship")]


Detector = Callable[[str, str, str], list[Finding]]

BEST_PRACTICE_DETECTORS: list[tuple[str, Detector]] = [
    ("AP-2",  detect_ap2),
    ("AP-4",  detect_ap4),
    ("AP-6",  detect_ap6),
    ("AP-7",  detect_ap7),
    ("AP-8",  detect_ap8),
    ("AP-9",  detect_ap9),
    ("AP-10", detect_ap10),
    ("AP-11", detect_ap11),
    ("AP-12", detect_ap12),
    ("AP-13", detect_ap13),
    ("AP-14", detect_ap14),
    ("AP-16", detect_ap16),
    ("AP-19", detect_ap19),
    ("AP-22", detect_ap22),
    ("AP-23", detect_ap23),
    ("AP-24", detect_ap24),
    ("AP-25", detect_ap25),
]
