"""Toy LSTM training on synthetic EURUSD M1 returns.

This is intentionally tiny so the end-to-end ONNX pipeline finishes in
< 5 minutes on the Devin VM. Real users replace this with their data
loader + model.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

try:
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyTorch missing; install via `pip install '.[ml]'`"
    ) from exc


class ToyLSTM(nn.Module):
    """Single-feature LSTM that predicts a 3-class trend signal."""

    def __init__(self, input_size: int = 1, hidden: int = 16, classes: int = 3) -> None:
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden, batch_first=True)
        self.head = nn.Linear(hidden, classes)

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])


def _make_data(n: int, seq_len: int = 10) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed=42)
    x = rng.normal(loc=0.0, scale=1e-4, size=(n, seq_len, 1)).astype(np.float32)
    # synthetic label: positive cumulative return → BUY (2), negative → SELL (0)
    cum = x.sum(axis=(1, 2))
    y = np.where(cum > 1e-4, 2, np.where(cum < -1e-4, 0, 1)).astype(np.int64)
    return x, y


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="train.py")
    parser.add_argument("--out", default="model.pt", help="Output state-dict path")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--samples", type=int, default=512)
    args = parser.parse_args(argv)

    torch.manual_seed(0)
    x, y = _make_data(args.samples)
    x_t = torch.from_numpy(x)
    y_t = torch.from_numpy(y)

    model = ToyLSTM()
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    loss_fn = nn.CrossEntropyLoss()
    for ep in range(args.epochs):
        opt.zero_grad()
        logits = model(x_t)
        loss = loss_fn(logits, y_t)
        loss.backward()
        opt.step()
        print(f"epoch {ep + 1}/{args.epochs} loss={loss.item():.4f}")

    out = Path(args.out)
    torch.save(model, out)  # save full module so export_onnx can use it
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
