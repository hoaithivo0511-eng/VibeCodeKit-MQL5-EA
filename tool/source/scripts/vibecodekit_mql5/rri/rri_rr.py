"""mql5-rri-rr — RRI Risk & Robustness review.

Focuses two dims (``d_risk`` and ``d_robustness``) with the personas that
materially own those dims at the VERIFY step: risk-auditor and
strategy-architect.

Inputs:
- trader_check.json — output of :mod:`vibecodekit_mql5.trader_check`
- walkforward.json  — output of :mod:`vibecodekit_mql5.walkforward`
- monte_carlo.json  — output of :mod:`vibecodekit_mql5.monte_carlo`
- overfit.json      — output of :mod:`vibecodekit_mql5.overfit_check`

Output: an HTML report covering 2 dims × 8 axes (= 16 cells).
"""

from __future__ import annotations

from pathlib import Path

from .matrix import AXES, MatrixReport, render_html
from .personas import filter_for_mode, load_persona

RRI_RR_PERSONAS: tuple[str, ...] = ("risk-auditor", "strategy-architect")
RRI_RR_DIMS: tuple[str, ...] = ("d_risk", "d_robustness")


def _risk_status(trader_check: dict) -> str:
    passes = int(trader_check.get("pass_count", 0))
    if passes >= 17:
        return "PASS"
    if passes >= 15:
        return "WARN"
    return "FAIL"


def _robustness_status(wf: dict, mc: dict, of: dict) -> str:
    corr = float(wf.get("oos_is_correlation") or 0.0)
    dd_p95_ratio = float(mc.get("dd_p95_over_reported") or 99.0)
    oos_is = float(of.get("oos_is_sharpe_ratio") or 0.0)
    if corr >= 0.5 and dd_p95_ratio <= 1.5 and oos_is >= 0.7:
        return "PASS"
    if corr >= 0.3 and dd_p95_ratio <= 2.0 and oos_is >= 0.5:
        return "WARN"
    return "FAIL"


def review(
    trader_check: dict,
    walkforward: dict,
    monte_carlo: dict,
    overfit: dict,
    output_html: Path,
) -> MatrixReport:
    matrix = MatrixReport()
    status_for = {
        "d_risk": _risk_status(trader_check),
        "d_robustness": _robustness_status(walkforward, monte_carlo, overfit),
    }
    for dim in RRI_RR_DIMS:
        for axis in AXES:
            matrix.set(dim, axis, status_for[dim])
    output_html.write_text(render_html(matrix), encoding="utf-8")
    return matrix


def question_count(mode: str) -> int:
    return sum(
        len(filter_for_mode(load_persona(pid), mode)) for pid in RRI_RR_PERSONAS
    )


def main(argv: list[str] | None = None) -> int:
    """alias for ``mql5-rri rr`` — forwards argv to the umbrella."""

    from . import main as umbrella_main
    import sys as _sys

    forwarded = ["rr", *(argv if argv is not None else _sys.argv[1:])]
    return umbrella_main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
