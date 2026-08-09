"""LLM review runner adapters.

Supports:
- codex CLI if available
- claude CLI if available
- OpenAI API if OPENAI_API_KEY is available

Fail-safe: if no adapter is available, creates a clear skipped result.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def detect_adapters() -> dict[str, Any]:
    return {
        "codex_cli": shutil.which("codex"),
        "claude_cli": shutil.which("claude"),
        "openai_api_key": bool(os.environ.get("OPENAI_API_KEY")),
    }


def read_prompt(pack_dir: Path) -> str:
    return (pack_dir / "LLM_REVIEW_PROMPT.md").read_text(encoding="utf-8")


def run_codex(pack_dir: Path, out: Path, timeout_sec: int = 1800) -> dict[str, Any]:
    codex = shutil.which("codex")
    if not codex:
        return {"ran": False, "adapter": "codex", "reason": "codex CLI not found"}
    prompt = read_prompt(pack_dir)
    # Codex CLI syntax may vary by install/version. Use non-interactive exec if available.
    cmd = [codex, "exec", "--full-auto", prompt]
    p = subprocess.run(cmd, cwd=pack_dir.parent, capture_output=True, text=True, timeout=timeout_sec)
    out.write_text(p.stdout + ("\n\nSTDERR:\n" + p.stderr if p.stderr else ""), encoding="utf-8")
    return {"ran": p.returncode == 0, "adapter": "codex", "returncode": p.returncode, "output": str(out), "cmd": " ".join(cmd[:3]) + " <prompt>"}


def run_claude(pack_dir: Path, out: Path, timeout_sec: int = 1800) -> dict[str, Any]:
    claude = shutil.which("claude")
    if not claude:
        return {"ran": False, "adapter": "claude", "reason": "claude CLI not found"}
    prompt = read_prompt(pack_dir)
    cmd = [claude, "-p", prompt]
    p = subprocess.run(cmd, cwd=pack_dir.parent, capture_output=True, text=True, timeout=timeout_sec)
    out.write_text(p.stdout + ("\n\nSTDERR:\n" + p.stderr if p.stderr else ""), encoding="utf-8")
    return {"ran": p.returncode == 0, "adapter": "claude", "returncode": p.returncode, "output": str(out), "cmd": "claude -p <prompt>"}


def run_openai_api(pack_dir: Path, out: Path, model: str = "gpt-5.1", timeout_sec: int = 1800) -> dict[str, Any]:
    if not os.environ.get("OPENAI_API_KEY"):
        return {"ran": False, "adapter": "openai_api", "reason": "OPENAI_API_KEY not set"}
    try:
        from openai import OpenAI
    except Exception as exc:
        return {"ran": False, "adapter": "openai_api", "reason": f"openai package not available: {exc!r}"}
    prompt = read_prompt(pack_dir)
    context = (pack_dir / "LLM_REVIEW_CONTEXT.json").read_text(encoding="utf-8")
    source_map = (pack_dir / "SOURCE_MAP.json").read_text(encoding="utf-8")
    client = OpenAI()
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": "You are a senior MQL5 Expert Advisor reviewer. Follow grounding rules strictly."},
            {"role": "user", "content": prompt + "\n\nLLM_REVIEW_CONTEXT.json:\n" + context + "\n\nSOURCE_MAP.json:\n" + source_map},
        ],
    )
    text = getattr(resp, "output_text", None) or str(resp)
    out.write_text(text, encoding="utf-8")
    return {"ran": True, "adapter": "openai_api", "model": model, "output": str(out)}


def run_llm_review(pack_dir: str | Path, adapter: str = "auto", out_file: str | Path | None = None, model: str = "gpt-5.1") -> dict[str, Any]:
    pack = Path(pack_dir)
    out = Path(out_file) if out_file else pack / "LLM_DEEP_REVIEW.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    detected = detect_adapters()

    attempts = []
    if adapter == "auto":
        order = ["codex", "claude", "openai_api"]
    else:
        order = [adapter]

    for a in order:
        if a == "codex":
            r = run_codex(pack, out)
        elif a == "claude":
            r = run_claude(pack, out)
        elif a == "openai_api":
            r = run_openai_api(pack, out, model=model)
        else:
            r = {"ran": False, "adapter": a, "reason": "unknown adapter"}
        attempts.append(r)
        if r.get("ran"):
            summary = {"llm_review_ran": True, "selected_adapter": a, "detected": detected, "attempts": attempts, "output": str(out)}
            (pack / "LLM_REVIEW_RUN.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
            return summary

    summary = {
        "llm_review_ran": False,
        "selected_adapter": None,
        "detected": detected,
        "attempts": attempts,
        "output": None,
        "fallback": "LLM review pack was created, but no runnable LLM adapter was available or successful.",
    }
    (pack / "LLM_REVIEW_RUN.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run LLM review from a generated pack.")
    ap.add_argument("--pack-dir", required=True)
    ap.add_argument("--adapter", default="auto", choices=["auto", "codex", "claude", "openai_api"])
    ap.add_argument("--out")
    ap.add_argument("--model", default="gpt-5.1")
    args = ap.parse_args(argv)
    result = run_llm_review(args.pack_dir, args.adapter, args.out, args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["llm_review_ran"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
