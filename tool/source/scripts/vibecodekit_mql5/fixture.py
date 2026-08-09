"""mql5-fixture — hermetic synthetic MetaTrader 5 report generator.

Generates deterministic, parseable XML reports that look like MT5's
Strategy Tester output so the entire backtest pipeline (backtest /
walkforward / monte-carlo / multibroker) can run on Linux **without
Wine + MetaTrader**. Closes the "loop breaks if you don't have MT5"
gap called out in the v0.0.1 review.

Two synthesis strategies:

    --strategy random      i.i.d. uniform-noise returns; tends to FAIL
                           walkforward (no edge); useful for negative-test
                           fixtures.
    --strategy trend       drifted returns with mild OOS decay; tends to
                           PASS walkforward + monte-carlo at default
                           thresholds; useful for happy-path fixtures.
    --strategy mean-rev    mean-reverting returns with neutral OOS; tends
                           to PASS multibroker stability + WARN walk-forward.

The output filenames follow a stable convention so downstream gates can
discover them: ``<out>/<type>-<strategy>-<seed>.xml`` plus, for
``--type backtest``, a matching ``returns.csv`` for ``mql5-monte-carlo``.

CLI::

    python -m vibecodekit_mql5.fixture \\
        --type backtest --strategy trend --seed 42 \\
        --out tests/fixtures/generated/

    python -m vibecodekit_mql5.fixture \\
        --type walkforward --strategy trend --seed 42 \\
        --out tests/fixtures/generated/

    python -m vibecodekit_mql5.fixture \\
        --type multibroker --strategy trend --seed 42 --brokers 3 \\
        --out tests/fixtures/generated/

All synthesised numbers are deterministic for a given ``--seed`` so
fixtures are reproducible across runs and CI machines.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from . import _agent_io

# ----------------------------------------------------------------------------
# Strategy synthesisers — generate one trade-return series each.
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Series:
    returns: list[float]
    label: str

    @property
    def total_trades(self) -> int:
        return len(self.returns)

    @property
    def profitable_pct(self) -> float:
        if not self.returns:
            return 0.0
        return 100.0 * sum(1 for r in self.returns if r > 0) / len(self.returns)

    @property
    def profit_factor(self) -> float:
        wins = sum(r for r in self.returns if r > 0)
        losses = -sum(r for r in self.returns if r < 0)
        if losses < 1e-9:
            return 99.0 if wins > 0 else 0.0
        return wins / losses

    @property
    def sharpe(self) -> float:
        if len(self.returns) < 2:
            return 0.0
        mean = statistics.fmean(self.returns)
        stdev = statistics.pstdev(self.returns)
        if stdev < 1e-9:
            return 0.0
        return mean / stdev

    @property
    def max_drawdown_pct(self) -> float:
        peak = 0.0
        equity = 0.0
        max_dd = 0.0
        for r in self.returns:
            equity += r
            peak = max(peak, equity)
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        # Express drawdown as a percent of starting nominal $10k.
        return round(100.0 * max_dd / 10_000.0, 2)


def _synth_random(rng: random.Random, n: int) -> list[float]:
    return [round(rng.uniform(-50.0, 50.0), 2) for _ in range(n)]


def _synth_trend(rng: random.Random, n: int, drift: float = 6.0) -> list[float]:
    return [round(drift + rng.gauss(0.0, 25.0), 2) for _ in range(n)]


def _synth_mean_rev(rng: random.Random, n: int) -> list[float]:
    out: list[float] = []
    prev = 0.0
    for _ in range(n):
        nxt = -0.5 * prev + rng.gauss(0.0, 20.0)
        prev = nxt
        out.append(round(nxt, 2))
    return out


def synth(strategy: str, seed: int, n: int) -> Series:
    rng = random.Random(seed)
    if strategy == "random":
        return Series(_synth_random(rng, n), strategy)
    if strategy == "trend":
        return Series(_synth_trend(rng, n), strategy)
    if strategy == "mean-rev":
        return Series(_synth_mean_rev(rng, n), strategy)
    raise ValueError(f"unknown strategy: {strategy!r}")


# ----------------------------------------------------------------------------
# XML emission — matches the parser at scripts/vibecodekit_mql5/backtest.py
# ----------------------------------------------------------------------------

def series_to_report_xml(
    series: Series,
    *,
    symbol: str = "EURUSD",
    period: str = "H1",
    from_date: str = "2023.01.01",
    to_date: str = "2024.12.31",
    report_date: str = "2024.12.31",
    broker_digits: int = 5,
) -> str:
    pf = series.profit_factor
    sr = series.sharpe
    dd = series.max_drawdown_pct
    n = series.total_trades
    win_pct = series.profitable_pct

    # Streak heuristic — long enough to be parseable, doesn't matter much
    # downstream because walkforward / monte-carlo don't read it.
    streak_w = max(1, int(n * 0.04))
    streak_l = max(1, int(n * 0.02))

    return (
        '<?xml version="1.0" encoding="UTF-16" ?>\n'
        '<!--\n'
        '  Synthetic MT5 Strategy Tester report.\n'
        '  Generated by mql5-fixture; do NOT edit by hand.\n'
        f'  strategy={series.label} seed-deterministic, n={n} trades.\n'
        '-->\n'
        '<TesterReport>\n'
        f'    <Symbol>{symbol}</Symbol>\n'
        f'    <Period>{period}</Period>\n'
        f'    <ReportDate>{report_date}</ReportDate>\n'
        f'    <FromDate>{from_date}</FromDate>\n'
        f'    <ToDate>{to_date}</ToDate>\n'
        '    <Statistics>\n'
        f'        <ProfitFactor>{pf:.2f}</ProfitFactor>\n'
        '        <RecoveryFactor>2.10</RecoveryFactor>\n'
        f'        <SharpeRatio>{sr:.3f}</SharpeRatio>\n'
        '        <GHPR>0.20</GHPR>\n'
        '        <AHPR>0.25</AHPR>\n'
        '        <ExpectedPayoff>10.0</ExpectedPayoff>\n'
        '        <LRCorrelation>0.50</LRCorrelation>\n'
        '        <LRStdError>0.05</LRStdError>\n'
        f'        <MaxDrawdownPct>{dd:.2f}</MaxDrawdownPct>\n'
        f'        <TotalTrades>{n}</TotalTrades>\n'
        f'        <ProfitablePct>{win_pct:.1f}</ProfitablePct>\n'
        f'        <WinningStreak>{streak_w}</WinningStreak>\n'
        f'        <LosingStreak>{streak_l}</LosingStreak>\n'
        '        <MFECorrelation>0.50</MFECorrelation>\n'
        '        <MAECorrelation>0.45</MAECorrelation>\n'
        f'        <BrokerDigits>{broker_digits}</BrokerDigits>\n'
        '    </Statistics>\n'
        '</TesterReport>\n'
    )


def series_to_journal(series: Series, *, with_pipnorm: bool = True) -> str:
    """Generate a synthetic journal log for multibroker pip-norm checks."""

    lines = [
        f"# Synthetic journal — strategy={series.label}, trades={series.total_trades}",
    ]
    if with_pipnorm:
        lines.append("2024.06.01 09:00:00.000  EURUSD [PipNorm] base_digits=5 pip=0.00010")
    for i, r in enumerate(series.returns[:10], start=1):
        lines.append(f"2024.06.01 09:{i:02d}:00.000  Trade#{i:03d} pnl={r:+.2f}")
    return "\n".join(lines) + "\n"


def series_to_returns_csv(series: Series) -> str:
    out = ["return"]
    out.extend(f"{r:.2f}" for r in series.returns)
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------
# Dispatch per --type
# ----------------------------------------------------------------------------

def emit_backtest(args: argparse.Namespace, out: Path) -> list[Path]:
    series = synth(args.strategy, args.seed, args.trades)
    paths: list[Path] = []
    xml_path = out / f"backtest-{args.strategy}-{args.seed}.xml"
    xml_path.write_text(series_to_report_xml(series, symbol=args.symbol, period=args.tf),
                        encoding="utf-8")
    paths.append(xml_path)
    csv_path = out / f"backtest-{args.strategy}-{args.seed}.returns.csv"
    csv_path.write_text(series_to_returns_csv(series), encoding="utf-8")
    paths.append(csv_path)
    return paths


def emit_walkforward(args: argparse.Namespace, out: Path) -> list[Path]:
    # Use 75% IS / 25% OOS. For trend, OOS decays slightly so ratio ≈ 0.6-0.9.
    is_series = synth(args.strategy, args.seed, int(args.trades * 0.75))
    if args.strategy == "trend":
        oos_series = synth("trend", args.seed + 1, args.trades - is_series.total_trades)
    elif args.strategy == "mean-rev":
        oos_series = synth("mean-rev", args.seed + 1, args.trades - is_series.total_trades)
    else:
        oos_series = synth("random", args.seed + 1, args.trades - is_series.total_trades)
    paths = [
        out / f"walkforward-{args.strategy}-{args.seed}-IS.xml",
        out / f"walkforward-{args.strategy}-{args.seed}-OOS.xml",
    ]
    paths[0].write_text(series_to_report_xml(is_series, symbol=args.symbol, period=args.tf),
                        encoding="utf-8")
    paths[1].write_text(series_to_report_xml(oos_series, symbol=args.symbol, period=args.tf),
                        encoding="utf-8")
    return paths


def emit_monte_carlo(args: argparse.Namespace, out: Path) -> list[Path]:
    series = synth(args.strategy, args.seed, args.trades)
    csv_path = out / f"montecarlo-{args.strategy}-{args.seed}.returns.csv"
    csv_path.write_text(series_to_returns_csv(series), encoding="utf-8")
    return [csv_path]


def emit_multibroker(args: argparse.Namespace, out: Path) -> list[Path]:
    paths: list[Path] = []
    for i in range(args.brokers):
        # Each broker is a small perturbation of the base seed so the
        # multibroker stability heuristic (PF/Sharpe/DD spread) gets
        # reasonable inputs.
        broker_seed = args.seed + i
        series = synth(args.strategy, broker_seed, args.trades)
        xml_path = out / f"multibroker-{args.strategy}-{args.seed}-b{i+1}.xml"
        xml_path.write_text(series_to_report_xml(series, symbol=args.symbol, period=args.tf),
                            encoding="utf-8")
        paths.append(xml_path)
        log_path = out / f"multibroker-{args.strategy}-{args.seed}-b{i+1}.log"
        log_path.write_text(series_to_journal(series), encoding="utf-8")
        paths.append(log_path)
    return paths


_EMITTERS = {
    "backtest":    emit_backtest,
    "walkforward": emit_walkforward,
    "monte-carlo": emit_monte_carlo,
    "multibroker": emit_multibroker,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-fixture", description=__doc__.splitlines()[0])
    p.add_argument("--type", required=True, choices=tuple(_EMITTERS),
                   help="Which gate's input to synthesise.")
    p.add_argument("--strategy", required=True, choices=("random", "trend", "mean-rev"),
                   help="Synthesis flavour. `trend` is the happy-path; `random` "
                        "is the negative-test path.")
    p.add_argument("--seed", type=int, default=42,
                   help="Deterministic seed (default 42).")
    p.add_argument("--trades", type=int, default=200,
                   help="Number of synthetic trades (default 200).")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--tf", default="H1")
    p.add_argument("--brokers", type=int, default=3,
                   help="Multi-broker only: number of broker XML reports to emit.")
    p.add_argument("--out", type=Path, default=Path("."),
                   help="Output directory. Created if missing.")
    _agent_io.add_json_flag(p)
    args = p.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    paths = _EMITTERS[args.type](args, args.out)

    envelope = _agent_io.Envelope(
        tool="mql5-fixture",
        ok=True,
        exit_code=0,
        summary=f"emitted {len(paths)} fixture(s) for type={args.type} strategy={args.strategy}",
        data={
            "type": args.type,
            "strategy": args.strategy,
            "seed": args.seed,
            "files": [str(p) for p in paths],
        },
        evidence=[str(p) for p in paths],
    )

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        for p in paths:
            print(str(p))

    return 0


if __name__ == "__main__":
    sys.exit(main())
