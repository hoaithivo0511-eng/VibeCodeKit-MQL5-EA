"""Code-generation capability registry for composable EA features.

The registry is intentionally vendor-neutral. Features with multiple valid
meanings declare an explicit variant contract; a generic label such as
``hedge.zone`` is never enough to select one proprietary algorithm.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureCapability:
    path: str
    maturity: str  # stable|beta|unsupported
    generator: str | None
    implementation: str | None
    tests: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    account_modes: tuple[str, ...] = ("netting", "hedging")
    notes: str = ""
    variant_path: str | None = None
    supported_variants: tuple[str, ...] = ()
    semantics_version: str = "1.0"

    @property
    def supported(self) -> bool:
        return self.maturity in {"stable", "beta"} and bool(self.generator)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cap(
    path: str,
    maturity: str,
    generator: str | None,
    implementation: str | None,
    tests: tuple[str, ...] = (),
    dependencies: tuple[str, ...] = (),
    account_modes: tuple[str, ...] = ("netting", "hedging"),
    notes: str = "",
    *,
    variant_path: str | None = None,
    supported_variants: tuple[str, ...] = (),
    semantics_version: str = "1.0",
) -> FeatureCapability:
    return FeatureCapability(
        path, maturity, generator, implementation, tests, dependencies,
        account_modes, notes, variant_path, supported_variants,
        semantics_version,
    )


_CAPS: tuple[FeatureCapability, ...] = (
    _cap("strategy.entry.signal_selectable", "stable", "entry_signal", "CEntryEngine", ("model:test_signal_dispatch",)),
    _cap("strategy.entry.trend_following", "stable", "entry_trend", "CEntryEngine::TrendSignal", ("model:test_trend_signal",)),
    _cap("strategy.entry.mean_reversion", "stable", "entry_mean_reversion", "CEntryEngine::MeanReversionSignal", ("model:test_mean_reversion",)),
    _cap("strategy.entry.breakout", "stable", "entry_breakout", "CEntryEngine::BreakoutSignal", ("model:test_breakout",)),
    _cap("strategy.dca.enabled", "stable", "dca_core", "CDCAEngine", ("model:test_dca_gate",), account_modes=("hedging",)),
    _cap("strategy.dca.step", "stable", "dca_step", "CDCAEngine::RequiredDistance", ("model:test_dca_step",), ("strategy.dca.enabled",), ("hedging",)),
    _cap("strategy.dca.step_multiplier", "stable", "dca_step_multiplier", "CDCAEngine::RequiredDistance", ("model:test_dca_step_multiplier",), ("strategy.dca.enabled",), ("hedging",)),
    _cap("strategy.dca.step_timeframe", "beta", "dca_policy", "ManageDCA::StepTimeframe", ("model:test_dca_bar_gate",), ("strategy.dca.enabled",), ("hedging",)),
    _cap("strategy.dca.signal", "beta", "dca_policy", "ManageDCA::Signal", ("model:test_dca_signal_gate",), ("strategy.dca.enabled",), ("hedging",)),
    _cap("strategy.dca.positive", "beta", "dca_policy", "ManageDCA::Positive", ("model:test_dca_positive",), ("strategy.dca.enabled",), ("hedging",)),
    _cap("strategy.dca.bidirectional", "beta", "dca_policy", "ManageDCA::Bidirectional", ("model:test_dca_bidirectional",), ("strategy.dca.enabled",), ("hedging",)),
    _cap("strategy.dca.closed_bar", "beta", "dca_policy", "ManageDCA::ClosedBar", ("model:test_dca_closed_bar",), ("strategy.dca.enabled",), ("hedging",)),
    _cap("strategy.sizing.martingale", "stable", "lot_progression", "CLotProgression::NextLot", ("model:test_lot_multiplier",), account_modes=("hedging",)),
    _cap("strategy.sizing.additive", "stable", "lot_progression", "CLotProgression::NextLot", ("model:test_lot_additive",), account_modes=("hedging",)),
    _cap(
        "strategy.sniper.same_chain", "beta", "sniper_same_chain",
        "CSniperEngine::ManageSameChain", ("model:test_same_chain_sniper",),
        account_modes=("hedging",),
        variant_path="strategy.parameters.same_chain_sniper_variant",
        supported_variants=("oldest_best_pair_v1",),
    ),
    _cap("strategy.sniper.partial", "beta", "sniper_partial", "CSniperEngine::PartialClose", ("model:test_partial_sniper",), account_modes=("hedging",)),
    _cap(
        "strategy.sniper.cross_chain", "beta", "sniper_cross_chain",
        "ManageCrossChainSniper", ("model:test_cross_chain_sniper",),
        account_modes=("hedging",),
        notes="Ownership scope must be explicit; proprietary cross-chain selection is not inferred.",
        variant_path="strategy.parameters.cross_sniper_variant",
        supported_variants=("pair_loss_profit_v1",),
    ),
    _cap(
        "strategy.hedge.standard", "stable", "hedge_standard",
        "CHedgeEngine::Manage", ("model:test_hedge_trigger",),
        account_modes=("hedging",),
        variant_path="strategy.parameters.hedge_variant",
        supported_variants=("single_opposite_leg_v1",),
    ),
    _cap(
        "strategy.hedge.zone", "beta", "hedge_zone", "ManageHedgeZone",
        ("model:test_hedge_zone_state",), account_modes=("hedging",),
        notes="The generic label has multiple meanings; select a documented state-machine variant.",
        variant_path="strategy.parameters.hedge_zone_variant",
        supported_variants=("alternating_boundaries_v1",),
        semantics_version="2.0",
    ),
    _cap(
        "strategy.reverse_entry", "beta", "reverse_entry", "ManageReverseEntry",
        ("model:test_reverse_entry",), account_modes=("hedging",),
        variant_path="strategy.parameters.reverse_entry_variant",
        supported_variants=("signal_confirmed_v1",),
    ),
    _cap(
        "strategy.lot_balance", "beta", "lot_balance", "ManageLotBalance",
        ("model:test_lot_balance",), account_modes=("hedging",),
        variant_path="strategy.parameters.lot_balance_variant",
        supported_variants=("managed_chain_v1",),
    ),
    _cap("strategy.exit.basket_tp", "stable", "basket_exit", "CExitEngine::ManageBasketTP", ("model:test_weighted_basket_tp",)),
    _cap("strategy.exit.money", "stable", "money_exit", "CExitEngine::ManageMoneyLimits", ("model:test_money_exit",)),
    _cap("strategy.exit.daily_target", "stable", "daily_guard", "CRiskEngine::DailyGate", ("model:test_daily_halt",)),
    _cap("strategy.exit.single_tp", "stable", "single_tp", "OpenLeg", ("model:test_single_tp",)),
    _cap("strategy.exit.adaptive_basket_tp", "beta", "adaptive_basket_tp", "AdaptiveBasketTP", ("model:test_adaptive_basket_tp",)),
    _cap("strategy.exit.account_money", "beta", "account_money_exit", "ManageAccountMoneyExit", ("model:test_account_money_exit",)),
    _cap("strategy.exit.side_money", "stable", "side_money_exit", "ManageSideMoneyExit", ("model:test_side_money_exit",)),
    _cap("strategy.exit.stepped_target", "beta", "stepped_target", "ManageSteppedTarget", ("model:test_stepped_target",)),
    _cap("strategy.exit.trailing", "stable", "trailing", "ManageTrailing", ("model:test_trailing",)),
    _cap("strategy.exit.trend_reversal", "beta", "trend_reversal_exit", "ManageTrendReversalExit", ("model:test_trend_reversal_exit",)),
    _cap("strategy.exit.balance_difference", "beta", "balance_difference_exit", "ManageBalanceDifferenceExit", ("model:test_balance_difference_exit",)),
    _cap(
        "strategy.lottery.after_sl", "beta", "lottery_after_sl",
        "OnTradeTransaction::Lottery", ("model:test_lottery_after_sl",),
        account_modes=("hedging",),
        variant_path="strategy.parameters.lottery_variant",
        supported_variants=("per_closed_position_v1",),
        semantics_version="2.0",
    ),
    _cap("strategy.time.sessions", "stable", "session_gate", "SessionAllowed", ("model:test_session_gate",)),
    _cap("strategy.filter.zone_cycle", "beta", "zone_cycle", "ManageZoneCycle", ("model:test_zone_cycle",)),
    _cap("controls.reset_lots", "beta", "reset_lots", "OnChartEvent::ResetLots", ("source:test_reset_lot_controls",)),
    _cap("strategy.filter.trend", "stable", "filters", "CFilterEngine", ("model:test_filter_gate",)),
    _cap("strategy.filter.ema", "stable", "filters", "CFilterEngine::EMA", ("model:test_ema_filter",)),
    _cap("strategy.filter.macd", "stable", "filters", "CFilterEngine::MACD", ("model:test_macd_filter",)),
    _cap("strategy.filter.rsi", "stable", "filters", "CFilterEngine::RSI", ("model:test_rsi_filter",)),
    _cap(
        "controls.pending_order_remote", "beta", "pending_command_bus",
        "CDataDrivenCommandBus", ("model:test_pending_commands",),
        notes="Commands are data-driven; no command IDs or prices are assumed.",
        variant_path="controls.pending_command_transport",
        supported_variants=("pending_order_v1",),
        semantics_version="2.0",
    ),
    _cap("controls.chart_panel", "beta", "chart_panel", "OnChartEvent/OBJ_BUTTON", ("source:test_chart_events",)),
    _cap("controls.new_cycle", "stable", "cycle_state", "CCycleState", ("model:test_new_cycle_gate",)),
    _cap("risk.max_spread", "stable", "risk_engine", "CRiskEngine::SpreadGate", ("model:test_spread_gate",)),
    _cap("risk.max_lot", "stable", "risk_engine", "CRiskEngine::NormalizeVolume", ("model:test_max_lot",)),
    _cap("risk.max_positions", "stable", "risk_engine", "CRiskEngine::PositionGate", ("model:test_position_cap",)),
    _cap("risk.daily_loss", "stable", "daily_guard", "CRiskEngine::DailyGate", ("model:test_daily_halt",)),
)

_SIGNAL_STABLE = {
    "cci": "CEntryEngine::CCI", "cci_reversal": "CEntryEngine::CCI",
    "stochastic": "CEntryEngine::Stochastic", "stochastic_reversal": "CEntryEngine::Stochastic",
    "momentum": "CEntryEngine::Momentum", "rsi": "CEntryEngine::RSI",
    "rsi_reversal": "CEntryEngine::RSIReversal", "bollinger_bands": "CEntryEngine::Bollinger",
    "pinbar": "CEntryEngine::Pinbar", "engulfing": "CEntryEngine::Engulfing",
    "macd": "CEntryEngine::MACD", "ema_cross": "CEntryEngine::EMACross",
    "atr_break": "CEntryEngine::ATRBreak",
}
_SIGNAL_BETA = {
    "supertrend": "CEntryEngine::Supertrend", "utbot": "CEntryEngine::UTBot",
    "ichimoku_kumo_break": "CEntryEngine::IchimokuKumoBreak",
    "smc": "CEntryEngine::MarketStructureBreak", "smc_all_with": "CEntryEngine::MarketStructureBreak",
    "smc_all_against": "CEntryEngine::MarketStructureBreak", "smc_internal_with": "CEntryEngine::MarketStructureBreak",
    "smc_internal_against": "CEntryEngine::MarketStructureBreak", "smc_swing_with": "CEntryEngine::MarketStructureBreak",
    "smc_swing_against": "CEntryEngine::MarketStructureBreak",
    "pinbar_engulfing": "CEntryEngine::PinbarOrEngulfing", "candle_color": "CEntryEngine::CandleColor",
    "no_condition": "CEntryEngine::Unconditional", "random": "CEntryEngine::Random",
    "external_indicator": "CEntryEngine::ExternalIndicator",
}

REGISTRY: dict[str, FeatureCapability] = {c.path: c for c in _CAPS}
for signal, impl in _SIGNAL_STABLE.items():
    path = f"strategy.entry.signals.{signal}"
    REGISTRY[path] = _cap(path, "stable", "entry_signal", impl, (f"model:test_signal_{signal}",))
for signal, impl in _SIGNAL_BETA.items():
    path = f"strategy.entry.signals.{signal}"
    REGISTRY[path] = _cap(
        path, "beta", "entry_signal", impl, (f"model:test_signal_{signal}",),
        notes="Deterministic reference implementation; proprietary semantics require explicit acceptance.",
    )


def get(path: str) -> FeatureCapability:
    return REGISTRY.get(path, _cap(path, "unsupported", None, None, notes="Feature is not registered."))


def catalogue() -> list[dict[str, Any]]:
    return [REGISTRY[k].to_dict() for k in sorted(REGISTRY)]
