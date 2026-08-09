"""Neo-Retro Dev Deck renderer for EA docs.

Pure-function renderer that turns docstring-style content into a
self-contained ``<EAName>.docs.html`` matching the design system
described in ``ea_docs_assets/style.css``.

Pipeline:

* ``render_html_document(content)`` builds a complete HTML page with CSS
  + pixel-art SVGs inlined — zero external assets, opens in any browser.
* PR-17 then feeds this HTML into headless Chromium via
  ``Page.printToPDF`` to produce the final ``<EAName>.docs.pdf``.
* A parallel Markdown renderer (PR-16) emits ``<EAName>.docs.md`` for
  git diff / agent consumption.

This module is intentionally split into small ``render_*`` component
functions so each can be unit-tested in isolation.

Wire format is stable across PR-15 → PR-18 — only the templates evolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Sequence

__all__ = [
    "DocContent",
    "LayerSpec",
    "TimelineStep",
    "ParamRow",
    "TakeNote",
    "load_asset",
    "load_icon",
    "render_frontmatter",
    "render_section_header",
    "render_manifesto",
    "render_layer_stack",
    "render_timeline",
    "render_param_table",
    "render_param_deep_dive",
    "render_flow_narrative",
    "render_take_note",
    "render_html_document",
]

ASSETS_DIR = Path(__file__).parent / "ea_docs_assets"
ICONS_DIR = ASSETS_DIR / "icons"
CSS_PATH = ASSETS_DIR / "style.css"

ICON_NAMES = (
    "rocket", "gear", "robot", "code", "browser", "chat", "chevron", "spark",
)

# ────────────────────────────────────────────────────────────────────────────
# Localized labels for the static section headers and table column names.
#
# Project identifiers — ``input`` names like ``InpMagic``, class names
# like ``CRiskGuard``, MQL5 types like ``double`` — are NEVER translated:
# they live in the rendered code/data, not in this label map.
# ────────────────────────────────────────────────────────────────────────────

_SECTION_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "overview": "Kiến trúc hệ thống",
        "strategy": "Chu trình chiến lược",
        "params": "Tham số EA",
        "param_deep_dive": "Chi tiết từng tham số",
        "flow": "Cách EA chạy",
        "notes": "Lưu ý quan trọng",
    },
    "en": {
        "overview": "System Architecture",
        "strategy": "Strategy Evolution",
        "params": "EA Inputs",
        "param_deep_dive": "Per-Input Deep Dive",
        "flow": "How the EA Runs",
        "notes": "Take Notes",
    },
}

_TABLE_HEADERS: dict[str, tuple[str, str, str, str, str]] = {
    "vi": ("Nhóm", "Tên", "Kiểu", "Mặc định", "Ghi chú"),
    "en": ("Group", "Name", "Type", "Default", "Note"),
}


def section_labels(lang: str) -> dict[str, str]:
    """Return the localized section-header labels (``overview``,
    ``strategy``, ``params``, ``notes``). Unknown languages fall back
    to Vietnamese, the project default."""
    return _SECTION_LABELS.get(lang) or _SECTION_LABELS["vi"]


def table_headers(lang: str) -> tuple[str, str, str, str, str]:
    """Return the localized 5-tuple of ``param-table`` column headers.

    Order: ``(group, name, type, default, note)``.
    Unknown languages fall back to Vietnamese."""
    return _TABLE_HEADERS.get(lang) or _TABLE_HEADERS["vi"]


# ────────────────────────────────────────────────────────────────────────────
# Data model — minimal, all pure-Python so callers can build content fixtures
# without touching the kit's full ``EaSpec``.
# ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LayerSpec:
    """One layer in a ``layer-stack`` architecture diagram."""

    title: str
    caption: str
    color: str = "cyan"  # pink | yellow | cyan | black
    icon: str = "gear"   # name from ICON_NAMES


@dataclass(frozen=True)
class TimelineStep:
    """One step in an evolution timeline."""

    label: str
    caption: str = ""
    icon: str = "chevron"
    highlight: bool = False


@dataclass(frozen=True)
class ParamRow:
    """One row of the ``param-table`` (an ``input`` declaration in .mq5)."""

    group: str
    name: str
    type: str
    default: str
    note: str = ""


@dataclass(frozen=True)
class TakeNote:
    """One annotated callout in §5 of the docs."""

    title: str
    body: str
    severity: str = "info"  # info | warn | danger
    icon: str = "spark"


@dataclass
class DocContent:
    """Full document model — what the renderer turns into HTML."""

    title_main: str  # main bold claim (e.g. "PORTFOLIO MEAN-REVERSION")
    title_jp: str = ""  # optional second-line accent (matches reference deck)
    title_en: str = ""  # optional small sub-label
    frontmatter: dict[str, str] = field(default_factory=dict)
    overview_layers: Sequence[LayerSpec] = ()
    strategy_timeline: Sequence[TimelineStep] = ()
    params: Sequence[ParamRow] = ()
    # v2.x enrichments. Both default to empty so existing callers and
    # archetypes without a FLOW-vi.md / matching semantics keep rendering
    # exactly as before.
    enriched_params: Sequence[object] = ()  # EnrichedParamRow from ea_docs_semantics
    flow_narrative: str = ""  # plain markdown narrative, already placeholder-substituted
    notes: Sequence[TakeNote] = ()
    closing_html: str = ""  # optional free-form HTML at the end
    lang: str = "vi"  # locale for section headers + table headers


# ────────────────────────────────────────────────────────────────────────────
# Asset loading
# ────────────────────────────────────────────────────────────────────────────


def load_asset(relative_path: str) -> str:
    """Read a packaged asset under ``ea_docs_assets/`` as UTF-8 text."""
    target = (ASSETS_DIR / relative_path).resolve()
    if ASSETS_DIR.resolve() not in target.parents and target != ASSETS_DIR.resolve():
        raise ValueError(f"asset path escapes ea_docs_assets: {relative_path}")
    return target.read_text(encoding="utf-8")


def load_icon(name: str) -> str:
    """Load a pixel-art SVG by short name (e.g. ``rocket``).

    Returns raw ``<svg>...</svg>`` markup ready to inline.
    Unknown names fall back to the ``spark`` icon (never crashes).
    """
    if name not in ICON_NAMES:
        name = "spark"
    return load_asset(f"icons/{name}.svg")


# ────────────────────────────────────────────────────────────────────────────
# Component renderers
# ────────────────────────────────────────────────────────────────────────────


def render_frontmatter(values: dict[str, str]) -> str:
    """Render machine-readable ``key: value`` header block."""
    if not values:
        return ""
    lines = []
    for k, v in values.items():
        lines.append(
            f'<span class="key">{escape(str(k))}:</span> '
            f'<span class="value">{escape(str(v))}</span>'
        )
    body = "\n".join(lines)
    return f'<pre class="frontmatter">{body}</pre>'


def render_section_header(title: str, icon: str = "chevron") -> str:
    """Render a horizontal bar with title + pixel icon."""
    return (
        '<div class="section-header">'
        f'<span class="pixel-icon">{load_icon(icon)}</span>'
        f'<h2 class="h-section">{escape(title)}</h2>'
        '</div>'
    )


def render_manifesto(content: DocContent) -> str:
    """Render the hero / manifesto card (huge claim + decorative icons)."""
    # PR-18.3: dropped the legacy ``「 」`` CJK corner brackets — Chrome
    # headless (PDF export) has no font with the bracket glyphs and
    # rendered them as tofu squares. The HTML class name ``title-jp`` is
    # kept for CSS back-compat (it now just means "subtitle").
    title_jp = (
        f'<p class="title-jp">{escape(content.title_jp)}</p>'
        if content.title_jp else ""
    )
    title_en = (
        f'<p class="title-en">{escape(content.title_en)}</p>'
        if content.title_en else ""
    )
    deco_tl = f'<div class="deco tl">{load_icon("code")}</div>'
    deco_tr = f'<div class="deco tr">{load_icon("gear")}</div>'
    deco_br = f'<div class="deco br">{load_icon("rocket")}</div>'
    return (
        '<section class="manifesto">'
        f'{deco_tl}{deco_tr}{deco_br}'
        f'{title_jp}{title_en}'
        f'<h1 class="claim">{escape(content.title_main)}</h1>'
        '</section>'
    )


def render_layer_stack(layers: Sequence[LayerSpec]) -> str:
    """Render stacked architecture layers (one color block per layer)."""
    if not layers:
        return ""
    items = []
    for layer in layers:
        items.append(
            f'<div class="layer block {escape(layer.color)}">'
            f'<span class="pixel-icon lg">{load_icon(layer.icon)}</span>'
            f'<div class="label">'
            f'<h3 class="h-card">{escape(layer.title)}</h3>'
            f'<p class="t-caption">{escape(layer.caption)}</p>'
            f'</div>'
            f'</div>'
        )
    return f'<div class="layer-stack">{"".join(items)}</div>'


def render_timeline(steps: Sequence[TimelineStep]) -> str:
    """Render left → right progression of steps with arrow accents."""
    if not steps:
        return ""
    items: list[str] = []
    for i, step in enumerate(steps):
        cls = "step highlight" if step.highlight else "step"
        items.append(
            f'<div class="{cls}">'
            f'<span class="pixel-icon">{load_icon(step.icon)}</span>'
            f'<h3 class="h-card">{escape(step.label)}</h3>'
            f'<p class="t-caption">{escape(step.caption)}</p>'
            f'</div>'
        )
        if i != len(steps) - 1:
            items.append(f'<span class="arrow">{load_icon("chevron")}</span>')
    return f'<div class="timeline">{"".join(items)}</div>'


def render_param_table(
    rows: Sequence[ParamRow],
    lang: str = "vi",
) -> str:
    """Render the EA's ``input`` declarations as a styled table.

    Column headers are localized; ``input`` names, MQL5 types and
    default values are project-level identifiers and are rendered
    verbatim regardless of ``lang``."""
    if not rows:
        return ""
    _group, name, type_, default, note = table_headers(lang)
    head = (
        '<thead><tr>'
        f'<th>{escape(name)}</th>'
        f'<th>{escape(type_)}</th>'
        f'<th>{escape(default)}</th>'
        f'<th>{escape(note)}</th>'
        '</tr></thead>'
    )
    body_rows: list[str] = []
    last_group: str | None = None
    for row in rows:
        if row.group and row.group != last_group:
            body_rows.append(
                f'<tr class="group-row"><td colspan="4">'
                f'{escape(row.group)}'
                '</td></tr>'
            )
            last_group = row.group
        body_rows.append(
            '<tr>'
            f'<td class="name">{escape(row.name)}</td>'
            f'<td class="type">{escape(row.type)}</td>'
            f'<td class="default">{escape(row.default)}</td>'
            f'<td>{escape(row.note)}</td>'
            '</tr>'
        )
    body = "<tbody>" + "".join(body_rows) + "</tbody>"
    return f'<table class="param-table">{head}{body}</table>'


_DEEP_DIVE_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "meaning": "Ý nghĩa",
        "unit": "Đơn vị",
        "formula": "Công thức",
        "depends_on": "Phụ thuộc",
        "used_by": "Sử dụng bởi",
        "range": "Dải hợp lý",
        "gotchas": "Lưu ý",
        "no_doc": "Chưa có mô tả trong input-semantics.yaml.",
    },
    "en": {
        "meaning": "Meaning",
        "unit": "Unit",
        "formula": "Formula",
        "depends_on": "Depends on",
        "used_by": "Used by",
        "range": "Sensible range",
        "gotchas": "Gotchas",
        "no_doc": "Not yet documented in input-semantics.yaml.",
    },
}


def render_param_deep_dive(rows: Sequence[object], lang: str = "vi") -> str:
    """Render the per-input deep-dive section.

    Each input gets a card with meaning / unit / formula / dependencies /
    sensible range / gotchas. Inputs not present in the semantics
    library still get a card so the user sees them — just with the
    ``no_doc`` placeholder.

    The ``rows`` argument is a sequence of ``EnrichedParamRow`` (from
    ``ea_docs_semantics``); typed as ``object`` here to avoid a hard
    import cycle.
    """
    if not rows:
        return ""
    labels = _DEEP_DIVE_LABELS.get(lang) or _DEEP_DIVE_LABELS["vi"]
    cards: list[str] = []
    for row in rows:
        name = escape(getattr(row, "name", ""))
        type_ = escape(getattr(row, "type", ""))
        default = escape(getattr(row, "default", ""))
        group = escape(getattr(row, "group", "") or "")
        sem = getattr(row, "semantic", None)
        header = (
            f'<div class="dd-header">'
            f'<code class="dd-name">{name}</code>'
            f'<code class="dd-type">{type_}</code>'
            f'<span class="dd-default">= {default}</span>'
        )
        if group:
            header += f'<span class="dd-group">{group}</span>'
        header += "</div>"

        body_parts: list[str] = []
        if sem is None:
            tooltip = escape(getattr(row, "tooltip", "") or "")
            if tooltip:
                body_parts.append(f'<p class="dd-tooltip">{tooltip}</p>')
            body_parts.append(
                f'<p class="dd-missing">{escape(labels["no_doc"])}</p>'
            )
        else:
            def _field(label_key: str, value: str) -> str:
                if not value:
                    return ""
                return (
                    f'<dt>{escape(labels[label_key])}</dt>'
                    f'<dd>{_escape_multiline(value)}</dd>'
                )

            dl_parts = [
                _field("meaning", sem.meaning),
                _field("unit", sem.unit),
                _field("formula", sem.formula),
                (
                    _field("depends_on", ", ".join(sem.depends_on))
                    if sem.depends_on else ""
                ),
                _field("used_by", sem.used_by),
                _field("range", sem.sensible_range),
                _field("gotchas", sem.gotchas),
            ]
            dl = "".join(part for part in dl_parts if part)
            if dl:
                body_parts.append(f'<dl class="dd-fields">{dl}</dl>')

        cards.append(
            f'<article class="param-card">{header}'
            f'{"".join(body_parts)}'
            '</article>'
        )
    return f'<div class="param-deep-dive">{"".join(cards)}</div>'


def _escape_multiline(text: str) -> str:
    """Escape + preserve newlines as <br>, suitable for short narrative blobs."""
    return escape(text).replace("\n", "<br>")


def render_flow_narrative(narrative_md: str) -> str:
    """Render the FLOW narrative inside a styled scroll block.

    The narrative is plain markdown (authored by humans, placeholder-
    substituted upstream). We do NOT run a full markdown parser — that
    would add a dep and the FLOW files deliberately use only simple
    constructs. Instead we wrap the content in a ``<pre>`` so newlines,
    tables and ASCII diagrams render verbatim, which is the look the
    Neo-Retro deck already uses for code-shaped artifacts.
    """
    if not narrative_md:
        return ""
    return (
        '<section class="flow-narrative">'
        f'<pre class="flow-body">{escape(narrative_md)}</pre>'
        '</section>'
    )


def render_take_note(note: TakeNote) -> str:
    """Render one annotated callout (used in §5 Take notes)."""
    severity = note.severity if note.severity in ("info", "warn", "danger") else "info"
    return (
        f'<div class="take-note {severity}">'
        f'<div class="icon">'
        f'<span class="pixel-icon lg">{load_icon(note.icon)}</span>'
        f'</div>'
        f'<div class="body">'
        f'<h3 class="h-card">{escape(note.title)}</h3>'
        f'<p>{escape(note.body)}</p>'
        f'</div>'
        f'</div>'
    )


def render_html_document(content: DocContent) -> str:
    """Render the full ``<!doctype html>`` page.

    All assets (CSS + SVG icons) are inlined so the output is a single
    self-contained file. Safe to ship via email, mount on a static host,
    or feed to headless Chrome for ``--print-to-pdf``.
    """
    css = load_asset("style.css")
    fm = render_frontmatter(content.frontmatter)
    manifesto = render_manifesto(content)

    labels = section_labels(content.lang)
    sections: list[str] = []
    if content.overview_layers:
        sections.append(render_section_header(labels["overview"], "robot"))
        sections.append(render_layer_stack(content.overview_layers))
    if content.strategy_timeline:
        sections.append(render_section_header(labels["strategy"], "rocket"))
        sections.append(render_timeline(content.strategy_timeline))
    if content.params:
        sections.append(render_section_header(labels["params"], "code"))
        sections.append(render_param_table(content.params, lang=content.lang))
    if content.enriched_params:
        sections.append(render_section_header(labels["param_deep_dive"], "gear"))
        sections.append(
            render_param_deep_dive(content.enriched_params, lang=content.lang)
        )
    if content.flow_narrative:
        sections.append(render_section_header(labels["flow"], "robot"))
        sections.append(render_flow_narrative(content.flow_narrative))
    if content.notes:
        sections.append(render_section_header(labels["notes"], "spark"))
        for note in content.notes:
            sections.append(render_take_note(note))
    if content.closing_html:
        sections.append(content.closing_html)

    body = (
        '<main>'
        f'{fm}'
        f'{manifesto}'
        f'{"".join(sections)}'
        '</main>'
    )
    head = (
        '<!doctype html>'
        '<html lang="vi">'
        '<head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(content.title_main)}</title>'
        f'<style>{css}</style>'
        '</head>'
    )
    return f'{head}<body>{body}</body></html>'
