"""XML report parser for ``mql5-optimize-run``.

Split out from :mod:`optimize_run` so that the orchestrator module
stays under the per-module LOC ceiling. All public
symbols — :class:`OptResult`, :func:`parse_opt_xml`,
:func:`parse_opt_xml_file` — are re-exported from ``optimize_run``
via a thin import alias, so existing callers keep working unchanged.

MT5 writes optimization reports as a Microsoft Excel 2003
SpreadsheetML workbook (``.xml``). Each ``Row`` after the header is
one parameter combination; the header columns are a mix of known
metric labels (``Profit``, ``Sharpe Ratio``, …) and EA-input names.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


__all__ = [
    "OptResult",
    "parse_opt_xml",
    "parse_opt_xml_file",
]


# Columns the optimizer always emits — anything else is an EA input.
_KNOWN_METRIC_COLUMNS: frozenset[str] = frozenset({
    "Pass", "Result", "Profit", "Expected Payoff", "Profit Factor",
    "Recovery Factor", "Sharpe Ratio", "Custom", "Equity DD %",
    "Trades",
})


@dataclass
class OptResult:
    """One row of the optimization report.

    ``params`` are the values of every optimized input. ``metrics``
    captures the rest of the columns (Profit, Sharpe Ratio, Trades, …).
    ``pass_num`` is the row's ``Pass`` column when present, else its
    1-based index inside the report.
    """
    pass_num: int
    params: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "pass": self.pass_num,
            "params": dict(self.params),
            "metrics": {k: round(v, 6) for k, v in self.metrics.items()},
        }


def _strip_ns(tag: str) -> str:
    """Drop the SpreadsheetML namespace prefix so XPath stays sane."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _decode_optimize_xml(raw: bytes) -> str:
    """Permissive decoder mirroring ``backtest._decode``.

    MT5 writes optimization reports as UTF-16-LE w/ BOM under Wine; the
    test fixtures we ship use UTF-8 for diff-friendliness.
    """
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw[:64].count(b"\x00") >= 16:
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


# Matches a bare ``&`` that is NOT already a valid XML entity. MT5 broker /
# symbol names with unescaped ampersands otherwise crash ``ET.fromstring``.
_BARE_AMP_RX = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9A-Fa-f]+);)")


def _xml_from_string(text: str) -> "ET.Element":
    """Parse XML, repairing bare ampersands MT5 emits; on persistent
    failure raise a clear ``ValueError`` instead of a raw ``ParseError``."""
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        repaired = _BARE_AMP_RX.sub("&amp;", text)
        try:
            return ET.fromstring(repaired)
        except ET.ParseError as exc:
            raise ValueError(f"malformed optimization XML: {exc}") from exc


def parse_opt_xml(text: str) -> list[OptResult]:
    """Parse a SpreadsheetML optimization report into ``OptResult``s.

    Tolerates two minor MT5 quirks:

    * an ``encoding="UTF-16"`` declaration on a text string ElementTree
      already decoded (we rewrite it to UTF-8);
    * empty ``<Cell/>`` elements that should keep the column position.
      MT5 uses ``ss:Index`` on the next non-empty cell instead of an
      empty filler, so we honor that index when present.
    """
    if text.lstrip().startswith("<?xml"):
        text = re.sub(r'encoding="[^"]+"', 'encoding="UTF-8"', text, count=1)
    root = _xml_from_string(text)

    # Find the first <Table> inside any <Worksheet>.
    table = None
    for el in root.iter():
        if _strip_ns(el.tag) == "Table":
            table = el
            break
    if table is None:
        return []

    rows = [el for el in table if _strip_ns(el.tag) == "Row"]
    if not rows:
        return []

    header = _row_cells(rows[0])
    if not header:
        return []

    results: list[OptResult] = []
    for idx, row in enumerate(rows[1:], start=1):
        cells = _row_cells(row, expected=len(header))
        if not any(cells):
            # Trailing empty rows are common in Excel exports.
            continue
        record = dict(zip(header, cells, strict=False))
        # MT5 optimization passes are 0-indexed, so we cannot use
        # ``_try_int(...) or idx`` here — that would silently renumber
        # the pass 0 row to ``idx == 1`` and collide with pass 1. Treat
        # an absent / unparseable cell as the only fallback to idx.
        pass_raw = _try_int(record.get("Pass", ""))
        pass_num = pass_raw if pass_raw is not None else idx
        params: dict[str, str] = {}
        metrics: dict[str, float] = {}
        for name, raw in record.items():
            if not name:
                continue
            if name in _KNOWN_METRIC_COLUMNS:
                # Pass is recorded separately so it doesn't shadow itself.
                if name == "Pass":
                    continue
                v = _try_float(raw)
                if v is not None:
                    metrics[name] = v
            else:
                params[name] = raw
        results.append(OptResult(pass_num=pass_num, params=params, metrics=metrics))
    return results


def parse_opt_xml_file(path: Path) -> list[OptResult]:
    return parse_opt_xml(_decode_optimize_xml(path.read_bytes()))


def _row_cells(row: ET.Element, *, expected: int | None = None) -> list[str]:
    """Extract textual cell values, honouring ``ss:Index`` skip markers."""
    cells: list[str] = []
    for cell in row:
        if _strip_ns(cell.tag) != "Cell":
            continue
        # ss:Index="N" means this cell is at column N (1-based); fill the
        # gap with empty strings so the header alignment stays correct.
        idx_attr = None
        for attr_name, attr_value in cell.attrib.items():
            if _strip_ns(attr_name) == "Index":
                idx_attr = attr_value
                break
        if idx_attr is not None:
            try:
                target = int(idx_attr) - 1
            except ValueError:
                target = len(cells)
            while len(cells) < target:
                cells.append("")
        data_text = ""
        for data in cell:
            if _strip_ns(data.tag) == "Data":
                data_text = (data.text or "").strip()
                break
        cells.append(data_text)
    if expected is not None and len(cells) < expected:
        cells.extend([""] * (expected - len(cells)))
    return cells


def _try_float(raw: str) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _try_int(raw: str) -> int | None:
    """Best-effort int parse; ``None`` distinguishes an absent cell from a 0.

    The optimization report uses 0-indexed pass numbers, so callers must
    NOT collapse ``0`` and "missing" into the same return.
    """
    if raw is None or raw == "":
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None
