"""vkmql-check status - the golden-flow status block.

Reads the SINGLE canonical evidence manifest (``<out-dir>/evidence/manifest.json``
written by :mod:`release_policy` / :mod:`evidence_v2`) and renders the whole
end-to-end flow at a glance so a user never has to guess where a build stands:

    BUILD -> COMPILE -> BACKTEST -> GATE -> RELEASE

plus exactly one ``Next action:`` line that names the next command to run.
No manifest yet => the flow has not started; we say so instead of inventing a
status. ``release_eligible`` is read from the manifest verbatim - this tool
never recomputes eligibility, it only reports what the canonical predicate
(:func:`release_policy.compute_release_eligible`) already decided.

The optional ``--html`` flag renders the same status as a self-contained
``report.html`` dashboard (no external CSS/JS) for sharing or publishing.
"""
from __future__ import annotations

import argparse
import json
import string as _string
import sys
from pathlib import Path
from typing import Any

# Ordered golden-flow steps -> (manifest summary key, command that produces it).
_STEPS: tuple[tuple[str, str, str], ...] = (
    ("BUILD", "build_ok", "vkmql-new build <preset> --name <EA>"),
    ("COMPILE", "compile_ok", "vkmql-check compile"),
    ("BACKTEST", "backtest_ok", "vkmql-check test"),
    ("GATE", "gate_ok", "vkmql-check audit"),
)

_MARK = {True: "[PASS]", False: "[FAIL]", None: "[ -- ]"}


def _load_summary(out_dir: Path) -> tuple[dict[str, Any] | None, Path]:
    path = out_dir / "evidence" / "manifest.json"
    if not path.is_file():
        return None, path
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = dict(data.get("summary", {}) or {})
    # Both v1 and v2 also stamp release_eligible at the top level; prefer the
    # summary value but fall back so either manifest shape renders correctly.
    if "release_eligible" not in summary and "release_eligible" in data:
        summary["release_eligible"] = data["release_eligible"]
    return summary, path


def _state(summary: dict[str, Any], key: str) -> bool | None:
    """True / False / None(=dimension absent from this manifest shape)."""
    if key not in summary:
        return None
    return bool(summary[key])


def _next_action(states: dict[str, bool | None], release_eligible: bool) -> str:
    for label, _key, cmd in _STEPS:
        s = states[label]
        if s is None:
            return f"run `{cmd}` (no evidence yet)"
        if s is False:
            return f"fix {label.lower()} failures, then re-run `{cmd}`"
    if release_eligible:
        return "release-eligible - run `vkmql-ship release`"
    return (
        "all steps pass but policy still blocks release - "
        "inspect evidence/manifest.json (unsafe flags / skipped stages / missing hashes)"
    )


def build_status(out_dir: Path) -> dict[str, Any]:
    summary, path = _load_summary(out_dir)
    if summary is None:
        return {
            "ok": False,
            "started": False,
            "manifest": str(path),
            "steps": {label: None for label, _k, _c in _STEPS},
            "release_eligible": False,
            "unsafe_flags_used": [],
            "skipped_stages": [],
            "next_action": "run `vkmql-new build <preset> --name <EA>` (no evidence manifest yet)",
        }
    states = {label: _state(summary, key) for label, key, _c in _STEPS}
    release_eligible = bool(summary.get("release_eligible"))
    return {
        "ok": release_eligible,
        "started": True,
        "manifest": str(path),
        "steps": states,
        "release_eligible": release_eligible,
        "status": summary.get("status"),
        "unsafe_flags_used": summary.get("unsafe_flags_used", []),
        "skipped_stages": summary.get("skipped_stages", []),
        "next_action": _next_action(states, release_eligible),
    }


