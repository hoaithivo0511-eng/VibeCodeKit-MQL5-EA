"""mql5-backtest-quality — quantitative backtest-quality gate.

The pre-existing :mod:`vibecodekit_mql5.backtest` parser already extracts every
metric MT5 writes to its XML report (profit factor, recovery factor, Sharpe,
expected payoff, max-drawdown%, LR correlation, trade count, …). What it did
NOT do was *judge* those numbers — a parsed report with a profit factor of 0.4
was reported exactly like one with 2.5. This module closes that gap.

Grounded in the two MQL5 references researched in report §20:

* Korotky, *MQL5 Programming for Traders* §6.5.5/6.5.6 — the built-in Strategy
  Tester optimization criteria (max profit factor / recovery factor / Sharpe /
  expected payoff / min drawdown) and the 0–100 "complex criterion".
* The balance-curve linear-regression statistics (``LRCorrelation``); R² is the
  square of that correlation and measures how linear (steady) the equity curve
  is — a high R² is the classic over-fit / curve-smoothness check.

Honesty contract (unchanged kit rule): this gate judges *metrics that already
exist in a report*. It never invents a backtest. If the report is a sample /
fixture (``tests/`` …), ``release_trusted`` is ``False`` so a green quality
verdict can never by itself make a build release-eligible. If the trade count
is below ``min_trades`` the verdict is ``INSUFFICIENT`` (treated as not-OK),
never a PASS — too few trades is not evidence of quality.

CLI::

    python -m vibecodekit_mql5.backtest_quality <report.xml> [--min-trades 30]
        [--profit-factor-pass 1.3] [--max-dd-pass 20] [--json]

Exit codes::

    0 — verdict PASS or WARN
    1 — verdict FAIL or INSUFFICIENT
    2 — invocation / parse error
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .backtest import BacktestResult, parse_xml_report_file
from . import release_policy


# A metric verdict is the worst tier any single metric reaches.
_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2, "INSUFFICIENT": 3}


@dataclass
class QualityThresholds:
    """Two-tier (PASS / WARN) thresholds. Defaults are deliberately
    conservative, industry-typical retail-EA acceptance bars — they are NOT a
    profitability guarantee and are documented as kit defaults the owner may
    override per strategy."""

    min_trades: int = 30
    # higher-is-better metrics: (pass, warn)
    profit_factor: tuple[float, float] = (1.3, 1.1)
    recovery_factor: tuple[float, float] = (2.0, 1.0)
    sharpe: tuple[float, float] = (1.0, 0.5)
    r2: tuple[float, float] = (0.90, 0.80)
    # expected payoff must simply be positive to PASS, >=0 to WARN
    expected_payoff: tuple[float, float] = (0.0, 0.0)
    # lower-is-better: (pass_ceiling, warn_ceiling)
    max_drawdown_pct: tuple[float, float] = (20.0, 35.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_trades": self.min_trades,
            "profit_factor": list(self.profit_factor),
            "recovery_factor": list(self.recovery_factor),
            "sharpe": list(self.sharpe),
            "r2": list(self.r2),
            "expected_payoff": list(self.expected_payoff),
            "max_drawdown_pct": list(self.max_drawdown_pct),
        }


@dataclass
class MetricVerdict:
    name: str
    value: float
    verdict: str  # PASS | WARN | FAIL
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "verdict": self.verdict, "detail": self.detail}


@dataclass
class QualityReport:
    verdict: str
    metrics: list[MetricVerdict] = field(default_factory=list)
    complex_criterion: float = 0.0
    r2: float = 0.0
    total_trades: int = 0
    release_trusted: bool = False
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "complex_criterion": round(self.complex_criterion, 1),
            "r2": round(self.r2, 4),
            "total_trades": self.total_trades,
            "release_trusted": self.release_trusted,
            "source": self.source,
            "metrics": [m.to_dict() for m in self.metrics],
            # A green metric verdict is NOT release-eligibility on its own.
            "backtest_ok": self.verdict in ("PASS", "WARN") and self.release_trusted,
        }


def _grade_high(value: float, thr: tuple[float, float]) -> str:
    p, w = thr
    if value >= p:
        return "PASS"
    if value >= w:
        return "WARN"
    return "FAIL"


def _grade_low(value: float, thr: tuple[float, float]) -> str:
    p, w = thr
    if value <= p:
        return "PASS"
    if value <= w:
        return "WARN"
    return "FAIL"


def _grade_payoff(value: float, thr: tuple[float, float]) -> str:
    p, _ = thr
    if value > p:
        return "PASS"
    if value == p:
        return "WARN"
    return "FAIL"


def compute_r2(result: BacktestResult) -> float:
    """R² of the balance curve = LRCorrelation². Clamped to [0,1]."""
    corr = result.lr_correlation
    if corr is None:
        return 0.0
    return max(0.0, min(1.0, corr * corr))


def complex_criterion(result: BacktestResult) -> float:
    """Transparent 0–100 composite inspired by Korotky §6.5.6 "complex
    criterion" (deals + drawdown + recovery + expectation + Sharpe).

    This is an INTERNAL, documented heuristic — not the proprietary MetaQuotes
    formula — so it is disclosed as such in the evidence/methodology block. It
    blends five normalised sub-scores with equal weight.
    """
    def clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    trades_s = clamp01(result.total_trades / 200.0)
    dd_s = clamp01(1.0 - (result.max_drawdown_pct / 50.0))
    rec_s = clamp01(result.recovery_factor / 3.0)
    pf_s = clamp01((result.profit_factor - 1.0) / 1.0) if result.profit_factor else 0.0
    sharpe_s = clamp01(result.sharpe / 2.0)
    score = (trades_s + dd_s + rec_s + pf_s + sharpe_s) / 5.0 * 100.0
    if result.profit_factor and result.profit_factor < 1.0:
        score = min(score, 19.0)  # unprofitable → "red" band (<20) like the book
    return round(score, 1)


def evaluate(
    result: BacktestResult,
    thresholds: QualityThresholds | None = None,
    *,
    source: str = "",
    release_trusted: bool = False,
) -> QualityReport:
    thr = thresholds or QualityThresholds()
    r2 = compute_r2(result)
    metrics = [
        MetricVerdict("profit_factor", result.profit_factor,
                      _grade_high(result.profit_factor, thr.profit_factor),
                      f"pass>={thr.profit_factor[0]} warn>={thr.profit_factor[1]}"),
        MetricVerdict("recovery_factor", result.recovery_factor,
                      _grade_high(result.recovery_factor, thr.recovery_factor),
                      f"pass>={thr.recovery_factor[0]} warn>={thr.recovery_factor[1]}"),
        MetricVerdict("sharpe", result.sharpe,
                      _grade_high(result.sharpe, thr.sharpe),
                      f"pass>={thr.sharpe[0]} warn>={thr.sharpe[1]}"),
        MetricVerdict("r2", round(r2, 4),
                      _grade_high(r2, thr.r2),
                      f"balance-curve linearity; pass>={thr.r2[0]} warn>={thr.r2[1]}"),
        MetricVerdict("expected_payoff", result.expected_payoff,
                      _grade_payoff(result.expected_payoff, thr.expected_payoff),
                      "must be > 0"),
        MetricVerdict("max_drawdown_pct", result.max_drawdown_pct,
                      _grade_low(result.max_drawdown_pct, thr.max_drawdown_pct),
                      f"lower better; pass<={thr.max_drawdown_pct[0]} warn<={thr.max_drawdown_pct[1]}"),
    ]

    # Too few trades → statistically meaningless: INSUFFICIENT, never PASS.
    if result.total_trades < thr.min_trades:
        verdict = "INSUFFICIENT"
    else:
        worst = max((_ORDER[m.verdict] for m in metrics), default=0)
        verdict = {0: "PASS", 1: "WARN", 2: "FAIL"}[worst]

    return QualityReport(
        verdict=verdict,
        metrics=metrics,
        complex_criterion=complex_criterion(result),
        r2=r2,
        total_trades=result.total_trades,
        release_trusted=release_trusted,
        source=source,
    )


def render_report(rep: QualityReport) -> str:
    lines = [
        "# BACKTEST QUALITY GATE",
        "",
        f"- Source: `{rep.source}`",
        f"- Overall verdict: **{rep.verdict}**",
        f"- Complex criterion (0–100, internal heuristic): {rep.complex_criterion}",
        f"- Balance-curve R²: {round(rep.r2, 4)}",
        f"- Trades: {rep.total_trades}",
        f"- Release-trusted source: {rep.release_trusted}",
        "",
        "| Metric | Value | Verdict | Threshold |",
        "|---|---|---|---|",
    ]
    for m in rep.metrics:
        lines.append(f"| {m.name} | {m.value} | {m.verdict} | {m.detail} |")
    lines += [
        "",
        "> Quality verdict judges metrics only. A green verdict on a fixture",
        "> report is NOT release-eligibility — release still requires a real,",
        "> hashed Strategy-Tester report (release_trusted=true).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    p = argparse.ArgumentParser(prog="mql5-backtest-quality",
                                description=__doc__.splitlines()[0])
    p.add_argument("report", help="Strategy Tester XML report to grade.")
    p.add_argument("--min-trades", type=int, default=30)
    p.add_argument("--profit-factor-pass", type=float, default=None)
    p.add_argument("--max-dd-pass", type=float, default=None)
    p.add_argument("--out", type=Path, default=None, help="Write the markdown report here.")
    _agent_io.add_json_flag(p)
    _agent_io.add_gate_report_flag(p)
    args = p.parse_args(argv)

    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"[backtest-quality] report not found: {report_path}", file=sys.stderr)
        return 2
    try:
        result = parse_xml_report_file(report_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[backtest-quality] could not parse report: {exc}", file=sys.stderr)
        return 2

    thr = QualityThresholds(min_trades=args.min_trades)
    if args.profit_factor_pass is not None:
        thr.profit_factor = (args.profit_factor_pass, thr.profit_factor[1])
    if args.max_dd_pass is not None:
        thr.max_drawdown_pct = (args.max_dd_pass, thr.max_drawdown_pct[1])

    release_trusted = not release_policy.is_fixture_path(report_path)
    rep = evaluate(result, thr, source=str(report_path), release_trusted=release_trusted)
    ok = rep.verdict in ("PASS", "WARN")

    md = render_report(rep)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")

    envelope = _agent_io.Envelope(
        tool="mql5-backtest-quality",
        ok=ok,
        exit_code=0 if ok else 1,
        summary=(f"quality verdict: {rep.verdict} "
                 f"(PF={result.profit_factor}, RF={result.recovery_factor}, "
                 f"Sharpe={result.sharpe}, R2={round(rep.r2,3)}, DD%={result.max_drawdown_pct}); "
                 f"release_trusted={release_trusted}"),
        data=rep.to_dict(),
        evidence=[str(report_path)],
        matrix_dim="d_robustness",
        matrix_axis="backtest",
        matrix_status=rep.verdict if rep.verdict in ("PASS", "WARN", "FAIL") else "FAIL",
    )
    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        sys.stdout.write(md if args.out is None else f"wrote {args.out}\n")
    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
