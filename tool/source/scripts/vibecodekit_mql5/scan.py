"""/mql5-scan — survey a project tree for MQL5 sources + classify.

``scan`` walks a directory, identifies ``.mq5`` /
``.mqh`` / ``.set`` / ``.ex5`` artefacts, and emits a concise JSON
report (path, kind, size).  No mutation, no compilation — just a
"what's here?" question answered.  Often the first command users run
after `/mql5-doctor`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

KIND_BY_EXT = {
    ".mq5":  "ea-source",
    ".mqh":  "include",
    ".set":  "tester-set",
    ".ex5":  "compiled",
    ".onnx": "onnx-model",
}


@dataclass
class ScanReport:
    root: str
    files: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def scan_tree(root: Path) -> ScanReport:
    # PR-21: single-file mode. If ``root`` points at one classified
    # source file (``.mq5`` / ``.mqh`` / ``.set`` / ``.ex5`` /
    # ``.onnx``), treat it as a 1-entry inventory. Previously the
    # function only worked on directories and silently returned
    # ``{files: [], counts: {}}`` for single files because
    # ``Path.rglob`` on a file yields nothing — that misled callers
    # who passed e.g. ``"My EA.mq5"`` straight from a download.
    #
    # The report's ``root`` is normalized to the parent directory so
    # the standard chain pattern ``Path(root) / files[i].path`` keeps
    # working in both modes.
    if root.exists() and root.is_file():
        rep = ScanReport(root=str(root.parent))
        kind = KIND_BY_EXT.get(root.suffix.lower())
        if kind is None:
            return rep
        rep.files.append({
            "path": root.name,
            "kind": kind,
            "size": root.stat().st_size,
        })
        rep.counts = {kind: 1}
        return rep

    rep = ScanReport(root=str(root))
    if not root.exists():
        return rep
    counts: dict[str, int] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        kind = KIND_BY_EXT.get(p.suffix.lower())
        if kind is None:
            continue
        rep.files.append({
            "path": str(p.relative_to(root)),
            "kind": kind,
            "size": p.stat().st_size,
        })
        counts[kind] = counts.get(kind, 0) + 1
    rep.counts = counts
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-scan")
    parser.add_argument("root", help="Project root to scan")
    args = parser.parse_args(argv)
    rep = scan_tree(Path(args.root))
    print(json.dumps({"root": rep.root, "files": rep.files, "counts": rep.counts}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