# Plain (non-f) template so literal CSS braces survive. Only ``$name`` tokens
# are substituted; there are no literal ``$`` characters in the body.
_HTML_TEMPLATE = _string.Template(
    """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VibeCodeKit - Golden Flow</title>
<style>
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem auto; max-width: 640px; color: #1f1f1f; }
  h1 { font-size: 1.25rem; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  td { padding: .6rem .8rem; border-bottom: 1px solid #eee; font-size: 1rem; }
  td.step { font-weight: 600; letter-spacing: .04em; }
  td.mark { text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }
  tr.release td { border-top: 2px solid #1f1f1f; border-bottom: none; font-size: 1.05rem; }
  .next { background: #f1f3f4; border-radius: 8px; padding: .8rem 1rem; }
  .warn { color: #b3261e; font-size: .9rem; }
  .meta { color: #8a8a8a; font-size: .8rem; margin-top: 1.5rem; }
</style></head>
<body>
<h1>Golden flow</h1>
<table>$rows</table>
$extras
<p class="next"><strong>Next action:</strong> $next_action</p>
<p class="meta">Source manifest: $manifest</p>
</body></html>
"""
)


def _html_escape(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_html(status: dict[str, Any]) -> str:
    """Self-contained (no external CSS/JS) golden-flow dashboard.

    Safe to drop next to the build output and open in any browser, or to
    publish via :mod:`dashboard`. Every value comes from the canonical
    evidence manifest; this function never recomputes eligibility.
    """
    colours = {True: "#137333", False: "#b3261e", None: "#8a8a8a"}
    labels = {True: "PASS", False: "FAIL", None: "-"}
    rows: list[str] = []
    for label, _key, _cmd in _STEPS:
        st = status["steps"][label]
        rows.append(
            '<tr><td class="step">' + _html_escape(label) + "</td>"
            '<td class="mark" style="color:' + colours[st] + '">'
            + labels[st] + "</td></tr>"
        )
    rel = bool(status["release_eligible"])
    rows.append(
        '<tr class="release"><td class="step">RELEASE</td>'
        '<td class="mark" style="color:' + colours[rel] + '">'
        + ("ELIGIBLE" if rel else "BLOCKED") + "</td></tr>"
    )
    extras = ""
    if status.get("unsafe_flags_used"):
        extras += (
            '<p class="warn">Unsafe flags: '
            + _html_escape(", ".join(status["unsafe_flags_used"]))
            + "</p>"
        )
    if status.get("skipped_stages"):
        extras += (
            '<p class="warn">Skipped stages: '
            + _html_escape(", ".join(status["skipped_stages"]))
            + "</p>"
        )
    return _HTML_TEMPLATE.substitute(
        rows="".join(rows),
        extras=extras,
        next_action=_html_escape(status["next_action"]),
        manifest=_html_escape(status["manifest"]),
    )


def _render(status: dict[str, Any]) -> str:
    lines = ["Golden flow:"]
    for label, _key, _cmd in _STEPS:
        lines.append(f"  {_MARK[status['steps'][label]]:<7} {label}")
    rel = status["release_eligible"]
    lines.append(
        f"  {('[PASS]' if rel else '[FAIL]'):<7} RELEASE "
        f"(release_eligible={str(rel).lower()})"
    )
    lines.append("")
    lines.append(f"Next action: {status['next_action']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="vkmql-check status",
        description="Show where a build stands in the golden flow.",
    )
    p.add_argument(
        "--out-dir",
        default=".",
        help="Workspace/build dir containing evidence/manifest.json (default: cwd).",
    )
    p.add_argument("--json", action="store_true", help="Emit the status as JSON.")
    p.add_argument(
        "--html",
        metavar="PATH",
        default=None,
        help="Write a self-contained report.html dashboard to PATH (use '-' for stdout).",
    )
    args = p.parse_args(argv)

    status = build_status(Path(args.out_dir))
    if args.html is not None:
        html = render_html(status)
        if args.html == "-":
            sys.stdout.write(html)
        else:
            out = Path(args.html)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html, encoding="utf-8")
            print(f"wrote {out}")
    if args.json:
        json.dump(status, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif args.html is None:
        print(_render(status))
    # Exit 0 always: this is a *reporting* tool, not a gate. Callers that need a
    # gate use `vkmql-ship release`, which enforces release_eligible.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
