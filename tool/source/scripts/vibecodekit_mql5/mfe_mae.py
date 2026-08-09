"""mql5-mfe-mae — analyze per-trade MFE/MAE CSV emitted by CMfeMaeLogger.

Reads `mfe_mae.csv` produced at runtime by `Include/CMfeMaeLogger.mqh`,
computes correlation of MFE and MAE vs realized profit, and prints
summary statistics.

CSV schema (written by CMfeMaeLogger):
    deal_id, open_time, close_time, magic, type, profit, mfe, mae

CLI:
    python -m vibecodekit_mql5.mfe_mae <mfe_mae.csv>
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path


REQUIRED_COLUMNS: tuple[str, ...] = ("profit", "mfe", "mae")
EXPECTED_HEADER: str = "deal_id,open_time,close_time,magic,type,profit,mfe,mae"


class MfeMaeCsvError(ValueError):
    """Raised when the input CSV is missing required MFE/MAE columns.

    Subclass of :class:`ValueError` so existing ``except ValueError`` blocks
    (including the ``verify.mfe_mae`` MCP bridge wrapper) keep working.
    """


@dataclass
class MfeMaeStats:
    n_trades: int
    mean_mfe: float
    mean_mae: float
    mfe_profit_corr: float
    mae_profit_corr: float

    def to_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "mean_mfe": round(self.mean_mfe, 4),
            "mean_mae": round(self.mean_mae, 4),
            "mfe_profit_corr": round(self.mfe_profit_corr, 4),
            "mae_profit_corr": round(self.mae_profit_corr, 4),
        }


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation; returns 0.0 if undefined."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    sx = statistics.pstdev(xs)
    sy = statistics.pstdev(ys)
    if sx == 0 or sy == 0:
        return 0.0
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    return cov / (sx * sy)


def parse_csv(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        out.append(row)
    return out


def compute_stats(rows: list[dict[str, str]]) -> MfeMaeStats:
    if rows:
        present = set(rows[0].keys())
        missing = [c for c in REQUIRED_COLUMNS if c not in present]
        if missing:
            raise MfeMaeCsvError(
                f"csv missing required column(s): {missing}; "
                f"expected header: {EXPECTED_HEADER}"
            )
    profits = [float(r["profit"]) for r in rows]
    mfes = [float(r["mfe"]) for r in rows]
    maes = [float(r["mae"]) for r in rows]
    return MfeMaeStats(
        n_trades=len(rows),
        mean_mfe=statistics.fmean(mfes) if mfes else 0.0,
        mean_mae=statistics.fmean(maes) if maes else 0.0,
        mfe_profit_corr=pearson(mfes, profits),
        mae_profit_corr=pearson(maes, profits),
    )


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    p = argparse.ArgumentParser(prog="mql5-mfe-mae", description=__doc__.splitlines()[0])
    p.add_argument("csv_path")
    _agent_io.add_json_flag(p)
    _agent_io.add_gate_report_flag(p)
    args = p.parse_args(argv)

    path = Path(args.csv_path)
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"csv_path not found: {path}"}), file=sys.stderr)
        return 2
    try:
        stats = compute_stats(parse_csv(path.read_text(encoding="utf-8")))
    except MfeMaeCsvError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2

    envelope = _agent_io.Envelope(
        tool="mql5-mfe-mae",
        ok=True,
        exit_code=0,
        summary=(f"mfe/mae: n={stats.n_trades} "
                 f"mfe_corr={stats.mfe_profit_corr:.3f} "
                 f"mae_corr={stats.mae_profit_corr:.3f}"),
        data=stats.to_dict(),
        evidence=[str(path)],
        matrix_dim="d_robustness",
        matrix_axis="backtest",
        matrix_status="PASS",
    )

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        print(json.dumps(stats.to_dict(), indent=2))

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
