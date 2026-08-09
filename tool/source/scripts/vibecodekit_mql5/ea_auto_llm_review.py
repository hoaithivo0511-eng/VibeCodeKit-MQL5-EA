"""Automatic EA review workflow: intake + static review + LLM pack + optional LLM run."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .ea_intake_review import run_intake_review
from .llm_review_pack import make_pack
from .llm_review_runner import run_llm_review
from .chat_review_pack import make_chat_pack


def run_auto_workflow(
    source: str | Path,
    out_dir: str | Path,
    name: str | None = None,
    profile: str = "auto",
    adapter: str = "auto",
    model: str = "gpt-5.1",
    no_llm: bool = False,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    intake_review = run_intake_review(source, out, name, profile)
    project = Path(intake_review["project"])
    review_dir = project / "review"
    llm_pack_dir = review_dir / "llm-review-pack"
    pack = make_pack(project, llm_pack_dir, intake_review.get("profile", profile))

    chat_pack_dir = review_dir / "chat-llm-pack"
    chat_pack = make_chat_pack(project, chat_pack_dir, intake_review.get("profile", profile), mode="compact")

    if no_llm:
        llm = {
            "llm_review_ran": False,
            "selected_adapter": None,
            "fallback": "Skipped by --no-llm",
            "output": None,
        }
        (llm_pack_dir / "LLM_REVIEW_RUN.json").write_text(json.dumps(llm, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        llm = run_llm_review(llm_pack_dir, adapter=adapter, model=model)

    result = {
        "ok": True,
        "source": str(source),
        "project": str(project),
        "profile": intake_review.get("profile"),
        "static_review_readiness": intake_review.get("senior_readiness"),
        "static_review_score": intake_review.get("senior_score"),
        "llm_review_ran": llm.get("llm_review_ran", False),
        "llm_adapter": llm.get("selected_adapter"),
        "outputs": {
            **intake_review.get("outputs", {}),
            "llm_pack": str(llm_pack_dir),
            "llm_prompt": pack.get("prompt"),
            "llm_run": str(llm_pack_dir / "LLM_REVIEW_RUN.json"),
            "llm_deep_review": llm.get("output"),
            "chat_llm_pack": str(chat_pack_dir),
            "chat_llm_prompt": chat_pack.get("prompt"),
            "chat_llm_context": chat_pack.get("context"),
        },
        "policy": "Static review always runs. LLM review is optional and must not be faked if adapter unavailable.",
    }
    (review_dir / "EA-AUTO-LLM-REVIEW-SUMMARY.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Automatic EA codebase review workflow with optional LLM integration.")
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name")
    ap.add_argument("--profile", default="auto")
    ap.add_argument("--adapter", default="auto", choices=["auto", "codex", "claude", "openai_api"])
    ap.add_argument("--model", default="gpt-5.1")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--json-only", "--quiet", dest="json_only", action="store_true", help="Output contract: stdout carries ONLY the final JSON document; no human progress on stderr.")
    args = ap.parse_args(argv)
    result = run_auto_workflow(args.source, args.out_dir, args.name, args.profile, args.adapter, args.model, args.no_llm)
    if not args.json_only:
        # Human-readable summary goes to stderr so stdout stays machine-parseable.
        print(
            "[auto-llm-review] project={p} static_score={s} readiness={r} llm_ran={l}".format(
                p=result.get("project"),
                s=result.get("static_review_score"),
                r=result.get("static_review_readiness"),
                l=result.get("llm_review_ran"),
            ),
            file=sys.stderr,
        )
    # stdout: exactly one JSON document (the machine contract).
    print(json.dumps(result, indent=2, ensure_ascii=False))
    # rc 0 if workflow completed; LLM absence is not a workflow failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
