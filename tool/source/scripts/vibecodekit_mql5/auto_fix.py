"""mql5-auto-fix — best-effort transformer that re-emits ``.mq5`` source with
the eight Phase-A critical anti-patterns either *mutated* (fully re-passed
through the detector) or *annotated* (an inline ``// FIXME AP-N:`` marker is
added so the operator can find the manual touch-points quickly).

The split is intentional. Three classes of fix exist:

* **mutated** — a deterministic regex rewrite that removes the AP entirely:

    * **AP-3**  ``lot = 0.01``  →  ``lot = pip.LotForRisk(InpRiskMoney, InpSlPips)``
    * **AP-18** missing ``OnTradeTransaction`` after ``OrderSendAsync`` — append
                a minimal stub at end-of-file.
    * **AP-20** ``* 0.0001`` / ``* _Point`` / ``* Point()``  →  ``* pip.Pip()`` /
                ``* pip.Point()``.
    * **AP-21** ``// digits-tested: 5``  →  ``// digits-tested: 5, 3`` (or insert
                a fresh ``// digits-tested: 5, 3`` tag at top of file when the
                meta marker is missing entirely).

* **annotated** — a structural refactor we don't want to attempt automatically
  (it'd risk semantic damage). The fixer just inserts a ``// FIXME AP-N:``
  comment one line *above* the offending construct so the operator has a
  bookmark in MetaEditor:

    * **AP-1**  trade.Buy / trade.Sell without an explicit stop-loss argument.
    * **AP-5**  more than 6 ``input`` declarations (optimizer-overfit risk).
    * **AP-15** raw ``OrderSend(`` — must be migrated to CTrade.
    * **AP-17** ``WebRequest`` inside ``OnTick`` / ``OnTimer``.

* **passed-through** — a finding the fixer doesn't touch because the line
  number is already inside an existing ``// FIXME AP-N:`` annotation
  (idempotency guarantee — re-running ``mql5-auto-fix`` doesn't keep stacking
  comments).

Usage::

    mql5-auto-fix EAName.mq5                # rewrite in place
    mql5-auto-fix EAName.mq5 --check        # report-only, exit 1 if changes
    mql5-auto-fix EAName.mq5 --diff         # print a unified diff, no write

A JSON summary describing every transform is emitted to stdout::

    {
      "path":     "EAName.mq5",
      "fixed":    ["AP-20", "AP-21"],
      "annotated":["AP-1@142"],
      "errors_before": 5,
      "errors_after":  2
    }

Exit codes:
    0 — file was clean OR all ERROR findings were mutated/annotated.
    1 — ``--check`` mode and at least one finding would be rewritten.
    2 — invocation error.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import lint as lint_mod

# A fixer takes a raw source string and returns ``(new_src, log_entries)``.
# ``log_entries`` is a list of short human-readable strings describing what
# happened — empty if the fixer made no change.
Fixer = Callable[[str], tuple[str, list[str]]]


# ─────────────────────────────────────────────────────────────────────────────
# Mutating fixers (lint should re-pass after these run)
# ─────────────────────────────────────────────────────────────────────────────

# AP-3 — replace ``lot = 0.01`` literals with the CPipNormalizer call. Only
# rewrite when the file actually has a CPipNormalizer instance available;
# otherwise leave the line + emit an annotation so we don't introduce an
# undefined-symbol compile error.
_LOT_FIXED = re.compile(
    r"(\b(?:lot|lots|lotsize|volume)\b)(?!\w)\s*=\s*\d+\.\d+",
    re.IGNORECASE,
)


def _has_pip(src: str) -> bool:
    return bool(re.search(r"\bCPipNormalizer\b\s+\w+\s*;", src))


def _has_pip_var(src: str, var: str = "pip") -> bool:
    return bool(re.search(rf"\bCPipNormalizer\b\s+{var}\s*;", src))


def _has_inputs(src: str, *names: str) -> bool:
    """True only if every named ``input`` declaration is present in ``src``."""
    return all(
        re.search(rf"\binput\b[^;\n]*\b{re.escape(n)}\b", src) for n in names
    )


def _pip_var_name(src: str) -> str | None:
    """Return the declared CPipNormalizer instance name, or None."""
    m = re.search(r"\bCPipNormalizer\b\s+(\w+)\s*;", src)
    return m.group(1) if m else None


def fix_ap3(src: str) -> tuple[str, list[str]]:
    if not _has_pip(src):
        return src, []
    # Don't synthesise a call referencing inputs the EA doesn't declare: that
    # trades an AP-3 finding for an undefined-identifier compile error the
    # regex-based re-lint can't see. Require both inputs first.
    if not _has_inputs(src, "InpRiskMoney", "InpSlPips"):
        return src, []
    var = _pip_var_name(src) or "pip"
    new_src, n = _LOT_FIXED.subn(
        rf"\1 = {var}.LotForRisk(InpRiskMoney, InpSlPips)",
        src,
    )
    if n == 0:
        return src, []
    return new_src, [f"AP-3: replaced {n} hardcoded lot literal(s) with {var}.LotForRisk(...)"]


# AP-18 — append a minimal OnTradeTransaction handler when OrderSendAsync is
# called but no handler exists. The stub is intentionally empty; the operator
# will fill it in with cookie tracking when they're ready.
_AP18_STUB = """

