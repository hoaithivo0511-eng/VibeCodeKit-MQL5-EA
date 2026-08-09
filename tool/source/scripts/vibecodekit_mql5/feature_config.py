"""Operational configuration and semantic contracts for code-generatable EA features."""
from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .ea_ir import EAIR
from .feature_registry import get


def _read(ir: EAIR, path: str) -> Any:
    root, _, tail = path.partition(".")
    current: Any = {
        "identity": ir.identity, "runtime": ir.runtime, "strategy": ir.strategy,
        "risk": ir.risk, "controls": ir.controls, "metadata": ir.metadata,
    }.get(root)
    if current is None:
        return None
    for part in tail.split(".") if tail else ():
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


FEATURE_CONFIG: dict[str, tuple[tuple[str, ...], ...]] = {
    "strategy.dca.enabled": (("strategy.parameters.dca_step_pips",),),
    "strategy.dca.step": (("strategy.parameters.dca_step_pips",),),
    "strategy.dca.step_multiplier": (("strategy.parameters.dca_step_pips",), ("strategy.parameters.dca_step_multiplier",)),
    "strategy.dca.step_timeframe": (("strategy.parameters.dca_step_pips",),),
    "strategy.dca.signal": (("strategy.parameters.dca_step_pips",),),
    "strategy.dca.positive": (("strategy.parameters.dca_step_pips",),),
    "strategy.dca.bidirectional": (("strategy.parameters.dca_step_pips",),),
    "strategy.dca.closed_bar": (("strategy.parameters.dca_step_pips",),),
    "strategy.sizing.martingale": (("strategy.parameters.lot_multiplier",),),
    "strategy.sizing.additive": (("strategy.parameters.lot_additive",),),
    "strategy.lottery.after_sl": (("strategy.parameters.lottery_sl_multiplier",),),
    "strategy.hedge.standard": (("strategy.parameters.hedge_trigger_positions", "strategy.parameters.hedge_trigger_loss_pct"), ("strategy.parameters.hedge_lot_pct", "strategy.parameters.hedge_use_dca_lot")),
    "strategy.hedge.zone": (("strategy.parameters.hedge_zone_trigger_positions",), ("strategy.parameters.hedge_zone_lot_multiplier",), ("strategy.parameters.hedge_zone_distance_pips",), ("strategy.parameters.hedge_zone_target_money", "strategy.parameters.hedge_zone_target_pips")),
    "strategy.reverse_entry": (("strategy.parameters.reverse_trigger_positions",), ("strategy.parameters.reverse_lot_pct", "strategy.parameters.reverse_fixed_lot")),
    "strategy.lot_balance": (("strategy.parameters.balance_trigger_lots",), ("strategy.parameters.balance_stop_lots",), ("strategy.parameters.balance_add_lot",)),
    "strategy.sniper.same_chain": (("strategy.parameters.sniper_trigger_positions",), ("strategy.parameters.sniper_target_money",)),
    "strategy.sniper.partial": (("strategy.parameters.partial_close_pct",),),
    "strategy.sniper.cross_chain": (("strategy.parameters.cross_sniper_trigger_positions",), ("strategy.parameters.cross_sniper_target_money",)),
    "strategy.exit.single_tp": (("risk.tp_pips",),),
    "strategy.exit.basket_tp": (("strategy.parameters.basket_target_money", "strategy.parameters.basket_tp_pips"),),
    "strategy.exit.adaptive_basket_tp": (("strategy.parameters.adaptive_tp_loss_pct", "strategy.parameters.adaptive_tp_loss_money"), ("strategy.parameters.adaptive_basket_tp_pips",)),
    "strategy.exit.money": (("strategy.parameters.basket_target_money",),),
    "strategy.exit.account_money": (("strategy.parameters.account_tp_money", "strategy.parameters.account_sl_money"),),
    "strategy.exit.side_money": (("strategy.parameters.buy_tp_money", "strategy.parameters.buy_sl_money", "strategy.parameters.sell_tp_money", "strategy.parameters.sell_sl_money"),),
    "strategy.exit.daily_target": (("strategy.parameters.daily_target_pct", "strategy.parameters.daily_target_money", "risk.daily_loss_pct", "strategy.parameters.daily_loss_money"),),
    "strategy.exit.stepped_target": (("strategy.parameters.stepped_target_money",),),
    "strategy.exit.trailing": (("strategy.parameters.trailing_start_pips",), ("strategy.parameters.trailing_distance_pips",)),
    "strategy.exit.balance_difference": (("strategy.parameters.balance_difference_pct",),),
    "strategy.time.sessions": (("strategy.parameters.sessions",),),
    "strategy.filter.zone_cycle": (("strategy.parameters.zone_cycle_upper",), ("strategy.parameters.zone_cycle_lower",)),
}

