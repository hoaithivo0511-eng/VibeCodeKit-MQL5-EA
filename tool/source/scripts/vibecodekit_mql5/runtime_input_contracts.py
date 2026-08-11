"""Single source of truth for generated runtime input semantics.

The same contracts are used to reject invalid EA-IR values before generation,
to emit a machine-readable project artifact, and to build the MQL5 ``OnInit``
guard.  This prevents documentation, generator defaults and runtime checks
from drifting to different sign/unit conventions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .ea_ir import EAIR


@dataclass(frozen=True)
class RuntimeInputContract:
    name: str
    source_path: str
    unit: str
    minimum: float | None
    maximum: float | None
    minimum_inclusive: bool = True
    maximum_inclusive: bool = True
    zero_semantics: str = "valid_value"

    @property
    def sign(self) -> str:
        if self.minimum is not None and self.minimum >= 0:
            return "non_negative" if self.minimum_inclusive else "positive"
        if self.maximum is not None and self.maximum <= 0:
            return "non_positive" if self.maximum_inclusive else "negative"
        return "signed"

    def accepts(self, value: float) -> bool:
        if self.minimum is not None and (
            value < self.minimum
            or (value == self.minimum and not self.minimum_inclusive)
        ):
            return False
        return (
            self.maximum is None
            or value < self.maximum
            or (value == self.maximum and self.maximum_inclusive)
        )

    def range_text(self) -> str:
        left = "(" if not self.minimum_inclusive else "["
        right = ")" if not self.maximum_inclusive else "]"
        low = "-inf" if self.minimum is None else f"{self.minimum:g}"
        high = "inf" if self.maximum is None else f"{self.maximum:g}"
        return f"{left}{low}, {high}{right}"


def _c(
    name: str,
    path: str,
    unit: str,
    minimum: float | None,
    maximum: float | None,
    *,
    min_inclusive: bool = True,
    max_inclusive: bool = True,
    zero: str = "valid_value",
) -> RuntimeInputContract:
    return RuntimeInputContract(
        name=name,
        source_path=path,
        unit=unit,
        minimum=minimum,
        maximum=maximum,
        minimum_inclusive=min_inclusive,
        maximum_inclusive=max_inclusive,
        zero_semantics=zero,
    )


INPUT_CONTRACTS: tuple[RuntimeInputContract, ...] = (
    _c("InpMagic", "identity.magic", "identifier", 1, None, zero="invalid"),
    _c("InpMinSecondsBetweenEntries", "strategy.parameters.min_seconds_between_entries", "seconds", 0, None, zero="no_delay"),
    _c("InpMinutesDelayAfterClear", "strategy.parameters.minutes_delay_after_clear", "minutes", 0, None, zero="no_delay"),
    _c("InpIntentUnknownTimeoutSeconds", "strategy.parameters.intent_unknown_timeout_seconds", "seconds", 5, None, zero="invalid"),
    _c("InpIntentHistoryLookbackSeconds", "strategy.parameters.intent_history_lookback_seconds", "seconds", 3600, None, zero="invalid"),
    _c("InpBaseLot", "risk.base_lot", "lots", 0, None, min_inclusive=False, zero="invalid"),
    _c("InpMaxLot", "risk.max_lot", "lots", 0, None, min_inclusive=False, zero="invalid"),
    _c("InpMaxSpreadPips", "risk.max_spread_pips", "pips", 0, None, min_inclusive=False, zero="blocks_all_entries"),
    _c("InpMaxBuyPositions", "strategy.parameters.max_buy_positions", "positions", 1, None, zero="invalid"),
    _c("InpMaxSellPositions", "strategy.parameters.max_sell_positions", "positions", 1, None, zero="invalid"),
    _c("InpMaxLevelsBuy", "risk.max_levels_buy", "levels", 1, None, zero="invalid"),
    _c("InpMaxLevelsSell", "risk.max_levels_sell", "levels", 1, None, zero="invalid"),
    _c("InpFreezeDDPct", "risk.freeze_drawdown_pct", "percent", 0, 100, zero="disabled"),
    _c("InpMaxDDPct", "risk.max_drawdown_pct", "percent", 0, 100, zero="disabled"),
    _c("InpSLPips", "risk.sl_pips", "pips", 0, None, zero="disabled"),
    _c("InpTPPips", "risk.tp_pips", "pips", 0, None, zero="disabled"),
    _c("InpDailyTargetPct", "strategy.parameters.daily_target_pct", "percent", 0, 100, zero="disabled"),
    _c("InpDailyLossPct", "risk.daily_loss_pct", "positive_percent_magnitude", 0, 100, zero="disabled"),
    _c("InpDailyTargetMoney", "strategy.parameters.daily_target_money", "account_currency", 0, None, zero="disabled"),
    _c("InpDailyLossMoney", "strategy.parameters.daily_loss_money", "account_currency", None, 0, zero="disabled"),
    _c("InpNewDayDelayMinutes", "strategy.parameters.new_day_delay_minutes", "minutes", 0, 1440, zero="no_delay"),
    _c("InpDCAStepPips", "strategy.parameters.dca_step_pips", "pips", 0, None, min_inclusive=False, zero="invalid_when_enabled"),
    _c("InpDCAStepMultiplier", "strategy.parameters.dca_step_multiplier", "ratio", 0, None, min_inclusive=False, zero="invalid"),
    _c("InpLotMultiplier", "strategy.parameters.lot_multiplier", "ratio", 0, None, min_inclusive=False, zero="invalid"),
    _c("InpLotAdditive", "strategy.parameters.lot_additive", "lots", 0, None, zero="no_increment"),
    _c("InpBasketTargetMoney", "strategy.parameters.basket_target_money", "account_currency", 0, None, zero="disabled"),
    _c("InpBasketStopMoney", "strategy.parameters.basket_stop_money", "account_currency", None, 0, zero="disabled"),
    _c("InpBasketTPPips", "strategy.parameters.basket_tp_pips", "pips", 0, None, zero="disabled"),
    _c("InpAdaptiveTPLossPct", "strategy.parameters.adaptive_tp_loss_pct", "signed_percent", -100, 0, zero="disabled"),
    _c("InpAdaptiveTPLossMoney", "strategy.parameters.adaptive_tp_loss_money", "account_currency", None, 0, zero="disabled"),
    _c("InpAdaptiveBasketTPPips", "strategy.parameters.adaptive_basket_tp_pips", "pips", 0, None, zero="disabled"),
    _c("InpAccountTPMoney", "strategy.parameters.account_tp_money", "account_currency", 0, None, zero="disabled"),
    _c("InpAccountSLMoney", "strategy.parameters.account_sl_money", "account_currency", None, 0, zero="disabled"),
    _c("InpBuyTPMoney", "strategy.parameters.buy_tp_money", "account_currency", 0, None, zero="disabled"),
    _c("InpBuySLMoney", "strategy.parameters.buy_sl_money", "account_currency", None, 0, zero="disabled"),
    _c("InpSellTPMoney", "strategy.parameters.sell_tp_money", "account_currency", 0, None, zero="disabled"),
    _c("InpSellSLMoney", "strategy.parameters.sell_sl_money", "account_currency", None, 0, zero="disabled"),
    _c("InpPartialClosePct", "strategy.parameters.partial_close_pct", "percent", 0, 100, zero="disabled"),
    _c("InpHedgeTriggerPositions", "strategy.parameters.hedge_trigger_positions", "positions", 0, None, zero="disabled"),
    _c("InpHedgeTriggerLossPct", "strategy.parameters.hedge_trigger_loss_pct", "signed_percent", -100, 0, zero="disabled"),
    _c("InpHedgeLotPct", "strategy.parameters.hedge_lot_pct", "percent", 0, 1000, zero="disabled"),
    _c("InpHedgeZoneTriggerPositions", "strategy.parameters.hedge_zone_trigger_positions", "positions", 0, None, zero="disabled"),
    _c("InpHedgeZoneLotMultiplier", "strategy.parameters.hedge_zone_lot_multiplier", "ratio", 0, None, min_inclusive=False, zero="invalid_when_enabled"),
    _c("InpHedgeZoneDistancePips", "strategy.parameters.hedge_zone_distance_pips", "pips", 0, None, min_inclusive=False, zero="invalid_when_enabled"),
    _c("InpHedgeZoneTargetMoney", "strategy.parameters.hedge_zone_target_money", "account_currency", 0, None, zero="disabled"),
    _c("InpHedgeZoneTargetPips", "strategy.parameters.hedge_zone_target_pips", "pips", 0, None, zero="disabled"),
    _c("InpHedgeZoneMaxLot", "strategy.parameters.hedge_zone_max_lot", "lots", 0, None, min_inclusive=False, zero="invalid_when_enabled"),
    _c("InpReverseTriggerPositions", "strategy.parameters.reverse_trigger_positions", "positions", 0, None, zero="disabled"),
    _c("InpReverseLotPct", "strategy.parameters.reverse_lot_pct", "percent", 0, 1000, zero="disabled"),
    _c("InpReverseFixedLot", "strategy.parameters.reverse_fixed_lot", "lots", 0, None, zero="disabled"),
    _c("InpBalanceTriggerLots", "strategy.parameters.balance_trigger_lots", "lots", 0, None, zero="disabled"),
    _c("InpBalanceStopLots", "strategy.parameters.balance_stop_lots", "lots", 0, None, zero="disabled"),
    _c("InpBalanceAddLot", "strategy.parameters.balance_add_lot", "lots", 0, None, zero="disabled"),
    _c("InpBalanceDelaySeconds", "strategy.parameters.balance_delay_seconds", "seconds", 0, None, zero="no_delay"),
    _c("InpLotterySLMultiplier", "strategy.parameters.lottery_sl_multiplier", "ratio", 0, None, min_inclusive=False, zero="invalid_when_enabled"),
    _c("InpLotteryDelayMinutes", "strategy.parameters.lottery_delay_minutes", "minutes", 0, None, zero="no_delay"),
    _c("InpLotteryResetLossMoney", "strategy.parameters.lottery_reset_loss_money", "account_currency", None, 0, zero="disabled"),
    _c("InpResetLot", "strategy.parameters.reset_lot", "lots", 0, None, min_inclusive=False, zero="invalid"),
    _c("InpResetMultiplier", "strategy.parameters.reset_multiplier", "ratio", 0, None, min_inclusive=False, zero="invalid"),
    _c("InpTrailingStartPips", "strategy.parameters.trailing_start_pips", "pips", 0, None, zero="disabled"),
    _c("InpTrailingDistancePips", "strategy.parameters.trailing_distance_pips", "pips", 0, None, zero="disabled"),
)


def _read(ir: EAIR, path: str) -> Any:
    root, _, tail = path.partition(".")
    current: Any = {
        "identity": ir.identity,
        "runtime": ir.runtime,
        "strategy": ir.strategy,
        "risk": ir.risk,
        "controls": ir.controls,
    }.get(root)
    for part in tail.split(".") if tail else ():
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def validate_ir_values(ir: EAIR) -> list[dict[str, Any]]:
    """Validate explicitly supplied values before source generation."""
    blockers: list[dict[str, Any]] = []
    for contract in INPUT_CONTRACTS:
        value = _read(ir, contract.source_path)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            blockers.append({
                "id": "INVALID-RUNTIME-INPUT-TYPE",
                "path": contract.source_path,
                "value": value,
                "expected": "number",
            })
            continue
        if not contract.accepts(float(value)):
            blockers.append({
                "id": "RUNTIME-INPUT-OUT-OF-RANGE",
                "path": contract.source_path,
                "input": contract.name,
                "value": value,
                "unit": contract.unit,
                "range": contract.range_text(),
                "zero_semantics": contract.zero_semantics,
            })
    return blockers


def contract_manifest(ir: EAIR) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "ir_sha256": ir.sha256(),
        "contracts": [
            {
                **asdict(contract),
                "sign": contract.sign,
                "range": contract.range_text(),
            }
            for contract in INPUT_CONTRACTS
        ],
        "cross_field_rules": [
            "InpBaseLot <= InpMaxLot",
            "InpFreezeDDPct == 0 or InpMaxDDPct == 0 or InpFreezeDDPct <= InpMaxDDPct",
            "InpBalanceStopLots <= InpBalanceTriggerLots",
            "feature-active alternatives must contain at least one enabled threshold",
            "session values must use HH:MM in the 00:00..23:59 range",
        ],
    }


def render_mql_validator() -> str:
    range_checks: list[str] = []
    for contract in INPUT_CONTRACTS:
        checks: list[str] = []
        if contract.minimum is not None:
            op = ">=" if contract.minimum_inclusive else ">"
            checks.append(f"{contract.name}{op}{contract.minimum:g}")
        if contract.maximum is not None:
            op = "<=" if contract.maximum_inclusive else "<"
            checks.append(f"{contract.name}{op}{contract.maximum:g}")
        condition = "&&".join(checks) or "true"
        detail = (
            f"VCK_CONFIG_INVALID|{contract.name}|unit={contract.unit}|"
            f"range={contract.range_text()}|zero={contract.zero_semantics}"
        )
        range_checks.append(f'   if(!({condition})){{Print("{detail}");ok=false;}}')

    relation_checks = [
        '   if(InpBaseLot>InpMaxLot){Print("VCK_CONFIG_INVALID|InpBaseLot|must_not_exceed=InpMaxLot");ok=false;}',
        '   if(InpFreezeDDPct>0&&InpMaxDDPct>0&&InpFreezeDDPct>InpMaxDDPct){Print("VCK_CONFIG_INVALID|InpFreezeDDPct|must_not_exceed=InpMaxDDPct");ok=false;}',
        '   if(VCK_USE_HEDGE&&InpHedgeTriggerPositions<=0&&InpHedgeTriggerLossPct>=0){Print("VCK_CONFIG_INVALID|hedge_trigger|positions_or_negative_loss_required");ok=false;}',
        '   if(VCK_USE_HEDGE&&!InpHedgeUseDCALot&&InpHedgeLotPct<=0){Print("VCK_CONFIG_INVALID|InpHedgeLotPct|positive_when_hedge_enabled");ok=false;}',
        '   if(VCK_USE_HEDGE_ZONE&&(InpHedgeZoneTargetMoney<=0&&InpHedgeZoneTargetPips<=0)){Print("VCK_CONFIG_INVALID|hedge_zone_target|money_or_pips_required");ok=false;}',
        '   if(VCK_USE_REVERSE_ENTRY&&InpReverseLotPct<=0&&InpReverseFixedLot<=0){Print("VCK_CONFIG_INVALID|reverse_lot|percent_or_fixed_required");ok=false;}',
        '   if(VCK_USE_LOT_BALANCE&&InpBalanceStopLots>InpBalanceTriggerLots){Print("VCK_CONFIG_INVALID|InpBalanceStopLots|must_not_exceed=InpBalanceTriggerLots");ok=false;}',
        '   if(VCK_USE_TRAILING&&(InpTrailingStartPips<=0||InpTrailingDistancePips<=0)){Print("VCK_CONFIG_INVALID|trailing|positive_start_and_distance_required");ok=false;}',
    ]

    lines: list[str] = []
    helper_names: list[str] = []
    for prefix, checks, batch_size in (
        ("ValidateOperationalInputRanges", range_checks, 5),
        ("ValidateOperationalInputRelations", relation_checks, 3),
    ):
        for index in range(0, len(checks), batch_size):
            helper_name = f"{prefix}{index // batch_size}"
            helper_names.append(helper_name)
            lines.extend([
                f"void {helper_name}(bool &ok)",
                "  {",
                *checks[index:index + batch_size],
                "  }",
            ])

    lines.extend(["bool ValidateOperationalInputs()", "  {", "   bool ok=true;"])
    lines.extend(f"   {name}(ok);" for name in helper_names)
    lines.extend(["   return ok;", "  }"])
    return "\n".join(lines)
