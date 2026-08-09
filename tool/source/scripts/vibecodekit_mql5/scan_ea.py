"""mql5-scan-ea -- SCAN REPORT for an existing EA source.

Where ``mql5-scan`` answers "what files are here?", ``mql5-scan-ea``
answers "what is THIS EA doing, and is it safe?". It runs cheap, static
heuristics over a single ``.mq5`` source (or raw text) and emits a SCAN
REPORT: detected behaviours, risk flags, and the safest pattern from the
``ea_patterns`` bank to steer the Vision step toward.

These are intentionally conservative *signals*, not a verdict -- the
report never claims PASS/READY. It feeds the human + RRI review.
"""

from __future__ import annotations
from .mq5_io import read_mq5_text

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit
from . import ea_patterns

TOOL = "mql5-scan-ea"

# (flag_id, severity, human-readable, compiled regex)
# severity: "high" = unbounded-risk smell, "warn" = needs a guard-rail,
# "info" = benign signal used for pattern inference.
_SIGNALS: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    ("martingale", "high", "Lot size multiplied/doubled after a loss",
     re.compile(r"(lot|lots|volume)\s*[\*]=?\s*([2-9]|1\.[5-9])", re.I)),
    ("lot-doubling", "high", "Explicit lot doubling (lot * 2)",
     re.compile(r"(lot|lots|volume)\w*\s*\*\s*2(\.0+)?\b", re.I)),
    ("grid", "warn", "Grid / ladder of orders detected",
     re.compile(r"\bgrid\b|grid_?step|gridstep|step\s*\*\s*point", re.I)),
    ("hedging", "warn", "Opposite-direction (hedging) orders",
     re.compile(r"\bhedg", re.I)),
    ("no-stop-loss", "warn", "OrderSend/trade with sl=0 (naked position)",
     re.compile(r"(sl\s*=\s*0(\.0+)?\b)|(\.SetTypeFilling)|(request\.sl\s*=\s*0)", re.I)),
    ("trend", "info", "Moving-average / trend filter present",
     re.compile(r"\biMA\b|MovingAverage|ema|sma|\btrend\b", re.I)),
    ("breakout", "info", "Breakout / range-escape logic",
     re.compile(r"break\s*out|highest\(|lowest\(|iHighest|iLowest", re.I)),
    ("mean-reversion", "info", "Band / reversion logic",
     re.compile(r"bollinger|iBands|revert|oversold|overbought|\brsi\b", re.I)),
    # --- v2.6 BIG HARDENING detections -------------------------------------
    ("raw-ordersend", "warn", "Raw OrderSend()/OrderSendAsync() instead of CTrade",
     re.compile(r"\bOrderSend(Async)?\s*\(", re.I)),
    ("ctrade", "info", "CTrade wrapper in use (preferred over raw OrderSend)",
     re.compile(r"\bCTrade\b|Trade/Trade\.mqh", re.I)),
    ("event-handler", "info", "Standard EA event handlers present (OnTick/OnInit/etc.)",
     re.compile(r"\bOn(Tick|Init|Deinit|Trade|TradeTransaction|Timer|Tester)\s*\(", re.I)),
    ("hardcoded-symbol", "warn", "Hardcoded symbol literal (use _Symbol / input instead)",
     re.compile(r"\"(XAU(USD)?|XAG(USD)?|EUR[A-Z]{3}|GBP[A-Z]{3}|USD[A-Z]{3}|US30|NAS100|BTCUSD)\"", re.I)),
    ("hardcoded-timeframe", "warn", "Hardcoded PERIOD_* literal (use _Period / input instead)",
     re.compile(r"\bPERIOD_(M1|M2|M3|M4|M5|M6|M10|M12|M15|M20|M30|H1|H2|H3|H4|H6|H8|H12|D1|W1|MN1)\b")),
    ("risk-input", "info", "Risk-style input (Lot/Risk/Volume) declared — confirm a cap guard exists",
     re.compile(r"input\s+\w+\s+\w*(Lot|Risk|Volume)\w*\s*=", re.I)),
)


@dataclass
class ScanEaReport:
    source: str
    behaviours: list[str] = field(default_factory=list)
    risk_flags: list[dict] = field(default_factory=list)
    recommended_pattern: str | None = None
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "behaviours": self.behaviours,
            "risk_flags": self.risk_flags,
            "recommended_pattern": self.recommended_pattern,
            "rationale": self.rationale,
        }


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    return text


def analyze_source(text: str, *, source: str = "<text>") -> ScanEaReport:
    """Run static heuristics over EA source text."""

    code = _strip_comments(text)
    rep = ScanEaReport(source=source)
    hits: dict[str, str] = {}
    for flag_id, severity, desc, rx in _SIGNALS:
        if rx.search(code):
            hits[flag_id] = severity
            rep.behaviours.append(flag_id)
            if severity in ("high", "warn"):
                rep.risk_flags.append({"id": flag_id, "severity": severity, "detail": desc})

    # Pattern recommendation: steer AWAY from unbounded risk toward the
    # safest defensible archetype. Order of preference mirrors the bank.
    rec: str | None = None
    why: str
    if "martingale" in hits or "lot-doubling" in hits:
        rec = "grid-safe"
        why = ("Unbounded-risk lot scaling detected -- if a ladder is truly "
               "required, migrate to the bounded grid-safe pattern (capped "
               "levels + drawdown freeze). Otherwise prefer trend-follow.")
    elif "grid" in hits or "hedging" in hits:
        rec = "grid-safe"
        why = "Grid/hedging behaviour -- adopt grid-safe rails (level cap + DD freeze)."
    elif "breakout" in hits:
        rec = "breakout"
        why = "Breakout signals dominate; enforce SL-inside-range rails."
    elif "mean-reversion" in hits:
        rec = "mean-reversion"
        why = "Reversion signals; cap exposure + hard invalidation stop."
    elif "trend" in hits:
        rec = "trend-follow"
        why = "Trend filter present; enforce single-position + mandatory SL."
    else:
        rec = "trend-follow"
        why = ("No decisive strategy signal; default to the safest archetype "
               "(trend-follow, single position, mandatory SL).")
    rep.recommended_pattern = rec
    rep.rationale = why
    return rep


