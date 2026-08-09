"""Export the toy LSTM (train.py output) to ONNX.

Thin wrapper around ``vibecodekit_mql5.onnx_export.export_torch`` so the
scaffold has a self-contained entry point.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from vibecodekit_mql5.onnx_export import export_torch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="export_onnx.py")
    parser.add_argument("--model", default="model.pt")
    parser.add_argument("--out", default="model.onnx")
    parser.add_argument("--opset", type=int, default=14)
    parser.add_argument("--seq-len", type=int, default=10)
    args = parser.parse_args(argv)

    rep = export_torch(
        Path(args.model), Path(args.out), opset=args.opset,
        input_shape=(1, args.seq_len, 1),
    )
    print(rep.as_json())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
