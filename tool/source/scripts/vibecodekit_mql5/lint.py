"""mql5-lint — 8 critical anti-pattern detector for .mq5 files.

Detects (per the kit spec §7 critical AP table):
    AP-1  No-SL                       OrderSend/CTrade.Buy without sl arg
    AP-3  Lot-fixed                   hardcoded `lot = 0.01`
    AP-5  Optimizer-overfitted        > 6 input params declared
    AP-15 Raw-OrderSend               direct `OrderSend(` not via CTrade
    AP-17 WebRequest-in-OnTick        WebRequest() called in OnTick/OnTimer
    AP-18 OrderSendAsync-no-handler   async without OnTradeTransaction()
    AP-20 Hardcoded-pip               `* 0.0001`, `* _Point`, `* Point()`
    AP-21 JPY-XAU-digits-broken       `digits-tested:` meta with < 2 classes

Output formats:
    text  (default) one line per finding, `<path>:<line>:<col>: <severity> <AP>: <msg>`.
    json  agent-friendly envelope (see :mod:`vibecodekit_mql5._agent_io`).
    sarif SARIF 2.1.0 log (plugs into Cursor / VS Code / GitHub code-scanning).

Exit code: 0 = clean, 1 = at least one ERROR finding, 2 = invocation error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import _agent_io
from .rule_registry import lint_error_codes as _lint_error_codes
from .rule_registry import lint_meta as _lint_meta


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    col: int
    severity: str  # "ERROR" | "WARN"
    code: str      # "AP-1", etc.
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.severity} {self.code}: {self.message}"


# Strip block + line comments so detectors don't match commented examples.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT  = re.compile(r"//[^\n]*")


def _strip_comments(src: str) -> str:
    src = _BLOCK_COMMENT.sub("", src)
    src = _LINE_COMMENT.sub("", src)
    return src


def _line_col(src: str, idx: int) -> tuple[int, int]:
    head = src[:idx]
    line = head.count("\n") + 1
    col = idx - (head.rfind("\n") + 1) + 1
    return line, col


# ─────────────────────────────────────────────────────────────────────────────
# Detectors
# ─────────────────────────────────────────────────────────────────────────────

# AP-1 No-SL: trade.Buy/Sell without a non-zero stop-loss argument.
_TRADE_NO_SL = re.compile(r"\b(?P<obj>\w+)\.(?:Buy|Sell)\s*\((?P<args>[^)]*)\)")


def _safe_trade_objects(src: str) -> set[str]:
    pattern = re.compile(r"\bCSafeTradeManager\s+(\w+)\s*;")
    return {m.group(1) for m in pattern.finditer(src)}


def detect_ap1(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    safe_trade = _safe_trade_objects(src)
    for m in _TRADE_NO_SL.finditer(src):
        args = [a.strip() for a in m.group("args").split(",")]
        sl_idx = 2 if m.group("obj") in safe_trade else 3
        sl_present = len(args) > sl_idx and args[sl_idx] not in {"", "0", "0.0"}
        if not sl_present:
            line, col = _line_col(src, m.start())
            out.append(Finding(path, line, col, "ERROR", "AP-1",
                               "CTrade.Buy/Sell without stop-loss"))
    return out


# AP-3 Lot-fixed: assignment `lot = 0.01` (literal decimal).
_LOT_FIXED = re.compile(r"\blot\w*\s*=\s*\d+\.\d+")

def detect_ap3(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _LOT_FIXED.finditer(src):
        line, col = _line_col(src, m.start())
        out.append(Finding(path, line, col, "ERROR", "AP-3",
                           "Hardcoded lot — use CPipNormalizer.LotForRisk"))
    return out


# AP-5 Overfitted: > 6 `input` declarations.
_INPUT_DECL = re.compile(r"^\s*input\s+\w+\s+\w+", re.MULTILINE)

def detect_ap5(path: str, raw: str, src: str) -> list[Finding]:
    matches = list(_INPUT_DECL.finditer(src))
    if len(matches) > 6:
        line, col = _line_col(src, matches[6].start())
        return [Finding(path, line, col, "ERROR", "AP-5",
                        f"{len(matches)} inputs declared — risk of optimizer overfitting (> 6)")]
    return []


# AP-15 Raw-OrderSend: bare `OrderSend(` (not `Async`, not `trade.OrderSend`).
_RAW_ORDERSEND = re.compile(r"(?<![.\w])OrderSend\s*\(")

def detect_ap15(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _RAW_ORDERSEND.finditer(src):
        line, col = _line_col(src, m.start())
        out.append(Finding(path, line, col, "ERROR", "AP-15",
                           "Direct OrderSend — use CTrade for safety"))
    return out


# AP-17 WebRequest-in-OnTick: any WebRequest( inside OnTick/OnTimer body.
_FUNC_BODY = re.compile(
    r"\b(OnTick|OnTimer)\s*\([^)]*\)\s*\{(?P<body>.*?)\n\}",
    re.DOTALL,
)
_WEB_CALL = re.compile(r"\bWebRequest\s*\(")

def detect_ap17(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _FUNC_BODY.finditer(src):
        body = m.group("body")
        body_start = m.start("body")
        for w in _WEB_CALL.finditer(body):
            line, col = _line_col(src, body_start + w.start())
            out.append(Finding(path, line, col, "ERROR", "AP-17",
                               f"WebRequest in {m.group(1)} blocks the tick — move to OnInit/timer task"))
    return out


# AP-18 OrderSendAsync-no-handler: async present without OnTradeTransaction.
_ASYNC_CALL = re.compile(r"\bOrderSendAsync\s*\(")
_HANDLER    = re.compile(r"\bOnTradeTransaction\s*\(")

def detect_ap18(path: str, raw: str, src: str) -> list[Finding]:
    async_matches = list(_ASYNC_CALL.finditer(src))
    if not async_matches:
        return []
    if _HANDLER.search(src):
        return []
    line, col = _line_col(src, async_matches[0].start())
    return [Finding(path, line, col, "ERROR", "AP-18",
                    "OrderSendAsync without OnTradeTransaction handler")]


# AP-20 Hardcoded-pip: `* 0.0001`, `* 0.001`, `* _Point`, `* Point()`.
_HARDCODED_PIP = re.compile(r"\*\s*(?:0\.000?1|_Point|Point\s*\(\s*\))")

def detect_ap20(path: str, raw: str, src: str) -> list[Finding]:
    out: list[Finding] = []
    for m in _HARDCODED_PIP.finditer(src):
        line, col = _line_col(src, m.start())
        out.append(Finding(path, line, col, "ERROR", "AP-20",
                           "Hardcoded pip math — use CPipNormalizer.Pips()"))
    return out


# AP-21 JPY-XAU-digits-broken: `// digits-tested: 5` (only one class).
# Accept either `// digits-tested: 5, 3` or `//| digits-tested: 5, 3 |` (the
# MetaEditor box-comment style emitted by every wizard scaffold).
_DIGITS_TESTED = re.compile(
    r"//\s*\|?\s*digits-tested\s*:\s*([0-9,\s]+)",
    re.IGNORECASE,
)

def detect_ap21(path: str, raw: str, src: str) -> list[Finding]:
    # Search the RAW source — the meta tag lives in a comment.
    m = _DIGITS_TESTED.search(raw)
    if not m:
        return [Finding(path, 1, 1, "WARN", "AP-21",
                        "Missing `// digits-tested:` meta tag")]
    classes = {c.strip() for c in m.group(1).split(",") if c.strip()}
    if len(classes) < 2:
        line, col = _line_col(raw, m.start())
        return [Finding(path, line, col, "WARN", "AP-21",
                        f"Tested only digits class {sorted(classes)} — need ≥ 2 classes")]
    return []


_ALL_DETECTORS = [
    ("AP-1",  detect_ap1),
    ("AP-3",  detect_ap3),
    ("AP-5",  detect_ap5),
    ("AP-15", detect_ap15),
    ("AP-17", detect_ap17),
    ("AP-18", detect_ap18),
    ("AP-20", detect_ap20),
    ("AP-21", detect_ap21),
]

# Best-practice detectors are added as WARN-only.
# They live in a separate module to keep this file under its 200-LOC ceiling.
try:
    from .lint_best_practice import BEST_PRACTICE_DETECTORS
    _ALL_DETECTORS.extend(BEST_PRACTICE_DETECTORS)
except ImportError:  # pragma: no cover — defensive; module always ships
    pass
try:
    from .lint_ui import BEST_UI_DETECTORS
    _ALL_DETECTORS.extend(BEST_UI_DETECTORS)
except ImportError:  # pragma: no cover
    pass


def lint_source(path: str, raw: str) -> list[Finding]:
    src = _strip_comments(raw)
    findings: list[Finding] = []
    for _code, fn in _ALL_DETECTORS:
        findings.extend(fn(path, raw, src))
    findings.sort(key=lambda f: (f.line, f.col, f.code))
    return findings


def lint_sources(files: dict[str, str]) -> list[Finding]:
    """Lint a coherent project source set with cross-file event context."""
    has_transaction_handler = any(
        _HANDLER.search(_strip_comments(raw)) for raw in files.values()
    )
    findings: list[Finding] = []
    for path, raw in files.items():
        for finding in lint_source(path, raw):
            if finding.code == "AP-18" and has_transaction_handler:
                continue
            findings.append(finding)
    findings.sort(
        key=lambda finding: (finding.path, finding.line, finding.col, finding.code)
    )
    return findings


def lint_file(path: Path) -> list[Finding]:
    from .mq5_io import read_mq5_text

    return lint_source(str(path), read_mq5_text(path, errors="replace"))


def lint_file_ast(path: Path) -> list[Finding]:
    """.D POC: AST-retrofitted lint pass.

    Runs the lightweight MQL5 structure-scanner under
    :mod:`vibecodekit_mql5.ast_parser` and uses AST-flavoured
    detectors for AP-1, AP-2 and AP-7. All other detectors still
    run as regex so the full Plan-v5 §7 coverage is preserved.
    """
    from .ast_parser import lint_source_ast
    from .mq5_io import read_mq5_text

    return lint_source_ast(str(path), read_mq5_text(path, errors="replace"))


# ----------------------------------------------------------------------------
# Output formatters
# ----------------------------------------------------------------------------

# Mapping AP code -> SARIF rule id + short description for the run.tool block.
# SARIF needs a stable rule id per AP-code so the run.tool.driver.rules array
# advertises every rule that could fire.
#
# The catalogue and per-rule severity now live in the single source of truth
# `rule_registry`. lint.py is a *consumer*: ERROR-severity (critical) detectors
# live in this module, WARN-only detectors in lint_best_practice, but both draw
# their identity/metadata from the registry so the three modules cannot drift.

_RULE_META: dict[str, tuple[str, str]] = _lint_meta()


def findings_to_sarif(findings: list[Finding]) -> dict:
    """Render findings as a SARIF 2.1.0 log document.

    Returns a Python dict ready for ``json.dumps``. Conforms to
    https://docs.oasis-open.org/sarif/sarif/v2.1.0/.
    """

    # Always emit the full rule catalogue so consumers see every AP, even
    # when the current run produced no finding for it. The the kit spec §7
    # critical-AP set defaults to SARIF `level=error`; everything else
    # defaults to `warning`. Severity is sourced from the rule registry.
    _ERROR_APS = _lint_error_codes()
    rules = []
    for code, (rule_id, short) in _RULE_META.items():
        rules.append({
            "id": rule_id,
            "name": code,
            "shortDescription": {"text": short},
            "fullDescription": {"text": short},
            "defaultConfiguration": {
                "level": "error" if code in _ERROR_APS else "warning",
            },
            "properties": {"ap_code": code},
        })

    results = []
    for f in findings:
        rule_id, _ = _RULE_META.get(f.code, (f.code.lower(), f.message))
        results.append({
            "ruleId": rule_id,
            "level": "error" if f.severity == "ERROR" else "warning",
            "message": {"text": f"{f.code}: {f.message}"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.path},
                    "region": {"startLine": f.line, "startColumn": f.col},
                },
            }],
            "properties": {"ap_code": f.code, "severity": f.severity},
        })

    return {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "mql5-lint",
                    "informationUri": "https://github.com/VibeMql5Codekit/vibecodekit-mql5-ea",
                    "rules": rules,
                },
            },
            "results": results,
        }],
    }


def findings_to_envelope_data(findings: list[Finding]) -> dict:
    return {
        "finding_count": len(findings),
        "error_count": sum(1 for f in findings if f.severity == "ERROR"),
        "warn_count": sum(1 for f in findings if f.severity == "WARN"),
        "findings": [
            {
                "path": f.path,
                "line": f.line,
                "column": f.col,
                "severity": f.severity,
                "code": f.code,
                "message": f.message,
            }
            for f in findings
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-lint", description=__doc__.splitlines()[0])
    p.add_argument("files", nargs="+", help=".mq5 file(s) to lint")
    p.add_argument("--format",
                   choices=("text", "sarif"),
                   default="text",
                   help="Output format. `sarif` emits a SARIF 2.1.0 log "
                        "that plugs into Cursor / GitHub code-scanning.")
    p.add_argument("--use-ast",
                   action="store_true",
                   help=".D POC: run AP-1, AP-2 and AP-7 through the "
                        "lightweight MQL5 AST scanner instead of the regex "
                        "detector. All other AP codes still use regex. "
                        "Findings are byte-identical to the regex pipeline "
                        "on the golden EA-bug fixtures.")
    _agent_io.add_json_flag(p)
    _agent_io.add_gate_report_flag(p)
    _agent_io.add_draft_flag(p)
    args = p.parse_args(argv)

    any_error = False
    all_findings: list[Finding] = []
    evidence: list[str] = []
    lint_fn = lint_file_ast if args.use_ast else lint_file
    for f in args.files:
        path = Path(f)
        if not path.is_file():
            print(f"{f}: not a file", file=sys.stderr)
            return 2
        evidence.append(str(path))
        for finding in lint_fn(path):
            all_findings.append(finding)
            if finding.severity == "ERROR":
                any_error = True

    exit_code = 1 if any_error else 0
    envelope = _agent_io.Envelope(
        tool="mql5-lint",
        ok=not any_error,
        exit_code=exit_code,
        summary=(f"{len(all_findings)} finding(s): "
                 f"{sum(1 for x in all_findings if x.severity == 'ERROR')} ERROR, "
                 f"{sum(1 for x in all_findings if x.severity == 'WARN')} WARN"),
        data=findings_to_envelope_data(all_findings),
        evidence=evidence,
        matrix_dim="d_correctness",
        matrix_axis="implement",
        matrix_status="PASS" if not any_error else "FAIL",
    )
    _agent_io.apply_draft(envelope, args.draft)

    if args.format == "sarif":
        # SARIF is the structured output; suppress the per-finding text lines.
        print(json.dumps(findings_to_sarif(all_findings), indent=2))
    elif args.emit_json:
        # JSON envelope is the structured output; emit it via the helper.
        _agent_io.emit(envelope)
    else:
        for finding in all_findings:
            print(finding.format())

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return envelope.exit_code


if __name__ == "__main__":
    sys.exit(main())
