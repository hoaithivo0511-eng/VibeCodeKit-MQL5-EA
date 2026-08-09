"""mql5-fitness — pick a tester fitness template from a labelled goal.

The MT5 Strategy Tester accepts custom optimization criteria; the kit spec §12
calls out templates that we expose under stable names:

    sharpe        — straightforward risk-adjusted return
    sortino       — Sharpe but downside-deviation only
    profit-dd     — Profit / MaxDD (recovery factor)
    expectancy    — average $ per trade
    composite     — multi-factor OnTester score (Korotky §6.5.6 BandOsMA)
    walkforward   — robustness Sharpe (single-pass surrogate)

Each template returns the *MQL5-friendly* expression string that should be
written to the tester's `OnTester()` function in the generated EA.

Walk-forward note
-----------------
`OnTester()` is invoked **once per tester pass** and only sees its own
period's statistics — there is no `STAT_SHARPE_RATIO_OOS` accessor on the
MQL5 side. A genuine "75% IS + 25% OOS" composite therefore cannot be
computed inside `OnTester()`. The kit produces that composite externally
via ``mql5-walkforward`` (see :mod:`vibecodekit_mql5.walkforward`), which
consumes the two separate XML reports MT5 emits when Forward 1/4 mode is
enabled.

The ``walkforward`` template below is a *single-pass robustness Sharpe* —
plain Sharpe gated on min-trade-count, drawdown, and profit positivity —
which is what an in-tester optimizer can reasonably score on its own.

Composite note
-------------------
The ``composite`` template implements the multi-factor custom criterion
described in Korotky §6.5.6 (the BandOsMA worked example): it rewards profit,
profit factor, trade-count significance and risk-adjusted return together so
the optimizer does not over-fit a single metric. It is sign-preserving so a
losing pass scores negative.

CLI:
    python -m vibecodekit_mql5.fitness <template>

Exit codes:
    0 — template printed (or list shown)
    2 — unknown template
"""
from __future__ import annotations

import argparse
import re
import sys

from .mq5_symbols import strip_comments_and_strings


TEMPLATES: dict[str, str] = {
    "sharpe": (
        "double profit = TesterStatistics(STAT_PROFIT);\n"
        "double trades = TesterStatistics(STAT_TRADES);\n"
        "double sharpe = TesterStatistics(STAT_SHARPE_RATIO);\n"
        "return (trades >= 30 && profit > 0) ? sharpe : 0.0;"
    ),
    "sortino": (
        "double dn = TesterStatistics(STAT_BALANCE_DDREL_PERCENT);\n"
        "double profit = TesterStatistics(STAT_PROFIT);\n"
        "if(profit <= 0 || dn <= 0) return 0.0;\n"
        "return profit / dn;"
    ),
    "profit-dd": (
        "double profit = TesterStatistics(STAT_PROFIT);\n"
        "double dd = TesterStatistics(STAT_BALANCEDD_PERCENT);\n"
        "return (dd > 0 && profit > 0) ? profit / dd : 0.0;"
    ),
    "expectancy": (
        "double ep = TesterStatistics(STAT_EXPECTED_PAYOFF);\n"
        "double trades = TesterStatistics(STAT_TRADES);\n"
        "return (trades >= 30 && ep > 0) ? ep : 0.0;"
    ),
    # multi-factor composite custom criterion (Korotky §6.5.6 BandOsMA
    # worked example). Combines profit, profit factor, trade-count
    # significance and risk-adjusted return into one sign-preserving score so
    # the optimizer can't over-fit a single statistic. A losing pass scores
    # negative; a too-thin pass (<30 trades) scores 0.
    "composite": (
        "double profit = TesterStatistics(STAT_PROFIT);\n"
        "double pf     = TesterStatistics(STAT_PROFIT_FACTOR);\n"
        "double trades = TesterStatistics(STAT_TRADES);\n"
        "double sharpe = TesterStatistics(STAT_SHARPE_RATIO);\n"
        "if(trades < 30) return 0.0;\n"
        "double sgn = (profit >= 0.0) ? 1.0 : -1.0;\n"
        "double score = sgn * MathSqrt(MathAbs(profit))\n"
        "             * MathSqrt(MathMax(pf, 0.0))\n"
        "             * MathSqrt(trades)\n"
        "             * MathSqrt(MathAbs(sharpe));\n"
        "return score;"
    ),
    # NOTE: OnTester() runs once per tester pass and only sees its own
    # period's stats — MQL5 has no STAT_SHARPE_RATIO_OOS. A true 75/25
    # IS/OOS composite is therefore computed externally by
    # `mql5-walkforward` against the two XML reports MT5 emits when
    # Forward 1/4 mode is on. This template is the in-tester surrogate:
    # plain Sharpe gated by min-trades + non-zero drawdown + positive PnL.
    "walkforward": (
        "double profit = TesterStatistics(STAT_PROFIT);\n"
        "double trades = TesterStatistics(STAT_TRADES);\n"
        "double sharpe = TesterStatistics(STAT_SHARPE_RATIO);\n"
        "double dd     = TesterStatistics(STAT_BALANCEDD_PERCENT);\n"
        "if(profit <= 0 || trades < 30 || dd <= 0 || sharpe <= 0) return 0.0;\n"
        "return sharpe;"
    ),
}


_ONTESTER = re.compile(r"\bdouble\s+OnTester\s*\(\s*\)", re.I)


def get(name: str) -> str:
    if name not in TEMPLATES:
        raise KeyError(name)
    return TEMPLATES[name]


def list_templates() -> list[str]:
    return sorted(TEMPLATES.keys())


def ea_has_ontester(text: str) -> bool:
    """True if the EA source defines a ``double OnTester()`` handler.

    Used by the composite-fitness advisory: an EA intended for optimization should expose a
    custom OnTester() criterion rather than relying on the tester's built-in
    single-metric maximisation. Comment/string-stripped so a mention in a
    docstring or string literal does not count as a real definition.
    """
    return bool(_ONTESTER.search(strip_comments_and_strings(text)))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-fitness", description=__doc__.splitlines()[0])
    p.add_argument("name", nargs="?", default=None,
                   help=f"One of: {', '.join(list_templates())} (omit to list)")
    args = p.parse_args(argv)

    if args.name is None:
        for k in list_templates():
            print(k)
        return 0
    try:
        print(get(args.name))
        return 0
    except KeyError:
        print(f"[fitness] unknown template: {args.name}", file=sys.stderr)
        print(f"  available: {', '.join(list_templates())}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
