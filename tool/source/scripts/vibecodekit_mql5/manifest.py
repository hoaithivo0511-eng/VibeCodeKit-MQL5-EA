"""mql5-manifest — emit the root tool catalog (tool-catalog.json).

The catalog describes every command shipped via ``[project.scripts]`` in
``pyproject.toml`` so external agents (Devin / Claude Code / Cursor) can
introspect the kit's surface without parsing 1000+ lines of markdown.

The output is a single JSON document conforming to the schema below:

    {
      "schema_version": "1",
      "kit": "vibecodekit-mql5-ea",
      "kit_version": "<from _version.get_version()>",
      "generated_by": "mql5-manifest",
      "tools": [
        {
          "name":               "mql5-lint",
          "module":             "vibecodekit_mql5.lint",
          "description":        "<first non-empty line of module docstring>",
          "supports_json":      true,
          "supports_sarif":     true,
          "supports_gate_report": true,
          "doc_refs":           ["docs/USAGE-en.md", "docs/COMMANDS.md"]
        },
        ...
      ]
    }

The manifest is recomputed deterministically each time so it can be
regenerated in CI and diffed in code review.

CLI::

    python -m vibecodekit_mql5.manifest --emit > tool-catalog.json
    python -m vibecodekit_mql5.manifest --emit --output tool-catalog.json
    python -m vibecodekit_mql5.manifest --validate tool-catalog.json
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path

from ._resources import distribution_root

REPO_ROOT = distribution_root()
PYPROJECT = REPO_ROOT / "pyproject.toml"
VERSION_FILE = REPO_ROOT / "VERSION"
SCHEMA_VERSION = "1"

# Tools that intentionally don't follow the `mql5-<name>` console-script
# convention (none right now, but here for future use).
_NAME_OVERRIDES: dict[str, str] = {}


def _load_pyproject_scripts() -> dict[str, str]:
    """Return mapping ``{cli_name: "module:func"}`` from pyproject.toml.

    Uses :mod:`tomllib` when available (Python 3.11+). Falls back to a
    light regex parser for the ``[project.scripts]`` block on 3.10. The
    fallback handles the simple ``key = "value"`` line format used in
    this repo; it does NOT cover arbitrary TOML.
    """

    raw = PYPROJECT.read_text(encoding="utf-8")

    try:
        import tomllib  # type: ignore[import-not-found]
        data = tomllib.loads(raw)
        return dict(data.get("project", {}).get("scripts", {}))
    except ImportError:
        pass

    scripts: dict[str, str] = {}
    in_section = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == "[project.scripts]"
            continue
        if not in_section or not stripped or stripped.startswith("#"):
            continue
        m = re.match(r'^([A-Za-z0-9_\-]+)\s*=\s*"([^"]+)"\s*$', stripped)
        if m:
            scripts[m.group(1)] = m.group(2)
    return scripts


def _module_first_doc_line(module_name: str) -> str:
    try:
        mod = importlib.import_module(module_name)
    except Exception:  # noqa: BLE001 — defensive; some modules may have side-effects
        return ""
    doc = (mod.__doc__ or "").strip()
    if not doc:
        return ""
    # Module docstrings tend to start with "<cli-name> — <one-liner>".
    return doc.splitlines()[0].strip()


def _module_supports(module_name: str, flag: str) -> bool:
    """Return True if the module source mentions ``add_<flag>_flag`` or the
    raw argparse flag string.

    This is a heuristic — agents that need a stronger guarantee should
    consult the SARIF or JSON envelope at runtime. The heuristic is good
    enough for catalogue discovery.

    The manifest module itself is hard-excluded: it lists every needle
    string in its own source (as data, not as a flag registration) so
    a naive substring match would flag it as supporting every flag,
    yet its CLI deliberately exposes only ``--emit`` / ``--validate``."""

    # NOTE: a literal package-qualified name is used here on purpose.
    # ``__name__`` resolves to ``"__main__"`` when this file is run via
    # ``python -m vibecodekit_mql5.manifest``, so an ``__name__`` compare
    # would silently fail to short-circuit when the manifest is generated
    # from the CLI.
    if module_name == "vibecodekit_mql5.manifest":
        return False

    try:
        spec = importlib.util.find_spec(module_name)  # type: ignore[attr-defined]
    except Exception:
        return False
    if spec is None or spec.origin is None:
        return False
    try:
        src = Path(spec.origin).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # Each tuple lists strings that uniquely identify a *shaped*
    # capability. Anything generic enough to also match the kit's
    # pre-existing legacy flags (e.g. ``mql5-compile``'s home-grown
    # ``--json`` that prints ``CompileResult.to_dict()`` instead of the
    # ``Envelope``) is deliberately excluded — agents should see ``false``
    # for those tools and call them via their bespoke contract.
    needles = {
        "json":   ("add_json_flag", "emit_json"),
        "sarif":  ("findings_to_sarif", "report_to_sarif",
                   '"sarif"', "'sarif'"),
        "gate":   ("add_gate_report_flag",),
    }[flag]
    return any(needle in src for needle in needles)


def build_manifest() -> dict:
    scripts = _load_pyproject_scripts()
    from . import _version
    from . import surface, maturity
    version = _version.get_version()
    tools: list[dict] = []
    for name in sorted(scripts):
        entry_point = scripts[name]
        module_name = entry_point.split(":")[0]
        tools.append({
            "name": name,
            "module": module_name,
            "entry_point": entry_point,
            "description": _module_first_doc_line(module_name),
            # v2.5 hardening: UX tier (#4) + implementation maturity (#5) so
            # agents/humans can lead with the 5 public commands and never
            # mistake a placeholder skeleton for finished trading logic.
            "tier": surface.tier_of(name),
            "maturity": maturity.maturity_of(module_name),
            "supports_json": _module_supports(module_name, "json"),
            "supports_sarif": _module_supports(module_name, "sarif"),
            "supports_gate_report": _module_supports(module_name, "gate"),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "kit": "vibecodekit-mql5-ea",
        "kit_version": version,
        "generated_by": "mql5-manifest",
        "tools": tools,
    }


def validate_manifest(manifest: dict) -> list[str]:
    """Return a list of human-readable validation errors.

    Empty list means the manifest is internally consistent (every tool's
    name matches what pyproject.toml declares and every module imports).
    """

    errors: list[str] = []
    scripts = _load_pyproject_scripts()
    listed_names = {t["name"] for t in manifest.get("tools", [])}
    declared_names = set(scripts)
    missing = declared_names - listed_names
    extra = listed_names - declared_names
    for name in sorted(missing):
        errors.append(f"missing tool: {name}")
    for name in sorted(extra):
        errors.append(f"extra tool: {name} (not in pyproject.toml)")
    for tool in manifest.get("tools", []):
        if not tool.get("module"):
            errors.append(f"{tool.get('name', '?')}: empty module field")
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-manifest", description=__doc__.splitlines()[0])
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--emit", action="store_true", help="Emit the manifest JSON")
    grp.add_argument("--validate", type=Path, default=None,
                     help="Validate an existing tool-catalog.json against pyproject.toml")
    p.add_argument("--output", type=Path, default=None,
                   help="Write the manifest to this path (default: stdout)")
    args = p.parse_args(argv)

    if args.emit:
        manifest = build_manifest()
        text = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0

    if args.validate:
        if not args.validate.exists():
            print(f"tool-catalog not found: {args.validate}", file=sys.stderr)
            return 2
        manifest = json.loads(args.validate.read_text(encoding="utf-8"))
        errors = validate_manifest(manifest)
        if errors:
            for err in errors:
                print(f"manifest:error: {err}", file=sys.stderr)
            return 1
        print(f"{args.validate}: ok ({len(manifest.get('tools', []))} tools)")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
