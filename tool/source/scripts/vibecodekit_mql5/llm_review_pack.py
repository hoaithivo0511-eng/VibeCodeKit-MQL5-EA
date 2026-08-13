"""LLM review pack generator for MQL5 EA projects.

Creates a grounded context pack for Codex/Claude/LLM review:
- source map
- report index
- prompt
- ground-truth rules
- files to read
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .ea_senior_review import review_project


def file_summary(project: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(project.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".mq5", ".mqh", ".json", ".yaml", ".yml", ".md"}:
            rel = p.relative_to(project).as_posix()
            if rel.startswith("original/") and p.stat().st_size > 200_000:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            out.append({
                "path": rel,
                "suffix": p.suffix.lower(),
                "bytes": p.stat().st_size,
                "lines": text.count("\n") + 1,
                "contains_inputs": "input " in text,
                "contains_on_tick": "OnTick" in text,
                "contains_trade": "CTrade" in text or "OrderSend" in text or "PositionClose" in text,
            })
    return out


def build_prompt(project: Path, senior: dict[str, Any], pack_dir: Path) -> str:
    return f"""# Senior MQL5 EA LLM Review Task

You are a senior MQL5 Expert Advisor reviewer.

## Non-negotiable grounding rules

1. Use the source files and generated JSON reports as ground truth.
2. Do not claim a feature exists unless the source or claim ledger supports it.
3. If a feature is only an input/placeholder and not implemented, say so explicitly.
4. Do not invent backtest, compile, profitability, robustness, or live-trading results.
5. Separate static findings from compile/backtest evidence.
6. Prioritize issues that can lose money: grid/DCA risk, execution safety, drawdown behavior, broker compatibility, state recovery, spread/slippage/news exposure.

## Project

```text
{project}
```

## Existing static review summary

```text
{senior.get('senior_summary','')}
```

## Required review output

Write a deep review in Vietnamese with these sections:

1. Executive summary
2. EA strategy actually implemented
3. OnInit / OnTick / OnTradeTransaction flow
4. Entry logic
5. Exit logic
6. Grid/DCA/martingale risk
7. Execution and broker compatibility
8. Risk management and DD behavior
9. State/recovery/restart safety
10. Input parameter quality and dangerous inputs
11. Documentation overclaim check
12. Release readiness
13. Concrete refactor plan by phase
14. Questions for the EA owner before live deployment

## Files/reports to inspect first

Read these files inside the review pack/project:

```text
LLM_REVIEW_CONTEXT.json
SOURCE_MAP.json
GROUND_TRUTH_RULES.md
FILES_TO_READ.txt
```

Then inspect the source files listed in `FILES_TO_READ.txt`.
"""


def make_pack(project: str | Path, out_dir: str | Path, profile: str = "auto") -> dict[str, Any]:
    project = Path(project)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    senior = review_project(project, profile)
    sources = file_summary(project)
    mql_files = [s for s in sources if s["suffix"] in {".mq5", ".mqh"}]
    reports = [s for s in sources if s["suffix"] == ".json" or s["path"].endswith(".md")]

    context = {
        "schema_version": "1.0",
        "project": str(project),
        "profile": profile,
        "senior_review": senior,
        "source_count": len(mql_files),
        "report_count": len(reports),
        "recommended_read_order": [
            "review/EA-SENIOR-REVIEW.json",
            "review/ap-policy.json",
            "docs/docs-context.json",
            "docs/docs-prompt.md",
            "Experts/*.mq5",
            "Include/**/*.mqh",
        ],
    }
    source_map = {
        "project": str(project),
        "files": sources,
    }
    files_to_read = []
    for s in mql_files:
        if s["contains_on_tick"] or s["contains_trade"] or s["contains_inputs"] or s["path"].startswith("Experts/"):
            files_to_read.append(s["path"])
    if not files_to_read:
        files_to_read = [s["path"] for s in mql_files[:20]]

    (out / "LLM_REVIEW_CONTEXT.json").write_text(json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "SOURCE_MAP.json").write_text(json.dumps(source_map, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "FILES_TO_READ.txt").write_text("\n".join(files_to_read) + "\n", encoding="utf-8")
    (out / "GROUND_TRUTH_RULES.md").write_text("""# Ground Truth Rules

- Source files and JSON reports are authoritative.
- Do not invent features absent from source.
- If `doc-verify.json` says a claim is unsupported, treat the feature as missing or unverified.
- If no `evidence/manifest.json` release eligible artifact exists, release readiness is blocked.
- Static review is not compile/backtest proof.
- Profitability cannot be claimed without MT5 Strategy Tester and forward evidence.
""", encoding="utf-8")
    prompt = build_prompt(project, senior, out)
    (out / "LLM_REVIEW_PROMPT.md").write_text(prompt, encoding="utf-8")
    result = {
        "ok": True,
        "pack_dir": str(out),
        "prompt": str(out / "LLM_REVIEW_PROMPT.md"),
        "context": str(out / "LLM_REVIEW_CONTEXT.json"),
        "source_map": str(out / "SOURCE_MAP.json"),
        "files_to_read": str(out / "FILES_TO_READ.txt"),
        "source_count": len(mql_files),
        "selected_files_to_read": len(files_to_read),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create grounded LLM review pack for EA project.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--profile", default="auto")
    args = ap.parse_args(argv)
    result = make_pack(args.project, args.out_dir, args.profile)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
