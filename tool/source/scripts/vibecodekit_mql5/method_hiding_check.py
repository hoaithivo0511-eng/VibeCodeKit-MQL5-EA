"""mql5-method-hiding-check — detect MQL5 inheritance hiding without `using`.

the kit spec §14 — MetaEditor build 5260+ (May 2025) treats unqualified
method redefinition in a derived class as ERROR instead of WARNING.
Migrating EAs must add explicit ``using BaseClass::method;`` directives
to opt back into the legacy hiding behaviour or rename methods.

This detector uses a regex heuristic (full MQL5 AST is not feasible
inside the kit) and accepts ``// vck-mql5: hiding-ok`` annotations on
the offending line as an opt-out.

Severity is build-dependent:
    target_build  < 5260 → WARN  (legacy MetaEditor — backwards compat)
    target_build >= 5260 → ERROR (strict, ships behaviour change)

False-positive tolerance: ≤ 30%, enforced by the bundled gate tests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BUILD_STRICT_THRESHOLD = 5260

CLASS_DEF = re.compile(
    r"class\s+(?P<name>\w+)\s*(?::\s*public\s+(?P<base>\w+))?\s*\{",
)
METHOD_DEF = re.compile(
    r"^\s*(?:virtual\s+)?(?:[\w:<>,\s\*&]+?)\s+(?P<name>\w+)\s*\("
    r"(?P<args>[^)]*)\)\s*(?:const\s*)?(?:override\s*)?[;{]",
    re.MULTILINE,
)
USING_DIRECTIVE = re.compile(r"using\s+(?P<base>\w+)::(?P<method>\w+)\s*;")
HIDING_OK_PRAGMA = "// vck-mql5: hiding-ok"


@dataclass
class HidingIssue:
    file: str
    line: int
    derived_class: str
    base_class: str
    method: str
    severity: str  # WARN | ERROR
    fix_hint: str


@dataclass
class CheckReport:
    ok: bool
    path: str
    target_build: int
    issues: list[HidingIssue] = field(default_factory=list)

    def as_json(self) -> str:
        return json.dumps(
            {
                "ok": self.ok, "path": self.path, "target_build": self.target_build,
                "issues": [iss.__dict__ for iss in self.issues],
            },
            indent=2,
        )


def _collect_class_bodies(src: str) -> list[tuple[str, str | None, int, str]]:
    """Return list of (class_name, base_name, body_start_line, body_text)."""
    results: list[tuple[str, str | None, int, str]] = []
    for m in CLASS_DEF.finditer(src):
        name = m.group("name")
        base = m.group("base")
        start = m.end()
        depth = 1
        idx = start
        while idx < len(src) and depth > 0:
            c = src[idx]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            idx += 1
        body = src[start: idx - 1]
        line_no = src[: m.start()].count("\n") + 1
        results.append((name, base, line_no, body))
    return results


def check_method_hiding(mq5_path: Path, target_build: int = 5260) -> CheckReport:
    if not mq5_path.exists():
        return CheckReport(False, str(mq5_path), target_build, [])
    from .mq5_io import read_mq5_text

    src = read_mq5_text(mq5_path, errors="replace")
    classes = _collect_class_bodies(src)
    by_name = {name: body for name, _, _, body in classes}

    severity = "ERROR" if target_build >= BUILD_STRICT_THRESHOLD else "WARN"
    issues: list[HidingIssue] = []

    for derived, base, body_line, body in classes:
        if not base or base not in by_name:
            continue
        base_methods = {m.group("name") for m in METHOD_DEF.finditer(by_name[base])}
        using_methods = {m.group("method") for m in USING_DIRECTIVE.finditer(body)
                         if m.group("base") == base}
        for m in METHOD_DEF.finditer(body):
            method_name = m.group("name")
            if method_name == derived or method_name == "~" + derived:
                continue  # ctor / dtor
            if method_name not in base_methods:
                continue
            if method_name in using_methods:
                continue
            line_in_body = body[: m.start()].count("\n")
            absolute_line = body_line + line_in_body
            # Check for hiding-ok pragma on the same or previous line.
            src_lines = src.splitlines()
            if absolute_line - 1 < len(src_lines):
                near = " ".join(src_lines[max(0, absolute_line - 2): absolute_line + 1])
                if HIDING_OK_PRAGMA in near:
                    continue
            issues.append(HidingIssue(
                file=str(mq5_path), line=absolute_line,
                derived_class=derived, base_class=base, method=method_name,
                severity=severity,
                fix_hint=f"add `using {base}::{method_name};` or annotate `{HIDING_OK_PRAGMA}`",
            ))
    return CheckReport(
        ok=not (severity == "ERROR" and issues),
        path=str(mq5_path), target_build=target_build, issues=issues,
    )


def report_to_sarif(rep: CheckReport) -> dict:
    """Render a method-hiding check report as SARIF 2.1.0."""

    rule = {
        "id": "mql5-method-hiding",
        "name": "method-hiding-no-using",
        "shortDescription": {"text": "Derived MQL5 class hides base method without `using`"},
        "fullDescription": {
            "text": "MetaEditor build 5260+ treats unqualified method redefinition in "
                    "a derived class as ERROR. Add `using Base::method;` or annotate "
                    "`// vck-mql5: hiding-ok`.",
        },
        "defaultConfiguration": {
            "level": "error" if rep.target_build >= BUILD_STRICT_THRESHOLD else "warning",
        },
        "properties": {"target_build": rep.target_build},
    }

    results = []
    for iss in rep.issues:
        results.append({
            "ruleId": rule["id"],
            "level": "error" if iss.severity == "ERROR" else "warning",
            "message": {
                "text": (f"{iss.derived_class} hides {iss.base_class}::{iss.method}. "
                         f"{iss.fix_hint}"),
            },
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": iss.file},
                    "region": {"startLine": iss.line, "startColumn": 1},
                },
            }],
            "properties": {
                "derived_class": iss.derived_class,
                "base_class": iss.base_class,
                "method": iss.method,
            },
        })

    return {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "mql5-method-hiding-check",
                    "informationUri": "https://github.com/VibeMql5Codekit/vibecodekit-mql5-ea",
                    "rules": [rule],
                },
            },
            "results": results,
        }],
    }


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    parser = argparse.ArgumentParser(prog="mql5-method-hiding-check")
    parser.add_argument("mq5", help="Path to .mq5 / .mqh source")
    parser.add_argument("--build", type=int, default=BUILD_STRICT_THRESHOLD)
    parser.add_argument("--format", choices=("text", "sarif"), default="text",
                        help="Output format. `sarif` emits SARIF 2.1.0; "
                             "`text` (default) emits the legacy JSON report.")
    _agent_io.add_json_flag(parser)
    _agent_io.add_gate_report_flag(parser)
    args = parser.parse_args(argv)

    rep = check_method_hiding(Path(args.mq5), target_build=args.build)

    envelope = _agent_io.Envelope(
        tool="mql5-method-hiding-check",
        ok=rep.ok,
        exit_code=0 if rep.ok else 1,
        summary=(f"{len(rep.issues)} hiding issue(s) at build {rep.target_build}"
                 if rep.issues else f"clean at build {rep.target_build}"),
        data={
            "target_build": rep.target_build,
            "issues": [iss.__dict__ for iss in rep.issues],
        },
        evidence=[rep.path],
        matrix_dim="d_correctness",
        matrix_axis="implement",
        matrix_status="PASS" if rep.ok else "FAIL",
    )

    if args.format == "sarif":
        print(json.dumps(report_to_sarif(rep), indent=2))
    elif args.emit_json:
        _agent_io.emit(envelope)
    else:
        print(rep.as_json())

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
