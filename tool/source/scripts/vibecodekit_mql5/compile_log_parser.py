"""MetaEditor compile log parser and safe repair hints."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re
from typing import Any


@dataclass
class CompileIssue:
    file: str | None
    line: int | None
    column: int | None
    severity: str
    message: str
    code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PATTERNS = [
    ("undeclared_identifier", re.compile(r"undeclared identifier", re.I)),
    ("wrong_parameters_count", re.compile(r"wrong parameters count|wrong number of parameters", re.I)),
    ("cannot_convert", re.compile(r"cannot convert|possible loss of data", re.I)),
    ("include_not_found", re.compile(r"cannot open include file|include file not found|file .* not found", re.I)),
    ("semicolon_expected", re.compile(r"semicolon expected|';' expected", re.I)),
    ("method_not_found", re.compile(r"member function.*not found|class method not found|no one of the overloads", re.I)),
    ("ambiguous_call", re.compile(r"ambiguous call", re.I)),
    ("array_required", re.compile(r"array required", re.I)),
    ("object_pointer_expected", re.compile(r"object pointer expected", re.I)),
]

_LINE_RE = re.compile(
    r"(?P<file>[A-Za-z]:\\[^:(]+|[^:(\n]+\.(?:mq5|mqh))?"
    r"(?:\((?P<line>\d+),(?P<col>\d+)\))?.*?"
    r"(?P<sev>error|warning)\s*:?\s*(?P<msg>.*)",
    re.I,
)


def classify_message(message: str) -> str:
    for code, pat in _PATTERNS:
        if pat.search(message):
            return code
    return "unknown"


def parse_compile_log_text(text: str) -> list[CompileIssue]:
    issues: list[CompileIssue] = []
    for raw in text.splitlines():
        if "error" not in raw.lower() and "warning" not in raw.lower():
            continue
        m = _LINE_RE.search(raw)
        if not m:
            sev = "error" if "error" in raw.lower() else "warning"
            msg = raw.strip()
            issues.append(CompileIssue(None, None, None, sev, msg, classify_message(msg)))
            continue
        msg = (m.group("msg") or raw).strip()
        issues.append(CompileIssue(
            file=m.group("file"),
            line=int(m.group("line")) if m.group("line") else None,
            column=int(m.group("col")) if m.group("col") else None,
            severity=m.group("sev").lower(),
            message=msg,
            code=classify_message(msg),
        ))
    return issues


def parse_compile_log(path: str | Path) -> list[CompileIssue]:
    return parse_compile_log_text(Path(path).read_text(encoding="utf-8", errors="ignore"))


def repair_hints(issues: list[CompileIssue]) -> list[dict[str, Any]]:
    hints = []
    for issue in issues:
        action = "manual_review"
        if issue.code == "include_not_found":
            action = "check_include_path_or_copy_missing_mqh"
        elif issue.code == "semicolon_expected":
            action = "syntax_patch_candidate"
        elif issue.code == "undeclared_identifier":
            action = "check_scope_typo_or_missing_include"
        elif issue.code == "wrong_parameters_count":
            action = "check_mql5_api_signature"
        elif issue.code == "cannot_convert":
            action = "add_explicit_cast_or_correct_enum"
        hints.append({**issue.to_dict(), "suggested_action": action, "auto_patch_safe": action == "syntax_patch_candidate"})
    return hints
