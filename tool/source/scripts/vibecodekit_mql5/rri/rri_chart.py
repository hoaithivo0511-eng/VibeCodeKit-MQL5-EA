"""mql5-rri-chart — optional RRI review for indicator development.

Indicator-only EAs / pure-MQL5 indicators don't go through the same
risk-auditor / broker-engineer lens that order-placing EAs do, so this
command runs a slimmed-down review covering correctness, observability,
and perf only. Personas involved: trader (UX) + perf-analyst.

This command is *optional* — it's only invoked from the indicator-only
scaffold and is treated as a sanity check, not a gate.
"""

from __future__ import annotations

from pathlib import Path

from .matrix import AXES, MatrixReport, render_html
from .personas import filter_for_mode, load_persona

RRI_CHART_PERSONAS: tuple[str, ...] = ("trader", "perf-analyst")
RRI_CHART_DIMS: tuple[str, ...] = ("d_correctness", "d_observability", "d_perf")


def review(metrics: dict, output_html: Path) -> MatrixReport:
    matrix = MatrixReport()
    correctness = "PASS" if metrics.get("compile_errors", 1) == 0 else "FAIL"
    observability = "PASS" if metrics.get("journal_lines", 0) > 0 else "WARN"
    perf = "PASS" if metrics.get("ontick_latency_us", 9999) < 1000 else "WARN"
    status_for = {
        "d_correctness": correctness,
        "d_observability": observability,
        "d_perf": perf,
    }
    for dim in RRI_CHART_DIMS:
        for axis in AXES:
            matrix.set(dim, axis, status_for[dim])
    output_html.write_text(render_html(matrix), encoding="utf-8")
    return matrix


def question_count(mode: str) -> int:
    return sum(
        len(filter_for_mode(load_persona(pid), mode)) for pid in RRI_CHART_PERSONAS
    )


def main(argv: list[str] | None = None) -> int:
    """alias for ``mql5-rri chart`` — forwards argv to the umbrella."""

    from . import main as umbrella_main
    import sys as _sys

    forwarded = ["chart", *(argv if argv is not None else _sys.argv[1:])]
    return umbrella_main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
