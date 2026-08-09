"""``ea-spec.yaml`` schema validator.

This is the structured DSL behind ``mql5-auto-build --spec ea.yaml``. The MVP
schema covers the four blocks needed to render a customised stdlib/netting
project:

    name:        EA name
    preset:      scaffold preset (stdlib, trend, ml-onnx, ...)
    stack:       scaffold stack (netting, hedging, python-bridge, ...)
    symbol:      trading symbol
    timeframe:   H1 / M15 / ...
    mode:        permission mode (personal/team/enterprise, default: personal)
    risk:
      per_trade_pct:    optional, default 0.5  — 0 < x ≤ 5.0
      daily_loss_pct:   optional, default 5.0  — 0 < x ≤ 20.0
      max_spread_pips:  optional, default 3.0  — 0 < x ≤ 50.0
      max_open_positions: optional, default 3  — 1 ≤ n ≤ 100
      sl_pips:          optional, default 30   — 1 ≤ n ≤ 10000
      tp_pips:          optional, default 60   — 1 ≤ n ≤ 10000
    signals:           # MVP: documented in <out_dir>/signals.md; codegen later
      - kind:  macd | sar | rsi | ema_cross | bbands | atr_break
        ...indicator-specific params...
      logic: AND | OR   # default AND
    filters:           # optional, MVP: documented only
      - kind: time_window | news_blackout
        ...
    hooks:             # optional, MVP: documented only
      on_init: [...]
      on_deinit: [...]

The validator is pure stdlib (no Pydantic) so it stays lightweight. Errors are
collected and raised together so the caller sees every problem in one shot
instead of fix-and-retry per field.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

# PR-2 schema extensions live in their own module to keep this file under
# the audit LOC ceiling. Re-export the public names so existing call sites
# (and tests) continue to import them from ``spec_schema``.
from vibecodekit_mql5.spec_extensions import (  # noqa: F401
    PropFirmConfig,
    StealthConfig,
    TimeExitConfig,
    check_unknown_keys as _check_unknown_keys,
    validate_prop_firm,
    validate_stealth,
    validate_time_exit,
)
# PR-8 schema extensions: 5 more optional, back-compat blocks. Re-export so
# call sites (and tests) keep importing from ``spec_schema``.
from vibecodekit_mql5.spec_blocks_extra import (  # noqa: F401
    EXTRA_BLOCK_VALIDATORS, CorrelationConfig, LogsConfig,
    PartialCloseConfig, SwapFilterConfig, TrailingConfig,
)


VALID_MODES: frozenset[str] = frozenset({"personal", "team", "enterprise"})
VALID_SIGNAL_KINDS: frozenset[str] = frozenset({
    "macd", "sar", "rsi", "ema_cross", "bbands", "atr_break",
})
VALID_FILTER_KINDS: frozenset[str] = frozenset({"time_window", "news_blackout"})
VALID_SIGNAL_LOGIC: frozenset[str] = frozenset({"AND", "OR"})

REQUIRED_TOP_FIELDS: tuple[str, ...] = (
    "name", "preset", "stack", "symbol", "timeframe",
)


class SpecValidationError(ValueError):
    """Raised when ``ea-spec.yaml`` is structurally invalid.

    The message lists every problem found, joined by ``"; "`` so a single
    ``str(exc)`` shows the operator everything to fix.
    """


@dataclass
class RiskConfig:
    """Risk-management overrides for the scaffolded EA inputs."""

    per_trade_pct: float = 0.5
    daily_loss_pct: float = 5.0
    max_spread_pips: float = 3.0
    max_open_positions: int = 3
    sl_pips: int = 30
    tp_pips: int = 60

    def as_template_vars(self) -> dict[str, str]:
        """Render risk fields as ``{{KEY}}`` string substitutions.

        Returns a dict ready to merge into ``build._render``'s replace table.
        Values are strings so the renderer can do straight string interpolation.
        """
        # `0.05` style daily-loss percent (legacy default) vs the new percent
        # representation (5.0 == 5%). Keep both keys so older templates that
        # still reference {{DAILY_LOSS_FRAC}} continue to work alongside the
        # new {{DAILY_LOSS_PCT}}.
        return {
            "RISK_PER_TRADE_PCT": _fmt_float(self.per_trade_pct),
            "DAILY_LOSS_PCT": _fmt_float(self.daily_loss_pct),
            "DAILY_LOSS_FRAC": _fmt_float(self.daily_loss_pct / 100.0),
            "MAX_SPREAD_PIPS": _fmt_float(self.max_spread_pips),
            "MAX_POSITIONS": str(int(self.max_open_positions)),
            "SL_PIPS": str(int(self.sl_pips)),
            "TP_PIPS": str(int(self.tp_pips)),
            # Legacy: stdlib/netting still has `InpRiskMoney = 100.0` hardcoded.
            # Derive a money figure from the percent for cosmetic parity until
            # the include lib starts respecting per_trade_pct directly (P1.x).
            "RISK_MONEY": _fmt_float(self.per_trade_pct * 200.0),
        }


@dataclass
class SignalConfig:
    """A single indicator entry inside the ``signals:`` list."""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.params}


@dataclass
class FilterConfig:
    """A single entry inside the ``filters:`` list."""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.params}


@dataclass
class EaSpec:
    """Validated spec ready to feed into the build/lint/compile pipeline."""

    name: str
    preset: str
    stack: str
    symbol: str
    timeframe: str
    mode: str = "personal"
    risk: RiskConfig = field(default_factory=RiskConfig)
    signals: list[SignalConfig] = field(default_factory=list)
    signal_logic: str = "AND"
    filters: list[FilterConfig] = field(default_factory=list)
    hooks: dict[str, list[str]] = field(default_factory=dict)
    prop_firm: PropFirmConfig | None = None
    time_exit: TimeExitConfig | None = None
    stealth: StealthConfig | None = None
    trailing: TrailingConfig | None = None
    partial_close: PartialCloseConfig | None = None
    correlation: CorrelationConfig | None = None
    swap_filter: SwapFilterConfig | None = None
    logs: LogsConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "preset": self.preset,
            "stack": self.stack,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "mode": self.mode,
            "risk": asdict(self.risk),
            "signals": [s.to_dict() for s in self.signals],
            "signal_logic": self.signal_logic,
            "filters": [f.to_dict() for f in self.filters],
            "hooks": dict(self.hooks),
        }
        if self.prop_firm is not None:
            out["prop_firm"] = self.prop_firm.to_dict()
        if self.time_exit is not None:
            out["time_exit"] = self.time_exit.to_dict()
        if self.stealth is not None:
            out["stealth"] = self.stealth.to_dict()
        for name in ("trailing", "partial_close", "correlation",
                     "swap_filter", "logs"):
            cfg = getattr(self, name)
            if cfg is not None:
                out[name] = cfg.to_dict()
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_float(value: float) -> str:
    """Render a float the way MQL5 ``input`` declarations expect it.

    Floats need a decimal point so MetaEditor parses them as ``double`` and not
    ``int``. ``1.0`` → ``"1.0"``, ``1.5`` → ``"1.5"``, ``0.05`` → ``"0.05"``.
    """
    s = f"{float(value):.6f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def _check_str(errors: list[str], spec: dict[str, Any], key: str) -> None:
    value = spec.get(key)
    if not isinstance(value, str) or not value:
        errors.append(f"spec.{key} must be a non-empty string")


def _check_num_range(
    errors: list[str],
    block: str,
    key: str,
    value: Any,
    *,
    min_excl: float,
    max_incl: float,
    is_int: bool = False,
) -> None:
    if is_int:
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{block}.{key} must be an integer, got {type(value).__name__}")
            return
    else:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{block}.{key} must be a number, got {type(value).__name__}")
            return
    if not (min_excl < float(value) <= max_incl):
        errors.append(
            f"{block}.{key}={value!r} must satisfy {min_excl} < x <= {max_incl}"
        )


def _validate_risk(errors: list[str], raw: Any) -> RiskConfig:
    if raw is None:
        return RiskConfig()
    if not isinstance(raw, dict):
        errors.append(f"spec.risk must be a mapping, got {type(raw).__name__}")
        return RiskConfig()
    cfg = RiskConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    unknown = set(raw.keys()) - valid_keys
    if unknown:
        errors.append(
            f"spec.risk has unknown keys: {sorted(unknown)} "
            f"(valid: {sorted(valid_keys)})"
        )
    bounds: dict[str, tuple[float, float, bool]] = {
        "per_trade_pct":      (0.0, 5.0, False),
        "daily_loss_pct":     (0.0, 20.0, False),
        "max_spread_pips":    (0.0, 50.0, False),
        "max_open_positions": (0.0, 100.0, True),
        "sl_pips":            (0.0, 10000.0, True),
        "tp_pips":            (0.0, 10000.0, True),
    }
    for k, (lo, hi, is_int) in bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        _check_num_range(errors, "spec.risk", k, raw[k],
                         min_excl=lo, max_incl=hi, is_int=is_int)
        if len(errors) == before:
            # value passed type + range checks — keep it on the cfg dataclass
            setattr(cfg, k, raw[k])
    return cfg


def _validate_signals(errors: list[str], raw: Any) -> tuple[list[SignalConfig], str]:
    if raw is None:
        return [], "AND"
    logic = "AND"
    items: Iterable[Any]
    if isinstance(raw, dict):
        # `signals: { list: [...], logic: AND }` shorthand for future-proofing.
        if "logic" in raw:
            logic = str(raw["logic"]).upper()
            if logic not in VALID_SIGNAL_LOGIC:
                errors.append(
                    f"spec.signals.logic={raw['logic']!r} not in {sorted(VALID_SIGNAL_LOGIC)}"
                )
                logic = "AND"
        items = raw.get("list") or raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        errors.append(f"spec.signals must be a list or mapping, got {type(raw).__name__}")
        return [], "AND"

    out: list[SignalConfig] = []
    for idx, entry in enumerate(items):
        if not isinstance(entry, dict):
            errors.append(f"spec.signals[{idx}] must be a mapping, got {type(entry).__name__}")
            continue
        kind = entry.get("kind")
        if not isinstance(kind, str) or kind not in VALID_SIGNAL_KINDS:
            errors.append(
                f"spec.signals[{idx}].kind={kind!r} not in {sorted(VALID_SIGNAL_KINDS)}"
            )
            continue
        params = {k: v for k, v in entry.items() if k != "kind"}
        out.append(SignalConfig(kind=kind, params=params))
    return out, logic


def _validate_filters(errors: list[str], raw: Any) -> list[FilterConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append(f"spec.filters must be a list, got {type(raw).__name__}")
        return []
    out: list[FilterConfig] = []
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            errors.append(f"spec.filters[{idx}] must be a mapping, got {type(entry).__name__}")
            continue
        kind = entry.get("kind")
        if not isinstance(kind, str) or kind not in VALID_FILTER_KINDS:
            errors.append(
                f"spec.filters[{idx}].kind={kind!r} not in {sorted(VALID_FILTER_KINDS)}"
            )
            continue
        params = {k: v for k, v in entry.items() if k != "kind"}
        out.append(FilterConfig(kind=kind, params=params))
    return out


def _validate_hooks(errors: list[str], raw: Any) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"spec.hooks must be a mapping, got {type(raw).__name__}")
        return {}
    out: dict[str, list[str]] = {}
    for stage, body in raw.items():
        if not isinstance(stage, str):
            errors.append(f"spec.hooks key {stage!r} must be a string")
            continue
        if not isinstance(body, list):
            errors.append(f"spec.hooks.{stage} must be a list, got {type(body).__name__}")
            continue
        out[stage] = [str(line) for line in body]
    return out


def _validate_prop_firm(errors: list[str], raw: Any) -> PropFirmConfig | None:
    return validate_prop_firm(errors, raw, check_num_range=_check_num_range)


def _validate_time_exit(errors: list[str], raw: Any) -> TimeExitConfig | None:
    return validate_time_exit(errors, raw, check_num_range=_check_num_range)


def _validate_stealth(errors: list[str], raw: Any) -> StealthConfig | None:
    return validate_stealth(errors, raw, check_num_range=_check_num_range)


def validate(
    spec: dict[str, Any],
    *,
    valid_presets: dict[str, list[str]] | None = None,
) -> EaSpec:
    """Validate a parsed spec dict and return an ``EaSpec``.

    ``valid_presets`` is the same shape as ``build.PRESETS`` — when supplied,
    the validator additionally checks that ``preset`` is known and ``stack``
    is allowed for that preset. Pass ``None`` to skip those checks (handy for
    pure schema-only unit tests).

    Raises :class:`SpecValidationError` collecting *every* problem at once.
    """
    errors: list[str] = []
    if not isinstance(spec, dict):
        raise SpecValidationError(f"spec must be a mapping, got {type(spec).__name__}")

    missing = [k for k in REQUIRED_TOP_FIELDS if k not in spec]
    if missing:
        # Match the legacy auto_build error string so existing consumers
        # (including downstream tooling that greps the message) keep working.
        errors.append(f"spec missing required fields: {missing}")
    for k in REQUIRED_TOP_FIELDS:
        if k in spec:
            _check_str(errors, spec, k)

    mode = spec.get("mode", "personal")
    if not isinstance(mode, str) or mode not in VALID_MODES:
        errors.append(f"spec.mode={mode!r} not in {sorted(VALID_MODES)}")
        mode = "personal"

    if valid_presets is not None and isinstance(spec.get("preset"), str):
        preset = spec["preset"]
        if preset not in valid_presets:
            errors.append(
                f"spec.preset={preset!r} not in {sorted(valid_presets)}"
            )
        else:
            stack = spec.get("stack")
            if isinstance(stack, str) and stack not in valid_presets[preset]:
                errors.append(
                    f"spec.stack={stack!r} not supported by preset {preset!r}; "
                    f"valid: {valid_presets[preset]}"
                )

    risk = _validate_risk(errors, spec.get("risk"))
    signals, signal_logic = _validate_signals(errors, spec.get("signals"))
    filters = _validate_filters(errors, spec.get("filters"))
    hooks = _validate_hooks(errors, spec.get("hooks"))
    prop_firm = _validate_prop_firm(errors, spec.get("prop_firm"))
    time_exit = _validate_time_exit(errors, spec.get("time_exit"))
    stealth = _validate_stealth(errors, spec.get("stealth"))
    extras = {
        n: v(errors, spec.get(n), check_num_range=_check_num_range)
        for n, v in EXTRA_BLOCK_VALIDATORS
    }

    unknown_top = set(spec.keys()) - {
        *REQUIRED_TOP_FIELDS, "mode", "risk", "signals", "filters", "hooks",
        "prop_firm", "time_exit", "stealth",
        "trailing", "partial_close", "correlation", "swap_filter", "logs",
    }
    if unknown_top:
        errors.append(f"spec has unknown top-level keys: {sorted(unknown_top)}")

    if errors:
        raise SpecValidationError("; ".join(errors))

    return EaSpec(
        name=spec["name"],
        preset=spec["preset"],
        stack=spec["stack"],
        symbol=spec["symbol"],
        timeframe=spec["timeframe"],
        mode=mode,
        risk=risk,
        signals=signals,
        signal_logic=signal_logic,
        filters=filters,
        hooks=hooks,
        prop_firm=prop_firm,
        time_exit=time_exit,
        stealth=stealth,
        **extras,
    )


def render_signals_doc(spec: EaSpec) -> str:
    """Render the ``signals.md`` companion file written alongside the EA.

    MVP: we do NOT generate MQL5 signal code yet — that's the P1.x fan-out. For
    now we emit a Markdown file documenting what the user asked for, so the
    operator (or a future codegen pass) has the rules in one canonical place.
    """
    lines: list[str] = [
        f"# Signals for {spec.name}",
        "",
        f"- Symbol: `{spec.symbol}`",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Logic: **{spec.signal_logic}** (combine all signals with this operator)",
        "",
    ]
    if not spec.signals:
        lines.append("_No signals declared in spec.signals._")
    else:
        lines.append("## Indicators")
        lines.append("")
        for idx, sig in enumerate(spec.signals, start=1):
            lines.append(f"### {idx}. `{sig.kind}`")
            if sig.params:
                lines.append("")
                for k, v in sig.params.items():
                    lines.append(f"- `{k}`: `{v}`")
            lines.append("")
    if spec.filters:
        lines.append("## Filters")
        lines.append("")
        for idx, flt in enumerate(spec.filters, start=1):
            lines.append(f"- {idx}. `{flt.kind}` — {flt.params}")
        lines.append("")
    lines.append(
        "_This file is generated by `mql5-auto-build` from the spec.signals "
        "block. MQL5 code-generation for these signals is deferred to a "
        "future iteration; for now, use this doc as the spec to hand-code "
        "the entry/exit logic in `{name}.mq5`._".format(name=spec.name)
    )
    return "\n".join(lines) + "\n"
