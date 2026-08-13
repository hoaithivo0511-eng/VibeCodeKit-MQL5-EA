"""Verify EA documentation claims against source evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from .ea_doc_claims import make_claim_ledger, claim_supported

REQUIRED_BY_PROFILE = {
    # A generic EA must NOT be forced to claim grid-specific features.
    "generic": [],
    "grid-safe": [
        "async_trade_execution",
        "grid_level_limit",
        "drawdown_freeze",
        "drawdown_hard_stop",
        "persistent_state",
    ],
    "grid-hedge": [
        "hedge_grid_initial_entries",
        "smc_breaker_detection",
        "async_trade_execution",
        "async_losing_side_close",
        "async_basket_close",
        "grid_level_limit",
        "drawdown_freeze",
        "drawdown_hard_stop",
    ],
}

FORBIDDEN_OVERCLAIM = [
    "news_filter",
    "spread_filter",
    "ml_filter",
    "basket_trailing_full",
]


def verify_docs(
    project: str | Path, profile: str = "generic", out: str | Path | None = None
) -> dict:
    ledger = make_claim_ledger(project)
    # Unknown/auto profiles fall back to the relaxed generic set, NOT grid-safe,
    # so a plain EA is never told it is missing grid claims it never made.
    required = REQUIRED_BY_PROFILE.get(profile, REQUIRED_BY_PROFILE.get("generic", []))
    missing_required = [cid for cid in required if not claim_supported(ledger, cid)]
    unsupported_notes = [cid for cid in FORBIDDEN_OVERCLAIM if not claim_supported(ledger, cid)]
    report = {
        "schema_version": "1.0",
        "artifact_type": "ea_doc_verify_report",
        "project": str(project),
        "profile": profile,
        "ok": not missing_required,
        "release_blocking": bool(missing_required),
        "missing_required_claims": missing_required,
        "unsupported_claims_that_must_be_marked_not_implemented": unsupported_notes,
        "ledger": ledger,
    }
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify EA manual claims against source evidence.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--profile", default="generic", help="generic | grid-safe | grid-hedge")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    r = verify_docs(args.project, args.profile, args.out)
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0 if r["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
