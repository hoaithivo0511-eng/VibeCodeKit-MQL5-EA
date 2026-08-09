"""mql5-docs-bundle — emit a deterministic LLM context + prompt pair.

This command is the *first* half of the LLM-driven `.docx` user-guide
ship pipeline (Pattern A — kit-light). It writes two artefacts into the
caller's output directory:

* ``docs-context.json`` — structured snapshot of everything the kit
  already knows about the EA: spec, scaffold archetype, parsed inputs
  (with semantic library enrichment), include headers used, and build
  metrics (if a prior ``auto-build-report.json`` is around). Runtime
  flow is intentionally NOT pre-templated — the LLM reconstructs it
  from the parsed inputs + includes + source structure.
* ``docs-prompt.md`` — language-agnostic instructions for an external
  LLM agent (Devin / Claude / Cursor) to author a ``guide.md`` markdown
  document. The prompt is static; per-EA variation is carried entirely
  by ``docs-context.json``.

The downstream ``mql5-docs-assemble`` command then converts the
LLM-authored ``guide.md`` into a Word ``.docx`` deliverable that ships
with the EA bundle (``mql5-package``).

Design notes (per the kit spec §3 / AGENTS.md "What you must NOT
introduce"): this module is intentionally archetype-agnostic. It never
hardcodes per-archetype chapter content — the structure of the guide is
authored adaptively by the LLM based on the context payload (see
``REFERENCE_OUTLINE`` for a non-prescriptive default). No model is
invoked from this module.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ea_docs_inputs import parse_inputs
from .ea_docs_semantics import load_input_semantics


__all__ = [
    "BundleResult",
    "REFERENCE_OUTLINE",
    "PROMPT_TEMPLATE",
    "build_context",
    "build_prompt",
    "write_bundle",
    "main",
]


# Repo-rooted default so callers don't have to plumb paths. Tests can
# override via the ``repo_root`` kwarg.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


REFERENCE_OUTLINE: tuple[str, ...] = (
    "Chương 1 — Tổng quan",
    "Chương 2 — Indicator math",
    "Chương 3 — Trigger engine",
    "Chương 4 — Special mechanic (nếu có)",
    "Chương 5 — Risk filters",
    "Chương 6 — Flow diagram",
    "Chương 7 — Install guide",
    "Chương 8 — Param tables",
    "Chương 9 — Backtest workflow",
    "Chương 10 — Risk warnings",
)


PROMPT_TEMPLATE = """\
# Nhiệm vụ: Viết hướng dẫn sử dụng EA cho end-user

## Input
- File `docs-context.json` (cùng thư mục): toàn bộ dữ liệu deterministic về EA

## Output yêu cầu
- Ghi file `guide.md` (markdown tiếng Việt) vào cùng thư mục
- Optional: PNG charts trong `images/` reference qua `![alt](images/xxx.png)`

## Quy tắc cấu trúc — ADAPTIVE theo logic EA
Cấu trúc CHƯƠNG do LLM **quyết định adaptive** theo nội dung context. Cấu
trúc tham chiếu ở `docs-context.json#reference_doc_structure.outline`
chỉ để tham khảo — KHÔNG copy nguyên xi. Cân nhắc:

- **EA scalping intrabar**: cần chương về tick handling, async mode
- **EA trend-following**: chú trọng filter trend, trailing
- **EA DCA/grid**: chương riêng cơ chế DCA + risk warnings dày
- **EA news-trading**: chương news filter timing
- **EA ML/ONNX**: chương model inference + tester validation
- **EA portfolio-basket multi-symbol**: chương correlation matrix
- **EA library/indicator-only**: cấu trúc gọn hơn (5-6 chương đủ)

## Quy tắc nội dung
1. Mọi giá trị input/threshold/timeframe trace về `context.spec` +
   `context.inputs` — KHÔNG hallucinate.
