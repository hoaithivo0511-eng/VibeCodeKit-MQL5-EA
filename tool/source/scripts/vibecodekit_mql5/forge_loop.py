"""mql5-forge-loop — hermetic forge iteration loop.

Closes the chat-driven build / verify loop on Linux *without* Wine: for
``N`` iterations, the loop synthesises a fresh MetaTester XML via
:mod:`vibecodekit_mql5.fixture` (the hermetic fixture
generator) and immediately parses it with
:mod:`vibecodekit_mql5.backtest.parse_xml_report_file`. The resulting
metrics + a stability summary are emitted to disk and stdout as a
``--json`` envelope so the rest of the kit (matrix collector,
dashboard, gate reports) consumes them unchanged.

Why this exists:

* Pre-, the operator had two choices when iterating on an EA:
  (a) install Wine + MetaTester locally, or (b) hand-craft an XML.
  ``mql5-fixture`` made (b) painless for one report; this loop makes
  it painless for ``N``.
* The synthetic XML format is the *same* format MetaTester emits, so
  any downstream consumer (RRI-BT, walkforward, multibroker, monte-
  carlo) keeps working unchanged.

Forbidden by design:

* This CLI does NOT compile an EA, does NOT call Wine, does NOT call
  MetaTester. It is a deterministic, seed-driven loop over
  :mod:`vibecodekit_mql5.fixture` + :mod:`vibecodekit_mql5.backtest`.
  For real broker-side backtests, ``mql5-auto-build`` + ``mql5-backtest``
  remains the canonical path.

CLI::

    mql5-forge-loop --iterations 3 --strategy trend --base-seed 100
                    --symbol EURUSD --tf H1 --out ./forge-run

Exit codes:

* 0 — every iteration produced a parseable BacktestResult.
* 1 — at least one iteration's metric crossed a `--fail-below` threshold
       (only when the gate is enabled).
* 2 — invocation error (bad CLI args, output dir not writable).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import _agent_io
from . import fixture as fixture_mod
from .backtest import parse_xml_report_file


# ---------------------------------------------------------------------------
# Iteration plumbing
# ---------------------------------------------------------------------------

@dataclass
class IterationResult:
    iteration: int
    seed: int
    xml_path: str
    profit_factor: float
    sharpe: float
    max_dd_pct: float
    total_trades: int
    profitable_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LoopReport:
    strategy: str
    symbol: str
    tf: str
    base_seed: int
    iterations: list[IterationResult] = field(default_factory=list)
    threshold_violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.threshold_violations

    def summary(self) -> dict[str, Any]:
        if not self.iterations:
            return {"iterations": 0, "ok": False, "note": "no iterations ran"}
        pf = [it.profit_factor for it in self.iterations]
        sh = [it.sharpe for it in self.iterations]
        dd = [it.max_dd_pct for it in self.iterations]
        return {
            "iterations": len(self.iterations),
            "pf_mean": statistics.mean(pf),
            "pf_stdev": statistics.pstdev(pf),
            "sharpe_mean": statistics.mean(sh),
            "max_dd_pct_worst": max(dd),
            "ok": self.ok,
            "threshold_violations": list(self.threshold_violations),
        }


def _build_namespace_for_fixture(
    strategy: str, seed: int, symbol: str, tf: str, trades: int, out: Path,
) -> argparse.Namespace:
    """Synthesise the argparse-style payload that
    :func:`vibecodekit_mql5.fixture.emit_backtest` expects.

    The fixture emitter accepts a Namespace from its own argparse, so we
    fake one here to avoid spawning a subprocess.
    """
    return argparse.Namespace(
        type="backtest",
        strategy=strategy,
        seed=seed,
        trades=trades,
        symbol=symbol,
        tf=tf,
        brokers=1,           # unused by emit_backtest
        out=out,
    )


def run_iteration(
    iteration: int, base_seed: int, strategy: str, symbol: str,
    tf: str, trades: int, out: Path,
) -> IterationResult:
    """Run one forge iteration: synthesise XML → parse → return metrics."""

    seed = base_seed + iteration
    ns = _build_namespace_for_fixture(strategy, seed, symbol, tf, trades, out)
    paths = fixture_mod.emit_backtest(ns, out)

    # emit_backtest writes the XML first, returns CSV second.
    xml_path = next((p for p in paths if p.suffix == ".xml"), None)
    if xml_path is None:
        raise RuntimeError(
            f"forge-loop iteration {iteration}: emit_backtest produced no XML"
        )

    result = parse_xml_report_file(xml_path)
    return IterationResult(
        iteration=iteration,
        seed=seed,
        xml_path=str(xml_path),
        profit_factor=result.profit_factor,
        sharpe=result.sharpe,
        max_dd_pct=result.max_drawdown_pct,
        total_trades=result.total_trades,
        profitable_pct=result.profitable_pct,
    )


def run_loop(
    *, iterations: int, base_seed: int, strategy: str, symbol: str,
    tf: str, trades: int, out: Path,
    pf_floor: float | None = None,
    sharpe_floor: float | None = None,
    max_dd_ceiling: float | None = None,
) -> LoopReport:
    """Run ``iterations`` forge iterations and aggregate the report."""

    out.mkdir(parents=True, exist_ok=True)
    report = LoopReport(
        strategy=strategy, symbol=symbol, tf=tf, base_seed=base_seed,
    )

    for i in range(iterations):
        it = run_iteration(
            iteration=i, base_seed=base_seed, strategy=strategy,
            symbol=symbol, tf=tf, trades=trades, out=out,
        )
        report.iterations.append(it)

        if pf_floor is not None and it.profit_factor < pf_floor:
            report.threshold_violations.append(
                f"iter {i}: profit_factor={it.profit_factor:.3f} < floor {pf_floor:.3f}"
            )
        if sharpe_floor is not None and it.sharpe < sharpe_floor:
            report.threshold_violations.append(
                f"iter {i}: sharpe={it.sharpe:.3f} < floor {sharpe_floor:.3f}"
            )
        if max_dd_ceiling is not None and it.max_dd_pct > max_dd_ceiling:
            report.threshold_violations.append(
                f"iter {i}: max_dd_pct={it.max_dd_pct:.3f} > ceiling {max_dd_ceiling:.3f}"
            )

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mql5-forge-loop",
        description=__doc__.splitlines()[0],
    )
    parser.add_argument(
        "--iterations", type=int, default=3,
        help="Number of synthetic backtest reports to emit + parse (≥1).",
    )
    parser.add_argument(
        "--strategy", choices=("random", "trend", "mean-rev"),
        default="trend",
        help="Fixture flavour; same as mql5-fixture --strategy.",
    )
    parser.add_argument(
        "--base-seed", type=int, default=100,
        help="Iteration N uses seed = base_seed + N (deterministic).",
    )
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--tf", default="H1")
    parser.add_argument(
        "--trades", type=int, default=200,
        help="Synthetic trades per iteration (passed to mql5-fixture).",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("forge-run"),
        help="Output directory; XML + JSON report are written here.",
    )
    parser.add_argument(
        "--pf-floor", type=float, default=None,
        help="Fail the loop if any iter's profit_factor drops below this.",
    )
    parser.add_argument(
        "--sharpe-floor", type=float, default=None,
        help="Fail the loop if any iter's sharpe drops below this.",
    )
    parser.add_argument(
        "--max-dd-ceiling", type=float, default=None,
        help="Fail the loop if any iter's max_drawdown_pct exceeds this.",
    )
    _agent_io.add_json_flag(parser)
    _agent_io.add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    if args.iterations < 1:
        print("mql5-forge-loop: --iterations must be ≥ 1", file=sys.stderr)
        return 2

    try:
        report = run_loop(
            iterations=args.iterations,
            base_seed=args.base_seed,
            strategy=args.strategy,
            symbol=args.symbol,
            tf=args.tf,
            trades=args.trades,
            out=args.out,
            pf_floor=args.pf_floor,
            sharpe_floor=args.sharpe_floor,
            max_dd_ceiling=args.max_dd_ceiling,
        )
    except (OSError, RuntimeError) as exc:
        print(f"mql5-forge-loop: {exc}", file=sys.stderr)
        return 2

    summary = report.summary()
    json_report_path = args.out / "forge-loop-report.json"
    json_report_path.write_text(
        json.dumps({
            "strategy": report.strategy,
            "symbol": report.symbol,
            "tf": report.tf,
            "base_seed": report.base_seed,
            "iterations": [it.to_dict() for it in report.iterations],
            "summary": summary,
        }, indent=2),
        encoding="utf-8",
    )

    envelope = _agent_io.Envelope(
        tool="mql5-forge-loop",
        ok=report.ok,
        exit_code=0 if report.ok else 1,
        summary=(
            f"{summary.get('iterations', 0)} iter(s); "
            f"pf_mean={summary.get('pf_mean', float('nan')):.3f}; "
            f"violations={len(report.threshold_violations)}"
        ),
        data={
            "strategy": report.strategy,
            "symbol": report.symbol,
            "tf": report.tf,
            "base_seed": report.base_seed,
            "iterations": [it.to_dict() for it in report.iterations],
            "summary": summary,
            "report_path": str(json_report_path),
        },
        evidence=[str(it.xml_path) for it in report.iterations],
        matrix_dim="d_robustness",
        matrix_axis="backtest",
        matrix_status="PASS" if report.ok else "FAIL",
    )

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        print(json.dumps(envelope.to_dict(), indent=2))

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
