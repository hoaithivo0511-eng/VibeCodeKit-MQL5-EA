"""mql5-verify-report -- render a VERIFY report with embedded evidence.

The verify step previously left evidence scattered in ``evidence/`` with
no human-readable summary tying claims to hashes. This renders a single
VERIFY report that embeds every artefact path + sha256 + fixture flag and
states -- explicitly -- whether the run is release-eligible. It never
fabricates a PASS: the verdict mirrors ``summary.release_eligible``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit

TOOL = "mql5-verify-evidence"


def resolve_manifest(path: Path) -> Path:
    """Accept a dir (-> evidence/manifest.json), an evidence dir, or a file."""
    if path.is_dir():
        cand = path / "evidence" / "manifest.json"
        if cand.is_file():
            return cand
        cand2 = path / "manifest.json"
        if cand2.is_file():
            return cand2
    return path


def build_verify_report(manifest: dict[str, Any]) -> str:
    summary = manifest.get("summary", {})
    eligible = bool(manifest.get("release_eligible") or summary.get("release_eligible"))
    artifacts = manifest.get("artifacts", [])
    hashed = [a for a in artifacts if a.get("sha256")]
    fixtures = [a for a in artifacts if a.get("fixture")]
    verdict = "RELEASE-ELIGIBLE" if eligible else "NOT release-eligible"

    lines = [
        "# VERIFY report",
        "",
        f"- Verdict: **{verdict}**",
        f"- Status: `{summary.get('status', 'unknown')}`",
        f"- Created: {manifest.get('created_at_utc', 'n/a')}",
        f"- Artefacts: {len(artifacts)} ({len(hashed)} hashed, {len(fixtures)} fixture)",
        "",
        "## Check summary",
        "| Check | Result |",
        "| --- | --- |",
    ]
    for key in ("command_ok", "build_ok", "compile_ok", "gate_ok",
                "backtest_ok", "stress_ok", "evidence_ok", "hash_chain_ok"):
        if key in summary:
            lines.append(f"| {key} | {'OK' if summary.get(key) else 'FAIL'} |")
    skipped = summary.get("skipped_stages") or []
    unsafe = summary.get("unsafe_flags_used") or []
    if skipped:
        lines.append(f"| skipped_stages | {', '.join(map(str, skipped))} |")
    if unsafe:
        lines.append(f"| unsafe_flags | {', '.join(map(str, unsafe))} |")

    lines += ["", "## Evidence artefacts (path + sha256)"]
    if hashed:
        for a in hashed:
            tag = " _(fixture)_" if a.get("fixture") else ""
            lines.append(f"- `{a.get('path')}`{tag}")
            lines.append(f"  - sha256: `{a.get('sha256')}`")
    else:
        lines.append("- (no hashed artefacts -- cannot be release-eligible)")

    lines += [
        "",
        "> Verdict mirrors `summary.release_eligible`. A NOT-eligible report",
        "> must be handed off via `mql5-gate-escalate` and remediated with",
        "> `mql5-refine-tip` -- it is never a PASS.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Render a VERIFY report from an evidence manifest.")
    ap.add_argument("--evidence", type=Path, required=True,
                    help="Evidence dir, build out dir, or manifest.json.")
    ap.add_argument("--out", type=Path, default=None, help="Write the report markdown here.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    mpath = resolve_manifest(args.evidence)
    if not mpath.is_file():
        sys.stderr.write(f"error: evidence manifest not found: {mpath}\n")
        return 2
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    md = build_verify_report(manifest)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
    if not args.emit_json:
        sys.stdout.write(md if args.out is None else f"wrote {args.out}\n")

    summary = manifest.get("summary", {})
    eligible = bool(manifest.get("release_eligible") or summary.get("release_eligible"))
    env = Envelope(
        tool=TOOL, ok=True, exit_code=0,
        summary=f"verify report: {'release-eligible' if eligible else 'NOT eligible'}",
        data={"release_eligible": eligible, "manifest": str(mpath),
              "out": str(args.out) if args.out else None},
        evidence=[str(mpath)],
    )
    maybe_emit(args, env)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
