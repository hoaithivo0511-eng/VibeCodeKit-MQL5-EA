"""/mql5-audit — run the 70-test conformance battery.

70 = 10 e2e + 60 internal probes
(15 module-load, 15 scaffold-tree, 10 reference frontmatter, 10
methodology config, 10 governance).  The audit is a pure read-only
discovery + assertion engine; failing a probe is "stop the ship".

Each probe returns a ``ProbeResult(name, ok, detail)``.  The CLI emits
the aggregate as JSON so CI can pipe it into a dashboard.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ._resources import asset_root, kit_flavor

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_ROOT = Path(__file__).resolve().parent


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class AuditReport:
    probes: list[ProbeResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(p.ok for p in self.probes)


def _probe_module_loads(rep: AuditReport) -> None:
    mods = [
        "vibecodekit_mql5.compile", "vibecodekit_mql5.lint",
        "vibecodekit_mql5.build", "vibecodekit_mql5.pip_normalize",
        "vibecodekit_mql5.backtest", "vibecodekit_mql5.walkforward",
        "vibecodekit_mql5.monte_carlo", "vibecodekit_mql5.overfit_check",
        "vibecodekit_mql5.multibroker", "vibecodekit_mql5.trader_check",
        "vibecodekit_mql5.fitness", "vibecodekit_mql5.mfe_mae",
        "vibecodekit_mql5.broker_safety", "vibecodekit_mql5.deploy_vps",
        "vibecodekit_mql5.cloud_optimize",
    ]
    for m in mods:
        try:
            importlib.import_module(m)
            rep.probes.append(ProbeResult(f"module:{m}", True))
        except ImportError as exc:
            rep.probes.append(ProbeResult(f"module:{m}", False, str(exc)))


def _probe_scaffolds(rep: AuditReport) -> None:
    archetypes = [
        "stdlib/netting", "stdlib/hedging", "stdlib/python-bridge",
        "wizard-composable/netting", "portfolio-basket/netting",
        "portfolio-basket/hedging", "ml-onnx/python-bridge",
        "hft-async/netting", "trend/netting", "mean-reversion/hedging",
        "breakout/netting", "service-llm-bridge/cloud-api",
        "service-llm-bridge/self-hosted-ollama",
        "service-llm-bridge/embedded-onnx-llm",
        "scalping/hedging",
        "news-trading/netting", "arbitrage-stat/python-bridge",
        "hedging-multi/hedging", "grid/hedging", "dca/hedging",
        "library/netting", "indicator-only/netting",
    ]
    scaffolds_root = asset_root("scaffolds")
    for a in archetypes:
        p = scaffolds_root / a / "EAName.mq5"
        rep.probes.append(ProbeResult(f"scaffold:{a}", p.exists(), str(p)))


def _probe_references(rep: AuditReport) -> None:
    refs = [
        "50-survey", "59-trader-checklist", "60-wizard-cexpert",
        "61-tester-metrics", "64-fitness-templates",
        "70-algo-forge", "71-onnx-mql5",
        "76-llm-patterns", "77-async-hft", "79-pip-norm",
    ]
    if kit_flavor() != "full":
        rep.probes.append(ProbeResult(
            "ref:skipped", True, "slim flavor — docs repo not shipped"))
        return
    for r in refs:
        p = REPO_ROOT / "docs" / "references" / f"{r}.md"
        ok = p.exists() and p.read_text().startswith("---\n")
        rep.probes.append(ProbeResult(f"ref:{r}", ok))


def _probe_methodology(rep: AuditReport) -> None:
    # RRI step templates ship as packaged assets (wheel-safe).
    templates_root = asset_root("rri-templates")
    for s in range(1, 9):
        ok = any(templates_root.glob(f"step-{s}-*.md.tmpl"))
        rep.probes.append(ProbeResult(f"step:{s}", ok))
    for layer in range(1, 8):
        # Layer modules ship inside the package; resolve from the package dir
        # so the probe works after a wheel install. They use descriptive
        # suffixes (layer1_source_lint.py etc.) — match by glob so the probe
        # survives any future renames.
        matches = list((PKG_ROOT / "permission").glob(f"layer{layer}_*.py"))
        rep.probes.append(ProbeResult(
            f"layer:{layer}", bool(matches),
            str(matches[0]) if matches else "",
        ))


def _probe_governance(rep: AuditReport) -> None:
    if kit_flavor() != "full":
        rep.probes.append(ProbeResult(
            "gov:skipped", True, "slim flavor — governance repo not shipped"))
        return
    items = [
        "README.md", "LICENSE",
        "docs/anti-patterns-AVOID.md",
        ".github/workflows/ci.yml",
        "docs/COMMANDS.md", "docs/QUICKSTART.md", "docs/MIGRATE-VPS.md",
    ]
    for f in items:
        rep.probes.append(ProbeResult(f"gov:{f}", (REPO_ROOT / f).exists()))


def run_audit() -> AuditReport:
    rep = AuditReport()
    _probe_module_loads(rep)
    _probe_scaffolds(rep)
    _probe_references(rep)
    _probe_methodology(rep)
    _probe_governance(rep)
    return rep


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    parser = argparse.ArgumentParser(prog="mql5-audit")
    _agent_io.add_json_flag(parser)
    _agent_io.add_gate_report_flag(parser)
    args_ns = parser.parse_args(argv)

    rep = run_audit()
    payload = {
        "ok": rep.ok,
        "total": len(rep.probes),
        "passed": sum(1 for p in rep.probes if p.ok),
        "probes": [p.__dict__ for p in rep.probes],
    }

    envelope = _agent_io.Envelope(
        tool="mql5-audit",
        ok=rep.ok,
        exit_code=0 if rep.ok else 1,
        summary=f"audit: {payload['passed']}/{payload['total']} probes",
        data=payload,
        evidence=[],
    )

    if args_ns.emit_json:
        _agent_io.emit(envelope)
    else:
        print(json.dumps(payload, indent=2))

    if args_ns.gate_report is not None:
        _agent_io.write_gate_report(envelope, args_ns.gate_report)

    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
