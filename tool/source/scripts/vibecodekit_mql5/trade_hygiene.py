"""mql5-trade-hygiene — static trade-call hygiene checklist.

Advisory, dependency-free static analysis of a single EA source for the
trade-call correctness items the two MQL5 references emphasise (report §20):

* Korotky §6.4.11 OrderCheck-before-OrderSend; volume/price normalization
  to SYMBOL_VOLUME_MIN/MAX/STEP and digits/tick size; SYMBOL_TRADE_FREEZE_LEVEL
  / SYMBOL_TRADE_STOPS_LEVEL respect; MqlTradeResult.retcode handling.
* §6.3.5 netting vs hedging (ACCOUNT_MARGIN_MODE awareness) and
  OnTradeTransaction reconciliation.

This tool REUSES the existing graph analyzer (:mod:`mq5_graphs`) for the
lifecycle / basket / risk findings it already computes (retcode check,
async-without-hook, basket-close-without-magic, volume clamp) and ADDS the
checklist items the graphs did not cover (OrderCheck presence, freeze/stops
level, price normalization, margin-mode awareness).

IMPORTANT — non-breaking by design: every finding here is **advisory**
(severity ``warn`` / ``info``). It is surfaced as its own report/CLI and (in
``check_all``) only as an advisory note. It is deliberately NOT promoted to a
``high`` risk flag, so it can never flip the pre-existing ``scan`` gate's
PASS/FAIL verdict for an EA that passed before.

CLI::

    python -m vibecodekit_mql5.trade_hygiene <ea.mq5> [--json]

Exit code is always 0 (advisory); callers gate on the JSON ``findings``.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .mq5_io import read_mq5_text
from .mq5_symbols import strip_comments_and_strings
from . import mq5_graphs

TOOL = "mql5-trade-hygiene"

_RAW_SEND = re.compile(r"(?<![.\w])OrderSend(Async)?\s*\(", re.I)
_ORDER_CHECK = re.compile(r"\bOrderCheck\s*\(", re.I)
_FREEZE_STOPS = re.compile(
    r"SYMBOL_TRADE_FREEZE_LEVEL|SYMBOL_TRADE_STOPS_LEVEL|TRADE_STOPS_LEVEL|FreezeLevel|StopsLevel",
    re.I,
)
_PRICE_NORMALIZE = re.compile(
    r"NormalizeDouble\s*\(|SYMBOL_TRADE_TICK_SIZE|SYMBOL_DIGITS|\b_Digits\b|SYMBOL_POINT",
    re.I,
)
_VOLUME_NORMALIZE = re.compile(
    r"SYMBOL_VOLUME_STEP|SYMBOL_VOLUME_MIN|SYMBOL_VOLUME_MAX|NormalizeVolume|CheckVolume",
    re.I,
)
_MARGIN_MODE = re.compile(
    r"ACCOUNT_MARGIN_MODE|MarginMode|MARGIN_MODE_RETAIL_HEDGING|MARGIN_MODE_RETAIL_NETTING",
    re.I,
)
_MARGIN_PRECHECK = re.compile(r"OrderCalcMargin\s*\(|OrderCalcProfit\s*\(", re.I)


@dataclass
class HygieneReport:
    source: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    checklist: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        warn = sum(1 for f in self.findings if f["severity"] == "warn")
        return {
            "source": self.source,
            "checklist": self.checklist,
            "findings": self.findings,
            "warn_count": warn,
            "info_count": len(self.findings) - warn,
        }


def _f(severity: str, item: str, detail: str, recommendation: str) -> dict[str, Any]:
    return {"severity": severity, "item": item, "detail": detail,
            "recommendation": recommendation, "source": "trade-hygiene"}


def analyze_source(text: str, *, source: str = "<text>") -> HygieneReport:
    code = strip_comments_and_strings(text)
    lifecycle = mq5_graphs.analyze_order_lifecycle(text)
    basket = mq5_graphs.analyze_basket_integrity(text)
    risk = mq5_graphs.analyze_risk_invariants(text)

    has_raw_send = bool(_RAW_SEND.search(code))
    sends = lifecycle["stages"]["send_detected"]
    has_order_check = bool(_ORDER_CHECK.search(code))
    has_freeze_stops = bool(_FREEZE_STOPS.search(code))
    has_price_norm = bool(_PRICE_NORMALIZE.search(code))
    has_volume_norm = bool(_VOLUME_NORMALIZE.search(code)) or risk["invariants"]["volume_clamp"]
    has_margin_mode = bool(_MARGIN_MODE.search(code))
    has_margin_precheck = bool(_MARGIN_PRECHECK.search(code))
    has_retcode = lifecycle["stages"]["retcode_checked"]
    has_txn_hook = lifecycle["stages"]["transaction_hook"]

    rep = HygieneReport(source=source)
    rep.checklist = {
        "sends_orders": sends,
        "order_check_before_send": has_order_check,
        "freeze_stops_level": has_freeze_stops,
        "price_normalization": has_price_norm,
        "volume_normalization": has_volume_norm,
        "retcode_handling": has_retcode,
        "margin_mode_aware": has_margin_mode,
        "margin_precheck": has_margin_precheck,
        "trade_transaction_hook": has_txn_hook,
    }

    # OrderCheck/normalize checklist (only meaningful when the EA actually sends orders)
    if sends:
        if has_raw_send and not has_order_check:
            rep.findings.append(_f(
                "warn", "order_check_before_send",
                "Raw OrderSend()/OrderSendAsync() with no OrderCheck() call found.",
                "Call OrderCheck(request,check) before OrderSend to validate margin, "
                "volume and stops up-front (Korotky §6.4.11)."))
        if not has_volume_norm:
            rep.findings.append(_f(
                "warn", "volume_normalization",
                "No SYMBOL_VOLUME_MIN/MAX/STEP normalization detected before sizing.",
                "Clamp lot to [VOLUME_MIN, VOLUME_MAX] and round to VOLUME_STEP."))
        if not has_price_norm:
            rep.findings.append(_f(
                "warn", "price_normalization",
                "No NormalizeDouble/_Digits/tick-size price rounding detected.",
                "Round SL/TP/price to SYMBOL_DIGITS / SYMBOL_TRADE_TICK_SIZE."))
        if not has_freeze_stops:
            rep.findings.append(_f(
                "warn", "freeze_stops_level",
                "No SYMBOL_TRADE_STOPS_LEVEL / FREEZE_LEVEL respect detected.",
                "Reject/adjust SL/TP closer than STOPS_LEVEL and skip modifies "
                "inside FREEZE_LEVEL to avoid retcode 10016."))
        if not has_retcode:
            rep.findings.append(_f(
                "warn", "retcode_handling",
                "Order send without MqlTradeResult.retcode inspection.",
                "Inspect result.retcode (10004/10016/10019/10027) and handle/retry."))
        if not has_margin_precheck:
            rep.findings.append(_f(
                "info", "margin_precheck",
                "No OrderCalcMargin/OrderCalcProfit pre-trade estimate found.",
                "Estimate required margin before sizing to avoid 10019 'no money'."))

    # netting/hedging correctness
    if not has_margin_mode:
        rep.findings.append(_f(
            "info", "margin_mode_aware",
            "EA does not read ACCOUNT_MARGIN_MODE (netting vs hedging).",
            "Branch close/modify logic on hedging vs netting; on netting an "
            "opposite order nets the position rather than opening a new one."))
    if lifecycle["stages"]["async"] and not has_txn_hook:
        rep.findings.append(_f(
            "warn", "trade_transaction_hook",
            "Async sends without OnTradeTransaction reconciliation.",
            "Add OnTradeTransaction to reconcile async fills/cancels."))
    # Fold the basket netting/hedging hazard (graph already detects it) in as
    # an advisory hygiene finding so it shows up on this checklist too.
    for issue in basket["issues"]:
        rep.findings.append(_f(
            "warn", "basket_magic_filter", issue["evidence"], issue["recommendation"]))

    return rep


def render_report(rep: HygieneReport) -> str:
    lines = [
        "# TRADE-CALL HYGIENE",
        "",
        f"- Source: `{rep.source}`",
        "",
        "## Checklist",
    ]
    for k, v in rep.checklist.items():
        lines.append(f"- [{'x' if v else ' '}] {k}")
    lines += ["", "## Findings"]
    if rep.findings:
        for f in rep.findings:
            lines.append(f"- [{f['severity'].upper()}] {f['item']}: {f['detail']}")
            lines.append(f"  - → {f['recommendation']}")
    else:
        lines.append("- none (all hygiene items satisfied or EA sends no orders)")
    lines += [
        "",
        "> Advisory only — never asserts PASS/READY and never blocks the scan gate.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    ap = argparse.ArgumentParser(prog=TOOL, description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("source", nargs="?", type=Path, default=None,
                     help="Path to a .mq5/.mqh source file.")
    src.add_argument("--text", default=None, help="Analyze raw source text instead.")
    ap.add_argument("--out", type=Path, default=None)
    _agent_io.add_json_flag(ap)
    _agent_io.add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    if args.text is not None:
        rep = analyze_source(args.text, source="<text>")
    else:
        if args.source is None or not args.source.is_file():
            print(f"error: source not found: {args.source}", file=sys.stderr)
            return 2
        rep = analyze_source(read_mq5_text(args.source, errors="replace"),
                             source=str(args.source))

    md = render_report(rep)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")

    env = _agent_io.Envelope(
        tool=TOOL, ok=True, exit_code=0,
        summary=(f"{rep.to_dict()['warn_count']} warn / "
                 f"{rep.to_dict()['info_count']} info hygiene finding(s)"),
        data=rep.to_dict(),
        evidence=[rep.source] if rep.source != "<text>" else [],
        matrix_dim="d_execution", matrix_axis="static",
        matrix_status="WARN" if rep.findings else "PASS",
    )
    if args.emit_json:
        _agent_io.emit(env)
    else:
        sys.stdout.write(md if args.out is None else f"wrote {args.out}\n")
    if args.gate_report is not None:
        _agent_io.write_gate_report(env, args.gate_report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
