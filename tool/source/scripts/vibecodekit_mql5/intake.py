"""Deterministic, evidence-preserving intake from EA prose to canonical EA-IR."""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .ea_ir import EAIR, Requirement, SourceRef
from .safe_paths import validate_ea_name
from .spec_from_prompt_recognisers import SYMBOLS, TIMEFRAMES
from .term_ontology import COMPONENT_PATTERNS, SIGNAL_PATTERNS

_PAGE_BREAK = "\f"


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _pages(text: str) -> list[str]:
    chunks = text.split(_PAGE_BREAK)
    return chunks if chunks else [text]


def _evidence(text: str, match: re.Match[str], *, limit: int = 220) -> str:
    start = max(0, text.rfind("\n", 0, match.start()) + 1)
    end = text.find("\n", match.end())
    if end < 0:
        end = min(len(text), match.end() + limit)
    value = " ".join(text[start:end].split())
    return value[:limit]


def _find(patterns: tuple[str, ...], pages: list[str], source: str) -> tuple[float, list[SourceRef]]:
    refs: list[SourceRef] = []
    for page_no, page in enumerate(pages, start=1):
        for pattern in patterns:
            for m in re.finditer(pattern, page, re.IGNORECASE | re.UNICODE):
                refs.append(SourceRef(source=source, page=page_no, evidence=_evidence(page, m)))
                if len(refs) >= 5:
                    break
            if len(refs) >= 5:
                break
        if len(refs) >= 5:
            break
    # Multiple independent mentions raise confidence without exceeding 0.99.
    confidence = min(0.99, 0.78 + 0.06 * len(refs)) if refs else 0.0
    return confidence, refs


def _find_signal(patterns: tuple[str, ...], pages: list[str], source: str) -> tuple[float, list[SourceRef]]:
    """Find entry-signal mentions while excluding filter-only contexts."""
    refs: list[SourceRef] = []
    for page_no, page in enumerate(pages, start=1):
        for pattern in patterns:
            for m in re.finditer(pattern, page, re.IGNORECASE | re.UNICODE):
                line_start = page.rfind("\n", 0, m.start()) + 1
                line_end = page.find("\n", m.end())
                if line_end < 0:
                    line_end = len(page)
                line = page[line_start:line_end]
                rel = m.start() - line_start
                filter_positions = [
                    hit.start() for hit in re.finditer(r"\bfilter\b|bộ lọc", line, re.IGNORECASE)
                ]
                # In "Bộ lọc: RSI, EMA, MACD", every indicator after the
                # filter label is a filter, not an entry signal.
                if filter_positions and rel > min(filter_positions):
                    continue
                refs.append(SourceRef(source=source, page=page_no, evidence=_evidence(page, m)))
                if len(refs) >= 5:
                    break
            if len(refs) >= 5:
                break
        if len(refs) >= 5:
            break
    confidence = min(0.99, 0.78 + 0.06 * len(refs)) if refs else 0.0
    return confidence, refs


def _number(raw: str) -> Decimal | None:
    token = raw.strip().rstrip(".,;:)")
    token = token.replace(",", ".")
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def _extract_risk(text: str) -> dict[str, Any]:
    patterns: dict[str, str] = {
        "per_trade_pct": r"(?:risk(?:[\s_]*per[\s_]*trade)?\s*[:=]?\s*([\d.,]+)|([\d.,]+)\s*%\s*risk)",
        "daily_loss_pct": r"daily[\s_]*loss(?:[\s_]*(?:limit|cap|stop|threshold))?\s*[:=]?\s*([\d.,]+)",
        "max_spread_pips": r"(?:max[\s_]*spread|spread tối đa)[^\d]{0,12}([\d.,]+)",
        "max_open_positions": r"(?:max(?:imum)?[\s_]*(?:open[\s_]*)?positions?|số lệnh[^\n]{0,20}tối đa)[^\d]{0,12}([\d]+)",
        "sl_pips": r"(?:\bSL\b|stop[\s-]?loss)[^\d-]{0,10}([\d.,]+)",
        "tp_pips": r"(?:\bTP\b|take[\s-]?profit)[^\d-]{0,10}([\d.,]+)",
        "base_lot": r"(?:base lots?|lots? cơ bản|\bLots\b)[^\d]{0,12}([\d.,]+)",
        "max_lot": r"(?:max lots?|lots? tối đa)[^\d]{0,12}([\d.,]+)",
    }
    out: dict[str, Any] = {}
    for key, pattern in patterns.items():
        m = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
        if not m:
            continue
        raw = next((g for g in m.groups() if g is not None), "")
        value = _number(raw)
        if value is None:
            continue
        out[key] = int(value) if key == "max_open_positions" else float(value)
    return out