2. Per-input cards: ý nghĩa (vi), đơn vị, công thức (nếu có), dải hợp lý,
   lưu ý/gotcha. Lấy từ `context.inputs[].semantics` khi có.
3. FLOW: tự dựng từ `context.inputs` + `context.scaffold.includes_used`
   + cấu trúc OnInit/OnTick/OnDeinit của EA — KHÔNG dùng template flow
   cố định theo archetype.
4. Install guide bắt buộc có (mặc dù EA loại gì): drag-attach MT5,
   AutoTrading ON, log expectation.
5. Backtest workflow bắt buộc có nếu EA có `OnTick` (skip cho
   indicator-only/library).
6. Risk warnings adaptive: đọc `lint_findings` + archetype → nêu rủi ro
   tương ứng.

## Format markdown bắt buộc
- H1 (`# Chương N — ...`) = chương
- H2 (`## N.M ...`) = mục con
- H3 (`### Title`) = sub-mục
- Bảng markdown chuẩn (sẽ convert sang Word table tự động)
- `![alt](images/name.png)` cho ảnh (embed vào docx ở bước assemble)
- `> **Lưu ý**: ...` callout (giữ trong docx)
- `[[TOC]]` ngay sau title H1 đầu tiên (sẽ render thành Word ToC field)

## Self-check trước khi finalize
- [ ] Mọi giá trị numeric khớp `context.spec` + `context.inputs`
- [ ] Tiếng Việt có dấu đầy đủ
- [ ] H1 đầu file là tên EA + version
- [ ] Có `[[TOC]]` ngay sau H1 đầu
- [ ] Tối thiểu 5 chương, không quá 12 chương
- [ ] Không tham chiếu file/path ngoài `docs-context.json`
"""


@dataclass
class BundleResult:
    """Summary of a ``write_bundle`` call, suitable for ``json.dumps``."""

    ok: bool
    context_path: str
    prompt_path: str
    inputs_total: int
    inputs_enriched: int
    notes: list[str] = field(default_factory=list)


def _detect_includes(mq5_text: str) -> list[str]:
    """Surface the ``#include "X.mqh"`` headers a scaffold pulls in.

    Returns a deduplicated, sorted list of class-name guesses
    (``CPipNormalizer``, ``CRiskGuard`` ...) — strip leading paths and
    the ``.mqh`` suffix so the JSON payload reads as kit-helper names
    rather than filesystem paths.
    """
    if not mq5_text:
        return []
    hits = re.findall(r'#include\s+"([^"]+\.mqh)"', mq5_text)
    return sorted({h.replace(".mqh", "").split("/")[-1] for h in hits})


def _read_build_report(report_path: Path) -> dict[str, Any]:
    """Pluck the few numbers we want from a previous ``auto-build-report.json``.

    Returns an all-``None`` skeleton when the report file is missing or
    unreadable so the JSON shape stays stable for the LLM consumer.
    """
    skeleton: dict[str, Any] = {
        "compile_ok": None,
        "errors": None,
        "warnings": None,
        "anti_patterns_passed": None,
        "anti_patterns_failed": None,
    }
    if not report_path.is_file():
        return skeleton
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return skeleton
    if not isinstance(data, dict):
        return skeleton
    stages = data.get("stages") or []
    compile_stage = next((s for s in stages if isinstance(s, dict) and s.get("name") == "compile"), {})
    lint_stage = next((s for s in stages if isinstance(s, dict) and s.get("name") == "lint"), {})
    skeleton["compile_ok"] = compile_stage.get("ok")
    errors = compile_stage.get("errors")
    warnings = compile_stage.get("warnings")
    if isinstance(errors, list):
        skeleton["errors"] = len(errors)
    elif isinstance(errors, int):
        skeleton["errors"] = errors
    if isinstance(warnings, list):
        skeleton["warnings"] = len(warnings)
    elif isinstance(warnings, int):
        skeleton["warnings"] = warnings
    findings = lint_stage.get("findings")
    if isinstance(findings, list):
        passed = sum(1 for f in findings if isinstance(f, dict) and f.get("ok"))
        failed = sum(1 for f in findings if isinstance(f, dict) and not f.get("ok"))
        skeleton["anti_patterns_passed"] = passed
        skeleton["anti_patterns_failed"] = failed
    return skeleton


def _read_lint_findings(report_path: Path) -> list[dict[str, Any]]:
    """Extract lint findings from a prior ``auto-build-report.json`` if any."""
    if not report_path.is_file():
        return []
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    stages = (isinstance(data, dict) and data.get("stages")) or []
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("name") != "lint":
            continue
        findings = stage.get("findings") or []
        out: list[dict[str, Any]] = []
        for f in findings:
            if not isinstance(f, dict):
                continue
            out.append(
                {
                    "code": f.get("code"),
                    "severity": f.get("severity"),
                    "line": f.get("line"),
                    "msg": f.get("message") or f.get("msg"),
                }
            )
        return out
    return []


def build_context(
    spec_path: Path,
    mq5_path: Path,
    *,
    repo_root: Path | None = None,
    semantics_path: Path | None = None,
    build_report_path: Path | None = None,
) -> dict[str, Any]:
    """Assemble the JSON-serialisable context payload for the LLM.

    Pure function: reads spec + mq5 + (optional) build report + (always)
    the input-semantics library, but never writes to disk. ``main`` and
    :func:`write_bundle` handle persistence.

    The spec is consumed in its raw dict form (the same shape as
    ``mql5-auto-build --spec`` accepts) — top-level fields like
    ``name`` / ``preset`` / ``stack`` / ``symbol`` / ``timeframe`` are
    re-projected into a nested ``ea`` / ``market`` shape that maps
    cleanly onto end-user guide vocabulary without exposing the kit's
    internal schema choices.
    """
    if repo_root is None:
        repo_root = _REPO_ROOT

    # Load spec as raw dict — matches what `mql5-auto-build` loads.
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover — pyyaml is a core dep
        raise RuntimeError("PyYAML required to read spec") from exc
    spec_raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    if not isinstance(spec_raw, dict):
        raise ValueError(
            f"spec must be a mapping, got {type(spec_raw).__name__}"
        )

    from .mq5_io import read_mq5_text

    mq5_text = read_mq5_text(mq5_path, errors="replace") if mq5_path.is_file() else ""
    decls = parse_inputs(mq5_text)
    semantics = load_input_semantics(semantics_path) if semantics_path else load_input_semantics()

    enriched_inputs: list[dict[str, Any]] = []
    for decl in decls:
        sem = semantics.get(decl.name)
        sem_payload: dict[str, Any] | None
        if sem is not None:
            sem_payload = {
                "meaning_vi": sem.meaning,
                "unit": sem.unit,
                "formula_vi": sem.formula,
                "depends_on": list(sem.depends_on),
                "used_by": sem.used_by,
                "sensible_range_vi": sem.sensible_range,
                "gotchas_vi": sem.gotchas,
            }
        else:
            sem_payload = None
        enriched_inputs.append(
            {
                "name": decl.name,
                "type": decl.type,
                "default": decl.default,
                "tooltip": decl.tooltip,
                "group": decl.group,
                "line_number": decl.line_number,
                "semantics": sem_payload,
            }
        )

    preset = str(spec_raw.get("preset", "stdlib"))
    stack = str(spec_raw.get("stack", "netting"))

    if build_report_path is None:
        build_report_path = mq5_path.parent / "auto-build-report.json"
    build_metrics = _read_build_report(build_report_path)
    lint_findings = _read_lint_findings(build_report_path)

    try:
        source_path = (
            str(mq5_path.relative_to(repo_root)) if mq5_path.is_absolute() else str(mq5_path)
        )
    except ValueError:
        source_path = str(mq5_path)

    return {
        "ea": {
            "name": spec_raw.get("name"),
            "version": str(spec_raw.get("version", "1.0.0")),
            "source_path": source_path,
            "build_timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        },
        "market": {
            "symbol": spec_raw.get("symbol"),
            "timeframe": spec_raw.get("timeframe"),
        },
        "account": {
            "mode": spec_raw.get("mode", "personal"),
            "type": stack,
        },
        "spec": spec_raw,
        "scaffold": {
            "preset": preset,
            "stack": stack,
            "archetype_label": f"{preset}/{stack}",
            "includes_used": _detect_includes(mq5_text),
        },
        "inputs": enriched_inputs,
        "lint_findings": lint_findings,
        "build_metrics": build_metrics,
        "reference_doc_structure": {
            "note_vi": (
                "Đây là cấu trúc tham chiếu (10 chương mặc định). LLM tham "
                "khảo nhưng cần adapt theo EA-specific logic — xem "
                "instructions trong docs-prompt.md."
            ),
            "outline": list(REFERENCE_OUTLINE),
        },
    }


def build_prompt(context: dict[str, Any] | None = None) -> str:
    """Return the LLM prompt body.

    The prompt is intentionally context-independent (per-EA variation
    lives in ``docs-context.json``). ``context`` is accepted for forward
    compatibility — callers may pass it and we ignore it.
    """
    del context
    return PROMPT_TEMPLATE


def write_bundle(
    spec_path: Path,
    mq5_path: Path,
    out_dir: Path,
    *,
    repo_root: Path | None = None,
    semantics_path: Path | None = None,
    build_report_path: Path | None = None,
) -> BundleResult:
    """Materialise ``docs-context.json`` + ``docs-prompt.md`` under ``out_dir``.

    Returns a :class:`BundleResult` summarising what was written and how
    many inputs the semantic library was able to enrich. The result is
    JSON-serialisable via ``dataclasses.asdict``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    context = build_context(
        spec_path,
        mq5_path,
        repo_root=repo_root,
        semantics_path=semantics_path,
        build_report_path=build_report_path,
    )
    prompt = build_prompt(context)

    context_path = out_dir / "docs-context.json"
    prompt_path = out_dir / "docs-prompt.md"
    context_path.write_text(
        json.dumps(context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    prompt_path.write_text(prompt, encoding="utf-8")

    inputs_total = len(context["inputs"])
    inputs_enriched = sum(1 for inp in context["inputs"] if inp.get("semantics"))
    notes: list[str] = []
    if inputs_total and inputs_enriched == 0:
        notes.append(
            "no inputs matched docs/input-semantics.yaml — per-input cards in"
            " guide.md will fall back to source-side tooltips only."
        )
    return BundleResult(
        ok=True,
        context_path=str(context_path),
        prompt_path=str(prompt_path),
        inputs_total=inputs_total,
        inputs_enriched=inputs_enriched,
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mql5-docs-bundle",
        description=(
            "Emit docs-context.json + docs-prompt.md for an external LLM "
            "agent to author guide.md (Pattern A — kit-light .docx ship)."
        ),
    )
    parser.add_argument("spec", type=Path, help="ea-spec.yaml path")
    parser.add_argument("mq5", type=Path, help="EA .mq5 source path")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="output directory (must be writable)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="override repo root for scaffold + semantics lookup",
    )
    parser.add_argument(
        "--build-report",
        type=Path,
        default=None,
        help=(
            "optional path to auto-build-report.json — when present, "
            "context.build_metrics + context.lint_findings are populated"
        ),
    )
    args = parser.parse_args(argv)

    if not args.spec.is_file():
        print(f"mql5-docs-bundle: spec not found: {args.spec}", file=sys.stderr)
        return 2
    if not args.mq5.is_file():
        print(f"mql5-docs-bundle: .mq5 not found: {args.mq5}", file=sys.stderr)
        return 2

    try:
        result = write_bundle(
            args.spec,
            args.mq5,
            args.out,
            repo_root=args.repo_root,
            build_report_path=args.build_report,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"mql5-docs-bundle: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
