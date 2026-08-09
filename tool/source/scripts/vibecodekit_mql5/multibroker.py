"""mql5-multibroker — run a backtest on N broker accounts; check stability.

This orchestrator does NOT itself open broker connections. It accepts a
list of pre-run backtest XML reports (one per broker) and computes the
stability metrics from the kit spec §12:

    PF_stdev / PF_mean   <= 0.30   → PASS for stability
    Sharpe_stdev         <= 0.20   → PASS for stability
    DD_diff (max - min)  <=  5.0   → PASS for stability

Also verifies that each report's "journal" sidecar (if present) contains
at least one ``[PipNorm]`` log line — a downstream signal that the EA
*actually* called `CPipNormalizer` on this broker.

CLI (orchestrator mode):
    python -m vibecodekit_mql5.multibroker --reports fx.xml,ex.xml,ic.xml \
        [--journals fx.log,ex.log,ic.log]

Exit codes:
    0 — all 3 stability checks PASS and PipNorm log present
    1 — any stability check FAIL
    2 — invocation error
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from vibecodekit_mql5.backtest import BacktestResult, parse_xml_report_file


PF_CV_MAX = 0.30        # CV = stdev / mean
SHARPE_STDEV_MAX = 0.20
DD_DIFF_MAX = 5.0


@dataclass
class StabilityResult:
    pf_mean: float
    pf_stdev: float
    pf_cv: float
    sharpe_mean: float
    sharpe_stdev: float
    dd_diff: float
    pipnorm_log_seen: list[str]
    verdict: str  # "PASS" | "FAIL"
    details: list[str]

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["pf_mean"] = round(self.pf_mean, 4)
        d["pf_stdev"] = round(self.pf_stdev, 4)
        d["pf_cv"] = round(self.pf_cv, 4)
        d["sharpe_mean"] = round(self.sharpe_mean, 4)
        d["sharpe_stdev"] = round(self.sharpe_stdev, 4)
        d["dd_diff"] = round(self.dd_diff, 4)
        return d


def _cv(values: list[float]) -> tuple[float, float, float]:
    """Return (mean, stdev, cv) — cv = stdev/mean or 0 if mean<=0."""
    if not values:
        return 0.0, 0.0, 0.0
    m = statistics.fmean(values)
    s = statistics.pstdev(values)  # population stdev (small N)
    cv = s / m if m > 0 else 0.0
    return m, s, cv


def evaluate(
    reports: list[BacktestResult],
    *,
    journals: list[str] | None = None,
) -> StabilityResult:
    pf_vals = [r.profit_factor for r in reports]
    sh_vals = [r.sharpe for r in reports]
    dd_vals = [r.max_drawdown_pct for r in reports]

    pf_mean, pf_stdev, pf_cv = _cv(pf_vals)
    sh_mean, sh_stdev, _ = _cv(sh_vals)
    dd_diff = (max(dd_vals) - min(dd_vals)) if dd_vals else 0.0

    pipnorm_log_seen: list[str] = []
    if journals:
        for j in journals:
            text = Path(j).read_text(encoding="utf-8", errors="replace") if Path(j).exists() else ""
            if "[PipNorm]" in text:
                pipnorm_log_seen.append(j)

    details: list[str] = []
    if pf_cv > PF_CV_MAX:
        details.append(f"PF CV {pf_cv:.3f} > {PF_CV_MAX}")
    if sh_stdev > SHARPE_STDEV_MAX:
        details.append(f"Sharpe stdev {sh_stdev:.3f} > {SHARPE_STDEV_MAX}")
    if dd_diff > DD_DIFF_MAX:
        details.append(f"DD diff {dd_diff:.2f} > {DD_DIFF_MAX}")
    if journals and len(pipnorm_log_seen) < len(journals):
        details.append(f"[PipNorm] log missing in "
                       f"{len(journals) - len(pipnorm_log_seen)}/{len(journals)} journals")

    verdict = "PASS" if not details else "FAIL"
    return StabilityResult(
        pf_mean=pf_mean, pf_stdev=pf_stdev, pf_cv=pf_cv,
        sharpe_mean=sh_mean, sharpe_stdev=sh_stdev,
        dd_diff=dd_diff,
        pipnorm_log_seen=pipnorm_log_seen,
        verdict=verdict, details=details,
    )


def _split(s: str | None) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    p = argparse.ArgumentParser(prog="mql5-multibroker", description=__doc__.splitlines()[0])
    p.add_argument("--reports", required=True, help="Comma-sep paths to per-broker XML reports")
    p.add_argument("--journals", default=None, help="Comma-sep paths to per-broker journal .log")
    _agent_io.add_json_flag(p)
    _agent_io.add_gate_report_flag(p)
    args = p.parse_args(argv)

    rpaths = _split(args.reports)
    if len(rpaths) < 2:
        print("[multibroker] need >= 2 reports", file=sys.stderr)
        return 2

    reports = []
    for rp in rpaths:
        try:
            reports.append(parse_xml_report_file(Path(rp)))
        except FileNotFoundError as e:
            print(f"[multibroker] missing: {e}", file=sys.stderr)
            return 2

    result = evaluate(reports, journals=_split(args.journals))
    ok = result.verdict == "PASS"

    envelope = _agent_io.Envelope(
        tool="mql5-multibroker",
        ok=ok,
        exit_code=0 if ok else 1,
        summary=f"multibroker verdict: {result.verdict} ({len(reports)} broker(s))",
        data=result.to_dict(),
        evidence=list(rpaths) + _split(args.journals),
        matrix_dim="d_broker_safety",
        matrix_axis="multi_broker",
        matrix_status=result.verdict if result.verdict in ("PASS", "WARN", "FAIL") else "N/A",
    )

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        print(json.dumps(result.to_dict(), indent=2))

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
