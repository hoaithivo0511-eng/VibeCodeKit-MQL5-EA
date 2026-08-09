"""mql5-eng-review — alias for ``mql5-review --lens eng``.

Engineering review preset: ``broker-engineer`` + ``devops`` personas
biased toward the ``build`` and ``verify`` steps. Kept as a standalone
console script so existing scripts and CI pipelines keep working.
The actual rendering lives in :mod:`vibecodekit_mql5.review.review`;
this file is a 1-line forwarder so help, JSON envelope, and the lens
definition stay in one place.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .review import LENSES, run_lens


# Public for back-compat with the pre-imports
# (e.g. ``from vibecodekit_mql5.review.eng_review import PERSONAS``).
PERSONAS: tuple[str, ...] = LENSES["eng"].personas
DEFAULT_STEPS: tuple[str, ...] = LENSES["eng"].steps


def render(mode: str, steps: tuple[str, ...] = DEFAULT_STEPS) -> str:
    from .review import render_lens
    return render_lens(LENSES["eng"], mode, steps)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-eng-review")
    ap.add_argument(
        "--mode", choices=("personal", "team", "enterprise"), default="personal",
    )
    ap.add_argument(
        "--output", type=Path, default=None,
        help="Output markdown path (default: eng-review.md).",
    )
    args = ap.parse_args(argv)
    return run_lens("eng", args.mode, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
