"""Chat-LLM review bridge pack.

Creates a compact upload-friendly bundle for any chat LLM:
- CHAT_LLM_REVIEW_PROMPT.md
- CHAT_LLM_CONTEXT_COMPACT.md
- SOURCE_EXCERPTS.md
- GROUND_TRUTH_REPORTS.json
- CHAT_LLM_FILES_TO_UPLOAD.txt

This does not call an LLM. It optimizes outputs for chats where the current LLM
will read the bundle and write the final deep review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .ea_doc_analyzer import read_mql_files, analyze_project
from .ea_senior_review import review_project


MAX_EXCERPT_CHARS_COMPACT = 4500
MAX_EXCERPT_CHARS_FULL = 12000


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def collect_ground_truth(project: Path) -> dict[str, Any]:
    review = project / "review"
    docs = project / "docs"
    data = {
        "intake_report": read_json_if_exists(project / "intake-report.json"),
        "senior_review": read_json_if_exists(review / "EA-SENIOR-REVIEW.json"),
        "ap_policy": read_json_if_exists(review / "ap-policy.json"),
        "architecture_check": read_json_if_exists(review / "architecture-check.json"),
        "doc_verify": read_json_if_exists(review / "doc-verify.json"),
        "auto_llm_summary": read_json_if_exists(review / "EA-AUTO-LLM-REVIEW-SUMMARY.json"),
        "doc_analysis": read_json_if_exists(docs / "ea-doc-analysis.json"),
    }
    # Drop missing keys to keep compact.
    return {k: v for k, v in data.items() if v is not None}


def important_score(path: str, text: str) -> int:
    s = 0
    lower = text.lower()
    if path.startswith("Experts/") and path.endswith(".mq5"):
        s += 100
    for kw in ["ontick", "oninit", "ontradetransaction", "positionclose", "ordersend", "ctrade", "lotmultiplier", "maxdd", "freezedd", "grid", "hedge", "basket", "async", "globalvariable"]:
        if kw in lower:
            s += 10
    if "input " in lower:
        s += 20
    return s


def make_excerpt(path: str, text: str, limit: int) -> str:
    # Keep beginning plus lines around important functions.
    lines = text.splitlines()
    picks: list[str] = []
    important_patterns = ["input ", "OnInit", "OnTick", "OnTradeTransaction", "PositionClose", "OrderSend", "Lot", "Grid", "DD", "Freeze", "Max"]
    selected = set()
    for idx, line in enumerate(lines):
        if any(p.lower() in line.lower() for p in important_patterns):
            for j in range(max(0, idx-3), min(len(lines), idx+8)):
                selected.add(j)
    if selected:
        last = -2
        for idx in sorted(selected):
            if idx > last + 1:
                picks.append("...")
            picks.append(f"{idx+1:04d}: {lines[idx]}")
            last = idx
    else:
        picks = [f"{i+1:04d}: {line}" for i, line in enumerate(lines[:160])]

    out = "\n".join(picks)
    if len(out) > limit:
        out = out[:limit] + "\n...[truncated]"
    return f"## {path}\n\n```mql5\n{out}\n```\n"


def build_source_excerpts(project: Path, mode: str = "compact") -> tuple[str, list[str]]:
    files = read_mql_files(project)
    limit = MAX_EXCERPT_CHARS_FULL if mode == "full" else MAX_EXCERPT_CHARS_COMPACT
    ranked = sorted(files.items(), key=lambda kv: important_score(kv[0], kv[1]), reverse=True)
    max_files = 25 if mode == "full" else 10
    chunks = []
    selected = []
    for path, text in ranked[:max_files]:
        chunks.append(make_excerpt(path, text, limit))
        selected.append(path)
    return "\n\n".join(chunks), selected


def build_context(project: Path, profile: str, mode: str) -> str:
    analysis = analyze_project(project)
    senior = review_project(project, profile)
    gt = collect_ground_truth(project)
    features = analysis.get("features", {})
    strategy = senior.get("strategy", {})
    issue_counts = senior.get("issue_counts", {})
    lines = [
        "# Chat LLM Context Compact",
        "",
        f"Project: `{project}`",
        f"Profile: `{profile}`",
        f"Mode: `{mode}`",
        "",
        "## Detected strategy",
        f"- Family: `{strategy.get('family')}`",
        f"- Signals: {', '.join(strategy.get('signals', []))}",
        "",
        "## Static review",
        f"- Score: {senior.get('score')}/100",
        f"- Readiness: `{senior.get('readiness')}`",
        f"- Issue counts: `{issue_counts}`",
        f"- Summary: {senior.get('senior_summary')}",
        "",
        "## Feature flags",
    ]
    for k, v in features.items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        "",
        "## Inputs",
    ]
    for p in analysis.get("inputs", [])[:80]:
        where = p.get("where_used") or []
        if isinstance(where, list):
            where_text = ", ".join(str(x) for x in where[:3])
        else:
            where_text = str(where)
        lines.append(f"- `{p.get('name')}` = `{p.get('default')}` ({p.get('type')}): {p.get('description','')} | where-used: {where_text}")
    lines += [
        "",
        "## Ground truth report availability",
    ]
    for k in gt.keys():
        lines.append(f"- `{k}`: available")
    return "\n".join(lines) + "\n"


def build_prompt(profile: str, mode: str) -> str:
    return f"""# Deep EA Review Request for Chat LLM

