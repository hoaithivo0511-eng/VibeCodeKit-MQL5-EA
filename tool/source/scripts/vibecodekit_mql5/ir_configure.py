"""Apply an explicit operator profile to a canonical EA-IR.

The document compiler extracts *capabilities* and preserves ambiguities.  A
manual is not a trading configuration, so operational values must come from a
separate, reviewable profile.  This module performs a provenance-preserving
deep merge and emits a new canonical hash; it never edits source documents or
silently invents values.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from .ea_ir import EAIR, Requirement, SourceRef, from_dict
from .safe_paths import validate_ea_name

PROFILE_SCHEMA_VERSION = "1"
_ALLOWED_ROOTS = {"identity", "runtime", "strategy", "risk", "controls", "metadata"}
# Mappings whose keys are complete operator-defined contracts, not partial
# configuration fragments. Merging these with extracted maps can create duplicate
# commands or stale policies, so an explicit profile replaces them atomically.
_ATOMIC_MAPPING_PATHS = {
    "controls.pending_command_ownership",
    "controls.pending_commands",
    "runtime.time_policy",
}


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        import yaml
        raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise TypeError("profile root must be a mapping")
    return raw


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if path in _ATOMIC_MAPPING_PATHS:
            out[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value, prefix=path)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _leaf_items(value: Any, prefix: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _leaf_items(child, path)
        return
    yield prefix, value


def apply_profile(ir: EAIR, profile: dict[str, Any], *, source: str = "profile") -> EAIR:
    version = str(profile.get("schema_version", ""))
    if version != PROFILE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported profile schema_version={version!r}; expected {PROFILE_SCHEMA_VERSION!r}"
        )
    overrides = profile.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise TypeError("profile overrides must be a mapping")
    unknown = sorted(set(overrides) - _ALLOWED_ROOTS)
    if unknown:
        raise ValueError(f"unsupported profile override roots: {', '.join(unknown)}")

    raw = ir.to_dict(include_hash=False)
    for root, values in overrides.items():
        if not isinstance(values, dict):
            raise TypeError(f"profile overrides.{root} must be a mapping")
        raw[root] = _deep_merge(dict(raw.get(root) or {}), values, prefix=root)

    name = str((raw.get("identity") or {}).get("name") or "")
    validate_ea_name(name)

    resolved_ids = set(profile.get("resolve_ambiguities") or [])
    raw["ambiguities"] = [a for a in raw.get("ambiguities", []) if a.get("id") not in resolved_ids]
    resolved_conflicts = set(profile.get("resolve_conflicts") or [])
    raw["conflicts"] = [c for c in raw.get("conflicts", []) if c.get("id") not in resolved_conflicts]

    profile_name = str(profile.get("profile_name") or Path(source).stem)
    assumptions = profile.get("assumptions") or []
    if not isinstance(assumptions, list):
        raise TypeError("profile assumptions must be a list")
    metadata = dict(raw.get("metadata") or {})
    metadata.update({
        "configuration_profile": profile_name,
        "configuration_profile_source": source,
        "configuration_profile_schema": PROFILE_SCHEMA_VERSION,
        "configuration_assumptions": copy.deepcopy(assumptions),
        "defaults_policy": "reject",
    })
    raw["metadata"] = metadata

    # Profile values are first-class requirements with provenance.  Replace an
    # extracted requirement at the exact path so traceability stays one-to-one.
    existing = [r for r in ir.requirements]
    leafs: list[tuple[str, Any]] = []
    for root, values in overrides.items():
        if root == "metadata":
            continue
        leafs.extend((f"{root}.{path}", value) for path, value in _leaf_items(values) if path)
    leaf_paths = {path for path, _ in leafs}
    atomic_replaced: set[str] = set()
    for atomic_path in _ATOMIC_MAPPING_PATHS:
        root, _, child = atomic_path.partition(".")
        root_values = overrides.get(root)
        if isinstance(root_values, dict) and child in root_values:
            atomic_replaced.add(atomic_path)
    requirements = [
        r for r in existing
        if r.path not in leaf_paths
        and not any(r.path == prefix or r.path.startswith(prefix + ".") for prefix in atomic_replaced)
    ]
    next_index = len(requirements) + 1
    for offset, (path, value) in enumerate(leafs):
        requirements.append(Requirement(
            id=f"CFG-{next_index + offset:04d}",
            path=path,
            value=value,
            confidence=1.0,
            status="confirmed",
            priority="must",
            source_refs=[SourceRef(source=source, evidence=f"{path}={value!r}")],
        ))
    raw["requirements"] = [r.to_dict() for r in requirements]
    raw["schema_version"] = ir.schema_version
    return from_dict(raw)


def run(ir_path: Path, profile_path: Path, out_path: Path) -> EAIR:
    ir = from_dict(json.loads(ir_path.read_text(encoding="utf-8")))
    profile = _load_mapping(profile_path)
    configured = apply_profile(ir, profile, source=str(profile_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(configured.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return configured


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-ir-configure", description=__doc__.splitlines()[0])
    ap.add_argument("--ir", required=True, type=Path)
    ap.add_argument("--profile", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        configured = run(args.ir, args.profile, args.out)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"mql5-ir-configure: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "ok": configured.ready_for_planning,
        "ir_sha256": configured.sha256(),
        "out": str(args.out),
        "blocking_issues": configured.blocking_issues,
    }, ensure_ascii=False, indent=2))
    return 0 if configured.ready_for_planning else 1


if __name__ == "__main__":
    raise SystemExit(main())
