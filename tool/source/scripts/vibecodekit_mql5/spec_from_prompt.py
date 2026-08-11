"""Translate a free-text description into canonical EA-IR 3.1 JSON.

This module is the bridge between the Devin **chat-driven build** playbook
(P2.2) and ``mql5-auto-build``. The playbook captures a single English (or
Vietnamese) sentence from the user — ``"build EA trend EURUSD H1 risk 0.5%
SL 30 TP 60 macd + sar"`` — and turns it into the EA-IR consumed by
``mql5-auto-build`` and ``mql5-ir-build``.

Design choices
--------------

* **Deterministic, regex-only**. The parser is intentionally rule-based so
  it can run inside an unattended pipeline (no LLM call, no network).
  Anything it can't parse is left at its schema default rather than
  hallucinated; ``--strict`` makes those gaps an error.

* **Canonical by default** — the normal CLI path emits the complete EA-IR
  object. The old single-preset YAML view exists only behind ``--legacy`` and
  carries an explicit non-release compatibility marker.

* **Idempotent**. Canonical EA-IR content has a stable hash; the explicit
  legacy emitter also produces stable YAML for compatibility callers.

Module layout — kept under the 400-LOC audit ceiling via two siblings:

* :mod:`vibecodekit_mql5.spec_from_prompt_recognisers` — recogniser
  tables + low-level match helpers for the original schema fields
  (preset, stack, symbol, timeframe, risk, signals, name).
* :mod:`vibecodekit_mql5.spec_from_prompt_blocks` — PR-2 / PR-8
  optional block matchers + YAML emitter helpers.

CLI
---

::

    mql5-spec-from-prompt "EA named TrendEA account netting EURUSD H1 trend"

Writes canonical JSON to stdout. Use ``--out PATH`` to write to a file and
``--strict`` to make unresolved planning fields block the command. Use
``--legacy`` only for callers that still require the older scaffold YAML.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import build as build_mod
from . import spec_schema
from .intake import parse_text as parse_ir_text
from .spec_from_prompt_blocks import (
    BLOCK_MATCHERS,
    OPTIONAL_BLOCKS,
)
from .spec_from_prompt_recognisers import (
    PRESET_KEYWORDS_PATTERNS,
    STACK_KEYWORDS,
    SYMBOLS,
    TIMEFRAMES,
    looked_up,
    match_name,
    match_preset,
    match_risk,
    match_signals,
    match_stack,
    match_symbol,
    match_symbols,
    match_timeframe,
)
from .spec_from_prompt_yaml import emit_yaml_block

LEGACY_COMPATIBILITY = {
    "mode": "legacy_scaffold",
    "release_eligible": False,
}


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PromptParseResult:
    """Structured outcome of parsing a single prompt.

    ``spec`` is a plain dict ready to be passed to ``spec_schema.validate``
    or rendered via ``to_yaml``. ``inferred`` lists the field paths that
    were filled from the prompt (vs falling back to schema defaults), so
    callers can surface "I assumed X because you didn't say" warnings.
    """

    spec: dict[str, object] = field(default_factory=dict)
    inferred: list[str] = field(default_factory=list)
    defaulted: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse(prompt: str) -> PromptParseResult:
    """Return the explicit legacy compatibility spec for ``prompt``.

    The parser never raises; gaps in the prompt are filled with the same
    defaults ``spec_schema.RiskConfig`` uses so the output is always
    schema-valid.
    """
    result = PromptParseResult()
    text = prompt.strip()
    if not text:
        # Fully blank prompts still produce a syntactically valid spec —
        # the caller can decide whether to accept that.
        result.spec = _default_spec()
        result.defaulted = ["everything"]
        return result

    ir = parse_ir_text(text, source="prompt", strict=False)
    features = set(ir.strategy.get("features") or [])
    all_symbols = list(ir.runtime.get("symbols") or match_symbols(text))
    # Legacy schema can express one archetype only. Choose a compatibility
    # view deterministically, but never discard the richer EA-IR silently.
    if len(all_symbols) > 1:
        preset, preset_stack = "portfolio-basket", "hedging" if ir.runtime.get("account_model") == "hedging" else "netting"
    elif "strategy.dca.enabled" in features:
        preset, preset_stack = "dca", "hedging"
    elif "strategy.hedge.standard" in features:
        preset, preset_stack = "hedging-multi", "hedging"
    else:
        preset, preset_stack = match_preset(text)
    explicit_account = ir.runtime.get("account_model")
    stack = str(explicit_account) if explicit_account in {"hedging", "netting"} else match_stack(text, fallback=preset_stack)
    allowed = build_mod.PRESETS.get(preset, [])
    if allowed and stack not in allowed:
        result.errors.append(
            f"legacy preset {preset!r} cannot represent explicit stack {stack!r}; "
            "remove --legacy or use mql5-ea-intake-ir instead of allowing a silent clamp"
        )
    symbol = all_symbols[0] if all_symbols else match_symbol(text)
    timeframe = match_timeframe(text)
    risk = match_risk(text)
    signals = match_signals(text)
    name = match_name(text, preset=preset, symbol=symbol, timeframe=timeframe)

    spec: dict[str, object] = {
        "name": name,
        "preset": preset,
        "stack": stack,
        "symbol": symbol,
        "timeframe": timeframe,
        "compatibility": dict(LEGACY_COMPATIBILITY),
    }
    if risk:
        spec["risk"] = risk
    if signals:
        spec["signals"] = signals

    # PR-2 / PR-8 optional blocks — only added when the prompt actually
    # mentions them. Each matcher returns ``None`` if it has nothing to
    # contribute, preserving back-compat with prompts that don't mention
    # any of these features.
    optional_blocks = {
        name: fn(text) for name, fn in BLOCK_MATCHERS.items()
    }
    for block_name, block_value in optional_blocks.items():
        if block_value:
            spec[block_name] = block_value

    # Track what we inferred vs what we defaulted, for transparency.
    inferred: list[str] = ["name"]
    for k, v in (
        ("preset", looked_up(text, PRESET_KEYWORDS_PATTERNS)),
        ("stack",  looked_up(text, STACK_KEYWORDS)),
        ("symbol", any(s.upper() in text.upper() for s in SYMBOLS)),
        ("timeframe", any(tf in text.upper() for tf in TIMEFRAMES)),
        ("risk",   bool(risk)),
        ("signals",bool(signals)),
    ):
        if v:
            inferred.append(k)
        else:
            result.defaulted.append(k)
    for block_name in OPTIONAL_BLOCKS:
        if optional_blocks[block_name]:
            inferred.append(block_name)
        else:
            result.defaulted.append(block_name)
    if ir.strategy.get("topology") == "multi_engine":
        result.warnings.append(
            "multi-engine EA detected; legacy ea-spec.yaml is only a compatibility "
            "view and cannot preserve every subsystem. Remove --legacy and use "
            "mql5-ir-build."
        )
    for conflict in ir.conflicts:
        result.errors.append(str(conflict.get("message") or conflict))

    # Surface (never silently drop) requirements the single-symbol scaffold
    # cannot encode. A multi-symbol / portfolio request keeps the first symbol
    # but the others are reported so the operator can act (v2.5.0 QA, #1).
    if len(all_symbols) > 1:
        result.warnings.append(
            "multi-symbol request (" + ", ".join(all_symbols) + ") — the "
            f"scaffold builds a single symbol '{symbol}'; add the other "
            "symbols manually or use a portfolio/correlation preset. "
            "(Requirement surfaced, not dropped.)"
        )
    result.spec = spec
    result.inferred = inferred
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Defaults + YAML emitter
# ─────────────────────────────────────────────────────────────────────────────

def _default_spec() -> dict[str, object]:
    """Schema-valid spec used when the prompt is completely empty."""
    return {
        "name": "StdlibEurusdH1",
        "preset": "stdlib",
        "stack": "netting",
        "symbol": "EURUSD",
        "timeframe": "H1",
        "compatibility": dict(LEGACY_COMPATIBILITY),
    }


def to_yaml(spec: dict[str, object]) -> str:
    """Emit a minimal YAML serialisation of ``spec``.

    Only handles the subset of types this module produces: strings, ints,
    floats, lists of dicts, plus the dict-shaped PR-2 / PR-8 optional
    blocks. Output is stable so test fixtures don't churn.
    """
    lines: list[str] = []
    for key in ("name", "preset", "stack", "symbol", "timeframe", "mode"):
        if key in spec:
            lines.append(f"{key}: {spec[key]}")
    if "compatibility" in spec:
        compatibility = spec["compatibility"]
        assert isinstance(compatibility, dict)
        lines.append("compatibility:")
        lines.append(f"  mode: {compatibility['mode']}")
        release_eligible = str(bool(compatibility["release_eligible"])).lower()
        lines.append(f"  release_eligible: {release_eligible}")
    if "risk" in spec:
        risk = spec["risk"]
        assert isinstance(risk, dict)
        lines.append("risk:")
        for rk in (
            "per_trade_pct", "daily_loss_pct", "max_spread_pips",
            "max_open_positions", "sl_pips", "tp_pips",
        ):
            if rk in risk:
                lines.append(f"  {rk}: {risk[rk]}")
    if "signals" in spec:
        sigs = spec["signals"]
        lines.append("signals:")
        if isinstance(sigs, dict):
            if "logic" in sigs:
                lines.append(f"  logic: {sigs['logic']}")
            entries = sigs.get("list", [])
            if entries:
                lines.append("  list:")
                for entry in entries:
                    assert isinstance(entry, dict)
                    (k, v), = entry.items()
                    lines.append(f"    - {k}: {v}")
        else:
            assert isinstance(sigs, list)
            for entry in sigs:
                assert isinstance(entry, dict)
                (k, v), = entry.items()
                lines.append(f"  - {k}: {v}")

    # PR-2 / PR-8 optional blocks — emit in canonical order so test
    # fixtures don't churn. Skip any block not present in the spec.
    for block_name in OPTIONAL_BLOCKS:
        if block_name not in spec:
            continue
        block = spec[block_name]
        assert isinstance(block, dict), block_name
        lines.append(f"{block_name}:")
        lines.extend(emit_yaml_block(block, indent=2))
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mql5-spec-from-prompt",
        description="Translate a free-text EA description into canonical EA-IR JSON.",
    )
    p.add_argument("prompt", help="Natural-language description of the EA")
    p.add_argument(
        "--out", type=Path,
        help="Write the spec here instead of stdout.",
    )
    p.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero when required planning fields remain unresolved.",
    )
    p.add_argument(
        "--explain", action="store_true",
        help="Print a one-line parse summary for the selected output mode.",
    )
    output_mode = p.add_mutually_exclusive_group()
    output_mode.add_argument(
        "--ir", action="store_true",
        help="Compatibility alias for the canonical default EA-IR output.",
    )
    output_mode.add_argument(
        "--legacy", action="store_true",
        help="Emit the non-release legacy single-preset YAML compatibility view.",
    )
    args = p.parse_args(argv)

    if not args.legacy:
        ir = parse_ir_text(args.prompt, source="prompt", strict=args.strict)
        payload = json.dumps(ir.to_dict(), ensure_ascii=False, indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(payload, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            sys.stdout.write(payload)
        if args.explain:
            print(
                "canonical EA-IR: "
                f"requirements={len(ir.requirements)} "
                f"ambiguities={len(ir.ambiguities)} conflicts={len(ir.conflicts)}",
                file=sys.stderr,
            )
        return 0 if ir.ready_for_planning else 1

    result = parse(args.prompt)
    if result.errors:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    # Run the spec through the real validator so we never emit garbage.
    spec_schema.validate(result.spec, valid_presets=build_mod.PRESETS)

    # A fully blank prompt yields a generic placeholder spec. That is
    # schema-valid but almost never what the operator intended, so never let it
    # slip out silently — warn on stderr (and refuse outright under --strict).
    blank_prompt = "everything" in result.defaulted
    if blank_prompt:
        print(
            "warning: empty prompt — emitting a generic placeholder spec "
            f"({result.spec.get('name')}); pass a real description to ground the build",
            file=sys.stderr,
        )

    # Always surface warnings (e.g. dropped multi-symbol) on stderr so the
    # operator is never silently given a narrower spec than they asked for.
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)

    if args.strict:
        if blank_prompt:
            print(
                "refusing to emit a spec from an empty prompt under --strict",
                file=sys.stderr,
            )
            return 1
        # Strictness is about whether the operator gave us enough to ground
        # the build. ``stack`` is implied by ``preset`` and ``name`` is
        # always synthesised from the other three, so we only insist on the
        # three fields a human would normally type into the prompt.
        required_for_strict = {"preset", "symbol", "timeframe"}
        missing = required_for_strict & set(result.defaulted)
        if missing:
            print(
                f"missing fields the prompt didn't mention: {sorted(missing)}",
                file=sys.stderr,
            )
            return 1
        if any("multi-engine EA detected" in w for w in result.warnings):
            print(
                "legacy schema cannot represent this multi-engine EA under "
                "--strict; remove --legacy to emit canonical EA-IR",
                file=sys.stderr,
            )
            return 1

    yaml_text = to_yaml(result.spec)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(yaml_text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(yaml_text)

    if args.explain:
        msg = (
            f"inferred: {result.inferred}  "
            f"defaulted: {result.defaulted}"
        )
        print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
