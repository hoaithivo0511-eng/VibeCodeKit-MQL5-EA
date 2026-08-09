"""EA composer for profile-required modules/hooks.

For grid-safe, this command writes required engine modules and patches the main
EA file with includes/global objects/OnTradeTransaction hook. It is conservative:
it does not rewrite strategy logic aggressively, but it gives the architecture
checker the required primitives and prevents release if raw close loops remain.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .engine_templates import write_engine_templates
from .architecture_check import check_architecture


def find_main_ea(project: Path) -> Path:
    experts = project / "Experts"
    mq5 = sorted(experts.glob("*.mq5")) if experts.exists() else sorted(project.rglob("*.mq5"))
    if not mq5:
        raise FileNotFoundError(f"no .mq5 file found under {project}")
    return mq5[0]


def include_root_name(project: Path) -> str:
    inc = project / "Include"
    if inc.exists():
        dirs = [p for p in inc.iterdir() if p.is_dir()]
        if dirs:
            return dirs[0].name
    return project.name


def patch_main_ea(ea_path: Path, root_name: str) -> dict[str, Any]:
    text = ea_path.read_text(encoding="utf-8", errors="ignore")
    changed = []

    includes = [
        f'#include <{root_name}/Execution/AsyncTradeExecutor.mqh>',
        f'#include <{root_name}/Execution/BasketCloseEngine.mqh>',
        f'#include <{root_name}/Risk/GridRiskGuard.mqh>',
        f'#include <{root_name}/State/PersistentStateStore.mqh>',
        f'#include <{root_name}/Telemetry/StructuredLogger.mqh>',
    ]
    insert_at = 0
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("#include"):
            insert_at = i + 1
    for inc in includes:
        if inc not in text:
            lines.insert(insert_at, inc)
            insert_at += 1
            changed.append(f"add include {inc}")

    text = "\n".join(lines) + "\n"

    globals_block = """
CAsyncTradeExecutor AsyncExec;
CBasketCloseEngine BasketCloser;
CGridRiskGuard GridRiskGuard;
CPersistentStateStore PersistentState;
CStructuredLogger StructuredLog;
"""
    if "CAsyncTradeExecutor AsyncExec;" not in text:
        # Insert after includes
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("#include"):
                insert_at = i + 1
        lines.insert(insert_at, globals_block.strip())
        text = "\n".join(lines) + "\n"
        changed.append("add async/grid-safe global objects")

    if "AsyncExec.Configure" not in text:
        marker = "int OnInit()"
        idx = text.find(marker)
        if idx >= 0:
            brace = text.find("{", idx)
            if brace >= 0:
                init_code = """
   int __ea_magic = (int)(AccountInfoInteger(ACCOUNT_LOGIN) % 100000) + 10000;
   AsyncExec.Configure(__ea_magic);
   BasketCloser.Configure(AsyncExec, __ea_magic);
   GridRiskGuard.Configure(0.0, 0.0, 0);   // caps disabled until tuned per strategy
   PersistentState.Configure(MQLInfoString(MQL_PROGRAM_NAME) + "." + _Symbol);
   StructuredLog.Configure(MQLInfoString(MQL_PROGRAM_NAME));
"""
                text = text[:brace+1] + init_code + text[brace+1:]
                changed.append("configure async/grid-safe objects in OnInit")
        else:
            text += """
int OnInit()
{
   int __ea_magic = (int)(AccountInfoInteger(ACCOUNT_LOGIN) % 100000) + 10000;
   AsyncExec.Configure(__ea_magic);
   BasketCloser.Configure(AsyncExec, __ea_magic);
   GridRiskGuard.Configure(0.0, 0.0, 0);   // caps disabled until tuned per strategy
   PersistentState.Configure(MQLInfoString(MQL_PROGRAM_NAME) + "." + _Symbol);
   StructuredLog.Configure(MQLInfoString(MQL_PROGRAM_NAME));
   return INIT_SUCCEEDED;
}
"""
            changed.append("add OnInit with async/grid-safe config")

    if "void OnTradeTransaction(" not in text:
        hook = """
void OnTradeTransaction(
   const MqlTradeTransaction& trans,
   const MqlTradeRequest& request,
   const MqlTradeResult& result
)
{
   AsyncExec.OnTradeTransaction(trans, request, result);
}
"""
        text += "\n" + hook
        changed.append("add OnTradeTransaction hook")

    ea_path.write_text(text, encoding="utf-8")
    return {"ea": str(ea_path), "changes": changed}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compose required EA engine modules/hooks for a profile.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--profile", default="grid-safe")
    ap.add_argument("--main-ea")
    ap.add_argument("--overwrite-engines", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    project = Path(args.project)
    root_name = include_root_name(project)
    include_root = project / "Include" / root_name
    written = write_engine_templates(include_root, overwrite=args.overwrite_engines)
    ea = Path(args.main_ea) if args.main_ea else find_main_ea(project)
    patch = patch_main_ea(ea, root_name)
    check = check_architecture(project, args.profile)

    report = {
        "schema_version": "1.0",
        "project": str(project),
        "profile": args.profile,
        "engine_files_written": written,
        "patch": patch,
        "architecture_check": check,
        "ok": check["ok"],
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
