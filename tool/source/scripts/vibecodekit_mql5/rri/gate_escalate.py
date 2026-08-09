"""mql5-gate-escalate -- auto-raise an escalation when a gate FAILS.

Closes the evidence loop: a failing build/verify gate should not just
print red text and stop -- it should leave an auditable hand-off so the
right role picks it up. Given a gate report or an ``evidence/manifest.json``,
this records a Builder -> Contractor escalation when the run is not
release-eligible. Deduplicates against OPEN escalations so re-running a
still-failing gate does not spam the log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit
from . import escalation as esc

TOOL = "mql5-gate-escalate"


def _failure_view(report: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Return (failed, summary) from a report / evidence manifest / summary."""
    summary = report
    if isinstance(report.get("summary"), dict):
        summary = report["summary"]
    if "release_eligible" in report:
        failed = not bool(report.get("release_eligible"))
    elif "release_eligible" in summary:
        failed = not bool(summary.get("release_eligible"))
    elif "ok" in report:
        failed = not bool(report.get("ok"))
    else:
        failed = True  # no positive signal -> treat as not eligible
    return failed, summary


def _reason(summary: dict[str, Any]) -> str:
    bad = [k for k in ("command_ok", "compile_ok", "gate_ok", "backtest_ok", "evidence_ok")
           if k in summary and not summary.get(k)]
    skipped = summary.get("skipped_stages") or []
    unsafe = summary.get("unsafe_flags_used") or []
    bits = []
    if bad:
        bits.append("failing: " + ", ".join(bad))
    if skipped:
        bits.append("skipped: " + ", ".join(map(str, skipped)))
    if unsafe:
        bits.append("unsafe flags: " + ", ".join(map(str, unsafe)))
    detail = "; ".join(bits) if bits else "gate not release-eligible"
    return f"Gate FAILED -- {detail}. Builder hands off to Contractor for review."


def _open_dupe(log_path: Path, *, to_actor: str, artefact: str | None) -> bool:
    try:
        for e in esc.load_log(log_path):
            if e.status == "OPEN" and e.to_actor == to_actor and (e.artefact or None) == (artefact or None):
                return True
    except (OSError, ValueError, KeyError):
        return False
    return False


def escalate_on_fail(
    report: dict[str, Any],
    *,
    log_path: Path,
    from_actor: str = "tho-thi-cong",
    to_actor: str = "chu-thau",
    level: int = 2,
    artefact: str | None = None,
    dedupe: bool = True,
):
    """Raise an escalation iff the report is a failing gate. Returns the
    Escalation, or None when the gate passed or a dupe was suppressed."""
    failed, summary = _failure_view(report)
    if not failed:
        return None
    if dedupe and _open_dupe(log_path, to_actor=to_actor, artefact=artefact):
        return None
    return esc.raise_escalation(
        from_actor=from_actor, to_actor=to_actor, level=level,
        reason=_reason(summary), artefact=artefact, log_path=log_path,
    )


def _load_report(path: Path) -> dict[str, Any]:
    if path.is_dir():
        path = path / "evidence" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Auto-raise an escalation on a failing gate.")
    ap.add_argument("--report", type=Path, required=True,
                    help="Gate report / evidence dir / evidence manifest.json.")
    ap.add_argument("--log", type=Path, default=esc.DEFAULT_LOG, help="Escalation log path.")
    ap.add_argument("--from", dest="from_actor", default="tho-thi-cong", choices=list(esc.ACTORS))
    ap.add_argument("--to", dest="to_actor", default="chu-thau", choices=list(esc.ACTORS))
    ap.add_argument("--level", type=int, default=2, choices=list(esc.LEVELS))
    ap.add_argument("--artefact", default=None)
    ap.add_argument("--no-dedupe", dest="dedupe", action="store_false")
    ap.add_argument("--fail-on-escalate", action="store_true",
                    help="Exit 1 when an escalation is raised (CI-friendly).")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    if not args.report.exists():
        sys.stderr.write(f"error: report not found: {args.report}\n")
        return 2
    report = _load_report(args.report)
    raised = escalate_on_fail(
        report, log_path=args.log, from_actor=args.from_actor, to_actor=args.to_actor,
        level=args.level, artefact=args.artefact, dedupe=args.dedupe,
    )
    failed, _ = _failure_view(report)

    if not args.emit_json:
        if raised is not None:
            sys.stdout.write(f"escalation raised: {raised.id} ({raised.from_actor} -> {raised.to_actor}, L{raised.level})\n")
        elif failed:
            sys.stdout.write("gate failed but an OPEN escalation already exists (deduped)\n")
        else:
            sys.stdout.write("gate passed -- no escalation needed\n")

    env = Envelope(
        tool=TOOL, ok=True, exit_code=0,
        summary=(f"raised {raised.id}" if raised else ("deduped" if failed else "passed")),
        data={"gate_failed": failed, "escalation": (raised.to_dict() if raised else None),
              "log": str(args.log)},
    )
    maybe_emit(args, env)
    if args.fail_on_escalate and raised is not None:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
