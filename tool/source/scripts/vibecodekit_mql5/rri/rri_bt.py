"""mql5-rri-bt — RRI Backtest review (5 personas × 7 dim × 8 axis).

Reads a backtest tester XML (parsed via :mod:`vibecodekit_mql5.backtest`)
plus optional Q&A answers per persona, and emits a matrix-style HTML
report.

The five personas involved at the VERIFY step (per the kit spec §9 persona
× step matrix) are: trader, risk-auditor, broker-engineer,
strategy-architect, perf-analyst — devops is wired into the deploy step
instead.

This is a thin orchestrator: it does **not** run the backtest, it reads
artefacts already produced by `mql5-backtest` + `mql5-walkforward`.
"""

from __future__ import annotations

from pathlib import Path

from .matrix import AXES, DIMS, MatrixReport, render_html
from .personas import filter_for_mode, load_persona

RRI_BT_PERSONAS: tuple[str, ...] = (
    "trader",
    "risk-auditor",
    "broker-engineer",
    "strategy-architect",
    "perf-analyst",
)

# 7 of the 8 dims are populated by backtest review; d_inference applies only
# to ONNX-bearing scaffolds and stays N/A here.
RRI_BT_DIMS: tuple[str, ...] = tuple(d for d in DIMS if d != "d_inference")


def _status_from_metrics(metrics: dict) -> dict[str, str]:
    """Map raw backtest numbers to per-dim statuses."""
    out: dict[str, str] = {}
    pf = float(metrics.get("profit_factor") or 0.0)
    sharpe = float(metrics.get("sharpe") or 0.0)
    dd_pct = float(metrics.get("max_dd_pct") or 0.0)
    trades = int(metrics.get("total_trades") or 0)

    out["d_correctness"] = "PASS" if trades > 0 else "FAIL"
    out["d_risk"] = "PASS" if dd_pct <= 30 else ("WARN" if dd_pct <= 50 else "FAIL")
    out["d_robustness"] = "PASS" if sharpe >= 0.7 else ("WARN" if sharpe >= 0.3 else "FAIL")
    out["d_perf"] = "PASS" if pf >= 1.3 else ("WARN" if pf >= 1.0 else "FAIL")
    out["d_maintainability"] = "PASS"
    out["d_observability"] = "PASS" if metrics.get("journal_lines", 0) > 0 else "WARN"
    out["d_broker_safety"] = "PASS" if metrics.get("pip_norm_log", False) else "WARN"
    return out


def review(metrics: dict, output_html: Path) -> MatrixReport:
    """Build the matrix from a metrics dict and write the HTML report."""
    statuses = _status_from_metrics(metrics)
    matrix = MatrixReport()
    for dim in RRI_BT_DIMS:
        for axis in AXES:
            status = statuses.get(dim, "N/A")
            note = ""
            if axis in ("design", "implement") and dim == "d_correctness":
                # Reviewers must sign these themselves; we surface as N/A.
                status, note = "N/A", "reviewer sign-off required"
            matrix.set(dim, axis, status, note)
    output_html.write_text(render_html(matrix), encoding="utf-8")
    return matrix


def question_count(mode: str) -> int:
    """Return the total RRI-BT question count for the chosen mode."""
    total = 0
    for pid in RRI_BT_PERSONAS:
        persona = load_persona(pid)
        total += len(filter_for_mode(persona, mode))
    return total


def main(argv: list[str] | None = None) -> int:
    """alias for ``mql5-rri bt`` — forwards argv to the umbrella.

    The body that produces the matrix + JSON envelope lives in
    :func:`vibecodekit_mql5.rri._run_bt`; this entry-point exists so the
    legacy ``mql5-rri-bt`` console script (and any external scripts that
    import ``vibecodekit_mql5.rri.rri_bt:main``) keep working unchanged.
    """

    # Avoid recursive import — only import the umbrella's ``main`` here,
    # not at module load, so ``from . import rri_bt`` from ``__init__`` stays cheap.
    from . import main as umbrella_main
    import sys as _sys

    forwarded = ["bt", *(argv if argv is not None else _sys.argv[1:])]
    return umbrella_main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