COMMON_EXECUTION_CONFIG: tuple[tuple[str, ...], ...] = (
    ("risk.base_lot",), ("risk.max_lot",), ("risk.max_spread_pips",),
    ("risk.max_open_positions",),
)

_ALLOWED_ORDER_TYPES = {"buy_stop", "sell_limit", "buy_limit", "sell_stop"}
_ALLOWED_STATE_PATHS = {
    "ea.enabled", "cycle.new_enabled", "direction.buy_enabled",
    "direction.sell_enabled",
}
_ALLOWED_CLOSE_SCOPES = {"managed_all", "managed_buy", "managed_sell", "account_all"}
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_COMMENT_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,15}$")


def _validate_remote_ownership(ir: EAIR) -> list[dict[str, Any]]:
    path = "controls.pending_command_ownership"
    ownership = ir.controls.get("pending_command_ownership")
    if not isinstance(ownership, dict) or not ownership:
        return [{
            "id": "MISSING-REMOTE-COMMAND-OWNERSHIP",
            "path": path,
            "message": "Pending-order commands require an explicit magic, comment prefix and managed-symbol scope.",
        }]
    blockers: list[dict[str, Any]] = []
    expected = {"magic", "comment_prefix", "symbol_scope"}
    unknown = sorted(set(ownership) - expected)
    missing = sorted(expected - set(ownership))
    if unknown or missing:
        blockers.append({
            "id": "INVALID-REMOTE-COMMAND-OWNERSHIP-SHAPE",
            "path": path,
            "missing": missing,
            "unknown": unknown,
        })
    magic = ownership.get("magic")
    if isinstance(magic, bool) or not isinstance(magic, int) or magic <= 0:
        blockers.append({
            "id": "INVALID-REMOTE-COMMAND-OWNER-MAGIC",
            "path": path + ".magic",
            "value": magic,
        })
    prefix = ownership.get("comment_prefix")
    if not isinstance(prefix, str) or not _COMMENT_PREFIX_RE.fullmatch(prefix):
        blockers.append({
            "id": "INVALID-REMOTE-COMMAND-COMMENT-PREFIX",
            "path": path + ".comment_prefix",
            "value": prefix,
            "message": "Use a portable 3-16 character ownership prefix.",
        })
    if ownership.get("symbol_scope") != "managed_symbol":
        blockers.append({
            "id": "INVALID-REMOTE-COMMAND-SYMBOL-SCOPE",
            "path": path + ".symbol_scope",
            "value": ownership.get("symbol_scope"),
        })
    return blockers


def _validate_remote_commands(ir: EAIR) -> list[dict[str, Any]]:
    blockers = _validate_remote_ownership(ir)
    commands = ir.controls.get("pending_commands") or {}
    if not isinstance(commands, dict) or not commands:
        return [{
            "id": "MISSING-REMOTE-COMMAND-MAP", "path": "controls.pending_commands",
            "message": "Remote control requires at least one explicit data-driven command.",
        }]
    seen: dict[tuple[str, float], str] = {}
    for command_id, config in sorted(commands.items()):
        path = f"controls.pending_commands.{command_id}"
        if not isinstance(command_id, str) or not _ID_RE.fullmatch(command_id):
            blockers.append({"id": "INVALID-REMOTE-COMMAND-ID", "path": path, "message": "Command IDs must be portable identifiers."})
            continue
        if not isinstance(config, dict):
            blockers.append({"id": "INVALID-REMOTE-COMMAND", "path": path, "message": "Command configuration must be a mapping."})
            continue
        order_type = str(config.get("order_type", "")).lower()
        price = config.get("price")
        action = config.get("action")
        if order_type not in _ALLOWED_ORDER_TYPES:
            blockers.append({"id": "INVALID-REMOTE-ORDER-TYPE", "path": path + ".order_type", "value": order_type})
        try:
            numeric_price = float(price)
            if numeric_price <= 0:
                raise ValueError
        except (TypeError, ValueError):
            blockers.append({"id": "INVALID-REMOTE-COMMAND-PRICE", "path": path + ".price", "value": price})
            numeric_price = -1.0
        key = (order_type, numeric_price)
        if numeric_price > 0 and order_type in _ALLOWED_ORDER_TYPES:
            if key in seen:
                blockers.append({
                    "id": "REMOTE-COMMAND-COLLISION", "path": path,
                    "conflicts_with": seen[key], "order_type": order_type,
                    "price": numeric_price,
                })
            else:
                seen[key] = command_id
        if not isinstance(action, dict):
            blockers.append({"id": "MISSING-REMOTE-COMMAND-ACTION", "path": path + ".action"})
            continue
        action_type = str(action.get("type", "")).lower()
        if action_type == "set_state":
            if action.get("path") not in _ALLOWED_STATE_PATHS or not isinstance(action.get("value"), bool):
                blockers.append({"id": "INVALID-SET-STATE-ACTION", "path": path + ".action", "action": action})
        elif action_type == "close_scope":
            scope = action.get("scope")
            if scope not in _ALLOWED_CLOSE_SCOPES:
                blockers.append({"id": "INVALID-CLOSE-SCOPE-ACTION", "path": path + ".action.scope", "value": scope})
            if scope == "account_all" and ir.controls.get("account_wide_close_approved") is not True:
                blockers.append({"id": "ACCOUNT-WIDE-COMMAND-NOT-APPROVED", "path": path + ".action.scope"})
        else:
            blockers.append({"id": "UNSUPPORTED-REMOTE-ACTION", "path": path + ".action.type", "value": action_type})
    return blockers


