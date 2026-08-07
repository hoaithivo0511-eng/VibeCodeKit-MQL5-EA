"""/mql5-second-opinion — run a one-shot lint + trader-check sanity pass.

Quick way to get a second-opinion review of
an EA: runs the kit's lint detectors + the Trader-17 checklist against
a single ``.mq5`` and prints both together.  Useful before opening a
PR or before promoting from PERSONAL to TEAM mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vibecodekit_mql5 import lint as vck_lint
from vibecodekit_mql5 import trader_check as vck_trader


def review_ea(mq5_path: Path, mode: str = "personal") -> dict:
    from .mq5_io import read_mq5_text

    findings = vck_lint.lint_file(mq5_path)
    text = read_mq5_text(mq5_path, errors="replace")
    result = vck_trader.evaluate(text)
    passed = vck_trader.verdict(result, mode=mode)
    return {
        "mq5_path": str(mq5_path),
        "lint_findings": [f.__dict__ for f in findings],
        "trader_result": result,
        "trader_passed": passed,
        "mode": mode,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-second-opinion")
    parser.add_argument("mq5", help="Target .mq5 source")
    parser.add_argument("--mode", choices=["personal", "enterprise"], default="personal")
    args = parser.parse_args(argv)
    print(json.dumps(review_ea(Path(args.mq5), args.mode), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