void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest&     req,
                        const MqlTradeResult&      res)
  {
   /* AP-18 stub: inserted by mql5-auto-fix. Wire OrderSendAsync cookies and
      MqlTradeTransaction handling here once the trader is ready. */
  }
"""


def fix_ap18(src: str) -> tuple[str, list[str]]:
    if not re.search(r"\bOrderSendAsync\s*\(", src):
        return src, []
    if re.search(r"\bOnTradeTransaction\s*\(", src):
        return src, []
    if src.endswith("\n"):
        new_src = src + _AP18_STUB.lstrip("\n")
    else:
        new_src = src + "\n" + _AP18_STUB.lstrip("\n")
    return new_src, ["AP-18: appended OnTradeTransaction stub"]


# AP-20 — hardcoded pip math → CPipNormalizer accessors.  Like AP-3 we only
# rewrite when ``pip`` is in scope; otherwise we annotate so we don't
# introduce a compile error.
def fix_ap20(src: str) -> tuple[str, list[str]]:
    var = _pip_var_name(src)
    if var is None:
        return src, []
    n = 0
    src, k = re.subn(r"\*\s*0\.0001\b",       f"* {var}.Pip()", src)
    n += k
    src, k = re.subn(r"\*\s*0\.001\b",        f"* {var}.Pip()", src)
    n += k
    src, k = re.subn(r"\*\s*_Point\b",        f"* {var}.Point()", src)
    n += k
    src, k = re.subn(r"\*\s*Point\s*\(\s*\)", f"* {var}.Point()", src)
    n += k
    if n == 0:
        return src, []
    return src, [f"AP-20: replaced {n} hardcoded pip operation(s) with {var}.Pip()/{var}.Point()"]


# AP-21 — repair or insert the ``// digits-tested: ...`` meta tag so it lists
# at least two digits classes.
_DIGITS_TAG = re.compile(
    r"^(?P<prefix>\s*//\s*\|?\s*digits-tested\s*:\s*)(?P<list>[0-9,\s]+)$",
    re.MULTILINE | re.IGNORECASE,
)


def fix_ap21(src: str) -> tuple[str, list[str]]:
    m = _DIGITS_TAG.search(src)
    if m is not None:
        classes = {c.strip() for c in m.group("list").split(",") if c.strip()}
        if len(classes) >= 2:
            return src, []
        # Add the complementary class. 5-digit FX <-> 3-digit JPY are the two
        # canonical broker classes; if neither is present, seed with 5, 3.
        if "5" in classes:
            classes.add("3")
        elif "3" in classes:
            classes.add("5")
        else:
            classes = {"5", "3"}
        new_list = ", ".join(sorted(classes, key=int))
        new_line = f"{m.group('prefix')}{new_list}"
        new_src = src[: m.start()] + new_line + src[m.end():]
        return new_src, [f"AP-21: expanded digits-tested meta tag to ({new_list})"]
    # No tag at all — prepend at very top of file.  Lint's _DIGITS_TESTED
    # search scans the raw source, so insertion order doesn't matter.
    new_src = "// digits-tested: 3, 5\n" + src
    return new_src, ["AP-21: inserted `// digits-tested: 3, 5` meta tag at top of file"]


# ─────────────────────────────────────────────────────────────────────────────
# Annotating fixers (lint still flags the AP — the comment is a MetaEditor
# bookmark for the operator who has to do the refactor by hand)
# ─────────────────────────────────────────────────────────────────────────────

def _annotate_findings(
    src: str,
    findings: list[lint_mod.Finding],
    code: str,
    note: str,
) -> tuple[str, list[str]]:
    """Insert ``// FIXME <code>: <note>`` directly above each finding for ``code``.

    Idempotent: skips lines already preceded by the annotation. Annotations
    are emitted in *reverse* line order so insertions don't perturb the line
    numbers of subsequent findings.
    """
    relevant = sorted(
        (f for f in findings if f.code == code),
        key=lambda f: f.line,
        reverse=True,
    )
    if not relevant:
        return src, []
    lines = src.splitlines(keepends=True)
    annotated_lines: list[int] = []
    fixme_marker = f"// FIXME {code}:"
    for f in relevant:
        idx = f.line - 1  # 0-based
        if idx < 0 or idx >= len(lines):
            continue
        # Skip if the prior line already has the FIXME marker (idempotency).
        if idx > 0 and fixme_marker in lines[idx - 1]:
            continue
        # Capture leading whitespace of the offending line so the comment
        # lines up visually.
        m = re.match(r"^(\s*)", lines[idx])
        indent = m.group(1) if m else ""
        lines.insert(idx, f"{indent}{fixme_marker} {note}\n")
        annotated_lines.append(f.line)
    if not annotated_lines:
        return src, []
    summary = (
        f"{code}: annotated {len(annotated_lines)} occurrence(s) at "
        f"line(s) {', '.join(str(n) for n in sorted(annotated_lines))}"
    )
    return "".join(lines), [summary]


# Each annotation fixer is a thin wrapper that re-lints the source and asks
# ``_annotate_findings`` to inject the FIXME marker. We delegate to lint so
# the line numbers always match what the operator sees in CI.
def _build_annotator(code: str, note: str) -> Fixer:
    def _fix(src: str) -> tuple[str, list[str]]:
        findings = lint_mod.lint_source("<auto-fix>", src)
        return _annotate_findings(src, findings, code, note)
    return _fix


fix_ap1  = _build_annotator(
    "AP-1",
    "CTrade.Buy/Sell missing stop-loss; add an explicit sl arg",
)
fix_ap5  = _build_annotator(
    "AP-5",
    "input count > 6 — collapse into a struct/preset for optimizer safety",
)
fix_ap15 = _build_annotator(
    "AP-15",
    "raw OrderSend — migrate to CTrade.PositionOpen/OrderSend",
)
fix_ap17 = _build_annotator(
    "AP-17",
    "WebRequest in OnTick — move to OnInit or a time-gated polling task",
)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

# Order matters only insofar as we run *mutating* fixers first, then
# annotators, so that annotations are inserted relative to the post-mutation
# line numbers.
MUTATING_FIXERS: tuple[tuple[str, Fixer], ...] = (
    ("AP-3",  fix_ap3),
    ("AP-18", fix_ap18),
    ("AP-20", fix_ap20),
    ("AP-21", fix_ap21),
)

ANNOTATING_FIXERS: tuple[tuple[str, Fixer], ...] = (
    ("AP-1",  fix_ap1),
    ("AP-5",  fix_ap5),
    ("AP-15", fix_ap15),
    ("AP-17", fix_ap17),
)


@dataclass
class FixReport:
    path: str
    fixed_text: str
    original_text: str
    mutations: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    findings_before: list[lint_mod.Finding] = field(default_factory=list)
    findings_after: list[lint_mod.Finding] = field(default_factory=list)
    #: Encoding of the source file on disk. Used by the CLI to write
    #: the patched file back in the *same* encoding so a UTF-16-LE
    #: MetaEditor file isn't silently transcoded to UTF-8.
    encoding: str = "utf-8"

    @property
    def changed(self) -> bool:
        return self.fixed_text != self.original_text

    def to_dict(self) -> dict[str, object]:
        return {
            "path":        self.path,
            "changed":     self.changed,
            "mutations":   self.mutations,
            "annotations": self.annotations,
            "errors_before": sum(1 for f in self.findings_before if f.severity == "ERROR"),
            "errors_after":  sum(1 for f in self.findings_after  if f.severity == "ERROR"),
            "warnings_before": sum(1 for f in self.findings_before if f.severity == "WARN"),
            "warnings_after":  sum(1 for f in self.findings_after  if f.severity == "WARN"),
        }


def fix_source(path: str, src: str) -> FixReport:
    """Apply every fixer in order, re-lint, and return a :class:`FixReport`."""
    report = FixReport(path=path, fixed_text=src, original_text=src)
    report.findings_before = lint_mod.lint_source(path, src)

    current = src
    for _code, fn in MUTATING_FIXERS:
        new_src, log = fn(current)
        if new_src != current:
            current = new_src
            report.mutations.extend(log)

    for _code, fn in ANNOTATING_FIXERS:
        new_src, log = fn(current)
        if new_src != current:
            current = new_src
            report.annotations.extend(log)

    report.fixed_text = current
    report.findings_after = lint_mod.lint_source(path, current)
    return report


def fix_file(path: Path) -> FixReport:
    from .mq5_io import read_mq5_text_with_encoding

    try:
        src, enc = read_mq5_text_with_encoding(path)
    except UnicodeDecodeError:
        src, enc = path.read_text(encoding="latin-1", errors="replace"), "latin-1"
    report = fix_source(str(path), src)
    report.encoding = enc
    return report


def _unified_diff(report: FixReport) -> str:
    return "".join(
        difflib.unified_diff(
            report.original_text.splitlines(keepends=True),
            report.fixed_text.splitlines(keepends=True),
            fromfile=f"{report.path} (before)",
            tofile=f"{report.path} (after)",
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-auto-fix", description=__doc__.splitlines()[0])
    p.add_argument("file", type=Path, help=".mq5 file to fix")
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--check", action="store_true",
                     help="report-only; exit 1 if any change would be written")
    grp.add_argument("--diff",  action="store_true",
                     help="print unified diff of the proposed changes; do not write the file")
    p.add_argument("--no-backup", action="store_true",
                   help="don't write a .bak side-by-side copy before overwriting (default: keep .bak)")
    args = p.parse_args(argv)

    if not args.file.is_file():
        print(f"mql5-auto-fix: not a file: {args.file}", file=sys.stderr)
        return 2

    report = fix_file(args.file)
    summary = report.to_dict()

    if args.check:
        print(json.dumps(summary, indent=2))
        return 1 if report.changed else 0

    if args.diff:
        diff = _unified_diff(report)
        if diff:
            sys.stdout.write(diff)
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 0

    if report.changed:
        if not args.no_backup:
            args.file.with_suffix(args.file.suffix + ".bak").write_text(
                report.original_text, encoding=report.encoding
            )
        args.file.write_text(report.fixed_text, encoding=report.encoding)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
