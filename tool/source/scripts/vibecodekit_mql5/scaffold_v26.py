"""Per-project governance scaffolding for the v3 flow (v2.6-compatible).

Generates the governance artefacts a hardened EA project carries:

    EA-SPEC.yaml            (vkmql-new spec)
    AI-BUILD-CONTRACT.{md,json}, RISK-CONTRACT.yaml, BROKER-CONTRACT.yaml,
    EVIDENCE-CONTRACT.yaml, AGENTS.md   (vkmql-new contract)
    TASK-GRAPH.yaml, TIP-STATE.json     (vkmql-new tip-graph)

These are thin, additive verbs over the v2.5 ``vkmql-new`` family; they do
NOT replace the build/project scaffolds. Each ``*_main`` is wired into the
``vkmql-new`` dispatcher.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ._agent_io import Envelope, add_json_flag, emit
from . import ai_build_contract as abc
from . import decision_ledger as dl
from . import spec_schema_v26 as sv
from . import tip_state as ts

TOOL = "vkmql-new"


def _dump_yaml(data: dict) -> str:
    try:
        import yaml  # type: ignore

        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    except Exception:  # noqa: BLE001 — yaml should be present, but stay safe
        return json.dumps(data, indent=2)


def write_ea_spec(project_dir: Path, name: str, symbol: str, timeframe: str, *, force: bool) -> Path:
    spec = sv.default_spec_v26(name=name, symbol=symbol, timeframe=timeframe)
    path = project_dir / "EA-SPEC.yaml"
    if path.exists() and not force:
        return path
    project_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_yaml(spec), encoding="utf-8")
    return path


def _risk_contract(spec: dict) -> dict:
    risk = spec.get("risk", {})
    return {
        "schema_version": "3.0",
        "max_drawdown_pct": risk.get("max_drawdown_pct"),
        "max_daily_loss_pct": risk.get("max_daily_loss_pct"),
        "max_positions": risk.get("max_positions"),
        "stop_loss_required": risk.get("stop_loss_required", True),
        "forbidden_logic": spec.get("strategy", {}).get("forbidden_logic", ["unbounded_martingale"]),
    }


def _broker_contract(spec: dict) -> dict:
    ex = spec.get("execution", {})
    return {
        "schema_version": "3.0",
        "account_modes": ex.get("account_modes", ["netting", "hedging"]),
        "slippage_points_max": ex.get("slippage_points_max", 30),
        "spread_points_max": ex.get("spread_points_max", 40),
        "magic_number_policy": ex.get("magic_number_policy", "required"),
        "respect_stop_level": True,
        "respect_freeze_level": True,
    }


def _evidence_contract() -> dict:
    return {
        "schema_version": "3.0",
        "required": [
            "compile log + EX5 hash",
            "backtest report",
            "stress matrix report",
            "deep review report",
            "evidence manifest",
            "evidence hash chain",
        ],
        "policy": "No release claim without a verified evidence hash chain.",
        "immutable_paths": ["evidence/", "release/"],
        "release_authority": "windows-native",
        "wine_role": "development-ci-only",
        "remote_store": "optional",
    }


def _agents_md(name: str) -> str:
    return (
        f"# AGENTS.md — {name}\n\n"
        "AI coding tools working in this project MUST obey AI-BUILD-CONTRACT.md.\n\n"
        "## Hard rules\n"
        "- Only edit paths listed in AI-BUILD-CONTRACT.json `allowed_paths`.\n"
        "- NEVER edit `evidence/`, `release/`, or any contract file.\n"
        "- NEVER change approved EA-SPEC semantics or DECISIONS.yaml.\n"
        "- Lite mode MUST be promoted when trading behavior may change.\n"
        "- NEVER claim READY / LIVE-READY / PRODUCTION-READY without evidence.\n"
        "- Return a Completion Report (TIP-ID + STATUS + tests) for each TIP.\n"
        "- STATUS=DONE is not acceptance; the kit verifies before accepting.\n\n"
        "## Flow\n"
        "1. `vkmql-agent next-tip .`\n"
        "2. implement within allowed paths\n"
        "3. `vkmql-agent ingest-report . --tip <ID> --report report.md`\n"
        "4. `vkmql-check contract .` then `vkmql-check all .`\n"
    )


def _default_task_graph(name: str) -> dict:
    return {
        "schema_version": "3.0",
        "project": name,
        "tips": [
            {"id": "TIP-001", "title": "Scaffold project + risk guard",
             "depends_on": [], "allowed_paths": ["Experts/", "Include/"],
             "forbidden_paths": ["evidence/", "release/", "review/", "EA-SPEC.yaml"],
             "acceptance_commands": ["vkmql-check contract", "vkmql-check compile"],
             "evidence_required": ["evidence/compile-log.txt"],
             "rollback_plan": "git restore Experts/ Include/ (or delete the scaffolded EA dir)"},
            {"id": "TIP-002", "title": "Entry/exit logic",
             "depends_on": ["TIP-001"], "allowed_paths": ["Experts/", "Include/"],
             "forbidden_paths": ["evidence/", "release/", "review/", "EA-SPEC.yaml"],
             "acceptance_commands": ["vkmql-check compile", "vkmql-check contract"],
             "evidence_required": ["evidence/compile-log.txt"],
             "rollback_plan": "git revert the entry/exit commit; keep the TIP-001 scaffold"},
            {"id": "TIP-003", "title": "Backtest + stress matrix",
             "depends_on": ["TIP-002"], "allowed_paths": ["Tester/", "Presets/"],
             "forbidden_paths": ["evidence/", "release/", "Experts/", "Include/"],
             "acceptance_commands": ["vkmql-check backtest", "vkmql-check stress", "vkmql-check all"],
             "evidence_required": ["evidence/backtest-report.html", "Tester/matrix.yaml"],
             "rollback_plan": "discard Tester/ + Presets/ changes; re-run from TIP-002 output"},
        ],
    }


def generate_project_contracts(project_dir: Path, *, name: str) -> dict[str, str]:
    """Generate AI-BUILD-CONTRACT + RISK/BROKER/EVIDENCE contracts + AGENTS.md.

    Requires an existing EA-SPEC.yaml (run ``vkmql-new spec`` first).
    """
    written: dict[str, str] = {}
    spec_res = sv.load_spec_v26(project_dir / "EA-SPEC.yaml")
    spec = spec_res.spec if spec_res.spec else sv.default_spec_v26(name=name)

    contract_res = abc.generate_ai_build_contract(project_dir)
    if contract_res.md_path:
        written["AI-BUILD-CONTRACT.md"] = contract_res.md_path
    if contract_res.json_path:
        written["AI-BUILD-CONTRACT.json"] = contract_res.json_path

    # UI contract is always emitted as an explicit, auditable eighth artifact.
    contract_data = json.loads((project_dir / abc.CONTRACT_JSON).read_text(encoding="utf-8"))
    ui_path = project_dir / "UI-CONTRACT.yaml"
    ui_path.write_text(_dump_yaml({"schema_version": 1, "ui_contract": contract_data["ui_contract"]}), encoding="utf-8")
    written["UI-CONTRACT.yaml"] = str(ui_path)

    # Release trust root: WHICH runner key may sign release evidence. Shipped
    # empty on purpose -- an unpinned project stays INCOMPLETE rather than
    # trusting any key that happens to appear in the environment (ADV-6).
    from .trust_root import TRUST_FILE, template as _trust_template
    trust_path = project_dir / TRUST_FILE
    if not trust_path.exists():
        trust_path.write_text(_trust_template(), encoding="utf-8")
    written[TRUST_FILE] = str(trust_path)

    ledger = dl.ensure_ledger(project_dir, name)
    written[dl.LEDGER_NAME] = str(ledger)

    for fname, payload in (
        ("RISK-CONTRACT.yaml", _risk_contract(spec)),
        ("BROKER-CONTRACT.yaml", _broker_contract(spec)),
        ("EVIDENCE-CONTRACT.yaml", _evidence_contract()),
    ):
        p = project_dir / fname
        p.write_text(_dump_yaml(payload), encoding="utf-8")
        written[fname] = str(p)

    agents = project_dir / "AGENTS.md"
    agents.write_text(_agents_md(name), encoding="utf-8")
    written["AGENTS.md"] = str(agents)
    return written


# --- CLI mains (wired into vkmql-new) --------------------------------------

def spec_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vkmql-new spec")
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("--name", default="MyEA")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", "--timeframe", dest="timeframe", default="M5")
    ap.add_argument("--force", action="store_true")
    add_json_flag(ap)
    args = ap.parse_args(argv)
    path = write_ea_spec(Path(args.project_dir), args.name, args.symbol, args.timeframe, force=args.force)
    env = Envelope(tool="vkmql-new-spec", ok=True, exit_code=0,
                   summary=f"wrote {path}", data={"path": str(path)}, evidence=[str(path)])
    if args.emit_json:
        emit(env)
    else:
        sys.stdout.write(f"wrote {path}\n")
    return 0


def contract_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vkmql-new contract")
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("--name", default="MyEA")
    add_json_flag(ap)
    args = ap.parse_args(argv)
    project_dir = Path(args.project_dir)
    if not (project_dir / "EA-SPEC.yaml").is_file():
        write_ea_spec(project_dir, args.name, "XAUUSD", "M5", force=False)
    written = generate_project_contracts(project_dir, name=args.name)
    env = Envelope(tool="vkmql-new-contract", ok=True, exit_code=0,
                   summary=f"wrote {len(written)} contract artefact(s)",
                   data={"written": written}, evidence=[str(project_dir)])
    if args.emit_json:
        emit(env)
    else:
        sys.stdout.write("\n".join(f"wrote {p}" for p in written.values()) + "\n")
    return 0


def tipgraph_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vkmql-new tip-graph")
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("--name", default="MyEA")
    ap.add_argument("--from-graph", type=Path, default=None,
                    help="Build TIP-STATE from an existing TASK-GRAPH.yaml.")
    add_json_flag(ap)
    args = ap.parse_args(argv)
    project_dir = Path(args.project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    if args.from_graph and args.from_graph.is_file():
        import yaml  # type: ignore

        graph = yaml.safe_load(args.from_graph.read_text(encoding="utf-8")) or {}
    else:
        graph = _default_task_graph(args.name)
        (project_dir / "TASK-GRAPH.yaml").write_text(_dump_yaml(graph), encoding="utf-8")

    state = ts.state_from_task_graph(graph)
    state_path = ts.save_tip_state(project_dir, state)
    env = Envelope(tool="vkmql-new-tip-graph", ok=True, exit_code=0,
                   summary=f"wrote TASK-GRAPH + {len(state.tips)} TIP(s)",
                   data={"tip_state": str(state_path), "tip_count": len(state.tips)},
                   evidence=[str(project_dir)])
    if args.emit_json:
        emit(env)
    else:
        sys.stdout.write(f"wrote {state_path} ({len(state.tips)} TIPs)\n")
    return 0


__all__ = [
    "write_ea_spec",
    "generate_project_contracts",
    "spec_main",
    "contract_main",
    "tipgraph_main",
]
