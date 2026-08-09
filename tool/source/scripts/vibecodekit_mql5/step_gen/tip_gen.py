"""mql5-tip-gen — auto-emit ``step-5-tip.md`` from ``step-4-blueprint.md``.

Parses the Step-4 BLUEPRINT for two structured patterns:

1. ``## Invariants`` — ``- [ ] <invariant text>`` lines. Each becomes a
   row in the Technical Implementation Plan table.
2. ``## Module diagram`` — text inside the first ``` fenced block after
   that header. Lines that contain ``— `` (em-dash separated) are
   parsed as ``<module> — <description>`` and emitted in the modules
   block.

Output is a per-module table (module / interface / tests / size) +
explicit cross-reference from each invariant to ≥ 1 module + ≥ 1 test
so the Step-5 exit criterion can be checked mechanically.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .._agent_io import (
    Envelope,
    add_gate_report_flag,
    add_json_flag,
    maybe_emit,
)

TOOL = "mql5-tip-gen"

_INVARIANT_LINE = re.compile(r"^\s*-\s*\[[ xX]\]\s+(.+?)\s*$")


@dataclass(frozen=True)
class Module:
    name: str
    description: str


@dataclass(frozen=True)
class TIPFacts:
    invariants: tuple[str, ...]
    modules: tuple[Module, ...]
    coverage: dict[str, list[str]] = field(default_factory=dict)


def _extract_invariants(body: str) -> list[str]:
    lines = body.splitlines()
    out: list[str] = []
    in_section = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_section = stripped == "## Invariants"
            continue
        if not in_section:
            continue
        m = _INVARIANT_LINE.match(raw)
        if not m:
            continue
        text = m.group(1).strip()
        # Skip the seeded "manual fill" placeholders.
        if text.lower().startswith("todo"):
            continue
        out.append(text)
    return out


def _extract_modules(body: str) -> list[Module]:
    """Pull modules out of the first fenced block under '## Module diagram'."""

    lines = body.splitlines()
    out: list[Module] = []
    in_section = False
    in_fence = False
    seen_fence = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_section = stripped == "## Module diagram"
            in_fence = False
            seen_fence = False
            continue
        if not in_section:
            continue
        if stripped.startswith("```"):
            if not seen_fence:
                in_fence = True
                seen_fence = True
            else:
                in_fence = False
                in_section = False
            continue
        if not in_fence:
            continue
        if " — " in stripped:
            name, desc = stripped.split(" — ", 1)
            out.append(Module(name=name.strip(), description=desc.strip()))
        elif stripped:
            out.append(Module(name=stripped, description=""))
    return out


_MODULE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "CPipNormalizer.mqh": ("pip math", "cpipnormalizer", "pip"),
    "CMagicRegistry.mqh": ("magic number", "cmagicregistry", "magic"),
    "CRiskGuard.mqh": ("daily-loss", "stop-loss", "risk", "ap-1", "daily loss"),
    "Signal block": ("signal", "indicator", "ema", "rsi", "macd", "sar", "bbands"),
    "Filter block": ("filter", "time-window", "news"),
    "COnnxLoader.mqh": ("onnx", "ml", "inference", "model"),
    "_bridge.py": ("python", "bridge", "ipc"),
    "OnTradeTransaction": ("async", "ontradetransaction", "ordersendasync"),
}


def _assign_modules(invariant: str, modules: list[Module]) -> list[str]:
    """Pick which modules likely cover each invariant.

    Naive substring heuristic over module names + a small keyword table;
    fall back to the EA entry-point file (`.mq5`) so every invariant gets
    at least one module.
    """

    lower = invariant.lower()
    picked: list[str] = []
    for mod in modules:
        for keyword, hits in _MODULE_KEYWORDS.items():
            if keyword in mod.name and any(h in lower for h in hits):
                picked.append(mod.name)
                break
    if not picked:
        entry = next((m.name for m in modules if m.name.endswith(".mq5")), None)
        if entry is not None:
            picked.append(entry)
        else:
            picked.append("TODO: assign module")
    return picked


def build_facts(body: str) -> TIPFacts:
    invariants = _extract_invariants(body)
    modules = _extract_modules(body)
    coverage: dict[str, list[str]] = {
        inv: _assign_modules(inv, modules) for inv in invariants
    }
    return TIPFacts(
        invariants=tuple(invariants),
        modules=tuple(modules),
        coverage=coverage,
    )


def _test_name_for(invariant: str) -> str:
    """Derive a deterministic pytest-style test name from the invariant."""

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", invariant.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return f"test_{slug[:60]}"


def render_tip(facts: TIPFacts, *, source: Path | None = None) -> str:
    lines: list[str] = [
        "# Step 5 / 8 — TIP (Technical Implementation Plan)",
        "",
        "Decompose the BLUEPRINT into module-level work items with interfaces.",
        "",
        "## Inputs",
    ]
    if source is not None:
        lines.append(f"- `{source.name}`")
    else:
        lines.append("- `step-4-blueprint.md`")
    lines += [
        "",
        "## Module table",
        "",
        "| Module | Description | Interface (TODO) | Tests (TODO) | Size |",
        "|---|---|---|---|---|",
    ]
    if facts.modules:
        for mod in facts.modules:
            size = "S" if mod.name.endswith(".mqh") else ("M" if mod.name.endswith(".mq5") else "S")
            lines.append(
                f"| `{mod.name}` | {mod.description or '_TBD_'} | TODO | TODO | {size} |"
            )
    else:
        lines.append("| TODO | no `## Module diagram` parsed from blueprint | TODO | TODO | _S/M/L_ |")

    lines += [
        "",
        "## Invariant → module + test coverage",
        "",
        "| # | Invariant | Module(s) | Test name |",
        "|---|---|---|---|",
    ]
    if facts.invariants:
        for idx, inv in enumerate(facts.invariants, 1):
            mods = ", ".join(f"`{m}`" for m in facts.coverage.get(inv, []))
            lines.append(f"| {idx} | {inv} | {mods} | `{_test_name_for(inv)}` |")
    else:
        lines.append("| 1 | TODO — no `## Invariants` parsed from blueprint | TODO | TODO |")

    lines += [
        "",
        "## Exit criteria",
        f"- {len(facts.invariants)} blueprint invariant(s) each map to ≥ 1 module + ≥ 1 test",
        "- LOC ceilings honoured per module",
        "",
        f"> Generated by `{TOOL}` from "
        f"{len(facts.invariants)} invariant(s) + {len(facts.modules)} module(s).",
        "> Activities below MUST be re-ticked after manual refinement.",
        "",
        "## Activities",
        "- [ ] List each module to add / modify; assign owner",
        "- [ ] Define public interface (functions, struct layout, return contract)",
        "- [ ] Note test surface (unit tests required for each public function)",
        "",
        "> Sentinel: `touch .rri-state/tip.done` (only after every activity is ticked).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=TOOL)
    parser.add_argument(
        "blueprint_file", type=Path,
        help="Path to the Step-4 BLUEPRINT (step-4-blueprint.md).",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Write the rendered TIP to this path instead of stdout.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite --out if it already exists.",
    )
    add_json_flag(parser)
    add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    if not args.blueprint_file.is_file():
        env = Envelope(
            tool=TOOL, ok=False, exit_code=2,
            summary=f"blueprint not found: {args.blueprint_file}",
            data={"blueprint": str(args.blueprint_file)},
        )
        maybe_emit(args, env)
        if not args.emit_json:
            sys.stderr.write(f"error: file not found: {args.blueprint_file}\n")
        return 2

    body = args.blueprint_file.read_text(encoding="utf-8")
    facts = build_facts(body)
    rendered = render_tip(facts, source=args.blueprint_file)

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

    env = Envelope(
        tool=TOOL, ok=True, exit_code=0,
        summary=(
            f"rendered TIP with {len(facts.invariants)} invariant(s) "
            f"→ {len(facts.modules)} module(s)"
        ),
        data={
            "invariants": list(facts.invariants),
            "modules": [{"name": m.name, "description": m.description} for m in facts.modules],
            "coverage": {k: list(v) for k, v in facts.coverage.items()},
            "out": str(args.out) if args.out else None,
        },
        evidence=[str(args.blueprint_file)],
    )
    maybe_emit(args, env)
    return 0


__all__ = [
    "Module",
    "TIPFacts",
    "build_facts",
    "main",
    "render_tip",
]


if __name__ == "__main__":
    raise SystemExit(main())
