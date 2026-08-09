"""mql5-bt-sim — Python tick-bar simulator (in-process).

A deterministic, dependency-free backtest engine that:

1. Generates synthetic OHLC bars under a seed-controlled random walk.
2. Runs a built-in strategy (SMA-cross / mean-rev / breakout) and
   tracks per-trade PnL on those bars.
3. Emits an XML report in the **same schema** as MetaTrader 5's
   Strategy Tester output (``<TesterReport><Statistics>…</Statistics></TesterReport>``)
   so the existing :mod:`vibecodekit_mql5.backtest` parser accepts the
   file unchanged — closing the "loop breaks if you don't have Wine"
   gap the review called out, this time with actual strategy
   simulation rather than canned-return synthesis (``mql5-fixture``).

Three built-in strategies:

    --strategy sma-cross   fast/slow SMA crossover (long-only).
                           Edge present under trending drift; degrades
                           under mean-reverting bars.
    --strategy mean-rev    Bollinger-band style: enter long when
                           price < SMA - k*sigma, exit at SMA. Edge
                           present under mean-reverting bars.
    --strategy breakout    Donchian-channel: enter long on N-bar high
                           breakout, exit at N-bar low. Edge under
                           strong trend.

The synthesised bars are deterministic for a given ``--seed`` so the
emitted XML hash is reproducible across runs and CI machines. The
chain ``mql5-bt-sim → mql5-backtest`` replaces ``mql5-fixture --type
backtest → mql5-backtest`` whenever the agent wants a strategy with
real entry / exit logic in the loop instead of raw return synthesis.

CLI examples::

    # Trend-up bars + SMA-cross, 500 bars, seed 42:
    mql5-bt-sim --strategy sma-cross --bars 500 --seed 42 \\
                --out tester.xml --returns-csv returns.csv

    # Chain into the existing XML parser unchanged:
    mql5-backtest --report tester.xml --json
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from . import _agent_io
from .fixture import Series, series_to_report_xml


# ─────────────────────────────────────────────────────────────────────────────
# Bar synthesis
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Bar:
    """A single OHLC bar. Volume omitted — not needed by the XML schema."""

    open: float
    high: float
    low: float
    close: float


def _synth_bars(
    strategy: str, seed: int, n_bars: int, start_price: float = 1.10000
) -> list[Bar]:
    """Generate ``n_bars`` synthetic OHLC bars under a random walk.

    ``strategy`` only affects the drift / autocorrelation knobs — the
    strategy LOGIC runs separately in :func:`run_strategy`. We pick
    bar-generation parameters that give each strategy a fair chance
    of detecting an edge (e.g. drift > 0 for ``sma-cross`` and
    ``breakout``, AR(1) coefficient -0.5 for ``mean-rev``).
    """

    rng = random.Random(seed)
    bars: list[Bar] = []
    price = start_price
    drift = 0.0
    ar_coef = 0.0
    sigma = 0.0008

    if strategy == "sma-cross":
        drift = 0.00012
    elif strategy == "breakout":
        drift = 0.00010
    elif strategy == "mean-rev":
        ar_coef = -0.5
    # else: random / unknown → zero drift, zero autocorrelation.

    prev_delta = 0.0
    for _ in range(n_bars):
        noise = rng.gauss(0.0, sigma)
        delta = drift + ar_coef * prev_delta + noise
        prev_delta = delta
        o = price
        c = o + delta
        wick = abs(rng.gauss(0.0, sigma * 0.4))
        h = max(o, c) + wick
        lo = min(o, c) - wick
        bars.append(Bar(open=o, high=h, low=lo, close=c))
        price = c
    return bars


def _sma(values: list[float], period: int, end_idx: int) -> float | None:
    """Simple moving average of ``values[end_idx - period + 1 : end_idx + 1]``."""
    if end_idx + 1 < period:
        return None
    window = values[end_idx - period + 1 : end_idx + 1]
    return sum(window) / period


def _stdev(values: list[float], period: int, end_idx: int) -> float | None:
    if end_idx + 1 < period:
        return None
    window = values[end_idx - period + 1 : end_idx + 1]
    mean = sum(window) / period
    var = sum((v - mean) ** 2 for v in window) / period
    return var ** 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Strategy logic — long-only for POC simplicity
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Trade:
    """A closed long-only trade. ``ret_pips`` is the per-trade PnL in
    pips (one pip = 0.0001 for 5-digit FX) so the XML report's PF /
    Sharpe / MaxDD numbers stay in a familiar range.
    """

    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    ret_pips: float


def run_strategy(
    strategy: str, bars: list[Bar], *, fast: int = 5, slow: int = 20, k: float = 2.0
) -> list[Trade]:
    """Run a built-in long-only strategy on ``bars``.

    Returns the closed trades in chronological order. Open positions
    at the end of the series are force-closed at the last bar so the
    PnL accounting is complete (no dangling exposure leaking into the
    metrics).
    """

    closes = [b.close for b in bars]
    trades: list[Trade] = []
    pos_entry_idx: int | None = None
    pos_entry_price: float = 0.0

    for i, bar in enumerate(bars):
        in_pos = pos_entry_idx is not None
        signal_long = False
        signal_exit = False

        if strategy == "sma-cross":
            fast_now = _sma(closes, fast, i)
            slow_now = _sma(closes, slow, i)
            fast_prev = _sma(closes, fast, i - 1) if i > 0 else None
            slow_prev = _sma(closes, slow, i - 1) if i > 0 else None
            if (
                fast_now is not None
                and slow_now is not None
                and fast_prev is not None
                and slow_prev is not None
            ):
                cross_up = fast_prev <= slow_prev and fast_now > slow_now
                cross_dn = fast_prev >= slow_prev and fast_now < slow_now
                signal_long = cross_up
                signal_exit = cross_dn
        elif strategy == "mean-rev":
            sma = _sma(closes, slow, i)
            sd = _stdev(closes, slow, i)
            if sma is not None and sd is not None and sd > 0:
                lower = sma - k * sd
                if not in_pos and bar.close < lower:
                    signal_long = True
                elif in_pos and bar.close >= sma:
                    signal_exit = True
        elif strategy == "breakout":
            if i >= slow:
                window_high = max(closes[i - slow : i])
                window_low = min(closes[i - slow : i])
                if not in_pos and bar.close > window_high:
                    signal_long = True
                elif in_pos and bar.close < window_low:
                    signal_exit = True
        else:
            # ``random`` falls back to the dumb-baseline: enter on
            # i%3==1 bars, exit on i%3==0 bars. Provides a non-degenerate
            # series for tests against zero-edge fixtures.
            if not in_pos and i % 3 == 1:
                signal_long = True
            elif in_pos and i % 3 == 0:
                signal_exit = True

        if not in_pos and signal_long:
            pos_entry_idx = i
            pos_entry_price = bar.close
        elif in_pos and (signal_exit or i == len(bars) - 1):
            ret_pips = (bar.close - pos_entry_price) * 10_000
            trades.append(
                Trade(
                    entry_bar=pos_entry_idx if pos_entry_idx is not None else i,
                    exit_bar=i,
                    entry_price=pos_entry_price,
                    exit_price=bar.close,
                    ret_pips=round(ret_pips, 2),
                )
            )
            pos_entry_idx = None
            pos_entry_price = 0.0

    return trades


def trades_to_series(trades: list[Trade], strategy_label: str) -> Series:
    """Convert simulated trades into the :class:`fixture.Series` shape
    so we can re-use ``series_to_report_xml`` for emission.
    """

    return Series(returns=[t.ret_pips for t in trades], label=strategy_label)


# ─────────────────────────────────────────────────────────────────────────────
# Public façade — used by tests + the CLI below
# ─────────────────────────────────────────────────────────────────────────────

def simulate(
    *,
    strategy: str,
    seed: int,
    bars: int,
    symbol: str = "EURUSD",
    period: str = "H1",
    from_date: str = "2023.01.01",
    to_date: str = "2024.12.31",
    fast: int = 5,
    slow: int = 20,
    k: float = 2.0,
) -> tuple[Series, list[Trade], str]:
    """End-to-end simulation: bars → trades → ``(Series, trades, xml)``.

    Deterministic for a given ``(strategy, seed, bars)``.
    """

    bar_data = _synth_bars(strategy, seed, bars)
    trade_list = run_strategy(strategy, bar_data, fast=fast, slow=slow, k=k)
    series = trades_to_series(trade_list, strategy)
    xml = series_to_report_xml(
        series, symbol=symbol, period=period, from_date=from_date, to_date=to_date
    )
    return series, trade_list, xml


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-bt-sim", description=__doc__.splitlines()[0])
    p.add_argument("--strategy",
                   choices=("sma-cross", "mean-rev", "breakout", "random"),
                   required=True,
                   help="Strategy to simulate.")
    p.add_argument("--bars", type=int, default=500,
                   help="Number of synthetic OHLC bars to generate (default: 500).")
    p.add_argument("--seed", type=int, default=42,
                   help="Seed for deterministic bar synthesis + strategy "
                        "tie-breaking (default: 42).")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--tf", default="H1",
                   help="MT5-style timeframe label (M5, H1, D1, …). "
                        "Used only in the emitted XML's <Period> tag.")
    p.add_argument("--from-date", default="2023.01.01")
    p.add_argument("--to-date", default="2024.12.31")
    p.add_argument("--fast", type=int, default=5,
                   help="SMA-cross fast period.")
    p.add_argument("--slow", type=int, default=20,
                   help="SMA-cross slow / mean-rev lookback / breakout lookback.")
    p.add_argument("--k", type=float, default=2.0,
                   help="Mean-rev band width in sigma (default: 2.0).")
    p.add_argument("--out", default="bt-sim.xml",
                   help="Path to write the MT5-compatible XML report.")
    p.add_argument("--returns-csv", default=None,
                   help="Optional path to also dump per-trade returns CSV.")
    _agent_io.add_json_flag(p)
    _agent_io.add_gate_report_flag(p)
    args = p.parse_args(argv)

    series, trades, xml = simulate(
        strategy=args.strategy,
        seed=args.seed,
        bars=args.bars,
        symbol=args.symbol,
        period=args.tf,
        from_date=args.from_date,
        to_date=args.to_date,
        fast=args.fast,
        slow=args.slow,
        k=args.k,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(xml, encoding="utf-8")

    csv_path: Path | None = None
    if args.returns_csv is not None:
        from .fixture import series_to_returns_csv
        csv_path = Path(args.returns_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(series_to_returns_csv(series), encoding="utf-8")

    pf = series.profit_factor
    sharpe = series.sharpe
    n_trades = series.total_trades
    summary = (
        f"{args.strategy}: {n_trades} trade(s), "
        f"PF={pf:.2f}, Sharpe={sharpe:.3f}, "
        f"MaxDD%={series.max_drawdown_pct:.2f}"
    )

    evidence = [str(out_path)]
    if csv_path is not None:
        evidence.append(str(csv_path))

    envelope = _agent_io.Envelope(
        tool="mql5-bt-sim",
        ok=True,
        exit_code=0,
        summary=summary,
        data={
            "strategy": args.strategy,
            "seed": args.seed,
            "bars": args.bars,
            "symbol": args.symbol,
            "period": args.tf,
            "trade_count": n_trades,
            "profit_factor": round(pf, 4),
            "sharpe": round(sharpe, 4),
            "max_drawdown_pct": series.max_drawdown_pct,
            "profitable_pct": round(series.profitable_pct, 2),
            "xml_path": str(out_path),
            "returns_csv": str(csv_path) if csv_path is not None else None,
        },
        evidence=evidence,
        matrix_dim="d_correctness",
        matrix_axis="implement",
        matrix_status="PASS",
    )

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        print(summary)
        print(f"wrote {out_path}")
        if csv_path is not None:
            print(f"wrote {csv_path}")

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return envelope.exit_code


if __name__ == "__main__":
    sys.exit(main())
