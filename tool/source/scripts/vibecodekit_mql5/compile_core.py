from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
import re


class CompileFailureCode(str, Enum):
    TOOLCHAIN_INSTALL_FAILED = "TOOLCHAIN_INSTALL_FAILED"
    TOOLCHAIN_PROBE_FAILED = "TOOLCHAIN_PROBE_FAILED"
    SOURCE_STAGE_FAILED = "SOURCE_STAGE_FAILED"
    COMPILE_ERRORS = "COMPILE_ERRORS"
    COMPILE_WARNINGS = "COMPILE_WARNINGS"
    LOG_MISSING = "LOG_MISSING"
    RESULT_MISSING = "RESULT_MISSING"
    EX5_MISSING = "EX5_MISSING"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    SOURCE_BINDING_MISMATCH = "SOURCE_BINDING_MISMATCH"
    INVOCATION_FAILED = "INVOCATION_FAILED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class CompilePolicy:
    max_errors: int = 0
    max_warnings: int = 0
    require_result_summary: bool = True
    require_ex5: bool = True


@dataclass
class CompileEvaluation:
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    result_summary: str | None = None
    ex5_path: str | None = None
    raw_log: str = ""
    failure_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_RESULT_RE = re.compile(
    r"\bResult:\s*(?P<errors>\d+)\s+errors?\s*,\s*(?P<warnings>\d+)\s+warnings?\b",
    re.IGNORECASE,
)


def decode_metaeditor_log_bytes(raw: bytes) -> str:
    """Decode MetaEditor logs conservatively across native/Wine variants."""
    if not raw:
        return ""
    for enc in ("utf-16", "utf-16-le", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if text.count("\x00") > max(1, len(text) // 20):
            continue
        return text.lstrip("\ufeff")
    return raw.decode("latin-1", errors="replace").lstrip("\ufeff")


def read_metaeditor_log(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    return decode_metaeditor_log_bytes(p.read_bytes())


def _append_code(codes: list[str], code: CompileFailureCode) -> None:
    if code.value not in codes:
        codes.append(code.value)


def parse_metaeditor_log(
    text: str,
    *,
    policy: CompilePolicy | None = None,
    ex5_path: str | Path | None = None,
) -> CompileEvaluation:
    policy = policy or CompilePolicy()
    diagnostics_errors: list[str] = []
    diagnostics_warnings: list[str] = []
    result_summary: str | None = None
    result_errors: int | None = None
    result_warnings: int | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _RESULT_RE.search(line)
        if match:
            result_summary = line
            result_errors = int(match.group("errors"))
            result_warnings = int(match.group("warnings"))
            continue
        low = line.lower()
        if ": error " in low:
            diagnostics_errors.append(line)
        elif ": warning " in low:
            diagnostics_warnings.append(line)

    failure_codes: list[str] = []
    errors = list(diagnostics_errors)
    warnings = list(diagnostics_warnings)

    if result_summary is None:
        if policy.require_result_summary:
            _append_code(failure_codes, CompileFailureCode.RESULT_MISSING)
            errors.append("compile: MetaEditor log has no parseable 'Result:' summary line")
        error_count = len(diagnostics_errors)
        warning_count = len(diagnostics_warnings)
    else:
        error_count = int(result_errors or 0)
        warning_count = int(result_warnings or 0)

    if error_count > policy.max_errors:
        _append_code(failure_codes, CompileFailureCode.COMPILE_ERRORS)
        if not diagnostics_errors:
            errors.append(
                f"compile: MetaEditor reported {error_count} errors (allowed {policy.max_errors})"
            )

    if warning_count > policy.max_warnings:
        _append_code(failure_codes, CompileFailureCode.COMPILE_WARNINGS)
        if not diagnostics_warnings:
            warnings.append(
                f"compile: MetaEditor reported {warning_count} warnings (allowed {policy.max_warnings})"
            )

    resolved_ex5: str | None = None
    if ex5_path is not None:
        ex5 = Path(ex5_path)
        if ex5.is_file():
            resolved_ex5 = str(ex5)
        elif policy.require_ex5:
            _append_code(failure_codes, CompileFailureCode.EX5_MISSING)
            errors.append(f"compile: expected .ex5 artifact was not produced: {ex5}")
    elif policy.require_ex5:
        _append_code(failure_codes, CompileFailureCode.EX5_MISSING)
        errors.append("compile: expected .ex5 artifact path was not supplied")

    return CompileEvaluation(
        success=not failure_codes,
        errors=errors,
        warnings=warnings,
        error_count=error_count,
        warning_count=warning_count,
        result_summary=result_summary,
        ex5_path=resolved_ex5,
        raw_log=text,
        failure_codes=failure_codes,
    )


def evaluate_compile_files(
    log_path: str | Path,
    ex5_path: str | Path,
    *,
    policy: CompilePolicy | None = None,
) -> CompileEvaluation:
    policy = policy or CompilePolicy()
    log = Path(log_path)
    if not log.is_file():
        result = parse_metaeditor_log("", policy=policy, ex5_path=ex5_path)
        _append_code(result.failure_codes, CompileFailureCode.LOG_MISSING)
        result.errors.insert(0, f"compile: MetaEditor log was not produced: {log}")
        result.success = False
        return result
    return parse_metaeditor_log(read_metaeditor_log(log), policy=policy, ex5_path=ex5_path)
