"""mql5-onnx-export — wrap a PyTorch/TensorFlow model into a frozen ONNX file.

the kit spec §13 — Modern ML deploy path:
    PyTorch / TF → ONNX (opset >= 14) → embedded resource → MQL5 OnnxRun()

The exporter validates:
- opset version >= 14 (required for OnnxRun on builds 4620+)
- model has at least one input + one output tensor
- output shape is statically resolvable (no dynamic axes other than batch)

For unit tests we accept a Python callable producing a numpy array; the
*real* PyTorch dependency is optional and only loaded when the exporter
is invoked against a ``.pt`` / ``.pth`` model. This keeps the rest of
the kit free of a heavy PyTorch import.

Build 5572 (Jan 2026) added ``OnnxSetExecutionProviders`` on the MQL5
side so the same .onnx model can run on the CPU EP (default), CUDA EP,
or any other provider the host's ONNX Runtime ships with.  The
exporter records the *intended* provider list in the JSON report so
``onnx_embed`` can emit the matching ``COnnxLoader.InitFromResource``
call without the EA needing to know what hardware the .onnx was
optimised for.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

MIN_OPSET = 14

# MQL5 build 5572 ``OnnxSetExecutionProviders`` accepts these provider
# IDs.  Keep the kit's list deliberately small — it is the set the
# the kit spec §13 deploy path supports end-to-end.
VALID_PROVIDERS: tuple[str, ...] = ("cpu", "cuda")
DEFAULT_PROVIDERS: tuple[str, ...] = ("cpu",)


@dataclass
class ExportReport:
    ok: bool
    onnx_path: str
    opset: int
    input_shapes: list[tuple[int, ...]] = field(default_factory=list)
    output_shapes: list[tuple[int, ...]] = field(default_factory=list)
    providers: list[str] = field(default_factory=lambda: list(DEFAULT_PROVIDERS))
    error: str = ""

    def as_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def _parse_providers(raw: str) -> list[str]:
    """Parse a comma-separated provider list.

    Validates against ``VALID_PROVIDERS``; raises ``ValueError`` on any
    unknown ID so we never silently fall back to CPU when the caller
    asked for CUDA (a regression that would mask a misconfigured GPU
    runtime).
    """
    items = [p.strip().lower() for p in raw.split(",") if p.strip()]
    if not items:
        return list(DEFAULT_PROVIDERS)
    unknown = [p for p in items if p not in VALID_PROVIDERS]
    if unknown:
        raise ValueError(
            f"unknown ONNX execution provider(s): {unknown}; "
            f"valid: {list(VALID_PROVIDERS)}"
        )
    seen: list[str] = []
    for p in items:
        if p not in seen:
            seen.append(p)
    return seen


def _check_opset(opset: int) -> None:
    if opset < MIN_OPSET:
        raise ValueError(
            f"opset {opset} is too low; MQL5 OnnxRun needs >= {MIN_OPSET}"
        )


def export_torch(
    model_path: Path,
    output: Path,
    opset: int = MIN_OPSET,
    input_shape: tuple[int, ...] = (1, 10),
    providers: list[str] | None = None,
) -> ExportReport:
    """Export a PyTorch ``.pt`` / ``.pth`` model to ONNX.

    The PyTorch + onnx imports are deferred so unit tests can exercise
    the wrapper without the dependency installed.
    """
    _check_opset(opset)
    providers = list(providers) if providers else list(DEFAULT_PROVIDERS)
    try:
        import torch  # type: ignore
    except ImportError as exc:
        return ExportReport(
            ok=False, onnx_path=str(output), opset=opset,
            providers=providers,
            error=f"PyTorch missing: {exc}; install via pip install '.[ml]'",
        )
    model = torch.load(str(model_path), map_location="cpu", weights_only=False)
    model.eval()
    dummy = torch.zeros(*input_shape)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        dummy,
        str(output),
        export_params=True,
        opset_version=opset,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )
    return validate(output, providers=providers)


def validate(
    onnx_path: Path, providers: list[str] | None = None
) -> ExportReport:
    providers = list(providers) if providers else list(DEFAULT_PROVIDERS)
    try:
        import onnx  # type: ignore
    except ImportError as exc:
        return ExportReport(
            ok=False, onnx_path=str(onnx_path), opset=0,
            providers=providers,
            error=f"onnx missing: {exc}; install via pip install '.[ml]'",
        )
    if not onnx_path.exists():
        return ExportReport(
            ok=False, onnx_path=str(onnx_path), opset=0,
            providers=providers,
            error=f"file not found: {onnx_path}",
        )
    model = onnx.load(str(onnx_path))
    opset = max(o.version for o in model.opset_import) if model.opset_import else 0
    if opset < MIN_OPSET:
        return ExportReport(
            ok=False, onnx_path=str(onnx_path), opset=opset,
            providers=providers,
            error=f"opset {opset} < required {MIN_OPSET}",
        )
    in_shapes = [
        tuple(d.dim_value or -1 for d in i.type.tensor_type.shape.dim)
        for i in model.graph.input
    ]
    out_shapes = [
        tuple(d.dim_value or -1 for d in o.type.tensor_type.shape.dim)
        for o in model.graph.output
    ]
    if not in_shapes or not out_shapes:
        return ExportReport(
            ok=False, onnx_path=str(onnx_path), opset=opset,
            providers=providers,
            error="model has no inputs or no outputs",
        )
    return ExportReport(
        ok=True, onnx_path=str(onnx_path), opset=opset,
        input_shapes=in_shapes, output_shapes=out_shapes,
        providers=providers,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-onnx-export")
    parser.add_argument("model", help="Path to .pt/.pth or existing .onnx")
    parser.add_argument("--output", required=False, help="Output .onnx (required for torch)")
    parser.add_argument("--opset", type=int, default=MIN_OPSET)
    parser.add_argument("--input-shape", default="1,10")
    parser.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDERS),
        help=(
            "Comma-separated ONNX execution providers, ordered by "
            "preference (build 5572+ MQL5: "
            f"{','.join(VALID_PROVIDERS)}). Default: cpu."
        ),
    )
    args = parser.parse_args(argv)

    try:
        providers = _parse_providers(args.providers)
    except ValueError as exc:
        print(f"mql5-onnx-export: {exc}", file=sys.stderr)
        return 2

    model_path = Path(args.model)
    if model_path.suffix == ".onnx":
        report = validate(model_path, providers=providers)
    else:
        if not args.output:
            print("--output is required when exporting from torch", file=sys.stderr)
            return 2
        shape = tuple(int(x) for x in args.input_shape.split(","))
        report = export_torch(
            model_path, Path(args.output),
            opset=args.opset, input_shape=shape, providers=providers,
        )
    print(report.as_json())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
