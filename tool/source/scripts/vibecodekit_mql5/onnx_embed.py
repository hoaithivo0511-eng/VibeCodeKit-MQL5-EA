"""mql5-onnx-embed — inject `#resource "model.onnx"` + COnnxLoader hookup.

the kit spec §13 — ONNX deploy pipeline step 3:
    .pt/.pth → onnx_export.py → .onnx → onnx_embed.py → .mq5 references resource

The embed step is purely textual:

1. Verify the .mq5 source compiles before injection (caller's job).
2. Insert ``#resource "<model_name>.onnx"`` after the last ``#property``
   directive.
3. Insert ``#include "COnnxLoader.mqh"`` if not already present.
4. Insert a default ``COnnxLoader onnx;`` global + ``onnx.InitFromResource()``
   call inside ``OnInit()`` — only if no existing onnx instance is found.

The script is intentionally additive: it never deletes existing lines.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EmbedReport:
    ok: bool
    mq5_path: str
    model_name: str
    added_resource: bool
    added_include: bool
    added_init: bool
    notes: list[str]


def embed_onnx(
    mq5_path: Path, model_path: Path, in_place: bool = True
) -> EmbedReport:
    notes: list[str] = []
    if not mq5_path.exists():
        return EmbedReport(
            False, str(mq5_path), str(model_path), False, False, False,
            [f"missing .mq5: {mq5_path}"],
        )
    from .mq5_io import read_mq5_text_with_encoding

    try:
        src, _enc = read_mq5_text_with_encoding(mq5_path)
    except UnicodeDecodeError:
        src, _enc = mq5_path.read_text(encoding="latin-1", errors="replace"), "latin-1"
    model_name = model_path.name

    added_resource = False
    added_include = False
    added_init = False

    if f'#resource "{model_name}"' not in src:
        last_prop = list(re.finditer(r"^#property\s+.*$", src, re.MULTILINE))
        anchor_end = last_prop[-1].end() if last_prop else 0
        line = f'\n#resource "{model_name}"\n'
        src = src[:anchor_end] + line + src[anchor_end:]
        added_resource = True
    else:
        notes.append("resource already present")

    if '#include "COnnxLoader.mqh"' not in src:
        # add include after the resource line (or after #property if none yet)
        anchor = src.find(f'#resource "{model_name}"')
        anchor_end = src.find("\n", anchor) + 1 if anchor != -1 else 0
        src = src[:anchor_end] + '#include "COnnxLoader.mqh"\n' + src[anchor_end:]
        added_include = True

    if "COnnxLoader " not in src:
        # add global declaration before OnInit
        oninit = re.search(r"^(int\s+OnInit\s*\()", src, re.MULTILINE)
        if oninit:
            decl = "COnnxLoader onnx;\n\n"
            src = src[: oninit.start()] + decl + src[oninit.start() :]

    if "onnx.InitFromResource" not in src:
        # try to inject right after the opening brace of OnInit
        m = re.search(r"OnInit\s*\([^)]*\)\s*\{", src)
        if m:
            ins = m.end()
            init_call = (
                f'\n   if(!onnx.InitFromResource("{model_name}")) '
                f'return INIT_FAILED;\n'
            )
            src = src[:ins] + init_call + src[ins:]
            added_init = True
        else:
            notes.append("OnInit() not found; init not auto-injected")

    if in_place:
        backup = mq5_path.with_suffix(mq5_path.suffix + ".bak")
        if not backup.exists():
            shutil.copy(mq5_path, backup)
        mq5_path.write_text(src, encoding=_enc)
    else:
        sys.stdout.write(src)

    return EmbedReport(
        ok=True, mq5_path=str(mq5_path), model_name=model_name,
        added_resource=added_resource, added_include=added_include,
        added_init=added_init, notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-onnx-embed")
    parser.add_argument("mq5", help="Target .mq5 source")
    parser.add_argument("--model", required=True, help=".onnx file to embed")
    parser.add_argument("--stdout", action="store_true",
                        help="Print resulting .mq5 to stdout instead of writing")
    args = parser.parse_args(argv)
    rep = embed_onnx(Path(args.mq5), Path(args.model), in_place=not args.stdout)
    import json
    print(json.dumps(rep.__dict__, indent=2), file=sys.stderr)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
