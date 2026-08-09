"""mql5-backtest — Strategy Tester wrapper.

Generates `tester.ini` from CLI args, invokes MetaTester via Wine, then
parses the XML report into a structured `BacktestResult`.

Result fields mirror the the kit spec §12 metric list:
    PF, RF, Sharpe, GHPR, AHPR, EP, LRCorr, LRStdErr,
    MaxDrawdownPct, total_trades, profitable_pct,
    winning_streak, losing_streak, MFE/MAE correlation.

CLI:
    python -m vibecodekit_mql5.backtest <ea.ex5> <set.set> --period FROM-TO

Exit codes:
    0 — backtest ran + parsed
    1 — tester invocation or report-parse failure
    2 — argv / file-not-found error
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Period parser  (FORMAT: "2023.01.01-2024.12.31"  or  "20230101-20241231")
# ─────────────────────────────────────────────────────────────────────────────

_PERIOD_RX = re.compile(
    r"^(?P<from>\d{4}[.\-]?\d{2}[.\-]?\d{2})-(?P<to>\d{4}[.\-]?\d{2}[.\-]?\d{2})$"
)


def parse_period(s: str) -> tuple[str, str]:
    """Return `(from, to)` in MT5 `YYYY.MM.DD` form. Raises `ValueError`."""
    m = _PERIOD_RX.match(s.strip())
    if not m:
        raise ValueError(f"period {s!r}: expected FROM-TO like 2023.01.01-2024.12.31")
    def _canon(d: str) -> str:
        d = d.replace("-", "").replace(".", "")
        if len(d) != 8:
            raise ValueError(f"period date {d!r}: 8 digits required")
        return f"{d[:4]}.{d[4:6]}.{d[6:]}"
    return _canon(m["from"]), _canon(m["to"])


# ─────────────────────────────────────────────────────────────────────────────
# tester.ini generator
# ─────────────────────────────────────────────────────────────────────────────

def render_tester_ini(
    *,
    ea_path: str,
    set_path: str,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    forward_mode: int = 0,
    report_path: str = "tester.xml",
    deposit: int = 10000,
    leverage: int = 100,
) -> str:
    """Render a minimal tester.ini. Caller owns paths (Wine drives accepted)."""
    return (
        "[Tester]\n"
        f"Expert={ea_path}\n"
        f"ExpertParameters={set_path}\n"
        f"Symbol={symbol}\n"
        f"Period={period}\n"
        f"FromDate={from_date}\n"
        f"ToDate={to_date}\n"
        f"ForwardMode={forward_mode}\n"
        f"Deposit={deposit}\n"
        f"Currency=USD\n"
        f"Leverage=1:{leverage}\n"
        "Model=1\n"  # 1 = 1-minute OHLC; 0 = every tick (slow)
        "Optimization=0\n"
        "ShutdownTerminal=1\n"
        f"Report={report_path}\n"
        "ReplaceReport=1\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# XML report parser
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    symbol: str = ""
    period: str = ""
    profit_factor: float = 0.0
    recovery_factor: float = 0.0
    sharpe: float = 0.0
    ghpr: float = 0.0
    ahpr: float = 0.0
    expected_payoff: float = 0.0
    lr_correlation: float = 0.0
    lr_std_error: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades: int = 0
    profitable_pct: float = 0.0
    winning_streak: int = 0
    losing_streak: int = 0
    mfe_correlation: float = 0.0
    mae_correlation: float = 0.0
    broker_digits: int = 0
    # Build 5260 added a pre-start data-availability check that shifts
    # FromDate forward when there's no history on the requested day.
    # When present, ``actual_from_date`` is the post-shift date as
    # ``YYYY.MM.DD`` and ``prestart_shift_days`` is the gap in days.
    actual_from_date: str = ""
    prestart_shift_days: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


_FLOAT_FIELDS: dict[str, str] = {
    "ProfitFactor":    "profit_factor",
    "RecoveryFactor":  "recovery_factor",
    "SharpeRatio":     "sharpe",
    "GHPR":            "ghpr",
    "AHPR":            "ahpr",
    "ExpectedPayoff":  "expected_payoff",
    "LRCorrelation":   "lr_correlation",
    "LRStdError":      "lr_std_error",
    "MaxDrawdownPct":  "max_drawdown_pct",
    "ProfitablePct":   "profitable_pct",
    "MFECorrelation":  "mfe_correlation",
    "MAECorrelation":  "mae_correlation",
}
_INT_FIELDS: dict[str, str] = {
    "TotalTrades":     "total_trades",
    "WinningStreak":   "winning_streak",
    "LosingStreak":    "losing_streak",
    "BrokerDigits":    "broker_digits",
}


def _decode(raw: bytes) -> str:
    """MT5 writes reports as UTF-16-LE w/ BOM; tolerate UTF-8 fixtures too.

    UTF-16 codecs never raise on even-length byte streams, so we cannot rely
    on a try/except cascade. Sniff the BOM (or ASCII `<?xml` signature) up
    front to pick the right codec.
    """
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    # ASCII-range XML declaration → plain UTF-8.
    if raw.lstrip()[:5] in (b"<?xml", b"<Test"):
        return raw.decode("utf-8", errors="replace")
    # Heuristic: lots of NULs → some UTF-16 flavour without a BOM.
    if raw[:64].count(b"\x00") >= 16:
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


# Matches a bare ``&`` that is NOT already the start of a valid XML entity.
# Real MT5 reports frequently embed un

_BARE_AMP_RX = re.compile(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)")


def _text(root: ET.Element, tag: str, default: str = "") -> str:
    node = root.find(f".//{tag}")
    return (node.text or "").strip() if node is not None else default


def _number(raw: str, cast: type[float] | type[int], default: Any = 0) -> Any:
    if not raw:
        return default
    try:
        return cast(raw.replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def parse_xml_report(xml: str | bytes) -> BacktestResult:
    """Parse an MT5 tester XML string into :class:`BacktestResult`.

    MT5 has emitted both UTF-16 and UTF-8 reports and some broker strings
    contain bare ampersands, so decoding and entity cleanup happen before the
    standard library XML parser is called.
    """
    raw = xml.encode("utf-8") if isinstance(xml, str) else xml
    text = _decode(raw)
    text = _BARE_AMP_RX.sub("&amp;", text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid tester XML: {exc}") from exc
    result = BacktestResult(
        symbol=_text(root, "Symbol"),
        period=_text(root, "Period"),
        profit_factor=_number(_text(root, "ProfitFactor"), float),
        recovery_factor=_number(_text(root, "RecoveryFactor"), float),
        sharpe=_number(_text(root, "SharpeRatio"), float),
        ghpr=_number(_text(root, "GHPR"), float),
        ahpr=_number(_text(root, "AHPR"), float),
        expected_payoff=_number(_text(root, "ExpectedPayoff"), float),
        lr_correlation=_number(_text(root, "LRCorrelation"), float),
        lr_std_error=_number(_text(root, "LRStdError"), float),
        max_drawdown_pct=_number(_text(root, "MaxDrawdownPct"), float),
        total_trades=_number(_text(root, "TotalTrades"), int),
        profitable_pct=_number(_text(root, "ProfitablePct"), float),
        winning_streak=_number(_text(root, "WinningStreak"), int),
        losing_streak=_number(_text(root, "LosingStreak"), int),
        mfe_correlation=_number(_text(root, "MFECorrelation"), float),
        mae_correlation=_number(_text(root, "MAECorrelation"), float),
        broker_digits=_number(_text(root, "BrokerDigits"), int),
        actual_from_date=_text(root, "ActualFromDate", _text(root, "FromDate")),
    )
    result.extra = {
        "report_date": _text(root, "ReportDate"),
        "from_date": _text(root, "FromDate"),
        "to_date": _text(root, "ToDate"),
    }
    return result


def parse_xml_report_file(path: Path) -> BacktestResult:
    """Read and parse an MT5 tester XML report from ``path``."""
    return parse_xml_report(Path(path).read_bytes())


def apply_tester_log(result: BacktestResult, log_text: str, requested_from: str) -> BacktestResult:
    """Merge a build-5260 pre-start data shift into a parsed result.

    The parser accepts common journal forms such as ``actual start:`` or
    ``testing starts from YYYY.MM.DD``. If no shift is present, the result is
    returned unchanged.
    """
    dates = re.findall(r"(?:actual\s+start|starts?\s+from|from\s+date)\D{0,20}(\d{4}[.]\d{2}[.]\d{2})",
                      log_text, flags=re.IGNORECASE)
    if not dates:
        return result
    actual = dates[-1]
    result.actual_from_date = actual
    result.extra["requested_from_date"] = requested_from
    try:
        from datetime import date

        requested = date.fromisoformat(requested_from.replace(".", "-"))
        observed = date.fromisoformat(actual.replace(".", "-"))
        result.prestart_shift_days = max(0, (observed - requested).days)
    except ValueError:
        result.prestart_shift_days = 0
    return result


def main(argv: list[str] | None = None) -> int:
    """Parse an existing tester XML report for automation-safe CLI use.

    Real MetaTester execution is delegated to the dedicated runner.  This
    entry point intentionally reports ``UNTESTABLE`` when no report is
    supplied instead of pretending a wrapper invocation was a backtest pass.
    """
    ap = argparse.ArgumentParser(prog="mql5-backtest")
    ap.add_argument("ea_path", nargs="?", help="compiled EX5 path (execution delegated)")
    ap.add_argument("set_path", nargs="?", help="tester .set path")
    ap.add_argument("--report", type=Path, help="existing MT5 tester XML report")
    ap.add_argument("--period", default="", help="requested FROM-TO period")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if not args.report:
        payload = {"ok": False, "status": "UNTESTABLE", "reason": "no tester report supplied"}
        print(json.dumps(payload, ensure_ascii=False) if args.json else "UNTESTABLE: no tester report supplied")
        return 3
    try:
        result = parse_xml_report_file(args.report)
    except (OSError, ValueError) as exc:
        payload = {"ok": False, "status": "FAIL", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False) if args.json else f"FAIL: {exc}")
        return 1
    payload = {"ok": True, "status": "PASS", "result": dataclasses.asdict(result)}
    print(json.dumps(payload, ensure_ascii=False) if args.json else json.dumps(payload["result"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
