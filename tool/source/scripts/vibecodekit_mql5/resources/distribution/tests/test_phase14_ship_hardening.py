from pathlib import Path

import yaml

from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.composable_codegen import generate
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.ir_configure import apply_profile


def test_multiple_lot_policies_require_explicit_mode():
    ir = parse_text(
        "EA named LotConflict account hedging EURUSD H1 RSI DCA Step 20 "
        "martingale multiplier 1.2 additive lots 0.01 base lot 0.01 max lot 1 "
        "max spread 2 max positions 8",
        strict=True,
    )
    build_plan = plan(ir)
    assert any(b["id"] == "AMBIGUOUS-LOT-MODE" for b in build_plan.blockers)


def test_multiple_dca_policies_require_explicit_mode():
    ir = parse_text(
        "EA named DCAConflict account hedging EURUSD H1 RSI DCA Step 20 "
        "Signal DCA positive DCA base lot 0.01 max lot 1 max spread 2 max positions 8",
        strict=True,
    )
    ir.strategy.setdefault("features", []).append("strategy.dca.positive")
    build_plan = plan(ir)
    assert any(b["id"] == "AMBIGUOUS-DCA-MODE" for b in build_plan.blockers)


def test_ship_profile_selects_sync_execution_and_multiply_mode(tmp_path: Path):
    fixture = Path(__file__).with_name("fixtures_ccbsn.txt")
    profile_path = Path(__file__).with_name("fixtures") / "ccbsn_demo_profile.yaml"
    ir = apply_profile(parse_text(fixture.read_text(encoding="utf-8"), source="ccbsn-golden-fixture", strict=True), yaml.safe_load(profile_path.read_text(encoding="utf-8")), source=str(profile_path))
    build_plan = plan(ir)
    assert build_plan.ok, build_plan.blockers
    out = generate(ir, build_plan, tmp_path / "project")
    cfg = (out / "Include/CCBSN_GoldenFixture/Config.mqh").read_text(encoding="utf-8")
    executor = (out / "Include/CCBSN_GoldenFixture/Core/AsyncTradeExecutor.mqh").read_text(encoding="utf-8")
    main = (out / "Experts/CCBSN_GoldenFixture/CCBSN_GoldenFixture.mq5").read_text(encoding="utf-8")
    assert "InpAsyncExecution=false" in cfg
    assert "InpLotMode=VCK_LOT_MULTIPLY" in cfg
    assert "SetAsyncMode(async_mode)" in executor
    assert "if(ProcessRemoteCommands()) return false;" in main
    assert "if(ManageTrailing()) return true;" in main and "return ManageTrendReversal(buy,sell);" in main
    assert "SYMBOL_TRADE_STOPS_LEVEL" in executor
    assert "SaveExtended" in (out / "Include/CCBSN_GoldenFixture/State/PersistentStateStore.mqh").read_text(encoding="utf-8")
    assert "g_day_start_balance" in main and "PersistState()" in main