def _extract_strategy_parameters(text: str) -> dict[str, Any]:
    """Extract only explicitly assigned operational values.

    Patterns deliberately require a value next to a parameter label. Narrative
    examples and capability lists are not promoted to build configuration.
    """
    patterns: dict[str, tuple[str, str]] = {
        "dca_step_pips": (r"(?:DCA[\s_-]*step|khoảng cách nhồi(?: lệnh)?(?: ban đầu)?)[^\d]{0,16}([\d.,]+)", "float"),
        "dca_step_multiplier": (r"(?:DCA[\s_-]*step[\s_-]*multiplier|hệ số nhân khoảng cách(?: ban đầu)?)[^\d]{0,16}([\d.,]+)", "float"),
        "lot_multiplier": (r"(?:lot[s]?[\s_-]*multiplier|hệ số nhân(?: ban đầu)?(?: lots?)?)[^\d]{0,16}([\d.,]+)", "float"),
        "lot_additive": (r"(?:lot[s]?[\s_-]*additive|hệ số cộng)[^\d]{0,16}([\d.,]+)", "float"),
        "basket_target_money": (r"(?:basket[\s_-]*(?:target|tp)[\s_-]*(?:money|usd)|số tiền chốt tổng|money TP all)[^\d-]{0,16}(-?[\d.,]+)", "float"),
        "basket_tp_pips": (r"(?:basket[\s_-]*tp[\s_-]*pips|TP chuỗi(?: DCA)?(?:,? pips)?)[^\d]{0,16}([\d.,]+)", "float"),
        "hedge_trigger_positions": (r"(?:hedge[\s_-]*trigger[\s_-]*positions?|số lệnh kích hoạt hedging)[^\d]{0,16}([\d]+)", "int"),
        "hedge_lot_pct": (r"(?:hedge[\s_-]*lot[\s_-]*(?:pct|percent)|phần trăm lots hedging)[^\d]{0,16}([\d.,]+)", "float"),
        "hedge_exit_money": (r"(?:hedge[\s_-]*exit[\s_-]*money|số tiền TP tổng khi hedging)[^\d-]{0,16}(-?[\d.,]+)", "float"),
        "sniper_trigger_positions": (r"(?:sniper[\s_-]*trigger[\s_-]*positions?|số lệnh kích hoạt tỉa(?: lần đầu)?)[^\d]{0,16}([\d]+)", "int"),
        "sniper_target_money": (r"(?:sniper[\s_-]*target[\s_-]*money|số tiền lời sau khi tỉa)[^\d-]{0,16}(-?[\d.,]+)", "float"),
        "partial_close_pct": (r"(?:partial[\s_-]*close[\s_-]*(?:pct|percent)|phần trăm lots (?:lệnh đầu )?(?:để|cần) tỉa)[^\d]{0,16}([\d.,]+)", "float"),
        "daily_target_pct": (r"(?:daily[\s_-]*target(?:[\s_-]*pct)?|target lợi nhuận ngày)[^\d]{0,16}([\d.,]+)", "float"),
        "trailing_start_pips": (r"(?:trailing[\s_-]*start(?:[\s_-]*pips)?|pips bắt đầu trailing)[^\d]{0,16}([\d.,]+)", "float"),
        "trailing_distance_pips": (r"(?:trailing[\s_-]*(?:distance|stop)(?:[\s_-]*pips)?|khoảng cách trailing)[^\d]{0,16}([\d.,]+)", "float"),
        "min_seconds_between_entries": (r"(?:min[\s_-]*seconds[\s_-]*between[\s_-]*entries|delay mỗi lần mở lệnh(?:,? giây)?)[^\d]{0,16}([\d]+)", "int"),
    }
    out: dict[str, Any] = {}
    for key, (pattern, kind) in patterns.items():
        m = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
        if not m:
            continue
        value = _number(m.group(1))
        if value is None:
            continue
        out[key] = int(value) if kind == "int" else float(value)
    return out

