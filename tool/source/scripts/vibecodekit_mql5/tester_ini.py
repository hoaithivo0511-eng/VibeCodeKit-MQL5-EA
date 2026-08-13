"""MT5 Strategy Tester INI generator.

Generates a deterministic tester.ini that can be sent to a local or remote
Windows MT5 terminal runner.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json


def build_tester_ini(
    *,
    expert: str,
    symbol: str,
    timeframe: str,
    date_from: str,
    date_to: str,
    deposit: float = 10000,
    currency: str = "USD",
    model: str = "Every tick based on real ticks",
    report: str = "tester.xml",
    inputs: str | None = None,
    optimization: bool = False,
) -> str:
    lines = [
        "[Tester]",
        f"Expert={expert}",
        f"Symbol={symbol}",
        f"Period={timeframe}",
        f"FromDate={date_from}",
        f"ToDate={date_to}",
        f"Deposit={deposit}",
        f"Currency={currency}",
        f"Model={model}",
        f"Report={report}",
        "ReplaceReport=1",
        "ShutdownTerminal=1",
        f"Optimization={1 if optimization else 0}",
    ]
    if inputs:
        lines.append(f"ExpertParameters={inputs}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate MT5 Strategy Tester .ini file.")
    ap.add_argument("--expert", required=True, help="EA path/name as expected by MT5")
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--timeframe", required=True)
    ap.add_argument("--from-date", required=True)
    ap.add_argument("--to-date", required=True)
    ap.add_argument("--deposit", type=float, default=10000)
    ap.add_argument("--currency", default="USD")
    ap.add_argument("--model", default="Every tick based on real ticks")
    ap.add_argument("--report", default="tester.xml")
    ap.add_argument("--inputs")
    ap.add_argument("--optimization", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    text = build_tester_ini(
        expert=args.expert,
        symbol=args.symbol,
        timeframe=args.timeframe,
        date_from=args.from_date,
        date_to=args.to_date,
        deposit=args.deposit,
        currency=args.currency,
        model=args.model,
        report=args.report,
        inputs=args.inputs,
        optimization=args.optimization,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(json.dumps({"out": str(out), "bytes": len(text.encode("utf-8")), "report": args.report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
