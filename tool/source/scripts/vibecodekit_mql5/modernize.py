"""Stage-6 modernization advisor.

Detects legacy MQL4/early-MQL5 idioms and recommends the modern MQL5 build
2024-2026 equivalents. Findings are advisory (severity 'info'/'warn') and
go under category ``modernize`` so the orchestrator can present them as an
\"upgrade opportunities\" section rather than blocking defects.

Every detector strips comments/strings first (shared Stage-0 helper) so
commented-out legacy code is not flagged.
"""
from __future__ import annotations

import re
from typing import Any

from .mq5_symbols import line_of, strip_comments_and_strings


def _issue(severity: str, title: str, evidence: str, rec: str,
           line: int | None = None) -> dict[str, Any]:
    d = {
        "severity": severity,
        "category": "modernize",
        "title": title,
        "evidence": evidence,
        "recommendation": rec,
    }
    if line is not None:
        d["line"] = line
    return d


# (regex, severity, title, recommendation). Each pattern targets a legacy
# construct with a well-defined modern replacement.
_DETECTORS: tuple[tuple[re.Pattern[str], str, str, str], ...] = (
    (re.compile(r"\bOrderSend\s*\(", re.I), "warn",
     "Legacy OrderSend() call",
     "Use CTrade / MqlTradeRequest+OrderSend(request,result) and check "
     "result.retcode against the ENUM_TRADE_RETURN_CODES."),
    (re.compile(r"\bOrderSelect\s*\([^)]*\bSELECT_BY_(?:POS|TICKET)\b", re.I), "warn",
     "MQL4-style OrderSelect()",
     "Use the MQL5 ticket-based OrderSelect(ticket) API, or position/deal APIs as appropriate."),
    (re.compile(r"\b(OrderClose|OrderModify)\s*\(", re.I), "warn",
     "MQL4 order API",
     "Migrate to CTrade position/order methods or MqlTradeRequest."),
    (re.compile(r"\bArrayCopyRates\s*\(", re.I), "info",
     "Deprecated ArrayCopyRates()",
     "Use CopyRates() into an MqlRates[] array."),
    (re.compile(r"\bRefreshRates\s*\(", re.I), "info",
     "MQL4 RefreshRates()",
     "Not needed in MQL5; use SymbolInfoTick()/CopyRates for fresh data."),
    (re.compile(r"\bWindowsTotal\s*\(|\bWindowFind\s*\(", re.I), "info",
     "Legacy Window* chart API",
     "Use Chart*/ChartIndicatorAdd functions in MQL5."),
    (re.compile(r"\bDoubleToStr\b|\bStrToDouble\b|\bStrToInteger\b", re.I),
     "info", "MQL4 conversion helpers",
     "Use DoubleToString/StringToDouble/StringToInteger (MQL5 names)."),
    (re.compile(r"\bday\s*\(\)|\bmonth\s*\(\)|\byear\s*\(\)", re.I), "info",
     "Legacy date functions",
     "Use TimeToStruct() with MqlDateTime for date components."),
)

# Opportunity hints: present when manual numeric loops could use matrix/vector
# or ONNX (build 3620+).
_MATRIX_HINT = re.compile(
    r"for\s*\([^)]*\)\s*{[^}]*\[[^\]]*\]\s*[*+]\s*[^}]*}", re.S)
_ML_HINT = re.compile(r"\bneural|\bweights?\b|\bgradient|\bperceptron", re.I)


def analyze_modernization(text: str) -> dict[str, Any]:
    code = strip_comments_and_strings(text)
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for pat, sev, title, rec in _DETECTORS:
        for m in pat.finditer(code):
            ln = line_of(code, m.start())
            key = (title, ln)
            if key in seen:
                continue
            seen.add(key)
            snippet = code[m.start():m.start() + 60].splitlines()[0].strip()
            issues.append(_issue(sev, title, f"`{snippet}` at line {ln}.", rec, ln))
            if len([i for i in issues if i["title"] == title]) >= 5:
                break  # cap repeats per detector

    if _ML_HINT.search(code) and "OnnxCreate" not in code and "matrix" not in code:
        issues.append(_issue(
            "info", "ML logic without ONNX/matrix APIs",
            "Neural/weight/gradient keywords present but no Onnx*/matrix usage.",
            "Consider the MQL5 ONNX runtime (build 3620/5572+) or matrix/vector "
            "types for ML inference instead of manual loops."))

    if _MATRIX_HINT.search(code) and "matrix" not in code and "vector" not in code:
        issues.append(_issue(
            "info", "Manual numeric loop could use matrix/vector",
            "Element-wise array arithmetic inside an explicit loop detected.",
            "Consider MQL5 matrix/vector types (build 3620+) for clearer, "
            "vectorized math instead of manual element loops."))

    return {
        "issues": issues,
        "metrics": {"modernize_findings": len(issues)},
    }


__all__ = ["analyze_modernization"]
