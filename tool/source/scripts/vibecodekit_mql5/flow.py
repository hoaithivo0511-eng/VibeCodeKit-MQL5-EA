"""mql5-flow -- methodology driver (status / next).

A thin "driver" layer on top of :mod:`rri.step_workflow`
plus :mod:`rri.role_state` so a human OR an AI coding agent can ask the
kit two questions without memorising the 50+ sub-commands:

    mql5-flow status   # where am I in the 8 steps + sign-off state
    mql5-flow next     # what should I run next (concrete command hint)

The driver is read-only and git-independent: it derives progress purely
from ``.rri-state/<step>.done`` sentinels (written by
``mql5-step-workflow``) and from the canonical JSON sign-off artifacts.
The ``--explain`` flag prints the reasoning (mode -> required steps ->
which sentinel is missing) so the suggestion is never a black box.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .rri import step_workflow as sw
from . import _agent_io

TOOL = "mql5-flow"

# Concrete next-command hint per step. Kept as plain strings (not exec'd)
# so the driver stays advisory -- it never runs a gate on the user's
# behalf, it only points at the right door.
STEP_COMMAND_HINTS: dict[str, str] = {
    "scan": "mql5-scan            (new idea)  /  mql5-ea-intake (existing .mq5)",
    "rri": "mql5-rri              (RRI interview -> owner-interview.json)",
    "vision": "mql5-vision-gen       (SCAN/VISION pattern selection)",
    "blueprint": "mql5-blueprint-gen    then Homeowner signs: 'APPROVED by <name> at <YYYY-MM-DD>'",
    "tip": "mql5-tip-gen          (blueprint TIP review, critical_count must be 0)",
    "build": "mql5-auto-build --spec ea-spec.yaml   /  mql5-contract-build",
    "verify": "mql5-verify-report    (needs evidence/manifest.json release_eligible=true)",
    "refine": "mql5-refine           (loops back to RRI on findings)",
}


def _role_state(state_dir: Path, search_root: Path) -> dict[str, Any]:
    """Best-effort role/sign-off summary; never crashes the driver."""
    try:
        from .rri import role_state as rs
        return rs.compute_state(state_dir=state_dir, search_root=search_root)
    except Exception as exc:  # noqa: BLE001 - advisory only
        return {"error": str(exc)}


def compute_status(mode: str, state_dir: Path, search_root: Path) -> dict[str, Any]:
    required = list(sw.required_steps(mode))
    completed = list(sw.completed_steps(state_dir)) if Path(state_dir).exists() else []
    missing = [s for s in required if s not in completed]
    nxt = missing[0] if missing else None
    return {
        "mode": mode,
        "state_dir": str(state_dir),
        "steps": list(sw.STEPS),
        "required_steps": required,
        "completed_steps": completed,
        "missing_steps": missing,
        "next_step": nxt,
        "next_step_number": sw.STEP_NUMBERS.get(nxt) if nxt else None,
        "next_command": STEP_COMMAND_HINTS.get(nxt) if nxt else None,
        "complete": not missing,
        "sign_off": _role_state(state_dir, search_root),
    }


def _render_status(st: dict[str, Any], explain: bool) -> str:
    lines = [
        f"mode             : {st['mode']}",
        f"state dir        : {st['state_dir']}",
        "steps (8)        : " + " -> ".join(
            (s.upper() if s in st["completed_steps"] else s) for s in st["steps"]
        ),
        f"required         : {', '.join(st['required_steps'])}",
        f"completed        : {', '.join(st['completed_steps']) or '(none)'}",
    ]
    so = st.get("sign_off") or {}
    if isinstance(so, dict) and "consistency" in so:
        c = so["consistency"]
        tag = "OK" if (not c["checked"] or c["ok"]) else "MISMATCH"
        lines.append(f"sign-off (canon={so.get('canonical')}) consistency: {tag}")
    if st["complete"]:
        lines.append("status           : COMPLETE (all required steps done)")
    else:
        lines.append(f"next step        : {st['next_step_number']}. {st['next_step']}")
        lines.append(f"  run            : {st['next_command']}")
        if explain:
            lines.append(
                "  why            : "
                f"mode '{st['mode']}' requires {st['required_steps']}; "
                f"missing {st['missing_steps']}; first missing is the next step."
            )
    return "\n".join(lines) + "\n"


def _render_next(st: dict[str, Any], explain: bool) -> str:
    if st["complete"]:
        out = "All required steps complete for mode " + st["mode"] + ".\n"
        if explain:
            out += f"  (required {st['required_steps']}, all have a .done sentinel)\n"
        return out
    lines = [
        f"next step : {st['next_step_number']}. {st['next_step']}",
        f"run       : {st['next_command']}",
    ]
    if explain:
        lines.append(
            f"why       : mode '{st['mode']}' requires {st['required_steps']}; "
            f"completed {st['completed_steps']}; first missing is '{st['next_step']}'."
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog=TOOL,
        description="Methodology driver: where am I (status) and what to run next (next).",
    )
    ap.add_argument("command", choices=("status", "next"))
    ap.add_argument("--mode", choices=tuple(sw.MODE_REQUIRED_STEPS), default="personal")
    ap.add_argument("--state-dir", type=Path, default=Path(".rri-state"))
    ap.add_argument("--search-root", type=Path, default=Path("."))
    ap.add_argument("--explain", action="store_true",
                    help="Print the reasoning behind the suggestion.")
    _agent_io.add_json_flag(ap)
    _agent_io.add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    st = compute_status(args.mode, args.state_dir, args.search_root)

    if not getattr(args, "emit_json", False):
        if args.command == "status":
            sys.stdout.write(_render_status(st, args.explain))
        else:
            sys.stdout.write(_render_next(st, args.explain))

    summary = (
        f"{args.command}: mode={st['mode']} "
        + ("complete" if st["complete"] else f"next={st['next_step']}")
    )
    env = _agent_io.Envelope(
        tool=TOOL,
        ok=True,
        exit_code=0,
        summary=summary,
        data=st,
        evidence=[st["state_dir"]],
    )
    _agent_io.maybe_emit(args, env)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
