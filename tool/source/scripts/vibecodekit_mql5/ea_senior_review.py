"""Senior-style static EA review.

This is not an LLM runtime. It is a deep static/rule analyzer that summarizes
strategy, risk, execution, state/recovery, input hygiene and release readiness.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .ea_doc_analyzer import analyze_project, read_mql_files
from .deadcode import find_dead_code
from .mq5_symbols import build_symbol_graph
from .structure_audit import audit_structure

# Unused-* finding titles suppressed for reusable library headers (.mqh): a
# toolkit header intentionally exposes helpers a single EA only partly uses.
# Reporting each as "unused" buried real findings (v2.5.0 QA review, #4).
_LIBRARY_SUPPRESS_TITLES = (
    "Unused function:",
    "Unused input:",
    "Possibly unused include:",
)


def code_quality_issues(files: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run Stage-3 structure audit + Stage-4 dead-code per source file.

    Line numbers are kept file-relative and the originating file is recorded
    in each issue's evidence string so the unified report can locate them.
    """
    issues: list[dict[str, Any]] = []
    agg = {"function_count": 0, "total_loc": 0, "max_complexity": 0,
           "dead_findings": 0, "suppressed_library_findings": 0}
    for rel, src in files.items():
        graph = build_symbol_graph(src, source=rel)
        sa = audit_structure(src, graph=graph)
        dc = find_dead_code(src, graph=graph)
        is_library = rel.lower().endswith(".mqh")
        suppressed_here = 0
        for grp in (sa["issues"], dc["issues"]):
            for it in grp:
                title = str(it.get("title", ""))
                if is_library and title.startswith(_LIBRARY_SUPPRESS_TITLES):
                    suppressed_here += 1
                    continue
                it = dict(it)
                it["file"] = rel
                it["evidence"] = f"[{rel}] " + it["evidence"]
                issues.append(it)
        agg["function_count"] += sa["metrics"]["function_count"]
        agg["total_loc"] += sa["metrics"]["total_loc"]
        agg["max_complexity"] = max(agg["max_complexity"], sa["metrics"]["max_complexity"])
        agg["dead_findings"] += max(0, dc["metrics"]["dead_findings"] - suppressed_here)
        agg["suppressed_library_findings"] += suppressed_here
    return issues, agg


def _all_text(project: Path) -> tuple[str, dict[str, str]]:
    files = read_mql_files(project)
    return "\n".join(f"\n// FILE: {k}\n{v}" for k, v in files.items()), files


def detect_strategy(text: str) -> dict[str, Any]:
    lower = text.lower()
    signals = []
    if "grid" in lower:
        signals.append("grid")
    if "hedge" in lower:
        signals.append("hedge")
    if "dca" in lower or "martingale" in lower or "lotmultiplier" in lower:
        signals.append("dca/martingale-like sizing")
    if "breaker" in lower or "swing_high" in lower or "swing_low" in lower or "smcdetector" in lower:
        signals.append("breaker/swing structure")
    if "onnx" in lower or "machine" in lower or "model" in lower:
        signals.append("ml/onnx")
    if "positions_total" in lower:
        signals.append("position basket management")
    if "copybuffer" in lower or "ihandle" in lower:
        signals.append("indicator-driven")
    if not signals:
        signals.append("custom/unknown")
    family = "grid-hedge" if "grid" in signals and "hedge" in signals else ("grid" if "grid" in signals else "custom")
    return {"family": family, "signals": signals}


def add_issue(issues: list[dict[str, Any]], severity: str, category: str, title: str, evidence: str, recommendation: str) -> None:
    issues.append({
        "severity": severity,
        "category": category,
        "title": title,
        "evidence": evidence,
        "recommendation": recommendation,
    })


def _evidence_ok(manifest: dict[str, Any], *keys: str) -> bool:
    """True only if the evidence manifest POSITIVELY proves the given flag.

    Absence of evidence is never treated as success (evidence-first).
    """
    if not isinstance(manifest, dict):
        return False
    for k in keys:
        v = manifest.get(k)
        if v is True:
            return True
        if isinstance(v, dict) and (v.get("ok") is True or v.get("passed") is True):
            return True
    return False


