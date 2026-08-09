"""mql5-contract-gen — emit ``contract.md`` from blueprint + spec.

The Contract is the **second sign-off artefact** of the
Triangle of Power (Homeowner / Contractor / Builder) introduced by
VIBECODE Master v5.0 and adapted to the MQL5 domain by this kit.
It sits between Step-4 (BLUEPRINT) and Step-5 (TIP / Task Graph) and
serves two purposes:

1. **Crystallise scope** — what *will* be delivered, what *will not* be
   delivered, and which tech stack is being committed to. After the
   Homeowner reply ``CONFIRM by <name> at <YYYY-MM-DD>`` is appended, the
   contract is immutable; further changes require re-opening Step 3.
2. **Anchor the sign-off sentinel** — adds
   ``mql5-permission --layer 5 --enforce-sign-off`` which verifies both
   the BLUEPRINT CHECKPOINT (``APPROVED by …``) and the contract CONFIRM
   block before allowing the methodology gate to pass for team /
   enterprise mode.

The generator is deterministic — same blueprint + spec in, same contract
out (modulo timestamp lines, which are omitted by design). It does NOT
call any LLM. The Contractor LLM (Claude Chat) refines the narrative
``[ ]`` checklist items the generator seeds.

Output structure (six sections + CONFIRM block):

* DELIVERABLES — concrete artefacts the Builder must hand off.
* EXCLUSIONS — explicit "will not deliver" list to avoid scope creep.
* TECH STACK — preset / stack / dependencies the Builder is locked to.
* INVARIANTS — copied verbatim from BLUEPRINT (immutable cross-link).
* TASK GRAPH SUMMARY — high-level decomposition; the per-TIP DAG is
  produced by ``mql5-task-graph-gen``.
* ACCEPTANCE OVERVIEW — the four gate-categories the Verify Report
  (``mql5-verify-report``) will assess against.

The CONFIRM block at the bottom is the **sign-off line** the homeowner
must append verbatim:

    ## CONFIRM — chu-nha sign-off

    Reply "CONFIRM by <name> at <YYYY-MM-DD>" to release the Task Graph.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
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

TOOL = "mql5-contract-gen"


# Token the Contractor LLM must emit at the bottom of the blueprint so
# the homeowner has an explicit place to reply with APPROVED. The
# sign-off sentinel (layer-5 enforce-sign-off) looks for this exact
# heading + the matching reply line.
APPROVED_PATTERN = re.compile(
    r"^\s*APPROVED\s+by\s+\S+.*$",
    re.MULTILINE,
)
CONFIRM_PATTERN = re.compile(
    r"^\s*CONFIRM\s+by\s+\S+.*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class BlueprintFacts:
    """Structured view of a Step-4 BLUEPRINT artefact."""

    invariants: tuple[str, ...]
    modules: tuple[str, ...]
    state_machine: tuple[str, ...]
    has_approved: bool
    blueprint_sha256: str
    preset_hint: str | None
    stack_hint: str | None
    name_hint: str | None


@dataclass(frozen=True)
class ContractFacts:
    """Pre-render structure used by :func:`render_contract`."""

    spec: EaSpec
    blueprint: BlueprintFacts
    deliverables: tuple[str, ...]
    exclusions: tuple[str, ...]
    task_summary: tuple[str, ...]
    acceptance: tuple[str, ...] = field(default_factory=tuple)


def _extract_section_items(body: str, header: str) -> list[str]:
    """Collect ``- <item>`` lines under a ``## <header>`` heading.

    Stops at the next ``## `` heading or end of file.
    """

    items: list[str] = []
    in_section = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == f"## {header}"
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            # Strip the optional `[ ]` / `[x]` checkbox prefix so the
            # contract carries the human-readable invariant text only.
            text = stripped[2:].strip()
            text = re.sub(r"^\[[ xX]\]\s*", "", text).strip()
            if text:
                items.append(text)
    return items


def _extract_code_block(body: str, header: str) -> list[str]:
    """Return the inner lines of the first fenced block under a heading."""

    lines = body.splitlines()
    out: list[str] = []
    in_section = False
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == f"## {header}"
            in_fence = False
            continue
        if not in_section:
            continue
        if stripped.startswith("```"):
            if in_fence:
                # Stop after the first closing fence.
                return out
            in_fence = True
            continue
        if in_fence:
            out.append(line.rstrip())
    return out


def _hash_blueprint(body: str) -> str:
    """SHA-256 of the blueprint body with any prior APPROVED line removed.

    The sentinel uses this so re-signing after a body edit fails — i.e.
    the homeowner cannot APPROVE one version of the blueprint and then
    silently swap it for another.
    """

    canonical = APPROVED_PATTERN.sub("", body).strip() + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_hint(body: str, label: str) -> str | None:
    """Best-effort label scrape; returns None when not found."""

    pattern = re.compile(
        rf"^[\-\s\*]*{re.escape(label)}\s*[:\-]\s*`?([A-Za-z0-9_\-./]+)`?",
        re.MULTILINE | re.IGNORECASE,
    )
    match = pattern.search(body)
    if match:
        return match.group(1).strip()
    return None


def parse_blueprint(body: str) -> BlueprintFacts:
    """Parse a Step-4 BLUEPRINT markdown into structured facts."""

    invariants = tuple(_extract_section_items(body, "Invariants"))
    modules = tuple(_extract_code_block(body, "Module diagram"))
    state_machine = tuple(_extract_code_block(body, "State machine"))
    has_approved = bool(APPROVED_PATTERN.search(body))
    # Try to recover preset / stack / name from the BLUEPRINT header so
    # callers that only have the blueprint (no spec) can still get a
    # partial contract for review.
    preset_hint = _extract_hint(body, "preset")
    stack_hint = _extract_hint(body, "stack")
    name_hint = _extract_hint(body, "Name")
    return BlueprintFacts(
        invariants=invariants,
        modules=modules,
        state_machine=state_machine,
        has_approved=has_approved,
        blueprint_sha256=_hash_blueprint(body),
        preset_hint=preset_hint,
        stack_hint=stack_hint,
        name_hint=name_hint,
    )


# Per-preset baseline deliverables. Same shape as
# blueprint_gen.PRESET_INVARIANTS so reviewers cross-check easily.
PRESET_DELIVERABLES: dict[str, tuple[str, ...]] = {
    "trend": (
        "Compiled `.ex5` produced from the scaffold (no MQL5 build errors)",
        "Strategy Tester XML proving the EA trades the declared symbol",
        "Backtest report parsed by `mql5-backtest` with PF / Sharpe / DD",
        "Walk-forward IS/OOS report parsed by `mql5-walkforward`",
        "7-layer permission gate PASS in the declared mode",
    ),
    "mean-reversion": (
        "Compiled `.ex5` produced from the scaffold",
        "Strategy Tester XML proving the EA respects the cooldown rule",
        "Backtest + walk-forward reports proving the strategy stays in-distribution",
        "`mql5-overfit-check` PASS with default thresholds",
        "7-layer permission gate PASS in the declared mode",
    ),
    "breakout": (
        "Compiled `.ex5` produced from the scaffold",
        "Strategy Tester XML proving entries trigger only on bar close",
        "Backtest + walk-forward reports",
        "Multibroker spread differential report (`mql5-multibroker`)",
        "7-layer permission gate PASS in the declared mode",
    ),
    "scalping": (
        "Compiled `.ex5` with spread guard active",
        "Strategy Tester XML covering a session-bounded window",
        "Backtest + walk-forward reports under each broker spread profile",
        "`mql5-monte-carlo` resampled equity curve report",
        "7-layer permission gate PASS in the declared mode",
    ),
    "hft-async": (
        "Compiled `.ex5` with OrderSendAsync + OnTradeTransaction wired",
        "Strategy Tester XML demonstrating async fill handling",
        "Latency budget report (p95 OnTick → OrderSendAsync ≤ 5 ms)",
        "Walk-forward + Monte-Carlo reports",
        "7-layer permission gate PASS in team mode (async is team-only)",
    ),
    "news-trading": (
        "Compiled `.ex5` with news blackout filter wired",
        "Strategy Tester XML with at least one blacked-out event in range",
        "WebRequest path moved outside OnTick / OnTimer (AP-17 check passes)",
        "Backtest + walk-forward reports",
        "7-layer permission gate PASS in the declared mode",
    ),
    "ml-onnx": (
        "Compiled `.ex5` loading a versioned ONNX model",
        "Inference p95 latency report ≤ 1 ms",
        "Fallback path verified when model returns no signal",
        "Backtest + walk-forward reports under the ONNX inference path",
        "7-layer permission gate PASS in the declared mode",
    ),
    "service-llm-bridge": (
        "Compiled `.ex5` with LLM call moved outside OnTick (AP-17 passes)",
        "LLM response schema validated before consumption",
        "Backtest XML proving the EA still trades when bridge degrades",
        "Walk-forward report",
        "7-layer permission gate PASS in the declared mode",
    ),
    "service": (
        "Compiled side-car artefact (no direct OrderSend)",
        "Heartbeat / health-check endpoint demonstrably reachable",
        "Logs streamed to documented sink",
        "Integration walk-through proving the parent EA consumes the service",
        "7-layer permission gate PASS in the declared mode",
    ),
    "grid": (
        "Compiled `.ex5` with bounded grid depth",
        "Strategy Tester XML covering the worst grid expansion in range",
        "Backtest + walk-forward reports",
        "`mql5-monte-carlo` equity curve report",
        "7-layer permission gate PASS in the declared mode",
    ),
    "dca": (
        "Compiled `.ex5` with bounded DCA add count",
        "Strategy Tester XML covering worst-case DCA chain",
        "Backtest + walk-forward reports",
        "Daily-loss cap respected under DCA stress",
        "7-layer permission gate PASS in the declared mode",
    ),
    "hedging-multi": (
        "Compiled `.ex5` with per-leg magic numbers reserved",
        "Strategy Tester XML covering both legs over the same window",
        "Hedge correlation report verified at OnInit",
        "Backtest + walk-forward reports per leg",
        "7-layer permission gate PASS in the declared mode",
    ),
    "arbitrage-stat": (
        "Compiled `.ex5` with cointegration rolling-window logic",
        "Strategy Tester XML proving both legs trade synchronously",
        "Backtest + walk-forward reports per leg",
        "Cointegration robustness report (z-score drift bounded)",
        "7-layer permission gate PASS in the declared mode",
    ),
    "portfolio-basket": (
        "Compiled `.ex5` with per-basket-leg magic numbers reserved",
        "Strategy Tester XML covering the basket-rebalancing window",
        "Backtest + walk-forward reports for the basket as a whole",
        "Daily-loss cap respected with concurrent basket positions",
        "7-layer permission gate PASS in the declared mode",
    ),
    "stdlib": (
        "Compiled `.ex5` produced from the scaffold",
        "Strategy Tester XML proving the EA trades the declared symbol",
        "Backtest report parsed by `mql5-backtest`",
        "7-layer permission gate PASS in the declared mode",
    ),
}


# Per-preset baseline exclusions — what the Builder is NOT delivering
# under this contract. Forces the Homeowner to acknowledge gaps before
# CONFIRM. The list is short by design — the homeowner can append more.
PRESET_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "trend": (
        "Live brokerage account integration beyond demo (deploy phase only)",
        "Manual override UI in the EA chart (not in scope for this contract)",
    ),
    "mean-reversion": (
        "Adaptive cooldown windows (fixed cooldown only in this contract)",
        "Real-time correlation cross-check with other EAs",
    ),
    "breakout": (
        "Sub-tick entry timing — entries only on bar close",
        "Cross-symbol confirmation (single-symbol contract)",
    ),
    "scalping": (
        "Tick-level news filtering — only session-window time guard",
        "Slippage compensation via partial fills (single-shot OrderSend)",
    ),
    "hft-async": (
        "Co-location latency tuning — out of scope (deploy phase)",
        "FPGA / kernel-bypass optimisations",
    ),
    "news-trading": (
        "Sentiment analysis — only event time blackout in this contract",
        "Live news WebSocket — `mql5-llm-context` cache only",
    ),
    "ml-onnx": (
        "Online model retraining — model is frozen for the contract window",
        "Multi-model ensembling (single model file in this contract)",
    ),
    "service-llm-bridge": (
        "LLM fine-tuning — only prompt-based interaction",
        "Multi-LLM routing — single bridge endpoint per contract",
    ),
    "service": (
        "End-to-end trade execution — service runs as side-car only",
    ),
    "grid": (
        "Martingale add-on — grid depth is hard-capped in this contract",
        "Adaptive grid spacing — fixed spacing only",
    ),
    "dca": (
        "Pyramid scaling on profit — DCA only on adverse moves in this contract",
        "Adaptive add intervals — fixed intervals only",
    ),
    "hedging-multi": (
        "Dynamic leg sizing — fixed leg ratio in this contract",
    ),
    "arbitrage-stat": (
        "Live order-book quoting — taker-only execution",
    ),
    "portfolio-basket": (
        "Dynamic basket weights — fixed weights for the contract window",
    ),
    "stdlib": (
        "Custom indicator authoring — stdlib indicators only in this contract",
    ),
}


def _task_summary(spec: EaSpec, blueprint: BlueprintFacts) -> tuple[str, ...]:
    """High-level task list — ``mql5-task-graph-gen`` expands this."""

    base: list[str] = [
        f"TIP-001 — scaffold `{spec.name}.mq5` from `{spec.preset}/{spec.stack}` archetype",
        f"TIP-002 — wire risk guard ({spec.risk.per_trade_pct}% per trade, "
        f"{spec.risk.daily_loss_pct}% daily-loss cap)",
        f"TIP-003 — implement signal block on `{spec.symbol}` / `{spec.timeframe}`",
    ]
    if spec.signals:
        for idx, sig in enumerate(spec.signals, start=4):
            base.append(
                f"TIP-{idx:03d} — implement signal `{sig.kind}` with declared params",
            )
    next_idx = len(base) + 1
    if spec.filters:
        base.append(
            f"TIP-{next_idx:03d} — implement filter chain "
            f"({', '.join(sorted({f.kind for f in spec.filters}))})",
        )
        next_idx += 1
    base.append(
        f"TIP-{next_idx:03d} — produce backtest + walk-forward XML on declared range",
    )
    next_idx += 1
    base.append(
        f"TIP-{next_idx:03d} — pass `mql5-permission --mode {spec.mode}` gate",
    )
    return tuple(base)


def _acceptance_categories(spec: EaSpec) -> tuple[str, ...]:
    """Four-line summary of what the Verify Report will measure."""

    return (
        "REQ-COVERAGE — every BLUEPRINT invariant is exercised by ≥ 1 test",
        "TECH-HEALTH — `mql5-lint`, `mql5-method-hiding-check`, "
        "`mql5-trader-check` all PASS",
        "BACKTEST-EVIDENCE — `mql5-backtest` + `mql5-walkforward` + "
        "`mql5-monte-carlo` reports parsed and within thresholds",
        f"PERMISSION-GATE — `mql5-permission --mode {spec.mode}` PASS",
    )


def build_facts(spec: EaSpec, blueprint: BlueprintFacts) -> ContractFacts:
    deliverables = PRESET_DELIVERABLES.get(
        spec.preset, PRESET_DELIVERABLES["stdlib"]
    )
    exclusions = PRESET_EXCLUSIONS.get(
        spec.preset, PRESET_EXCLUSIONS["stdlib"]
    )
    return ContractFacts(
        spec=spec,
        blueprint=blueprint,
        deliverables=deliverables,
        exclusions=exclusions,
        task_summary=_task_summary(spec, blueprint),
        acceptance=_acceptance_categories(spec),
    )


def render_contract(
    facts: ContractFacts,
    *,
    blueprint_path: Path | None = None,
    spec_path: Path | None = None,
) -> str:
    spec = facts.spec
    bp = facts.blueprint
    lines: list[str] = [
        "# Contract — chu-nha ↔ chu-thau handoff ()",
        "",
        "_Emitted by `mql5-contract-gen`. Modify the seeded bullets, but do_",
        "_NOT delete sections — the layer-5 sign-off sentinel parses them._",
        "",
        "## Inputs",
    ]
    if blueprint_path is not None:
        lines.append(f"- BLUEPRINT: `{blueprint_path.name}`")
    else:
        lines.append("- BLUEPRINT: (inline)")
    lines.append(f"  - sha256: `{bp.blueprint_sha256}`")
    if not bp.has_approved:
        lines.append(
            "  - **WARNING**: BLUEPRINT lacks an `APPROVED by …` line — "
            "homeowner sign-off MUST be completed before this contract "
            "is signed (the layer-5 sentinel will FAIL otherwise)."
        )
    if spec_path is not None:
        lines.append(f"- EA-SPEC: `{spec_path.name}`")
    else:
        lines.append("- EA-SPEC: (inline)")

    lines += [
        "",
        "## EA identity",
        f"- Name: `{spec.name}`",
        f"- Symbol / TF: `{spec.symbol}` / `{spec.timeframe}`",
        f"- Mode: `{spec.mode}`",
        f"- Preset / stack: `{spec.preset}` / `{spec.stack}`",
        f"- Risk: per-trade `{spec.risk.per_trade_pct}%`, "
        f"daily-loss cap `{spec.risk.daily_loss_pct}%`",
        "",
        "## DELIVERABLES",
        "_The Builder MUST produce every item below before the Verify_",
        "_Report can return OVERALL STATUS = READY._",
        "",
    ]
    for item in facts.deliverables:
        lines.append(f"- [ ] {item}")

    lines += [
        "",
        "## EXCLUSIONS",
        "_Items the Homeowner explicitly acknowledges are NOT part of_",
        "_this contract. Edit freely; deleting items widens scope._",
        "",
    ]
    for item in facts.exclusions:
        lines.append(f"- {item}")

    lines += [
        "",
        "## TECH STACK",
        "- Language: MQL5 (MetaTrader 5)",
        f"- Preset: `{spec.preset}`",
        f"- Stack: `{spec.stack}`",
        "- Required Includes (from BLUEPRINT modules):",
    ]
    if bp.modules:
        for mod in bp.modules:
            stripped = mod.strip()
            if stripped:
                lines.append(f"  - `{stripped}`")
    else:
        lines.append("  - (none parsed — BLUEPRINT lacks a `## Module diagram` block)")

    lines += [
        "",
        "## INVARIANTS — copied verbatim from BLUEPRINT",
        "_The Builder cannot violate these. Verify Report cross-checks._",
        "",
    ]
    if bp.invariants:
        for inv in bp.invariants:
            lines.append(f"- {inv}")
    else:
        lines.append(
            "- (none parsed — BLUEPRINT lacks a `## Invariants` section)"
        )

    lines += [
        "",
        "## TASK GRAPH SUMMARY",
        "_High-level decomposition. `mql5-task-graph-gen` will_",
        "_expand each line into a `tasks/TIP-NNN.md` with Gherkin specs._",
        "",
    ]
    for tip in facts.task_summary:
        lines.append(f"- {tip}")

    lines += [
        "",
        "## ACCEPTANCE OVERVIEW",
        "_The Verify Report (`mql5-verify-report`) measures these four_",
        "_categories. OVERALL STATUS = READY requires all four PASS._",
        "",
    ]
    for cat in facts.acceptance:
        lines.append(f"- {cat}")

    lines += [
        "",
        "## CONFIRM — chu-nha sign-off",
        "",
        "Reply with the **exact** line below at the bottom of this file",
        "after reviewing every section above:",
        "",
        "```",
        "CONFIRM by <your name> at <YYYY-MM-DD>",
        "```",
        "",
        f"_Tool: `{TOOL}` — generated from BLUEPRINT sha256 prefix "
        f"`{bp.blueprint_sha256[:12]}…`_",
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
        "blueprint",
        type=Path,
        help="Path to step-4-blueprint.md (Step-4 / mql5-blueprint-gen output).",
    )
    parser.add_argument(
        "--ea-spec",
        type=Path,
        default=None,
        help="Path to ea-spec.yaml; required when the blueprint header does "
        "not declare preset / stack / name (recommended in all modes).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the contract markdown to this path (default: stdout).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite --out if it already exists.",
    )
    add_json_flag(parser)
    add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    if not args.blueprint.is_file():
        env = Envelope(
            tool=TOOL,
            ok=False,
            exit_code=2,
            summary=f"blueprint not found: {args.blueprint}",
            data={"blueprint": str(args.blueprint)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(f"error: file not found: {args.blueprint}\n")
        return 2

    blueprint_body = args.blueprint.read_text(encoding="utf-8")
    bp = parse_blueprint(blueprint_body)

    if args.ea_spec is not None:
        if not args.ea_spec.is_file():
            env = Envelope(
                tool=TOOL,
                ok=False,
                exit_code=2,
                summary=f"ea-spec not found: {args.ea_spec}",
                data={"ea_spec": str(args.ea_spec)},
            )
            maybe_emit(args, env)
            if not args.emit_json:
                sys.stderr.write(f"error: file not found: {args.ea_spec}\n")
            return 2
        try:
            spec = load_spec(args.ea_spec)
        except Exception as exc:  # noqa: BLE001
            env = Envelope(
                tool=TOOL,
                ok=False,
                exit_code=2,
                summary=f"ea-spec invalid: {exc}",
                data={"ea_spec": str(args.ea_spec), "error": str(exc)},
            )
            maybe_emit(args, env)
            if not args.emit_json:
                sys.stderr.write(f"error: invalid spec: {exc}\n")
            return 2
    else:
        # Spec is strongly recommended. If the blueprint header has both
        # preset / stack / name hints we *could* fabricate a minimal
        # spec, but the deliverable list quality drops noticeably; force
        # the operator to be explicit.
        env = Envelope(
            tool=TOOL,
            ok=False,
            exit_code=2,
            summary="--ea-spec is required (contract needs spec for "
            "deliverable + exclusion + acceptance derivation)",
            data={"blueprint": str(args.blueprint)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(
                "error: --ea-spec <path> is required (contracts "
                "derive deliverables / exclusions / acceptance categories "
                "from the EA spec; pass the same ea-spec.yaml that produced "
                "the blueprint)\n"
            )
        return 2

    facts = build_facts(spec, bp)
    rendered = render_contract(
        facts, blueprint_path=args.blueprint, spec_path=args.ea_spec
    )

    if args.out is not None:
        if args.out.exists() and not args.force:
            env = Envelope(
                tool=TOOL,
                ok=False,
                exit_code=2,
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

    evidence: list[str] = [str(args.blueprint), str(args.ea_spec)]
    env = Envelope(
        tool=TOOL,
        ok=True,
        exit_code=0,
        summary=(
            f"rendered contract for {spec.preset}/{spec.stack} with "
            f"{len(facts.deliverables)} deliverable(s), "
            f"{len(facts.exclusions)} exclusion(s), "
            f"{len(facts.task_summary)} task-summary line(s)"
        ),
        data={
            "preset": spec.preset,
            "stack": spec.stack,
            "blueprint_sha256": bp.blueprint_sha256,
            "blueprint_approved": bp.has_approved,
            "deliverables": list(facts.deliverables),
            "exclusions": list(facts.exclusions),
            "task_summary": list(facts.task_summary),
            "acceptance": list(facts.acceptance),
            "out": str(args.out) if args.out else None,
        },
        evidence=evidence,
    )
    maybe_emit(args, env)
    return 0


__all__ = [
    "APPROVED_PATTERN",
    "BlueprintFacts",
    "CONFIRM_PATTERN",
    "ContractFacts",
    "PRESET_DELIVERABLES",
    "PRESET_EXCLUSIONS",
    "build_facts",
    "load_spec",
    "main",
    "parse_blueprint",
    "render_contract",
]


if __name__ == "__main__":
    raise SystemExit(main())
