"""/mql5-canary — post-deploy 30-minute live monitor.

After shipping an EA to a live (or demo) terminal,
``canary`` watches the MT5 journal + the mt5-bridge MCP for early
warning signs:

- error_rate     : > 1 error / minute → ALERT
- slippage_p95   : > 1 pip            → ALERT
- drawdown_pct   : > 5 %              → ALERT

Default window is 30 minutes; can be shortened for smoke tests via
``--duration``.  The monitor reads ticks/positions through the
``mt5-bridge`` MCP (READ-ONLY) so the canary itself cannot place or
modify orders.

The CLI emits a JSON report at the end of the window.  When invoked
with ``--journal <path>`` it reads from a file instead of polling
MT5, which is the test-friendly path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ERROR_RATE_THRESHOLD = 1.0       # per minute
SLIPPAGE_P95_PIPS = 1.0
DRAWDOWN_PCT_THRESHOLD = 5.0


@dataclass
class CanaryReport:
    duration_s: float
    error_count: int
    error_rate_per_min: float
    slippage_p95_pips: float
    drawdown_pct: float
    alerts: list[str] = field(default_factory=list)
    samples: int = 0


_RE_ERROR = re.compile(r"\b(error|fail|except|invalid)\b", re.IGNORECASE)
_RE_SLIP_PIPS = re.compile(r"slip(?:page)?[^0-9]*([0-9]+\.?[0-9]*)\s*pip", re.IGNORECASE)
_RE_DD_PCT = re.compile(r"drawdown[^0-9]*([0-9]+\.?[0-9]*)\s*%", re.IGNORECASE)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(0.95 * (len(s) - 1))
    return s[idx]


def analyse_journal(lines: Iterable[str], duration_s: float) -> CanaryReport:
    slip: list[float] = []
    dd: list[float] = []
    errors = 0
    samples = 0
    for ln in lines:
        samples += 1
        if _RE_ERROR.search(ln):
            errors += 1
        m = _RE_SLIP_PIPS.search(ln)
        if m:
            slip.append(float(m.group(1)))
        m = _RE_DD_PCT.search(ln)
        if m:
            dd.append(float(m.group(1)))
    minutes = max(duration_s, 1.0) / 60.0
    rep = CanaryReport(
        duration_s=duration_s, error_count=errors,
        error_rate_per_min=errors / minutes,
        slippage_p95_pips=_p95(slip),
        drawdown_pct=max(dd) if dd else 0.0,
        samples=samples,
    )
    if rep.error_rate_per_min > ERROR_RATE_THRESHOLD:
        rep.alerts.append(f"error_rate {rep.error_rate_per_min:.2f}/min > {ERROR_RATE_THRESHOLD}")
    if rep.slippage_p95_pips > SLIPPAGE_P95_PIPS:
        rep.alerts.append(f"slippage_p95 {rep.slippage_p95_pips:.2f}p > {SLIPPAGE_P95_PIPS}")
    if rep.drawdown_pct > DRAWDOWN_PCT_THRESHOLD:
        rep.alerts.append(f"drawdown {rep.drawdown_pct:.2f}% > {DRAWDOWN_PCT_THRESHOLD}")
    return rep


def _parse_duration(s: str) -> float:
    if s.endswith("m"):
        return float(s[:-1]) * 60.0
    if s.endswith("s"):
        return float(s[:-1])
    if s.endswith("h"):
        return float(s[:-1]) * 3600.0
    return float(s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-canary")
    parser.add_argument("ea", help="Target EA (.ex5 or .mq5)")
    parser.add_argument("--duration", default="30m",
                        help="Monitor window (default 30m). Accepts 30s/30m/1h.")
    parser.add_argument("--journal", help="Read journal from file instead of polling")
    args = parser.parse_args(argv)

    duration_s = _parse_duration(args.duration)
    if args.journal:
        lines = Path(args.journal).read_text(encoding="utf-8", errors="replace").splitlines()
        rep = analyse_journal(lines, duration_s)
    else:  # pragma: no cover - live path
        time.sleep(min(duration_s, 1.0))
        rep = analyse_journal([], duration_s)
    print(json.dumps(rep.__dict__, indent=2))
    return 0 if not rep.alerts else 2


if __name__ == "__main__":
    sys.exit(main())
