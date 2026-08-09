"""mql5-agent-contract — emit the kit's machine-readable agent contract.

While ``tool-catalog.json`` (see :mod:`vibecodekit_mql5.manifest`) is the flat
list of every CLI command, the *agent contract* is the higher-level handshake
an external agent (Devin / Claude Code / Cursor) reads first. It answers:

  * what kit + version + flavor am I talking to?
  * what is the canonical project layout? (mt5-native)
  * which entrypoints should I drive? (the vkmql-* verbs, when present)
  * where do artifacts live? (tool catalog, evidence manifest)
  * what does "release eligible" actually require?
  * which lint/policy rule namespaces exist?
  * which OS environments are supported by CI?

The document is regenerated deterministically so it can live in version
control and be diffed in review.

CLI::

    python -m vibecodekit_mql5.agent_contract --emit > agent-contract.json
    python -m vibecodekit_mql5.agent_contract --emit --output agent-contract.json
    python -m vibecodekit_mql5.agent_contract --validate agent-contract.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import _version
from . import rule_registry as rr
from ._resources import kit_flavor
from .manifest import _load_pyproject_scripts

SCHEMA_VERSION = "1"
KIT_NAME = "vibecodekit-mql5-ea"
CANONICAL_LAYOUT = "mt5"
TOOL_CATALOG = "tool-catalog.json"
EVIDENCE_MANIFEST = "evidence/manifest.json"

# High-level verbs an agent should prefer. Listed in driving order. Only the
# ones actually declared in pyproject.toml are emitted, so this stays correct
# whether or not the vkmql-* entrypoints have been wired yet.
PRIMARY_ENTRYPOINTS = ("vkmql-new", "vkmql-check", "vkmql-ship")
# Legacy fallback so the contract is never empty before the vkmql-* verbs land.
LEGACY_PRIMARY = ("mql5-init", "mql5-auto-build", "mql5-ship")

SUPPORTED_ENVIRONMENTS = ("linux", "windows")

# Release gate — mirrors the kit's hard rule: nothing is release-eligible
# without a signed evidence manifest produced from real tooling.
RELEASE_POLICY = {
    "requires_evidence_manifest": True,
    "evidence_manifest_path": EVIDENCE_MANIFEST,
    "release_eligible_field": "release_eligible",
    "accepted_compile_evidence": ["actual_metaeditor", "remote_worker_metaeditor"],
    "accepted_backtest_evidence": [
        "actual_mt5_strategy_tester",
        "remote_worker_strategy_tester",
    ],
    "rejected_evidence": [
        "stub",
        "imported_log",
        "sample_fixture",
        "manual_unverified",
        "unknown",
    ],
    "unsafe_flags": ["--draft", "--no-compile", "--no-gate", "--unsafe-allow-skips"],
}


def _entrypoints() -> dict:
    scripts = _load_pyproject_scripts()
    declared = set(scripts)
    primary = [n for n in PRIMARY_ENTRYPOINTS if n in declared]
    if not primary:
        primary = [n for n in LEGACY_PRIMARY if n in declared]
    return {
        "primary": primary,
        "count": len(declared),
        "catalog": TOOL_CATALOG,
    }


def _rule_namespaces() -> list[dict]:
    return [
        {"namespace": ns, "rule_count": len(rr.by_namespace(ns))}
        for ns in rr.NAMESPACES
    ]


def build_contract() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "mql5-agent-contract",
        "kit": {
            "name": KIT_NAME,
            "version": _version.get_version(),
            "flavor": kit_flavor(),
            "canonical_layout": CANONICAL_LAYOUT,
        },
        "entrypoints": _entrypoints(),
        "artifacts": {
            "tool_catalog": TOOL_CATALOG,
            "evidence_manifest": EVIDENCE_MANIFEST,
        },
        "release_policy": RELEASE_POLICY,
        "rule_namespaces": _rule_namespaces(),
        "environments": list(SUPPORTED_ENVIRONMENTS),
    }


def validate_contract(contract: dict) -> list[str]:
    """Return human-readable validation errors; empty list means consistent."""
    errors: list[str] = []
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version {contract.get('schema_version')!r} != {SCHEMA_VERSION!r}"
        )
    kit = contract.get("kit", {})
    canonical = _version.get_version()
    if kit.get("version") != canonical:
        errors.append(f"kit.version {kit.get('version')!r} != canonical {canonical!r}")
    if kit.get("canonical_layout") != CANONICAL_LAYOUT:
        errors.append(
            f"kit.canonical_layout {kit.get('canonical_layout')!r} != {CANONICAL_LAYOUT!r}"
        )
    if not contract.get("entrypoints", {}).get("primary"):
        errors.append("entrypoints.primary is empty")
    declared_ns = {n["namespace"] for n in contract.get("rule_namespaces", [])}
    if declared_ns != set(rr.NAMESPACES):
        errors.append(
            f"rule_namespaces {sorted(declared_ns)} != {sorted(rr.NAMESPACES)}"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mql5-agent-contract", description=__doc__.splitlines()[0]
    )
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--emit", action="store_true", help="Emit the agent contract JSON")
    grp.add_argument(
        "--validate",
        type=Path,
        default=None,
        help="Validate an existing agent-contract.json against the live kit",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the contract to this path (default: stdout)",
    )
    args = p.parse_args(argv)

    if args.emit:
        text = json.dumps(build_contract(), indent=2, sort_keys=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        return 0

    if args.validate:
        if not args.validate.exists():
            print(f"agent-contract not found: {args.validate}", file=sys.stderr)
            return 2
        contract = json.loads(args.validate.read_text(encoding="utf-8"))
        errors = validate_contract(contract)
        if errors:
            for err in errors:
                print(f"agent-contract:error: {err}", file=sys.stderr)
            return 1
        print(f"{args.validate}: ok")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
