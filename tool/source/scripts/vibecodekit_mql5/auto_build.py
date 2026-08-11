"""mql5-auto-build — single-command EA build pipeline.

Reads a YAML or JSON spec and runs, in order:

    1. build     — render scaffold + Include/.mqh → project dir
    2. lint      — 23 anti-pattern detectors on the rendered .mq5
    3. compile   — MetaEditor (Wine on Linux) → .ex5  (skippable)
    4. gate      — permission.orchestrator in spec-declared mode (skippable)
    5. dashboard — render quality-matrix HTML + optional publish (skippable)
    6. docs      — LLM structure-driven pipeline: emit docs-context.json +
                   docs-prompt.md (from the real .mq5 inputs) and, when a
                   guide.md has been authored, render the ship .docx via
                   docs-assemble. (skippable)

Each stage is fail-fast: the first stage to fail aborts the pipeline.
A `report.json` summarising every stage is always written to
``<out_dir>/auto-build-report.json``, even on failure.

Spec schema (YAML or JSON, minimum required fields):

    name:      str  EA name; also the project dir + magic seed
    preset:    str  scaffold preset (trend, stdlib, ml-onnx, ...)
    stack:     str  scaffold stack (netting, hedging, python-bridge, ...)
    symbol:    str  trading symbol (EURUSD, XAUUSD, ...)
    timeframe: str  H1, M15, M5, ...
    mode:      str  optional; permission mode (personal/team/enterprise),
                    default "personal"

Usage:
    mql5-auto-build --spec ea-spec.yaml [--out-dir DIR] [--no-compile]
                    [--no-gate] [--force]

Exit codes:
    0 — pipeline succeeded
    1 — one stage failed (see report.json)
    2 — invocation error (bad spec, missing files, etc.)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import auto_build_docs_ship_stage as docs_ship_stage_mod
from . import build as build_mod
from . import compile as compile_mod
from . import dashboard as dashboard_mod
from . import ir_build as ir_build_mod
from . import lint as lint_mod
from . import package as package_mod
from . import release_policy, spec_schema
from .ea_ir import from_dict as ir_from_dict

# Kept for backward compat with anything that imported these constants from
# auto_build. The canonical source-of-truth now lives in spec_schema.
REQUIRED_FIELDS: tuple[str, ...] = spec_schema.REQUIRED_TOP_FIELDS
VALID_MODES: frozenset[str] = spec_schema.VALID_MODES


@dataclass
class StageResult:
    name: str
    ok: bool
    skipped: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "skipped": self.skipped, **self.detail}


@dataclass
class PipelineReport:
    spec: dict[str, Any]
    out_dir: str
    ok: bool = True
    stages: list[StageResult] = field(default_factory=list)
    dashboard: dict[str, Any] | None = None
    docs: dict[str, Any] | None = None
    package: dict[str, Any] | None = None
    # LLM-driven `.docx` ship pipeline (Pattern A): `docs_bundle` is the
    # deterministic context+prompt the kit emits for an external agent;
    # `docs_assemble` is the conversion of the agent's `guide.md` to a
    # Word `.docx`. Both are informational stages and never flip
    # ``report.ok``.
    docs_bundle: dict[str, Any] | None = None
    docs_assemble: dict[str, Any] | None = None
    status: dict[str, Any] | None = None
    evidence_manifest: dict[str, Any] | None = None
    unsafe_flags_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec,
            "out_dir": self.out_dir,
            "ok": self.ok,
            "stages": [s.to_dict() for s in self.stages],
            "dashboard": self.dashboard,
            "docs": self.docs,
            "docs_bundle": self.docs_bundle,
            "docs_assemble": self.docs_assemble,
            "package": self.package,
            "status": self.status,
            "evidence_manifest": self.evidence_manifest,
            "unsafe_flags_used": self.unsafe_flags_used,
            "release_eligible": bool((self.status or {}).get("release_eligible")),
        }


def load_spec(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"spec not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "YAML spec given but PyYAML not installed; "
                "`pip install pyyaml` or use a .json spec"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        # Keep ValueError for the established CLI/API contract.
        raise ValueError(  # noqa: TRY004
            f"spec must be a mapping, got {type(data).__name__}"
        )
    return data


def validate_spec(spec: dict[str, Any]) -> spec_schema.EaSpec:
    """Validate ``spec`` and return a populated :class:`EaSpec`.

    Delegates to :func:`spec_schema.validate` so the schema (required fields,
    risk bounds, signal kinds) lives in exactly one place. Raises ``ValueError``
    on bad input so the existing ``main()`` error-handling path keeps working
    — ``SpecValidationError`` is a subclass of ``ValueError``.
    """
    return spec_schema.validate(spec, valid_presets=build_mod.PRESETS)


def _stage_build(
    spec: dict[str, Any],
    out_dir: Path,
    force: bool,
    ea_spec: spec_schema.EaSpec | None = None,
) -> StageResult:
    # Validated EaSpec carries risk + signals/filters/hooks for template
    # substitution and signals.md emission. When ``ea_spec`` is None (e.g. a
    # direct caller that bypassed validate_spec) fall back to defaults.
    extras: dict[str, str] = {}
    extra_files: list[tuple[str, str]] = []
    if ea_spec is not None:
        extras = ea_spec.risk.as_template_vars()
        if ea_spec.signals or ea_spec.filters:
            extra_files.append(("signals.md", spec_schema.render_signals_doc(ea_spec)))

    req = build_mod.BuildRequest(
        preset=spec["preset"],
        name=spec["name"],
        symbol=spec["symbol"],
        tf=spec["timeframe"],
        stack=spec["stack"],
        out_dir=out_dir,
        scaffolds_root=build_mod.DEFAULT_SCAFFOLDS,
        include_root=build_mod.DEFAULT_INCLUDE,
        force=force,
        extras=extras,
        extra_files=extra_files,
    )
    try:
        result_dir = build_mod.build(req)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        return StageResult("build", ok=False, detail={"error": str(exc)})
    files = sorted(str(p.relative_to(result_dir)) for p in result_dir.rglob("*") if p.is_file())
    return StageResult("build", ok=True, detail={"out_dir": str(result_dir), "files": files})


def _locate_main_mq5(result_dir: Path, name: str) -> Path | None:
    """Locate the primary ``.mq5`` the build stage produced.

    Handles both the flat layout (``<out>/<name>.mq5``) and the MT5-native
    layout (``<out>/Experts/<name>/<name>.mq5``). Falls back to any single
    ``.mq5`` under the build dir so renamed scaffolds keep working. Returns
    ``None`` only when the build produced no ``.mq5`` at all.
    """
    direct = result_dir / f"{name}.mq5"
    if direct.is_file():
        return direct
    named = sorted(result_dir.rglob(f"{name}.mq5"))
    if named:
        for p in named:
            if "Experts" in p.parts:
                return p
        return named[0]
    any_mq5 = sorted(result_dir.rglob("*.mq5"))
    return any_mq5[0] if any_mq5 else None


def _stage_lint(mq5_path: Path) -> StageResult:
    findings = lint_mod.lint_file(mq5_path)
    errors = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARN"]
    return StageResult(
        "lint",
        ok=not errors,
        detail={
            "errors": [f.format() for f in errors],
            "warnings": [f.format() for f in warnings],
            "n_errors": len(errors),
            "n_warnings": len(warnings),
        },
    )


def _stage_compile(mq5_path: Path) -> StageResult:
    result = compile_mod.compile_mq5(mq5_path)
    data = result.to_dict()
    return StageResult(
        "compile",
        ok=bool(data.get("success")),
        detail={
            "errors": data.get("errors", []),
            "warnings": data.get("warnings", []),
            "ex5_path": data.get("ex5_path", ""),
        },
    )


def _stage_gate(mq5_path: Path, mode: str) -> StageResult:
    # Lazy import — orchestrator pulls in all 7 layers, keep startup light.
    from .permission import orchestrator as orch_mod

    ns = argparse.Namespace(
        source=mq5_path,
        mode=mode,
        compile_log=None,
        trader_check_report=None,
        state_dir=Path(".rri-state"),
        matrix=None,
        multibroker=None,
        journal=None,
    )
    report = orch_mod.run(ns)
    return StageResult(
        "gate",
        ok=report.ok,
        detail={"mode": report.mode, "layers": report.layers},
    )


def run_pipeline(
    spec: dict[str, Any],
    out_dir: Path,
    skip_compile: bool = False,
    skip_gate: bool = False,
    skip_dashboard: bool = False,
    skip_docs: bool = False,
    force: bool = False,
    ea_spec: spec_schema.EaSpec | None = None,
    publish_cmd: str | None = None,
    docs_lang: str = "vi",
    docs_formats: tuple[str, ...] = ("html", "md"),
    package_artifacts: bool = False,
    package_spec: Path | None = None,
    package_zip: Path | None = None,
    draft: bool = False,
) -> PipelineReport:
    report = PipelineReport(spec=spec, out_dir=str(out_dir))
    compatibility = spec.get("compatibility")
    if (
        isinstance(compatibility, dict)
        and compatibility.get("mode") == "legacy_scaffold"
        and compatibility.get("release_eligible") is False
    ):
        report.unsafe_flags_used.append("--legacy-scaffold")
    if draft:
        report.unsafe_flags_used.append("--draft")
    if skip_compile:
        report.unsafe_flags_used.append("--no-compile")
    if skip_gate:
        report.unsafe_flags_used.append("--no-gate")

    def _finalize(mq5: Path | None) -> PipelineReport:
        # Informational stages always run last and never flip pipeline ok.
        # Docs runs BEFORE dashboard so the dashboard embed card can
        # derive its links from what the docs stage actually wrote
        # (report.docs['outputs']) instead of promising files that the
        # PDF render — or an early build failure — may never produce.
        # Docgen policy (v2.6+): the ship docs are authored ONLY by the
        # LLM structure-driven pipeline (docs-bundle -> guide.md ->
        # docs-assemble). The legacy fixed-template renderer fabricated
        # generic per-archetype prose and only documented inputs present
        # in a hand-authored semantics dictionary, so it described
        # inputs/logic that did not match the actually-built EA. It has
        # been removed entirely.
        if skip_docs:
            report.docs = {"skipped": True}
        else:
            report.docs = {
                "skipped": True,
                "reason": (
                    "ship docs come from the LLM structure-driven "
                    "pipeline (docs-bundle -> guide.md -> docs-assemble); "
                    "the legacy fixed-template renderer has been removed."
                ),
                "mode": "llm",
            }
        docs_ship_stage_mod.attach_docs_bundle(
            report, out_dir, spec=spec, mq5_path=mq5, skip=skip_docs,
        )
        docs_ship_stage_mod.attach_docs_assemble(
            report, out_dir, ea_name=str(spec.get("name", "")), skip=skip_docs,
        )
        _maybe_attach_dashboard(
            report, out_dir, skip=skip_dashboard,
            publish_cmd=publish_cmd,
        )
        # When packaging is enabled, snapshot the pipeline report to disk
        # BEFORE the packager runs so the ship-zip captures the
        # build/lint/compile/gate/docs/dashboard verdict. The packager
        # picks the file off disk; without this pre-write the zip ships
        # without `auto-build-report.json` and a reviewer has no proof of
        # which gates ran green.
        report.status = release_policy.summarize(report.to_dict(), unsafe_flags=report.unsafe_flags_used)
        report.evidence_manifest = release_policy.write_evidence_manifest(out_dir, report.to_dict(), unsafe_flags=report.unsafe_flags_used)
        report.status = release_policy.summarize(report.to_dict(), unsafe_flags=report.unsafe_flags_used)
        if package_artifacts:
            _write_report(report, out_dir)
        _maybe_attach_package(
            report,
            out_dir,
            enabled=package_artifacts,
            spec_path=package_spec,
            zip_path=package_zip,
        )
        # Canonical on-disk write, run unconditionally so the file always
        # reflects the post-package state of `report.package`. When
        # `package_artifacts=False` this is `{"skipped": True}`; when the
        # packager ran it's the manifest summary. The copy inside the
        # zip (already sealed above) stays at the pre-package snapshot,
        # which is the build-side verdict and avoids the sha256
        # chicken-and-egg with `manifest.json`.
        _write_report(report, out_dir)
        return report

    build_stage = _stage_build(spec, out_dir, force, ea_spec=ea_spec)
    report.stages.append(build_stage)
    if not build_stage.ok:
        report.ok = False
        return _finalize(None)

    # Locate the .mq5 from the build result directory. The build stage may emit
    # an MT5-native tree (Experts/<name>/<name>.mq5), so a flat lookup is wrong;
    # search the actual result dir recursively instead.
    result_dir = Path(build_stage.detail.get("out_dir") or out_dir)
    mq5_path = _locate_main_mq5(result_dir, spec["name"])
    if mq5_path is None:
        report.stages.append(StageResult("lint", ok=False, detail={"error": "no .mq5 produced"}))
        report.ok = False
        return _finalize(None)

    lint_stage = _stage_lint(mq5_path)
    report.stages.append(lint_stage)
    if not lint_stage.ok:
        report.ok = False
        return _finalize(mq5_path)

    if skip_compile:
        report.stages.append(StageResult("compile", ok=False, skipped=True, detail={"release_eligible": False}))
    else:
        compile_stage = _stage_compile(mq5_path)
        report.stages.append(compile_stage)
        if not compile_stage.ok:
            report.ok = False
            return _finalize(mq5_path)

    if skip_gate:
        report.stages.append(StageResult("gate", ok=False, skipped=True, detail={"release_eligible": False}))
    else:
        gate_stage = _stage_gate(mq5_path, spec.get("mode", "personal"))
        report.stages.append(gate_stage)
        if not gate_stage.ok:
            report.ok = False

    return _finalize(mq5_path)


def _maybe_attach_package(
    report: PipelineReport,
    out_dir: Path,
    *,
    enabled: bool,
    spec_path: Path | None,
    zip_path: Path | None,
) -> None:
    if not enabled:
        report.package = {"skipped": True}
        return
    status = release_policy.summarize(report.to_dict(), unsafe_flags=report.unsafe_flags_used)
    if not status.get("release_eligible"):
        report.package = {"skipped": True, "blocked": True, "reason": "not release eligible", "status": status}
        return
    if not report.ok:
        report.package = {"skipped": True, "reason": "pipeline failed"}
        return
    try:
        manifest = package_mod.package_out_dir(
            out_dir,
            zip_path=zip_path,
            spec_path=spec_path,
        )
        manifest_path = out_dir / package_mod.DEFAULT_MANIFEST_NAME
        report.package = {
            "ok": True,
            "manifest_path": str(manifest_path),
            "zip_path": manifest.zip_path,
            "groups": manifest.groups,
            "artifact_count": len(manifest.artifacts),
        }
    except OSError as exc:
        report.package = {"ok": False, "error": f"package failed: {exc}"}


def _maybe_attach_dashboard(
    report: PipelineReport,
    out_dir: Path,
    *,
    skip: bool,
    publish_cmd: str | None,
) -> None:
    """Render + publish the quality-matrix dashboard and stash it on report.

    Never raises; on failure the dashboard block records the error and the
    overall pipeline outcome is unchanged. The dashboard step is
    informational — a broken publish hook must not turn a green build red.

    The embedded docs card is built from ``report.docs['outputs']`` —
    i.e. the files the docs stage actually wrote on disk. This is the
    single source of truth so the dashboard never advertises a broken
    link (PDF render failed, build aborted before docs ran, etc.).
    """
    if skip:
        report.dashboard = {"skipped": True}
        return
    try:
        name = str(report.spec.get("name", "ea"))
        digest = dashboard_mod.PipelineDigest(
            name=name,
            ok=report.ok,
            stages=[s.to_dict() for s in report.stages],
            docs_links=_docs_links_from_report(report.docs, out_dir),
        )
        html_path = dashboard_mod.write_dashboard(digest, out_dir)
        location = dashboard_mod.publish(html_path, publish_cmd=publish_cmd)
        report.dashboard = location.to_dict()
    except (OSError, ValueError) as exc:
        # ``OSError`` covers filesystem permission / disk-full / etc.;
        # ``ValueError`` previously leaked out of ``Path.as_uri()`` when
        # callers passed a relative ``--out-dir``. The dashboard step is
        # informational — a broken publish path must never turn a green
        # build red, so swallow both and record the failure on the report.
        report.dashboard = {"error": f"dashboard render failed: {exc}"}


def _docs_links_from_report(
    docs: dict[str, Any] | None,
    out_dir: Path,
) -> dict[str, str]:
    """Derive the embed-card links from the docs stage's actual outputs.

    ``docs['outputs']`` is a dict of ``format → absolute path`` recorded
    by the docs stage (when present). We turn those absolute
    paths into filenames relative to ``out_dir`` (since the dashboard
    HTML sits in the same directory, ``<filename>`` is the right href).

    Returns an empty dict when:

    * docs is unset (the docs stage recorded no outputs),
    * docs.ok is missing/false (stage errored / skipped),
    * docs.outputs is empty (no format succeeded — e.g. PDF-only and
      Chrome was unavailable).
    """
    if not docs or not docs.get("ok"):
        return {}
    outputs = docs.get("outputs") or {}
    if not isinstance(outputs, dict):
        return {}
    links: dict[str, str] = {}
    for fmt, abs_path in outputs.items():
        if not isinstance(fmt, str) or not isinstance(abs_path, str):
            continue
        try:
            rel = Path(abs_path).resolve().relative_to(out_dir.resolve())
        except ValueError:
            # Output lives outside out_dir (shouldn't happen, but the
            # dashboard uses relative hrefs so absolute paths from
            # foreign dirs would point at the wrong file).
            continue
        links[fmt] = str(rel)
    return links


def _write_report(report: PipelineReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "auto-build-report.json"
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path




def _run_ir_auto_build(spec_path: Path, raw: dict[str, Any], args: argparse.Namespace) -> int:
    """Run the strict EA-IR pipeline through the familiar auto-build CLI.

    EA-IR capability blockers are never suppressed by ``--draft``: draft may
    skip native verification, but it must not claim an unsupported requirement
    was implemented.
    """
    ir = ir_from_dict(raw)
    name = str(ir.identity.get("name") or "")
    out_dir = args.out_dir or Path.cwd() / name
    try:
        report = ir_build_mod.run(
            spec_path, out_dir, force=args.force, allow_beta=bool(args.draft),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"mql5-auto-build: {exc}", file=sys.stderr)
        return 2

    stages: list[dict[str, Any]] = [
        {"name": "intake", "ok": bool(report["status"].get("requirements_confirmed"))},
        {"name": "capability", "ok": bool(report["status"].get("capability_satisfied"))},
        {"name": "source", "ok": bool(report["status"].get("source_complete"))},
    ]
    if not report["status"].get("source_complete"):
        report["ok"] = False
        report["stages"] = stages
        (out_dir / "auto-build-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    main_path = Path(report["generated_main"])
    if args.no_compile:
        stages.append({"name": "compile", "ok": False, "skipped": True})
    else:
        compile_stage = _stage_compile(main_path)
        stages.append(compile_stage.to_dict())
        report["status"]["compile_verified"] = compile_stage.ok
    if args.no_gate:
        stages.append({"name": "gate", "ok": False, "skipped": True})
    elif report["status"].get("compile_verified"):
        gate_stage = _stage_gate(main_path, "enterprise")
        stages.append(gate_stage.to_dict())
        report["status"]["governance_verified"] = gate_stage.ok
    else:
        stages.append({"name": "gate", "ok": False, "skipped": True, "reason": "compile not verified"})

    requested_ok = bool(report["status"].get("source_complete"))
    if not args.no_compile:
        requested_ok = requested_ok and bool(report["status"].get("compile_verified"))
    if not args.no_gate:
        requested_ok = requested_ok and bool(report["status"].get("governance_verified"))
    report["ok"] = requested_ok
    report["stages"] = stages
    # Runtime/tester evidence is still mandatory for release eligibility.
    report["status"]["release_eligible"] = bool(
        report["status"].get("compile_verified")
        and report["status"].get("tester_verified")
        and report["status"].get("governance_verified")
    )
    (out_dir / "auto-build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nreport: {out_dir / 'auto-build-report.json'}", file=sys.stderr)
    return 0 if requested_ok else 1

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-auto-build", description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True, type=Path, help="YAML or JSON spec file")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="output directory (default: ./<spec.name>)")
    ap.add_argument("--no-compile", action="store_true",
                    help="skip MetaEditor compile stage (useful without Wine)")
    ap.add_argument("--no-gate", action="store_true",
                    help="skip permission.orchestrator stage")
    ap.add_argument("--no-dashboard", action="store_true",
                    help="skip the quality-matrix dashboard step")
    ap.add_argument("--publish-cmd", default=None,
                    help="override $MQL5_DASHBOARD_PUBLISH_CMD for this run")
    ap.add_argument("--no-docs", action="store_true",
                    help="skip the post-build EA documentation step")
    ap.add_argument("--docs-lang", choices=("vi", "en"), default="vi",
                    help="language for generated docs (default: vi)")
    ap.add_argument("--docs-formats", default="html,md",
                    help="(reserved) comma-separated docs formats. The "
                         "legacy fixed-template renderer was removed; ship "
                         "docs now come from the LLM structure-driven "
                         "pipeline (docs-bundle -> guide.md -> docs-assemble).")
    ap.add_argument("--package", action="store_true",
                    help="write manifest.json and a ship-ready zip after a green build")
    ap.add_argument("--package-zip", type=Path, default=None,
                    help="override the package zip path (default: <out-dir>/<name>-ship.zip)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing output directory")
    ap.add_argument("--draft", action="store_true",
                    help="Draft mode: skip the permission gate, skip the "
                         "(slow) MetaEditor compile + docs steps, and "
                         "always exit 0 so the chat-driven build loop can "
                         "iterate on a half-finished EA without the "
                         "pipeline slamming the door on every commit. "
                         "Implies --no-compile --no-gate --no-docs.")
    args = ap.parse_args(argv)
    if args.draft:
        args.no_compile = True
        args.no_gate = True
        args.no_docs = True

    try:
        spec = load_spec(args.spec)
    except (FileNotFoundError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"mql5-auto-build: {exc}", file=sys.stderr)
        return 2

    if spec.get("schema_version") == "3.1":
        return _run_ir_auto_build(args.spec, spec, args)

    try:
        ea_spec = validate_spec(spec)
    except (ValueError, RuntimeError) as exc:
        print(f"mql5-auto-build: {exc}", file=sys.stderr)
        return 2

    out_dir = args.out_dir or Path.cwd() / spec["name"]
    docs_formats_raw = {f.strip() for f in args.docs_formats.split(",") if f.strip()}
    invalid_formats = docs_formats_raw - {"html", "md", "pdf"}
    if invalid_formats:
        print(
            f"mql5-auto-build: unknown --docs-formats values: "
            f"{sorted(invalid_formats)} (supported: html, md, pdf)",
            file=sys.stderr,
        )
        return 2
    docs_formats = tuple(
        f for f in ("html", "md", "pdf") if f in docs_formats_raw
    )
    report = run_pipeline(
        spec,
        out_dir,
        skip_compile=args.no_compile,
        skip_gate=args.no_gate,
        skip_dashboard=args.no_dashboard,
        skip_docs=args.no_docs,
        force=args.force,
        ea_spec=ea_spec,
        publish_cmd=args.publish_cmd,
        docs_lang=args.docs_lang,
        docs_formats=docs_formats,
        package_artifacts=args.package,
        package_spec=args.spec,
        package_zip=args.package_zip,
        draft=args.draft,
    )
    # run_pipeline._finalize() already wrote auto-build-report.json (once
    # pre-package so the zip captures the build verdict, and again after
    # packaging when --package is set so the on-disk file also carries the
    # manifest summary). Nothing left to write here — just emit the JSON
    # body + a stderr breadcrumb for callers.
    report_path = out_dir / "auto-build-report.json"
    print(json.dumps(report.to_dict(), indent=2))
    print(f"\nreport: {report_path}", file=sys.stderr)
    if args.draft:
        # Draft mode never blocks the chat-driven build loop. The full
        # report is still on stdout so the caller can see what would
        # have failed; the exit code just stops being a gate.
        if not report.ok:
            print("(draft mode: pipeline reported failures, but "
                  "exit code suppressed to 0)", file=sys.stderr)
        return 0
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
