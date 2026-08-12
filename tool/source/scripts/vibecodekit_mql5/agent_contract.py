"""mql5-agent-contract — emit the kit's machine-readable agent contract.

While ``tool-catalog.json`` is the flat list of CLI commands, the agent
contract is the higher-level handshake for external agents. It is generated
deterministically from the canonical package version and runtime policy.
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

PRIMARY_ENTRYPOINTS = ("vkmql-new", "vkmql-check", "vkmql-ship")
LEGACY_PRIMARY = ("mql5-init", "mql5-auto-build", "mql5-ship")
SUPPORTED_ENVIRONMENTS = ("linux", "windows")

RELEASE_POLICY = {
    "requires_evidence_manifest": True,
    "evidence_manifest_path": EVIDENCE_MANIFEST,
    "release_eligible_field": "release_eligible",
    "accepted_compile_evidence": [
        "actual_metaeditor",
        "remote_worker_metaeditor",
        "github_actions_metaeditor",
    ],
    "compile_evidence_conditions": {
        "github_actions_metaeditor": (
            "trusted only after exact Windows runner, repository, commit/tree, "
            "correlated workflow run/job, ProbeEA, 0-error/0-warning, EX5 and "
            "artifact hash/size provenance validation"
        ),
        "wine_metaeditor": "development/diagnostic only; not release authority",
    },
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
    primary = [name for name in PRIMARY_ENTRYPOINTS if name in declared]
    if not primary:
        primary = [name for name in LEGACY_PRIMARY if name in declared]
    return {"primary": primary, "count": len(declared), "catalog": TOOL_CATALOG}


def _rule_namespaces() -> list[dict]:
    return [
        {"namespace": namespace, "rule_count": len(rr.by_namespace(namespace))}
        for namespace in rr.NAMESPACES
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
    declared_ns = {item["namespace"] for item in contract.get("rule_namespaces", [])}
    if declared_ns != set(rr.NAMESPACES):
        errors.append(
            f"rule_namespaces {sorted(declared_ns)} != {sorted(rr.NAMESPACES)}"
        )
    accepted = set(contract.get("release_policy", {}).get("accepted_compile_evidence", []))
    if "github_actions_metaeditor" not in accepted:
        errors.append("release_policy does not declare provenance-gated github_actions_metaeditor")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mql5-agent-contract", description=__doc__.splitlines()[0]
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--emit", action="store_true", help="Emit the agent contract JSON")
    group.add_argument(
        "--validate",
        type=Path,
        default=None,
        help="Validate an existing agent-contract.json against the live kit",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the contract to this path (default: stdout)",
    )
    args = parser.parse_args(argv)

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
            for error in errors:
                print(f"agent-contract:error: {error}", file=sys.stderr)
            return 1
        print(f"{args.validate}: ok")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
