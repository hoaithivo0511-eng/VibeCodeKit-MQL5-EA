"""mql5-ceo-review — alias for ``mql5-review --lens ceo``.

Executive review preset: ``trader`` + ``strategy-architect`` personas
biased toward the ``vision`` and ``refine`` steps. Frames the EA in
business / strategy terms (do we ship something the trader wants? does
the strategy edge exist?). Body lives in :mod:`vibecodekit_mql5.review.review`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .review import LENSES, run_lens


PERSONAS: tuple[str, ...] = LENSES["ceo"].personas
DEFAULT_STEPS: tuple[str, ...] = LENSES["ceo"].steps


def render(mode: str, steps: tuple[str, ...] = DEFAULT_STEPS) -> str:
    from .review import render_lens
    return render_lens(LENSES["ceo"], mode, steps)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-ceo-review")
    ap.add_argument(
        "--mode", choices=("personal", "team", "enterprise"), default="personal",
    )
    ap.add_argument(
        "--output", type=Path, default=None,
        help="Output markdown path (default: ceo-review.md).",
    )
    args = ap.parse_args(argv)
    return run_lens("ceo", args.mode, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
