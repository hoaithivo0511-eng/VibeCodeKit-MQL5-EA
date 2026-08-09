"""mql5-rri-run -- make the RRI step executable.

The v2.x review found Step-2 (RRI) was only a markdown template: the
Homeowner had to hand-author ``owner-interview.json``. This driver turns
RRI into a real command. It collects answers (non-interactively via
``--answers``/``--set`` or interactively), seeds them through a chosen
safe pattern from the bank, writes the canonical ``owner-interview.json``,
and emits a Requirements Matrix so the human can see -- at a glance --
which requirements are pinned and which are still open.

Non-interactive is the default so the tool is CI- and agent-friendly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit
from . import ea_patterns
from .contract_utils import write_json, now_iso
from .owner_interview import (
    REQUIRED_PATHS,
    default_interview,
    get_path,
    validate_interview,
)

TOOL = "mql5-rri-run"

# Prompts used only in --interactive mode, keyed by dotted path.
_PROMPTS: dict[str, str] = {
    "owner.name": "Owner name",
    "capital.account_size": "Account size (number)",
    "broker.symbol": "Primary symbol",
    "strategy.intent": f"Strategy pattern {ea_patterns.list_patterns()}",
}


def _coerce(value: str) -> Any:
    """Coerce a string answer to bool/int/float/str."""
    low = value.strip().lower()
    if low in ("true", "yes", "y", "1"):
        return True
    if low in ("false", "no", "n", "0"):
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def set_path(data: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = data
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _flatten_answers(raw: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Accept both dotted keys and nested dicts in --answers files."""
    out: dict[str, Any] = {}
    for k, v in raw.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_answers(v, key))
        else:
            out[key] = v
    return out


def apply_pattern(interview: dict, pattern_id: str) -> list[str]:
    """Apply a pattern's owner-interview defaults; return applied paths."""
    pat = ea_patterns.get_pattern(pattern_id)
    if pat is None:
        raise ValueError(f"unknown pattern {pattern_id!r}")
    applied = []
    for path, val in pat.get("owner_interview_defaults", {}).items():
        set_path(interview, path, val)
        applied.append(path)
    return applied


def build_interview(
    *,
    answers: dict[str, Any] | None = None,
    pattern: str | None = None,
    approve: bool = False,
) -> dict:
    """Assemble a canonical owner-interview dict from answers + pattern."""
    answers = dict(answers or {})
    name = str(answers.pop("owner.name", None) or answers.pop("name", None) or "Owner")
    symbol = str(answers.get("broker.symbol") or answers.pop("symbol", None) or "XAUUSD")
    strategy = str(
        answers.get("strategy.intent")
        or pattern
        or answers.pop("strategy", None)
        or "grid-safe"
    )
    capital_raw = answers.get("capital.account_size", answers.pop("capital", 1500))
    try:
        capital = float(capital_raw)
    except (TypeError, ValueError):
        capital = 1500.0

    interview = default_interview(name, strategy, capital, symbol)

    if pattern:
        apply_pattern(interview, pattern)

    for path, val in answers.items():
        if "." not in path:
            continue  # ignore stray scalars already consumed above
        set_path(interview, path, val)

    set_path(interview, "broker.symbol", symbol)
    set_path(interview, "capital.account_size", capital)
    set_path(interview, "strategy.intent", strategy)
    interview["owner"]["approved_to_build"] = bool(approve)
    interview["rri_generated_at"] = now_iso()
    return interview


