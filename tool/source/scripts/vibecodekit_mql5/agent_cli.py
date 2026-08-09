"""vkmql-agent — the agent-orchestration surface (v3 governance).

This is the single command an external AI coding agent (Claude Code / Codex /
Cursor) drives to participate in the kit's TIP loop without memorising the
low-level modules. It ties together :mod:`tip_state`,
:mod:`completion_report_parser`, :mod:`ai_build_contract`, and
:mod:`contract_check`.

Subcommands::

    vkmql-agent export-context ./MyEA   # emit the agent context bundle (JSON)
    vkmql-agent next-tip ./MyEA         # the next runnable TIP (deps satisfied)
    vkmql-agent ingest-report ./MyEA --tip TIP-009 --report report.md
    vkmql-agent status ./MyEA           # TIP-state summary + contract check
    vkmql-agent repair-loop ./MyEA      # list TIPs needing repair

Every subcommand supports ``--json`` and emits the stable agent envelope.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ._agent_io import Envelope, add_json_flag, emit
from . import ai_build_contract as abc
from . import completion_report_parser as crp
from . import contract_check as cc
from . import tip_state as ts

TOOL = "vkmql-agent"


def _emit_or_print(args: argparse.Namespace, env: Envelope, text: str) -> int:
    if getattr(args, "emit_json", False):
        emit(env)
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return env.exit_code


def _cmd_export_context(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir)
    state = ts.load_tip_state(project_dir)
    contract_path = project_dir / abc.CONTRACT_JSON
    contract = None
    if contract_path.is_file():
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            contract = None
    next_tip = state.next_tip()
    context = {
        "project_dir": str(project_dir),
        "contract": contract,
        "tip_count": len(state.tips),
        "next_tip": next_tip.to_dict() if next_tip else None,
        "tips": [t.to_dict() for t in state.ordered()],
        "instructions": [
            "Only edit allowed_paths from AI-BUILD-CONTRACT.json.",
            "Never touch evidence/, release/, or the contract files.",
            "Return a Completion Report (TIP-ID + STATUS + tests) per TIP.",
            "STATUS=DONE requires real test evidence; it is not auto-accepted.",
        ],
    }
    env = Envelope(tool=TOOL, ok=True, exit_code=0,
                   summary=f"context for {len(state.tips)} TIP(s)",
                   data=context, evidence=[str(project_dir)])
    return _emit_or_print(args, env, json.dumps(context, indent=2))


def _cmd_next_tip(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir)
    state = ts.load_tip_state(project_dir)
    tip = state.next_tip()
    if tip is None:
        env = Envelope(tool=TOOL, ok=True, exit_code=0,
                       summary="no runnable TIP (all accepted or blocked on deps)",
                       data={"next_tip": None}, evidence=[str(project_dir)])
        return _emit_or_print(args, env, "no runnable TIP")
    env = Envelope(tool=TOOL, ok=True, exit_code=0,
                   summary=f"next TIP: {tip.id}",
                   data={"next_tip": tip.to_dict()}, evidence=[str(project_dir)])
    return _emit_or_print(args, env, f"{tip.id}: {tip.title}")


def _cmd_ingest_report(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir)
    state = ts.load_tip_state(project_dir)
    report_path = Path(args.report)
    if not report_path.is_file():
        env = Envelope(tool=TOOL, ok=False, exit_code=2,
                       summary=f"report not found: {report_path}",
                       data={}, evidence=[])
        return _emit_or_print(args, env, f"error: report not found: {report_path}")
    report = crp.parse_completion_report(report_path)
    tip_id = args.tip or report.tip_id
    if not tip_id:
        env = Envelope(tool=TOOL, ok=False, exit_code=2,
                       summary="no TIP-ID (pass --tip or include TIP-ID in report)",
                       data=report.to_dict(), evidence=[str(report_path)])
        return _emit_or_print(args, env, "error: no TIP-ID")
    tip = state.get(tip_id)
    val = crp.validate_completion_report(report, tip)
    data = {"report": report.to_dict(), "validation": val.to_dict(), "tip_id": tip_id}
    if not val.ok:
        env = Envelope(tool=TOOL, ok=False, exit_code=1,
                       summary=f"completion report rejected: {len(val.errors)} error(s)",
                       data=data, evidence=[str(report_path)])
        return _emit_or_print(args, env, "rejected:\n" + "\n".join(val.errors))
    if tip is not None:
        try:
            state.update_tip_from_report(tip_id, report)
            ts.save_tip_state(project_dir, state)
            data["new_state"] = state.get(tip_id).state  # type: ignore[union-attr]
        except (KeyError, ValueError) as exc:
            env = Envelope(tool=TOOL, ok=False, exit_code=1,
                           summary=f"state transition failed: {exc}",
                           data=data, evidence=[str(report_path)])
            return _emit_or_print(args, env, f"error: {exc}")
    env = Envelope(tool=TOOL, ok=True, exit_code=0,
                   summary=f"ingested report for {tip_id} (state={data.get('new_state', 'n/a')})",
                   data=data, evidence=[str(report_path)])
    return _emit_or_print(args, env, f"ingested {tip_id} -> {data.get('new_state', 'n/a')}")


def _cmd_status(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir)
    state = ts.load_tip_state(project_dir)
    by_state: dict[str, int] = {}
    for tip in state.ordered():
        by_state[tip.state] = by_state.get(tip.state, 0) + 1
    contract = cc.check_project_contract(project_dir)
    data = {
        "tip_count": len(state.tips),
        "by_state": by_state,
        "contract_ok": contract.ok,
        "contract_errors": contract.errors,
    }
    summary = (
        f"{len(state.tips)} TIP(s); states={by_state}; "
        f"contract={'OK' if contract.ok else 'FAILED'}"
    )
    env = Envelope(tool=TOOL, ok=contract.ok, exit_code=0 if contract.ok else 1,
                   summary=summary, data=data, evidence=[str(project_dir)])
    return _emit_or_print(args, env, summary)


def _cmd_repair_loop(args: argparse.Namespace) -> int:
    project_dir = Path(args.project_dir)
    state = ts.load_tip_state(project_dir)
    needs_repair = [
        t.to_dict() for t in state.ordered()
        if t.state in ("repair_required", "failed", "blocked")
    ]
    env = Envelope(tool=TOOL, ok=True, exit_code=0,
                   summary=f"{len(needs_repair)} TIP(s) need repair",
                   data={"needs_repair": needs_repair}, evidence=[str(project_dir)])
    text = "\n".join(f"{t['id']}: {t['state']}" for t in needs_repair) or "no TIPs need repair"
    return _emit_or_print(args, env, text)


_COMMANDS = {
    "export-context": _cmd_export_context,
    "next-tip": _cmd_next_tip,
    "ingest-report": _cmd_ingest_report,
    "status": _cmd_status,
    "repair-loop": _cmd_repair_loop,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Agent orchestration over the TIP loop.")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in _COMMANDS:
        sp = sub.add_parser(name)
        sp.add_argument("project_dir", type=Path, help="Path to the EA project directory.")
        if name == "ingest-report":
            sp.add_argument("--tip", default=None, help="TIP-ID (overrides the report's).")
            sp.add_argument("--report", required=True, help="Path to the Completion Report markdown.")
        add_json_flag(sp)
    args = ap.parse_args(argv)
    return _COMMANDS[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
