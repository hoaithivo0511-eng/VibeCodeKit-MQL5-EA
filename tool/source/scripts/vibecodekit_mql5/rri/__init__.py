"""Vibecodekit RRI methodology package + umbrella ``mql5-rri``.

consolidates the four RRI console scripts (``mql5-rri``,
``mql5-rri-bt``, ``mql5-rri-rr``, ``mql5-rri-chart``) into a single
subcommand-aware entry-point::

    mql5-rri                # legacy default: print Step-2 RRI template
    mql5-rri template       # same as no-arg invocation, explicit form
    mql5-rri bt    --metrics bt.json [--mode personal] [--output rri-bt.html]
    mql5-rri rr    --trader-check tc.json --walkforward wf.json
                   --monte-carlo mc.json --overfit of.json
                   [--mode personal] [--output rri-rr.html]
    mql5-rri chart --metrics chart.json [--mode personal] [--output rri-chart.html]

The three matrix-builder modules (:mod:`vibecodekit_mql5.rri.rri_bt`,
:mod:`.rri_rr`, :mod:`.rri_chart`) still expose their ``main()`` as
console-script aliases for back-compat, but their bodies now delegate
to this umbrella so help, JSON output, and arg semantics stay aligned.

Calling ``mql5-rri`` with **no** subcommand prints the Step-2 RRI
template to stdout — same behavior as the pre-CLI, so existing
scripts and operator habits keep working.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[3] / "docs" / "rri-templates" / "step-2-rri.md.tmpl"

VALID_MODES: tuple[str, ...] = ("personal", "team", "enterprise")


def render() -> str:
    """Return the Step-2 RRI markdown template (the legacy ``mql5-rri`` output)."""

    if not TEMPLATE.exists():
        return f"# RRI\n\n(template not installed: {TEMPLATE})\n"
    return TEMPLATE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Subcommand handlers — each returns the JSON envelope that the original
# CLI used to emit, so back-compat is preserved exactly.
# ---------------------------------------------------------------------------

def _run_template() -> int:
    sys.stdout.write(render())
    return 0


def _run_bt(metrics_path: Path, mode: str, output: Path) -> int:
    # Local import keeps the no-arg ``mql5-rri`` path cold-start fast and
    # avoids loading the matrix renderer when only the template is needed.
    from . import rri_bt

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    matrix = rri_bt.review(metrics, output)
    payload = {
        "kind": "bt",
        "personas": list(rri_bt.RRI_BT_PERSONAS),
        "mode": mode,
        "questions_to_answer": rri_bt.question_count(mode),
        "matrix_counts": matrix.counts(),
        "output": str(output),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _run_rr(
    trader_check_path: Path, walkforward_path: Path, monte_carlo_path: Path,
    overfit_path: Path, mode: str, output: Path,
) -> int:
    from . import rri_rr

    payloads = {
        "tc": json.loads(trader_check_path.read_text(encoding="utf-8")),
        "wf": json.loads(walkforward_path.read_text(encoding="utf-8")),
        "mc": json.loads(monte_carlo_path.read_text(encoding="utf-8")),
        "of": json.loads(overfit_path.read_text(encoding="utf-8")),
    }
    matrix = rri_rr.review(
        payloads["tc"], payloads["wf"], payloads["mc"], payloads["of"], output,
    )
    payload = {
        "kind": "rr",
        "personas": list(rri_rr.RRI_RR_PERSONAS),
        "mode": mode,
        "questions_to_answer": rri_rr.question_count(mode),
        "matrix_counts": matrix.counts(),
        "output": str(output),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _run_chart(metrics_path: Path, mode: str, output: Path) -> int:
    from . import rri_chart

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    matrix = rri_chart.review(metrics, output)
    payload = {
        "kind": "chart",
        "personas": list(rri_chart.RRI_CHART_PERSONAS),
        "mode": mode,
        "questions_to_answer": rri_chart.question_count(mode),
        "matrix_counts": matrix.counts(),
        "output": str(output),
    }
    print(json.dumps(payload, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mql5-rri",
        description=__doc__.splitlines()[0],
    )
    sub = parser.add_subparsers(dest="kind")

    # template — explicit form, equivalent to no-arg invocation.
    sub.add_parser(
        "template",
        help="Print the Step-2 RRI markdown template (default when no "
             "subcommand is given).",
    )

    p_bt = sub.add_parser(
        "bt",
        help="Build the RRI-BT 7×8 matrix from a backtest metrics JSON "
             "(alias of the legacy mql5-rri-bt console script).",
    )
    p_bt.add_argument("--metrics", type=Path, required=True)
    p_bt.add_argument("--mode", choices=VALID_MODES, default="personal")
    p_bt.add_argument("--output", type=Path, default=Path("rri-bt.html"))

    p_rr = sub.add_parser(
        "rr",
        help="Build the RRI-RR 2×8 matrix from trader-check + walkforward + "
             "monte-carlo + overfit envelopes (alias of mql5-rri-rr).",
    )
    p_rr.add_argument("--trader-check", type=Path, required=True)
    p_rr.add_argument("--walkforward", type=Path, required=True)
    p_rr.add_argument("--monte-carlo", type=Path, required=True)
    p_rr.add_argument("--overfit", type=Path, required=True)
    p_rr.add_argument("--mode", choices=VALID_MODES, default="personal")
    p_rr.add_argument("--output", type=Path, default=Path("rri-rr.html"))

    p_chart = sub.add_parser(
        "chart",
        help="Build the indicator RRI matrix from a chart metrics JSON "
             "(alias of mql5-rri-chart).",
    )
    p_chart.add_argument("--metrics", type=Path, required=True)
    p_chart.add_argument("--mode", choices=VALID_MODES, default="personal")
    p_chart.add_argument("--output", type=Path, default=Path("rri-chart.html"))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # No subcommand or explicit ``template`` -> legacy no-arg behavior.
    if not args.kind or args.kind == "template":
        return _run_template()
    if args.kind == "bt":
        return _run_bt(args.metrics, args.mode, args.output)
    if args.kind == "rr":
        return _run_rr(
            args.trader_check, args.walkforward, args.monte_carlo,
            args.overfit, args.mode, args.output,
        )
    if args.kind == "chart":
        return _run_chart(args.metrics, args.mode, args.output)

    # argparse should already reject unknown kinds; defensive fallback.
    parser.error(f"unknown subcommand: {args.kind!r}")
    return 2  # unreachable, parser.error() raises SystemExit


__all__ = ["main", "render", "TEMPLATE", "VALID_MODES"]
