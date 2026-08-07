"""One-shot workflow for generic chat LLM environments.

This command intentionally does not call Codex/Claude/OpenAI. It creates a
compact review workspace optimized for uploading/reading in the current chat LLM.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .ea_intake_review import run_intake_review
from .chat_review_pack import make_chat_pack


def run_chat_workflow(source: str | Path, out_dir: str | Path, name: str | None = None, profile: str = "auto", mode: str = "compact") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    intake = run_intake_review(source, out, name, profile)
    project = Path(intake["project"])
    review_dir = project / "review"
    chat_pack = make_chat_pack(project, review_dir / "chat-llm-pack", intake.get("profile", profile), mode=mode)
    result = {
        "ok": True,
        "source": str(source),
        "project": str(project),
        "profile": intake.get("profile"),
        "static_review_score": intake.get("senior_score"),
        "static_review_readiness": intake.get("senior_readiness"),
        "chat_llm_ready": True,
        "outputs": {
            **intake.get("outputs", {}),
            "chat_llm_pack": chat_pack.get("pack_dir"),
            "chat_llm_prompt": chat_pack.get("prompt"),
            "chat_llm_context": chat_pack.get("context"),
            "source_excerpts": chat_pack.get("source_excerpts"),
            "ground_truth_reports": chat_pack.get("ground_truth_reports"),
            "files_to_upload": chat_pack.get("files_to_upload"),
        },
        "how_to_use": [
            "Upload or open CHAT_LLM_REVIEW_PROMPT.md first.",
            "Then provide CHAT_LLM_CONTEXT_COMPACT.md, SOURCE_EXCERPTS.md and GROUND_TRUTH_REPORTS.json.",
            "Ask the chat LLM to follow grounding rules and write the final deep review.",
        ],
    }
    (review_dir / "EA-CHAT-REVIEW-WORKFLOW-SUMMARY.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create chat-LLM optimized EA review workflow outputs.")
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name")
    ap.add_argument("--profile", default="auto")
    ap.add_argument("--mode", default="compact", choices=["compact", "full"])
    args = ap.parse_args(argv)
    result = run_chat_workflow(args.source, args.out_dir, args.name, args.profile, args.mode)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
