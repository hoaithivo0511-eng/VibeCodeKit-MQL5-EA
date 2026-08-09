"""PR-8 schema extension blocks for ``ea-spec.yaml``.

Five more optional, back-compat blocks split out of :mod:`spec_schema`
to keep that module under the audit LOC ceiling and to mirror the
one-block-per-concept pattern :mod:`spec_extensions` established for
PR-2. Adding these blocks to a spec is purely additive — specs that
don't supply them validate unchanged, and scaffolds that don't read
them ignore them.

The blocks are:

* :class:`TrailingConfig`     — trailing-stop configuration (start,
  step, min distance, mode {fixed, atr, parabolic}, ATR params).
* :class:`PartialCloseConfig` — scale-out levels (close N% at +M pips)
  + move-SL-to-breakeven trigger + buffer.
* :class:`CorrelationConfig`  — correlated-symbol exposure controls
  (max correlated positions, Pearson threshold, lookback bars, symbol
  group, block-on-correlated-loss switch).
* :class:`SwapFilterConfig`   — broker swap-cost filters (per-side
  daily swap pip cap, max hold bars under negative swap, skip the
  Wednesday triple-swap rollover).
* :class:`LogsConfig`         — EA-side logging knobs (enabled, level
  {debug,info,warn,error}, to-file, file pattern, to-terminal, redact
  account numbers).

Validators follow exactly the contract used in :mod:`spec_extensions`:
they accept the running ``errors`` list, append on problems, and
return either a fully-populated dataclass or ``None`` when the input
is missing / unparseable. ``check_num_range`` is injected from
:mod:`spec_schema` to avoid a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vibecodekit_mql5.spec_extensions import check_unknown_keys

# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

TRAILING_MODES = ("fixed", "atr", "parabolic")
LOG_LEVELS = ("debug", "info", "warn", "error")


@dataclass
class TrailingConfig:
    """Trailing-stop configuration.

    All fields optional. Templates that don't reference these fields
    ignore the section entirely.
    """

    enabled: bool = False
    mode: str | None = None  # one of TRAILING_MODES
    start_pips: float | None = None
    step_pips: float | None = None
    min_distance_pips: float | None = None
    atr_period: int | None = None
    atr_mult: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.enabled:
            out["enabled"] = True
        for k in ("mode", "start_pips", "step_pips",
                  "min_distance_pips", "atr_period", "atr_mult"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        return out


@dataclass
class PartialCloseConfig:
    """Scale-out (partial close) configuration.

    ``levels`` is a list of ``{at_pips: float, pct: float}`` entries —
    e.g. close 50% at +20 pips, close 30% at +50 pips. ``pct`` is in
    [0, 100). Order matters: the EA closes lower ``at_pips`` levels
    first.
    """

    enabled: bool = False
    levels: list[dict[str, float]] = field(default_factory=list)
    move_sl_to_breakeven_after_first: bool = False
    breakeven_buffer_pips: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.enabled:
            out["enabled"] = True
        if self.levels:
            out["levels"] = [dict(level) for level in self.levels]
        if self.move_sl_to_breakeven_after_first:
            out["move_sl_to_breakeven_after_first"] = True
        if self.breakeven_buffer_pips is not None:
            out["breakeven_buffer_pips"] = self.breakeven_buffer_pips
        return out


@dataclass
class CorrelationConfig:
    """Correlated-symbol exposure controls.

    All fields optional. ``correlation_threshold`` is the absolute
    Pearson |r| above which two symbols are considered "correlated".
    """

    max_correlated_positions: int | None = None
    correlation_threshold: float | None = None
    correlation_window_bars: int | None = None
    symbol_group: list[str] = field(default_factory=list)
    block_if_correlated_loss: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k in ("max_correlated_positions", "correlation_threshold",
                  "correlation_window_bars"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        if self.symbol_group:
            out["symbol_group"] = list(self.symbol_group)
        if self.block_if_correlated_loss:
            out["block_if_correlated_loss"] = True
        return out


@dataclass
class SwapFilterConfig:
    """Broker swap-cost filters."""

    max_long_swap_pips_per_day: float | None = None
    max_short_swap_pips_per_day: float | None = None
    max_hold_bars_if_negative_swap: int | None = None
    skip_wednesday_triple_swap: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k in ("max_long_swap_pips_per_day",
                  "max_short_swap_pips_per_day",
                  "max_hold_bars_if_negative_swap"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        if self.skip_wednesday_triple_swap:
            out["skip_wednesday_triple_swap"] = True
        return out


@dataclass
class LogsConfig:
    """EA-side logging knobs."""

    enabled: bool = False
    level: str | None = None  # one of LOG_LEVELS
    to_file: bool = False
    file_pattern: str | None = None
    to_terminal: bool = True
    redact_account_numbers: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.enabled:
            out["enabled"] = True
        if self.level is not None:
            out["level"] = self.level
        if self.to_file:
            out["to_file"] = True
        if self.file_pattern is not None:
            out["file_pattern"] = self.file_pattern
        # to_terminal defaults to True — only emit when explicitly disabled.
        if not self.to_terminal:
            out["to_terminal"] = False
        if self.redact_account_numbers:
            out["redact_account_numbers"] = True
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Validators
# ─────────────────────────────────────────────────────────────────────────────


def _check_bool(errors: list[str], block: str, key: str, value: Any) -> bool:
    if not isinstance(value, bool):
        errors.append(f"spec.{block}.{key} must be a bool, got {type(value).__name__}")
        return False
    return True


def validate_trailing(
    errors: list[str], raw: Any, *, check_num_range: Any,
) -> TrailingConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"spec.trailing must be a mapping, got {type(raw).__name__}")
        return None
    cfg = TrailingConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    check_unknown_keys(errors, "trailing", raw, valid_keys)
    if "enabled" in raw and _check_bool(errors, "trailing", "enabled", raw["enabled"]):
        cfg.enabled = raw["enabled"]
    if "mode" in raw:
        m = raw["mode"]
        if not isinstance(m, str) or m not in TRAILING_MODES:
            errors.append(
                f"spec.trailing.mode={m!r} not in {list(TRAILING_MODES)}"
            )
        else:
            cfg.mode = m
    float_bounds: dict[str, tuple[float, float]] = {
        "start_pips":        (0.0, 10000.0),
        "step_pips":         (0.0, 10000.0),
        "min_distance_pips": (0.0, 10000.0),
        "atr_mult":          (0.0, 100.0),
    }
    for k, (lo, hi) in float_bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        check_num_range(errors, "spec.trailing", k, raw[k],
                        min_excl=lo, max_incl=hi, is_int=False)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    if "atr_period" in raw:
        before = len(errors)
        check_num_range(errors, "spec.trailing", "atr_period", raw["atr_period"],
                        min_excl=0.0, max_incl=10000.0, is_int=True)
        if len(errors) == before:
            cfg.atr_period = raw["atr_period"]
    return cfg


def validate_partial_close(
    errors: list[str], raw: Any, *, check_num_range: Any,
) -> PartialCloseConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(
            f"spec.partial_close must be a mapping, got {type(raw).__name__}"
        )
        return None
    cfg = PartialCloseConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    check_unknown_keys(errors, "partial_close", raw, valid_keys)
    if "enabled" in raw and _check_bool(errors, "partial_close",
                                        "enabled", raw["enabled"]):
        cfg.enabled = raw["enabled"]
    if "move_sl_to_breakeven_after_first" in raw and _check_bool(
        errors, "partial_close", "move_sl_to_breakeven_after_first",
        raw["move_sl_to_breakeven_after_first"],
    ):
        cfg.move_sl_to_breakeven_after_first = raw[
            "move_sl_to_breakeven_after_first"
        ]
    if "breakeven_buffer_pips" in raw:
        before = len(errors)
        check_num_range(errors, "spec.partial_close", "breakeven_buffer_pips",
                        raw["breakeven_buffer_pips"],
                        min_excl=-1.0, max_incl=10000.0, is_int=False)
        if len(errors) == before:
            cfg.breakeven_buffer_pips = raw["breakeven_buffer_pips"]
    if "levels" in raw:
        levels = raw["levels"]
        if not isinstance(levels, list):
            errors.append(
                f"spec.partial_close.levels must be a list, got {type(levels).__name__}"
            )
        else:
            out_levels: list[dict[str, float]] = []
            for idx, lvl in enumerate(levels):
                if not isinstance(lvl, dict):
                    errors.append(
                        f"spec.partial_close.levels[{idx}] must be a mapping, "
                        f"got {type(lvl).__name__}"
                    )
                    continue
                unknown = set(lvl.keys()) - {"at_pips", "pct"}
                if unknown:
                    errors.append(
                        f"spec.partial_close.levels[{idx}] has unknown keys: "
                        f"{sorted(unknown)} (valid: ['at_pips', 'pct'])"
                    )
                ok = True
                # at_pips uses an exclusive lower bound (> 0): a partial-close
                # at 0 pips is meaningless. pct uses an effectively inclusive
                # lower bound (>= 0) — we shave a tiny epsilon off the kit's
                # exclusive check so pct=0 still passes while pct<0 (e.g. -0.5)
                # is rejected as semantically invalid.
                for k, (lo, hi) in (("at_pips",  (0.0, 100000.0)),
                                    ("pct",      (0.0, 100.0))):
                    if k not in lvl:
                        errors.append(
                            f"spec.partial_close.levels[{idx}].{k} is required"
                        )
                        ok = False
                        continue
                    before = len(errors)
                    check_num_range(errors,
                                    f"spec.partial_close.levels[{idx}]",
                                    k, lvl[k],
                                    min_excl=lo if k == "at_pips" else lo - 1e-9,
                                    max_incl=hi, is_int=False)
                    if len(errors) != before:
                        ok = False
                if ok:
                    out_levels.append({"at_pips": float(lvl["at_pips"]),
                                       "pct":     float(lvl["pct"])})
            cfg.levels = out_levels
    return cfg


def validate_correlation(
    errors: list[str], raw: Any, *, check_num_range: Any,
) -> CorrelationConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(
            f"spec.correlation must be a mapping, got {type(raw).__name__}"
        )
        return None
    cfg = CorrelationConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    check_unknown_keys(errors, "correlation", raw, valid_keys)
    int_bounds: dict[str, tuple[float, float]] = {
        "max_correlated_positions": (0.0, 1000.0),
        "correlation_window_bars":  (0.0, 100000.0),
    }
    for k, (lo, hi) in int_bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        check_num_range(errors, "spec.correlation", k, raw[k],
                        min_excl=lo, max_incl=hi, is_int=True)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    if "correlation_threshold" in raw:
        before = len(errors)
        check_num_range(errors, "spec.correlation", "correlation_threshold",
                        raw["correlation_threshold"],
                        min_excl=-1.0, max_incl=1.0, is_int=False)
        if len(errors) == before:
            cfg.correlation_threshold = raw["correlation_threshold"]
    if "symbol_group" in raw:
        grp = raw["symbol_group"]
        if not isinstance(grp, list) or not all(isinstance(s, str) for s in grp):
            errors.append(
                "spec.correlation.symbol_group must be a list of strings"
            )
        else:
            cfg.symbol_group = list(grp)
    if "block_if_correlated_loss" in raw and _check_bool(
        errors, "correlation", "block_if_correlated_loss",
        raw["block_if_correlated_loss"],
    ):
        cfg.block_if_correlated_loss = raw["block_if_correlated_loss"]
    return cfg


def validate_swap_filter(
    errors: list[str], raw: Any, *, check_num_range: Any,
) -> SwapFilterConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(
            f"spec.swap_filter must be a mapping, got {type(raw).__name__}"
        )
        return None
    cfg = SwapFilterConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    check_unknown_keys(errors, "swap_filter", raw, valid_keys)
    float_bounds: dict[str, tuple[float, float]] = {
        "max_long_swap_pips_per_day":  (-10000.0, 10000.0),
        "max_short_swap_pips_per_day": (-10000.0, 10000.0),
    }
    for k, (lo, hi) in float_bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        check_num_range(errors, "spec.swap_filter", k, raw[k],
                        min_excl=lo, max_incl=hi, is_int=False)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    if "max_hold_bars_if_negative_swap" in raw:
        before = len(errors)
        check_num_range(errors, "spec.swap_filter", "max_hold_bars_if_negative_swap",
                        raw["max_hold_bars_if_negative_swap"],
                        min_excl=0.0, max_incl=100000.0, is_int=True)
        if len(errors) == before:
            cfg.max_hold_bars_if_negative_swap = raw["max_hold_bars_if_negative_swap"]
    if "skip_wednesday_triple_swap" in raw and _check_bool(
        errors, "swap_filter", "skip_wednesday_triple_swap",
        raw["skip_wednesday_triple_swap"],
    ):
        cfg.skip_wednesday_triple_swap = raw["skip_wednesday_triple_swap"]
    return cfg


def validate_logs(
    errors: list[str], raw: Any, *, check_num_range: Any,
) -> LogsConfig | None:
    # check_num_range kept in signature for API uniformity (registry dispatch).
    del check_num_range
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"spec.logs must be a mapping, got {type(raw).__name__}")
        return None
    cfg = LogsConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    check_unknown_keys(errors, "logs", raw, valid_keys)
    if "enabled" in raw and _check_bool(errors, "logs", "enabled", raw["enabled"]):
        cfg.enabled = raw["enabled"]
    if "level" in raw:
        lvl = raw["level"]
        if not isinstance(lvl, str) or lvl not in LOG_LEVELS:
            errors.append(
                f"spec.logs.level={lvl!r} not in {list(LOG_LEVELS)}"
            )
        else:
            cfg.level = lvl
    if "to_file" in raw and _check_bool(errors, "logs", "to_file", raw["to_file"]):
        cfg.to_file = raw["to_file"]
    if "to_terminal" in raw and _check_bool(errors, "logs",
                                            "to_terminal", raw["to_terminal"]):
        cfg.to_terminal = raw["to_terminal"]
    if "file_pattern" in raw:
        fp = raw["file_pattern"]
        if not isinstance(fp, str) or not fp:
            errors.append(
                "spec.logs.file_pattern must be a non-empty string"
            )
        else:
            cfg.file_pattern = fp
    if "redact_account_numbers" in raw and _check_bool(
        errors, "logs", "redact_account_numbers", raw["redact_account_numbers"],
    ):
        cfg.redact_account_numbers = raw["redact_account_numbers"]
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Registry — dispatched from spec_schema.validate() in a single loop so the
# core module doesn't need 5 thin wrappers (audit LOC ceiling).
# ─────────────────────────────────────────────────────────────────────────────

EXTRA_BLOCK_VALIDATORS = (
    ("trailing",      validate_trailing),
    ("partial_close", validate_partial_close),
    ("correlation",   validate_correlation),
    ("swap_filter",   validate_swap_filter),
    ("logs",          validate_logs),
)