def _extract_symbols(text: str) -> list[str]:
    up = text.upper()
    hits: list[tuple[int, str]] = []
    for sym in SYMBOLS:
        for m in re.finditer(rf"(?<![A-Z0-9]){re.escape(sym)}(?![A-Z0-9])", up):
            hits.append((m.start(), sym))
    for m in re.finditer(r"\b([A-Z]{3})\s*/\s*([A-Z]{3})\b", up):
        joined = m.group(1) + m.group(2)
        if joined in SYMBOLS:
            hits.append((m.start(), joined))
    return list(dict.fromkeys(sym for _, sym in sorted(hits)))


def _extract_timeframes(text: str) -> list[str]:
    up = text.upper()
    hits: list[tuple[int, str]] = []
    # Longest first prevents M1 matching inside M15.
    for tf in sorted(TIMEFRAMES, key=len, reverse=True):
        for m in re.finditer(rf"(?<![A-Z0-9]){re.escape(tf)}(?![A-Z0-9])", up):
            hits.append((m.start(), tf))
    return list(dict.fromkeys(tf for _, tf in sorted(hits)))




def _command_slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    if not value or not value[0].isalpha():
        value = "command_" + value
    return value[:56]


def _classify_pending_action(description: str) -> tuple[str, dict[str, Any]] | None:
    """Map a command description to a generic action contract.

    This is an action ontology, not a vendor command table: no prices, command
    IDs, or required command set are supplied here.  Unknown actions remain
    unresolved so the planner can request an explicit operator profile rather
    than invent behavior.
    """
    compact = " ".join(description.split())
    low = compact.casefold()
    rules: tuple[tuple[str, tuple[str, ...], dict[str, Any]], ...] = (
        ("disable_ea", ("dừng mọi hoạt động", "stop ea", "disable ea", "pause ea", "stop all activity"),
         {"type": "set_state", "path": "ea.enabled", "value": False}),
        ("enable_ea", ("cho phép ea hoạt động", "start ea", "enable ea", "resume ea"),
         {"type": "set_state", "path": "ea.enabled", "value": True}),
        ("disable_new_cycle", ("tắt new cycle", "disable new cycle", "block new cycle", "pause new cycle"),
         {"type": "set_state", "path": "cycle.new_enabled", "value": False}),
        ("enable_new_cycle", ("bật new cycle", "enable new cycle", "allow new cycle", "resume new cycle"),
         {"type": "set_state", "path": "cycle.new_enabled", "value": True}),
        ("disable_buy", ("stop buy", "dừng buy", "disable buy", "block buy"),
         {"type": "set_state", "path": "direction.buy_enabled", "value": False}),
        ("enable_buy", ("start buy", "bật buy", "enable buy", "allow buy"),
         {"type": "set_state", "path": "direction.buy_enabled", "value": True}),
        ("disable_sell", ("stop sell", "dừng sell", "disable sell", "block sell"),
         {"type": "set_state", "path": "direction.sell_enabled", "value": False}),
        ("enable_sell", ("start sell", "bật sell", "enable sell", "allow sell"),
         {"type": "set_state", "path": "direction.sell_enabled", "value": True}),
        ("close_managed_all", ("close managed all", "đóng toàn bộ lệnh quản lý", "close all managed"),
         {"type": "close_scope", "scope": "managed_all"}),
        ("close_managed_buy", ("close managed buy", "đóng lệnh buy quản lý", "close buy managed"),
         {"type": "close_scope", "scope": "managed_buy"}),
        ("close_managed_sell", ("close managed sell", "đóng lệnh sell quản lý", "close sell managed"),
         {"type": "close_scope", "scope": "managed_sell"}),
        ("close_account_all", ("close account all", "đóng mọi lệnh toàn tài khoản", "close all account"),
         {"type": "close_scope", "scope": "account_all"}),
    )
    for semantic_id, phrases, action in rules:
        if any(phrase in low for phrase in phrases):
            return semantic_id, dict(action)
    return None