def render_report(rep: ScanEaReport) -> str:
    lines = [
        "# EA SCAN REPORT",
        "",
        f"- Source: `{rep.source}`",
        f"- Behaviours detected: {', '.join(rep.behaviours) or 'none'}",
        "",
        "## Risk flags",
    ]
    if rep.risk_flags:
        for f in rep.risk_flags:
            lines.append(f"- [{f['severity'].upper()}] {f['id']}: {f['detail']}")
    else:
        lines.append("- none (no high/warn smells found)")
    lines += [
        "",
        "## Recommended safe pattern",
        f"- **{rep.recommended_pattern}** -- {rep.rationale}",
        "",
        "## Required safety rails",
    ]
    pat = ea_patterns.get_pattern(rep.recommended_pattern or "")
    if pat:
        lines += [f"- {r}" for r in pat["safety_rails"]]
    lines += [
        "",
        "> SCAN REPORT is advisory only -- it never asserts PASS/READY.",
        "> Feed it into Step-2 RRI + Step-3 VISION for human + persona review.",
        "",
    ]
    return "\n".join(lines)


def _render_graph_section(graphs: dict) -> str:
    """Render the v2.5 structured-graph findings as a markdown appendix."""
    ol = graphs.get("order_lifecycle", {}).get("stages", {})
    ri = graphs.get("risk_invariant", {}).get("invariants", {})
    lines = [
        "",
        "## Structured graph analysis (v2.5)",
        "",
        f"- Functions: {graphs.get('call_graph', {}).get('function_count', 0)} "
        f"| unreachable: {len(graphs.get('call_graph', {}).get('unreachable', []))}",
        f"- Unused inputs: {len(graphs.get('input_usage', {}).get('unused', []))}",
        f"- Order lifecycle: send={ol.get('send_detected')} async={ol.get('async')} "
        f"retcode_checked={ol.get('retcode_checked')} transaction_hook={ol.get('transaction_hook')}",
        f"- Risk invariants: lot_scaling={ri.get('lot_scaling_detected')} "
        f"level_cap={ri.get('level_cap')} volume_clamp={ri.get('volume_clamp')} "
        f"drawdown_stop={ri.get('drawdown_stop')} stop_loss={ri.get('stop_loss')}",
        "",
        "### Graph findings",
    ]
    issues = graphs.get("issues", [])
    if issues:
        for it in issues:
            lines.append(f"- [{it['severity'].upper()}] {it['title']} — {it['evidence']}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Static SCAN REPORT for an EA source.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("source", nargs="?", type=Path, default=None,
                     help="Path to a .mq5/.mqh source file.")
    src.add_argument("--text", default=None, help="Analyze raw source text instead of a file.")
    ap.add_argument("--out", type=Path, default=None, help="Write the report markdown here.")
    ap.add_argument("--graph", action="store_true",
                    help="Also run the v2.5 structured graphs (call / input-usage / "
                         "order-lifecycle / risk-invariant) for deeper, grounded findings.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    src_text: str | None = None
    if args.text is not None:
        src_text = args.text
        rep = analyze_source(args.text, source="<text>")
    else:
        if args.source is None or not args.source.is_file():
            if not args.emit_json:
                sys.stderr.write(f"error: source not found: {args.source}\n")
            env = Envelope(tool=TOOL, ok=False, exit_code=2,
                           summary=f"source not found: {args.source}",
                           data={"source": str(args.source)})
            maybe_emit(args, env)
            return 2
        src_text = read_mq5_text(args.source, errors="replace")
        rep = analyze_source(src_text, source=str(args.source))

    graph_result = None
    if args.graph and src_text is not None:
        from .mq5_graphs import analyze_source_graphs
        graph_result = analyze_source_graphs(src_text, source=rep.source)

    md = render_report(rep)
    if graph_result is not None:
        md += _render_graph_section(graph_result)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
    if not args.emit_json:
        sys.stdout.write(md if args.out is None else f"wrote {args.out}\n")

    high = [f for f in rep.risk_flags if f["severity"] == "high"]
    env = Envelope(
        tool=TOOL, ok=True, exit_code=0,
        summary=(f"{len(rep.behaviours)} behaviour(s), {len(rep.risk_flags)} risk flag(s); "
                 f"recommend {rep.recommended_pattern}"),
        data=rep.to_dict(),
        evidence=[rep.source] if rep.source != "<text>" else [],
    )
    if graph_result is not None:
        env.data["graphs"] = graph_result
    maybe_emit(args, env)
    # Advisory tool: do not fail the process on smells (exit 0); callers
    # gate on the JSON risk_flags. high-severity count surfaced in data.
    env.data["high_severity_count"] = len(high)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
