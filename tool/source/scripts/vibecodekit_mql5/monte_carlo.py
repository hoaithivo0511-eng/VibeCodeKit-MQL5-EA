"""mql5-monte-carlo — bootstrap trade history → DD distribution.

Given a flat trade-return series (CSV of one number per row, or list passed
programmatically), perform `N` shuffles (default 1000), compute the running
equity curve, and extract the max drawdown of each simulation. Report the
50th, 75th, and 95th percentile of the DD distribution.

Acceptance:
    P95(DD_sim) <= 1.5 × reported_DD   → PASS
    P95 > 1.5 × reported              → WARN/FAIL

CLI:
    python -m vibecodekit_mql5.monte_carlo <returns.csv> --reported-dd 8.2

Exit codes:
    0 — PASS
    1 — FAIL (P95 > 1.5×)
    2 — invocation error
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

@dataclass
class MonteCarloResult:
    n_sims: int
    p50_dd: float
    p75_dd: float
    p95_dd: float
    reported_dd: float
    verdict: str  # "PASS" | "FAIL"

    def to_dict(self) -> dict:
        return {
            "n_sims": self.n_sims,
            "p50_dd": round(self.p50_dd, 4),
            "p75_dd": round(self.p75_dd, 4),
            "p95_dd": round(self.p95_dd, 4),
            "reported_dd": self.reported_dd,
            "verdict": self.verdict,
        }


def max_drawdown_pct(returns: list[float]) -> float:
    """Compute peak-to-trough drawdown as a percentage of running peak equity.

    Uses an arithmetic running balance starting at 0 (returns interpreted as
    monetary P&L, so DD is reported as a percentage of peak running equity
    above a $1 floor — same approximation MT5 uses for tiny early peaks).
    """
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in returns:
        eq += r
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    return max_dd


def percentile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank percentile on a pre-sorted list. `q` in [0,100]."""
    if not sorted_values:
        return 0.0
    if q <= 0:
        return sorted_values[0]
    if q >= 100:
        return sorted_values[-1]
    rank = int(round(q / 100.0 * (len(sorted_values) - 1)))
    return sorted_values[rank]


def bootstrap(
    returns: list[float],
    n_sims: int = 1000,
    *,
    seed: int | None = None,
    with_replacement: bool = True,
) -> list[float]:
    """Return DD values for ``n_sims`` resamples of ``returns``.

    A real bootstrap samples *with replacement* (each sim can repeat/drop
    trades, widening the DD distribution). Set ``with_replacement=False``
    for the legacy permutation/shuffle behaviour.
    """
    rng = random.Random(seed)
    n = len(returns)
    out: list[float] = []
    for _ in range(n_sims):
        if with_replacement:
            sample = rng.choices(returns, k=n)
        else:
            sample = list(returns)
            rng.shuffle(sample)
        out.append(max_drawdown_pct(sample))
    return out


def evaluate(
    returns: list[float],
    reported_dd: float,
    *,
    n_sims: int = 1000,
    seed: int | None = None,
) -> MonteCarloResult:
    dds = sorted(bootstrap(returns, n_sims=n_sims, seed=seed))
    p50 = percentile(dds, 50)
    p75 = percentile(dds, 75)
    p95 = percentile(dds, 95)
    threshold = 1.5 * reported_dd
    verdict = "PASS" if p95 <= threshold else "FAIL"
    return MonteCarloResult(n_sims=n_sims, p50_dd=p50, p75_dd=p75, p95_dd=p95,
                            reported_dd=reported_dd, verdict=verdict)


def _read_returns_csv(path: Path) -> list[float]:
    out: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(float(line.split(",")[0]))
        except ValueError:
            continue
    return out


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io
    from .console import ensure_utf8_stdio

    ensure_utf8_stdio()

    p = argparse.ArgumentParser(prog="mql5-monte-carlo", description=__doc__.splitlines()[0])
    p.add_argument("returns_csv", help="One return per row (CSV header optional)")
    p.add_argument("--reported-dd", type=float, required=True,
                   help="Backtest's reported MaxDD in percent")
    p.add_argument("--n-sims", type=int, default=1000)
    p.add_argument("--seed", type=int, default=42)
    _agent_io.add_json_flag(p)
    _agent_io.add_gate_report_flag(p)
    args = p.parse_args(argv)

    returns = _read_returns_csv(Path(args.returns_csv))
    if not returns:
        print("[monte_carlo] no returns parsed", file=sys.stderr)
        return 2

    result = evaluate(returns, args.reported_dd, n_sims=args.n_sims, seed=args.seed)
    ok = result.verdict == "PASS"

    envelope = _agent_io.Envelope(
        tool="mql5-monte-carlo",
        ok=ok,
        exit_code=0 if ok else 1,
        summary=f"monte-carlo verdict: {result.verdict} (n_sims={args.n_sims})",
        data=result.to_dict(),
        evidence=[args.returns_csv],
        matrix_dim="d_robustness",
        matrix_axis="backtest",
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
