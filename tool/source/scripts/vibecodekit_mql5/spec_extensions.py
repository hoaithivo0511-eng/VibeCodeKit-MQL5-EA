"""PR-2 schema extension blocks for ``ea-spec.yaml``.

Three optional, back-compat blocks split out of :mod:`spec_schema` to
keep that module under the audit LOC ceiling (one responsibility per
file). Adding these blocks to a spec is purely additive — specs that
don't supply them validate unchanged.

The blocks are:

* :class:`PropFirmConfig` — FTMO/MFF/FundedNext-style compliance
  guards (daily DD, max DD, profit target, news blackout, weekend-flat,
  copy-trading lock).
* :class:`TimeExitConfig` — time-based exits layered on top of
  price-based SL/TP (Friday close, max trade duration, session
  windows).
* :class:`StealthConfig`  — broker-side anti-pattern obfuscation
  switches (slippage / comment / lot-jitter randomisation, split
  orders, avoid round numbers). Enabling these is a policy decision
  per broker ToS; the kit only validates shape.

Validators follow the same contract as the core ones in
:mod:`spec_schema`: they accept the running ``errors`` list, append
to it on problems, and return either a fully-populated dataclass or
``None`` when the input is missing / unparseable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PropFirmConfig:
    """Prop-firm compliance constraints (FTMO/MFF/FundedNext-style).

    All fields are optional. When omitted the auto-build pipeline treats
    the section as absent and skips any prop-firm-specific safeguards.
    Templates that don't reference these fields ignore the section
    entirely — the block is purely additive.
    """

    daily_dd_pct: float | None = None
    max_dd_pct: float | None = None
    profit_target_pct: float | None = None
    news_block_min: int | None = None
    weekend_flat: bool = False
    copy_trading_lock: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v is not False}


@dataclass
class TimeExitConfig:
    """Time-based exit constraints layered on top of price-based SL/TP.

    All fields are optional.
    """

    close_on_friday: bool = False
    friday_close_hour: int | None = None
    max_trade_hours: int | None = None
    session_end_hour: int | None = None
    session_start_hour: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v is not False}


@dataclass
class StealthConfig:
    """Broker-side anti-pattern obfuscation switches.

    All fields are optional. NB: stealth tactics interact with broker
    ToS — enabling them is a policy decision, not a code one. The kit
    only validates shape; ship/no-ship is a human call.
    """

    randomize_slippage_pips: float | None = None
    randomize_comment_pool: list[str] = field(default_factory=list)
    randomize_lot_jitter_pct: float | None = None
    split_orders: bool = False
    avoid_round_numbers: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.randomize_slippage_pips is not None:
            out["randomize_slippage_pips"] = self.randomize_slippage_pips
        if self.randomize_comment_pool:
            out["randomize_comment_pool"] = list(self.randomize_comment_pool)
        if self.randomize_lot_jitter_pct is not None:
            out["randomize_lot_jitter_pct"] = self.randomize_lot_jitter_pct
        if self.split_orders:
            out["split_orders"] = True
        if self.avoid_round_numbers:
            out["avoid_round_numbers"] = True
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Validators
# ─────────────────────────────────────────────────────────────────────────────


def check_unknown_keys(
    errors: list[str], block: str, raw: dict[str, Any], valid: set[str],
) -> None:
    """Emit an error listing any keys in ``raw`` that aren't in ``valid``."""
    unknown = set(raw.keys()) - valid
    if unknown:
        errors.append(
            f"spec.{block} has unknown keys: {sorted(unknown)} "
            f"(valid: {sorted(valid)})"
        )


def validate_prop_firm(
    errors: list[str],
    raw: Any,
    *,
    check_num_range: Any,
) -> PropFirmConfig | None:
    """Validate the optional ``prop_firm`` block.

    ``check_num_range`` is the helper from :mod:`spec_schema` — injected
    to keep this module dependency-free of the core.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"spec.prop_firm must be a mapping, got {type(raw).__name__}")
        return None
    cfg = PropFirmConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    check_unknown_keys(errors, "prop_firm", raw, valid_keys)
    bounds: dict[str, tuple[float, float, bool]] = {
        "daily_dd_pct":      (0.0, 100.0, False),
        "max_dd_pct":        (0.0, 100.0, False),
        "profit_target_pct": (0.0, 100.0, False),
        "news_block_min":    (0.0, 1440.0, True),
    }
    for k, (lo, hi, is_int) in bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        check_num_range(errors, "spec.prop_firm", k, raw[k],
                        min_excl=lo, max_incl=hi, is_int=is_int)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    for k in ("weekend_flat", "copy_trading_lock"):
        if k in raw:
            v = raw[k]
            if not isinstance(v, bool):
                errors.append(f"spec.prop_firm.{k} must be a bool, got {type(v).__name__}")
                continue
            setattr(cfg, k, v)
    return cfg


def validate_time_exit(
    errors: list[str],
    raw: Any,
    *,
    check_num_range: Any,
) -> TimeExitConfig | None:
    """Validate the optional ``time_exit`` block."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"spec.time_exit must be a mapping, got {type(raw).__name__}")
        return None
    cfg = TimeExitConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    check_unknown_keys(errors, "time_exit", raw, valid_keys)
    int_bounds: dict[str, tuple[float, float]] = {
        # 0-23 for hours (allow 0); use min_excl=-1 so 0 passes.
        "friday_close_hour":  (-1.0, 23.0),
        "session_end_hour":   (-1.0, 23.0),
        "session_start_hour": (-1.0, 23.0),
        # max_trade_hours must be positive (a 0-hour cap is meaningless).
        "max_trade_hours":    (0.0, 720.0),
    }
    for k, (lo, hi) in int_bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        check_num_range(errors, "spec.time_exit", k, raw[k],
                        min_excl=lo, max_incl=hi, is_int=True)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    if "close_on_friday" in raw:
        v = raw["close_on_friday"]
        if not isinstance(v, bool):
            errors.append(
                f"spec.time_exit.close_on_friday must be a bool, got {type(v).__name__}"
            )
        else:
            cfg.close_on_friday = v
    return cfg


def validate_stealth(
    errors: list[str],
    raw: Any,
    *,
    check_num_range: Any,
) -> StealthConfig | None:
    """Validate the optional ``stealth`` block."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"spec.stealth must be a mapping, got {type(raw).__name__}")
        return None
    cfg = StealthConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    check_unknown_keys(errors, "stealth", raw, valid_keys)
    float_bounds: dict[str, tuple[float, float]] = {
        "randomize_slippage_pips":  (0.0, 100.0),
        "randomize_lot_jitter_pct": (0.0, 50.0),
    }
    for k, (lo, hi) in float_bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        check_num_range(errors, "spec.stealth", k, raw[k],
                        min_excl=lo, max_incl=hi, is_int=False)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    if "randomize_comment_pool" in raw:
        pool = raw["randomize_comment_pool"]
        if not isinstance(pool, list) or not all(isinstance(p, str) for p in pool):
            errors.append("spec.stealth.randomize_comment_pool must be a list of strings")
        else:
            cfg.randomize_comment_pool = list(pool)
    for k in ("split_orders", "avoid_round_numbers"):
        if k in raw:
            v = raw[k]
            if not isinstance(v, bool):
                errors.append(f"spec.stealth.{k} must be a bool, got {type(v).__name__}")
                continue
            setattr(cfg, k, v)
    return cfg
