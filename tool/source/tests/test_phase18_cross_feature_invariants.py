
from vibecodekit_mql5.build_planner import plan
from tests.test_phase17_runtime_safety import base_ir


def test_account_wide_exit_requires_scope_and_operator_approval():
    ir = base_ir()
    ir.strategy["features"].append("strategy.exit.account_money")
    ir.strategy["parameters"].update({"account_tp_money": 100, "ownership_scope": "managed"})
    build = plan(ir)
    assert any(b["id"] == "ACCOUNT-WIDE-OWNERSHIP-NOT-APPROVED" for b in build.blockers)


def test_account_wide_exit_passes_only_with_explicit_account_contract():
    ir = base_ir()
    ir.strategy["features"].append("strategy.exit.account_money")
    ir.strategy["parameters"].update({"account_tp_money": 100, "ownership_scope": "account"})
    ir.controls["account_wide_close_approved"] = True
    build = plan(ir)
    assert not any(b["id"] == "ACCOUNT-WIDE-OWNERSHIP-NOT-APPROVED" for b in build.blockers)


def test_cross_sniper_pause_requires_defined_hedge_scope():
    ir = base_ir()
    ir.strategy["features"].append("strategy.sniper.cross_chain")
    ir.strategy["parameters"].update({
        "cross_sniper_variant": "pair_loss_profit_v1",
        "cross_sniper_trigger_positions": 5,
        "cross_sniper_target_money": 1,
        "stop_sniper_during_hedge": True,
    })
    build = plan(ir)
    assert any(b["id"] == "SNIPER-HEDGE-PAUSE-SCOPE-REQUIRED" for b in build.blockers)


def test_remote_command_collision_is_blocked():
    ir = base_ir()
    ir.controls = {
        "features": ["controls.pending_order_remote"],
        "pending_command_transport": "pending_order_v1",
        "pending_commands": {
            "pause_a": {"order_type": "buy_stop", "price": 1234, "action": {"type": "set_state", "path": "ea.enabled", "value": False}},
            "pause_b": {"order_type": "buy_stop", "price": 1234, "action": {"type": "set_state", "path": "cycle.new_enabled", "value": False}},
        },
    }
    build = plan(ir)
    assert any(b["id"] == "REMOTE-COMMAND-COLLISION" for b in build.blockers)


def test_dca_outside_session_cannot_override_daily_halt_precedence():
    ir = base_ir(daily=True)
    ir.runtime["time_policy"] = {
        "daily_basis": "server", "session_basis": "server",
        "history_sync_required": True, "cashflow_policy": "exclude", "dst_policy": "platform_clock",
    }
    ir.strategy["parameters"]["risk_precedence_policy"] = "session_overrides_daily"
    build = plan(ir)
    assert any(b["id"] == "INVALID-RISK-PRECEDENCE" for b in build.blockers)


def test_unsupported_semantic_variant_is_blocked():
    ir = base_ir()
    ir.strategy["features"].append("strategy.hedge.zone")
    ir.strategy["parameters"].update({
        "hedge_zone_variant": "vendor_secret_v9",
        "hedge_zone_trigger_positions": 6,
        "hedge_zone_lot_multiplier": 0.5,
        "hedge_zone_distance_pips": 20,
        "hedge_zone_target_money": 10,
    })
    build = plan(ir)
    assert any(b["id"] == "UNSUPPORTED-FEATURE-VARIANT" for b in build.blockers)


def test_cooperative_hedge_zone_emits_per_engine_admission_contract(tmp_path):
    ir = base_ir()
    ir.strategy["features"] += ["strategy.hedge.zone", "strategy.hedge.standard", "strategy.lot_balance"]
    ir.strategy["parameters"].update({
        "hedge_zone_variant": "alternating_boundaries_v1",
        "hedge_zone_trigger_positions": 6,
        "hedge_zone_lot_multiplier": 0.5,
        "hedge_zone_distance_pips": 20,
        "hedge_zone_target_money": 10,
        "hedge_variant": "single_opposite_leg_v1",
        "hedge_trigger_positions": 4,
        "hedge_lot_pct": 20,
        "lot_balance_variant": "managed_chain_v1",
        "balance_trigger_lots": 0.2,
        "balance_stop_lots": 0.05,
        "balance_add_lot": 0.01,
        "hedge_zone_concurrency_policy": "explicit_cooperative",
        "hedge_zone_allowed_engines": ["strategy.hedge.standard", "strategy.lot_balance"],
    })
    build = plan(ir)
    assert build.ok, build.blockers
    from vibecodekit_mql5.advanced_codegen import generate
    out = generate(ir, build, tmp_path / "cooperative")
    config = (out / "Include/RuntimeSafeEA/Config.mqh").read_text(encoding="utf-8")
    main = (out / "Experts/RuntimeSafeEA/RuntimeSafeEA.mq5").read_text(encoding="utf-8")
    assert "VCK_HZ_ALLOW_HEDGE=true" in config
    assert "VCK_HZ_ALLOW_BALANCE=true" in config
    assert "VCK_HZ_ALLOW_REVERSE=false" in config
    assert "HedgeZoneAllowsSource" in main


def test_account_wide_cross_sniper_requires_ownership_approval():
    ir = base_ir()
    ir.strategy["features"].append("strategy.sniper.cross_chain")
    ir.strategy["parameters"].update({
        "cross_sniper_variant": "pair_loss_profit_v1",
        "cross_sniper_trigger_positions": 5,
        "cross_sniper_target_money": 1,
        "cross_sniper_magic_pair_only": False,
        "ownership_scope": "managed",
    })
    build = plan(ir)
    assert any(b["id"] == "CROSS-SNIPER-ACCOUNT-SCOPE-NOT-APPROVED" for b in build.blockers)
