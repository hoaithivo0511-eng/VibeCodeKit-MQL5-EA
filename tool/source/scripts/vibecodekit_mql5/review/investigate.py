"""mql5-investigate — alias for ``mql5-review --lens investigate``.

Open-ended investigation review: when a backtest, walkforward, or live
deployment misbehaves, this lens combines ``perf-analyst`` +
``strategy-architect`` with the ``scan`` + ``rri`` step templates and
appends a Hypotheses worksheet so the reviewer can record hypotheses
and the data each one needs. Body lives in
:mod:`vibecodekit_mql5.review.review`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .review import LENSES, run_lens


PERSONAS: tuple[str, ...] = LENSES["investigate"].personas
DEFAULT_STEPS: tuple[str, ...] = LENSES["investigate"].steps


def render(mode: str, steps: tuple[str, ...] = DEFAULT_STEPS) -> str:
    from .review import render_lens
    return render_lens(LENSES["investigate"], mode, steps)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-investigate")
    ap.add_argument(
        "--mode", choices=("personal", "team", "enterprise"), default="personal",
    )
    ap.add_argument(
        "--output", type=Path, default=None,
        help="Output markdown path (default: investigate.md).",
    )
    args = ap.parse_args(argv)
    return run_lens("investigate", args.mode, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
