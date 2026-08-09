"""Evidence-bound claim analysis for EA manuals.

This module creates a claim ledger from actual source patterns. The doc generator
must only describe claims that are supported here, or explicitly mark them as
not implemented/placeholder.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse, json
import re

from .mq5_symbols import strip_comments_and_strings

_INCLUDE_LINE = re.compile(r"^\s*#\s*include\b")


def read_sources(project: str | Path) -> dict[str, str]:
    root = Path(project)
    files: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".mq5", ".mqh"}:
            files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8", errors="ignore")
    return files


def find_evidence(
    files: dict[str, str], patterns: list[str], *, code_only: bool = True,
) -> list[dict[str, Any]]:
    """Find pattern hits in source.

    ``code_only`` (default) blanks comments + string/char literals and skips
    ``#include`` directive lines, so a claim can never be "proven" by a code
    comment, a doc banner, or the mere presence of a bundled library header.
    This is the evidence-integrity fix for the v2.5.0 QA review (blocker #3):
    docs must reflect logic that is actually wired in code, not prose.
    """
    out: list[dict[str, Any]] = []
    for rel, text in files.items():
        raw_lines = text.splitlines()
        scan_lines = (
            strip_comments_and_strings(text).splitlines() if code_only
            else raw_lines
        )
        for pat in patterns:
            rx = re.compile(pat, re.I)
            for idx, line in enumerate(scan_lines, start=1):
                if code_only and _INCLUDE_LINE.match(line):
                    continue
                if rx.search(line):
                    snippet = (
                        raw_lines[idx - 1] if idx - 1 < len(raw_lines) else line
                    ).strip()[:220]
                    out.append({"file": rel, "line": idx, "pattern": pat, "snippet": snippet})
    return out


def make_claim_ledger(project: str | Path) -> dict[str, Any]:
    files = read_sources(project)
    # "Weak" capability claims must be evidenced in the EA *entrypoint* (.mq5)
    # — i.e. actually wired by the EA — not merely present inside a bundled
    # library header (.mqh). This stops over-claiming features like ONNX /
    # spread / news filters that ship as unused toolkit includes (QA #3).
    entry_files = {
        k: v for k, v in files.items() if k.lower().endswith(".mq5")
    } or files
    weak_claims = {"news_filter", "spread_filter", "ml_filter"}
    claim_defs = [
        ("hedge_grid_initial_entries", "EA can open initial Buy/Sell hedge positions", [r"OpenInitialHedge", r"BuyFast\s*\(", r"SellFast\s*\("]),
        ("smc_breaker_detection", "EA detects buy/sell breaker from swing high/low", [r"SMCDetector", r"BUY_BREAKER", r"SELL_BREAKER", r"BreakerMode", r"iHighest", r"iLowest"]),
        ("async_trade_execution", "EA uses async trade execution", [r"CAsyncTradeExecutor", r"SetAsyncMode\s*\(\s*true\s*\)", r"OnTradeTransaction"]),
        ("async_losing_side_close", "EA closes losing side asynchronously on breaker", [r"ReduceLosingSideOnBreaker", r"CloseSideFast"]),
        ("async_basket_close", "EA closes basket asynchronously", [r"CloseBasketFast", r"VirtualTPAndBasketTrail"]),
        ("grid_level_limit", "EA limits grid levels", [r"InpMaxLevels", r"LevelAllowed", r"m_max_levels"]),
        ("drawdown_freeze", "EA freezes new exposure at drawdown threshold", [r"InpFreezeDDPercent", r"Freeze\s*\(", r"ShouldFreeze"]),
        ("drawdown_hard_stop", "EA stops opening exposure at max drawdown", [r"InpMaxDDPercent", r"Stop\s*\(", r"MustStop"]),
        ("persistent_state", "EA persists state", [r"CPersistentStateStore", r"GlobalVariable", r"PersistentState\.Save"]),
        ("structured_logging", "EA writes structured logs", [r"CStructuredLogger", r"StructuredLog", r"\{\\\"level\\\""]),
        ("account_seed_divergence", "EA uses account seed divergence", [r"AccountSeed", r"ACCOUNT_LOGIN", r"InpUseAccountSeedDivergence"]),
        ("virtual_tp", "EA uses VirtualTP basket close threshold", [r"InpVirtualTPPoints", r"m_virtual_tp", r"SYMBOL_TRADE_TICK_VALUE"]),
        ("basket_trailing_full", "EA implements full basket trailing", [r"trailing_stop", r"trail_lock", r"BasketTrail", r"m_trail_start"]),
        ("news_filter", "EA has a news filter", [r"CalendarValueHistory", r"CalendarValue\w*\s*\(", r"\bCNewsFilter\b", r"\bIsNewsTime\b", r"\bInpUseNews\w*\b", r"\bNewsBlackout\b"]),
        ("spread_filter", "EA has a spread filter", [r"SYMBOL_SPREAD", r"\bCSpreadGuard\s+\w", r"\bIsSpreadOK\b", r"\bSpreadOK\s*\(", r"\bInpMaxSpread\w*\b"]),
        ("ml_filter", "EA uses ML/ONNX filter", [r"\bOnnxRun\b", r"\bOnnxCreate\w*\b", r"\bCOnnxLoader\s+\w", r"\bMLPredict\b", r"\bml_predict\b"])
    ]
    claims=[]
    for cid, desc, pats in claim_defs:
        scope = entry_files if cid in weak_claims else files
        ev=find_evidence(scope,pats)
        supported=bool(ev)
        # stricter claims require multiple anchors
        if cid in {"async_trade_execution"}:
            supported=bool(find_evidence(files,[r"SetAsyncMode\s*\(\s*true\s*\)"])) and bool(find_evidence(files,[r"OnTradeTransaction"]))
        if cid in {"async_losing_side_close"}:
            supported=bool(find_evidence(files,[r"ReduceLosingSideOnBreaker"])) and bool(find_evidence(files,[r"CloseSideFast"]))
        if cid in {"async_basket_close"}:
            supported=bool(find_evidence(files,[r"CloseBasketFast"])) and bool(find_evidence(files,[r"VirtualTPAndBasketTrail"]))
        if cid in {"basket_trailing_full"}:
            # input alone is not enough; require stateful trail lock/stop semantics
            supported=bool(find_evidence(files,[r"trail_lock", r"trailing_stop"]))
        claims.append({
            "id": cid,
            "description": desc,
            "supported": supported,
            "confidence": "high" if supported else "none",
            "evidence": ev[:20],
        })
    return {"schema_version":"1.0","artifact_type":"ea_doc_claim_ledger","project":str(project),"claims":claims}


def write_claim_ledger(project: str | Path, out: str | Path) -> dict[str, Any]:
    ledger=make_claim_ledger(project)
    p=Path(out); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    return ledger


def claim_supported(ledger: dict[str, Any], claim_id: str) -> bool:
    for c in ledger.get("claims", []):
        if c.get("id") == claim_id:
            return bool(c.get("supported"))
    return False

_RELEASE_CLAIM = re.compile(r"\b(?:production[- ]?ready|live[- ]?ready|release[- ]?eligible)\b", re.I)

def audit_document(project: str | Path, document: str | Path) -> list[dict[str, Any]]:
    """Flag release-looking prose unless canonical evidence validates it."""
    text = Path(document).read_text(encoding="utf-8", errors="ignore")
    findings=[]
    from .release_policy import validate_release_manifest
    valid, reason = validate_release_manifest(Path(project))
    if not valid:
        for m in _RELEASE_CLAIM.finditer(text):
            findings.append({"line": text[:m.start()].count("\n")+1, "claim": m.group(0), "reason": reason})
    return findings

def main(argv: list[str] | None = None) -> int:
    ap=argparse.ArgumentParser(prog="ea-doc-claims", description="Audit EA documentation claims against source and release evidence.")
    ap.add_argument("project", type=Path)
    ap.add_argument("--document", type=Path)
    ap.add_argument("--out", type=Path)
    args=ap.parse_args(argv)
    ledger=make_claim_ledger(args.project)
    findings=audit_document(args.project,args.document) if args.document else []
    payload={"ok":not findings,"ledger":ledger,"document_findings":findings}
    if args.out: args.out.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(payload,indent=2,ensure_ascii=False))
    return 0 if not findings else 1

if __name__ == "__main__":
    raise SystemExit(main())
