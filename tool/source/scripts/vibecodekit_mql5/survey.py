"""/mql5-survey — map a strategy description to a scaffold archetype.

Heuristic-only: matches a short free-text strategy
description against the kit's 11 scaffold archetypes and returns the
closest match plus the runner-up.  Used by ``/mql5-build`` as a
suggestion engine, not a hard router.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass

# (archetype, keyword regex)
ARCHETYPES = [
    ("trend",            r"\b(trend|ma cross|moving average|breakout pullback|sar)\b"),
    ("mean-reversion",   r"\b(mean[-\s]?revers|bollinger|z[-\s]?score|rsi)\b"),
    ("breakout",         r"\b(breakout|donchian|range break|orb)\b"),
    ("hedging-multi",    r"\b(hedge|hedging|long[-\s]?short|pair)\b"),
    ("news-trading",     r"\b(news|nfp|fomc|cpi|event[-\s]?driven)\b"),
    ("arbitrage-stat",   r"\b(arbitrage|stat[-\s]?arb|cointegration|spread trade)\b"),
    ("scalping",         r"\b(scalp|tick|low[-\s]?latency)\b"),
    ("library",          r"\b(library|stdlib only|reusable)\b"),
    ("indicator-only",   r"\b(indicator only|signal indicator|alert indicator)\b"),
    ("grid",             r"\b(grid|martingale)\b"),
    ("dca",              r"\b(dca|dollar[-\s]?cost|averaging)\b"),
]


@dataclass
class SurveyReport:
    description: str
    matches: list[tuple[str, int]]
    primary: str
    runner_up: str


def survey(description: str) -> SurveyReport:
    desc = description.lower()
    scored: list[tuple[str, int]] = []
    for archetype, pattern in ARCHETYPES:
        hits = len(re.findall(pattern, desc))
        scored.append((archetype, hits))
    scored.sort(key=lambda x: (-x[1], x[0]))
    primary = scored[0][0] if scored and scored[0][1] > 0 else "trend"
    runner_up = scored[1][0] if len(scored) > 1 else ""
    return SurveyReport(description, scored, primary, runner_up)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-survey")
    parser.add_argument("description", help="Free-text strategy description")
    args = parser.parse_args(argv)
    rep = survey(args.description)
    print(json.dumps({
        "description": rep.description,
        "primary": rep.primary,
        "runner_up": rep.runner_up,
        "matches": [{"archetype": a, "hits": h} for a, h in rep.matches],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
