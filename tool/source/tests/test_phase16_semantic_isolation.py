from pathlib import Path

from vibecodekit_mql5.advanced_codegen import generate
from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.ea_ir import EAIR


def generic_ir() -> EAIR:
    return EAIR(
        identity={"name": "OrionRecovery", "version": "1.0"},
        runtime={"account_model": "hedging", "symbols": ["EURUSD"], "timeframes": ["H1"]},
        strategy={
            "features": [
                "strategy.entry.signal_selectable",
                "strategy.hedge.zone",
                "strategy.lot_balance",
            ],
            "signals": ["rsi"],
            "signal_logic": "selectable",
            "parameters": {
                "hedge_zone_variant": "alternating_boundaries_v1",
                "hedge_zone_trigger_positions": 6,
                "hedge_zone_lot_multiplier": 0.5,
                "hedge_zone_distance_pips": 20,
                "hedge_zone_target_money": 15,
                "lot_balance_variant": "managed_chain_v1",
                "balance_trigger_lots": 0.2,
                "balance_stop_lots": 0.05,
                "balance_add_lot": 0.01,
                "hedge_zone_concurrency_policy": "exclusive",
                "async_execution": False,
                "execution_idempotency_policy": "reconcile_before_retry",
            },
        },
        risk={"base_lot": 0.01, "max_lot": 1.0, "max_spread_pips": 2.0, "max_open_positions": 10},
        controls={
            "features": ["controls.pending_order_remote"],
            "pending_command_transport": "pending_order_v1",
            "pending_commands": {
                "pause_engine": {
                    "order_type": "buy_limit",
                    "price": 12345.25,
                    "action": {"type": "set_state", "path": "ea.enabled", "value": False},
                },
                "resume_engine": {
                    "order_type": "sell_stop",
                    "price": 23456.75,
                    "action": {"type": "set_state", "path": "ea.enabled", "value": True},
                },
            },
        },
    )


def test_no_ccbsn_vendor_literals_or_command_prices_in_production_source():
    root = Path(__file__).parents[1] / "scripts" / "vibecodekit_mql5"
    production = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in root.rglob("*.py")
        if "resources/distribution/tests" not in p.as_posix()
    )
    for token in ("CCBSN", "Bo.Botfx", "Can Cu Bu Sieng Nang", "999999.0", "666666.0", "888888.0", "555555.0"):
        assert token not in production


def test_feature_variant_is_required_before_semantic_codegen():
    ir = generic_ir()
    del ir.strategy["parameters"]["hedge_zone_variant"]
    build = plan(ir)
    assert any(b["id"] == "MISSING-FEATURE-VARIANT" for b in build.blockers)


def test_generic_remote_commands_are_data_driven(tmp_path: Path):
    ir = generic_ir()
    build = plan(ir)
    assert build.ok, build.blockers
    out = generate(ir, build, tmp_path / "project")
    cfg = (out / "Include/OrionRecovery/Config.mqh").read_text(encoding="utf-8")
    main = (out / "Experts/OrionRecovery/OrionRecovery.mq5").read_text(encoding="utf-8")
    assert "InpCmd_PAUSE_ENGINE=12345.25000000" in cfg
    assert "InpCmd_RESUME_ENGINE=23456.75000000" in cfg
    assert "g_ea_enabled=false" in main and "g_ea_enabled=true" in main
    assert "STOP_EA" not in main and "START_EA" not in main


def test_all_exposure_engines_pass_central_direction_gate(tmp_path: Path):
    ir = generic_ir()
    build = plan(ir)
    out = generate(ir, build, tmp_path / "project")
    main = (out / "Experts/OrionRecovery/OrionRecovery.mq5").read_text(encoding="utf-8")
    assert "bool ExposureAllowed" in main
    assert "(d>0&&g_stop_buy)||(d<0&&g_stop_sell)" in main
    for source in ("VCK_SRC_ENTRY", "VCK_SRC_DCA", "VCK_SRC_HEDGE", "VCK_SRC_HEDGE_ZONE", "VCK_SRC_REVERSE", "VCK_SRC_BALANCE"):
        assert source in main
    assert "if(g_hedge_zone&&VCK_HEDGE_ZONE_EXCLUSIVE) return false;" in main


def test_hedge_zone_composition_requires_concurrency_policy():
    ir = generic_ir()
    del ir.strategy["parameters"]["hedge_zone_concurrency_policy"]
    build = plan(ir)
    assert any(b["id"] == "MISSING-HEDGE-ZONE-CONCURRENCY-POLICY" for b in build.blockers)
