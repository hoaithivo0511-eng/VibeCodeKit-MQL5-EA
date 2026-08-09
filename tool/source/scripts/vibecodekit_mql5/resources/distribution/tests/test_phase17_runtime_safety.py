from pathlib import Path

from vibecodekit_mql5.advanced_codegen import generate
from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.ea_ir import EAIR


def base_ir(*, daily: bool = False) -> EAIR:
    features = ["strategy.entry.signal_selectable", "strategy.dca.enabled", "strategy.dca.step"]
    parameters = {
        "dca_step_pips": 20,
        "async_execution": False,
        "execution_idempotency_policy": "reconcile_before_retry",
    }
    risk = {"base_lot": 0.01, "max_lot": 1.0, "max_spread_pips": 2.0, "max_open_positions": 8}
    runtime = {"account_model": "hedging", "symbols": ["EURUSD"], "timeframes": ["H1"]}
    if daily:
        features += ["strategy.exit.daily_target", "strategy.time.sessions"]
        parameters.update({
            "daily_target_money": 20,
            "sessions": [{"enabled": True, "start": "08:00", "end": "18:00"}],
            "dca_outside_session": True,
            "risk_precedence_policy": "daily_halt_preempts_exposure",
        })
        risk["daily_loss_pct"] = 5
    return EAIR(
        identity={"name": "RuntimeSafeEA"}, runtime=runtime,
        strategy={"features": features, "signals": ["rsi"], "signal_logic": "selectable", "parameters": parameters},
        risk=risk, controls={},
    )


def test_daily_and_session_features_require_explicit_time_policy():
    ir = base_ir(daily=True)
    build = plan(ir)
    assert any(b["id"] == "MISSING-TIME-POLICY" for b in build.blockers)


def test_time_policy_unifies_daily_and_session_clocks(tmp_path: Path):
    ir = base_ir(daily=True)
    ir.runtime["time_policy"] = {
        "daily_basis": "server", "session_basis": "server",
        "history_sync_required": True, "cashflow_policy": "exclude", "dst_policy": "platform_clock",
        "day_boundary_minutes": 0,
    }
    build = plan(ir)
    assert build.ok, build.blockers
    out = generate(ir, build, tmp_path / "project")
    cfg = (out / "Include/RuntimeSafeEA/Config.mqh").read_text(encoding="utf-8")
    main = (out / "Experts/RuntimeSafeEA/RuntimeSafeEA.mq5").read_text(encoding="utf-8")
    assert "VCK_DAILY_TIME_BASIS=VCK_TIME_SERVER" in cfg
    assert "VCK_SESSION_TIME_BASIS=VCK_TIME_SERVER" in cfg
    assert "ClockNow(VCK_SESSION_TIME_BASIS)" in main
    assert "ClockNow(VCK_DAILY_TIME_BASIS)" in main
    assert "ComputeDaySnapshot" in main
    assert "HISTORY_NOT_READY" in main
    assert "account_trading" in main
    assert "day_start_balance=AccountInfoDouble(ACCOUNT_BALANCE)-account_trading-cashflow" in main
    assert "g_history_sync_confirmations>=2" in main


def test_trade_intent_ledger_blocks_unknown_outcome_retry(tmp_path: Path):
    ir = base_ir()
    build = plan(ir)
    assert build.ok, build.blockers
    out = generate(ir, build, tmp_path / "project")
    ledger = (out / "Include/RuntimeSafeEA/Core/TradeIntentLedger.mqh").read_text(encoding="utf-8")
    executor = (out / "Include/RuntimeSafeEA/Core/AsyncTradeExecutor.mqh").read_text(encoding="utf-8")
    assert "FindByRequest(request_id" in ledger
    assert "FindByOrder(order" in ledger
    assert "FindByPosition(trans.position" in ledger
    assert "request_event=trans.type==TRADE_TRANSACTION_REQUEST" in ledger
    assert "if(VCK_BLOCK_UNKNOWN_OUTCOME||created==0" in ledger
    assert "HistorySelect" in ledger
    assert "m_intents.Prepare" in executor
    assert "OpenDefinitelyRejected" in executor
    assert "m_intents.MarkSubmitted" in executor
    assert "m_intents.MarkRejected" in executor


