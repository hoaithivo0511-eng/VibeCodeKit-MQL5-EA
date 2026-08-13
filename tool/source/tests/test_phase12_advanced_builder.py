import json
from datetime import time
from pathlib import Path

import yaml

from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.ir_build import run
from vibecodekit_mql5.ir_configure import apply_profile
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.strategy_models import (
    adaptive_basket_tp, dca_condition, dca_distance, hedge_zone_step,
    in_session, next_lot,
)


def test_advanced_policy_models_cover_high_risk_arithmetic():
    assert round(next_lot(0.01, 3, mode="multiply", multiplier=2.0, maximum=1.0), 4) == 0.08
    assert round(next_lot(0.01, 5, mode="add", additive=0.01, maximum=1.0), 8) == 0.06
    assert dca_distance(10, 3, multiplier=2, exponential=True) == 40
    assert dca_condition("signal", 1, 1.1, 1.0, 1.01, 0.05, signal=1)
    assert not dca_condition("closed_bar", 1, 1.1, 1.0, 1.01, 0.05, new_bar=False)
    assert adaptive_basket_tp(10, 3, -250, 1000, loss_pct=-20) == 3
    assert in_session(time(23, 30), "22:00", "02:00")
    decision = hedge_zone_step(active=True, max_side_count=15, trigger_count=15,
                               bid=0.99, ask=1.0, lower=1.01, upper=1.10,
                               buy_lots=1.0, sell_lots=0.5, floating=-10,
                               target_money=20)
    assert decision.direction == -1 and not decision.close_all


def test_ccbsn_manual_can_be_configured_and_planned_without_vendor_hardcoding(tmp_path: Path):
    fixture = Path(__file__).with_name("fixtures_ccbsn.txt")
    profile_path = Path(__file__).with_name("fixtures") / "ccbsn_demo_profile.yaml"
    extracted = parse_text(fixture.read_text(encoding="utf-8"), source="ccbsn-golden-fixture", strict=True)
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    configured = apply_profile(extracted, profile, source=str(profile_path))
    build_plan = plan(configured)
    assert build_plan.ok
    paths = {f.path for f in build_plan.features}
    for required in (
        "strategy.dca.signal", "strategy.dca.bidirectional", "strategy.hedge.zone",
        "strategy.sniper.cross_chain", "strategy.lot_balance", "strategy.reverse_entry",
        "strategy.lottery.after_sl", "strategy.exit.account_money", "strategy.time.sessions",
    ):
        assert required in paths


def test_advanced_build_has_full_feature_traceability(tmp_path: Path):
    fixture = Path(__file__).with_name("fixtures_ccbsn.txt")
    profile_path = Path(__file__).with_name("fixtures") / "ccbsn_demo_profile.yaml"
    extracted = parse_text(fixture.read_text(encoding="utf-8"), source="ccbsn-golden-fixture", strict=True)
    configured = apply_profile(extracted, yaml.safe_load(profile_path.read_text(encoding="utf-8")), source=str(profile_path))
    configured_path = tmp_path / "configured-ir.json"
    configured_path.write_text(json.dumps(configured.to_dict(), ensure_ascii=False), encoding="utf-8")
    report = run(configured_path, tmp_path / "project", force=True)
    assert report["status"]["source_complete"]
    assert report["traceability"]["missing_markers"] == []
    main = Path(report["generated_main"]).read_text(encoding="utf-8")
    for function in ("ManageHedgeZone", "ManageCrossChainSniper", "ManageLotBalance",
                     "ManageReverseEntry", "OnTradeTransaction"):
        assert function in main