Bạn là senior MQL5 Expert Advisor reviewer.

Tôi đã chạy tool static scanner trước. Hãy dùng các file trong bundle này làm ground truth:

1. `CHAT_LLM_CONTEXT_COMPACT.md`
2. `GROUND_TRUTH_REPORTS.json`
3. `SOURCE_EXCERPTS.md`
4. Nếu cần, đọc source/project gốc được upload kèm.

## Quy tắc bắt buộc

- Không được bịa feature không có trong source hoặc reports.
- Nếu `doc_verify` nói claim unsupported, phải coi feature đó là chưa có hoặc chưa đủ evidence.
- Không được claim compile/backtest/profit/live-ready nếu không có evidence manifest release eligible.
- Phân biệt rõ static review và kết quả test thật.
- Ưu tiên lỗi có thể gây mất tiền: grid/DCA, lot multiplier, DD stop, execution, state recovery, broker hedging/netting, spread/slippage/news.

## Yêu cầu output bằng tiếng Việt

Viết deep review gồm:

1. Tóm tắt executive summary
2. EA thực sự đang dùng chiến lược gì
3. Luồng OnInit / OnTick / OnTradeTransaction
4. Logic vào lệnh
5. Logic thoát lệnh
6. Rủi ro grid/DCA/martingale
7. Execution và broker compatibility
8. Risk management/DD behavior
9. State/recovery/restart safety
10. Input nguy hiểm, input unused, input cần giải thích lại
11. Docs có overclaim không
12. Release readiness
13. Refactor plan theo phase
14. Câu hỏi cần hỏi owner trước khi live

Profile: `{profile}`
Mode: `{mode}`
"""


def make_chat_pack(project: str | Path, out_dir: str | Path, profile: str = "auto", mode: str = "compact") -> dict[str, Any]:
    project = Path(project)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mode = "full" if mode == "full" else "compact"

    context = build_context(project, profile, mode)
    excerpts, selected = build_source_excerpts(project, mode)
    gt = collect_ground_truth(project)
    prompt = build_prompt(profile, mode)

    (out / "CHAT_LLM_REVIEW_PROMPT.md").write_text(prompt, encoding="utf-8")
    (out / "CHAT_LLM_CONTEXT_COMPACT.md").write_text(context, encoding="utf-8")
    (out / "SOURCE_EXCERPTS.md").write_text(excerpts, encoding="utf-8")
    (out / "GROUND_TRUTH_REPORTS.json").write_text(json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8")
    upload_list = [
        "CHAT_LLM_REVIEW_PROMPT.md",
        "CHAT_LLM_CONTEXT_COMPACT.md",
        "SOURCE_EXCERPTS.md",
        "GROUND_TRUTH_REPORTS.json",
    ]
    (out / "CHAT_LLM_FILES_TO_UPLOAD.txt").write_text("\n".join(upload_list) + "\n", encoding="utf-8")

    result = {
        "ok": True,
        "pack_dir": str(out),
        "mode": mode,
        "prompt": str(out / "CHAT_LLM_REVIEW_PROMPT.md"),
        "context": str(out / "CHAT_LLM_CONTEXT_COMPACT.md"),
        "source_excerpts": str(out / "SOURCE_EXCERPTS.md"),
        "ground_truth_reports": str(out / "GROUND_TRUTH_REPORTS.json"),
        "files_to_upload": str(out / "CHAT_LLM_FILES_TO_UPLOAD.txt"),
        "selected_source_files": selected,
        "selected_source_count": len(selected),
    }
    (out / "CHAT_LLM_PACK_SUMMARY.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create chat-LLM optimized review pack.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--profile", default="auto")
    ap.add_argument("--mode", default="compact", choices=["compact", "full"])
    args = ap.parse_args(argv)
    result = make_chat_pack(args.project, args.out_dir, args.profile, args.mode)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