def validate(ir: EAIR, requested: Iterable[str]) -> list[dict[str, Any]]:
    """Return blockers for missing operational or semantic values."""
    paths = set(requested)
    allow_defaults = ir.metadata.get("defaults_policy") == "allow"
    blockers: list[dict[str, Any]] = []

    executable = any(
        p.startswith(("strategy.entry.", "strategy.dca.", "strategy.hedge."))
        for p in paths
    )
    required_groups: dict[tuple[str, ...], set[str]] = {}
    if executable:
        for group in COMMON_EXECUTION_CONFIG:
            required_groups.setdefault(group, set()).add("execution")
    for feature in sorted(paths):
        for group in FEATURE_CONFIG.get(feature, ()):
            required_groups.setdefault(group, set()).add(feature)

    for alternatives, required_by in sorted(required_groups.items()):
        if any(_present(_read(ir, p)) for p in alternatives):
            continue
        if allow_defaults:
            continue
        blockers.append({
            "id": "MISSING-FEATURE-CONFIG",
            "path": alternatives[0] if len(alternatives) == 1 else "one_of:" + "|".join(alternatives),
            "required_any_of": list(alternatives), "required_by": sorted(required_by),
            "message": "Operational value is missing; silent trading defaults are disabled.",
        })

    for feature in sorted(paths):
        cap = get(feature)
        if not cap.variant_path:
            continue
        variant = _read(ir, cap.variant_path)
        if not _present(variant):
            blockers.append({
                "id": "MISSING-FEATURE-VARIANT", "path": cap.variant_path,
                "feature": feature, "supported": list(cap.supported_variants),
                "semantics_version": cap.semantics_version,
                "message": "A generic feature label cannot select one semantic implementation.",
            })
        elif str(variant) not in cap.supported_variants:
            blockers.append({
                "id": "UNSUPPORTED-FEATURE-VARIANT", "path": cap.variant_path,
                "feature": feature, "value": variant,
                "supported": list(cap.supported_variants),
            })

    sizing_modes = {p for p in paths if p in {"strategy.sizing.martingale", "strategy.sizing.additive"}}
    if len(sizing_modes) > 1 and not _present(_read(ir, "strategy.parameters.lot_mode")):
        blockers.append({"id": "AMBIGUOUS-LOT-MODE", "path": "strategy.parameters.lot_mode", "requested": sorted(sizing_modes)})

    dca_modes = {p for p in paths if p in {
        "strategy.dca.step", "strategy.dca.step_multiplier", "strategy.dca.step_timeframe",
        "strategy.dca.signal", "strategy.dca.positive", "strategy.dca.bidirectional",
        "strategy.dca.closed_bar",
    }}
    specialised = dca_modes - {"strategy.dca.step"}
    if len(specialised) > 1 and not _present(_read(ir, "strategy.parameters.dca_mode")):
        blockers.append({"id": "AMBIGUOUS-DCA-MODE", "path": "strategy.parameters.dca_mode", "requested": sorted(specialised)})

    if "controls.pending_order_remote" in paths:
        blockers.extend(_validate_remote_commands(ir))
    return blockers
