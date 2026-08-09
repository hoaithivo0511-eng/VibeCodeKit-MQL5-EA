"""Pure deterministic reference models for generated EA policies.

These functions mirror high-risk arithmetic and state gates in the MQL5
runtime so regression tests can validate the generator without pretending to
be MetaTrader execution evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from math import pow


def staged_value(count: int, initial: float, stages: list[tuple[int, float]]) -> float:
    value = float(initial)
    for threshold, candidate in sorted(stages):
        if threshold > 0 and count >= threshold:
            value = float(candidate)
    return value


def next_lot(base: float, count: int, *, mode: str, multiplier: float = 1.0,
             additive: float = 0.0, stages: list[tuple[int, float]] | None = None,
             lottery_factor: float = 1.0, maximum: float = 100.0) -> float:
    active = staged_value(count, multiplier, stages or [])
    lot = base * pow(active, count) if mode == "multiply" else base + additive * count
    return max(0.0, min(lot * lottery_factor, maximum))


def dca_distance(base_pips: float, count: int, *, multiplier: float = 1.0,
                 staged_distances: list[tuple[int, float]] | None = None,
                 exponential: bool = False) -> float:
    base = staged_value(count, base_pips, staged_distances or [])
    return base * (pow(multiplier, max(count - 1, 0)) if exponential else 1.0)


def dca_condition(mode: str, direction: int, newest: float, bid: float, ask: float,
                  required: float, signal: int = 0, new_bar: bool = True) -> bool:
    adverse = newest - bid if direction > 0 else ask - newest
    favorable = bid - newest if direction > 0 else newest - ask
    displacement = abs((bid if direction > 0 else ask) - newest)
    if mode == "positive":
        return favorable >= required
    if mode == "bidirectional":
        return displacement >= required
    if mode == "signal":
        return adverse >= required and signal == direction
    if mode == "signal_bidirectional":
        return displacement >= required and signal == direction
    if mode in {"step_timeframe", "closed_bar"}:
        return new_bar and adverse >= required
    return adverse >= required


def adaptive_basket_tp(normal_pips: float, adjusted_pips: float, side_profit: float,
                       balance: float, loss_pct: float = 0.0,
                       loss_money: float = 0.0) -> float:
    pct = side_profit / balance * 100.0 if balance > 0 else 0.0
    triggered = (loss_pct < 0 and pct <= loss_pct) or (loss_money < 0 and side_profit <= loss_money)
    return adjusted_pips if triggered and adjusted_pips > 0 else normal_pips


def _minutes(value: str) -> int:
    hour, minute = (int(x) for x in value.split(":", 1))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid HH:MM: {value}")
    return hour * 60 + minute


def in_session(now: time, start: str, end: str) -> bool:
    current = now.hour * 60 + now.minute
    a, b = _minutes(start), _minutes(end)
    if a == b:
        return True
    return a <= current <= b if a < b else current >= a or current <= b


@dataclass(frozen=True)
class HedgeZoneDecision:
    active: bool
    direction: int
    close_all: bool


def hedge_zone_step(*, active: bool, max_side_count: int, trigger_count: int,
                    bid: float, ask: float, lower: float, upper: float,
                    buy_lots: float, sell_lots: float, floating: float,
                    target_money: float) -> HedgeZoneDecision:
    enabled = active or max_side_count >= trigger_count
    if not enabled:
        return HedgeZoneDecision(False, 0, False)
    if target_money > 0 and floating >= target_money:
        return HedgeZoneDecision(False, 0, True)
    if ask >= upper and buy_lots <= sell_lots:
        return HedgeZoneDecision(True, 1, False)
    if bid <= lower and sell_lots <= buy_lots:
        return HedgeZoneDecision(True, -1, False)
    return HedgeZoneDecision(True, 0, False)
