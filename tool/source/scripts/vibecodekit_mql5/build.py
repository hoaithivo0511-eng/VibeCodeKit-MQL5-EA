"""mql5-build — render a scaffold into a fresh project directory.

Usage:
    mql5-build <preset> --name X --symbol Y --tf Z [--stack S] [--out DIR]

Core presets:
    stdlib              stacks: netting, hedging, python-bridge
    wizard-composable   stacks: netting
    portfolio-basket    stacks: netting, hedging
    ml-onnx             stacks: python-bridge

What it does:
    1. Locate <scaffolds_root>/<preset>/<stack>/ — defaults to <repo>/scaffolds.
    2. Render every file under it, substituting {{NAME}}, {{SYMBOL}}, {{TF}},
       {{MAGIC}} into both filenames and content.
    3. Refuse to overwrite an existing output dir unless --force.
    4. Copy every `Include/*.mqh` helper next to the rendered .mq5 so the
       project is self-contained and `mql5-compile` Just Works. As of
       v2.0.0 that is 10 headers (CAsyncTradeManager, CHistorySync,
       CMagicRegistry, CMemorySafety, CMfeMaeLogger, COnnxLoader,
       CPipNormalizer, CRiskGuard, CSafeTradeManager, CSpreadGuard); the
       copy step is a `*.mqh` glob, so adding a new header to `Include/`
       picks it up automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ._resources import asset_root, repo_root
from .safe_paths import safe_join, validate_ea_name

REPO_ROOT = repo_root()
DEFAULT_SCAFFOLDS = asset_root("scaffolds")
DEFAULT_INCLUDE   = asset_root("Include")

CORE_PRESETS: dict[str, list[str]] = {
    "stdlib":            ["netting", "hedging", "python-bridge"],
    "wizard-composable": ["netting"],
    "portfolio-basket":  ["netting", "hedging"],
    "ml-onnx":           ["python-bridge"],
}

# 14 additional scaffolds (1 HFT async, 3 LLM bridge variants, 10 strategy
# archetypes). Kept as a separate dict so the core preset tests stay
# untouched but consumers see the combined map via PRESETS below.
ADVANCED_PRESETS: dict[str, list[str]] = {
    "hft-async":          ["netting"],
    "service-llm-bridge": ["cloud-api", "self-hosted-ollama", "embedded-onnx-llm"],
    "trend":              ["netting"],
    "mean-reversion":     ["hedging"],
    "breakout":           ["netting"],
    "hedging-multi":      ["hedging"],
    "news-trading":       ["netting"],
    "arbitrage-stat":     ["python-bridge"],
    "scalping":           ["hedging"],
    "library":            ["netting"],
    "indicator-only":     ["netting"],
    "grid":               ["hedging"],
    "dca":                ["hedging"],
}

# The MQL5 Service archetype (build 5320+). Services are chart-less
# background programs (data collectors, LLM/REST pollers, VPS canaries)
# — they live alongside EAs but never call CTrade, so they intentionally
# bypass the EA risk-guard wiring.
SERVICE_PRESETS: dict[str, list[str]] = {
    "service":            ["standalone"],
}

PRESETS: dict[str, list[str]] = {
    **CORE_PRESETS,
    **ADVANCED_PRESETS,
    **SERVICE_PRESETS,
}


@dataclass
class BuildRequest:
    preset: str
    name: str
    symbol: str
    tf: str
    stack: str
    out_dir: Path
    scaffolds_root: Path
    include_root: Path
    force: bool = False
    # Output directory layout. "mt5" (default) emits an MT5-native tree
    # (Experts/<Name>/, Include/<Name>/, Presets/<Name>/, Files/<Name>/) and
    # rewrites quoted local includes to angle-bracket <Name/Foo.mqh> form so
    # MetaEditor resolves them from the MQL5/Include root. "flat" preserves the
    # legacy single-folder output (everything beside the .mq5); kept for
    # internal callers and quick throwaway compiles.
    layout: str = "mt5"
    # Optional per-build template variables, e.g. risk overrides emitted by
    # ``spec_schema.RiskConfig.as_template_vars``. Each key/value is replaced
    # in scaffold text as ``{{KEY}}`` -> ``value``. Empty by default so the
    # existing callers (``mql5-build`` CLI, preset tests) keep their old
    # behaviour: scaffolds with no extra placeholders render identically.
    extras: dict[str, str] = field(default_factory=dict)
    # Optional companion files to write into ``out_dir`` after the scaffold
    # has been rendered, e.g. ``signals.md`` describing the indicator chain
    # the user asked for. ``(rel_path, content)`` tuples; UTF-8 text only.
    extra_files: list[tuple[str, str]] = field(default_factory=list)


def _magic_for(name: str) -> int:
    """Deterministic 5-digit-ish magic from the EA name. 70000–79999 range."""
    h = int(hashlib.sha1(name.encode("utf-8")).hexdigest(), 16)
    return 70000 + (h % 10000)


# Default values for spec-driven placeholders. Used when a scaffold template
# references e.g. ``{{RISK_MONEY}}`` but the caller didn't supply ``extras``
# (typical for the bare ``mql5-build`` CLI). These match the previous hardcoded
# numbers in stdlib/netting so the rendered output is identical to v1.0.1.
_EXTRA_DEFAULTS: dict[str, str] = {
    "RISK_MONEY":         "100.0",
    "RISK_PER_TRADE_PCT": "0.5",
    "SL_PIPS":            "30",
    "TP_PIPS":            "60",
    "DAILY_LOSS_FRAC":    "0.05",
    "DAILY_LOSS_PCT":     "5.0",
    "MAX_SPREAD_PIPS":    "3.0",
    "MAX_POSITIONS":      "3",
}


def _render(text: str, req: BuildRequest, magic: int) -> str:
    out = (
        text.replace("{{NAME}}",   req.name)
            .replace("{{SYMBOL}}", req.symbol)
            .replace("{{TF}}",     req.tf)
            .replace("{{MAGIC}}",  str(magic))
    )
    # Apply spec-driven overrides first, then fill any leftover defaults so
    # scaffolds that reference {{RISK_MONEY}} / {{SL_PIPS}} / ... still render
    # correctly when the caller (e.g. plain ``mql5-build`` CLI) didn't pass an
    # ``extras`` dict. Templates that don't reference a given placeholder
    # simply ignore it, keeping the change backward-compatible.
    merged: dict[str, str] = {**_EXTRA_DEFAULTS, **req.extras}
    for key, value in merged.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def _render_name(name: str, req: BuildRequest) -> str:
    return name.replace("EAName", req.name).replace("{{NAME}}", req.name)


# Scaffold files with these suffixes are treated as binary: copied as raw
# bytes, no template substitution. Everything else is text + rendered.
_BINARY_SUFFIXES = frozenset({".onnx", ".png", ".jpg", ".jpeg", ".gif",
                              ".ico", ".bin", ".dat"})

VALID_LAYOUTS = ("mt5", "flat")

# Suffixes treated as runtime data assets in MT5-native layout (routed to Files/).
_DATA_SUFFIXES = frozenset({".onnx", ".bin", ".dat", ".csv", ".json"})


def _is_service_preset(preset: str) -> bool:
    return preset in SERVICE_PRESETS


def _route(rel: Path, name: str, layout: str, is_service: bool) -> Path:
    """Map a rendered scaffold file to its destination relative to out_dir.

    ``flat`` returns ``rel`` unchanged (legacy behaviour). ``mt5`` routes by
    program/file type into the canonical MetaTrader 5 folder tree.
    """
    if layout == "flat":
        return rel
    suffix = rel.suffix.lower()
    program_dir = "Services" if is_service else "Experts"
    if suffix == ".mq5":
        return Path(program_dir, name, rel.name)
    if suffix == ".mqh":
        return Path("Include", name, *rel.parts)
    if suffix == ".set":
        return Path("Presets", name, rel.name)
    if suffix in _DATA_SUFFIXES:
        return Path("Files", name, rel.name)
    # Docs / readme / misc text stay at the project root.
    return rel


_INCLUDE_RE = re.compile(r'#include\s+"([^"]+\.mqh)"')


def _rewrite_includes(text: str, header_map: dict[str, str]) -> str:
    """Rewrite quoted local includes to angle-bracket Include-root form.

    ``#include "CRiskGuard.mqh"`` -> ``#include <MyEA/CRiskGuard.mqh>`` when the
    header was routed under ``Include/<Name>/``. Includes whose basename is not
    a project header are left untouched.
    """
    def _sub(m: re.Match) -> str:
        basename = Path(m.group(1)).name
        target = header_map.get(basename)
        return f"#include <{target}>" if target else m.group(0)

    return _INCLUDE_RE.sub(_sub, text)


def build(req: BuildRequest) -> Path:
    validate_ea_name(req.name)
    if req.preset not in PRESETS:
        raise ValueError(f"unknown preset {req.preset!r}; valid: {sorted(PRESETS)}")
    if req.stack not in PRESETS[req.preset]:
        raise ValueError(
            f"preset {req.preset!r} does not support stack {req.stack!r}; "
            f"valid: {PRESETS[req.preset]}"
        )

    src_dir = req.scaffolds_root / req.preset / req.stack
    if not src_dir.is_dir():
        raise FileNotFoundError(f"scaffold not found: {src_dir}")

    if req.out_dir.exists():
        if not req.force:
            raise FileExistsError(f"refusing to overwrite {req.out_dir} (use --force)")
        shutil.rmtree(req.out_dir)
    req.out_dir.mkdir(parents=True)

    if req.layout not in VALID_LAYOUTS:
        raise ValueError(f"unknown layout {req.layout!r}; valid: {list(VALID_LAYOUTS)}")

    magic = _magic_for(req.name)
    is_service = _is_service_preset(req.preset)

    # ---- Pass 1: render + route every file into an in-memory plan. --------
    # (rel_dst, payload, is_text). We collect header destinations first so
    # Pass 2 can rewrite includes to the canonical Include-root path.
    planned: list[tuple[Path, object, bool]] = []
    header_map: dict[str, str] = {}  # basename -> "<Name>/.../Foo.mqh"

    def _record_header(rel_dst: Path) -> None:
        # In mt5 layout headers live under Include/<Name>/...; the include
        # path is everything after the leading "Include/" segment.
        parts = rel_dst.parts
        if len(parts) >= 2 and parts[0] == "Include":
            header_map[rel_dst.name] = "/".join(parts[1:])

    for src in src_dir.rglob("*"):
        if src.is_dir():
            continue
        # FLOW-{vi,en}.md are authoring artifacts consumed by the docs
        # renderer (``ea_docs_semantics.load_flow_narrative``). They are
        # injected — already placeholder-substituted — into the
        # generated ``.docs.html`` / ``.docs.md``, so the raw template
        # should never reach the end-user's build folder.
        if src.name in ("FLOW-vi.md", "FLOW-en.md"):
            continue
        rel = src.relative_to(src_dir)
        rendered_rel = Path(*[_render_name(p, req) for p in rel.parts])
        rel_dst = _route(rendered_rel, req.name, req.layout, is_service)
        if src.suffix.lower() in _BINARY_SUFFIXES:
            planned.append((rel_dst, src.read_bytes(), False))
        else:
            text = _render(src.read_text(encoding="utf-8", errors="replace"), req, magic)
            planned.append((rel_dst, text, True))
        if req.layout == "mt5" and rel_dst.suffix.lower() == ".mqh":
            _record_header(rel_dst)

    # Co-locate Include/.mqh helpers. flat: beside the .mq5; mt5: under
    # Include/<Name>/ so MetaEditor resolves <Name/Foo.mqh> from MQL5/Include.
    if req.include_root.is_dir():
        for inc in req.include_root.glob("*.mqh"):
            rel_dst = _route(Path(inc.name), req.name, req.layout, is_service)
            planned.append((rel_dst, inc.read_bytes(), False))
            if req.layout == "mt5":
                _record_header(rel_dst)

    # ---- Pass 2: write everything, rewriting includes in mt5 layout. ------
    for rel_dst, payload, is_text in planned:
        dst = safe_join(req.out_dir, rel_dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if is_text:
            text = payload  # type: ignore[assignment]
            if req.layout == "mt5" and dst.suffix.lower() in (".mq5", ".mqh"):
                text = _rewrite_includes(text, header_map)
            dst.write_text(text, encoding="utf-8")
        else:
            dst.write_bytes(payload)  # type: ignore[arg-type]

    # Spec-driven companion files (e.g. signals.md describing the indicator
    # chain the user asked for). Written after the scaffold so they can
    # deliberately shadow any scaffold file of the same name.
    for rel_path, content in req.extra_files:
        dst = safe_join(req.out_dir, rel_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
    return req.out_dir


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-build", description=__doc__.splitlines()[0])
    p.add_argument("preset", choices=sorted(PRESETS))
    p.add_argument("--name",   required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--tf",     required=True)
    p.add_argument("--stack",  default=None,
                   help="default = first stack supported by preset")
    # `--out` is canonical; `--out-dir` / `--workspace` are accepted aliases so
    # the build verb takes the same output flag users already pass to
    # ship/package/dist-package (which use --out-dir). All map to one dest.
    p.add_argument("--out", "--out-dir", "--workspace", dest="out", default=None,
                   metavar="DIR",
                   help="output directory (default: ./<name>); "
                        "aliases: --out-dir, --workspace")
    p.add_argument("--scaffolds-root", default=str(DEFAULT_SCAFFOLDS))
    p.add_argument("--include-root",   default=str(DEFAULT_INCLUDE))
    p.add_argument("--layout", choices=list(VALID_LAYOUTS), default="mt5",
                   help="output tree: mt5 (canonical, default) or flat (legacy)")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)

    stack = args.stack or PRESETS[args.preset][0]
    out_dir = Path(args.out) if args.out else Path.cwd() / args.name
    req = BuildRequest(
        preset=args.preset,
        name=args.name,
        symbol=args.symbol,
        tf=args.tf,
        stack=stack,
        out_dir=out_dir,
        scaffolds_root=Path(args.scaffolds_root),
        include_root=Path(args.include_root),
        force=args.force,
        layout=args.layout,
    )
    try:
        out = build(req)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        print(f"mql5-build: {exc}", file=sys.stderr)
        return 2
    print(f"built {req.preset}/{req.stack} → {out}")
    for f in sorted(out.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
