"""mql5-optimize-run — drive the MetaTrader 5 Strategy Tester optimizer end-to-end.

This is the post-v1.0.1 sibling of ``mql5-tester-run``. Where the latter
drives a single ``Optimization=0`` backtest pass, this module renders a
``tester.ini`` with ``Optimization=1`` (slow / complete) or
``Optimization=2`` (genetic), launches ``terminal64.exe`` against it,
waits for the optimizer to finish, and parses the Microsoft Excel
SpreadsheetML XML report MT5 emits into a top-N parameter-combination
JSON.

Why this exists
---------------
The kit's existing ``mql5-cloud-optimize`` only **plans** an optimization
run — it emits a ``tester.ini`` and an estimated USD cost for Cloud
Network, but never invokes any binary. To actually sweep parameters on
a local Wine + MetaEditor stack the operator was still forced to open
MT5 by hand. ``optimize-run`` closes that gap. The Linux/Wine path is
the primary target: agents and CI bots can now hand a ``.set`` file with
``optimize=true`` flags + start/step/stop ranges to a single command and
get back the top-N parameter sets in JSON.

The driver does NOT:

* run a paid Cloud Network optimization (use ``mql5-cloud-optimize`` to
  cost-estimate and emit a cloud ``tester.ini`` instead);
* place or modify live orders;
* mutate the ``.set`` file (read-only input).

CLI
---
::

    mql5-optimize-run MyEA.ex5 default.set \\
        --symbol EURUSD --period 2024.01.01-2024.12.31 --tf H1 \\
        --mode genetic --criterion sharpe-max --top 10 \\
        [--report opt-results.xml] [--timeout 1800] \\
        [--terminal /path/to/terminal64.exe] [--wine] \\
        [--print-ini-only] [--from-xml fixture.xml]

Exit codes
----------
* 0 — optimization finished, XML parsed, JSON result printed to stdout.
* 1 — XML parsed but contained zero rows (optimizer produced no
  results), or fitness column is missing from every row.
* 2 — invocation error (bad ``--period``, mutually exclusive flags, …).
* 3 — terminal binary not found in any known location and ``--terminal``
  was not supplied.
* 4 — terminal launched but timed out without producing the XML report.
* 5 — XML report exists but does not parse (corrupt / truncated).

Hermetic testing
----------------
``--from-xml <path>`` skips the launch entirely and parses the supplied
XML as if the terminal had just written it. This is the path CI and
agent test suites use, since installing MT5 in a container is not
feasible. Round-trip tests cover render + parse symmetrically.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from vibecodekit_mql5.backtest import parse_period
from vibecodekit_mql5.optimize_run_xml import (
    OptResult,
    parse_opt_xml,
    parse_opt_xml_file,
)
from vibecodekit_mql5.tester_run import (
    TerminalLocation,
    build_command,
    find_terminal,
    wait_for_report,
)


__all__ = [
    "OPTIMIZATION_MODES",
    "OPTIMIZATION_CRITERIA",
    "DEFAULT_CRITERION",
    "OptResult",
    "OptimizeRunSpec",
    "main",
    "parse_opt_xml",
    "parse_opt_xml_file",
    "render_optimize_ini",
    "run",
    "top_n",
]


# ─────────────────────────────────────────────────────────────────────────────
# Optimization mode + criterion enums (Strategy Tester reference)
# ─────────────────────────────────────────────────────────────────────────────
#
# Source: docs.mql5.com — Tester section. The ``Optimization`` key in the
# tester.ini is a small int; the kit names them so the CLI can accept
# human-readable choices without leaking magic numbers.

OPTIMIZATION_MODES: dict[str, int] = {
    "off":                 0,
    "slow":                1,   # Slow complete algorithm
    "genetic":             2,   # Fast genetic algorithm
    "fast-1m":             3,   # Fast 1-min OHLC genetic
    "all-symbols-genetic": 4,   # Forward selection on all symbols
}

# The same enum lives in cloud_optimize.OPTIMIZATION_CRITERIA but with
# integer keys; here we keep a human-name → (int, xml-column) map so
# the CLI and the parser share the same vocabulary.
#
# ``xml_column`` is the SpreadsheetML header label MT5 writes for that
# criterion. ``Result`` is the universal column the optimizer always
# emits; for criterion=custom the value is whatever ``OnTester()`` in
# the EA returned.
OPTIMIZATION_CRITERIA: dict[str, dict[str, object]] = {
    "balance-max":        {"id": 0, "xml_column": "Profit"},
    "profit-factor-max":  {"id": 1, "xml_column": "Profit Factor"},
    "expected-payoff-max":{"id": 2, "xml_column": "Expected Payoff"},
    "drawdown-min":       {"id": 3, "xml_column": "Equity DD %"},
    "recovery-max":       {"id": 4, "xml_column": "Recovery Factor"},
    "sharpe-max":         {"id": 5, "xml_column": "Sharpe Ratio"},
    "custom-max":         {"id": 6, "xml_column": "Result"},
}
DEFAULT_CRITERION = "balance-max"

# Whether a criterion is maximised (False) or minimised (True). Used to
# decide sort direction when picking top-N.
_MINIMISE: frozenset[str] = frozenset({"drawdown-min"})


# ─────────────────────────────────────────────────────────────────────────────
# tester.ini generator
# ─────────────────────────────────────────────────────────────────────────────

def render_optimize_ini(
    *,
    ea_path: str,
    set_path: str,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    optimization_mode: int,
    optimization_criterion: int,
    forward_mode: int = 0,
    report_path: str = "opt-results.xml",
    deposit: int = 10000,
    leverage: int = 100,
) -> str:
    """Render a tester.ini configured for an optimizer pass.

    Differences from ``backtest.render_tester_ini``:

    * ``Optimization`` defaults to a non-zero mode (slow / genetic / …).
    * ``OptimizationCriterion`` selects which column MT5 sorts by.
    * ``Report`` should end with ``.xml`` — MT5 writes a SpreadsheetML
      workbook there with one row per parameter combination.
    """
    if optimization_mode not in OPTIMIZATION_MODES.values():
        raise ValueError(
            f"optimization_mode must be one of {sorted(OPTIMIZATION_MODES.values())}, "
            f"got {optimization_mode}",
        )
    valid_criteria = {c["id"] for c in OPTIMIZATION_CRITERIA.values()}
    if optimization_criterion not in valid_criteria:
        raise ValueError(
            f"optimization_criterion must be one of {sorted(valid_criteria)}, "
            f"got {optimization_criterion}",
        )
    return (
        "[Tester]\n"
        f"Expert={ea_path}\n"
        f"ExpertParameters={set_path}\n"
        f"Symbol={symbol}\n"
        f"Period={period}\n"
        f"FromDate={from_date}\n"
        f"ToDate={to_date}\n"
        f"ForwardMode={forward_mode}\n"
        f"Deposit={deposit}\n"
        "Currency=USD\n"
        f"Leverage=1:{leverage}\n"
        "Model=1\n"
        f"Optimization={optimization_mode}\n"
        f"OptimizationCriterion={optimization_criterion}\n"
        "ShutdownTerminal=1\n"
        f"Report={report_path}\n"
        "ReplaceReport=1\n"
    )


# The XML report parser (``OptResult`` dataclass, ``parse_opt_xml``,
# ``parse_opt_xml_file`` and friends) lives in
# :mod:`optimize_run_xml` so this module stays under the audit
# script's per-module LOC ceiling. Public symbols are re-exported via
# the top-of-file import so existing callers keep working unchanged.


# ─────────────────────────────────────────────────────────────────────────────
# top-N selection
# ─────────────────────────────────────────────────────────────────────────────

def top_n(
    results: Iterable[OptResult],
    fitness_column: str,
    n: int,
    *,
    minimise: bool = False,
) -> list[OptResult]:
    """Sort ``results`` by the given metric column and return the first N.

    Rows missing the requested metric are excluded — callers that want
    "any row, even un-fit" should pass ``fitness_column="Result"`` since
    MT5 always emits that.
    """
    if n <= 0:
        return []
    qualified = [r for r in results if fitness_column in r.metrics]
    qualified.sort(
        key=lambda r: r.metrics[fitness_column],
        reverse=not minimise,
    )
    return qualified[:n]


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class OptimizeRunSpec:
    __test__ = False
    ea_path: str
    set_path: str
    symbol: str
    period: str
    from_date: str
    to_date: str
    optimization_mode: int
    optimization_criterion: int
    report_path: str = "opt-results.xml"
    forward_mode: int = 0


def run(
    spec: OptimizeRunSpec,
    *,
    terminal: TerminalLocation,
    ini_path: Path,
    timeout_sec: float = 1800.0,
    subprocess_runner=None,
) -> list[OptResult]:
    """Render tester.ini, launch the terminal, wait, parse the opt XML."""
    ini_path.parent.mkdir(parents=True, exist_ok=True)
    ini_path.write_text(
        render_optimize_ini(
            ea_path=spec.ea_path,
            set_path=spec.set_path,
            symbol=spec.symbol,
            period=spec.period,
            from_date=spec.from_date,
            to_date=spec.to_date,
            optimization_mode=spec.optimization_mode,
            optimization_criterion=spec.optimization_criterion,
            forward_mode=spec.forward_mode,
            report_path=spec.report_path,
        ),
        encoding="utf-8",
    )

    cmd = build_command(terminal, ini_path)
    runner = subprocess_runner or subprocess.run
    try:
        runner(cmd, timeout=timeout_sec, check=False)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"terminal exceeded timeout={timeout_sec}s: {' '.join(cmd)}"
        ) from exc

    report = Path(spec.report_path)
    if not wait_for_report(report, timeout_sec=10.0):
        raise TimeoutError(
            f"terminal exited but report {report} was not produced "
            f"(check /portable data dir for the actual write location)"
        )

    return parse_opt_xml_file(report)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mql5-optimize-run",
        description=__doc__.splitlines()[0] if __doc__ else None,
    )
    p.add_argument("ea", help="EA path or name (interpreted by MT5)")
    p.add_argument("set_file", help="EA input set file (.set) with optimize=true flags")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument(
        "--period", required=True,
        help="YYYY.MM.DD-YYYY.MM.DD (FromDate-ToDate)",
    )
    p.add_argument("--tf", default="H1", help="MT5 timeframe enum, e.g. H1")
    p.add_argument(
        "--mode", default="genetic", choices=sorted(OPTIMIZATION_MODES),
        help="optimization algorithm (default: genetic)",
    )
    p.add_argument(
        "--criterion", default=DEFAULT_CRITERION,
        choices=sorted(OPTIMIZATION_CRITERIA),
        help=f"fitness column the optimizer sorts by (default: {DEFAULT_CRITERION})",
    )
    p.add_argument(
        "--forward-mode", type=int, default=0, choices=[0, 1, 2, 3, 4],
        help="forward-test split (0=off, 1=1/2, 2=1/3, 3=1/4, 4=custom)",
    )
    p.add_argument(
        "--top", type=int, default=10,
        help="how many of the best parameter combinations to keep (default: 10)",
    )
    p.add_argument(
        "--report", default="opt-results.xml",
        help="Report=<path> in tester.ini (relative to terminal data dir)",
    )
    p.add_argument(
        "--ini-out", default="optimize.ini",
        help="where to write the rendered tester.ini",
    )
    p.add_argument(
        "--timeout", type=float, default=1800.0,
        help="upper bound on terminal run, seconds (default: 30 min)",
    )
    p.add_argument(
        "--terminal", default=None,
        help="absolute path to terminal64.exe (override probe)",
    )
    p.add_argument("--wine", action="store_true",
                   help="force Wine wrapping even on non-Linux hosts")
    p.add_argument("--no-wine", action="store_true",
                   help="force native launch even on Linux")
    p.add_argument(
        "--print-ini-only", action="store_true",
        help="render tester.ini and exit (no terminal launch)",
    )
    p.add_argument(
        "--from-xml", default=None,
        help="parse this XML report instead of launching MT5 (hermetic test path)",
    )
    args = p.parse_args(argv)

    try:
        from_date, to_date = parse_period(args.period)
    except ValueError as exc:
        print(f"[optimize-run] {exc}", file=sys.stderr)
        return 2

    mode_id = OPTIMIZATION_MODES[args.mode]
    if mode_id == OPTIMIZATION_MODES["off"]:
        print(
            "[optimize-run] --mode off would produce a single backtest; "
            "use mql5-tester-run instead",
            file=sys.stderr,
        )
        return 2
    criterion_meta = OPTIMIZATION_CRITERIA[args.criterion]
    criterion_id = int(criterion_meta["id"])
    fitness_column = str(criterion_meta["xml_column"])
    minimise = args.criterion in _MINIMISE

    spec = OptimizeRunSpec(
        ea_path=args.ea,
        set_path=args.set_file,
        symbol=args.symbol,
        period=args.tf,
        from_date=from_date,
        to_date=to_date,
        optimization_mode=mode_id,
        optimization_criterion=criterion_id,
        report_path=args.report,
        forward_mode=args.forward_mode,
    )

    if args.print_ini_only:
        print(render_optimize_ini(
            ea_path=spec.ea_path,
            set_path=spec.set_path,
            symbol=spec.symbol,
            period=spec.period,
            from_date=spec.from_date,
            to_date=spec.to_date,
            optimization_mode=spec.optimization_mode,
            optimization_criterion=spec.optimization_criterion,
            forward_mode=spec.forward_mode,
            report_path=spec.report_path,
        ), end="")
        return 0

    if args.from_xml:
        try:
            results = parse_opt_xml_file(Path(args.from_xml))
        except (FileNotFoundError, ET.ParseError) as exc:
            print(f"[optimize-run] XML parse failed: {exc}", file=sys.stderr)
            return 5
    else:
        if args.wine and args.no_wine:
            print(
                "[optimize-run] --wine and --no-wine are mutually exclusive",
                file=sys.stderr,
            )
            return 2
        use_wine: bool | None
        if args.wine:
            use_wine = True
        elif args.no_wine:
            use_wine = False
        else:
            use_wine = None

        try:
            terminal = find_terminal(args.terminal, use_wine=use_wine)
        except FileNotFoundError as exc:
            print(f"[optimize-run] {exc}", file=sys.stderr)
            return 3

        try:
            results = run(
                spec,
                terminal=terminal,
                ini_path=Path(args.ini_out),
                timeout_sec=args.timeout,
            )
        except TimeoutError as exc:
            print(f"[optimize-run] {exc}", file=sys.stderr)
            return 4
        except ET.ParseError as exc:
            print(f"[optimize-run] XML parse failed: {exc}", file=sys.stderr)
            return 5

    if not results:
        print(
            json.dumps({
                "ok": False,
                "error": "optimizer produced zero rows",
                "fitness_column": fitness_column,
                "minimise": minimise,
                "total_passes": 0,
                "top": [],
            }, indent=2),
        )
        return 1

    selected = top_n(results, fitness_column, args.top, minimise=minimise)
    if not selected:
        print(
            json.dumps({
                "ok": False,
                "error": (
                    f"fitness column {fitness_column!r} missing from every row "
                    "(criterion choice does not match the XML columns)"
                ),
                "fitness_column": fitness_column,
                "minimise": minimise,
                "total_passes": len(results),
                "top": [],
            }, indent=2),
        )
        return 1

    payload = {
        "ok": True,
        "fitness_column": fitness_column,
        "minimise": minimise,
        "total_passes": len(results),
        "top": [r.to_dict() for r in selected],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
