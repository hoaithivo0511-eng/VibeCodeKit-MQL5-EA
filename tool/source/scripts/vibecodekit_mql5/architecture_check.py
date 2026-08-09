"""Architecture compliance checker for profile-driven EA generation.

This checker is intentionally static and conservative. It prevents a profile
such as grid-safe from passing when required execution/risk modules are missing.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


from ._resources import asset_root

DEFAULT_PROFILE_DIR = asset_root("profiles")


def load_profile(profile: str, profile_dir: str | Path | None = None) -> dict[str, Any]:
    pdir = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
    path = pdir / f"{profile}.json"
    if not path.is_file():
        raise FileNotFoundError(f"profile manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def available_profiles(profile_dir: str | Path | None = None) -> list[str]:
    """Return the sorted profile names discoverable as ``<name>.json``."""
    pdir = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
    if not pdir.is_dir():
        return []
    return sorted(p.stem for p in pdir.glob("*.json"))


def read_project_text(project: str | Path) -> tuple[str, list[str]]:
    root = Path(project)
    files = []
    chunks = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".mq5", ".mqh"}:
            rel = p.relative_to(root).as_posix()
            files.append(rel)
            chunks.append(f"\n// FILE: {rel}\n" + p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks), files


def check_architecture(project: str | Path, profile: str, profile_dir: str | Path | None = None) -> dict[str, Any]:
    manifest = load_profile(profile, profile_dir)
    text, files = read_project_text(project)

    missing_modules = []
    for module in manifest.get("required_modules", []):
        if module not in text and not any(module in f for f in files):
            missing_modules.append(module)

    missing_hooks = []
    for hook in manifest.get("required_hooks", []):
        if hook not in text:
            missing_hooks.append(hook)

    missing_terms = []
    for term in manifest.get("required_terms", []):
        if re.search(re.escape(term), text, flags=re.I) is None:
            missing_terms.append(term)

    # Raw CTrade is allowed inside the dedicated AsyncTradeExecutor module.
    main_text_chunks = []
    for rel in files:
        if rel.endswith(".mq5") or ("AsyncTradeExecutor" not in rel and "BasketCloseEngine" not in rel):
            # text already includes FILE markers; keep overall scan for loop-close pattern,
            # but handle sync_trade_without_async_executor semantically below.
            pass

    forbidden_hits = []
    has_async_executor = "CAsyncTradeExecutor" in text and "OnTradeTransaction" in text
    for item in manifest.get("forbidden_patterns", []):
        pattern = item["regex"] if isinstance(item, dict) else str(item)
        item_id = item.get("id", pattern) if isinstance(item, dict) else pattern
        if item_id == "sync_trade_without_async_executor":
            if (not has_async_executor) and re.search(pattern, text, flags=re.I | re.M):
                forbidden_hits.append({
                    "id": item_id,
                    "description": item.get("description", "") if isinstance(item, dict) else "",
                })
            continue
        if re.search(pattern, text, flags=re.I | re.M):
            forbidden_hits.append({
                "id": item_id,
                "description": item.get("description", "") if isinstance(item, dict) else "",
            })

    ok = not missing_modules and not missing_hooks and not forbidden_hits and not missing_terms
    return {
        "schema_version": "1.0",
        "profile": profile,
        "ok": ok,
        "release_blocking": not ok,
        "missing_required_modules": missing_modules,
        "missing_hooks": missing_hooks,
        "missing_required_terms": missing_terms,
        "forbidden_patterns": forbidden_hits,
        "files_scanned": files,
        "policy": "Profile architecture compliance is required before release evidence can be trusted.",
    }


def _emit(report: dict[str, Any], out: str | None) -> None:
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    _packaged = available_profiles()
    ap = argparse.ArgumentParser(description="Check EA architecture against profile capability manifest.")
    # --project is validated manually (not argparse-required) so --list-profiles
    # works on its own and so unknown/missing profiles return structured JSON
    # rather than argparse's plain-text exit.
    ap.add_argument("--project")
    ap.add_argument(
        "--profile", default="grid-safe",
        help="Capability profile name. Packaged profiles: " + ", ".join(_packaged),
    )
    ap.add_argument("--profile-dir", help="Directory of <profile>.json manifests (default: packaged profiles).")
    ap.add_argument("--out")
    ap.add_argument(
        "--list-profiles", action="store_true",
        help="List available profile manifests as JSON and exit 0.",
    )
    args = ap.parse_args(argv)

    if args.list_profiles:
        pdir = Path(args.profile_dir) if args.profile_dir else DEFAULT_PROFILE_DIR
        _emit({
            "schema_version": "1.0",
            "ok": True,
            "profiles": available_profiles(args.profile_dir),
            "profile_dir": str(pdir),
        }, args.out)
        return 0

    if not args.project:
        _emit({
            "schema_version": "1.0",
            "ok": False,
            "release_blocking": True,
            "error": "--project is required (or pass --list-profiles)",
            "available_profiles": available_profiles(args.profile_dir),
        }, args.out)
        return 2

    try:
        report = check_architecture(args.project, args.profile, args.profile_dir)
    except FileNotFoundError as exc:
        _emit({
            "schema_version": "1.0",
            "ok": False,
            "release_blocking": True,
            "profile": args.profile,
            "error": str(exc),
            "available_profiles": available_profiles(args.profile_dir),
            "policy": "Unknown or missing profile manifest; architecture cannot be validated, so release is blocked.",
        }, args.out)
        return 2

    _emit(report, args.out)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
