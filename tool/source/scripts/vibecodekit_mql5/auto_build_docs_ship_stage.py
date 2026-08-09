"""Auto-build pipeline integration for the LLM-driven ``.docx`` ship pair.

This module hosts the ``attach_docs_bundle`` and ``attach_docs_assemble``
helpers that ``auto_build`` invokes inside ``_finalize``. Keeping them in
a sister module keeps ``auto_build`` under the audit script's
module-LOC ceiling.

Both helpers are intentionally informational: they record outcomes on
``report.docs_bundle`` / ``report.docs_assemble`` without ever flipping
the pipeline's ``ok`` verdict, so a broken renderer or a
not-yet-authored ``guide.md`` never turns a green build red.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import docs_bundle as docs_bundle_mod

if TYPE_CHECKING:
    from .auto_build import PipelineReport


def materialise_spec_for_bundle(out_dir: Path, spec: dict[str, Any]) -> Path:
    """Persist the raw spec dict to a regenerable YAML file.

    The pipeline currently passes the spec around as a raw dict (the
    YAML file is loaded once and discarded), so the bundle helper has
    no original path to read from. Writing a regenerable copy at
    ``<out_dir>/ea-spec.bundle.yaml`` keeps :func:`docs_bundle.write_bundle`
    a pure function over a file path; the packager's
    ``classify_artifact`` routes spec-shaped YAML into the ``repro``
    group so it doesn't pollute the primary ``review`` deliverable.
    """
    import yaml

    out_dir.mkdir(parents=True, exist_ok=True)
    spec_path = out_dir / "ea-spec.bundle.yaml"
    spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return spec_path


def attach_docs_bundle(
    report: "PipelineReport",
    out_dir: Path,
    *,
    spec: dict[str, Any],
    mq5_path: Path | None,
    skip: bool,
) -> None:
    """Write ``docs-context.json`` + ``docs-prompt.md`` for the LLM step."""
    if skip:
        report.docs_bundle = {"skipped": True}
        return
    if mq5_path is None or not mq5_path.is_file():
        report.docs_bundle = {
            "skipped": True,
            "reason": "docs-bundle skipped: .mq5 not available",
        }
        return
    spec_path = materialise_spec_for_bundle(out_dir, spec)
    try:
        result = docs_bundle_mod.write_bundle(
            spec_path,
            mq5_path,
            out_dir,
            build_report_path=out_dir / "auto-build-report.json",
        )
        report.docs_bundle = {
            "ok": result.ok,
            "context_path": result.context_path,
            "prompt_path": result.prompt_path,
            "inputs_total": result.inputs_total,
            "inputs_enriched": result.inputs_enriched,
            "notes": list(result.notes),
        }
    except (OSError, ValueError, RuntimeError) as exc:
        report.docs_bundle = {"ok": False, "error": f"docs-bundle failed: {exc}"}


def attach_docs_assemble(
    report: "PipelineReport",
    out_dir: Path,
    *,
    ea_name: str,
    skip: bool,
) -> None:
    """Render ``guide.md`` to ``<ea>.docs.docx`` when the LLM has written it.

    When the LLM step hasn't run yet (no ``guide.md`` on disk), we
    record a structured skip with the hint to run
    ``mql5-docs-assemble`` later — that matches the kit-light pattern
    where the LLM authoring step lives outside the build.
    """
    if skip:
        report.docs_assemble = {"skipped": True}
        return
    guide_path = out_dir / "guide.md"
    if not guide_path.is_file():
        report.docs_assemble = {
            "skipped": True,
            "reason": (
                "guide.md not found — author it from docs-context.json / "
                "docs-prompt.md then run `mql5-docs-assemble`."
            ),
        }
        return
    docx_path = out_dir / f"{ea_name or 'EA'}.docs.docx"
    try:
        # Lazy import: docs_assemble pulls heavy optional deps (python-docx,
        # markdown-it). Importing them only when the .docx render actually runs
        # keeps `mql5-auto-build` importable/usable on hosts without those deps.
        try:
            from . import docs_assemble as docs_assemble_mod
        except ImportError as exc:
            report.docs_assemble = {
                "skipped": True,
                "reason": f"docs rendering deps unavailable: {exc}",
            }
            return
        result = docs_assemble_mod.assemble(guide_path, docx_path)
        report.docs_assemble = {
            "ok": result.ok,
            "docx_path": result.docx_path,
            "chapters": result.chapters,
            "tables": result.tables,
            "images_embedded": result.images_embedded,
            "warnings": list(result.warnings),
        }
    except (OSError, ValueError) as exc:
        report.docs_assemble = {"ok": False, "error": f"docs-assemble failed: {exc}"}
