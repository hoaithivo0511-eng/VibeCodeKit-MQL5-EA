"""Advanced composable MQL5 generator for canonical EA-IR projects.

The generator is domain-generic.  It composes feature policies from the build
plan and uses explicit operational values from the configured IR.  Vendor
manuals are acceptance fixtures, never templates baked into the architecture.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .ai_build_contract import build_contract_dict, render_contract_md
from .build_planner import BuildPlan
from .ea_ir import EAIR
from .ir_verify import build_artifact_manifest
from .runtime_input_contracts import contract_manifest, render_mql_validator
from .safe_paths import safe_join, validate_ea_name
from .traceability import to_csv


def _enabled(paths: set[str], path: str) -> str:
    return "true" if path in paths else "false"


def _p(ir: EAIR, key: str, default: Any) -> Any:
    return (ir.strategy.get("parameters") or {}).get(key, default)


def _r(ir: EAIR, key: str, default: Any) -> Any:
    return ir.risk.get(key, default)


def _magic(name: str) -> int:
    return 910000 + (sum((i + 1) * ord(ch) for i, ch in enumerate(name)) % 80000)


_SIGNAL_ENUM = {
    "rsi": "VCK_SIGNAL_RSI",
    "rsi_reversal": "VCK_SIGNAL_RSI_REVERSAL",
    "cci": "VCK_SIGNAL_CCI_REVERSAL",
    "cci_reversal": "VCK_SIGNAL_CCI_REVERSAL",
    "stochastic": "VCK_SIGNAL_STOCH_REVERSAL",
    "stochastic_reversal": "VCK_SIGNAL_STOCH_REVERSAL",
    "momentum": "VCK_SIGNAL_MOMENTUM",
    "supertrend": "VCK_SIGNAL_SUPERTREND",
    "utbot": "VCK_SIGNAL_UTBOT",
    "ichimoku_kumo_break": "VCK_SIGNAL_ICHIMOKU_BREAK",
    "smc": "VCK_SIGNAL_SMC_SWING_WITH",
    "smc_all_with": "VCK_SIGNAL_SMC_ALL_WITH",
    "smc_all_against": "VCK_SIGNAL_SMC_ALL_AGAINST",
    "smc_internal_with": "VCK_SIGNAL_SMC_INTERNAL_WITH",
    "smc_internal_against": "VCK_SIGNAL_SMC_INTERNAL_AGAINST",
    "smc_swing_with": "VCK_SIGNAL_SMC_SWING_WITH",
    "smc_swing_against": "VCK_SIGNAL_SMC_SWING_AGAINST",
    "bollinger_bands": "VCK_SIGNAL_BB_REVERSION",
    "pinbar": "VCK_SIGNAL_PINBAR",
    "engulfing": "VCK_SIGNAL_ENGULFING",
    "pinbar_engulfing": "VCK_SIGNAL_PINBAR_ENGULFING",
    "macd": "VCK_SIGNAL_MACD_CROSS",
    "ema_cross": "VCK_SIGNAL_EMA_CROSS",
    "atr_break": "VCK_SIGNAL_ATR_BREAKOUT",
    "candle_color": "VCK_SIGNAL_CANDLE_COLOR",
    "no_condition": "VCK_SIGNAL_NO_CONDITION",
    "random": "VCK_SIGNAL_RANDOM",
    "external_indicator": "VCK_SIGNAL_EXTERNAL",
}

_DCA_ENUM = {
    "step": "VCK_DCA_STEP",
    "step_timeframe": "VCK_DCA_STEP_TIMEFRAME",
    "step_multiplier": "VCK_DCA_STEP_MULTIPLIER",
    "signal": "VCK_DCA_SIGNAL",
    "positive": "VCK_DCA_POSITIVE",
    "bidirectional": "VCK_DCA_BIDIRECTIONAL",
    "signal_bidirectional": "VCK_DCA_SIGNAL_BIDIRECTIONAL",
    "closed_bar": "VCK_DCA_CLOSED_BAR",
}


def _default_signal(ir: EAIR) -> str:
    signals = list(ir.strategy.get("signals") or [])
    return _SIGNAL_ENUM.get(signals[0], "VCK_SIGNAL_RSI_REVERSAL") if signals else "VCK_SIGNAL_RSI_REVERSAL"


def _default_dca(ir: EAIR, paths: set[str]) -> str:
    explicit = str(_p(ir, "dca_mode", "")).lower()
    if explicit in _DCA_ENUM:
        return _DCA_ENUM[explicit]
    priorities = (
        ("strategy.dca.closed_bar", "VCK_DCA_CLOSED_BAR"),
        ("strategy.dca.signal", "VCK_DCA_SIGNAL"),
        ("strategy.dca.positive", "VCK_DCA_POSITIVE"),
        ("strategy.dca.bidirectional", "VCK_DCA_BIDIRECTIONAL"),
        ("strategy.dca.step_timeframe", "VCK_DCA_STEP_TIMEFRAME"),
        ("strategy.dca.step_multiplier", "VCK_DCA_STEP_MULTIPLIER"),
    )
    return next((mode for feature, mode in priorities if feature in paths), "VCK_DCA_STEP")


def _secondary_dca(ir: EAIR, paths: set[str]) -> str:
    explicit = str(_p(ir, "dca_secondary_mode", "")).lower()
    return _DCA_ENUM.get(explicit, _default_dca(ir, paths))


def _command_identifier(command_id: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in command_id)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "CMD_" + cleaned
    return cleaned.upper()[:64]


def _command_definitions(ir: EAIR) -> list[dict[str, Any]]:
    commands = ir.controls.get("pending_commands") or {}
    if not isinstance(commands, dict):
        return []
    order_types = {
        "buy_stop": "ORDER_TYPE_BUY_STOP", "sell_limit": "ORDER_TYPE_SELL_LIMIT",
        "buy_limit": "ORDER_TYPE_BUY_LIMIT", "sell_stop": "ORDER_TYPE_SELL_STOP",
    }
    result: list[dict[str, Any]] = []
    for command_id, raw in sorted(commands.items()):
        if not isinstance(raw, dict):
            continue
        result.append({
            "id": command_id,
            "identifier": _command_identifier(command_id),
            "order_type": order_types[str(raw["order_type"]).lower()],
            "price": float(raw["price"]),
            "action": dict(raw["action"]),
        })
    return result


def _command_ownership(ir: EAIR) -> dict[str, Any]:
    ownership = ir.controls.get("pending_command_ownership") or {}
    return ownership if isinstance(ownership, dict) else {}


def _remote_action_statement(action: dict[str, Any]) -> str:
    action_type = str(action.get("type", "")).lower()
    if action_type == "set_state":
        value = "true" if action.get("value") is True else "false"
        target = {
            "ea.enabled": "g_ea_enabled",
            "cycle.new_enabled": "g_new_cycle",
            "direction.buy_enabled": "g_stop_buy",
            "direction.sell_enabled": "g_stop_sell",
        }[str(action["path"])]
        if str(action["path"]).startswith("direction."):
            value = "false" if value == "true" else "true"
        return f"{target}={value};applied=true;"
    scope = str(action.get("scope", ""))
    return {
        "managed_all": "CloseMagicPositions();applied=RemoteManagedScopeEmpty(0);",
        "managed_buy": "CloseSide(POSITION_TYPE_BUY);applied=RemoteManagedScopeEmpty(1);",
        "managed_sell": "CloseSide(POSITION_TYPE_SELL);applied=RemoteManagedScopeEmpty(-1);",
        "account_all": "CloseAccountPositions();applied=RemoteAccountScopeEmpty();",
    }[scope]


def _remote_effect_expression(action: dict[str, Any]) -> str:
    if str(action.get("type", "")).lower() == "set_state":
        value = "true" if action.get("value") is True else "false"
        target = {
            "ea.enabled": "g_ea_enabled",
            "cycle.new_enabled": "g_new_cycle",
            "direction.buy_enabled": "g_stop_buy",
            "direction.sell_enabled": "g_stop_sell",
        }[str(action["path"])]
        if str(action["path"]).startswith("direction."):
            value = "false" if value == "true" else "true"
        return f"{target}=={value}"
    return {
        "managed_all": "RemoteManagedScopeEmpty(0)",
        "managed_buy": "RemoteManagedScopeEmpty(1)",
        "managed_sell": "RemoteManagedScopeEmpty(-1)",
        "account_all": "RemoteAccountScopeEmpty()",
    }[str(action.get("scope", ""))]


def _remote_command_handler(ir: EAIR) -> str:
    commands = _command_definitions(ir)
    if not commands:
        return "bool ProcessRemoteCommands(){return false;}"
    match_branches: list[str] = []
    apply_branches: list[str] = []
    effect_branches: list[str] = []
    for index, command in enumerate(commands):
        prefix = "if" if index == 0 else "else if"
        ident = command["identifier"]
        statement = _remote_action_statement(command["action"])
        match_branches.append(
            f"{prefix}(type==VCK_CMD_{ident}_TYPE&&MathAbs(p-InpCmd_{ident})<=point)"
            f"return {index};"
        )
        apply_branches.append(f"{prefix}(command_index=={index}){{{statement}}}")
        effect_branches.append(
            f"{prefix}(command_index=={index})return {_remote_effect_expression(command['action'])};"
        )
    match_body = "".join(match_branches)
    apply_body = "".join(apply_branches)
    effect_body = "".join(effect_branches)
    return (
        "bool RemoteManagedScopeEmpty(const int direction){for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);"
        "if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)!=g_symbol||(long)PositionGetInteger(POSITION_MAGIC)!=InpMagic)continue;"
        "ENUM_POSITION_TYPE side=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);if(direction==0||(direction>0&&side==POSITION_TYPE_BUY)||(direction<0&&side==POSITION_TYPE_SELL))return false;}return true;}"
        "bool RemoteAccountScopeEmpty(){return PositionsTotal()==0;}"
        "bool RemoteOrderOwned(const ulong ticket){if(ticket==0||!OrderSelect(ticket))return false;string comment=OrderGetString(ORDER_COMMENT);"
        "return OrderGetString(ORDER_SYMBOL)==g_symbol&&(long)OrderGetInteger(ORDER_MAGIC)==VCK_COMMAND_OWNER_MAGIC&&StringFind(comment,VCK_COMMAND_COMMENT_PREFIX)==0;}"
        "int MatchRemoteCommand(){ENUM_ORDER_TYPE type=(ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);double p=OrderGetDouble(ORDER_PRICE_OPEN);"
        "double point=SymbolInfoDouble(g_symbol,SYMBOL_POINT);" + match_body + "return -1;}"
        "bool ApplyRemoteCommandOnce(const int command_index){bool applied=false;" + apply_body + "return applied;}"
        "bool RemoteCommandEffectSatisfied(const int command_index){" + effect_body + "return false;}"
        "bool ContinueRemoteCommand(){int state=CommandLedger.State();if(state==VCK_CMD_IDLE)return false;"
        "ulong ticket=CommandLedger.Ticket();int command_index=CommandLedger.CommandIndex();"
        "if(state==VCK_CMD_APPLIED){CommandLedger.FinalizeApplied();return true;}"
        "if(state==VCK_CMD_BLOCKED){g_ea_enabled=false;PersistStateCritical();Log.Event(\"REMOTE_COMMAND_BLOCKED\",\"manual reconciliation required\",(double)ticket);return true;}"
        "if(state==VCK_CMD_CLAIMED){if(!RemoteOrderOwned(ticket)){CommandLedger.Block();return true;}"
        "if(!Trade.DeleteOrder(ticket))return true;if(!CommandLedger.MarkDeleted(ticket,command_index))return true;state=VCK_CMD_DELETED;}"
        "if(state==VCK_CMD_DELETED){if(!CommandLedger.BeginApply(ticket,command_index))return true;ApplyRemoteCommandOnce(command_index);state=VCK_CMD_APPLYING;}"
        "if(state==VCK_CMD_APPLYING){if(RemoteCommandEffectSatisfied(command_index)){PersistStateCritical();CommandLedger.MarkApplied(ticket,command_index);}"
        "else{g_ea_enabled=false;PersistStateCritical();Log.Event(\"REMOTE_COMMAND_INCOMPLETE\",\"effect not satisfied; no replay\",(double)ticket);}return true;}return true;}"
        "bool ProcessRemoteCommands(){if(!VCK_USE_REMOTE)return false;if(CommandLedger.State()!=VCK_CMD_IDLE)return ContinueRemoteCommand();"
        "for(int i=OrdersTotal()-1;i>=0;i--){ulong ticket=OrderGetTicket(i);if(!RemoteOrderOwned(ticket))continue;int command_index=MatchRemoteCommand();"
        "if(command_index<0)continue;if(!CommandLedger.Claim(ticket,command_index))return true;return ContinueRemoteCommand();}return false;}"
    )

def _sessions(ir: EAIR) -> list[dict[str, Any]]:
    raw = _p(ir, "sessions", [])
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw[:4]:
        if isinstance(item, dict):
            result.append({"enabled": bool(item.get("enabled", True)), "start": str(item.get("start", "00:00")), "end": str(item.get("end", "23:59"))})
    return result


def _time_policy(ir: EAIR) -> dict[str, Any]:
    raw = ir.runtime.get("time_policy") or {}
    return raw if isinstance(raw, dict) else {}


def _time_basis(value: Any) -> str:
    return {
        "server": "VCK_TIME_SERVER", "local": "VCK_TIME_LOCAL",
        "utc": "VCK_TIME_UTC", "fixed_offset": "VCK_TIME_FIXED_OFFSET",
    }.get(str(value or "server").lower(), "VCK_TIME_SERVER")


def _config(ir: EAIR, plan: BuildPlan) -> str:
    paths = {f.path for f in plan.features}
    name = str(ir.identity["name"])
    symbols = list(ir.runtime.get("symbols") or [])
    timeframes = list(ir.runtime.get("timeframes") or [])
    symbol = symbols[0] if symbols else ""
    tf = timeframes[0] if timeframes else "CURRENT"
    tf_expr = tf if str(tf).startswith("PERIOD_") else f"PERIOD_{tf}"
    if tf_expr == "PERIOD_CURRENT":
        tf_expr = "PERIOD_CURRENT"
    sessions = _sessions(ir)
    time_policy = _time_policy(ir)
    while len(sessions) < 4:
        sessions.append({"enabled": False, "start": "00:00", "end": "00:00"})
    commands = _command_definitions(ir)
    command_ownership = _command_ownership(ir)

    lines: list[str] = [
        "// digits-tested: 5,4,3,2", f"// Generated from EA-IR {ir.sha256()}", "#pragma once", "",
        "enum VCKSignalMode { VCK_SIGNAL_NONE=0,VCK_SIGNAL_RSI,VCK_SIGNAL_RSI_REVERSAL,VCK_SIGNAL_CCI_REVERSAL,VCK_SIGNAL_STOCH_REVERSAL,VCK_SIGNAL_EMA_CROSS,VCK_SIGNAL_BB_REVERSION,VCK_SIGNAL_PINBAR,VCK_SIGNAL_ENGULFING,VCK_SIGNAL_PINBAR_ENGULFING,VCK_SIGNAL_MACD_CROSS,VCK_SIGNAL_MOMENTUM,VCK_SIGNAL_ATR_BREAKOUT,VCK_SIGNAL_SUPERTREND,VCK_SIGNAL_UTBOT,VCK_SIGNAL_ICHIMOKU_BREAK,VCK_SIGNAL_SMC_ALL_WITH,VCK_SIGNAL_SMC_ALL_AGAINST,VCK_SIGNAL_SMC_INTERNAL_WITH,VCK_SIGNAL_SMC_INTERNAL_AGAINST,VCK_SIGNAL_SMC_SWING_WITH,VCK_SIGNAL_SMC_SWING_AGAINST,VCK_SIGNAL_CANDLE_COLOR,VCK_SIGNAL_NO_CONDITION,VCK_SIGNAL_RANDOM,VCK_SIGNAL_EXTERNAL };",
        "enum VCKDCAMode { VCK_DCA_STEP=0,VCK_DCA_STEP_TIMEFRAME,VCK_DCA_STEP_MULTIPLIER,VCK_DCA_SIGNAL,VCK_DCA_POSITIVE,VCK_DCA_BIDIRECTIONAL,VCK_DCA_SIGNAL_BIDIRECTIONAL,VCK_DCA_CLOSED_BAR };",
        "enum VCKLotMode { VCK_LOT_MULTIPLY=0,VCK_LOT_ADD };",
        "enum VCKTimeBasis { VCK_TIME_SERVER=0,VCK_TIME_LOCAL,VCK_TIME_UTC,VCK_TIME_FIXED_OFFSET };", "",
        'input group "Identity and runtime"',
        f"input long InpMagic={_magic(name)};",
        f'input string InpTradeSymbol="{symbol}";',
        f"input ENUM_TIMEFRAMES InpSignalTimeframe={tf_expr};",
        f"input VCKSignalMode InpSignalMode={_default_signal(ir)};",
        f"input VCKDCAMode InpDCAMode={_default_dca(ir, paths)};",
        f"input int InpDCASwitchCount={int(_p(ir, 'dca_switch_count', 0))};",
        f"input VCKDCAMode InpDCASecondaryMode={_secondary_dca(ir, paths)};",
        f"input bool InpAllowBuy={str(bool(_p(ir, 'allow_buy', True))).lower()};",
        f"input bool InpAllowSell={str(bool(_p(ir, 'allow_sell', True))).lower()};",
        f"input int InpMinSecondsBetweenEntries={int(_p(ir, 'min_seconds_between_entries', 2))};",
        f"input int InpMinutesDelayAfterClear={int(_p(ir, 'minutes_delay_after_clear', 0))};",
        f"input bool InpAsyncExecution={str(bool(_p(ir, 'async_execution', False))).lower()};",
        f"input int InpIntentUnknownTimeoutSeconds={int(_p(ir, 'intent_unknown_timeout_seconds', 30))};",
        f"input int InpIntentHistoryLookbackSeconds={int(_p(ir, 'intent_history_lookback_seconds', 86400))};",
        '', '// Time and accounting policy sealed from EA-IR.',
        f"const VCKTimeBasis VCK_DAILY_TIME_BASIS={_time_basis(time_policy.get('daily_basis'))};",
        f"const VCKTimeBasis VCK_SESSION_TIME_BASIS={_time_basis(time_policy.get('session_basis', time_policy.get('daily_basis')))};",
        f"const int VCK_UTC_OFFSET_MINUTES={int(time_policy.get('utc_offset_minutes', 0))};",
        f"const int VCK_DAY_BOUNDARY_MINUTES={int(time_policy.get('day_boundary_minutes', 0))};",
        f"const bool VCK_HISTORY_SYNC_REQUIRED={str(time_policy.get('history_sync_required', False) is True).lower()};",
        f"const bool VCK_EXCLUDE_CASHFLOWS={str(time_policy.get('cashflow_policy', 'exclude') == 'exclude').lower()};",
        f"const bool VCK_RECOVERY_OUTSIDE_SESSION={str(_p(ir, 'recovery_session_policy', 'respect_sessions') == 'allow_recovery_outside_sessions').lower()};",
        '', 'input group "Execution and risk"',
        f"input double InpBaseLot={float(_r(ir, 'base_lot', 0.01)):.4f};",
        f"input double InpMaxLot={float(_r(ir, 'max_lot', 1.0)):.4f};",
        f"input double InpMaxSpreadPips={float(_r(ir, 'max_spread_pips', 3.0)):.2f};",
        f"input int InpMaxBuyPositions={int(_p(ir, 'max_buy_positions', _r(ir, 'max_open_positions', 10)))};",
        f"input int InpMaxSellPositions={int(_p(ir, 'max_sell_positions', _r(ir, 'max_open_positions', 10)))};",
        f"input int InpMaxLevelsBuy={int(_r(ir, 'max_levels_buy', _p(ir, 'max_buy_positions', _r(ir, 'max_open_positions', 10))))};",
        f"input int InpMaxLevelsSell={int(_r(ir, 'max_levels_sell', _p(ir, 'max_sell_positions', _r(ir, 'max_open_positions', 10))))};",
        f"input double InpFreezeDDPct={float(_r(ir, 'freeze_drawdown_pct', 15.0)):.2f};",
        f"input double InpMaxDDPct={float(_r(ir, 'max_drawdown_pct', 20.0)):.2f};",
        f"input int InpSLPips={int(_r(ir, 'sl_pips', 0))};",
        f"input int InpTPPips={int(_r(ir, 'tp_pips', 0))};",
        f"input double InpDailyTargetPct={float(_p(ir, 'daily_target_pct', 0.0)):.2f};",
        f"input double InpDailyLossPct={float(_r(ir, 'daily_loss_pct', 0.0)):.2f};",
        f"input double InpDailyTargetMoney={float(_p(ir, 'daily_target_money', 0.0)):.2f};",
        f"input double InpDailyLossMoney={float(_p(ir, 'daily_loss_money', 0.0)):.2f};",
        f"input int InpNewDayDelayMinutes={int(_p(ir, 'new_day_delay_minutes', 0))};",
        '', 'input group "DCA and lot progression"',
        f"input double InpDCAStepPips={float(_p(ir, 'dca_step_pips', 25.0)):.2f};",
        f"input double InpDCAStepMultiplier={float(_p(ir, 'dca_step_multiplier', 1.2)):.4f};",
        f"input VCKLotMode InpLotMode={'VCK_LOT_ADD' if str(_p(ir, 'lot_mode', 'multiply')).lower() in {'add', 'additive', 'plus'} else 'VCK_LOT_MULTIPLY'};",
        f"input double InpLotMultiplier={float(_p(ir, 'lot_multiplier', 1.2)):.4f};",
        f"input double InpLotAdditive={float(_p(ir, 'lot_additive', 0.01)):.4f};",
        f"input int InpTrendFilterAfterPositions={int(_p(ir, 'dca_trend_filter_after_positions', 0))};",
        f"input bool InpDCAOutsideSession={str(bool(_p(ir, 'dca_outside_session', True))).lower()};",
    ]
    for i in range(1, 6):
        lines += [f"input int InpLotStage{i}Count={int(_p(ir, f'lot_stage_{i}_count', 0))};", f"input double InpLotStage{i}Multiplier={float(_p(ir, f'lot_stage_{i}_multiplier', 1.0)):.4f};"]
    for i in range(1, 5):
        lines += [f"input int InpDistanceStage{i}Count={int(_p(ir, f'distance_stage_{i}_count', 0))};", f"input double InpDistanceStage{i}Pips={float(_p(ir, f'distance_stage_{i}_pips', 0.0)):.2f};"]
    lines += [
        '', 'input group "Basket, money exits and trailing"',
        f"input double InpBasketTargetMoney={float(_p(ir, 'basket_target_money', 0.0)):.2f};",
        f"input double InpBasketStopMoney={float(_p(ir, 'basket_stop_money', 0.0)):.2f};",
        f"input double InpBasketTPPips={float(_p(ir, 'basket_tp_pips', 0.0)):.2f};",
        f"input double InpAdaptiveTPLossPct={float(_p(ir, 'adaptive_tp_loss_pct', 0.0)):.2f};",
        f"input double InpAdaptiveTPLossMoney={float(_p(ir, 'adaptive_tp_loss_money', 0.0)):.2f};",
        f"input double InpAdaptiveBasketTPPips={float(_p(ir, 'adaptive_basket_tp_pips', 0.0)):.2f};",
        f"input double InpAccountTPMoney={float(_p(ir, 'account_tp_money', 0.0)):.2f};",
        f"input double InpAccountSLMoney={float(_p(ir, 'account_sl_money', 0.0)):.2f};",
        f"input bool InpAllowAccountWideClose={str(bool(_p(ir, 'allow_account_wide_close', False))).lower()};",
        f"input double InpBuyTPMoney={float(_p(ir, 'buy_tp_money', 0.0)):.2f};",
        f"input double InpBuySLMoney={float(_p(ir, 'buy_sl_money', 0.0)):.2f};",
        f"input double InpSellTPMoney={float(_p(ir, 'sell_tp_money', 0.0)):.2f};",
        f"input double InpSellSLMoney={float(_p(ir, 'sell_sl_money', 0.0)):.2f};",
        f"input double InpSteppedTargetMoney={float(_p(ir, 'stepped_target_money', 0.0)):.2f};",
        f"input int InpSteppedTargetDelayMinutes={int(_p(ir, 'stepped_target_delay_minutes', 0))};",
        f"input double InpBalanceDifferencePct={float(_p(ir, 'balance_difference_pct', 0.0)):.2f};",
        f"input double InpTrailingStartPips={float(_p(ir, 'trailing_start_pips', 0.0)):.2f};",
        f"input double InpTrailingDistancePips={float(_p(ir, 'trailing_distance_pips', 0.0)):.2f};",
        '', 'input group "Sniper and partial recovery"',
        f"input int InpSniperTriggerPositions={int(_p(ir, 'sniper_trigger_positions', 0))};",
        f"input int InpSniperHeadCount={int(_p(ir, 'sniper_head_count', 1))};",
        f"input int InpSniperTailMaxCount={int(_p(ir, 'sniper_tail_max_count', 1))};",
        f"input double InpSniperTargetMoney={float(_p(ir, 'sniper_target_money', 0.0)):.2f};",
        f"input double InpPartialClosePct={float(_p(ir, 'partial_close_pct', 0.0)):.2f};",
        f"input int InpCrossSniperTriggerPositions={int(_p(ir, 'cross_sniper_trigger_positions', 0))};",
        f"input double InpCrossSniperTargetMoney={float(_p(ir, 'cross_sniper_target_money', 0.0)):.2f};",
        f"input bool InpCrossSniperMagicPairOnly={str(bool(_p(ir, 'cross_sniper_magic_pair_only', True))).lower()};",
        '', 'input group "Hedge, hedge zone and balancing"',
        f"input int InpHedgeTriggerPositions={int(_p(ir, 'hedge_trigger_positions', 0))};",
        f"input double InpHedgeTriggerLossPct={float(_p(ir, 'hedge_trigger_loss_pct', 0.0)):.2f};",
        f"input bool InpHedgeUseDCALot={str(bool(_p(ir, 'hedge_use_dca_lot', False))).lower()};",
        f"input double InpHedgeLotPct={float(_p(ir, 'hedge_lot_pct', 0.0)):.2f};",
        f"input double InpHedgeTPPips={float(_p(ir, 'hedge_tp_pips', 0.0)):.2f};",
        f"input double InpHedgeExitMoney={float(_p(ir, 'hedge_exit_money', 0.0)):.2f};",
        f"input bool InpStopSniperDuringHedge={str(bool(_p(ir, 'stop_sniper_during_hedge', True))).lower()};",
        f"input int InpHedgeZoneTriggerPositions={int(_p(ir, 'hedge_zone_trigger_positions', 0))};",
        f"input double InpHedgeZoneLotMultiplier={float(_p(ir, 'hedge_zone_lot_multiplier', 1.0)):.2f};",
        f"input double InpHedgeZoneDistancePips={float(_p(ir, 'hedge_zone_distance_pips', 0.0)):.2f};",
        f"input double InpHedgeZoneTargetMoney={float(_p(ir, 'hedge_zone_target_money', 0.0)):.2f};",
        f"input double InpHedgeZoneTargetPips={float(_p(ir, 'hedge_zone_target_pips', 0.0)):.2f};",
        f"input int InpHedgeZoneNewTargetCount={int(_p(ir, 'hedge_zone_new_target_count', 0))};",
        f"input double InpHedgeZoneNewTargetMoney={float(_p(ir, 'hedge_zone_new_target_money', 0.0)):.2f};",
        f"input double InpHedgeZoneMaxLot={float(_p(ir, 'hedge_zone_max_lot', _r(ir, 'max_lot', 1.0))):.4f};",
        f"input int InpReverseTriggerPositions={int(_p(ir, 'reverse_trigger_positions', 0))};",
        f"input double InpReverseLotPct={float(_p(ir, 'reverse_lot_pct', 0.0)):.2f};",
        f"input double InpReverseFixedLot={float(_p(ir, 'reverse_fixed_lot', 0.0)):.4f};",
        f"input double InpBalanceTriggerLots={float(_p(ir, 'balance_trigger_lots', 0.0)):.4f};",
        f"input double InpBalanceStopLots={float(_p(ir, 'balance_stop_lots', 0.0)):.4f};",
        f"input double InpBalanceAddLot={float(_p(ir, 'balance_add_lot', 0.0)):.4f};",
        f"input int InpBalanceDelaySeconds={int(_p(ir, 'balance_delay_seconds', 30))};",
        '', 'input group "Lottery after SL and manual reset"',
        f"input double InpLotterySLMultiplier={float(_p(ir, 'lottery_sl_multiplier', 1.0)):.4f};",
        f"input int InpLotteryDelayMinutes={int(_p(ir, 'lottery_delay_minutes', 0))};",
        f"input double InpLotteryResetLossMoney={float(_p(ir, 'lottery_reset_loss_money', 0.0)):.2f};",
        f"input double InpResetLot={float(_p(ir, 'reset_lot', _r(ir, 'base_lot', 0.01))):.4f};",
        f"input double InpResetMultiplier={float(_p(ir, 'reset_multiplier', 1.0)):.4f};",
        f"input double InpResetBasketTPPips={float(_p(ir, 'reset_basket_tp_pips', 0.0)):.2f};",
        '', 'input group "Signal parameters"',
        f"input int InpRSIPeriod={int(_p(ir, 'rsi_period', 14))};",
        f"input double InpRSIOversold={float(_p(ir, 'rsi_oversold', 25.0)):.2f};",
        f"input double InpRSIOverbought={float(_p(ir, 'rsi_overbought', 75.0)):.2f};",
        f"input int InpCCIPeriod={int(_p(ir, 'cci_period', 14))};",
        f"input double InpCCIOversold={float(_p(ir, 'cci_oversold', -100.0)):.2f};",
        f"input double InpCCIOverbought={float(_p(ir, 'cci_overbought', 100.0)):.2f};",
        f"input int InpStochK={int(_p(ir, 'stoch_k', 5))};",
        f"input int InpStochD={int(_p(ir, 'stoch_d', 3))};",
        f"input int InpStochSlowing={int(_p(ir, 'stoch_slowing', 3))};",
        f"input int InpMomentumPeriod={int(_p(ir, 'momentum_period', 14))};",
        f"input double InpMomentumBuyLevel={float(_p(ir, 'momentum_buy_level', 100.45)):.2f};",
        f"input double InpMomentumSellLevel={float(_p(ir, 'momentum_sell_level', 99.45)):.2f};",
        f"input int InpEMAFast={int(_p(ir, 'ema_fast', 34))};",
        f"input int InpEMASlow={int(_p(ir, 'ema_slow', 89))};",
        f"input int InpBBPeriod={int(_p(ir, 'bb_period', 20))};",
        f"input double InpBBDeviation={float(_p(ir, 'bb_deviation', 2.0)):.2f};",
        f"input int InpATRPeriod={int(_p(ir, 'atr_period', 10))};",
        f"input double InpATRBreakMultiplier={float(_p(ir, 'atr_break_multiplier', 1.0)):.2f};",
        f"input int InpSupertrendPeriod={int(_p(ir, 'supertrend_period', 21))};",
        f"input double InpSupertrendMultiplier={float(_p(ir, 'supertrend_multiplier', 3.0)):.2f};",
        f"input int InpUTBotPeriod={int(_p(ir, 'utbot_period', 10))};",
        f"input double InpUTBotSensitivity={float(_p(ir, 'utbot_sensitivity', 1.0)):.2f};",
        f"input int InpIchimokuTenkan={int(_p(ir, 'ichimoku_tenkan', 9))};",
        f"input int InpIchimokuKijun={int(_p(ir, 'ichimoku_kijun', 26))};",
        f"input int InpIchimokuSenkou={int(_p(ir, 'ichimoku_senkou', 52))};",
        f"input int InpSMCInternalLookback={int(_p(ir, 'smc_internal_lookback', 5))};",
        f"input int InpSMCSwingLookback={int(_p(ir, 'smc_swing_lookback', 20))};",
        f"input double InpPinbarWickRatio={float(_p(ir, 'pinbar_wick_ratio', 5.0)):.2f};",
        f"input double InpPinbarOppositeRatio={float(_p(ir, 'pinbar_opposite_ratio', 6.0)):.2f};",
        f"input double InpMinCandlePips={float(_p(ir, 'min_candle_pips', 0.0)):.2f};",
        f"input bool InpEngulfFullWick={str(bool(_p(ir, 'engulf_full_wick', True))).lower()};",
        f"input int InpUnconditionalDirection={int(_p(ir, 'unconditional_direction', 1))};",
        f'input string InpExternalIndicator="{_p(ir, "external_indicator_name", "")!s}";',
        f"input int InpExternalBuyBuffer={int(_p(ir, 'external_buy_buffer', 0))};",
        f"input int InpExternalSellBuffer={int(_p(ir, 'external_sell_buffer', 1))};",
        '', 'input group "Filters and zone cycle"',
        f"input bool InpUseEMAFilter={_enabled(paths, 'strategy.filter.ema')};",
        f"input bool InpUseMACDFilter={_enabled(paths, 'strategy.filter.macd')};",
        f"input bool InpUseRSIFilter={_enabled(paths, 'strategy.filter.rsi')};",
        f"input double InpEMAMaxPriceDistancePips={float(_p(ir, 'ema_max_price_distance_pips', 0.0)):.2f};",
        f"input double InpEMAMinSeparationPips={float(_p(ir, 'ema_min_separation_pips', 0.0)):.2f};",
        f"input double InpZoneCycleUpper={float(_p(ir, 'zone_cycle_upper', 0.0)):.5f};",
        f"input double InpZoneCycleLower={float(_p(ir, 'zone_cycle_lower', 0.0)):.5f};",
        '', 'input group "Trading sessions"',
    ]
    for i, session in enumerate(sessions, 1):
        lines += [f"input bool InpSession{i}Enabled={str(session['enabled']).lower()};", f'input string InpSession{i}Start="{session["start"]}";', f'input string InpSession{i}End="{session["end"]}";']
    if commands:
        lines += ['', 'input group "Remote controls"']
        lines += [
            f"const long VCK_COMMAND_OWNER_MAGIC={int(command_ownership['magic'])};",
            f'const string VCK_COMMAND_COMMENT_PREFIX="{command_ownership["comment_prefix"]}";',
        ]
        for command in commands:
            ident = command["identifier"]
            lines += [
                f"input double InpCmd_{ident}={command['price']:.8f};",
                f"const ENUM_ORDER_TYPE VCK_CMD_{ident}_TYPE={command['order_type']};",
            ]
    lines += [
        '', '// Cross-feature semantic contracts (sealed from EA-IR).',
        f"const bool VCK_HEDGE_ZONE_EXCLUSIVE={str(_p(ir, 'hedge_zone_concurrency_policy', 'exclusive') == 'exclusive').lower()};",
        f"const bool VCK_HZ_ALLOW_HEDGE={str('strategy.hedge.standard' in set(_p(ir, 'hedge_zone_allowed_engines', []))).lower()};",
        f"const bool VCK_HZ_ALLOW_REVERSE={str('strategy.reverse_entry' in set(_p(ir, 'hedge_zone_allowed_engines', []))).lower()};",
        f"const bool VCK_HZ_ALLOW_BALANCE={str('strategy.lot_balance' in set(_p(ir, 'hedge_zone_allowed_engines', []))).lower()};",
        f"const bool VCK_SNIPER_PAUSE_HEDGE_ORIGIN_ONLY={str(_p(ir, 'sniper_hedge_pause_scope', 'hedge_origin_only') == 'hedge_origin_only').lower()};",
        f"const bool VCK_ACCOUNT_WIDE_APPROVED={str(ir.controls.get('account_wide_close_approved') is True).lower()};",
        f"const bool VCK_RECONCILE_BEFORE_RETRY={str(_p(ir, 'execution_idempotency_policy', 'reconcile_before_retry') == 'reconcile_before_retry').lower()};",
        f"const bool VCK_BLOCK_UNKNOWN_OUTCOME={str(_p(ir, 'unknown_outcome_policy', 'block_until_reconciled') == 'block_until_reconciled').lower()};",
        '', '// Feature contract emitted by the capability plan.'
    ]
    toggles = {
        "DCA": "strategy.dca.enabled", "STEP_MULTIPLIER": "strategy.dca.step_multiplier",
        "LOT_MULTIPLIER": "strategy.sizing.martingale", "LOT_ADDITIVE": "strategy.sizing.additive",
        "LOTTERY": "strategy.lottery.after_sl", "HEDGE": "strategy.hedge.standard",
        "HEDGE_ZONE": "strategy.hedge.zone", "REVERSE_ENTRY": "strategy.reverse_entry",
        "LOT_BALANCE": "strategy.lot_balance", "BASKET_TP": "strategy.exit.basket_tp",
        "ADAPTIVE_TP": "strategy.exit.adaptive_basket_tp", "MONEY_EXIT": "strategy.exit.money",
        "ACCOUNT_MONEY_EXIT": "strategy.exit.account_money", "SIDE_MONEY_EXIT": "strategy.exit.side_money",
        "DAILY_GUARD": "strategy.exit.daily_target", "STEPPED_TARGET": "strategy.exit.stepped_target",
        "TRAILING": "strategy.exit.trailing", "TREND_REVERSAL_EXIT": "strategy.exit.trend_reversal",
        "BALANCE_DIFFERENCE_EXIT": "strategy.exit.balance_difference", "SNIPER": "strategy.sniper.same_chain",
        "PARTIAL_SNIPER": "strategy.sniper.partial", "CROSS_SNIPER": "strategy.sniper.cross_chain",
        "SESSIONS": "strategy.time.sessions", "ZONE_CYCLE": "strategy.filter.zone_cycle",
        "REMOTE": "controls.pending_order_remote", "PANEL": "controls.chart_panel", "RESET_LOTS": "controls.reset_lots",
    }
    for const, feature in toggles.items():
        lines += [f"// VCK-FEATURE:{feature}", f"const bool VCK_USE_{const}={_enabled(paths, feature)};"]
    lines += ["", "// Complete planned feature trace markers."]
    for feature in sorted(paths):
        lines.append(f"// VCK-IMPLEMENTED:{feature}")
    lines = [("sinput " + line[6:]) if line.startswith("input ") and not line.startswith("input group") else line for line in lines]
    return "\n".join(lines) + "\n"


TRADE_INTENT_LEDGER = r'''// digits-tested: 5,4,3,2
#pragma once
enum VCKTradeIntentState { VCK_INTENT_NONE=0,VCK_INTENT_PREPARED,VCK_INTENT_SUBMITTED,VCK_INTENT_ACKNOWLEDGED,VCK_INTENT_PARTIAL,VCK_INTENT_COMPLETED,VCK_INTENT_UNKNOWN };
class CTradeIntentLedger
  {
private:
   string m_prefix,m_symbol;long m_magic;int m_counter,m_timeout,m_lookback;
   string Key(const int source,const int direction,const string suffix){return m_prefix+(string)source+"_"+(string)direction+"_"+suffix;}
   long MakeId(const int source,const int direction){m_counter=(m_counter+1)%1000;return(long)TimeCurrent()*10000+(long)(source+10)*100+(direction>0?50:0)+m_counter;}
   string DiagnosticPrefix(const long id){return"I"+(string)id+"|";}
   void SaveUlong(const int source,const int direction,const string suffix,const ulong value){GlobalVariableSet(Key(source,direction,suffix+"_hi"),(double)(value>>32));GlobalVariableSet(Key(source,direction,suffix+"_lo"),(double)(value&0xFFFFFFFF));}
   ulong LoadUlong(const int source,const int direction,const string suffix){ulong hi=GlobalVariableCheck(Key(source,direction,suffix+"_hi"))?(ulong)GlobalVariableGet(Key(source,direction,suffix+"_hi")):0,lo=GlobalVariableCheck(Key(source,direction,suffix+"_lo"))?(ulong)GlobalVariableGet(Key(source,direction,suffix+"_lo")):0;return(hi<<32)|lo;}
   void SetState(const int source,const int direction,const VCKTradeIntentState state){GlobalVariableSet(Key(source,direction,"state"),(double)state);GlobalVariablesFlush();}
   void Clear(const int source,const int direction){string fields[]={"id","created","state","request_id","volume","diag_seen","order_hi","order_lo","position_hi","position_lo","deal_hi","deal_lo"};for(int i=0;i<ArraySize(fields);i++)GlobalVariableDel(Key(source,direction,fields[i]));GlobalVariablesFlush();}
   bool FindByRequest(const uint request_id,int &source,int &direction){if(request_id==0)return false;for(source=0;source<6;source++)for(direction=-1;direction<=1;direction+=2)if(GlobalVariableCheck(Key(source,direction,"request_id"))&&(uint)GlobalVariableGet(Key(source,direction,"request_id"))==request_id)return true;return false;}
   bool FindByOrder(const ulong order,int &source,int &direction){if(order==0)return false;for(source=0;source<6;source++)for(direction=-1;direction<=1;direction+=2)if(LoadUlong(source,direction,"order")==order)return true;return false;}
   bool FindByPosition(const ulong position,int &source,int &direction){if(position==0)return false;for(source=0;source<6;source++)for(direction=-1;direction<=1;direction+=2)if(LoadUlong(source,direction,"position")==position)return true;return false;}
   bool LivePositionIdentity(const ulong position_id){if(position_id==0)return false;for(int i=0;i<PositionsTotal();i++){ulong ticket=PositionGetTicket(i);if(ticket>0&&PositionSelectByTicket(ticket)&&PositionGetString(POSITION_SYMBOL)==m_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==m_magic&&(ulong)PositionGetInteger(POSITION_IDENTIFIER)==position_id)return true;}return false;}
   bool HistoryDealIdentity(const ulong deal){return deal>0&&HistoryDealSelect(deal)&&HistoryDealGetString(deal,DEAL_SYMBOL)==m_symbol&&(long)HistoryDealGetInteger(deal,DEAL_MAGIC)==m_magic;}
   bool HistoryDealForOrder(const ulong order){if(order==0)return false;for(int i=0;i<HistoryDealsTotal();i++){ulong deal=HistoryDealGetTicket(i);if(deal>0&&(ulong)HistoryDealGetInteger(deal,DEAL_ORDER)==order&&HistoryDealGetString(deal,DEAL_SYMBOL)==m_symbol&&(long)HistoryDealGetInteger(deal,DEAL_MAGIC)==m_magic)return true;}return false;}
   bool DefinitelyRejected(const uint retcode){return retcode==TRADE_RETCODE_REJECT||retcode==TRADE_RETCODE_INVALID||retcode==TRADE_RETCODE_INVALID_VOLUME||retcode==TRADE_RETCODE_INVALID_PRICE||retcode==TRADE_RETCODE_INVALID_STOPS||retcode==TRADE_RETCODE_TRADE_DISABLED||retcode==TRADE_RETCODE_MARKET_CLOSED||retcode==TRADE_RETCODE_NO_MONEY||retcode==TRADE_RETCODE_INVALID_FILL||retcode==TRADE_RETCODE_INVALID_ORDER;}
   bool ReconcileSlot(const int source,const int direction)
     {
      ulong deal=LoadUlong(source,direction,"deal"),position=LoadUlong(source,direction,"position"),order=LoadUlong(source,direction,"order");
      if(order>0&&OrderSelect(order)&&OrderGetString(ORDER_SYMBOL)==m_symbol&&(long)OrderGetInteger(ORDER_MAGIC)==m_magic){ENUM_ORDER_STATE live_state=(ENUM_ORDER_STATE)OrderGetInteger(ORDER_STATE);SetState(source,direction,live_state==ORDER_STATE_PARTIAL?VCK_INTENT_PARTIAL:VCK_INTENT_ACKNOWLEDGED);return true;}
      if(!HistorySelect(TimeCurrent()-m_lookback,TimeCurrent()))return false;
      if(order>0&&HistoryOrderSelect(order))
        {
         ENUM_ORDER_STATE state=(ENUM_ORDER_STATE)HistoryOrderGetInteger(order,ORDER_STATE);
         if(state==ORDER_STATE_FILLED||(HistoryDealForOrder(order)&&(state==ORDER_STATE_CANCELED||state==ORDER_STATE_REJECTED||state==ORDER_STATE_EXPIRED))){SetState(source,direction,VCK_INTENT_COMPLETED);Clear(source,direction);return true;}
         if(state==ORDER_STATE_CANCELED||state==ORDER_STATE_REJECTED||state==ORDER_STATE_EXPIRED){Clear(source,direction);return true;}
         if(state==ORDER_STATE_PARTIAL){SetState(source,direction,VCK_INTENT_PARTIAL);return true;}
        }
      if(HistoryDealForOrder(order)||HistoryDealIdentity(deal)||LivePositionIdentity(position)){SetState(source,direction,VCK_INTENT_PARTIAL);return true;}
      return false;
     }
public:
   void Configure(const long magic,const string symbol,const int timeout_seconds,const int lookback_seconds){m_magic=magic;m_symbol=symbol;m_timeout=MathMax(5,timeout_seconds);m_lookback=MathMax(3600,lookback_seconds);m_prefix="VCK_INTENT_V2_"+(string)magic+"_"+symbol+"_";m_counter=0;}
   bool Prepare(const int source,const int direction,const string base_comment,string &wire_comment)
     {
      string id_key=Key(source,direction,"id");
      if(GlobalVariableCheck(id_key)){ReconcileSlot(source,direction);if(GlobalVariableCheck(id_key)){datetime created=GlobalVariableCheck(Key(source,direction,"created"))?(datetime)GlobalVariableGet(Key(source,direction,"created")):0;if(VCK_BLOCK_UNKNOWN_OUTCOME||created==0||TimeCurrent()-created<m_timeout||!HistorySelect(TimeCurrent()-m_lookback,TimeCurrent()))return false;Clear(source,direction);}}
      long id=MakeId(source,direction);GlobalVariableSet(id_key,(double)id);GlobalVariableSet(Key(source,direction,"created"),(double)TimeCurrent());SetState(source,direction,VCK_INTENT_PREPARED);wire_comment=StringSubstr(DiagnosticPrefix(id)+base_comment,0,31);return true;
     }
   void MarkSubmitted(const int source,const int direction,const MqlTradeResult &result,const double requested_volume)
     {
      GlobalVariableSet(Key(source,direction,"request_id"),(double)result.request_id);SaveUlong(source,direction,"order",result.order);SaveUlong(source,direction,"deal",result.deal);GlobalVariableSet(Key(source,direction,"volume"),requested_volume);
      if(result.retcode==TRADE_RETCODE_DONE_PARTIAL)SetState(source,direction,VCK_INTENT_PARTIAL);else if(result.retcode==TRADE_RETCODE_DONE){SetState(source,direction,VCK_INTENT_COMPLETED);Clear(source,direction);}else SetState(source,direction,VCK_INTENT_SUBMITTED);
     }
   void MarkUnknown(const int source,const int direction,const MqlTradeResult &result){GlobalVariableSet(Key(source,direction,"request_id"),(double)result.request_id);SaveUlong(source,direction,"order",result.order);SaveUlong(source,direction,"deal",result.deal);SetState(source,direction,VCK_INTENT_UNKNOWN);}
   void MarkRejected(const int source,const int direction){Clear(source,direction);}
   void ObserveDiagnosticComment(const string comment)
     {
      if(StringLen(comment)<3||StringGetCharacter(comment,0)!=73)return;int sep=StringFind(comment,"|");if(sep<2)return;long id=(long)StringToInteger(StringSubstr(comment,1,sep-1));for(int source=0;source<6;source++)for(int direction=-1;direction<=1;direction+=2){string key=Key(source,direction,"id");if(GlobalVariableCheck(key)&&(long)GlobalVariableGet(key)==id)GlobalVariableSet(Key(source,direction,"diag_seen"),(double)TimeCurrent());}
     }
   bool OnTransaction(const MqlTradeTransaction &trans,const MqlTradeResult &result)
     {
      bool request_event=trans.type==TRADE_TRANSACTION_REQUEST;
      bool order_event=trans.type==TRADE_TRANSACTION_ORDER_ADD||trans.type==TRADE_TRANSACTION_ORDER_UPDATE||trans.type==TRADE_TRANSACTION_ORDER_DELETE||trans.type==TRADE_TRANSACTION_HISTORY_ADD||trans.type==TRADE_TRANSACTION_HISTORY_UPDATE||trans.type==TRADE_TRANSACTION_HISTORY_DELETE;
      uint request_id=request_event?result.request_id:0;ulong order=trans.order>0?trans.order:(request_event?result.order:0),deal=trans.deal>0?trans.deal:(request_event?result.deal:0);
      int source=0,direction=0;bool matched=FindByRequest(request_id,source,direction);if(!matched)matched=FindByOrder(order,source,direction);if(!matched)matched=FindByPosition(trans.position,source,direction);if(!matched)return false;
      if(order>0)SaveUlong(source,direction,"order",order);if(trans.position>0)SaveUlong(source,direction,"position",trans.position);if(deal>0)SaveUlong(source,direction,"deal",deal);
      if(request_event&&DefinitelyRejected(result.retcode)){MarkRejected(source,direction);return true;}
      if((request_event&&result.retcode==TRADE_RETCODE_DONE_PARTIAL)||(order_event&&trans.order_state==ORDER_STATE_PARTIAL)){SetState(source,direction,VCK_INTENT_PARTIAL);return true;}
      if((request_event&&result.retcode==TRADE_RETCODE_DONE)||(order_event&&trans.order_state==ORDER_STATE_FILLED)){SetState(source,direction,VCK_INTENT_COMPLETED);Clear(source,direction);return true;}
      if(trans.type==TRADE_TRANSACTION_DEAL_ADD&&trans.deal>0){SetState(source,direction,VCK_INTENT_PARTIAL);return true;}
      if(request_event&&result.retcode==TRADE_RETCODE_PLACED)SetState(source,direction,VCK_INTENT_ACKNOWLEDGED);return true;
     }
   void Reconcile(){for(int source=0;source<6;source++)for(int direction=-1;direction<=1;direction+=2)if(GlobalVariableCheck(Key(source,direction,"id")))ReconcileSlot(source,direction);}
  };
'''

TRADE_EVENT_REDUCER = r'''// digits-tested: 5,4,3,2
#pragma once
class CTradeEventReducer
  {
private:
   string m_prefix; int m_slots;
   string Key(const string kind,const int slot,const string part){return m_prefix+kind+"_"+(string)slot+"_"+part;}
   uint High(const ulong value){return (uint)(value>>32);}
   uint Low(const ulong value){return (uint)(value&0xFFFFFFFF);}
   ulong Read(const string kind,const int slot)
     {
      string hi=Key(kind,slot,"hi"),lo=Key(kind,slot,"lo");
      if(!GlobalVariableCheck(hi)||!GlobalVariableCheck(lo))return 0;
      return ((ulong)(uint)GlobalVariableGet(hi)<<32)|(ulong)(uint)GlobalVariableGet(lo);
     }
   void Write(const string kind,const int slot,const ulong value){GlobalVariableSet(Key(kind,slot,"hi"),(double)High(value));GlobalVariableSet(Key(kind,slot,"lo"),(double)Low(value));}
   bool Seen(const string kind,const ulong value){for(int i=0;i<m_slots;i++)if(Read(kind,i)==value)return true;return false;}
   bool Accept(const string kind,const ulong value){if(value==0||Seen(kind,value))return false;int cursor_key=(kind=="deal"?0:1);string ck=m_prefix+"cursor_"+(string)cursor_key;int cursor=GlobalVariableCheck(ck)?(int)GlobalVariableGet(ck):0;Write(kind,cursor%m_slots,value);GlobalVariableSet(ck,(double)((cursor+1)%m_slots));return true;}
public:
   void Configure(const long magic,const string symbol,const int slots=128){m_prefix="VCK_EVENT_"+(string)magic+"_"+symbol+"_";m_slots=MathMax(32,MathMin(256,slots));}
   int Slots(){return m_slots;}
   ulong PendingDeal(const int slot){if(slot<0||slot>=m_slots)return 0;return Read("pending",slot);}
   bool EnqueueDeal(const ulong deal)
     {
      if(deal==0||Seen("deal",deal)||Seen("pending",deal))return true;
      for(int i=0;i<m_slots;i++)if(Read("pending",i)==0){Write("pending",i,deal);return true;}
      GlobalVariableSet(m_prefix+"overflow",1.0);return false;
     }
   bool MarkDealProcessed(const ulong deal)
     {
      if(deal==0||Seen("deal",deal))return false;
      if(!Accept("deal",deal))return false;
      for(int i=0;i<m_slots;i++)if(Read("pending",i)==deal)Write("pending",i,0);
      return true;
     }
   bool Overflowed(){return GlobalVariableCheck(m_prefix+"overflow")&&GlobalVariableGet(m_prefix+"overflow")>0.5;}
   bool AcceptClosedPosition(const ulong position_id){return Accept("position",position_id);}
  };
'''


REMOTE_COMMAND_LEDGER = r'''// digits-tested: 5,4,3,2
#pragma once
enum VCKRemoteCommandState { VCK_CMD_IDLE=0,VCK_CMD_CLAIMED,VCK_CMD_DELETED,VCK_CMD_APPLYING,VCK_CMD_APPLIED,VCK_CMD_BLOCKED };
class CRemoteCommandLedger
  {
private:
   string m_prefix;
   string Key(const string suffix){return m_prefix+suffix;}
   void SaveTicket(const ulong value){GlobalVariableSet(Key("ticket_hi"),(double)(value>>32));GlobalVariableSet(Key("ticket_lo"),(double)(value&0xFFFFFFFF));}
   void Clear(){GlobalVariableDel(Key("ticket_hi"));GlobalVariableDel(Key("ticket_lo"));GlobalVariableDel(Key("command"));GlobalVariableSet(Key("state"),(double)VCK_CMD_IDLE);GlobalVariablesFlush();}
public:
   void Configure(const long magic,const string symbol){m_prefix="VCK_REMOTE_"+(string)magic+"_"+symbol+"_";if(!GlobalVariableCheck(Key("state")))GlobalVariableSet(Key("state"),(double)VCK_CMD_IDLE);}
   int State(){return GlobalVariableCheck(Key("state"))?(int)GlobalVariableGet(Key("state")):VCK_CMD_IDLE;}
   ulong Ticket(){ulong hi=GlobalVariableCheck(Key("ticket_hi"))?(ulong)GlobalVariableGet(Key("ticket_hi")):0,lo=GlobalVariableCheck(Key("ticket_lo"))?(ulong)GlobalVariableGet(Key("ticket_lo")):0;return(hi<<32)|lo;}
   int CommandIndex(){return GlobalVariableCheck(Key("command"))?(int)GlobalVariableGet(Key("command")):-1;}
   bool Claim(const ulong ticket,const int command_index){string state=Key("state");if(!GlobalVariableSetOnCondition(state,(double)VCK_CMD_CLAIMED,(double)VCK_CMD_IDLE))return false;SaveTicket(ticket);GlobalVariableSet(Key("command"),(double)command_index);GlobalVariablesFlush();return true;}
   bool MarkDeleted(const ulong ticket,const int command_index){if(State()!=VCK_CMD_CLAIMED||Ticket()!=ticket||CommandIndex()!=command_index)return false;GlobalVariableSet(Key("state"),(double)VCK_CMD_DELETED);GlobalVariablesFlush();return true;}
   bool BeginApply(const ulong ticket,const int command_index){if(Ticket()!=ticket||CommandIndex()!=command_index||!GlobalVariableSetOnCondition(Key("state"),(double)VCK_CMD_APPLYING,(double)VCK_CMD_DELETED))return false;GlobalVariablesFlush();return true;}
   void MarkApplied(const ulong ticket,const int command_index){if(State()==VCK_CMD_APPLYING&&Ticket()==ticket&&CommandIndex()==command_index){GlobalVariableSet(Key("state"),(double)VCK_CMD_APPLIED);GlobalVariablesFlush();}}
   void FinalizeApplied(){if(State()==VCK_CMD_APPLIED)Clear();}
   void Block(){GlobalVariableSet(Key("state"),(double)VCK_CMD_BLOCKED);GlobalVariablesFlush();}
  };
'''


TRADE_EXECUTOR = r'''// digits-tested: 5,4,3,2
#pragma once
#include <Trade/Trade.mqh>
#include "TradeIntentLedger.mqh"
#include "../Risk/GridRiskGuard.mqh"
#include "../Telemetry/MfeMaeLogger.mqh"
class CAsyncTradeExecutor
  {
private:
   CTrade m_trade;CSpreadGuard m_spread;CTradeIntentLedger m_intents;long m_magic,m_last_bars;bool m_async;
   bool OpenRetcodeAccepted(const uint code){return code==TRADE_RETCODE_DONE||code==TRADE_RETCODE_PLACED||code==TRADE_RETCODE_DONE_PARTIAL;}
   bool ModifyRetcodeAccepted(const uint code){return code==TRADE_RETCODE_DONE||code==TRADE_RETCODE_NO_CHANGES||(m_async&&code==TRADE_RETCODE_PLACED);}
   bool CloseRetcodeAccepted(const uint code){return code==TRADE_RETCODE_DONE||code==TRADE_RETCODE_DONE_PARTIAL||(m_async&&code==TRADE_RETCODE_PLACED);}
   bool DeleteRetcodeAccepted(const uint code){return code==TRADE_RETCODE_DONE||(m_async&&code==TRADE_RETCODE_PLACED);}
   bool OpenDefinitelyRejected(const uint code){return code==TRADE_RETCODE_REJECT||code==TRADE_RETCODE_INVALID||code==TRADE_RETCODE_INVALID_VOLUME||code==TRADE_RETCODE_INVALID_PRICE||code==TRADE_RETCODE_INVALID_STOPS||code==TRADE_RETCODE_TRADE_DISABLED||code==TRADE_RETCODE_MARKET_CLOSED||code==TRADE_RETCODE_NO_MONEY||code==TRADE_RETCODE_INVALID_FILL||code==TRADE_RETCODE_INVALID_ORDER;}
public:
   void Configure(const long magic,const string symbol,const ENUM_TIMEFRAMES tf,const double max_spread,const bool async_mode){m_magic=magic;m_last_bars=Bars(symbol,tf);m_async=async_mode;m_spread.Configure(symbol,max_spread);m_trade.SetExpertMagicNumber((ulong)magic);m_trade.SetAsyncMode(async_mode);m_intents.Configure(magic,symbol,InpIntentUnknownTimeoutSeconds,InpIntentHistoryLookbackSeconds);}
   void Reconcile(){if(VCK_RECONCILE_BEFORE_RETRY)m_intents.Reconcile();}
   bool TransactionRetcodeAccepted(const ENUM_TRADE_REQUEST_ACTIONS action,const uint code){if(action==TRADE_ACTION_SLTP||action==TRADE_ACTION_MODIFY)return ModifyRetcodeAccepted(code);if(action==TRADE_ACTION_REMOVE)return DeleteRetcodeAccepted(code);if(action==TRADE_ACTION_CLOSE_BY)return CloseRetcodeAccepted(code);return OpenRetcodeAccepted(code);}
   void ObserveDealDiagnostic(const ulong deal){if(deal>0&&HistoryDealSelect(deal)){string comment=HistoryDealGetString(deal,DEAL_COMMENT);if(StringLen(comment)>0)m_intents.ObserveDiagnosticComment(comment);}}
   void OnTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result){m_intents.OnTransaction(trans,result);if(trans.order>0&&OrderSelect(trans.order)){string comment=OrderGetString(ORDER_COMMENT);if(StringLen(comment)>0)m_intents.ObserveDiagnosticComment(comment);}if(trans.deal>0)ObserveDealDiagnostic(trans.deal);}
   double NormalizeVolume(const string symbol,const double requested,const double maximum){double step=SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP),lo=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN),hi=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);if(step<=0)step=0.01;if(lo<=0)lo=step;if(hi<=0)hi=maximum;hi=MathMin(hi,maximum);if(hi<lo||requested<lo)return 0;double v=MathMin(requested,hi);return NormalizeDouble(MathFloor(v/step+1e-8)*step,8);}
   bool MarginAvailable(const ENUM_ORDER_TYPE type,const string symbol,const double volume){MqlTick t;if(!SymbolInfoTick(symbol,t))return false;double m=0,p=type==ORDER_TYPE_BUY?t.ask:t.bid;return OrderCalcMargin(type,symbol,volume,p,m)&&m<=AccountInfoDouble(ACCOUNT_MARGIN_FREE);}
   bool Open(const int direction,const string symbol,const double requested,const double maximum,const double sl_requested,const double tp_requested,const string comment,const int source){long bars=Bars(symbol,PERIOD_CURRENT);if(bars<=0||!m_spread.Allowed())return false;m_last_bars=bars;ENUM_ORDER_TYPE type=direction>0?ORDER_TYPE_BUY:ORDER_TYPE_SELL;double volume=NormalizeVolume(symbol,requested,maximum);if(volume<=0||!MarginAvailable(type,symbol,volume))return false;MqlTick tick;if(!SymbolInfoTick(symbol,tick))return false;double price=direction>0?tick.ask:tick.bid,point=SymbolInfoDouble(symbol,SYMBOL_POINT),sl=sl_requested,tp=tp_requested;int digits=(int)SymbolInfoInteger(symbol,SYMBOL_DIGITS),stops=(int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);double min_dist=MathMax(0,stops)*point;if(sl>0&&MathAbs(price-sl)<min_dist)sl=NormalizeDouble(price-direction*min_dist,digits);if(tp>0&&MathAbs(tp-price)<min_dist)tp=NormalizeDouble(price+direction*min_dist,digits);bool tracked=VCK_RECONCILE_BEFORE_RETRY;string wire_comment=comment;if(tracked&&!m_intents.Prepare(source,direction,comment,wire_comment))return false;m_trade.SetExpertMagicNumber((ulong)m_magic);m_trade.SetTypeFillingBySymbol(symbol);bool submitted=direction>0?m_trade.Buy(volume,symbol,0,sl,tp,wire_comment):m_trade.Sell(volume,symbol,0,sl,tp,wire_comment);MqlTradeResult submit_result;ZeroMemory(submit_result);m_trade.Result(submit_result);if(!submitted){if(tracked){if(OpenDefinitelyRejected(submit_result.retcode))m_intents.MarkRejected(source,direction);else m_intents.MarkUnknown(source,direction,submit_result);}return false;}if(OpenRetcodeAccepted(submit_result.retcode)){if(tracked)m_intents.MarkSubmitted(source,direction,submit_result,volume);return true;}if(tracked)m_intents.MarkUnknown(source,direction,submit_result);return false;}
   bool Modify(const ulong ticket,const double sl,const double tp){if(!m_trade.PositionModify(ticket,sl,tp))return false;return ModifyRetcodeAccepted(m_trade.ResultRetcode());}
   bool Close(const ulong ticket){if(!m_trade.PositionClose(ticket))return false;return CloseRetcodeAccepted(m_trade.ResultRetcode());}
   bool ClosePartial(const ulong ticket,const double volume){if(!m_trade.PositionClosePartial(ticket,volume))return false;return CloseRetcodeAccepted(m_trade.ResultRetcode());}
   bool DeleteOrder(const ulong ticket){if(!m_trade.OrderDelete(ticket))return false;return DeleteRetcodeAccepted(m_trade.ResultRetcode());}
  };
'''

POSITION_BOOK = r'''// digits-tested: 5,4,3,2
#pragma once
struct VCKSideStats { int count; double lots,weighted_price,average_price,profit,newest_price,oldest_profit,oldest_volume,best_profit,best_volume; datetime newest_time,oldest_time; ulong oldest_ticket,oldest_identifier,best_ticket; };
class CVCKPositionBook
  {
public:
   void Collect(const string symbol,const long magic,const ENUM_POSITION_TYPE side,VCKSideStats &s)
     { ZeroMemory(s); s.best_profit=-DBL_MAX; for(int i=0;i<PositionsTotal();i++){ ulong t=PositionGetTicket(i); if(t==0||!PositionSelectByTicket(t))continue; if(PositionGetString(POSITION_SYMBOL)!=symbol||(long)PositionGetInteger(POSITION_MAGIC)!=magic||(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)!=side)continue; double v=PositionGetDouble(POSITION_VOLUME),p=PositionGetDouble(POSITION_PRICE_OPEN),pr=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP); datetime tm=(datetime)PositionGetInteger(POSITION_TIME); s.count++;s.lots+=v;s.weighted_price+=p*v;s.profit+=pr; if(tm>=s.newest_time){s.newest_time=tm;s.newest_price=p;} if(s.oldest_ticket==0||tm<s.oldest_time){s.oldest_ticket=t;s.oldest_identifier=(ulong)PositionGetInteger(POSITION_IDENTIFIER);s.oldest_time=tm;s.oldest_profit=pr;s.oldest_volume=v;} if(pr>s.best_profit){s.best_ticket=t;s.best_profit=pr;s.best_volume=v;} } if(s.lots>0)s.average_price=s.weighted_price/s.lots; }
   double Floating(const string symbol,const long magic)
     { double total=0; for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)==symbol&&(long)PositionGetInteger(POSITION_MAGIC)==magic)total+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);}return total;}
  };
'''


GRID_RISK_GUARD = r'''// digits-tested: 5,4,3,2
#pragma once
#include "../Config.mqh"
class CSpreadGuard
  {
private: string m_symbol; double m_max_pips;
public:
 void Configure(const string symbol,const double max_pips){m_symbol=symbol;m_max_pips=max_pips;}
 double Pip(){int d=(int)SymbolInfoInteger(m_symbol,SYMBOL_DIGITS);double p=SymbolInfoDouble(m_symbol,SYMBOL_POINT);return(d==3||d==5)?p*10.0:p;}
 bool Allowed(){MqlTick t;double pip=Pip();return SymbolInfoTick(m_symbol,t)&&pip>0&&(t.ask-t.bid)/pip<=m_max_pips;}
  };
class CGridRiskGuard
  {
private: double m_peak_equity;
public:
 void Init(const double persisted_peak=0){double now=AccountInfoDouble(ACCOUNT_EQUITY);m_peak_equity=MathMax(now,persisted_peak);}
 double Peak(){DD();return m_peak_equity;}
 double DD(){double e=AccountInfoDouble(ACCOUNT_EQUITY);m_peak_equity=MathMax(m_peak_equity,e);return m_peak_equity>0?(m_peak_equity-e)/m_peak_equity*100.0:0.0;}
 bool FreezeDD(){return InpFreezeDDPct>0&&DD()>=InpFreezeDDPct;}
 bool MustStop(){return InpMaxDDPct>0&&DD()>=InpMaxDDPct;}
 bool LevelAllowed(const int levels,const int MaxLevels){return levels<MaxLevels;}
  };
'''

STRUCTURED_LOGGER = r'''// digits-tested: 5,4,3,2
#pragma once
class CStructuredLogger
  {
private: string m_file;
public:
 void Configure(const string name){m_file=name+"-events.csv";}
 void Event(const string event,const string detail,const double value=0.0)
   {PrintFormat("VCK_EVENT|%s|%s|%.8f",event,detail,value);int h=FileOpen(m_file,FILE_COMMON|FILE_CSV|FILE_READ|FILE_WRITE|FILE_SHARE_READ,';');if(h!=INVALID_HANDLE){FileSeek(h,0,SEEK_END);FileWrite(h,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),event,detail,DoubleToString(value,8));FileClose(h);}}
  };
'''

PERSISTENT_STATE_STORE = r'''// digits-tested: 5,4,3,2
#pragma once
class CPersistentStateStore
  {
private:
 string m_prefix;
 string Key(const string suffix){return m_prefix+suffix;}
 void SaveUlong(const string suffix,const ulong value){GlobalVariableSet(Key(suffix+"_hi"),(double)(value>>32));GlobalVariableSet(Key(suffix+"_lo"),(double)(value&0xFFFFFFFF));}
 ulong LoadUlong(const string suffix){ulong hi=GlobalVariableCheck(Key(suffix+"_hi"))?(ulong)GlobalVariableGet(Key(suffix+"_hi")):0;ulong lo=GlobalVariableCheck(Key(suffix+"_lo"))?(ulong)GlobalVariableGet(Key(suffix+"_lo")):0;return (hi<<32)|lo;}
public:
 void Configure(const long magic,const string symbol){m_prefix="VCK_"+(string)magic+"_"+symbol+"_";}
 void Save(const bool enabled,const bool new_cycle,const bool stop_buy,const bool stop_sell,const double lottery)
   {GlobalVariableSet(Key("enabled"),enabled?1:0);GlobalVariableSet(Key("new_cycle"),new_cycle?1:0);GlobalVariableSet(Key("stop_buy"),stop_buy?1:0);GlobalVariableSet(Key("stop_sell"),stop_sell?1:0);GlobalVariableSet(Key("lottery"),lottery);}
 void Load(bool &enabled,bool &new_cycle,bool &stop_buy,bool &stop_sell,double &lottery)
   {if(GlobalVariableCheck(Key("enabled")))enabled=GlobalVariableGet(Key("enabled"))>0.5;if(GlobalVariableCheck(Key("new_cycle")))new_cycle=GlobalVariableGet(Key("new_cycle"))>0.5;if(GlobalVariableCheck(Key("stop_buy")))stop_buy=GlobalVariableGet(Key("stop_buy"))>0.5;if(GlobalVariableCheck(Key("stop_sell")))stop_sell=GlobalVariableGet(Key("stop_sell"))>0.5;if(GlobalVariableCheck(Key("lottery")))lottery=GlobalVariableGet(Key("lottery"));}
 void SaveExtended(const int halt_day,const int balance_day,const double day_balance,const double peak,const bool hedge_zone,const int zone_phase,const int zone_cycle_id,const ulong zone_anchor_position_id,const double zone_low,const double zone_high,const datetime cooldown)
   {GlobalVariableSet(Key("state_schema"),3.0);GlobalVariableSet(Key("halt_day"),(double)halt_day);GlobalVariableSet(Key("balance_day"),(double)balance_day);GlobalVariableSet(Key("day_balance"),day_balance);GlobalVariableSet(Key("peak_equity"),peak);GlobalVariableSet(Key("hedge_zone"),hedge_zone?1:0);GlobalVariableSet(Key("zone_phase"),(double)zone_phase);GlobalVariableSet(Key("zone_cycle_id"),(double)zone_cycle_id);SaveUlong("zone_anchor_position",zone_anchor_position_id);GlobalVariableSet(Key("zone_low"),zone_low);GlobalVariableSet(Key("zone_high"),zone_high);GlobalVariableSet(Key("cooldown"),(double)cooldown);}
 void LoadExtended(int &halt_day,int &balance_day,double &day_balance,double &peak,bool &hedge_zone,int &zone_phase,int &zone_cycle_id,ulong &zone_anchor_position_id,double &zone_low,double &zone_high,datetime &cooldown)
   {double schema=GlobalVariableCheck(Key("state_schema"))?GlobalVariableGet(Key("state_schema")):0;if(GlobalVariableCheck(Key("halt_day")))halt_day=(int)GlobalVariableGet(Key("halt_day"));if(GlobalVariableCheck(Key("balance_day")))balance_day=(int)GlobalVariableGet(Key("balance_day"));if(GlobalVariableCheck(Key("day_balance")))day_balance=GlobalVariableGet(Key("day_balance"));if(GlobalVariableCheck(Key("peak_equity")))peak=GlobalVariableGet(Key("peak_equity"));if(GlobalVariableCheck(Key("cooldown")))cooldown=(datetime)GlobalVariableGet(Key("cooldown"));if(schema>=3.0){if(GlobalVariableCheck(Key("hedge_zone")))hedge_zone=GlobalVariableGet(Key("hedge_zone"))>0.5;if(GlobalVariableCheck(Key("zone_phase")))zone_phase=(int)GlobalVariableGet(Key("zone_phase"));if(GlobalVariableCheck(Key("zone_cycle_id")))zone_cycle_id=(int)GlobalVariableGet(Key("zone_cycle_id"));zone_anchor_position_id=LoadUlong("zone_anchor_position");if(GlobalVariableCheck(Key("zone_low")))zone_low=GlobalVariableGet(Key("zone_low"));if(GlobalVariableCheck(Key("zone_high")))zone_high=GlobalVariableGet(Key("zone_high"));}else{hedge_zone=false;zone_phase=0;zone_cycle_id=0;zone_anchor_position_id=0;zone_low=0;zone_high=0;}}
  };
'''

MFE_MAE_LOGGER = r'''// digits-tested: 5,4,3,2
#pragma once
class CMfeMaeLogger
  {
private:
 string m_file;
 string Key(const ulong id,const string suffix){return "VCK_MFE_"+(string)id+"_"+suffix;}
public:
 void Configure(const string name){m_file=name+"-mfe-mae.csv";}
 void Sample(const string symbol,const long magic)
   {for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)!=symbol||(long)PositionGetInteger(POSITION_MAGIC)!=magic)continue;ulong id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);double p=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP),mfe=GlobalVariableCheck(Key(id,"mfe"))?GlobalVariableGet(Key(id,"mfe")):p,mae=GlobalVariableCheck(Key(id,"mae"))?GlobalVariableGet(Key(id,"mae")):p;GlobalVariableSet(Key(id,"mfe"),MathMax(mfe,p));GlobalVariableSet(Key(id,"mae"),MathMin(mae,p));}}
 void Finalize(const ulong id,const double realized)
   {double mfe=GlobalVariableCheck(Key(id,"mfe"))?GlobalVariableGet(Key(id,"mfe")):0,mae=GlobalVariableCheck(Key(id,"mae"))?GlobalVariableGet(Key(id,"mae")):0;int h=FileOpen(m_file,FILE_COMMON|FILE_CSV|FILE_READ|FILE_WRITE|FILE_SHARE_READ,';');if(h!=INVALID_HANDLE){FileSeek(h,0,SEEK_END);FileWrite(h,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),(string)id,DoubleToString(mfe,2),DoubleToString(mae,2),DoubleToString(realized,2));FileClose(h);}GlobalVariableDel(Key(id,"mfe"));GlobalVariableDel(Key(id,"mae"));}
  };
'''

BASKET_CLOSE_ENGINE = r'''// digits-tested: 5,4,3,2
#pragma once
class CBasketCloseEngine
  {
public:
 bool MoneyHit(const double profit,const double target,const double stop){return(target>0&&profit>=target)||(stop<0&&profit<=stop);}
 bool SidePipsHit(const int direction,const double current,const double average,const double target_pips,const double pip){if(target_pips<=0)return false;return direction>0?current>=average+target_pips*pip:current<=average-target_pips*pip;}
  };
'''

ENTRY_ENGINE = r'''// digits-tested: 5,4,3,2
#pragma once
#include "../Config.mqh"
class CVCKEntryEngine
  {
private:
 string m_symbol; ENUM_TIMEFRAMES m_tf; int h_rsi,h_cci,h_stoch,h_fast,h_slow,h_bands,h_macd,h_atr,h_supertrend,h_utbot,h_momentum,h_ichimoku,h_external;
 bool Value(const int h,const int b,const int shift,double &out){double v[];ArrayResize(v,1);if(h==INVALID_HANDLE||BarsCalculated(h)<=shift||CopyBuffer(h,b,shift,1,v)!=1)return false;out=v[0];return MathIsValidNumber(out);}
 bool Rates(const int shift,const int count,MqlRates &r[]){ArrayResize(r,count);ArraySetAsSeries(r,true);return CopyRates(m_symbol,m_tf,shift,count,r)==count;}
 double Pip(){int d=(int)SymbolInfoInteger(m_symbol,SYMBOL_DIGITS);double p=SymbolInfoDouble(m_symbol,SYMBOL_POINT);return(d==3||d==5)?p*10.0:p;}
 double Highest(const MqlRates &r[],const int start,const int count){double x=-DBL_MAX;for(int i=start;i<start+count;i++)x=MathMax(x,r[i].high);return x;}
 double Lowest(const MqlRates &r[],const int start,const int count){double x=DBL_MAX;for(int i=start;i<start+count;i++)x=MathMin(x,r[i].low);return x;}
 int CandleColor(){MqlRates r[];if(!Rates(1,1,r))return 0;return r[0].close>r[0].open?1:(r[0].close<r[0].open?-1:0);}
 int Pinbar(){MqlRates r[];if(!Rates(1,1,r))return 0;double body=MathMax(MathAbs(r[0].close-r[0].open),_Point),up=r[0].high-MathMax(r[0].open,r[0].close),dn=MathMin(r[0].open,r[0].close)-r[0].low,range=(r[0].high-r[0].low);if(range<InpMinCandlePips*Pip())return 0;if(dn>=InpPinbarWickRatio*body&&dn>=InpPinbarOppositeRatio*up)return 1;if(up>=InpPinbarWickRatio*body&&up>=InpPinbarOppositeRatio*dn)return -1;return 0;}
 int Engulfing(){MqlRates r[];if(!Rates(1,2,r))return 0;bool bull=InpEngulfFullWick?(r[0].low<=r[1].low&&r[0].high>=r[1].high):(r[1].close<r[1].open&&r[0].close>r[0].open&&r[0].open<=r[1].close&&r[0].close>=r[1].open);bool bear=InpEngulfFullWick?(r[0].high>=r[1].high&&r[0].low<=r[1].low&&r[0].close<r[0].open):(r[1].close>r[1].open&&r[0].close<r[0].open&&r[0].open>=r[1].close&&r[0].close<=r[1].open);return bull?1:(bear?-1:0);}
 int Structure(const int lookback,const bool against){MqlRates r[];if(!Rates(1,lookback+2,r))return 0;double hi=Highest(r,1,lookback),lo=Lowest(r,1,lookback);int d=r[0].close>hi?1:(r[0].close<lo?-1:0);return against?-d:d;}
public:
 CVCKEntryEngine():h_rsi(INVALID_HANDLE),h_cci(INVALID_HANDLE),h_stoch(INVALID_HANDLE),h_fast(INVALID_HANDLE),h_slow(INVALID_HANDLE),h_bands(INVALID_HANDLE),h_macd(INVALID_HANDLE),h_atr(INVALID_HANDLE),h_supertrend(INVALID_HANDLE),h_utbot(INVALID_HANDLE),h_momentum(INVALID_HANDLE),h_ichimoku(INVALID_HANDLE),h_external(INVALID_HANDLE){}
 bool Init(const string symbol,const ENUM_TIMEFRAMES tf){m_symbol=symbol;m_tf=tf;h_rsi=iRSI(symbol,tf,InpRSIPeriod,PRICE_CLOSE);h_cci=iCCI(symbol,tf,InpCCIPeriod,PRICE_CLOSE);h_stoch=iStochastic(symbol,tf,InpStochK,InpStochD,InpStochSlowing,MODE_SMA,STO_LOWHIGH);h_fast=iMA(symbol,tf,InpEMAFast,0,MODE_EMA,PRICE_CLOSE);h_slow=iMA(symbol,tf,InpEMASlow,0,MODE_EMA,PRICE_CLOSE);h_bands=iBands(symbol,tf,InpBBPeriod,0,InpBBDeviation,PRICE_CLOSE);h_macd=iMACD(symbol,tf,12,26,9,PRICE_CLOSE);h_atr=iATR(symbol,tf,InpATRPeriod);h_supertrend=iATR(symbol,tf,InpSupertrendPeriod);h_utbot=iATR(symbol,tf,InpUTBotPeriod);h_momentum=iMomentum(symbol,tf,InpMomentumPeriod,PRICE_CLOSE);h_ichimoku=iIchimoku(symbol,tf,InpIchimokuTenkan,InpIchimokuKijun,InpIchimokuSenkou);if(StringLen(InpExternalIndicator)>0)h_external=iCustom(symbol,tf,InpExternalIndicator);return ReadyHandles();}
 void Release(){int a[]={h_rsi,h_cci,h_stoch,h_fast,h_slow,h_bands,h_macd,h_atr,h_supertrend,h_utbot,h_momentum,h_ichimoku,h_external};for(int i=0;i<ArraySize(a);i++)if(a[i]!=INVALID_HANDLE)IndicatorRelease(a[i]);}
 bool ReadyHandles(){int a[]={h_rsi,h_cci,h_stoch,h_fast,h_slow,h_bands,h_macd,h_atr,h_supertrend,h_utbot,h_momentum,h_ichimoku};for(int i=0;i<ArraySize(a);i++)if(a[i]==INVALID_HANDLE)return false;return true;}
 bool EMAFilterAllow(const int direction){if(!InpUseEMAFilter&&InpEMAMaxPriceDistancePips<=0&&InpEMAMinSeparationPips<=0)return true;double fast,slow;MqlRates rate[];if(!Value(h_fast,0,1,fast)||!Value(h_slow,0,1,slow)||!Rates(0,1,rate))return false;if(InpUseEMAFilter&&direction>0&&fast<=slow)return false;if(InpUseEMAFilter&&direction<0&&fast>=slow)return false;double pip=Pip();if(InpEMAMaxPriceDistancePips>0&&MathAbs(rate[0].close-fast)/pip>InpEMAMaxPriceDistancePips)return false;if(InpEMAMinSeparationPips>0&&MathAbs(fast-slow)/pip<InpEMAMinSeparationPips)return false;return true;}
 bool MACDFilterAllow(const int direction){if(!InpUseMACDFilter)return true;double main,signal;if(!Value(h_macd,0,1,main)||!Value(h_macd,1,1,signal))return false;return direction>0?main>signal:main<signal;}
 bool RSIFilterAllow(const int direction){if(!InpUseRSIFilter)return true;double value;if(!Value(h_rsi,0,1,value))return false;return direction>0?value>=50:value<=50;}
 bool FiltersAllow(const int direction){return EMAFilterAllow(direction)&&MACDFilterAllow(direction)&&RSIFilterAllow(direction);}
 int SignalRSI(){double a;if(!Value(h_rsi,0,1,a))return 0;return a<=InpRSIOversold?1:(a>=InpRSIOverbought?-1:0);}
 int SignalRSIReversal(){double a,b;if(!Value(h_rsi,0,2,a)||!Value(h_rsi,0,1,b))return 0;return a<=InpRSIOversold&&b>InpRSIOversold?1:(a>=InpRSIOverbought&&b<InpRSIOverbought?-1:0);}
 int SignalCCIReversal(){double a,b;if(!Value(h_cci,0,2,a)||!Value(h_cci,0,1,b))return 0;return a<=InpCCIOversold&&b>InpCCIOversold?1:(a>=InpCCIOverbought&&b<InpCCIOverbought?-1:0);}
 int SignalStochastic(){double a,b,c,d;if(!Value(h_stoch,0,2,a)||!Value(h_stoch,1,2,b)||!Value(h_stoch,0,1,c)||!Value(h_stoch,1,1,d))return 0;if(a<=b&&c>d&&c<20)return 1;if(a>=b&&c<d&&c>80)return -1;return 0;}
 int SignalEMACross(){double a,b,c,d;if(!Value(h_fast,0,2,a)||!Value(h_slow,0,2,b)||!Value(h_fast,0,1,c)||!Value(h_slow,0,1,d))return 0;return a<=b&&c>d?1:(a>=b&&c<d?-1:0);}
 int SignalBands(){double lower_prev,lower_now,upper_prev,upper_now;MqlRates r[];if(!Value(h_bands,2,2,lower_prev)||!Value(h_bands,2,1,lower_now)||!Value(h_bands,1,2,upper_prev)||!Value(h_bands,1,1,upper_now)||!Rates(1,2,r))return 0;if(r[1].close<lower_prev&&r[0].close>lower_now)return 1;if(r[1].close>upper_prev&&r[0].close<upper_now)return -1;return 0;}
 int SignalMACD(){double a,b,c,d;if(!Value(h_macd,0,2,a)||!Value(h_macd,1,2,b)||!Value(h_macd,0,1,c)||!Value(h_macd,1,1,d))return 0;return a<=b&&c>d?1:(a>=b&&c<d?-1:0);}
 int SignalMomentum(){double a;if(!Value(h_momentum,0,1,a))return 0;return a>=InpMomentumBuyLevel?1:(a<=InpMomentumSellLevel?-1:0);}
 int SignalATRBreak(){double atr;MqlRates r[];if(!Value(h_atr,0,1,atr)||!Rates(1,2,r))return 0;if(r[0].close>r[1].high+InpATRBreakMultiplier*atr)return 1;if(r[0].close<r[1].low-InpATRBreakMultiplier*atr)return -1;return 0;}
 int SignalSupertrend(){double atr;MqlRates r[];if(!Value(h_supertrend,0,1,atr)||!Rates(1,2,r))return 0;double mid=(r[0].high+r[0].low)/2;return r[0].close>mid-InpSupertrendMultiplier*atr?1:-1;}
 int SignalUTBot(){double atr;MqlRates r[];if(!Value(h_utbot,0,1,atr)||!Rates(1,2,r))return 0;if(r[0].close>r[1].close+InpUTBotSensitivity*atr)return 1;if(r[0].close<r[1].close-InpUTBotSensitivity*atr)return -1;return 0;}
 int SignalIchimoku(){double a,b;MqlRates r[];if(!Value(h_ichimoku,2,1,a)||!Value(h_ichimoku,3,1,b)||!Rates(1,1,r))return 0;double top=MathMax(a,b),bottom=MathMin(a,b);return r[0].close>top?1:(r[0].close<bottom?-1:0);}
 int SignalExternal(){double a,b;if(h_external==INVALID_HANDLE)return 0;if(Value(h_external,InpExternalBuyBuffer,1,a)&&a!=0&&a!=EMPTY_VALUE)return 1;if(Value(h_external,InpExternalSellBuffer,1,b)&&b!=0&&b!=EMPTY_VALUE)return -1;return 0;}
 int OscillatorDirection(){switch(InpSignalMode){case VCK_SIGNAL_RSI:return SignalRSI();case VCK_SIGNAL_RSI_REVERSAL:return SignalRSIReversal();case VCK_SIGNAL_CCI_REVERSAL:return SignalCCIReversal();case VCK_SIGNAL_STOCH_REVERSAL:return SignalStochastic();default:return 0;}}
 int ClassicDirection(){switch(InpSignalMode){case VCK_SIGNAL_EMA_CROSS:return SignalEMACross();case VCK_SIGNAL_BB_REVERSION:return SignalBands();case VCK_SIGNAL_PINBAR:return Pinbar();case VCK_SIGNAL_ENGULFING:return Engulfing();case VCK_SIGNAL_PINBAR_ENGULFING:{int x=Pinbar();return x!=0?x:Engulfing();}case VCK_SIGNAL_MACD_CROSS:return SignalMACD();default:return 0;}}
 int TrendDirection(){switch(InpSignalMode){case VCK_SIGNAL_MOMENTUM:return SignalMomentum();case VCK_SIGNAL_ATR_BREAKOUT:return SignalATRBreak();case VCK_SIGNAL_SUPERTREND:return SignalSupertrend();case VCK_SIGNAL_UTBOT:return SignalUTBot();case VCK_SIGNAL_ICHIMOKU_BREAK:return SignalIchimoku();default:return 0;}}
 int SMCDirection(){switch(InpSignalMode){case VCK_SIGNAL_SMC_ALL_WITH:return Structure(InpSMCSwingLookback,false);case VCK_SIGNAL_SMC_ALL_AGAINST:return Structure(InpSMCSwingLookback,true);case VCK_SIGNAL_SMC_INTERNAL_WITH:return Structure(InpSMCInternalLookback,false);case VCK_SIGNAL_SMC_INTERNAL_AGAINST:return Structure(InpSMCInternalLookback,true);case VCK_SIGNAL_SMC_SWING_WITH:return Structure(InpSMCSwingLookback,false);case VCK_SIGNAL_SMC_SWING_AGAINST:return Structure(InpSMCSwingLookback,true);default:return 0;}}
 int SpecialDirection(){switch(InpSignalMode){case VCK_SIGNAL_CANDLE_COLOR:return CandleColor();case VCK_SIGNAL_NO_CONDITION:return InpUnconditionalDirection>=0?1:-1;case VCK_SIGNAL_RANDOM:return MathRand()%2==0?1:-1;case VCK_SIGNAL_EXTERNAL:return SignalExternal();default:return 0;}}
 int Direction(){int mode=(int)InpSignalMode;if(mode>=VCK_SIGNAL_RSI&&mode<=VCK_SIGNAL_STOCH_REVERSAL)return OscillatorDirection();if(mode>=VCK_SIGNAL_EMA_CROSS&&mode<=VCK_SIGNAL_MACD_CROSS)return ClassicDirection();if(mode>=VCK_SIGNAL_MOMENTUM&&mode<=VCK_SIGNAL_ICHIMOKU_BREAK)return TrendDirection();if(mode>=VCK_SIGNAL_SMC_ALL_WITH&&mode<=VCK_SIGNAL_SMC_SWING_AGAINST)return SMCDirection();return SpecialDirection();}
  };
'''

# This main intentionally keeps policies explicit and auditable rather than
# hiding them behind vendor-specific names.
MAIN_TEMPLATE = r'''// digits-tested: 5,4,3,2
//+------------------------------------------------------------------+
//| __NAME__.mq5 | EA-IR __HASH__
//+------------------------------------------------------------------+
#property strict
#property version "3.30"
#include <__NAME__/Config.mqh>
#include <__NAME__/Core/AsyncTradeExecutor.mqh>
#include <__NAME__/Core/PositionBook.mqh>
#include <__NAME__/Core/TradeEventReducer.mqh>
#include <__NAME__/Core/RemoteCommandLedger.mqh>
#include <__NAME__/Signal/EntryEngine.mqh>
#include <__NAME__/Risk/GridRiskGuard.mqh>
#include <__NAME__/Exit/BasketCloseEngine.mqh>
#include <__NAME__/State/PersistentStateStore.mqh>
#include <__NAME__/Telemetry/StructuredLogger.mqh>
#include <__NAME__/Telemetry/MfeMaeLogger.mqh>
enum VCKLifecycleState { VCK_IDLE,VCK_ACTIVE_CYCLE,VCK_DCA_ACTIVE,VCK_HEDGE_ACTIVE,VCK_HEDGE_ZONE_ACTIVE,VCK_CLOSING,VCK_COOLDOWN,VCK_STOPPED };
enum VCKExposureSource { VCK_SRC_ENTRY,VCK_SRC_DCA,VCK_SRC_HEDGE,VCK_SRC_HEDGE_ZONE,VCK_SRC_REVERSE,VCK_SRC_BALANCE };
enum VCKZonePhase { VCK_ZONE_IDLE,VCK_ZONE_ACTIVE,VCK_ZONE_EXITING,VCK_ZONE_RECONCILING };
CAsyncTradeExecutor Trade; CTradeEventReducer EventReducer; CRemoteCommandLedger CommandLedger; CVCKPositionBook Book; CVCKEntryEngine Entry; CGridRiskGuard GridRisk; CBasketCloseEngine Basket; CPersistentStateStore StateStore; CStructuredLogger Log; CMfeMaeLogger MfeMae;
VCKLifecycleState g_state=VCK_IDLE; int g_zone_phase=VCK_ZONE_IDLE; string g_symbol=""; double g_pip=0; bool g_ea_enabled=true,g_new_cycle=true,g_stop_buy=false,g_stop_sell=false,g_hedge_zone=false,g_daily_history_ready=true; datetime g_last_entry=0,g_last_balance=0,g_last_clear=0,g_last_dca_bar=0,g_cooldown_until=0; double g_lottery_factor=1,g_buy_reset_lot=0,g_sell_reset_lot=0,g_zone_low=0,g_zone_high=0,g_day_start_balance=0,g_persisted_peak=0; int g_daily_halt_day=0,g_balance_day=0,g_zone_cycle_id=0,g_history_sync_confirmations=0; ulong g_zone_anchor_position_id=0;
const string VCKP_PREFIX="VCKP_"; bool g_close_armed=false; datetime g_close_armed_at=0;
void PersistState(){StateStore.Save(g_ea_enabled,g_new_cycle,g_stop_buy,g_stop_sell,g_lottery_factor);StateStore.SaveExtended(g_daily_halt_day,g_balance_day,g_day_start_balance,GridRisk.Peak(),g_hedge_zone,g_zone_phase,g_zone_cycle_id,g_zone_anchor_position_id,g_zone_low,g_zone_high,g_cooldown_until);}
void PersistStateCritical(){PersistState();GlobalVariablesFlush();}

double PipSize(){int d=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);double p=SymbolInfoDouble(g_symbol,SYMBOL_POINT);return(d==3||d==5)?p*10:p;}
datetime ClockNow(const VCKTimeBasis basis){if(basis==VCK_TIME_LOCAL)return TimeLocal();if(basis==VCK_TIME_UTC)return TimeGMT();if(basis==VCK_TIME_FIXED_OFFSET)return TimeGMT()+VCK_UTC_OFFSET_MINUTES*60;return TimeCurrent();}
int DayKey(datetime when){MqlDateTime x;TimeToStruct(when,x);return x.year*10000+x.mon*100+x.day;}
datetime TradingDayStart(){datetime shifted=ClockNow(VCK_DAILY_TIME_BASIS)-VCK_DAY_BOUNDARY_MINUTES*60;MqlDateTime x;TimeToStruct(shifted,x);x.hour=0;x.min=0;x.sec=0;return StructToTime(x)+VCK_DAY_BOUNDARY_MINUTES*60;}
int CurrentTradingDayKey(){return DayKey(ClockNow(VCK_DAILY_TIME_BASIS)-VCK_DAY_BOUNDARY_MINUTES*60);}
bool EntryDelayPassed(){return g_last_entry==0||TimeCurrent()-g_last_entry>=InpMinSecondsBetweenEntries;}
bool NewBar(datetime &last){datetime t=iTime(g_symbol,InpSignalTimeframe,0);if(t==0||t==last)return false;last=t;return true;}
int HHMM(const string value){int p=StringFind(value,":");if(p<0)return -1;return (int)StringToInteger(StringSubstr(value,0,p))*60+(int)StringToInteger(StringSubstr(value,p+1));}
bool InWindow(const string start,const string finish){MqlDateTime x;TimeToStruct(ClockNow(VCK_SESSION_TIME_BASIS),x);int n=x.hour*60+x.min,a=HHMM(start),b=HHMM(finish);if(a<0||b<0)return false;if(a==b)return true;return a<b?(n>=a&&n<=b):(n>=a||n<=b);}
bool SessionAllowed(){if(!VCK_USE_SESSIONS)return true;return(InpSession1Enabled&&InWindow(InpSession1Start,InpSession1End))||(InpSession2Enabled&&InWindow(InpSession2Start,InpSession2End))||(InpSession3Enabled&&InWindow(InpSession3Start,InpSession3End))||(InpSession4Enabled&&InWindow(InpSession4Start,InpSession4End));}

double StageMultiplier(const int count){double m=InpLotMultiplier;if(InpLotStage1Count>0&&count>=InpLotStage1Count)m=InpLotStage1Multiplier;if(InpLotStage2Count>0&&count>=InpLotStage2Count)m=InpLotStage2Multiplier;if(InpLotStage3Count>0&&count>=InpLotStage3Count)m=InpLotStage3Multiplier;if(InpLotStage4Count>0&&count>=InpLotStage4Count)m=InpLotStage4Multiplier;if(InpLotStage5Count>0&&count>=InpLotStage5Count)m=InpLotStage5Multiplier;return m;}
double StageDistance(const int count){double p=InpDCAStepPips;if(InpDistanceStage1Count>0&&count>=InpDistanceStage1Count)p=InpDistanceStage1Pips;if(InpDistanceStage2Count>0&&count>=InpDistanceStage2Count)p=InpDistanceStage2Pips;if(InpDistanceStage3Count>0&&count>=InpDistanceStage3Count)p=InpDistanceStage3Pips;if(InpDistanceStage4Count>0&&count>=InpDistanceStage4Count)p=InpDistanceStage4Pips;return p;}
double NextLot(const int direction,const int count){double base=direction>0&&g_buy_reset_lot>0?g_buy_reset_lot:(direction<0&&g_sell_reset_lot>0?g_sell_reset_lot:InpBaseLot),lot=base;if(InpLotMode==VCK_LOT_MULTIPLY){double mult=((direction>0&&g_buy_reset_lot>0)||(direction<0&&g_sell_reset_lot>0))?InpResetMultiplier:StageMultiplier(count);lot=base*MathPow(mult,count);}else lot=base+InpLotAdditive*count;lot*=g_lottery_factor;return Trade.NormalizeVolume(g_symbol,lot,InpMaxLot);}
VCKDCAMode ActiveDCAMode(const int count){return InpDCASwitchCount>0&&count>=InpDCASwitchCount?InpDCASecondaryMode:InpDCAMode;}
double RequiredDistance(const int count){double p=StageDistance(count);if(ActiveDCAMode(count)==VCK_DCA_STEP_MULTIPLIER)p*=MathPow(InpDCAStepMultiplier,MathMax(count-1,0));return p*g_pip;}
bool SpreadAllowed(){MqlTick t;return SymbolInfoTick(g_symbol,t)&&(t.ask-t.bid)/g_pip<=InpMaxSpreadPips;}

bool ComputeDaySnapshot(const long magic_filter,double &trading_pnl,double &cashflow,double &day_start_balance){trading_pnl=0;cashflow=0;day_start_balance=0;if(!TerminalInfoInteger(TERMINAL_CONNECTED))return false;datetime from=TradingDayStart(),now=ClockNow(VCK_DAILY_TIME_BASIS);if(!HistorySelect(from,now))return false;double account_trading=0;for(int i=0;i<HistoryDealsTotal();i++){ulong d=HistoryDealGetTicket(i);if(d==0)continue;ENUM_DEAL_TYPE type=(ENUM_DEAL_TYPE)HistoryDealGetInteger(d,DEAL_TYPE);long magic=(long)HistoryDealGetInteger(d,DEAL_MAGIC);double value=HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_SWAP)+HistoryDealGetDouble(d,DEAL_COMMISSION);if(type==DEAL_TYPE_BUY||type==DEAL_TYPE_SELL){account_trading+=value;if(magic_filter<0||magic==magic_filter)trading_pnl+=value;}else cashflow+=value;}day_start_balance=AccountInfoDouble(ACCOUNT_BALANCE)-account_trading-cashflow;return true;}
double ClosedProfitToday(const long magic_filter){double trading=0,cashflow=0,baseline=0;if(!ComputeDaySnapshot(magic_filter,trading,cashflow,baseline))return 0;return trading+(VCK_EXCLUDE_CASHFLOWS?0:cashflow);}
double AccountFloating(){double x=0;for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t>0&&PositionSelectByTicket(t))x+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);}return x;}

int LiveDirectionCount(const int d){VCKSideStats s;Book.Collect(g_symbol,InpMagic,d>0?POSITION_TYPE_BUY:POSITION_TYPE_SELL,s);return s.count;}
bool HedgeZoneAllowsSource(const VCKExposureSource source){if(source==VCK_SRC_HEDGE_ZONE)return true;if(VCK_HEDGE_ZONE_EXCLUSIVE)return false;if(source==VCK_SRC_HEDGE)return VCK_HZ_ALLOW_HEDGE;if(source==VCK_SRC_REVERSE)return VCK_HZ_ALLOW_REVERSE;if(source==VCK_SRC_BALANCE)return VCK_HZ_ALLOW_BALANCE;return false;}
bool DirectionPermissionAllowed(const int d){if(d>0)return InpAllowBuy&&!g_stop_buy;if(d<0)return InpAllowSell&&!g_stop_sell;return false;}
bool SourceTimingAllowed(const VCKExposureSource source){if(source==VCK_SRC_ENTRY)return g_new_cycle&&SessionAllowed()&&TimeCurrent()>=g_cooldown_until;if(source==VCK_SRC_DCA)return SessionAllowed()||InpDCAOutsideSession;if(source==VCK_SRC_HEDGE||source==VCK_SRC_HEDGE_ZONE||source==VCK_SRC_REVERSE||source==VCK_SRC_BALANCE)return SessionAllowed()||VCK_RECOVERY_OUTSIDE_SESSION;return true;}
bool DirectionCapacityAllowed(const int d){int count=LiveDirectionCount(d);if(d>0)return count<InpMaxBuyPositions;if(d<0)return count<InpMaxSellPositions;return false;}
bool ExposureAllowed(const int d,const VCKExposureSource source){if(!g_ea_enabled||g_daily_halt_day==CurrentTradingDayKey())return false;if(!DirectionPermissionAllowed(d))return false;if(g_hedge_zone&&!HedgeZoneAllowsSource(source))return false;if(!SourceTimingAllowed(source))return false;return DirectionCapacityAllowed(d);}
bool OpenLeg(const int d,const double lot,const string comment,const VCKExposureSource source,const double custom_tp_pips=0){if(!ExposureAllowed(d,source))return false;MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;double price=d>0?t.ask:t.bid,sl=0,tp=0;int digits=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);if(InpSLPips>0)sl=NormalizeDouble(price-d*InpSLPips*g_pip,digits);double tp_pips=custom_tp_pips>0?custom_tp_pips:InpTPPips;if(tp_pips>0)tp=NormalizeDouble(price+d*tp_pips*g_pip,digits);if(Trade.Open(d,g_symbol,lot,InpMaxLot,sl,tp,comment,(int)source)){g_last_entry=TimeCurrent();return true;}return false;}
bool CloseTicket(const ulong t){return t>0&&Trade.Close(t);}
bool CloseMagicPositions(){g_state=VCK_CLOSING;bool acted=false;for(int i=PositionsTotal()-1;i>=0;i--){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)==g_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==InpMagic)acted=CloseTicket(t)||acted;}if(acted)g_last_clear=TimeCurrent();return acted;}
bool CloseAccountPositions(){if(!VCK_ACCOUNT_WIDE_APPROVED)return false;g_state=VCK_CLOSING;bool acted=false;for(int i=PositionsTotal()-1;i>=0;i--){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;acted=CloseTicket(t)||acted;}if(acted)g_last_clear=TimeCurrent();return acted;}
bool CloseSide(const ENUM_POSITION_TYPE side){bool acted=false;for(int i=PositionsTotal()-1;i>=0;i--){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)==g_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==InpMagic&&(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)==side)acted=CloseTicket(t)||acted;}return acted;}

double AdaptiveBasketPips(const VCKSideStats &s){if((g_buy_reset_lot>0||g_sell_reset_lot>0)&&InpResetBasketTPPips>0)return InpResetBasketTPPips;if(!VCK_USE_ADAPTIVE_TP||InpAdaptiveBasketTPPips<=0)return InpBasketTPPips;double bal=AccountInfoDouble(ACCOUNT_BALANCE),pct=bal>0?s.profit/bal*100:0;if((InpAdaptiveTPLossPct<0&&pct<=InpAdaptiveTPLossPct)||(InpAdaptiveTPLossMoney<0&&s.profit<=InpAdaptiveTPLossMoney))return InpAdaptiveBasketTPPips;return InpBasketTPPips;}
bool RefreshDailySnapshot(double &trading,double &cashflow,double &baseline){bool ok=ComputeDaySnapshot(InpMagic,trading,cashflow,baseline);g_history_sync_confirmations=ok?MathMin(g_history_sync_confirmations+1,2):0;g_daily_history_ready=ok&&(!VCK_HISTORY_SYNC_REQUIRED||g_history_sync_confirmations>=2);return g_daily_history_ready||!VCK_HISTORY_SYNC_REQUIRED;}
void UpdateTradingDay(const int key,const double baseline){if(g_balance_day!=key){g_balance_day=key;g_day_start_balance=g_daily_history_ready?baseline:AccountInfoDouble(ACCOUNT_BALANCE);if(g_daily_halt_day!=key)g_daily_halt_day=0;PersistStateCritical();return;}if(g_daily_history_ready&&baseline>0)g_day_start_balance=baseline;}
bool NewDayDelayActive(){if(g_daily_halt_day==0||InpNewDayDelayMinutes<=0)return false;return ClockNow(VCK_DAILY_TIME_BASIS)-TradingDayStart()<InpNewDayDelayMinutes*60;}
bool DailyThresholdHit(const double total,const double balance){if(InpDailyTargetMoney>0&&total>=InpDailyTargetMoney)return true;if(InpDailyLossMoney<0&&total<=InpDailyLossMoney)return true;if(InpDailyTargetPct>0&&balance>0&&total/balance*100>=InpDailyTargetPct)return true;if(InpDailyLossPct>0&&balance>0&&total/balance*100<=-InpDailyLossPct)return true;return false;}
bool DailyAllowed(){int key=CurrentTradingDayKey();double trading=0,cashflow=0,baseline=0;if(!RefreshDailySnapshot(trading,cashflow,baseline))return false;UpdateTradingDay(key,baseline);if(g_daily_halt_day==key||NewDayDelayActive())return false;double closed=trading+(VCK_EXCLUDE_CASHFLOWS?0:cashflow),total=closed+Book.Floating(g_symbol,InpMagic),balance=g_day_start_balance>0?g_day_start_balance:baseline;if(!DailyThresholdHit(total,balance))return true;g_daily_halt_day=key;PersistStateCritical();return false;}
bool ManageAccountMoneyExit(){if(!VCK_USE_ACCOUNT_MONEY_EXIT||!InpAllowAccountWideClose||!VCK_ACCOUNT_WIDE_APPROVED)return false;double profit=AccountFloating();if(!Basket.MoneyHit(profit,InpAccountTPMoney,InpAccountSLMoney))return false;Log.Event("ACCOUNT_EXIT","money threshold",profit);CloseAccountPositions();return true;}
bool ManageManagedMoneyExit(const double managed){if(!VCK_USE_MONEY_EXIT||!Basket.MoneyHit(managed,InpBasketTargetMoney,InpBasketStopMoney))return false;Log.Event("BASKET_EXIT","managed money threshold",managed);CloseMagicPositions();return true;}
bool ManageSideMoneyExits(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_SIDE_MONEY_EXIT)return false;bool acted=false;if(Basket.MoneyHit(buy.profit,InpBuyTPMoney,InpBuySLMoney))acted=CloseSide(POSITION_TYPE_BUY)||acted;if(Basket.MoneyHit(sell.profit,InpSellTPMoney,InpSellSLMoney))acted=CloseSide(POSITION_TYPE_SELL)||acted;return acted;}
bool ManageSteppedTarget(const double managed){if(!VCK_USE_STEPPED_TARGET||InpSteppedTargetMoney<=0)return false;if(ClosedProfitToday(InpMagic)+managed<InpSteppedTargetMoney)return false;CloseMagicPositions();g_cooldown_until=TimeCurrent()+InpSteppedTargetDelayMinutes*60;return true;}
bool ManageBalanceDifferenceExit(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_BALANCE_DIFFERENCE_EXIT||InpBalanceDifferencePct<=0||buy.count==0||sell.count==0)return false;double good=MathMax(buy.profit,sell.profit),bad=MathMin(buy.profit,sell.profit);if(good<=0||bad>=0||good+bad*(1+InpBalanceDifferencePct/100.0)<0)return false;CloseMagicPositions();return true;}
bool ManageGlobalExits(const VCKSideStats &buy,const VCKSideStats &sell){double managed=buy.profit+sell.profit;if(ManageAccountMoneyExit())return true;if(ManageManagedMoneyExit(managed))return true;if(ManageSideMoneyExits(buy,sell))return true;if(ManageSteppedTarget(managed))return true;return ManageBalanceDifferenceExit(buy,sell);}
bool ManageBasketExit(const VCKSideStats &buy,const VCKSideStats &sell){MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;if(VCK_USE_BASKET_TP){double bp=AdaptiveBasketPips(buy),sp=AdaptiveBasketPips(sell);if(buy.count>0&&Basket.SidePipsHit(1,t.bid,buy.average_price,bp,g_pip)){Log.Event("BUY_BASKET_TP","pips target",bp);CloseSide(POSITION_TYPE_BUY);return true;}if(sell.count>0&&Basket.SidePipsHit(-1,t.ask,sell.average_price,sp,g_pip)){Log.Event("SELL_BASKET_TP","pips target",sp);CloseSide(POSITION_TYPE_SELL);return true;}}if(VCK_USE_HEDGE&&buy.count>0&&sell.count>0&&InpHedgeExitMoney>0&&buy.profit+sell.profit>=InpHedgeExitMoney){CloseMagicPositions();return true;}return false;}
bool ManageTrailing(){if(!VCK_USE_TRAILING||InpTrailingStartPips<=0||InpTrailingDistancePips<=0)return false;MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;int digits=(int)SymbolInfoInteger(g_symbol,SYMBOL_DIGITS);bool acted=false;for(int i=PositionsTotal()-1;i>=0;i--){ulong ticket=PositionGetTicket(i);if(ticket==0||!PositionSelectByTicket(ticket))continue;if(PositionGetString(POSITION_SYMBOL)!=g_symbol||(long)PositionGetInteger(POSITION_MAGIC)!=InpMagic)continue;ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);double open=PositionGetDouble(POSITION_PRICE_OPEN),old=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP),current=type==POSITION_TYPE_BUY?t.bid:t.ask,gain=type==POSITION_TYPE_BUY?(current-open)/g_pip:(open-current)/g_pip;if(gain<InpTrailingStartPips)continue;double sl=NormalizeDouble(type==POSITION_TYPE_BUY?current-InpTrailingDistancePips*g_pip:current+InpTrailingDistancePips*g_pip,digits);if(type==POSITION_TYPE_BUY?(old==0||sl>old):(old==0||sl<old))acted=Trade.Modify(ticket,sl,tp)||acted;}return acted;}
bool ManageTrendReversal(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_TREND_REVERSAL_EXIT)return false;int d=Entry.Direction();if(d<0&&buy.count>0&&Entry.FiltersAllow(-1))return CloseSide(POSITION_TYPE_BUY);if(d>0&&sell.count>0&&Entry.FiltersAllow(1))return CloseSide(POSITION_TYPE_SELL);return false;}
bool ManageSniper(VCKSideStats &s){if(!VCK_USE_SNIPER||InpSniperHeadCount<1||InpSniperTailMaxCount<1||s.count<InpSniperTriggerPositions||s.oldest_ticket==0||s.best_ticket==0||s.oldest_ticket==s.best_ticket)return false;if(s.oldest_profit+s.best_profit<InpSniperTargetMoney)return false;bool acted=false;if(VCK_USE_PARTIAL_SNIPER){double v=Trade.NormalizeVolume(g_symbol,s.oldest_volume*InpPartialClosePct/100,s.oldest_volume),lo=SymbolInfoDouble(g_symbol,SYMBOL_VOLUME_MIN);if(v>=lo&&v<s.oldest_volume)acted=Trade.ClosePartial(s.oldest_ticket,v);}else acted=CloseTicket(s.oldest_ticket);if(acted)CloseTicket(s.best_ticket);return acted;}
bool ManageCrossChainSniper(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_CROSS_SNIPER||buy.count+sell.count<InpCrossSniperTriggerPositions)return false;if(!InpCrossSniperMagicPairOnly){ulong worst=0,best=0;double worstp=DBL_MAX,bestp=-DBL_MAX;for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;double p=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);if(p<worstp){worstp=p;worst=t;}if(p>bestp){bestp=p;best=t;}}if(worst>0&&best>0&&worst!=best&&worstp+bestp>=InpCrossSniperTargetMoney){bool acted=CloseTicket(worst);if(acted)CloseTicket(best);return acted;}return false;}VCKSideStats loser,winner;if(buy.profit<sell.profit){loser=buy;winner=sell;}else{loser=sell;winner=buy;}if(loser.oldest_ticket>0&&winner.best_ticket>0&&loser.oldest_profit+winner.best_profit>=InpCrossSniperTargetMoney){bool acted=CloseTicket(loser.oldest_ticket);if(acted)CloseTicket(winner.best_ticket);return acted;}return false;}

bool ManageHedge(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_HEDGE||!EntryDelayPassed())return false;double bal=AccountInfoDouble(ACCOUNT_BALANCE),buy_loss=bal>0?buy.profit/bal*100:0,sell_loss=bal>0?sell.profit/bal*100:0;bool hb=buy.count>=InpHedgeTriggerPositions||(InpHedgeTriggerLossPct<0&&buy_loss<=InpHedgeTriggerLossPct),hs=sell.count>=InpHedgeTriggerPositions||(InpHedgeTriggerLossPct<0&&sell_loss<=InpHedgeTriggerLossPct);if(hb&&sell.count==0){double v=InpHedgeUseDCALot?NextLot(-1,buy.count):buy.lots*InpHedgeLotPct/100;return OpenLeg(-1,MathMax(InpBaseLot,v),"VCK-HEDGE-SELL",VCK_SRC_HEDGE,InpHedgeTPPips);}if(hs&&buy.count==0){double v=InpHedgeUseDCALot?NextLot(1,sell.count):sell.lots*InpHedgeLotPct/100;return OpenLeg(1,MathMax(InpBaseLot,v),"VCK-HEDGE-BUY",VCK_SRC_HEDGE,InpHedgeTPPips);}return false;}
bool ManageReverseEntry(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_REVERSE_ENTRY||!EntryDelayPassed())return false;int d=Entry.Direction();if(buy.count>=InpReverseTriggerPositions&&sell.count==0&&d<0){double v=InpReverseLotPct>0?buy.lots*InpReverseLotPct/100:InpReverseFixedLot;return OpenLeg(-1,v,"VCK-REVERSE-SELL",VCK_SRC_REVERSE);}if(sell.count>=InpReverseTriggerPositions&&buy.count==0&&d>0){double v=InpReverseLotPct>0?sell.lots*InpReverseLotPct/100:InpReverseFixedLot;return OpenLeg(1,v,"VCK-REVERSE-BUY",VCK_SRC_REVERSE);}return false;}
bool ManageLotBalance(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_LOT_BALANCE||TimeCurrent()-g_last_balance<InpBalanceDelaySeconds)return false;double diff=buy.lots-sell.lots;if(MathAbs(diff)<InpBalanceTriggerLots||MathAbs(diff)<=InpBalanceStopLots)return false;if(OpenLeg(diff>0?-1:1,InpBalanceAddLot,"VCK-BALANCE",VCK_SRC_BALANCE)){g_last_balance=TimeCurrent();return true;}return false;}
bool ManagedPositionExists(const ulong ticket){return ticket>0&&PositionSelectByTicket(ticket)&&PositionGetString(POSITION_SYMBOL)==g_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==InpMagic;}
bool ManagedPositionIdentifierExists(const ulong position_id){for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)==g_symbol&&(long)PositionGetInteger(POSITION_MAGIC)==InpMagic&&(ulong)PositionGetInteger(POSITION_IDENTIFIER)==position_id)return true;}return false;}
bool PositionRealizedSummary(const ulong position_id,double &realized,ENUM_DEAL_REASON &reason){realized=0;reason=DEAL_REASON_CLIENT;datetime from=TimeCurrent()-InpIntentHistoryLookbackSeconds;if(!HistorySelect(from,TimeCurrent()))return false;bool found=false;for(int i=0;i<HistoryDealsTotal();i++){ulong d=HistoryDealGetTicket(i);if(d==0||(ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID)!=position_id)continue;ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(d,DEAL_ENTRY);if(entry!=DEAL_ENTRY_OUT&&entry!=DEAL_ENTRY_OUT_BY)continue;realized+=HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_SWAP)+HistoryDealGetDouble(d,DEAL_COMMISSION);reason=(ENUM_DEAL_REASON)HistoryDealGetInteger(d,DEAL_REASON);found=true;}return found;}
void ResetHedgeZoneState(const string reason){if(g_hedge_zone||g_zone_phase!=VCK_ZONE_IDLE)Log.Event("HEDGE_ZONE_RESET",reason);g_hedge_zone=false;g_zone_phase=VCK_ZONE_IDLE;g_zone_low=0;g_zone_high=0;g_zone_anchor_position_id=0;PersistStateCritical();}
void ReconcileHedgeZoneState(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_HEDGE_ZONE){if(g_hedge_zone)ResetHedgeZoneState("feature disabled");return;}int total=buy.count+sell.count;if(total==0){if(g_hedge_zone||g_zone_phase!=VCK_ZONE_IDLE)ResetHedgeZoneState("no managed positions");return;}if(!g_hedge_zone){if(g_zone_phase!=VCK_ZONE_IDLE)ResetHedgeZoneState("inactive flag mismatch");return;}if(g_zone_phase==VCK_ZONE_EXITING)return;bool invalid_bounds=g_zone_low<=0||g_zone_high<=g_zone_low;bool missing_anchor=g_zone_anchor_position_id>0&&!ManagedPositionIdentifierExists(g_zone_anchor_position_id);if(invalid_bounds||missing_anchor){g_zone_phase=VCK_ZONE_RECONCILING;double anchor=buy.count>=sell.count?buy.average_price:sell.average_price;g_zone_anchor_position_id=buy.count>=sell.count?buy.oldest_identifier:sell.oldest_identifier;g_zone_low=anchor-InpHedgeZoneDistancePips*g_pip;g_zone_high=anchor+InpHedgeZoneDistancePips*g_pip;g_zone_phase=VCK_ZONE_ACTIVE;Log.Event("HEDGE_ZONE_RECONCILE",missing_anchor?"anchor changed":"bounds rebuilt");PersistStateCritical();}}
bool ManageHedgeZone(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_HEDGE_ZONE)return false;int total=buy.count+sell.count;if(!g_hedge_zone&&MathMax(buy.count,sell.count)>=InpHedgeZoneTriggerPositions){g_hedge_zone=true;g_zone_phase=VCK_ZONE_ACTIVE;g_zone_cycle_id++;g_state=VCK_HEDGE_ZONE_ACTIVE;double anchor=buy.count>=sell.count?buy.average_price:sell.average_price;g_zone_anchor_position_id=buy.count>=sell.count?buy.oldest_identifier:sell.oldest_identifier;g_zone_low=anchor-InpHedgeZoneDistancePips*g_pip;g_zone_high=anchor+InpHedgeZoneDistancePips*g_pip;PersistStateCritical();}if(!g_hedge_zone||g_zone_phase==VCK_ZONE_EXITING)return false;double target=(InpHedgeZoneNewTargetCount>0&&total>=InpHedgeZoneNewTargetCount)?InpHedgeZoneNewTargetMoney:InpHedgeZoneTargetMoney;double pip_value=0,tick_value=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_VALUE),tick_size=SymbolInfoDouble(g_symbol,SYMBOL_TRADE_TICK_SIZE);if(tick_size>0)pip_value=tick_value*g_pip/tick_size;double pip_money=MathAbs(buy.lots-sell.lots)*InpHedgeZoneTargetPips*pip_value;if((target>0&&buy.profit+sell.profit>=target)||(target<=0&&InpHedgeZoneTargetPips>0&&buy.profit+sell.profit>=pip_money)){g_zone_phase=VCK_ZONE_EXITING;PersistStateCritical();return CloseMagicPositions();}if(!EntryDelayPassed())return false;MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;double lot=Trade.NormalizeVolume(g_symbol,MathMax(buy.lots,sell.lots)*InpHedgeZoneLotMultiplier,InpHedgeZoneMaxLot);if(lot<=0)return false;if(t.ask>=g_zone_high&&buy.lots<=sell.lots)return OpenLeg(1,lot,"VCK-HZ-BUY",VCK_SRC_HEDGE_ZONE);if(t.bid<=g_zone_low&&sell.lots<=buy.lots)return OpenLeg(-1,lot,"VCK-HZ-SELL",VCK_SRC_HEDGE_ZONE);return false;}
bool DCACondition(const int direction,const VCKSideStats &side,const MqlTick &tick){if(side.count<=0||side.newest_price<=0)return false;VCKDCAMode mode=ActiveDCAMode(side.count);double distance=RequiredDistance(side.count);double current=direction>0?tick.ask:tick.bid;bool adverse=direction>0?(side.newest_price-current>=distance):(current-side.newest_price>=distance);bool favorable=direction>0?(current-side.newest_price>=distance):(side.newest_price-current>=distance);switch(mode){case VCK_DCA_STEP:case VCK_DCA_STEP_MULTIPLIER:return adverse;case VCK_DCA_STEP_TIMEFRAME:return adverse&&NewBar(g_last_dca_bar);case VCK_DCA_SIGNAL:return adverse&&Entry.Direction()==direction;case VCK_DCA_POSITIVE:return favorable;case VCK_DCA_BIDIRECTIONAL:return adverse||favorable;case VCK_DCA_SIGNAL_BIDIRECTIONAL:return(adverse||favorable)&&Entry.Direction()==direction;case VCK_DCA_CLOSED_BAR:return adverse&&NewBar(g_last_dca_bar);default:return false;}}
bool ManageDCA(const VCKSideStats &buy,const VCKSideStats &sell){if(!VCK_USE_DCA||!EntryDelayPassed()||g_hedge_zone)return false;if(!SessionAllowed()&&!InpDCAOutsideSession)return false;MqlTick t;if(!SymbolInfoTick(g_symbol,t))return false;if(buy.count>0&&buy.count<InpMaxBuyPositions&&GridRisk.LevelAllowed(buy.count,InpMaxLevelsBuy)&&DCACondition(1,buy,t)&&(!g_stop_buy)&&((buy.count<InpTrendFilterAfterPositions)||Entry.FiltersAllow(1))&&OpenLeg(1,NextLot(1,buy.count),"VCK-DCA-BUY",VCK_SRC_DCA))return true;if(sell.count>0&&sell.count<InpMaxSellPositions&&GridRisk.LevelAllowed(sell.count,InpMaxLevelsSell)&&DCACondition(-1,sell,t)&&(!g_stop_sell)&&((sell.count<InpTrendFilterAfterPositions)||Entry.FiltersAllow(-1))&&OpenLeg(-1,NextLot(-1,sell.count),"VCK-DCA-SELL",VCK_SRC_DCA))return true;return false;}
bool ManageInitialEntry(const VCKSideStats &buy,const VCKSideStats &sell){if(!g_new_cycle||!SessionAllowed()||!EntryDelayPassed()||buy.count+sell.count>0||TimeCurrent()<g_cooldown_until)return false;int d=Entry.Direction();if(d==0||!Entry.FiltersAllow(d)||(d>0&&g_stop_buy)||(d<0&&g_stop_sell))return false;if(OpenLeg(d,NextLot(d,0),"VCK-ENTRY",VCK_SRC_ENTRY)){g_state=VCK_ACTIVE_CYCLE;return true;}return false;}
void ManageZoneCycle(){if(!VCK_USE_ZONE_CYCLE||InpZoneCycleUpper<=InpZoneCycleLower)return;MqlTick t;if(SymbolInfoTick(g_symbol,t)&&(t.bid>InpZoneCycleUpper||t.ask<InpZoneCycleLower))g_new_cycle=false;}

__REMOTE_COMMAND_HANDLER__
void CreateButton(const string key,const string text,const int y){string n=VCKP_PREFIX+key;if(ObjectFind(0,n)>=0)return;if(!ObjectCreate(0,n,OBJ_BUTTON,0,0,0))return;ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_LEFT_UPPER);ObjectSetInteger(0,n,OBJPROP_XDISTANCE,10);ObjectSetInteger(0,n,OBJPROP_YDISTANCE,y);ObjectSetInteger(0,n,OBJPROP_XSIZE,145);ObjectSetInteger(0,n,OBJPROP_YSIZE,22);ObjectSetString(0,n,OBJPROP_TEXT,text);}
void CreatePanel(){if(!VCK_USE_PANEL)return;CreateButton("NEW","Toggle New Cycle",20);CreateButton("CLOSE_BUY","Close Buy",46);CreateButton("CLOSE_SELL","Close Sell",72);CreateButton("CLOSE_ALL","Close All (2-step)",98);CreateButton("STOP_BUY","Toggle Buy",124);CreateButton("STOP_SELL","Toggle Sell",150);if(VCK_USE_RESET_LOTS){CreateButton("RESET_BUY","Reset Lots Buy",176);CreateButton("RESET_SELL","Reset Lots Sell",202);}}
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &s){if(id!=CHARTEVENT_OBJECT_CLICK)return;if(s==VCKP_PREFIX+"NEW")g_new_cycle=!g_new_cycle;else if(s==VCKP_PREFIX+"CLOSE_BUY")CloseSide(POSITION_TYPE_BUY);else if(s==VCKP_PREFIX+"CLOSE_SELL")CloseSide(POSITION_TYPE_SELL);else if(s==VCKP_PREFIX+"STOP_BUY")g_stop_buy=!g_stop_buy;else if(s==VCKP_PREFIX+"STOP_SELL")g_stop_sell=!g_stop_sell;else if(s==VCKP_PREFIX+"RESET_BUY")g_buy_reset_lot=InpResetLot;else if(s==VCKP_PREFIX+"RESET_SELL")g_sell_reset_lot=InpResetLot;else if(s==VCKP_PREFIX+"CLOSE_ALL"){datetime n=TimeCurrent();if(!g_close_armed||n-g_close_armed_at>5){g_close_armed=true;g_close_armed_at=n;ObjectSetString(0,s,OBJPROP_TEXT,"Confirm Close All");return;}g_close_armed=false;ObjectSetString(0,s,OBJPROP_TEXT,"Close All (2-step)");CloseMagicPositions();}PersistStateCritical();}

__INPUT_VALIDATOR__

int OnInit(){if(!ValidateOperationalInputs())return INIT_PARAMETERS_INCORRECT;g_symbol=StringLen(InpTradeSymbol)>0?InpTradeSymbol:_Symbol;if(!SymbolSelect(g_symbol,true))return INIT_FAILED;if((VCK_USE_DCA||VCK_USE_HEDGE||VCK_USE_HEDGE_ZONE||VCK_USE_REVERSE_ENTRY||VCK_USE_LOT_BALANCE)&&(ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING){Print("Composition requires MT5 hedging account");return INIT_FAILED;}g_pip=PipSize();if(g_pip<=0||!Entry.Init(g_symbol,InpSignalTimeframe))return INIT_FAILED;MathSrand((int)GetTickCount());Trade.Configure(InpMagic,g_symbol,InpSignalTimeframe,InpMaxSpreadPips,InpAsyncExecution);EventReducer.Configure(InpMagic,g_symbol);CommandLedger.Configure(InpMagic,g_symbol);StateStore.Configure(InpMagic,g_symbol);StateStore.Load(g_ea_enabled,g_new_cycle,g_stop_buy,g_stop_sell,g_lottery_factor);StateStore.LoadExtended(g_daily_halt_day,g_balance_day,g_day_start_balance,g_persisted_peak,g_hedge_zone,g_zone_phase,g_zone_cycle_id,g_zone_anchor_position_id,g_zone_low,g_zone_high,g_cooldown_until);GridRisk.Init(g_persisted_peak);Log.Configure("__NAME__");MfeMae.Configure("__NAME__");Trade.Reconcile();VCKSideStats buy,sell;Book.Collect(g_symbol,InpMagic,POSITION_TYPE_BUY,buy);Book.Collect(g_symbol,InpMagic,POSITION_TYPE_SELL,sell);ReconcileHedgeZoneState(buy,sell);CreatePanel();Log.Event("INIT","EA initialized");return INIT_SUCCEEDED;}
void OnDeinit(const int reason){PersistStateCritical();Log.Event("DEINIT",IntegerToString(reason));Entry.Release();ObjectsDeleteAll(0,VCKP_PREFIX);}
bool TickAdmissionGate()
  {
   if(ProcessRemoteCommands()) return false;
   ManageZoneCycle();
   MfeMae.Sample(g_symbol,InpMagic);
   if(!g_ea_enabled){g_state=VCK_STOPPED;return false;}
   return SpreadAllowed();
  }

bool RiskMutationGate(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(GridRisk.MustStop())
     {
      Log.Event("MAX_DD_STOP","hard drawdown stop",GridRisk.DD());
      CloseMagicPositions();
      g_ea_enabled=false;
      PersistStateCritical();
      return true;
     }
   if(!DailyAllowed())
     {
      if(!g_daily_history_ready){Log.Event("HISTORY_NOT_READY","daily accounting frozen");return true;}
      Log.Event("DAILY_HALT","daily target/loss");
      CloseMagicPositions();
      return true;
     }
   if(VCK_USE_LOTTERY && InpLotteryResetLossMoney<0 && buy.profit+sell.profit<=InpLotteryResetLossMoney)
     {
      Log.Event("LOTTERY_RESET","loss reset",buy.profit+sell.profit);
      CloseMagicPositions();
      g_lottery_factor=1.0;
      PersistStateCritical();
      return true;
     }
   return false;
  }

bool ExitMutationChain(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(ManageGlobalExits(buy,sell)) return true;
   if(ManageBasketExit(buy,sell)) return true;
   if(ManageTrailing()) return true;
   return ManageTrendReversal(buy,sell);
  }

bool HedgeOriginExposureActive(){for(int i=0;i<PositionsTotal();i++){ulong t=PositionGetTicket(i);if(t==0||!PositionSelectByTicket(t))continue;if(PositionGetString(POSITION_SYMBOL)!=g_symbol||(long)PositionGetInteger(POSITION_MAGIC)!=InpMagic)continue;string c=PositionGetString(POSITION_COMMENT);if(StringFind(c,"VCK-HEDGE")>=0||StringFind(c,"VCK-HZ-")>=0)return true;}return false;}
bool SniperMutationChain(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(InpStopSniperDuringHedge && (VCK_SNIPER_PAUSE_HEDGE_ORIGIN_ONLY?HedgeOriginExposureActive():(buy.count>0&&sell.count>0))) return false;
   if(ManageSniper(buy)) return true;
   if(ManageSniper(sell)) return true;
   return ManageCrossChainSniper(buy,sell);
  }

bool ExposureMutationChain(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(GridRisk.FreezeDD())
     {
      Log.Event("DD_FREEZE","new exposure frozen",GridRisk.DD());
      return true;
     }
   if(ManageHedgeZone(buy,sell)) return true;
   if(g_hedge_zone&&VCK_HEDGE_ZONE_EXCLUSIVE) return false;
   if(ManageHedge(buy,sell)) return true;
   if(ManageReverseEntry(buy,sell)) return true;
   if(ManageLotBalance(buy,sell)) return true;
   if(ManageDCA(buy,sell)) return true;
   return ManageInitialEntry(buy,sell);
  }

void FinalizeCycleState(const VCKSideStats &buy,const VCKSideStats &sell)
  {
   if(buy.count+sell.count!=0 || g_state!=VCK_CLOSING) return;
   g_state=VCK_COOLDOWN;
   g_cooldown_until=TimeCurrent()+InpMinutesDelayAfterClear*60;
   PersistStateCritical();
  }

bool ApplyTradeDeal(const ulong deal)
  {
   if(deal==0||!HistoryDealSelect(deal)||!EventReducer.MarkDealProcessed(deal)) return false;
   Trade.ObserveDealDiagnostic(deal);
   ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal,DEAL_ENTRY);
   if(entry!=DEAL_ENTRY_OUT&&entry!=DEAL_ENTRY_OUT_BY) return false;
   ulong position_id=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
   double deal_realized=HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_SWAP)+HistoryDealGetDouble(deal,DEAL_COMMISSION);
   ENUM_DEAL_REASON reason=(ENUM_DEAL_REASON)HistoryDealGetInteger(deal,DEAL_REASON);
   bool position_fully_closed=!ManagedPositionIdentifierExists(position_id);
   if(position_fully_closed&&EventReducer.AcceptClosedPosition(position_id))
     {
      double position_realized=deal_realized;ENUM_DEAL_REASON final_reason=reason;PositionRealizedSummary(position_id,position_realized,final_reason);MfeMae.Finalize(position_id,position_realized);
      if(VCK_USE_LOTTERY&&final_reason==DEAL_REASON_SL){g_lottery_factor*=InpLotterySLMultiplier;g_cooldown_until=TimeCurrent()+InpLotteryDelayMinutes*60;}
      else if(final_reason==DEAL_REASON_TP)g_lottery_factor=1.0;
      Log.Event("POSITION_CLOSED",EnumToString(final_reason),position_realized);
      return true;
     }
   else Log.Event("DEAL_OUT_PARTIAL",EnumToString(reason),deal_realized);
   return false;
  }
bool ProcessPendingTradeEvents()
  {
   if(EventReducer.Overflowed()){g_ea_enabled=false;Log.Event("EVENT_QUEUE_OVERFLOW","manual reconciliation required");return true;}
   bool critical=false;
   for(int i=0;i<EventReducer.Slots();i++){ulong deal=EventReducer.PendingDeal(i);if(deal>0)critical=ApplyTradeDeal(deal)||critical;}
   return critical;
  }
void ProcessAndPersistPendingTradeEvents(){if(ProcessPendingTradeEvents())PersistStateCritical();}
void OnTick()
  {
   ProcessAndPersistPendingTradeEvents();
   if(!TickAdmissionGate()) return;
   Trade.Reconcile();
   VCKSideStats buy,sell;
   Book.Collect(g_symbol,InpMagic,POSITION_TYPE_BUY,buy);
   Book.Collect(g_symbol,InpMagic,POSITION_TYPE_SELL,sell);
   ReconcileHedgeZoneState(buy,sell);
   if(RiskMutationGate(buy,sell)) return;
   if(ExitMutationChain(buy,sell)) return;
   if(SniperMutationChain(buy,sell)) return;
   if(ExposureMutationChain(buy,sell)) return;
   FinalizeCycleState(buy,sell);
  }
void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result)
  {
   Trade.OnTransaction(trans,request,result);
   bool critical=false;
   if(trans.deal>0&&!EventReducer.EnqueueDeal(trans.deal)){g_ea_enabled=false;critical=true;Log.Event("EVENT_QUEUE_OVERFLOW","deal queue full",(double)trans.deal);}
   critical=ProcessPendingTradeEvents()||critical;
   VCKSideStats buy,sell;Book.Collect(g_symbol,InpMagic,POSITION_TYPE_BUY,buy);Book.Collect(g_symbol,InpMagic,POSITION_TYPE_SELL,sell);ReconcileHedgeZoneState(buy,sell);
   if(critical)PersistStateCritical();
   if(trans.type==TRADE_TRANSACTION_REQUEST&&result.retcode!=0&&!Trade.TransactionRetcodeAccepted(request.action,result.retcode))Log.Event("TRADE_RETCODE",IntegerToString((int)result.retcode),(double)request.action);
  }
'''


def _main(ir: EAIR) -> str:
    return (MAIN_TEMPLATE
            .replace("__NAME__", str(ir.identity["name"]))
            .replace("__HASH__", ir.sha256())
            .replace("__REMOTE_COMMAND_HANDLER__", _remote_command_handler(ir))
            .replace("__INPUT_VALIDATOR__", render_mql_validator()))


def _governance_spec(ir: EAIR) -> dict[str, Any]:
    symbols = list(ir.runtime.get("symbols") or []) or ["_Symbol"]
    timeframes = list(ir.runtime.get("timeframes") or []) or ["CURRENT"]
    max_buy = int(_p(ir, "max_buy_positions", _r(ir, "max_open_positions", 10)))
    max_sell = int(_p(ir, "max_sell_positions", _r(ir, "max_open_positions", 10)))
    return {
        "schema_version": "3.0",
        "ir_sha256": ir.sha256(),
        "project": {"name": str(ir.identity["name"]), "version": str(ir.identity.get("version") or "0.1.0"), "status": "DRAFT-NOT-VALIDATED"},
        "strategy": {
            "class": "hybrid", "symbols": symbols, "timeframes": timeframes,
            "entry_logic": "Selectable signal engine with explicit trend filters and cycle admission gates.",
            "exit_logic": "Single/basket/money exits, trailing, recovery, hedge and drawdown controls composed from EA-IR.",
            "forbidden_logic": ["unbounded_martingale"],
        },
        "risk": {
            "max_lot": float(_r(ir, "max_lot", 1.0)),
            "risk_per_trade_pct": float(_r(ir, "risk_per_trade_pct", 0.5)),
            "max_daily_loss_pct": float(_r(ir, "daily_loss_pct", 5.0)),
            "max_drawdown_pct": float(_r(ir, "max_drawdown_pct", 20.0)),
            "max_positions": max(max_buy, max_sell),
            "stop_loss_required": bool(float(_r(ir, "sl_pips", 0)) > 0),
        },
        "execution": {
            "account_modes": [str(ir.runtime.get("account_model") or "hedging")],
            "slippage_points_max": int(_r(ir, "slippage_points_max", 30)),
            "spread_points_max": float(_r(ir, "max_spread_pips", 3.0)) * 10.0,
            "magic_number_policy": "required",
        },
        "validation": {"compile_required": True, "backtest_required": True, "stress_required": True, "evidence_manifest_required": True},
        "governance": {
            "mode": "full", "release_target": "draft", "semantic_approved": True,
            "behavior_changed": True, "trading_logic_changed": True, "risk_changed": True,
            "architecture_changed": True, "porting_changed": False, "derived_fields": ["project.version", "execution.spread_points_max"],
        },
        "release": {"environment_authority": "windows-native", "owner_approval_required_for_live": True},
    }


def _risk_contract(ir: EAIR) -> dict[str, Any]:
    return {
        "schema_version": "1.0", "ir_sha256": ir.sha256(),
        "max_lot": float(_r(ir, "max_lot", 1.0)),
        "max_levels_buy": int(_r(ir, "max_levels_buy", _p(ir, "max_buy_positions", 10))),
        "max_levels_sell": int(_r(ir, "max_levels_sell", _p(ir, "max_sell_positions", 10))),
        "freeze_drawdown_pct": float(_r(ir, "freeze_drawdown_pct", 15.0)),
        "max_drawdown_pct": float(_r(ir, "max_drawdown_pct", 20.0)),
        "daily_loss_pct": float(_r(ir, "daily_loss_pct", 5.0)),
        "unbounded_lot_scaling": False,
    }


def _evidence_manifest(ir: EAIR, artifact_manifest: dict[str, Any]) -> dict[str, Any]:
    artifact_hash = hashlib.sha256(json.dumps(artifact_manifest, sort_keys=True).encode("utf-8")).hexdigest()
    pending_compile = {
        "ok": False, "source": "unavailable", "command": "pending Windows MetaEditor runner",
        "tool_version": "pending", "host": "pending", "recorded_at_utc": "pending", "returncode": None,
    }
    pending_backtest = {
        "ok": False, "source": "unavailable", "command": "pending MT5 Strategy Tester runner",
        "tool_version": "pending", "host": "pending", "recorded_at_utc": "pending", "returncode": None,
    }
    summary = {
        "compile_ok": False, "backtest_ok": False, "gate_ok": False,
        "evidence_ok": False, "matrix_ok": False, "release_eligible": False,
    }
    return {
        "schema_version": "2.0", "ir_sha256": ir.sha256(),
        "created_at_utc": "SOURCE_GENERATION_TIME",
        "tool_policy": "No release claim is valid without native compile, tester, hashes and trusted runner attestation.",
        "source_artifact_manifest_sha256": artifact_hash,
        "compile": pending_compile, "backtest": pending_backtest,
        "gates": {"ok": False, "reason": "native gates pending"},
        "matrix": {"ok": False, "reason": "native stress matrix pending"},
        "artifacts": [], "unsafe_flags_used": [],
        "skipped_stages": ["native_compile", "mt5_strategy_tester"],
        "compile_ok": False, "backtest_ok": False,
        "native_compile_verified": False, "mt5_tester_verified": False,
        "release_eligible": False, "summary": summary,
        "status": "SOURCE-COMPLETE-NATIVE-EVIDENCE-PENDING", "authority": "windows-native",
    }

def generate(ir: EAIR, plan: BuildPlan, out_dir: Path, *, force: bool = False) -> Path:
    if not plan.ok:
        raise ValueError("build plan has blockers")
    name = validate_ea_name(str(ir.identity.get("name") or ""))
    parent = out_dir.parent.resolve(); parent.mkdir(parents=True, exist_ok=True)
    if out_dir.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {out_dir} (use force)")
    temp = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=parent))
    try:
        gov_spec = _governance_spec(ir)
        contract = build_contract_dict(gov_spec)
        files = {
            f"Experts/{name}/{name}.mq5": _main(ir),
            f"Include/{name}/Config.mqh": _config(ir, plan),
            f"Include/{name}/Core/AsyncTradeExecutor.mqh": TRADE_EXECUTOR,
            f"Include/{name}/Core/TradeIntentLedger.mqh": TRADE_INTENT_LEDGER,
            f"Include/{name}/Core/TradeEventReducer.mqh": TRADE_EVENT_REDUCER,
            f"Include/{name}/Core/RemoteCommandLedger.mqh": REMOTE_COMMAND_LEDGER,
            f"Include/{name}/Core/PositionBook.mqh": POSITION_BOOK,
            f"Include/{name}/Signal/EntryEngine.mqh": ENTRY_ENGINE,
            f"Include/{name}/Risk/GridRiskGuard.mqh": GRID_RISK_GUARD,
            f"Include/{name}/Exit/BasketCloseEngine.mqh": BASKET_CLOSE_ENGINE,
            f"Include/{name}/State/PersistentStateStore.mqh": PERSISTENT_STATE_STORE,
            f"Include/{name}/Telemetry/StructuredLogger.mqh": STRUCTURED_LOGGER,
            f"Include/{name}/Telemetry/MfeMaeLogger.mqh": MFE_MAE_LOGGER,
            "EA-IR.json": json.dumps(ir.to_dict(), ensure_ascii=False, indent=2)+"\n",
            "BUILD-PLAN.json": json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)+"\n",
            "EA-SPEC.yaml": yaml.safe_dump(gov_spec, sort_keys=False, allow_unicode=True),
            "AI-BUILD-CONTRACT.json": json.dumps(contract, ensure_ascii=False, indent=2)+"\n",
            "AI-BUILD-CONTRACT.md": render_contract_md(contract),
            "RISK-CONTRACT.yaml": yaml.safe_dump(_risk_contract(ir), sort_keys=False, allow_unicode=True),
            "RUNTIME-INPUT-CONTRACTS.json": json.dumps(contract_manifest(ir), ensure_ascii=False, indent=2)+"\n",
            "BROKER-CONTRACT.yaml": yaml.safe_dump({"schema_version":"1.0","ir_sha256":ir.sha256(),"account_model":ir.runtime.get("account_model","hedging"),"symbols":list(ir.runtime.get("symbols") or ["_Symbol"]),"digits_tested":[5,4,3,2],"native_validation_required":True}, sort_keys=False),
            "EVIDENCE-CONTRACT.yaml": yaml.safe_dump({"schema_version":"1.0","ir_sha256":ir.sha256(),"required":["MetaEditor compile log","EX5 SHA-256","MT5 Strategy Tester report","stress matrix","deep review"],"authority":"windows-native"}, sort_keys=False),
            "RELEASE-TRUST.yaml": yaml.safe_dump({"schema_version":"1.0","ir_sha256":ir.sha256(),"release_eligible":False,"reason":"native compile and MT5 tester evidence pending"}, sort_keys=False),
            "AGENTS.md": "# Agent rules\n\nDo not edit EA-IR, governance contracts, evidence, review, or release artifacts. Do not claim ready without Windows-native evidence.\n",
            "requirements-matrix.csv": to_csv(ir, plan, implemented_status="GENERATED"),
            "docs/docs-context.json": json.dumps({"ir_sha256":ir.sha256(),"source_documents":ir.metadata.get("source_documents",[]),"assumptions":ir.metadata.get("assumptions",[])}, ensure_ascii=False, indent=2)+"\n",
            "docs/docs-prompt.md": "# Verification prompt\n\nCompile the generated EA in Windows MetaEditor, run MT5 Strategy Tester and attach immutable evidence bound to the EA-IR hash.\n",
            "docs/guide.md": "# Operator guide\n\nThis project is a clean-room reference implementation generated from a functional manual plus an explicit operator profile. Review every input, compile in MetaEditor, and validate in MT5 Strategy Tester before any deployment.\n",
            "ACCEPTANCE-SCOPE.md": "# Acceptance scope\n\nThe manual defines features and parameter meanings, but does not provide original proprietary formulas for every signal. SMC, UTBOT and Supertrend are deterministic reference implementations recorded in the operator-profile assumptions. This is not a source-code clone.\n",
            "README.md": f"# {name}\n\nCanonical IR hash: `{ir.sha256()}`.\n\nStatus: **SOURCE-COMPLETE / NATIVE EVIDENCE PENDING**. MetaEditor compile and MT5 Strategy Tester evidence are mandatory before release.\n",
        }
        written: list[Path] = []
        for rel, content in files.items():
            dst=safe_join(temp,rel);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(content,encoding="utf-8");written.append(dst)
        evidence=safe_join(temp,"evidence");evidence.mkdir(parents=True,exist_ok=True)
        manifest=build_artifact_manifest(temp,ir,written)
        (evidence/"ir-artifacts.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        (evidence/"manifest.json").write_text(json.dumps(_evidence_manifest(ir,manifest),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        if out_dir.exists():shutil.rmtree(out_dir)
        temp.rename(out_dir);return out_dir
    except Exception:
        shutil.rmtree(temp,ignore_errors=True);raise
