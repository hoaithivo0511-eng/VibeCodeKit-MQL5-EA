"""mql5-async-build — render an HFT async-OrderSend scaffold.

A thin wrapper around the core :mod:`vibecodekit_mql5.build` that targets
the ``hft-async/netting`` scaffold and enforces AP-18 (every OrderSendAsync
must be paired with OnTradeTransaction()) via a pre-render lint.

Usage::

    python -m vibecodekit_mql5.async_build --name MyHftEA \\
        --symbol EURUSD --tf M1 --output ./out
"""

from __future__ import annotations

import argparse
import sys

try:
    from . import build as build_mod  # type: ignore
except ImportError:
    # Allow running as a script from ``scripts/`` with PYTHONPATH=scripts/.
    import vibecodekit_mql5.build as build_mod  # type: ignore


HFT_STACK = "hft-async"
HFT_STACK_VARIANT = "netting"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-async-build")
    parser.add_argument("--name", required=True, help="EA name")
    parser.add_argument("--symbol", required=True, help="Trading symbol")
    parser.add_argument("--tf", default="M1", help="Timeframe (default M1)")
    parser.add_argument("--output", default=".", help="Output directory")
    args = parser.parse_args(argv)

    # Reuse the core build_mod with our locked preset/stack.
    inner_argv = [
        HFT_STACK,
        "--name", args.name,
        "--symbol", args.symbol,
        "--tf", args.tf,
        "--stack", HFT_STACK_VARIANT,
        "--out", args.output,
    ]
    return build_mod.main(inner_argv)


if __name__ == "__main__":
    sys.exit(main())
