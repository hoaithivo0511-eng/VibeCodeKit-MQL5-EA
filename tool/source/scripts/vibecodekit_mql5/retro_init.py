"""Create a conservative Retro evidence skeleton for a project."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import retro_guards


def initialize(project_dir: Path | str, *, force: bool = False) -> Path:
    project_dir = Path(project_dir)
    target = project_dir / "evidence" / "retro" / "guards.yaml"
    if target.exists() and not force:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    selected = retro_guards.catalog()
    contract = project_dir / "AI-BUILD-CONTRACT.json"
    if contract.is_file():
        try:
            data = json.loads(contract.read_text(encoding="utf-8"))
            declared = data.get("behavioral_guards")
            if isinstance(declared, list) and declared:
                selected = [g for g in declared if isinstance(g, dict)]
        except Exception:  # leave full conservative catalog on invalid contract
            pass
    for guard in selected:
        records.append({
            "id": guard["id"],
            "canonical_id": guard["canonical_id"],
            "status": "UNTESTABLE",
            "checker": guard["checker"],
            "checker_result": {
                "status": "UNTESTABLE",
                "findings": ["replace with checker output after attaching evidence"],
            },
            "artifacts": [],
        })
    import yaml  # type: ignore
    target.write_text(yaml.safe_dump({"schema_version": "1.1", "guards": records}, sort_keys=False), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mql5-retro-init")
    ap.add_argument("project_dir", type=Path)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    try:
        path = initialize(args.project_dir, force=args.force)
    except FileExistsError as exc:
        print(json.dumps({"ok": False, "error": f"already exists: {exc}"}))
        return 1
    import yaml  # type: ignore
    count = len((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("guards", []))
    print(json.dumps({"ok": True, "path": path.as_posix(), "guards": count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
