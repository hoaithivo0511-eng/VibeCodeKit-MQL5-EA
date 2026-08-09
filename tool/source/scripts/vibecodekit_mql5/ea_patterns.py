"""mql5-ea-patterns -- safety-first EA strategy pattern bank.

The v2.x review flagged the SCAN/VISION steps as too thin for the EA
domain: the generic Vision skeleton never proposed concrete, *safe*
strategy archetypes, so a Homeowner with only a vague idea got no
guard-rails. This module ships a small, opinionated bank of EA patterns
with their non-negotiable safety rails and the owner-interview defaults
they imply.

Ordering is deliberate: ``grid-safe`` and ``trend-follow`` come first
because they are the two archetypes the kit can defend with bounded-risk
rails out of the box. Martingale / unbounded grids are intentionally
NOT in the bank -- the kit refuses to scaffold an unbounded-risk EA.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit

TOOL = "mql5-ea-patterns"

# Order matters: first two are the defensible defaults.
PATTERN_BANK: dict[str, dict] = {
    "grid-safe": {
        "title": "Grid (bounded, drawdown-frozen)",
        "intent": "Recover adverse moves with a capped ladder of orders, "
                  "never an unbounded martingale.",
        "safety_rails": [
            "max_levels is hard-capped (default 7) -- no Nth-level escape hatch",
            "freeze_dd_percent halts NEW grid entries before max_dd_percent",
            "lot_multiplier <= 1.5 and explicitly bounded (no 2.0+ doubling)",
            "no_unbounded_martingale must be true in owner-interview",
            "per-basket equity stop closes the whole grid on freeze breach",
        ],
        "required_params": {
            "max_levels": 7,
            "lot_multiplier": 1.25,
            "freeze_dd_percent": 22.0,
            "max_dd_percent": 35.0,
        },
        "risks": [
            "Trending markets can walk the grid into the freeze band fast",
            "Requires broker with stable spread; widen filter on news",
        ],
        "owner_interview_defaults": {
            "strategy.intent": "grid-safe",
            "strategy.allows_grid": True,
            "strategy.allows_hedging": True,
            "risk.no_unbounded_martingale": True,
        },
    },
    "trend-follow": {
        "title": "Trend following (single-position, SL-mandatory)",
        "intent": "Ride a confirmed trend with one position at a time and a "
                  "hard stop-loss on every entry.",
        "safety_rails": [
            "every market order carries an initial stop-loss (no naked entries)",
            "single net position per symbol (no averaging down)",
            "risk per trade bounded by risk.per_trade_pct (default 0.5%)",
            "trailing stop locks profit; never widens the stop away from price",
        ],
        "required_params": {
            "max_levels": 1,
            "risk_per_trade_pct": 0.5,
            "stop_loss_required": True,
        },
        "risks": [
            "Whipsaw in ranging markets -> many small stop-outs",
            "Needs a robust trend filter to avoid late entries",
        ],
        "owner_interview_defaults": {
            "strategy.intent": "trend-follow",
            "strategy.allows_grid": False,
            "strategy.allows_hedging": False,
            "risk.max_levels": 1,
            "risk.no_unbounded_martingale": True,
        },
    },
    "mean-reversion": {
        "title": "Mean reversion (band, capped exposure)",
        "intent": "Fade stretched moves back toward a moving average with "
                  "capped, non-compounding exposure.",
        "safety_rails": [
            "max_levels small (default 3) with bounded add size",
            "hard stop beyond the band invalidation level",
            "no averaging once invalidation stop is hit",
        ],
        "required_params": {"max_levels": 3, "stop_loss_required": True},
        "risks": ["Regime shift turns reversion into a sustained trend loss"],
        "owner_interview_defaults": {
            "strategy.intent": "mean-reversion",
            "strategy.allows_grid": False,
            "risk.max_levels": 3,
            "risk.no_unbounded_martingale": True,
        },
    },
    "breakout": {
        "title": "Breakout (range escape, SL-mandatory)",
        "intent": "Enter on a confirmed break of a range with a stop back "
                  "inside the range.",
        "safety_rails": [
            "stop-loss inside the broken range on every entry",
            "single position; no re-entry stacking on the same break",
            "spread / slippage filter to avoid false breaks on news",
        ],
        "required_params": {"max_levels": 1, "stop_loss_required": True},
        "risks": ["False breakouts; requires confirmation + spread filter"],
        "owner_interview_defaults": {
            "strategy.intent": "breakout",
            "strategy.allows_grid": False,
            "risk.max_levels": 1,
            "risk.no_unbounded_martingale": True,
        },
    },
}

# Default order for listing / first-suggestion.
PATTERN_ORDER: tuple[str, ...] = (
    "grid-safe", "trend-follow", "mean-reversion", "breakout",
)


def get_pattern(pattern_id: str) -> dict | None:
    return PATTERN_BANK.get(pattern_id)


def list_patterns() -> list[str]:
    return list(PATTERN_ORDER)


def _render_one(pid: str) -> str:
    p = PATTERN_BANK[pid]
    lines = [
        f"# {pid} -- {p['title']}",
        "",
        p["intent"],
        "",
        "## Safety rails (non-negotiable)",
    ]
    lines += [f"- {r}" for r in p["safety_rails"]]
    lines += ["", "## Required params"]
    lines += [f"- {k} = {v}" for k, v in p["required_params"].items()]
    lines += ["", "## Risks"]
    lines += [f"- {r}" for r in p["risks"]]
    return "\n".join(lines) + "\n"


def _render_list() -> str:
    out = ["Available EA strategy patterns (safe-by-default):", ""]
    for pid in PATTERN_ORDER:
        out.append(f"  {pid:16s} {PATTERN_BANK[pid]['title']}")
    out.append("")
    out.append("Note: unbounded martingale is intentionally NOT offered.")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="EA strategy pattern bank (safe-by-default).")
    ap.add_argument("--show", metavar="PATTERN", default=None,
                    help="Show one pattern's rails/params/risks.")
    ap.add_argument("--list", action="store_true", help="List available patterns.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    if args.show is not None:
        p = get_pattern(args.show)
        if p is None:
            if not args.emit_json:
                sys.stderr.write(f"unknown pattern {args.show!r}; choose from {list_patterns()}\n")
            env = Envelope(tool=TOOL, ok=False, exit_code=2,
                           summary=f"unknown pattern {args.show!r}",
                           data={"available": list_patterns()})
            maybe_emit(args, env)
            return 2
        if not args.emit_json:
            sys.stdout.write(_render_one(args.show))
        env = Envelope(tool=TOOL, ok=True, exit_code=0,
                       summary=f"pattern {args.show}",
                       data={"pattern": p, "id": args.show})
        maybe_emit(args, env)
        return 0

    if not args.emit_json:
        sys.stdout.write(_render_list())
    env = Envelope(tool=TOOL, ok=True, exit_code=0,
                   summary=f"{len(PATTERN_ORDER)} patterns",
                   data={"patterns": list_patterns()})
    maybe_emit(args, env)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
