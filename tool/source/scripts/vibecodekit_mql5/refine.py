"""/mql5-refine — classify a diff against the refine envelope.

The kit spec §C8 ("REFINE") splits post-ship changes into
three envelopes:

- **tweak**   — parameter / threshold / lot-size change, no logic
                change.  Allowed without re-running RRI.
- **patch**   — bug fix or stdlib-bounded change.  Requires re-running
                Layers 3, 4 only.
- **rework**  — logic change.  Requires re-running the full 8-step
                methodology + 64-cell matrix.

This module classifies a unified diff (read from disk or stdin) by
inspecting line counts + touched file kinds.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RefineReport:
    classification: str   # tweak | patch | rework
    files_touched: list[str]
    lines_added: int
    lines_removed: int
    reason: str


def classify(diff: str) -> RefineReport:
    files = re.findall(r"^\+\+\+ b/(.+)$", diff, re.MULTILINE)
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))

    touches_set_only = files and all(f.endswith(".set") for f in files)
    touches_logic = any(f.endswith((".mq5", ".mqh")) for f in files)
    delta = added + removed

    if touches_set_only:
        return RefineReport("tweak", files, added, removed,
                            "only .set parameter files changed")
    if not touches_logic:
        return RefineReport("tweak", files, added, removed,
                            "no .mq5/.mqh files in diff")
    if delta <= 20:
        return RefineReport("patch", files, added, removed,
                            f"small logic change ({delta} lines)")
    return RefineReport("rework", files, added, removed,
                        f"large logic change ({delta} lines)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-refine")
    parser.add_argument("--diff", help="path to a unified diff; reads stdin if omitted")
    args = parser.parse_args(argv)
    text = Path(args.diff).read_text(encoding="utf-8") if args.diff else sys.stdin.read()
    rep = classify(text)
    print(json.dumps(rep.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
