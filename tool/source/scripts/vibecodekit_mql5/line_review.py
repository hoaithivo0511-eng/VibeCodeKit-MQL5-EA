"""Stage-7 grounded line-by-line review.

The LLM is powerful but hallucinates on raw code. This module makes the
review *grounded*: every function chunk is shipped together with the static
evidence already computed by Stages 0/3/4 (symbol graph, structure metrics,
dead-code findings) plus an explicit MQL5-2026 rubric. The model is then
asked to ONLY report issues it can tie to a concrete line, and each finding
is re-checked against the chunk before it is accepted.

Two operating modes (no network/API key required):

* ``build_review_packets(...)``  -> structured chunks + rubric + evidence.
  The orchestrator can feed these to whatever LLM is available (including
  the agent runtime), or serialise them for the user to paste into a chat
  model ("pack -> paste" mode).
* ``merge_findings(...)``         -> fuse model findings with static ones,
  attaching ``confidence`` and validating ``evidence_line`` against the
  actual source so unverifiable claims are demoted.

This module never calls the network itself; that keeps the kit deterministic
and offline-safe. A thin adapter can wire a real API later.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .mq5_symbols import (
    SymbolGraph,
    build_symbol_graph,
)

# Compact rubric the model must apply, distilled from the MQL5 2024-2026
# build notes (handle caching, OrderSend retcodes, OnTradeTransaction,
# matrix/vector + ONNX, OpenBLAS, multi-threaded tester).
MQL5_2026_RUBRIC: tuple[str, ...] = (
    "Indicator handles must be created once in OnInit and cached, never "
    "re-created in OnTick; verify with CopyBuffer usage.",
    "OrderSend/CTrade calls must check the return retcode (10009 done, "
    "10004/10016/10019/10027 require retry/abort handling); OrderCheck "
    "should precede OrderSend.",
    "Async order flow (OrderSendAsync) requires an OnTradeTransaction hook.",
    "No blocking calls in OnTick (Sleep, WebRequest, heavy FileIO).",
    "Grid/DCA/martingale sizing must clamp volume to SYMBOL_VOLUME_MIN/MAX/STEP "
    "and enforce a hard max-level + drawdown stop.",
    "Prefer matrix/vector and ONNX APIs (build 3620+) over manual loops for "
    "ML/linear-algebra paths where applicable.",
    "State that must survive restarts should be persisted (files/global vars).",
    "Magic-number filtering on every position/basket operation.",
)

# Severity vocabulary shared with the static layers.
_VALID_SEVERITY = {"critical", "error", "warn", "info"}


@dataclass
class ReviewPacket:
    """A single function ready for grounded LLM review."""
    file: str
    function: str
    start_line: int
    end_line: int
    code: str
    static_evidence: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "function": self.function,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "metrics": self.metrics,
            "static_evidence": self.static_evidence,
            "code": self.code,
        }


def _numbered(code: str, start_line: int) -> str:
    """Prefix each line with its absolute 1-based number for grounding."""
    out = []
    for i, ln in enumerate(code.splitlines()):
        out.append(f"{start_line + i:>5}: {ln}")
    return "\n".join(out)


def build_review_packets(
    text: str,
    *,
    file: str = "<ea>",
    graph: SymbolGraph | None = None,
    static_findings: list[dict[str, Any]] | None = None,
    max_functions: int | None = None,
) -> list[ReviewPacket]:
    """Chunk a source file by function and attach static evidence per chunk."""
    if graph is None:
        graph = build_symbol_graph(text, source=file)
    static_findings = static_findings or []
    # index findings by line so we can attach them to the owning function
    by_line: list[tuple[int | None, dict[str, Any]]] = [
        (f.get("line"), f) for f in static_findings
    ]
    packets: list[ReviewPacket] = []
    funcs = sorted(graph.functions, key=lambda f: f.start_line)
    if max_functions is not None:
        funcs = funcs[:max_functions]
    for fn in funcs:
        evidence: list[str] = []
        for line, f in by_line:
            if line is not None and fn.start_line <= line <= fn.end_line:
                evidence.append(f"L{line} [{f['severity']}] {f['title']}: {f['evidence']}")
        from .structure_audit import cyclomatic_complexity, max_nesting_depth
        packets.append(ReviewPacket(
            file=file,
            function=fn.name,
            start_line=fn.start_line,
            end_line=fn.end_line,
            code=_numbered(fn.body, fn.start_line),
            static_evidence=evidence,
            metrics={
                "loc": fn.loc,
                "arg_count": fn.arg_count,
                "complexity": cyclomatic_complexity(fn.body),
                "max_nesting": max_nesting_depth(fn.body),
            },
        ))
    return packets


def build_prompt(packet: ReviewPacket) -> str:
    """Render a self-contained grounded prompt for one function chunk."""
    rubric = "\n".join(f"  {i + 1}. {r}" for i, r in enumerate(MQL5_2026_RUBRIC))
    evidence = "\n".join(f"  - {e}" for e in packet.static_evidence) or "  (none)"
    return (
        "You are a senior MQL5 (MetaTrader 5) code reviewer. Review ONLY the "
        "function below. Report issues you can tie to a SPECIFIC line number "
        "shown in the left margin. Do not invent code that is not present.\n\n"
        f"FILE: {packet.file}\n"
        f"FUNCTION: {packet.function} (lines {packet.start_line}-{packet.end_line})\n"
        f"METRICS: {json.dumps(packet.metrics)}\n\n"
        "MQL5 2024-2026 RUBRIC:\n" + rubric + "\n\n"
        "STATIC EVIDENCE ALREADY FOUND (corroborate or extend, do not repeat blindly):\n"
        + evidence + "\n\n"
        "CODE (line-numbered):\n" + packet.code + "\n\n"
        "Respond with a JSON array. Each item: "
        '{"severity":"critical|error|warn|info","line":<int>,"title":<str>,'
        '"evidence":<str quoting the line>,"recommendation":<str>}. '
        "If nothing is wrong, return []."
    )


def pack_for_paste(packets: list[ReviewPacket]) -> str:
    """Serialise all packets into one document for manual paste into a chat LLM.

    Used when no API key is configured: the user pastes this into any model
    and pastes the JSON answers back through :func:`merge_findings`.
    """
    blocks = [
        "# MQL5 grounded line-review pack",
        "Paste each block into your LLM, collect the JSON answers, then run",
        "`mql5-ea-deep-review --apply-line-review answers.json`.",
        "",
    ]
    for i, p in enumerate(packets, 1):
        blocks.append(f"<<<CHUNK {i}: {p.function}>>>")
        blocks.append(build_prompt(p))
        blocks.append("<<<END CHUNK>>>\n")
    return "\n".join(blocks)


def _validate_line(finding: dict[str, Any], text: str) -> str:
    """Return a confidence label based on whether evidence_line is verifiable."""
    line = finding.get("line")
    lines = text.splitlines()
    if not isinstance(line, int) or not (1 <= line <= len(lines)):
        return "low"  # unverifiable line -> demote
    quoted = str(finding.get("evidence", ""))
    src_line = lines[line - 1]
    # crude grounding: does the source line share a meaningful token with quote?
    src_tokens = set(re.findall(r"[A-Za-z_]\w{2,}", src_line))
    quote_tokens = set(re.findall(r"[A-Za-z_]\w{2,}", quoted))
    if src_tokens & quote_tokens:
        return "high"
    return "medium"


def merge_findings(
    llm_findings: list[dict[str, Any]],
    static_findings: list[dict[str, Any]],
    text: str,
) -> list[dict[str, Any]]:
    """Fuse LLM + static findings, dedupe by (line,title), attach confidence.

    * Static findings are trusted (confidence=high, source=static).
    * LLM findings are validated against the source line; unverifiable ones
      are demoted to low confidence but kept for human triage.
    """
    merged: dict[tuple[Any, str], dict[str, Any]] = {}
    for f in static_findings:
        key = (f.get("line"), f.get("title", "").lower())
        item = dict(f)
        item.setdefault("category", "code_quality")
        item["source"] = "static"
        item["confidence"] = "high"
        merged[key] = item
    for f in llm_findings:
        sev = f.get("severity", "info")
        if sev not in _VALID_SEVERITY:
            sev = "info"
        title = str(f.get("title", "LLM finding"))
        key = (f.get("line"), title.lower())
        conf = _validate_line(f, text)
        if key in merged:
            # corroborated by static analysis -> boost
            merged[key]["source"] = "static+llm"
            merged[key]["confidence"] = "high"
            continue
        merged[key] = {
            "severity": sev,
            "category": f.get("category", "code_quality"),
            "title": title,
            "evidence": str(f.get("evidence", "")),
            "recommendation": str(f.get("recommendation", "")),
            "line": f.get("line"),
            "source": "llm",
            "confidence": conf,
        }
    # stable order: severity rank then line
    rank = {"critical": 0, "error": 1, "warn": 2, "info": 3}
    return sorted(
        merged.values(),
        key=lambda x: (rank.get(x["severity"], 9), x.get("line") or 0),
    )


def run_line_review(
    text: str,
    *,
    file: str = "<ea>",
    graph: SymbolGraph | None = None,
    static_findings: list[dict[str, Any]] | None = None,
    llm: Callable[[str], str] | None = None,
    max_functions: int | None = None,
) -> dict[str, Any]:
    """Full Stage-7 entry point.

    If ``llm`` (a ``prompt -> json-string`` callable) is supplied, each packet
    is reviewed and findings merged. Without it, the function returns the
    paste-pack so the caller can run the review manually (offline-safe).
    """
    packets = build_review_packets(
        text, file=file, graph=graph,
        static_findings=static_findings, max_functions=max_functions,
    )
    if llm is None:
        return {
            "mode": "pack",
            "packets": [p.to_dict() for p in packets],
            "paste_pack": pack_for_paste(packets),
        }
    llm_findings: list[dict[str, Any]] = []
    for p in packets:
        try:
            raw = llm(build_prompt(p))
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        item.setdefault("file", p.file)
                        llm_findings.append(item)
        except (ValueError, TypeError):
            continue  # ignore malformed model output, never crash the pipeline
    merged = merge_findings(llm_findings, static_findings or [], text)
    return {"mode": "review", "findings": merged,
            "function_count": len(packets)}


__all__ = [
    "MQL5_2026_RUBRIC",
    "ReviewPacket",
    "build_review_packets",
    "build_prompt",
    "pack_for_paste",
    "merge_findings",
    "run_line_review",
]
