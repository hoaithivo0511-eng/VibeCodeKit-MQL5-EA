"""/mql5-install — reconcile-install kit overlay onto an existing project.

Copies the kit's ``Include/`` headers, scaffolds, and
canonical scripts into a target MQL5 project tree **without
overwriting existing files**.  Each file the user already has is
preserved; the kit-supplied version is written next to it as
``<name>.kit-template`` so the user can diff before promoting.

The intent is to make the kit installable into a brownfield project in
one shot — no merge conflicts, no destructive overwrites.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ._resources import asset_root, repo_root

REPO_ROOT = repo_root()

OVERLAY_DIRS = ["Include", "scaffolds"]


@dataclass
class InstallReport:
    target: str
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)


def install(target: Path, source: Path | None = None) -> InstallReport:
    rep = InstallReport(target=str(target))
    if not target.exists():
        target.mkdir(parents=True)
    for od in OVERLAY_DIRS:
        # Resolve each overlay group from the packaged resources (wheel-safe)
        # unless an explicit source root is provided (dev/testing).
        src_dir = (Path(source) / od) if source is not None else asset_root(od)
        if not src_dir.exists():
            continue
        for src in src_dir.rglob("*"):
            if src.is_dir():
                continue
            rel = Path(od) / src.relative_to(src_dir)
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Use POSIX-style separators in the report so JSON output and
            # downstream string matches are platform-stable (Windows would
            # otherwise emit `Include\\CPipNormalizer.mqh`).
            if dst.exists():
                tmpl = dst.with_suffix(dst.suffix + ".kit-template")
                shutil.copyfile(src, tmpl)
                rep.templates.append(tmpl.relative_to(target).as_posix())
                rep.skipped.append(rel.as_posix())
            else:
                shutil.copyfile(src, dst)
                rep.written.append(rel.as_posix())
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-install")
    parser.add_argument("target", help="Existing MQL5 project root")
    parser.add_argument("--source", default=None,
                        help="Override asset source root (defaults to packaged resources)")
    args = parser.parse_args(argv)
    rep = install(Path(args.target), Path(args.source) if args.source else None)
    print(json.dumps({
        "target": rep.target,
        "written": rep.written,
        "skipped": rep.skipped,
        "templates": rep.templates,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
