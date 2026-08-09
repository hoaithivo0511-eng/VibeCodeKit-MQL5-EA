"""mql5-docs-assemble — convert an LLM-authored ``guide.md`` to ``.docx``.

Second half of the LLM-driven user-guide ship pipeline (see
:mod:`docs_bundle` for the first half). Takes a Vietnamese markdown
file the LLM agent wrote against ``docs-context.json`` and renders it
to a Word document suitable for inclusion in the ship.zip.

What's supported (the markdown subset the bundle prompt asks for):

* Headings (``#`` … ``####``) — mapped to Word ``Heading 1`` …
  ``Heading 4``.
* Paragraphs with inline bold (``**``), italic (``*``), code spans
  (`````) and links (``[text](url)``). Links keep their URL inline so a
  printed copy is still useful.
* Bullet and ordered lists (single level — the LLM prompt asks for flat
  outlines).
* Fenced code blocks (```` ``` ````) — rendered in Consolas 9pt.
* Markdown tables — emitted as Word tables with a bold header row.
* Blockquote callouts (``> **Lưu ý**: ...``) — emitted as italic
  paragraphs.
* Images (``![alt](images/...)``) — embedded from the configured
  ``images_dir``; missing files surface as warnings rather than errors.
* ``[[TOC]]`` marker → Word ToC field that updates with ``F9``.

What we deliberately don't try to support: HTML passthrough, nested
lists, footnotes, definition lists. The LLM prompt steers away from
those.

This module is **archetype-agnostic** — it never injects per-EA chapter
content. All variation comes from the markdown the LLM authored.

The low-level token-→-docx rendering helpers live in
:mod:`docs_assemble_render` to keep this module under the audit
script's per-module LOC ceiling.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from docx import Document
try:  # keep catalog/import diagnostics usable when optional docs deps are absent
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover - installation dependent
    MarkdownIt = None  # type: ignore[assignment,misc]

from . import docs_assemble_render as render


__all__ = [
    "AssembleResult",
    "assemble",
    "build_document",
    "validate_guide_md",
    "main",
]


_TOC_MARKER = render.TOC_MARKER
_MIN_CHAPTERS = 5
_MAX_CHAPTERS = 12


@dataclass
class AssembleResult:
    """Summary of a markdown → docx run."""

    ok: bool
    docx_path: str
    chapters: int = 0
    tables: int = 0
    images_embedded: int = 0
    warnings: list[str] = field(default_factory=list)


def _iter_outside_code_fences(lines: list[str]) -> list[str]:
    """Yield the subset of ``lines`` that sit outside ``\\`\\`\\```-fenced blocks.

    Toggle on any line that opens or closes a code fence (``\\`\\`\\``` /
    ``\\`\\`\\`bash``). Indented fences (``    \\`\\`\\```) are honoured too —
    `lstrip` keeps the detection symmetric with markdown-it.
    """
    visible: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            visible.append(line)
    return visible


def validate_guide_md(md_text: str) -> list[str]:
    """Lightweight structural checks on the LLM-authored markdown.

    Returns a list of human-readable issues (Vietnamese). An empty list
    means the markdown clears the structural bar set by ``docs-prompt.md``.
    Callers may treat any issue as a soft warning — :func:`assemble`
    still renders a docx so a reviewer can eyeball the result and fix.

    H1 and ``[[TOC]]`` detection runs against the lines *outside* fenced
    code blocks so a shell snippet like ``# rebuild`` inside ``\\`\\`\\``` is
    not counted as a chapter heading.
    """
    issues: list[str] = []
    lines = md_text.strip().splitlines() if md_text else []
    if not lines or not lines[0].startswith("# "):
        issues.append("H1 phải là dòng đầu tiên của guide.md")
    visible_lines = _iter_outside_code_fences(lines)
    visible_text = "\n".join(visible_lines)
    if _TOC_MARKER not in visible_text:
        issues.append(f"Thiếu marker {_TOC_MARKER} (Word ToC field)")
    h1_count = sum(1 for line in visible_lines if line.startswith("# "))
    chapter_count = max(h1_count - 1, 0)  # exclude the title H1
    if chapter_count < _MIN_CHAPTERS:
        issues.append(
            f"Quá ít chương: đếm được {chapter_count}, tối thiểu {_MIN_CHAPTERS}"
        )
    if chapter_count > _MAX_CHAPTERS:
        issues.append(
            f"Quá nhiều chương: đếm được {chapter_count}, tối đa {_MAX_CHAPTERS}"
        )
    return issues


def _resolve_image_path(images_dir: Path, src: str) -> Path:
    """Resolve a markdown image src against ``images_dir``.

    Accepts either an absolute path, a path relative to ``images_dir``,
    or a path with a leading ``images/`` so callers can pass either the
    root or the parent and have both shapes resolve cleanly.
    """
    image_path = images_dir / src if not Path(src).is_absolute() else Path(src)
    if not image_path.is_file() and src.startswith("images/"):
        image_path = images_dir.parent / src
    return image_path


def build_document(
    md_text: str,
    images_dir: Path,
) -> tuple[Document, AssembleResult]:
    """Render ``md_text`` into a fresh :class:`docx.Document`.

    Pure: takes markdown + an image-resolution root, returns the docx
    object plus a structural summary. The caller is responsible for
    persistence — see :func:`assemble`.
    """
    if MarkdownIt is None:
        raise RuntimeError("markdown-it-py is required for mql5-docs-assemble; install project dependencies")
    md = MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")
    tokens = md.parse(md_text)

    doc = Document()
    render.apply_default_style(doc)
    result = AssembleResult(ok=True, docx_path="")
    h1_total = 0

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        ttype = tok.type
        if ttype == "heading_open":
            level = int(tok.tag[1])  # "h1" → 1
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            text = inline.content if inline else ""
            render.heading_from_token(doc, level, text)
            if level == 1:
                h1_total += 1
            i += 3
            continue
        if ttype == "paragraph_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if inline and render.is_toc_marker_paragraph(inline):
                render.insert_toc_field(doc)
                i += 3
                continue
            if inline and render.is_image_only_paragraph(inline):
                src = render.extract_image_src(inline)
                if src:
                    render.embed_image(doc, _resolve_image_path(images_dir, src), result)
                i += 3
                continue
            paragraph = doc.add_paragraph()
            if inline:
                render.add_inline_runs(paragraph, inline.children or [])
            i += 3
            continue
        if ttype == "bullet_list_open":
            i = render.add_list_items(doc, tokens, i, ordered=False)
            continue
        if ttype == "ordered_list_open":
            i = render.add_list_items(doc, tokens, i, ordered=True)
            continue
        if ttype == "fence" or ttype == "code_block":
            render.add_code_block(doc, tok.content or "")
            i += 1
            continue
        if ttype == "table_open":
            i = render.add_table(doc, tokens, i, result)
            continue
        if ttype == "blockquote_open":
            body: list[Any] = []
            j = i + 1
            depth = 1
            while j < len(tokens) and depth > 0:
                if tokens[j].type == "blockquote_open":
                    depth += 1
                elif tokens[j].type == "blockquote_close":
                    depth -= 1
                    if depth == 0:
                        break
                else:
                    body.append(tokens[j])
                j += 1
            render.add_callout(doc, body)
            i = j + 1
            continue
        if ttype == "hr":
            doc.add_paragraph("─" * 40)
            i += 1
            continue
        i += 1

    # The first H1 is the doc title (EA name + version per the prompt
    # checklist); subsequent H1s are chapters. Floor at zero so a guide
    # with only a title still surfaces a sensible chapter count.
    result.chapters = max(h1_total - 1, 0)
    return doc, result


def assemble(
    guide_md_path: Path,
    out_path: Path,
    images_dir: Path | None = None,
) -> AssembleResult:
    """Render ``guide_md_path`` to ``out_path`` (Word ``.docx``).

    ``images_dir`` defaults to ``<guide.parent>/images``. Validation
    issues from :func:`validate_guide_md` land in ``result.warnings``
    but do not fail the run — the caller can inspect the warnings and
    decide whether to re-prompt the LLM.
    """
    md_text = guide_md_path.read_text(encoding="utf-8")
    issues = validate_guide_md(md_text)
    if images_dir is None:
        images_dir = guide_md_path.parent / "images"
    doc, result = build_document(md_text, images_dir)
    result.warnings.extend(issues)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    result.docx_path = str(out_path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mql5-docs-assemble",
        description=(
            "Convert an LLM-authored guide.md into a .docx Word document "
            "for the EA ship bundle."
        ),
    )
    parser.add_argument("guide", type=Path, help="LLM-authored guide.md path")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="output .docx path",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=None,
        help="root directory for `![alt](images/...)` references "
        "(default: <guide-parent>/images)",
    )
    args = parser.parse_args(argv)

    if not args.guide.is_file():
        print(f"mql5-docs-assemble: guide.md not found: {args.guide}", file=sys.stderr)
        return 2

    try:
        result = assemble(args.guide, args.out, images_dir=args.images_dir)
    except OSError as exc:
        print(f"mql5-docs-assemble: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
