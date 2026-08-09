"""Owner interview contract artifact.

Creates or validates owner-interview.json. This is the "chủ nhà" layer:
capital, risk limits, broker constraints, strategy intent, validation demands.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .contract_utils import write_json, read_json, validation_report, now_iso


REQUIRED_PATHS = [
    "owner.name",
    "capital.account_size",
    "capital.currency_mode",
    "risk.max_dd_percent",
    "risk.freeze_dd_percent",
    "risk.max_levels",
    "broker.symbol",
    "broker.account_mode",
    "strategy.intent",
    "strategy.allows_grid",
    "strategy.allows_hedging",
    "validation_required.compile",
    "validation_required.backtest",
]


def get_path(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def default_interview(name: str, strategy: str, capital: float, symbol: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_type": "owner_interview",
        "created_at": now_iso(),
        "owner": {
            "name": name,
            "approved_to_build": False,
        },
        "capital": {
            "account_size": capital,
            "currency_mode": "cent",
            "max_loss_policy": "bounded_by_account_equity",
            "profit_policy": "withdraw_profit_to_new_accounts",
        },
        "risk": {
            "max_dd_percent": 35.0,
            "freeze_dd_percent": 22.0,
            "max_levels": 7,
            "base_lot": 0.01,
            "lot_multiplier": 1.25,
            "no_unbounded_martingale": True,
        },
        "broker": {
            "symbol": symbol,
            "account_mode": "hedging",
            "min_spread_filter_required": True,
            "execution_notes": "Requires broker-specific validation before live.",
        },
        "strategy": {
            "intent": strategy,
            "allows_grid": True,
            "allows_hedging": True,
            "allows_dca": True,
            "allows_breaker_one_way": True,
            "requires_async_close": True,
            "requires_account_seed_divergence": True,
        },
        "validation_required": {
            "compile": True,
            "backtest": True,
            "architecture_check": True,
            "ap_policy": True,
            "multi_broker": True,
            "walk_forward": True,
            "evidence_manifest": True,
        },
        "open_questions": [
            "Exact broker/server and symbol suffix?",
            "Maximum allowed spread and slippage?",
            "News filter requirements?",
            "Live account versus cent account deployment plan?"
        ],
    }


def validate_interview(data: dict[str, Any]) -> dict[str, Any]:
    missing = [p for p in REQUIRED_PATHS if get_path(data, p) in (None, "")]
    warnings = []
    if get_path(data, "owner.approved_to_build") is not True:
        warnings.append("owner.approved_to_build is not true; build should remain draft until approval.")
    if get_path(data, "risk.no_unbounded_martingale") is not True:
        missing.append("risk.no_unbounded_martingale")
    return validation_report(not missing, missing, warnings)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create or validate owner interview artifact.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="Owner")
    ap.add_argument("--strategy", default="grid-safe")
    ap.add_argument("--capital", type=float, default=1500)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out)
    if args.validate:
        data = read_json(out)
    else:
        data = default_interview(args.name, args.strategy, args.capital, args.symbol)
        write_json(out, data)

    report = validate_interview(data)
    report["artifact"] = str(out)
    print(__import__("json").dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
