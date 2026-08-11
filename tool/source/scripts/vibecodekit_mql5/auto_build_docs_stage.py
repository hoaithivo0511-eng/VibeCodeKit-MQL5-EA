"""Compatibility entry point for on-demand EA documentation rendering.

This restores the public ``docs.ea_render`` MCP contract after the original
pipeline module was split.  It renders HTML and Markdown from a validated
``EaSpec`` and reports PDF unavailability without turning it into a fake PASS.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

from . import ea_docs_render
from .ea_docs import BuildMeta
from .ea_docs_inputs import InputDecl, parse_inputs
from .ea_docs_render import DocContent, LayerSpec, ParamRow, TakeNote, TimelineStep
from .ea_docs_semantics import (
    enrich_param_rows,
    load_flow_narrative,
    substitute_placeholders,
)
from .spec_schema import EaSpec

_FORMATS = frozenset({"html", "md", "pdf"})


def _content(ea: EaSpec, mq5_text: str, lang: str, meta: BuildMeta) -> DocContent:
    decls = parse_inputs(mq5_text)
    params = tuple(
        ParamRow(
            group=item.group,
            name=item.name,
            type=item.type,
            default=item.default,
            note=item.tooltip,
        )
        for item in decls
    )
    signals = tuple(
        TimelineStep(label=item.kind, caption=str(item.params), icon="chevron")
        for item in ea.signals
    )
    flow = load_flow_narrative(ea.preset, ea.stack, lang=lang) or ""
    if flow:
        flow = substitute_placeholders(flow, ea)
    return DocContent(
        title_main=ea.name,
        title_en=f"{ea.symbol} · {ea.timeframe} · {ea.preset}/{ea.stack}",
        frontmatter={
            "ea_version": meta.ea_version,
            "kit_version": meta.kit_version,
            "built_from": meta.built_from,
            "built_at_utc": meta.built_at_utc,
        },
        overview_layers=(
            LayerSpec("Strategy", ea.preset, "cyan", "robot"),
            LayerSpec("Risk", f"mode={ea.mode}", "yellow", "gear"),
            LayerSpec("Execution", ea.stack, "pink", "code"),
        ),
        strategy_timeline=signals,
        params=params,
        enriched_params=tuple(enrich_param_rows(decls, semantics={})),
        flow_narrative=flow,
        notes=(
            TakeNote(
                "Release evidence",
                "Generated documentation is not native compile or Strategy Tester evidence.",
                "warn",
            ),
        ),
        lang=lang,
    )


def _markdown(ea: EaSpec, decls: Iterable[InputDecl], meta: BuildMeta, lang: str) -> str:
    title = "Hướng dẫn vận hành" if lang == "vi" else "Operator guide"
    lines = [
        f"# {ea.name} — {title}",
        "",
        f"- EA version: `{meta.ea_version}`",
        f"- Kit version: `{meta.kit_version}`",
        f"- Symbol/timeframe: `{ea.symbol}` / `{ea.timeframe}`",
        f"- Preset/stack: `{ea.preset}` / `{ea.stack}`",
        f"- Build source: `{meta.built_from}`",
        "",
        "## Inputs",
        "",
        "| Group | Name | Type | Default | Note |",
        "|---|---|---|---|---|",
    ]
    for item in decls:
        values = (item.group, item.name, item.type, item.default, item.tooltip)
        escaped = [str(value).replace("|", "\\|") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    lines.extend(
        [
            "",
            "> Generated documentation is not native compile or Strategy Tester evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _render_pdf(html_path: Path, pdf_path: Path) -> str | None:
    chrome = _chrome()
    if chrome is None:
        return "headless Chrome/Chromium is not installed"
    proc = subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ],
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if proc.returncode or not pdf_path.is_file():
        detail = (proc.stderr or proc.stdout).strip()
        return f"headless Chrome PDF export failed ({proc.returncode}): {detail[-500:]}"
    return None


def write_docs_to_disk(
    ea: EaSpec,
    mq5_text: str,
    out_dir: Path,
    *,
    lang: str = "vi",
    formats: tuple[str, ...] = ("html", "md"),
    build_meta: BuildMeta,
) -> dict[str, object]:
    """Render requested formats and return the stable MCP result envelope."""

    if lang not in {"vi", "en"}:
        return {"ok": False, "error": f"unsupported language: {lang}"}
    requested = tuple(dict.fromkeys(formats or ("html", "md")))
    unknown = sorted(set(requested) - _FORMATS)
    if unknown:
        return {"ok": False, "error": f"unsupported formats: {unknown}"}

    out_dir.mkdir(parents=True, exist_ok=True)
    decls = parse_inputs(mq5_text)
    content = _content(ea, mq5_text, lang, build_meta)
    html = ea_docs_render.render_html_document(content)
    outputs: dict[str, str] = {}
    html_path = out_dir / f"{ea.name}.docs.html"
    temporary_html = "html" not in requested and "pdf" in requested
    if "html" in requested or temporary_html:
        html_path.write_text(html, encoding="utf-8", newline="\n")
        if "html" in requested:
            outputs["html"] = str(html_path.resolve())
    if "md" in requested:
        md_path = out_dir / f"{ea.name}.docs.md"
        md_path.write_text(
            _markdown(ea, decls, build_meta, lang), encoding="utf-8", newline="\n"
        )
        outputs["md"] = str(md_path.resolve())

    pdf_error: str | None = None
    if "pdf" in requested:
        pdf_path = out_dir / f"{ea.name}.docs.pdf"
        pdf_error = _render_pdf(html_path, pdf_path)
        if pdf_error is None:
            outputs["pdf"] = str(pdf_path.resolve())
    if temporary_html:
        html_path.unlink(missing_ok=True)

    return {
        "ok": True,
        "lang": lang,
        "formats": list(requested),
        "outputs": outputs,
        "pdf_error": pdf_error,
    }
