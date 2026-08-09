"""mql5-cso — alias for ``mql5-review --lens cso``.

Chief Safety Officer review preset: single-persona drill on the risk
envelope (``risk-auditor``) biased toward ``rri`` + ``verify`` steps.
Useful for compliance sign-off before live deployment. Body lives in
:mod:`vibecodekit_mql5.review.review`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .review import LENSES, run_lens


PERSONA: str = LENSES["cso"].personas[0]
DEFAULT_STEPS: tuple[str, ...] = LENSES["cso"].steps


def render(mode: str, steps: tuple[str, ...] = DEFAULT_STEPS) -> str:
    from .review import render_lens
    return render_lens(LENSES["cso"], mode, steps)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-cso")
    ap.add_argument(
        "--mode", choices=("personal", "team", "enterprise"), default="personal",
    )
    ap.add_argument(
        "--output", type=Path, default=None,
        help="Output markdown path (default: cso-review.md).",
    )
    args = ap.parse_args(argv)
    return run_lens("cso", args.mode, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
