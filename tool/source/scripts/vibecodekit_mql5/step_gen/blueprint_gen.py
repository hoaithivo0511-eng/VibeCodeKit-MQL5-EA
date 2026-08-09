"""mql5-blueprint-gen — auto-emit ``step-4-blueprint.md`` from ``ea-spec.yaml``.

Reads a validated ``ea-spec.yaml`` (optionally fused with a
``step-3-vision.md`` for the Scope section) and emits an ASCII module
diagram + state machine + invariants list seeded from the preset.

Invariants are *deterministic* per preset/stack pair so the kit can pin
"every invariant testable" by golden-output regression. The operator can
add new invariants manually but should not delete the seeded ones — they
encode the AGENTS.md rules (CPipNormalizer, CMagicRegistry,
OnTradeTransaction for async stacks, etc.).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from .._agent_io import (
    Envelope,
    add_gate_report_flag,
    add_json_flag,
    maybe_emit,
)
from .. import build as build_mod
from ..spec_schema import EaSpec, validate as validate_spec

TOOL = "mql5-blueprint-gen"


# Per-preset seed invariants. The kit's AGENTS.md "must NOT introduce"
# list translates directly into these — adding a new preset MUST extend
# this map so the build invariant set stays exhaustive.
PRESET_INVARIANTS: dict[str, tuple[str, ...]] = {
    "trend": (
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer for JPY/XAU symmetry",
        "Magic number reserved via CMagicRegistry (70000-79999)",
        "State machine: idle → entry-armed → in-trade → exit → idle",
    ),
    "mean-reversion": (
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
        "Mean reversion confirmed by ≥ 2 indicators (e.g. RSI + bbands)",
        "Cooldown after each exit (no immediate re-entry)",
    ),
    "breakout": (
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
        "Breakout confirmed on close (not on tick)",
        "Maximum 1 concurrent position per direction",
    ),
    "scalping": (
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer (slippage-aware)",
        "Magic number reserved via CMagicRegistry",
        "MaxSpread guard rejects entries when spread > InpMaxSpread",
        "Time-window filter active (session-bounded)",
    ),
    "hft-async": (
        "OrderSendAsync paired with OnTradeTransaction handler (AP-18)",
        "Stop-loss set on every async send (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
        "Latency budget < 5ms p95 between OnTick and OrderSendAsync",
    ),
    "news-trading": (
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
        "News blackout filter active (no entries N minutes around event)",
        "WebRequest NOT inside OnTick / OnTimer (AP-17)",
    ),
    "ml-onnx": (
        "ONNX model versioned (model_v<semver>.onnx) and hashed",
        "Inference p95 latency < 1ms (measured on OnTick)",
        "Fallback rule when model returns no signal (graceful degrade)",
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
    ),
    "service-llm-bridge": (
        "LLM call outside OnTick (cached or async; AP-17 compliant)",
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
        "LLM response schema validated before consumed (no string-prompt drift)",
    ),
    "service": (
        "Service runs as side-car (no trading directly)",
        "Health-check endpoint or heartbeat exposed",
        "Logs go to a documented sink (file / journal / syslog)",
    ),
    "grid": (
        "Stop-loss set on every grid level (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
        "Max grid depth bounded (no martingale runaway)",
        "Daily-loss cap respected even with multiple grid orders",
    ),
    "dca": (
        "Stop-loss set on every average-down add (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
        "Max DCA add bounded (no infinite averaging)",
        "Daily-loss cap respected",
    ),
    "hedging-multi": (
        "Stop-loss set on every leg (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved per leg via CMagicRegistry",
        "Hedge leg correlation verified at OnInit",
    ),
    "arbitrage-stat": (
        "Stop-loss set on every leg (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved per leg via CMagicRegistry",
        "Cointegration recomputed on rolling window",
    ),
    "portfolio-basket": (
        "Stop-loss set on every basket leg (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved per leg via CMagicRegistry",
        "Basket re-balance cadence documented",
    ),
    "wizard-composable": (
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
        "Signal / Trailing / Money modules each addressable independently",
    ),
    "indicator-only": (
        "No OrderSend (indicator/analysis only)",
        "OnCalculate prev_calculated check correct",
    ),
    "library": (
        "Exports declared via #import / #resource correctly",
        "No global state leak between EAs",
    ),
    "stdlib": (
        "Stop-loss set on every OrderSend (AP-1)",
        "Pip math via CPipNormalizer",
        "Magic number reserved via CMagicRegistry",
    ),
}


@dataclass(frozen=True)
class BlueprintFacts:
    spec: EaSpec
    invariants: tuple[str, ...]
    scope: tuple[str, ...]
    state_machine: tuple[str, ...]
    modules: tuple[str, ...]


def _scope_from_vision(vision_body: str | None) -> tuple[str, ...]:
    if not vision_body:
        return ()
    in_scope = False
    out: list[str] = []
    for line in vision_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_scope = stripped == "## Scope"
            continue
        if in_scope and stripped.startswith("- ") and "TODO" not in stripped.upper():
            out.append(stripped[2:].strip())
    return tuple(out)


def _state_machine(preset: str, has_async: bool) -> tuple[str, ...]:
    if has_async or preset == "hft-async":
        return (
            "idle → entry-armed (OnTick + signal AND-fold) →",
            "  in-flight (OrderSendAsync) → confirmed (OnTradeTransaction) →",
            "  in-trade → exit (TP/SL/manual) → idle",
        )
    if preset == "indicator-only":
        return ("idle → calc (OnCalculate) → idle",)
    return (
        "idle → entry-armed (OnTick + signal AND-fold) →",
        "  in-trade (OrderSend resolved synchronously) →",
        "  exit (TP/SL/manual) → idle",
    )


def _modules(spec: EaSpec) -> tuple[str, ...]:
    base = [
        f"{spec.name}.mq5 — entry-point (OnInit/OnTick/OnDeinit)",
        "Include/CPipNormalizer.mqh — broker pip math",
        "Include/CMagicRegistry.mqh — magic number issuance",
        "Include/CRiskGuard.mqh — equity + daily-loss enforcement",
    ]
    if spec.signals:
        kinds = ", ".join(sorted({s.kind for s in spec.signals}))
        base.append(f"Signal block — {len(spec.signals)} indicator(s): {kinds}")
    if spec.filters:
        kinds = ", ".join(sorted({f.kind for f in spec.filters}))
        base.append(f"Filter block — {kinds}")
    if spec.preset == "ml-onnx":
        base.append("Include/COnnxLoader.mqh — ONNX inference wrapper")
    if spec.stack == "python-bridge":
        base.append("scripts/<name>_bridge.py — Python sidecar over IPC")
    return tuple(base)


def build_facts(spec: EaSpec, vision_body: str | None = None) -> BlueprintFacts:
    invariants = PRESET_INVARIANTS.get(spec.preset, PRESET_INVARIANTS["stdlib"])
    scope = _scope_from_vision(vision_body)
    has_async = spec.preset == "hft-async" or "async" in spec.stack
    return BlueprintFacts(
        spec=spec,
        invariants=invariants,
        scope=scope,
        state_machine=_state_machine(spec.preset, has_async),
        modules=_modules(spec),
    )


def render_blueprint(facts: BlueprintFacts, *, source: Path | None = None) -> str:
    spec = facts.spec
    lines: list[str] = [
        "# Step 4 / 8 — BLUEPRINT",
        "",
        "Capture the architecture diagram, state machine, and invariants the EA must obey.",
        "",
        "## Inputs",
    ]
    if source is not None:
        lines.append(f"- `{source.name}` (preset: `{spec.preset}`, stack: `{spec.stack}`)")
    else:
        lines.append(f"- `ea-spec.yaml` (preset: `{spec.preset}`, stack: `{spec.stack}`)")
    if facts.scope:
        lines.append("- Vision scope (Step-3):")
        lines += [f"  - {s}" for s in facts.scope]

    lines += [
        "",
        "## EA identity",
        f"- Name: `{spec.name}`",
        f"- Symbol / TF: `{spec.symbol}` / `{spec.timeframe}`",
        f"- Risk: per-trade `{spec.risk.per_trade_pct}%`, daily-loss cap `{spec.risk.daily_loss_pct}%`",
        f"- Mode: `{spec.mode}`",
        "",
        "## Module diagram",
        "```",
        *[f"  {m}" for m in facts.modules],
        "```",
        "",
        "## State machine",
        "```",
        *[f"  {s}" for s in facts.state_machine],
        "```",
        "",
        "## Invariants",
        f"_Seeded from preset `{spec.preset}`. Each invariant MUST map to ≥ 1 module + ≥ 1 test in Step-5._",
        "",
    ]
    for inv in facts.invariants:
        lines.append(f"- [ ] {inv}")

    lines += [
        "",
        "## Exit criteria",
        "- Each invariant is testable (will appear in the 64-cell matrix)",
        "- No undefined transitions in the state machine",
        "",
        f"> Generated by `{TOOL}` from `{spec.preset}/{spec.stack}` preset.",
        "> Activities below MUST be re-ticked after manual refinement.",
        "",
        "## Activities",
        "- [ ] Module diagram (Include / scripts / external)",
        "- [ ] State machine (idle → entry-armed → in-trade → exit → idle)",
        "- [ ] Invariants list (e.g. `magic` reserved, pip math via CPipNormalizer)",
        "",
        "> Sentinel: `touch .rri-state/blueprint.done` (only after every activity is ticked).",
        "",
    ]
    return "\n".join(lines)


def load_spec(path: Path) -> EaSpec:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: spec must be a mapping")
    return validate_spec(raw, valid_presets=build_mod.PRESETS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=TOOL)
    parser.add_argument(
        "spec_file", type=Path,
        help="Path to ea-spec.yaml (Step-2 / mql5-init / mql5-spec-from-prompt output).",
    )
    parser.add_argument(
        "--vision", type=Path, default=None,
        help="Optional step-3-vision.md to fuse Scope from.",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Write the rendered BLUEPRINT to this path instead of stdout.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite --out if it already exists.",
    )
    add_json_flag(parser)
    add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    if not args.spec_file.is_file():
        env = Envelope(
            tool=TOOL, ok=False, exit_code=2,
            summary=f"spec not found: {args.spec_file}",
            data={"spec": str(args.spec_file)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(f"error: file not found: {args.spec_file}\n")
        return 2

    try:
        spec = load_spec(args.spec_file)
    except Exception as exc:  # noqa: BLE001 — surface to operator + envelope
        env = Envelope(
            tool=TOOL, ok=False, exit_code=2,
            summary=f"spec invalid: {exc}",
            data={"spec": str(args.spec_file), "error": str(exc)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(f"error: invalid spec: {exc}\n")
        return 2

    vision_body: str | None = None
    if args.vision is not None:
        if not args.vision.is_file():
            env = Envelope(
                tool=TOOL, ok=False, exit_code=2,
                summary=f"vision not found: {args.vision}",
                data={"vision": str(args.vision)},
            )
            maybe_emit(args, env)
            if not args.emit_json:
                sys.stderr.write(f"error: file not found: {args.vision}\n")
            return 2
        vision_body = args.vision.read_text(encoding="utf-8")

    facts = build_facts(spec, vision_body=vision_body)
    rendered = render_blueprint(facts, source=args.spec_file)

    if args.out is not None:
        if args.out.exists() and not args.force:
            env = Envelope(
                tool=TOOL, ok=False, exit_code=2,
                summary=f"refusing to overwrite {args.out} (use --force)",
                data={"out": str(args.out)},
            )
            maybe_emit(args, env)
            if not args.emit_json:
                sys.stderr.write(f"error: {args.out} exists (use --force)\n")
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")

    if not args.emit_json:
        if args.out is None:
            sys.stdout.write(rendered)
        else:
            sys.stderr.write(f"wrote {args.out}\n")

    evidence: list[str] = [str(args.spec_file)]
    if args.vision is not None:
        evidence.append(str(args.vision))
    env = Envelope(
        tool=TOOL, ok=True, exit_code=0,
        summary=(
            f"rendered BLUEPRINT for {spec.preset}/{spec.stack} "
            f"with {len(facts.invariants)} invariant(s) + {len(facts.modules)} module(s)"
        ),
        data={
            "preset": spec.preset,
            "stack": spec.stack,
            "invariants": list(facts.invariants),
            "modules": list(facts.modules),
            "scope": list(facts.scope),
            "out": str(args.out) if args.out else None,
        },
        evidence=evidence,
    )
    maybe_emit(args, env)
    return 0


__all__ = [
    "PRESET_INVARIANTS",
    "BlueprintFacts",
    "build_facts",
    "load_spec",
    "main",
    "render_blueprint",
]


if __name__ == "__main__":
    raise SystemExit(main())
