"""Existing EA intake.

Accepts a single .mq5 file, an existing project directory, or a .zip codebase
and normalizes it into a review workspace:

ReviewProject/
  Experts/<name>.mq5
  Include/...
  original/
  intake-report.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from ._safe_archive import safe_extract


def safe_name(name: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name.strip())
    return out or "ExistingEA"


def copy_tree_filtered(src: Path, dst: Path) -> None:
    for p in src.rglob("*"):
        if p.is_file():
            if any(part in {".git", "__pycache__", ".venv", "build", "dist"} for part in p.parts):
                continue
            rel = p.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)


def find_main_mq5(root: Path) -> Path | None:
    experts = sorted((root / "Experts").glob("*.mq5")) if (root / "Experts").exists() else []
    if experts:
        return experts[0]
    mq5 = sorted(root.rglob("*.mq5"))
    return mq5[0] if mq5 else None


def intake_source(source: str | Path, out_dir: str | Path, name: str | None = None) -> dict[str, Any]:
    src = Path(source)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    project_name = safe_name(name or src.stem)
    project = out / project_name
    if project.exists():
        shutil.rmtree(project)
    project.mkdir(parents=True)

    original = project / "original"
    original.mkdir()

    source_kind = "unknown"
    extracted_root = original

    if src.is_file() and src.suffix.lower() == ".mq5":
        source_kind = "single_mq5"
        (project / "Experts").mkdir()
        shutil.copy2(src, project / "Experts" / f"{project_name}.mq5")
        shutil.copy2(src, original / src.name)
    elif src.is_file() and src.suffix.lower() == ".zip":
        source_kind = "zip"
        with zipfile.ZipFile(src) as z:
            safe_extract(z, original)
        # If zip contains a single top folder, use it as source root.
        children = [p for p in original.iterdir()]
        extracted_root = children[0] if len(children) == 1 and children[0].is_dir() else original
        main = find_main_mq5(extracted_root)
        if main is None:
            raise FileNotFoundError("No .mq5 file found inside zip")
        # Normalize while preserving Include if present.
        (project / "Experts").mkdir(exist_ok=True)
        shutil.copy2(main, project / "Experts" / f"{project_name}.mq5")
        inc = extracted_root / "Include"
        if inc.exists():
            copy_tree_filtered(inc, project / "Include")
        # Also copy any sibling .mqh folders preserving relative structure.
        for mqh in extracted_root.rglob("*.mqh"):
            rel = mqh.relative_to(extracted_root)
            if rel.parts and rel.parts[0] == "Include":
                continue
            target = project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mqh, target)
    elif src.is_dir():
        source_kind = "directory"
        copy_tree_filtered(src, original)
        main = find_main_mq5(src)
        if main is None:
            raise FileNotFoundError("No .mq5 file found inside directory")
        # If already project-like, copy relevant structure.
        if (src / "Experts").exists():
            copy_tree_filtered(src / "Experts", project / "Experts")
        else:
            (project / "Experts").mkdir(exist_ok=True)
            shutil.copy2(main, project / "Experts" / f"{project_name}.mq5")
        if (src / "Include").exists():
            copy_tree_filtered(src / "Include", project / "Include")
        for mqh in src.rglob("*.mqh"):
            try:
                rel = mqh.relative_to(src)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] == "Include":
                continue
            target = project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mqh, target)
    else:
        raise FileNotFoundError(f"Unsupported source: {src}")

    normalized_main = find_main_mq5(project)
    report = {
        "ok": True,
        "source": str(src),
        "source_kind": source_kind,
        "project": str(project),
        "name": project_name,
        "main_ea": str(normalized_main) if normalized_main else None,
        "mql_files": sorted(str(p.relative_to(project)) for p in project.rglob("*") if p.suffix.lower() in {".mq5", ".mqh"}),
    }
    (project / "intake-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize existing EA source into review workspace.")
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name")
    args = ap.parse_args(argv)
    report = intake_source(args.source, args.out_dir, args.name)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