def review_project(project: str | Path, profile: str = "auto") -> dict[str, Any]:
    project = Path(project)
    analysis = analyze_project(project)
    text, files = _all_text(project)
    lower = text.lower()
    strategy = detect_strategy(text)
    issues: list[dict[str, Any]] = []

    # Execution review
    has_raw_ctrade = bool(re.search(r"\bCTrade\s+\w+\s*;", text))
    has_async = "CAsyncTradeExecutor" in text and "OnTradeTransaction" in text
    raw_close_loop = bool(re.search(r"for\s*\([^)]*PositionsTotal\s*\([^)]*\)[\s\S]{0,1500}?\.PositionClose\s*\(", text, flags=re.I | re.M))
    if raw_close_loop and not has_async:
        add_issue(issues, "critical", "execution", "Raw synchronous PositionClose loop", "PositionClose appears inside a PositionsTotal loop without async executor.", "Use async basket close engine with OnTradeTransaction tracking.")
    if has_async and "OnTradeTransaction" not in text:
        add_issue(issues, "critical", "execution", "Async execution without transaction hook", "CAsyncTradeExecutor detected but no OnTradeTransaction hook.", "Forward OnTradeTransaction to async executor.")
    if has_raw_ctrade and not has_async:
        add_issue(issues, "warn", "execution", "Raw CTrade usage", "CTrade object detected without async/safe wrapper.", "Wrap order execution in a safe trade manager with retry/logging.")

    # P1.1: Huge Sleep in OnTick
    if "OnTick" in text and re.search(r'Sleep\s*\(\s*\d{5,}\s*\)', text):
        add_issue(issues, "critical", "execution", "Huge Sleep in OnTick", "Sleep >10000ms detected in OnTick; blocks EA thread.", "Remove Sleep from OnTick or cap to <100ms.")

    # P1.2: Expiry/license lock detection
    if re.search(r'202[6-9]\.[0-1]\d\.[0-3]\d|AccountNumber\s*\(\s*\)\s*!=|MQLInfoString\s*\([^)]*PROGRAM_NAME[^)]*\)\s*!=', text):
        add_issue(issues, "warn", "license", "Expiry/name-lock/account-lock detected", "EA contains license/expiry/account restriction logic.", "Document license terms in user manual; ensure end-user is informed.")

    # P1.3: Basket close/profit without magic filter
    if re.search(r'\b(?:ProfitAll|ClosePositionAll|CloseAll)\s*\([^)]*\bSymbol\b[^)]*\)', text, re.I):
        if not re.search(r'Magic\s*\(\s*\)\s*==|\bm_magic\b', text):
            add_issue(issues, "error", "risk", "Basket close/profit without magic filter", "Basket operation filters by symbol but not magic; may affect other EAs.", "Add magic number filter to basket operations.")

    # P1.4: PositionGetSymbol + Magic without SelectByIndex
    if re.search(r'PositionGetSymbol\s*\(', text) and re.search(r'm_position\.Magic\s*\(', text):
        if not re.search(r'SelectByIndex\s*\(', text):
            add_issue(issues, "warn", "execution", "PositionGetSymbol + Magic() without SelectByIndex", "Magic() called after PositionGetSymbol without SelectByIndex; may use stale position object.", "Call m_position.SelectByIndex(i) before accessing Magic() in loop.")

    # Risk review
    is_grid = "grid" in strategy["signals"] or "dca" in lower or "lotmultiplier" in lower
    if is_grid:
        if not re.search(r"maxlevels|m_max_levels|levelallowed", lower):
            add_issue(issues, "critical", "risk", "Grid/DCA without max level evidence", "No MaxLevels/LevelAllowed pattern found.", "Add a hard max level limit per side.")
        if not re.search(r"maxdd|muststop|hard.?stop|stop\(\)", lower):
            add_issue(issues, "critical", "risk", "No hard drawdown stop evidence", "No MaxDD/MustStop/hard stop pattern found.", "Add account-level hard DD stop.")
        if not re.search(r"freezedd|freeze\(", lower):
            add_issue(issues, "error", "risk", "No drawdown freeze evidence", "No FreezeDD/Freeze() pattern found.", "Freeze new exposure when DD reaches warning threshold.")
        if re.search(r"lotmultiplier", lower) and not re.search(r"symbol_volume_max|volume_max", lower):
            add_issue(issues, "error", "risk", "Multiplier lot without broker volume clamp evidence", "LotMultiplier present but no SYMBOL_VOLUME_MAX clamp found.", "Clamp lots by min/max/step before sending orders.")

    # State/recovery
    if is_grid and not re.search(r"globalvariable|persistentstatestore|fileread|filewrite|state", lower):
        add_issue(issues, "error", "state", "Grid strategy without persistence/recovery evidence", "No persistent state/recovery pattern found.", "Persist basket/grid state for restart safety.")

    # Market safety
    if is_grid and not re.search(r"spread|symbol_spread|ask-bid|bid-ask", lower):
        add_issue(issues, "warn", "market_safety", "No spread filter evidence", "No spread filter pattern found.", "Add spread/slippage guard before opening grid levels.")
    if is_grid and not re.search(r"news|calendar|session|timefilter", lower):
        add_issue(issues, "info", "market_safety", "No news/session filter evidence", "No news/session guard found.", "Consider optional news/session filters for high-volatility periods.")

    # Input hygiene
    inputs = analysis.get("inputs", [])
    input_names = [p["name"] for p in inputs]
    for p in inputs:
        name = p["name"]
        occurrences = len(re.findall(r"\b" + re.escape(name) + r"\b", text))
        if occurrences <= 1:
            add_issue(issues, "warn", "input", f"Input appears unused: {name}", f"{name} appears only in declaration.", "Remove unused input or wire it into logic/docs.")
    if len(inputs) > 30:
        add_issue(issues, "warn", "input", "Large input surface", f"{len(inputs)} inputs detected.", "Group inputs and document risk-sensitive parameters clearly.")

    # Code quality (Stage 3 structure audit + Stage 4 dead-code)
    cq_issues, cq_metrics = code_quality_issues(files)
    issues.extend(cq_issues)

    # Release readiness
    if not (project / "docs" / "docs-context.json").is_file() or not (project / "docs" / "docs-prompt.md").is_file():
        add_issue(issues, "error", "docs", "Missing end-user docs bundle", "docs/docs-context.json + docs/docs-prompt.md not found (LLM docgen inputs).", "Run mql5-docs-bundle, then author guide.md and run mql5-docs-assemble.")
    manifest_path = project / "evidence" / "manifest.json"
    manifest_data: dict[str, Any] = {}
    if not manifest_path.is_file():
        add_issue(issues, "critical", "release", "Missing release evidence manifest", "evidence/manifest.json not found.", "Run real compile/backtest/evidence pipeline before release.")
    else:
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest_data = {}
            add_issue(issues, "error", "release", "Unreadable evidence manifest", "evidence/manifest.json present but not valid JSON.", "Regenerate the evidence manifest.")
    # Absence of real compile/backtest proof is a hard blocker on its own,
    # so a bare EA cannot score as 'almost ready' just for shipping a manifest stub.
    if not _evidence_ok(manifest_data, "compile_ok", "compiled", "compile"):
        add_issue(issues, "critical", "release", "No compile evidence", "Manifest does not prove a real compile (compile_ok missing/false).", "Run the real compile pipeline and record compile_ok=true.")
    if not _evidence_ok(manifest_data, "backtest_ok", "backtested", "backtest"):
        add_issue(issues, "critical", "release", "No backtest evidence", "Manifest does not prove a real backtest (backtest_ok missing/false).", "Run the real backtest pipeline and record backtest_ok=true.")

    severity_weight = {"critical": 25, "error": 12, "warn": 5, "info": 1}
    penalty = sum(severity_weight.get(i["severity"], 0) for i in issues)
    score = max(0, 100 - penalty)
    readiness = "release-blocked" if any(i["severity"] == "critical" for i in issues) else ("needs-work" if issues else "review-clean")

    return {
        "schema_version": "1.0",
        "artifact_type": "ea_senior_review",
        "project": str(project),
        "strategy": strategy,
        "score": score,
        "readiness": readiness,
        "issue_counts": {s: sum(1 for i in issues if i["severity"] == s) for s in ["critical", "error", "warn", "info"]},
        "issues": issues,
        "analysis_summary": {
            "input_count": len(inputs),
            "handlers": analysis.get("handlers", []),
            "features": analysis.get("features", {}),
            "files_scanned": analysis.get("files_scanned", []),
            "code_quality": cq_metrics,
        },
        "senior_summary": make_summary(strategy, issues, score, readiness),
    }


def make_summary(strategy: dict[str, Any], issues: list[dict[str, Any]], score: int, readiness: str) -> str:
    crit = [i for i in issues if i["severity"] == "critical"]
    err = [i for i in issues if i["severity"] == "error"]
    parts = [
        f"Strategy family detected: {strategy.get('family')} ({', '.join(strategy.get('signals', []))}).",
        f"Review score: {score}/100. Readiness: {readiness}.",
    ]
    if crit:
        parts.append("Critical blockers: " + "; ".join(i["title"] for i in crit[:5]) + ".")
    if err:
        parts.append("Major fixes recommended: " + "; ".join(i["title"] for i in err[:5]) + ".")
    if not issues:
        parts.append("No static blocking issue found, but real compile/backtest evidence is still required.")
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Senior-style static review for existing EA project.")
    ap.add_argument("--project", required=True)
    ap.add_argument("--profile", default="auto")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    report = review_project(args.project, args.profile)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["readiness"] != "release-blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
