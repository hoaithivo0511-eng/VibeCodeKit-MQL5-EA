"""mql5-wizard — render the wizard-composable scaffold.

A thin wrapper around the core :mod:`vibecodekit_mql5.build` that targets
the ``wizard-composable/netting`` scaffold.  The wizard-composable archetype
is the MQL5 Wizard-style CExpert + signal + trailing + money-mgmt stack
(see ``docs/references/60-wizard-cexpert.md``).

Usage::

    python -m vibecodekit_mql5.wizard --name MyWizardEA \\\\
        --symbol EURUSD --tf H1 --output ./out
"""

from __future__ import annotations

import argparse
import sys

try:
    from . import build as build_mod  # type: ignore
except ImportError:
    import vibecodekit_mql5.build as build_mod  # type: ignore


WIZARD_STACK = "wizard-composable"
WIZARD_VARIANT = "netting"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-wizard")
    parser.add_argument("--name", required=True, help="EA name")
    parser.add_argument("--symbol", required=True, help="Trading symbol")
    parser.add_argument("--tf", default="H1", help="Timeframe (default H1)")
    parser.add_argument("--output", default=".", help="Output directory")
    args = parser.parse_args(argv)

    inner_argv = [
        WIZARD_STACK,
        "--name", args.name,
        "--symbol", args.symbol,
        "--tf", args.tf,
        "--stack", WIZARD_VARIANT,
        "--out", args.output,
    ]
    return build_mod.main(inner_argv)


if __name__ == "__main__":
    sys.exit(main())
