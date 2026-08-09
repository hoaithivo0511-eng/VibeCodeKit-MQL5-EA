"""Modular EA project generator for complex EA architectures."""
from __future__ import annotations

import argparse
from pathlib import Path
import json

from .engine_templates import write_engine_templates
from .ea_compose import patch_main_ea

PROFILES = {
    "complex-portfolio": ["Signal", "Risk", "Execution", "Regime", "Telemetry", "State", "Portfolio"],
    "ml-assisted": ["Signal", "Risk", "Execution", "Regime", "Telemetry", "State", "ML"],
    "prop-firm-risk": ["Signal", "Risk", "Execution", "Regime", "Telemetry", "State", "PropFirm"],
    "grid-safe": ["Signal", "Risk", "Execution", "Regime", "Telemetry", "State", "Grid"],
}

FILES = {
    "Config.mqh": """#pragma once\ninput double InpRiskPct = 1.0;\ninput int InpMagic = 0;          // REQUIRED: set a unique magic per EA/deployment\ninput int InpMaxLevels = 0;        // 0 = configure caps per strategy before live\ninput double InpFreezeDDPercent = 0.0; // tune per strategy/blueprint before live\ninput double InpMaxDDPercent = 0.0;    // tune per strategy/blueprint before live\n""",
    "Signal/ISignal.mqh": """#pragma once\nclass ISignal { public: virtual int Direction() { return 0; } };\n""",
    "Risk/IRiskModel.mqh": """#pragma once\nclass IRiskModel { public: virtual double Lots(double stop_points) { return 0.0; } };\n""",
    "Execution/IExecutionEngine.mqh": """#pragma once\nclass IExecutionEngine { public: virtual bool Buy(double lots) { return false; } virtual bool Sell(double lots) { return false; } };\n""",
    "Regime/MarketRegimeGuard.mqh": """#pragma once\nclass CMarketRegimeGuard { public: bool AllowTrading() { return true; } };\n""",
    "Telemetry/Logger.mqh": """#pragma once\nclass CLogger { public: void Info(string msg) { Print(msg); } };\n""",
    "State/StateStore.mqh": """#pragma once\nclass CStateStore { public: bool Load() { return true; } bool Save() { return true; } };\n""",
    "Portfolio/PortfolioRisk.mqh": """#pragma once\nclass CPortfolioRisk { public: bool AllowSymbol(string symbol) { return true; } };\n""",
    "ML/MLGate.mqh": """#pragma once\nclass CMLGate { public: bool ModelReady() { return false; } };\n""",
    "PropFirm/PropFirmGuard.mqh": """#pragma once\nclass CPropFirmGuard { public: bool DailyLossOk() { return true; } };\n""",
    "Grid/GridGuard.mqh": """#pragma once\nclass CGridGuard { public: bool AllowGridAdd() { return true; } };\n""",
}

EA_TEMPLATE = """#property strict\n#property version \"1.00\"\n#include <{include_root}/Config.mqh>\n#include <{include_root}/Signal/ISignal.mqh>\n#include <{include_root}/Risk/IRiskModel.mqh>\n#include <{include_root}/Execution/IExecutionEngine.mqh>\n#include <{include_root}/Regime/MarketRegimeGuard.mqh>\n#include <{include_root}/Telemetry/Logger.mqh>\n#include <{include_root}/State/StateStore.mqh>\n\nCMarketRegimeGuard Regime;\nCLogger Log;\nCStateStore State;\n\nint OnInit() {{\n  State.Load();\n  Log.Info(\"{name} initialized\");\n  return INIT_SUCCEEDED;\n}}\n\nvoid OnDeinit(const int reason) {{\n  State.Save();\n}}\n\nvoid OnTick() {{\n  if(!Regime.AllowTrading()) return;\n  // TODO: plug signal, risk, and execution modules here.\n}}\n"""


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name).strip("_") or "MyEA"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate modular EA project skeleton.")
    ap.add_argument("--name", required=True)
    ap.add_argument("--profile", default="complex-portfolio", choices=sorted(PROFILES))
    ap.add_argument("--out", default=".")
    args = ap.parse_args(argv)

    name = safe_name(args.name)
    base = Path(args.out) / name
    include_root = f"{name}"
    expert_dir = base / "Experts"
    inc_dir = base / "Include" / name
    expert_dir.mkdir(parents=True, exist_ok=True)
    inc_dir.mkdir(parents=True, exist_ok=True)

    modules = set(PROFILES[args.profile])
    for rel, content in FILES.items():
        top = rel.split("/")[0]
        if "/" in rel and top not in modules:
            continue
        path = inc_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    ea_path = expert_dir / f"{name}.mq5"
    ea_path.write_text(EA_TEMPLATE.format(name=name, include_root=include_root), encoding="utf-8")

    composed = None
    if args.profile == "grid-safe":
        write_engine_templates(inc_dir, overwrite=False)
        composed = patch_main_ea(ea_path, include_root)

    spec = {
        "name": name,
        "profile": args.profile,
        "architecture": "modular",
        "modules": sorted(modules),
        "validation_policy": "release requires actual compile/backtest/gate/evidence manifest",
        "composed_engines": composed,
    }
    (base / "ea-spec.yaml").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (base / "README.md").write_text(f"# {name}\n\nGenerated profile: `{args.profile}`.\n\nThis skeleton is not release eligible until actual MetaEditor compile, MT5 Strategy Tester, gates, and evidence manifest pass.\n", encoding="utf-8")
    print(json.dumps({"project": str(base), "ea": str(ea_path), "profile": args.profile, "modules": sorted(modules)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