def _parse_structured_pending_commands(text: str) -> dict[str, dict[str, Any]]:
    """Parse portable explicit command declarations.

    Accepted examples::

      COMMAND pause_dca: buy_stop 12345 -> set_state ea.enabled=false
      COMMAND flatten: sell_limit 23456 -> close_scope managed_all

    The portable syntax lets unrelated projects define arbitrary command IDs
    without relying on natural-language recognizers.
    """
    out: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"(?im)^\s*COMMAND\s+([A-Za-z][A-Za-z0-9_]*)\s*:\s*"
        r"(buy_stop|sell_limit|buy_limit|sell_stop)\s+([\d.,]+)\s*->\s*"
        r"(set_state|close_scope)\s+([^\r\n]+)$"
    )
    for m in pattern.finditer(text):
        command_id, order_type, raw_price, action_type, payload = m.groups()
        price = _number(raw_price)
        if price is None:
            continue
        if action_type == "set_state":
            state = re.fullmatch(
                r"\s*([A-Za-z][A-Za-z0-9_.]*)\s*=\s*(true|false)\s*",
                payload,
                re.IGNORECASE,
            )
            if not state:
                continue
            action = {"type": "set_state", "path": state.group(1), "value": state.group(2).lower() == "true"}
        else:
            scope = payload.strip().lower()
            action = {"type": "close_scope", "scope": scope}
        out[command_id] = {"order_type": order_type.lower(), "price": float(price), "action": action}
    return out


def _extract_pending_commands(text: str) -> dict[str, dict[str, Any]]:
    """Extract data-driven pending-order commands without vendor defaults.

    First consume portable explicit ``COMMAND`` declarations.  Then scan
    document table/prose rows for ``order type + price + effect`` and classify
    only the effect.  Prices and command presence always originate from the
    input document; unrecognized effects are not guessed.
    """
    out = _parse_structured_pending_commands(text)

    # Flatten PDF/table whitespace while retaining a bounded description up to
    # the next pending-order row or major heading.
    compact = " ".join(text.replace("\x0c", " ").split())
    row = re.compile(
        r"(?i)\b(Buy\s+Stop|Sell\s+Limit|Buy\s+Limit|Sell\s+Stop)"
        r"(?:\s+(?:giá|price))?\s+([\d.,]+)\s+(.+?)"
        r"(?=(?:\b(?:Buy\s+Stop|Sell\s+Limit|Buy\s+Limit|Sell\s+Stop)\b(?:\s+(?:giá|price))?\s+[\d.,]+)|$)"
    )
    order_map = {
        "buy stop": "buy_stop", "sell limit": "sell_limit",
        "buy limit": "buy_limit", "sell stop": "sell_stop",
    }
    for match in row.finditer(compact):
        order_type = order_map[" ".join(match.group(1).lower().split())]
        price = _number(match.group(2))
        if price is None:
            continue
        # A table row's actionable label is normally near the start. Limiting
        # the window prevents the next explanatory sections from influencing
        # classification when PDF extraction merges columns.
        description = match.group(3)[:320]
        classified = _classify_pending_action(description)
        if classified is None:
            continue
        semantic_id, action = classified
        command_id = semantic_id
        suffix = 2
        while command_id in out and out[command_id] != {"order_type": order_type, "price": float(price), "action": action}:
            command_id = f"{semantic_id}_{suffix}"
            suffix += 1
        out[command_id] = {"order_type": order_type, "price": float(price), "action": action}
    return out