def test_event_reducer_deduplicates_deals_and_final_close_side_effects(tmp_path: Path):
    ir = base_ir()
    ir.strategy["features"].append("strategy.lottery.after_sl")
    ir.strategy["parameters"].update({
        "lottery_sl_multiplier": 2.0,
        "lottery_variant": "per_closed_position_v1",
    })
    build = plan(ir)
    assert build.ok, build.blockers
    out = generate(ir, build, tmp_path / "project")
    reducer = (out / "Include/RuntimeSafeEA/Core/TradeEventReducer.mqh").read_text(encoding="utf-8")
    main = (out / "Experts/RuntimeSafeEA/RuntimeSafeEA.mq5").read_text(encoding="utf-8")
    assert "EnqueueDeal" in reducer and "MarkDealProcessed" in reducer and "AcceptClosedPosition" in reducer
    assert 'Key(kind,slot,"hi")' in reducer and 'Key(kind,slot,"lo")' in reducer
    assert "EventReducer.EnqueueDeal(trans.deal)" in main
    assert "ProcessPendingTradeEvents" in main and "EventReducer.PendingDeal" in main
    assert "HistoryDealSelect(deal)||!EventReducer.MarkDealProcessed" in main
    assert "ManagedPositionIdentifierExists(position_id)" in main
    assert "position_fully_closed&&EventReducer.AcceptClosedPosition(position_id)" in main
    assert "PositionRealizedSummary(position_id" in main


def test_hedge_zone_state_is_reconciled_from_live_position_book(tmp_path: Path):
    ir = base_ir()
    ir.strategy["features"] += ["strategy.hedge.zone", "strategy.lot_balance"]
    ir.strategy["parameters"].update({
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
    })
    build = plan(ir)
    assert build.ok, build.blockers
    out = generate(ir, build, tmp_path / "project")
    main = (out / "Experts/RuntimeSafeEA/RuntimeSafeEA.mq5").read_text(encoding="utf-8")
    state = (out / "Include/RuntimeSafeEA/State/PersistentStateStore.mqh").read_text(encoding="utf-8")
    assert 'ResetHedgeZoneState("no managed positions")' in main
    assert "missing_anchor" in main and "bounds rebuilt" in main
    assert "oldest_identifier" in main or "oldest_identifier" in (out / "Include/RuntimeSafeEA/Core/PositionBook.mqh").read_text(encoding="utf-8")
    assert "state_schema" in state and "3.0" in state
    assert "g_zone_phase==VCK_ZONE_EXITING" in main
    assert "zone_anchor_position_id" in state and "zone_cycle_id" in state


def test_async_execution_requires_reconcile_before_retry_policy():
    ir = base_ir()
    ir.strategy["parameters"]["async_execution"] = True
    ir.strategy["parameters"].pop("execution_idempotency_policy")
    build = plan(ir)
    assert any(b["id"] == "ASYNC-IDEMPOTENCY-POLICY-REQUIRED" for b in build.blockers)


def test_async_timeout_retry_policy_is_blocked():
    ir = base_ir()
    ir.strategy["parameters"].update({
        "async_execution": True,
        "unknown_outcome_policy": "retry_after_timeout",
    })
    build = plan(ir)
    assert any(b["id"] == "ASYNC-UNKNOWN-OUTCOME-MUST-BLOCK" for b in build.blockers)


def test_mixed_daily_and_session_clocks_require_explicit_approval():
    ir = base_ir(daily=True)
    ir.runtime["time_policy"] = {
        "daily_basis": "server", "session_basis": "local",
        "history_sync_required": True, "cashflow_policy": "exclude",
        "dst_policy": "platform_clock",
    }
    build = plan(ir)
    assert any(b["id"] == "TIME-BASIS-MISMATCH" for b in build.blockers)


def test_session_only_strategy_requires_explicit_clock_policy():
    ir = base_ir()
    ir.strategy["features"].append("strategy.time.sessions")
    ir.strategy["parameters"]["sessions"] = [{"enabled": True, "start": "08:00", "end": "18:00"}]
    build = plan(ir)
    assert any(b["id"] == "MISSING-TIME-POLICY" for b in build.blockers)


def test_recovery_engines_with_sessions_require_explicit_timing_contract(tmp_path: Path):
    ir = base_ir()
    ir.strategy["features"] += ["strategy.time.sessions", "strategy.hedge.standard"]
    ir.strategy["parameters"].update({
        "sessions": [{"enabled": True, "start": "08:00", "end": "18:00"}],
        "hedge_variant": "single_opposite_leg_v1",
        "hedge_trigger_positions": 4,
        "hedge_lot_pct": 25,
    })
    ir.runtime["time_policy"] = {"session_basis": "server", "dst_policy": "platform_clock"}
    build = plan(ir)
    assert any(b["id"] == "RECOVERY-SESSION-POLICY-REQUIRED" for b in build.blockers)
    ir.strategy["parameters"]["recovery_session_policy"] = "respect_sessions"
    build = plan(ir)
    assert build.ok, build.blockers
    out = generate(ir, build, tmp_path / "session-recovery")
    cfg = (out / "Include/RuntimeSafeEA/Config.mqh").read_text(encoding="utf-8")
    main = (out / "Experts/RuntimeSafeEA/RuntimeSafeEA.mq5").read_text(encoding="utf-8")
    assert "VCK_RECOVERY_OUTSIDE_SESSION=false" in cfg
    assert "source==VCK_SRC_HEDGE||source==VCK_SRC_HEDGE_ZONE" in main