def requirements_matrix(interview: dict) -> str:
    """Render a Requirements Matrix markdown table over REQUIRED_PATHS."""
    rows = []
    for path in REQUIRED_PATHS:
        val = get_path(interview, path)
        status = "MISSING" if val in (None, "") else "set"
        shown = "" if val in (None, "") else str(val)
        rows.append((path, shown, status))
    missing = sum(1 for _, _, s in rows if s == "MISSING")
    lines = [
        "# Requirements Matrix (Step-2 RRI)",
        "",
        f"- Owner: {get_path(interview, 'owner.name')}",
        f"- Strategy: {get_path(interview, 'strategy.intent')}",
        f"- Approved to build: {get_path(interview, 'owner.approved_to_build')}",
        f"- Open requirements: {missing}/{len(rows)}",
        "",
        "| Requirement | Value | Status |",
        "| --- | --- | --- |",
    ]
    for path, shown, status in rows:
        mark = "OK" if status == "set" else "MISSING"
        lines.append(f"| `{path}` | {shown} | {mark} |")
    lines += [
        "",
        "> Generated by `mql5-rri-run`. `MISSING` rows block the build gate.",
        "",
    ]
    return "\n".join(lines)


def _load_answers_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml  # local import: only needed for YAML answers
        return _flatten_answers(yaml.safe_load(text) or {})
    return _flatten_answers(json.loads(text))


def _interactive(answers: dict[str, Any]) -> dict[str, Any]:
    for path, label in _PROMPTS.items():
        if path in answers:
            continue
        try:
            resp = input(f"{label}: ").strip()
        except EOFError:
            resp = ""
        if resp:
            answers[path] = _coerce(resp)
    return answers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Run RRI -> owner-interview.json + Requirements Matrix.")
    ap.add_argument("--out", type=Path, default=Path("owner-interview.json"),
                    help="Where to write the canonical owner-interview.json.")
    ap.add_argument("--matrix-out", type=Path, default=None,
                    help="Optional path for the Requirements Matrix markdown.")
    ap.add_argument("--answers", type=Path, default=None,
                    help="JSON/YAML file of answers (dotted keys or nested).")
    ap.add_argument("--set", action="append", default=[], metavar="path=value",
                    help="Override one dotted path (repeatable).")
    ap.add_argument("--pattern", default=None, choices=ea_patterns.list_patterns(),
                    help="Seed safe defaults from this strategy pattern.")
    ap.add_argument("--approve", action="store_true",
                    help="Set owner.approved_to_build=true (Homeowner sign-off).")
    ap.add_argument("--interactive", action="store_true",
                    help="Prompt for core fields not already provided.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    answers: dict[str, Any] = {}
    if args.answers is not None:
        if not args.answers.is_file():
            sys.stderr.write(f"error: answers file not found: {args.answers}\n")
            return 2
        answers.update(_load_answers_file(args.answers))
    for item in args.set:
        if "=" not in item:
            sys.stderr.write(f"error: --set expects path=value, got {item!r}\n")
            return 2
        k, v = item.split("=", 1)
        answers[k.strip()] = _coerce(v)
    if args.interactive:
        answers = _interactive(answers)

    try:
        interview = build_interview(answers=answers, pattern=args.pattern, approve=args.approve)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    write_json(args.out, interview)
    matrix = requirements_matrix(interview)
    if args.matrix_out is not None:
        args.matrix_out.parent.mkdir(parents=True, exist_ok=True)
        args.matrix_out.write_text(matrix, encoding="utf-8")

    report = validate_interview(interview)
    if not args.emit_json:
        sys.stdout.write(matrix)
        sys.stderr.write(f"wrote {args.out}"
                         + (f" + {args.matrix_out}" if args.matrix_out else "")
                         + f"  (ok={report['ok']})\n")

    env = Envelope(
        tool=TOOL,
        ok=bool(report["ok"]),
        exit_code=0 if report["ok"] else 2,
        summary=(f"RRI interview written ({'complete' if report['ok'] else 'incomplete'}); "
                 f"{len(report.get('missing', []))} missing"),
        data={
            "out": str(args.out),
            "matrix_out": str(args.matrix_out) if args.matrix_out else None,
            "validation": report,
            "approved_to_build": interview["owner"]["approved_to_build"],
            "pattern": args.pattern,
        },
        evidence=[str(args.out)],
    )
    maybe_emit(args, env)
    return 0 if report["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