def _extract_name(text: str) -> tuple[str | None, float]:
    patterns = (
        r"\b(?:name(?:d)?(?:\s+as)?|call(?:ed)?)\s*[:=]?\s*([A-Za-z][A-Za-z0-9_]{0,63})",
        r"(?:EA|bot)\s+(?:tên|name|named|called)\s*[:=]?\s*([A-Za-z][A-Za-z0-9_]{0,63})",
        r"\b([A-Z][A-Z0-9_]{2,31})\s*[–-]\s*EA\b",
        r"Giới thiệu bot\s+([A-Za-z][A-Za-z0-9 ]{2,60})",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        candidate = re.sub(r"[^A-Za-z0-9_]", "_", m.group(1).strip())
        candidate = re.sub(r"_+", "_", candidate).strip("_")
        if candidate and not candidate[0].isalpha():
            candidate = "EA_" + candidate
        try:
            return validate_ea_name(candidate[:64]), 0.92
        except ValueError:
            continue
    return None, 0.0


def _version(text: str) -> str | None:
    m = re.search(r"(?:phiên bản|version)\s*v?([0-9]+(?:\.[0-9]+){1,3})", text, re.IGNORECASE)
    return m.group(1) if m else None


def _requirement(reqs: list[Requirement], path: str, value: Any, confidence: float,
                 refs: list[SourceRef], *, status: str = "extracted", priority: str = "must") -> None:
    reqs.append(Requirement(
        id=f"REQ-{len(reqs)+1:04d}", path=path, value=value,
        confidence=confidence, status=status, priority=priority, source_refs=refs,
    ))


def parse_text(text: str, *, source: str = "prompt", strict: bool = False) -> EAIR:
    text = _norm(text)
    pages = _pages(text)
    reqs: list[Requirement] = []
    components: dict[str, Any] = {}

    for path, patterns in COMPONENT_PATTERNS.items():
        confidence, refs = _find(patterns, pages, source)
        if refs:
            components[path] = True
            _requirement(reqs, path, True, confidence, refs)

    signals: list[str] = []
    signal_evidence: dict[str, list[SourceRef]] = {}
    for signal, patterns in SIGNAL_PATTERNS.items():
        confidence, refs = _find_signal(patterns, pages, source)
        if refs:
            signals.append(signal)
            signal_evidence[signal] = refs
            _requirement(reqs, f"strategy.entry.signals.{signal}", True, confidence, refs, priority="should")

    name, name_conf = _extract_name(text)
    version = _version(text)
    symbols = _extract_symbols(text)
    timeframes = _extract_timeframes(text)

    explicit_hedging = bool(re.search(r"(?:account|tài khoản|stack|mode)[^\n]{0,25}\bhedg(?:e|ing)\b", text, re.IGNORECASE))
    explicit_netting = bool(re.search(r"(?:account|tài khoản|stack|mode)[^\n]{0,25}\bnetting\b", text, re.IGNORECASE))
    hedge_required = any(k.startswith("strategy.hedge.") and v for k, v in components.items())

    conflicts: list[dict[str, Any]] = []
    ambiguities: list[dict[str, Any]] = []
    if explicit_hedging and explicit_netting:
        conflicts.append({
            "id": "CONFLICT-ACCOUNT-MODEL",
            "path": "runtime.account_model",
            "values": ["hedging", "netting"],
            "message": "Both hedging and netting account models are explicitly requested.",
        })
        account_model = None
        account_status = "conflict"
    elif explicit_hedging:
        account_model, account_status = "hedging", "confirmed"
    elif explicit_netting:
        account_model, account_status = "netting", "confirmed"
    elif hedge_required:
        account_model, account_status = "hedging", "inferred"
        ambiguities.append({
            "id": "AMB-ACCOUNT-MODEL",
            "severity": "warning",
            "path": "runtime.account_model",
            "assumption": "hedging",
            "message": "Hedge components require a hedging account; inferred from requested behavior.",
        })
    else:
        account_model, account_status = None, "unresolved"
        ambiguities.append({
            "id": "AMB-ACCOUNT-MODEL",
            "severity": "blocking" if strict else "warning",
            "path": "runtime.account_model",
            "message": "Account model was not stated; choose hedging or netting.",
        })

    if explicit_netting and hedge_required:
        conflicts.append({
            "id": "CONFLICT-HEDGE-NETTING",
            "path": "runtime.account_model",
            "values": ["netting", "hedge components"],
            "message": "Requested hedge components cannot preserve independent hedge legs on a netting account.",
        })

    # A manual often describes a chart-attached EA rather than one fixed pair/TF.
    chart_symbol = bool(re.search(r"(?:cặp tiền|symbol).*?(?:đang chạy bot|trên chart|chart symbol)", text, re.IGNORECASE | re.DOTALL))
    chart_tf = bool(re.search(r"(?:khung thời gian|timeframe).*?(?:chart|biểu đồ)", text, re.IGNORECASE | re.DOTALL))
    symbol_mode = "explicit_list" if symbols else ("chart_symbol" if chart_symbol else "unresolved")
    timeframe_mode = "explicit_list" if timeframes else ("chart_timeframe" if chart_tf else "unresolved")
    if symbol_mode == "unresolved":
        ambiguities.append({"id": "AMB-SYMBOL", "severity": "blocking" if strict else "warning",
                            "path": "runtime.symbols", "message": "Symbol scope is unresolved."})
    if timeframe_mode == "unresolved":
        ambiguities.append({"id": "AMB-TIMEFRAME", "severity": "blocking" if strict else "warning",
                            "path": "runtime.timeframes", "message": "Timeframe scope is unresolved."})
    if not name:
        ambiguities.append({"id": "AMB-NAME", "severity": "blocking" if strict else "warning",
                            "path": "identity.name", "message": "EA name is unresolved."})

    if name:
        _requirement(reqs, "identity.name", name, name_conf, [SourceRef(source=source, evidence=name)], status="inferred")
    if account_model:
        _requirement(reqs, "runtime.account_model", account_model,
                     0.99 if account_status == "confirmed" else 0.9,
                     [SourceRef(source=source, evidence=f"account model {account_model}")], status=account_status)
    for sym in symbols:
        _requirement(reqs, f"runtime.symbols.{sym}", True, 0.99, [SourceRef(source=source, evidence=sym)])
    for tf in timeframes:
        _requirement(reqs, f"runtime.timeframes.{tf}", True, 0.99, [SourceRef(source=source, evidence=tf)])

    # New Cycle semantics are version-sensitive. Resolve only when source text
    # states the normalized post-2.6.1 behavior or version is new enough.
    new_cycle_semantics: str | None = None
    if components.get("controls.new_cycle"):
        if version and tuple(int(x) for x in version.split(".")) >= (2, 6, 1):
            new_cycle_semantics = "true_means_allow_new_cycle"
        elif re.search(r"New Cycle\s*=\s*false\s+mới cho phép", text, re.IGNORECASE):
            new_cycle_semantics = "false_means_allow_new_cycle"
        else:
            ambiguities.append({
                "id": "AMB-NEW-CYCLE-SEMANTICS", "severity": "blocking" if strict else "warning",
                "path": "controls.new_cycle_semantics",
                "message": "New Cycle polarity is version-sensitive and could not be resolved.",
            })

    core_prefixes = ("strategy.dca.", "strategy.sniper.", "strategy.hedge.",
                     "strategy.entry.trend_following", "strategy.entry.mean_reversion",
                     "strategy.entry.breakout")
    core_count = sum(1 for k in components if k.startswith(core_prefixes))
    topology = "multi_engine" if core_count > 1 else "single_engine"

    # Convert flattened component paths into a generic enabled feature list.
    feature_list = sorted(k for k, enabled in components.items() if enabled and k.startswith("strategy."))
    controls_features = sorted(k for k, enabled in components.items() if enabled and k.startswith("controls."))
    document_kind = "manual" if re.search(
        r"(?:mô tả chi tiết tất cả các nhóm input|hướng dẫn sử dụng|user manual|parameter reference)",
        text, re.IGNORECASE,
    ) else "build_request"
    risk = _extract_risk(text) if document_kind == "build_request" else {}
    for key, value in risk.items():
        _requirement(reqs, f"risk.{key}", value, 0.93, [SourceRef(source=source, evidence=f"{key}={value}")])

    parameters = _extract_strategy_parameters(text) if document_kind == "build_request" else {}
    for key, value in parameters.items():
        _requirement(reqs, f"strategy.parameters.{key}", value, 0.93,
                     [SourceRef(source=source, evidence=f"{key}={value}")])

    pending_commands = _extract_pending_commands(text)
    for command, config in pending_commands.items():
        _requirement(
            reqs, f"controls.pending_commands.{command}", config, 0.96,
            [SourceRef(source=source, evidence=f"{command}={config['price']}")],
        )
    if "controls.pending_order_remote" in controls_features and not pending_commands:
        ambiguities.append({
            "id": "AMB-REMOTE-COMMAND-MAP",
            "severity": "blocking" if strict else "warning",
            "path": "controls.pending_commands",
            "message": "Remote control is requested but no explicit command mapping was extracted.",
        })
    if pending_commands:
        controls_features = sorted(set(controls_features) | {"controls.pending_order_remote"})
        ambiguities.append({
            "id": "AMB-REMOTE-COMMAND-OWNERSHIP",
            "severity": "blocking" if strict else "warning",
            "path": "controls.pending_command_ownership",
            "message": "Choose authenticated_ea_order, manual_comment_token or legacy_price_only ownership and a managed-symbol scope. Legacy price-only is draft-only.",
        })

    explicit_signal_logic: str | None = None
    if components.get("strategy.entry.signal_selectable"):
        explicit_signal_logic = "selectable"
    elif re.search(r"(?:signals?|tín hiệu)[^\n]{0,80}\bAND\b", text, re.IGNORECASE):
        explicit_signal_logic = "AND"
    elif re.search(r"(?:signals?|tín hiệu)[^\n]{0,80}\bOR\b", text, re.IGNORECASE):
        explicit_signal_logic = "OR"
    elif len(signals) <= 1:
        explicit_signal_logic = "single"
    else:
        ambiguities.append({
            "id": "AMB-SIGNAL-LOGIC",
            "severity": "blocking" if strict else "warning",
            "path": "strategy.signal_logic",
            "message": "Multiple entry signals were found; choose AND, OR or selectable mode.",
            "signals": signals,
        })

    return EAIR(
        identity={"name": name, "version": version, "source_documents": [source]},
        runtime={
            "platform": "MT5",
            "account_model": account_model,
            "account_model_status": account_status,
            "symbol_mode": symbol_mode,
            "symbols": symbols,
            "timeframe_mode": timeframe_mode,
            "timeframes": timeframes,
        },
        strategy={
            "topology": topology,
            "features": feature_list,
            "signals": signals,
            "signal_logic": explicit_signal_logic,
            "parameters": parameters,
        },
        risk=risk,
        controls={
            "features": controls_features,
            "new_cycle_semantics": new_cycle_semantics,
            "pending_command_transport": "pending_order_v1" if pending_commands else None,
            "pending_command_ownership": {},
            "pending_commands": pending_commands,
        },
        requirements=reqs,
        ambiguities=ambiguities,
        conflicts=conflicts,
        metadata={
            "intake_engine": "deterministic-ea-ir-v2",
            "source_length": len(text),
            "document_kind": document_kind,
            "defaults_policy": "allow" if re.search(
                r"(?:accept|allow|use|dùng|chấp nhận).{0,30}(?:tool|conservative|safe|mặc định|defaults?)",
                text, re.IGNORECASE,
            ) else "reject",
        },
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-ea-intake-ir")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--file", type=Path)
    ap.add_argument("--source", default=None)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    if args.file:
        source = args.source or str(args.file)
        if args.file.suffix.lower() in {".pdf", ".docx"}:
            from .document_ingest import load_document
            document = load_document(args.file)
            text = document.text
        else:
            document = None
            text = args.file.read_text(encoding="utf-8", errors="replace")
    else:
        document = None
        text = args.text
        source = args.source or "prompt"
    ir = parse_text(text, source=source, strict=args.strict)
    if document is not None:
        ir.metadata.update({
            "document_format": document.format,
            "document_pages": document.page_count,
            "document_metadata": document.metadata,
        })
    payload = json.dumps(ir.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0 if ir.ready_for_planning else 2


if __name__ == "__main__":
    raise SystemExit(main())
