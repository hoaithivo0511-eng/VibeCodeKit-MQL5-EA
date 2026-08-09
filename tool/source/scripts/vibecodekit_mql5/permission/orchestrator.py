"""Permission orchestrator — run the 7 layers in order, fail-fast.

the kit spec §11 — each layer is independently invocable, the orchestrator
just sequences them and stops at the first FAIL. Per the kit spec §11:

    Personal   : layers 1, 2, 3, 4, 7
    Team       : layers 1-5, 7
    Enterprise : layers 1-7

Each layer's `gate()` is called with the inputs supplied via flags;
missing inputs cause that layer to be skipped with status ``skipped``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import (
    layer1_source_lint,
    layer2_compile,
    layer3_ap_lint,
    layer4_checklist,
    layer5_methodology,
    layer6_quality_matrix,
    layer7_broker_safety,
)

MODE_LAYERS: dict[str, tuple[int, ...]] = {
    "personal": (1, 2, 3, 4, 7),
    "team": (1, 2, 3, 4, 5, 7),
    "enterprise": (1, 2, 3, 4, 5, 6, 7),
}


@dataclass
class OrchestratorReport:
    mode: str
    ok: bool = True
    layers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "ok": self.ok, "layers": self.layers}


def _run_layer(layer_id: int, args: argparse.Namespace) -> dict:
    if layer_id == 1:
        return layer1_source_lint.lint_source(args.source)
    if layer_id == 2:
        return layer2_compile.gate(args.source, args.compile_log)
    if layer_id == 3:
        return layer3_ap_lint.gate(args.source)
    if layer_id == 4:
        if args.trader_check_report:
            return layer4_checklist.gate(args.trader_check_report, args.mode)
        return layer4_checklist.gate_from_ea(args.source, args.mode)
    if layer_id == 5:
        return layer5_methodology.gate(args.state_dir, args.mode)
    if layer_id == 6:
        if not args.matrix:
            return {"ok": True, "skipped": True, "reason": "no --matrix provided"}
        return layer6_quality_matrix.gate(args.matrix, args.mode)
    if layer_id == 7:
        if not args.multibroker:
            return {"ok": True, "skipped": True, "reason": "no --multibroker provided"}
        return layer7_broker_safety.gate(args.multibroker, args.journal)
    raise ValueError(f"unknown layer: {layer_id}")


def run(args: argparse.Namespace) -> OrchestratorReport:
    report = OrchestratorReport(mode=args.mode)
    allow_skips = getattr(args, "unsafe_allow_skips", False) or getattr(args, "allow_skips", False)
    for layer_id in MODE_LAYERS[args.mode]:
        try:
            result = _run_layer(layer_id, args)
        except Exception as exc:  # noqa: BLE001 — surface as layer error
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        # A layer REQUIRED for this mode but skipped for lack of input must
        # NOT count as a pass, otherwise the gate reports PASS while silently
        # not running a mandatory check. Downgrade to failure unless allowed.
        if result.get("skipped") and not allow_skips:
            result = {
                **result,
                "ok": False,
                "error": result.get("reason", "required layer skipped (missing input)"),
            }
        result_with_id = {"layer": layer_id, **result}
        report.layers.append(result_with_id)
        if not result.get("ok", False):
            report.ok = False
            break  # fail-fast
    return report


def main() -> int:
    from .. import _agent_io

    ap = argparse.ArgumentParser(prog="mql5-permission")
    ap.add_argument("source", type=Path, help="EA .mq5 file")
    ap.add_argument("--mode", choices=tuple(MODE_LAYERS), default="personal")
    ap.add_argument("--compile-log", type=Path, default=None)
    ap.add_argument("--trader-check-report", type=Path, default=None)
    ap.add_argument("--state-dir", type=Path, default=Path(".rri-state"))
    ap.add_argument("--matrix", type=Path, default=None)
    ap.add_argument("--multibroker", type=Path, default=None)
    ap.add_argument("--journal", type=Path, default=None)
    ap.add_argument("--unsafe-allow-skips", dest="unsafe_allow_skips", action="store_true",
                    help="UNSAFE diagnostics only: allow required skipped layers. Result is not release eligible.")
    ap.add_argument("--allow-skips", action="store_true",
                    help="DEPRECATED alias for --unsafe-allow-skips; never release eligible.")
    _agent_io.add_json_flag(ap)
    _agent_io.add_gate_report_flag(ap)
    _agent_io.add_draft_flag(ap)
    args = ap.parse_args()
    report = run(args)

    envelope = _agent_io.Envelope(
        tool="mql5-permission",
        ok=report.ok,
        exit_code=0 if report.ok else 1,
        summary=(f"permission [{args.mode}]: "
                 f"{'PASS' if report.ok else 'FAIL'} "
                 f"({len(report.layers)} layer(s))"),
        data={**report.to_dict(), "unsafe_flags_used": (["--unsafe-allow-skips"] if (getattr(args, "unsafe_allow_skips", False) or getattr(args, "allow_skips", False)) else []), "release_eligible": False if (getattr(args, "unsafe_allow_skips", False) or getattr(args, "allow_skips", False)) else report.ok},
        evidence=[str(args.source)],
        matrix_dim="d_correctness",
        matrix_axis="integration",
        matrix_status="PASS" if report.ok else "FAIL",
    )
    _agent_io.apply_draft(envelope, args.draft)

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        print(json.dumps(report.to_dict(), indent=2))

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return envelope.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
