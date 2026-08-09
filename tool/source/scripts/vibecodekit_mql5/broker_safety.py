"""mql5-broker-safety — standalone Layer-7 (broker-safety) checks.

the kit spec §12 lists a 7-layer permission engine; the 7th layer is broker
safety, implemented as a standalone module so it can be
called from CI as a final pre-deploy gate (without needing the full
permission engine).

Checks performed:
    1. fill_policy_supported  — FOK/IOC/RETURN matches symbol.execution_mode
    2. min_lot_respected      — InpLot >= SYMBOL_VOLUME_MIN
    3. lot_step_aligned       — InpLot is a multiple of SYMBOL_VOLUME_STEP
    4. magic_in_range         — the kit spec reserves 70000-79999

This module is text-static (does not contact a broker); it operates on a
.mq5 file plus a sidecar JSON that describes the broker symbol contract.

CLI:
    python -m vibecodekit_mql5.broker_safety <ea.mq5> <symbol.json>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# the kit spec §6 reserves 70000-79999 for kit-generated EAs.
MAGIC_LOW, MAGIC_HIGH = 70000, 79999


@dataclass
class BrokerSafetyResult:
    fill_policy_supported: str
    min_lot_respected: str
    lot_step_aligned: str
    magic_in_range: str
    notes: list[str]

    def to_dict(self) -> dict:
        return self.__dict__

    @property
    def all_pass(self) -> bool:
        return all(v == "PASS" for k, v in self.__dict__.items() if k != "notes")


_LOT_RX = re.compile(r"InpLot\w*\s*=\s*(?P<v>\d+(?:\.\d+)?)", re.IGNORECASE)
_MAGIC_RX = re.compile(r"InpMagic\s*=\s*(?P<v>\d+)", re.IGNORECASE)
_FILL_RX = re.compile(r"\bORDER_FILLING_(?P<v>FOK|IOC|RETURN)\b")


def _first(rx: re.Pattern[str], text: str, default: str | None = None) -> str | None:
    m = rx.search(text)
    return m.group("v") if m else default


def evaluate(ea_text: str, symbol_info: dict) -> BrokerSafetyResult:
    notes: list[str] = []

    fill_decl = _first(_FILL_RX, ea_text)
    fill_supported = symbol_info.get("filling_modes", [])
    fp = "PASS"
    if fill_decl is None:
        fp = "WARN"
        notes.append("no ORDER_FILLING_* declared")
    elif fill_decl not in fill_supported:
        fp = "FAIL"
        notes.append(f"ORDER_FILLING_{fill_decl} not in {fill_supported}")

    lot_str = _first(_LOT_RX, ea_text)
    min_lot = float(symbol_info.get("volume_min", 0.01))
    step = float(symbol_info.get("volume_step", 0.01))
    ml = "PASS"
    ls = "PASS"
    if lot_str is None:
        ml = ls = "WARN"
        notes.append("no InpLot found")
    else:
        lot = float(lot_str)
        if lot < min_lot:
            ml = "FAIL"
            notes.append(f"InpLot {lot} < volume_min {min_lot}")
        if step > 0:
            ratio = round(lot / step, 6)
            if abs(ratio - round(ratio)) > 1e-6:
                ls = "FAIL"
                notes.append(f"InpLot {lot} not aligned to volume_step {step}")

    magic_str = _first(_MAGIC_RX, ea_text)
    mr = "PASS"
    if magic_str is None:
        mr = "WARN"
        notes.append("no InpMagic found")
    else:
        m = int(magic_str)
        if not (MAGIC_LOW <= m <= MAGIC_HIGH):
            mr = "FAIL"
            notes.append(f"InpMagic {m} outside reserved {MAGIC_LOW}-{MAGIC_HIGH}")

    return BrokerSafetyResult(
        fill_policy_supported=fp,
        min_lot_respected=ml,
        lot_step_aligned=ls,
        magic_in_range=mr,
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    p = argparse.ArgumentParser(prog="mql5-broker-safety", description=__doc__.splitlines()[0])
    p.add_argument("ea")
    p.add_argument("symbol_json")
    _agent_io.add_json_flag(p)
    _agent_io.add_gate_report_flag(p)
    args = p.parse_args(argv)

    from .mq5_io import read_mq5_text

    ea_text = read_mq5_text(args.ea, errors="replace")
    sym = json.loads(Path(args.symbol_json).read_text(encoding="utf-8"))
    result = evaluate(ea_text, sym)

    envelope = _agent_io.Envelope(
        tool="mql5-broker-safety",
        ok=result.all_pass,
        exit_code=0 if result.all_pass else 1,
        summary=("4/4 broker-safety checks PASS" if result.all_pass
                 else f"broker-safety FAIL ({len(result.notes)} note(s))"),
        data=result.to_dict(),
        evidence=[args.ea, args.symbol_json],
        matrix_dim="d_broker_safety",
        matrix_axis="multi_broker",
        matrix_status="PASS" if result.all_pass else "FAIL",
    )

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        print(json.dumps(result.to_dict(), indent=2))

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return 0 if result.all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
