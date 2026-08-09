"""Permission Layer 7 — BROKER-SAFETY (multi-broker + pip-norm verified).

Reads the multibroker stability JSON (output of ``mql5-multibroker``) and
asserts:

  - verdict == "PASS" (PF CV / Sharpe stdev / DD diff all within tolerance)
  - at least one journal contained ``[PipNorm]`` log line

Both checks come from :mod:`vibecodekit_mql5.multibroker`. If a journal
text is supplied directly, the pip-norm log presence is checked here so
the layer is usable without re-running multibroker.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _has_pipnorm_log(text: str) -> bool:
    return "[PipNorm]" in text


def gate(multibroker_json: Path, journal_path: Path | None = None) -> dict:
    if not multibroker_json.exists():
        return {"ok": False, "error": f"missing multibroker report: {multibroker_json}"}
    payload = json.loads(multibroker_json.read_text(encoding="utf-8"))
    verdict = str(payload.get("verdict", "FAIL")).upper()
    pipnorm_seen = list(payload.get("pipnorm_log_seen", []))
    if journal_path and journal_path.exists():
        if _has_pipnorm_log(journal_path.read_text(encoding="utf-8", errors="replace")):
            pipnorm_seen.append(str(journal_path))
    ok = verdict == "PASS" and bool(pipnorm_seen)
    return {
        "ok": ok,
        "verdict": verdict,
        "pipnorm_log_count": len(pipnorm_seen),
        "details": list(payload.get("details", [])),
        "multibroker": str(multibroker_json),
        "journal": str(journal_path) if journal_path else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="mql5-permission-layer7")
    ap.add_argument("--multibroker", type=Path, required=True,
                    help="JSON output of mql5-multibroker")
    ap.add_argument("--journal", type=Path, default=None,
                    help="Additional journal log to scan for [PipNorm] lines")
    args = ap.parse_args()
    result = gate(args.multibroker, args.journal)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
