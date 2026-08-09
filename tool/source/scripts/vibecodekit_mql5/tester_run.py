"""mql5-tester-run — drive the MetaTrader 5 Strategy Tester end-to-end.

This is the missing W8 driver from the post-v1.0.1 audit. It composes
already-shipped infrastructure rather than duplicating it:

* ``backtest.render_tester_ini``   — emits the canonical ``tester.ini``
* ``backtest.parse_xml_report_file`` — parses the resulting XML report
* ``backtest.apply_tester_log``    — merges build-5260 pre-start-shift
                                     diagnostics from the journal log

The driver itself adds three responsibilities:

1. **Locate** the platform's ``terminal64.exe`` (or ``wine ... .exe``
   on Linux) without hard-coding a path.
2. **Launch** that binary headlessly with the rendered ``tester.ini``
   under ``/portable`` mode and a ``ShutdownTerminal=1`` ini so the
   process exits when the run finishes.
3. **Wait** for the XML report file to appear, with an upper-bound
   timeout, and gracefully report a missing-environment error when the
   terminal binary cannot be located.

The driver does NOT itself contact any broker, install MT5, or run an
unsupervised live trade — it only drives the Strategy Tester, which is
sandboxed by MT5 itself.

CLI
---
::

    python -m vibecodekit_mql5.tester_run MyEA.ex5 default.set \\
        --symbol EURUSD --period 2024.01.01-2024.12.31 --tf H1 \\
        [--report tester.xml] [--timeout 600] \\
        [--terminal /path/to/terminal64.exe] [--wine] \\
        [--print-ini-only]

Exit codes
----------
* 0 — backtest finished, XML parsed, JSON result printed to stdout.
* 1 — backtest finished but the XML report could not be parsed
  (corrupt / truncated / unexpected schema).
* 2 — invocation error (missing args, bad ``--period`` syntax, etc.).
* 3 — terminal binary not found in any known location and ``--terminal``
  was not supplied. Tells the user exactly which paths were probed.
* 4 — terminal launched but timed out without producing an XML report.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from vibecodekit_mql5.backtest import (
    BacktestResult,
    apply_tester_log,
    parse_period,
    parse_xml_report_file,
    render_tester_ini,
)


# ─────────────────────────────────────────────────────────────────────────────
# Terminal binary discovery
# ─────────────────────────────────────────────────────────────────────────────

# Probed in order. Each entry can use ``$VAR`` style env expansion which
# happens at call time so the snapshot caches the *recipe*, not the
# resolved path.
_PROBE_PATHS_LINUX = (
    "$MQL5_TERMINAL_PATH",
    "$MT5_TERMINAL_PATH",
    "$MT5_TERMINAL64",
    "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe",
    "$HOME/.wine-mql5/drive_c/Program Files/MetaTrader 5/terminal64.exe",
    "$HOME/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe",
)
_PROBE_PATHS_WIN = (
    "$MQL5_TERMINAL_PATH",
    "$MT5_TERMINAL_PATH",
    "$MT5_TERMINAL64",
    "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
    "C:\\Program Files (x86)\\MetaTrader 5\\terminal64.exe",
)


@dataclass
class TerminalLocation:
    path: Path
    use_wine: bool          # True on Linux Wine prefix; False on native
    probed: tuple[str, ...] # for the "not found" error message


def find_terminal(
    override: str | None = None,
    *,
    use_wine: bool | None = None,
    platform: str | None = None,
) -> TerminalLocation:
    """Locate ``terminal64.exe``.

    Order of precedence:
        1. ``override`` argument (e.g. CLI ``--terminal``).
        2. ``$MQL5_TERMINAL_PATH``.
        3. Platform-specific standard install locations.

    Raises ``FileNotFoundError`` with the full probe list when nothing
    is found, so the operator can see exactly which paths were tried.
    """
    plat = (platform or sys.platform).lower()
    is_windows = plat.startswith("win")
    probe = _PROBE_PATHS_WIN if is_windows else _PROBE_PATHS_LINUX
    wine_default = use_wine if use_wine is not None else (not is_windows)

    tried: list[str] = []

    if override:
        p = Path(os.path.expandvars(os.path.expanduser(override)))
        tried.append(str(p))
        if p.exists():
            return TerminalLocation(p, wine_default, tuple(tried))

    for raw in probe:
        expanded = os.path.expandvars(raw)
        if expanded == raw and raw.startswith("$"):
            # Env var was empty; skip silently.
            continue
        p = Path(expanded)
        tried.append(str(p))
        if p.exists():
            return TerminalLocation(p, wine_default, tuple(tried))

    raise FileNotFoundError(
        "MetaTrader 5 terminal64.exe not found. Paths probed:\n  - "
        + "\n  - ".join(tried)
        + "\nSet $MQL5_TERMINAL_PATH or pass --terminal <abs-path>."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TesterRunSpec:
    # Pytest sees the ``Test`` prefix and tries to collect this dataclass
    # as a test class. Disable collection explicitly.
    __test__ = False

    ea_path: str
    set_path: str
    symbol: str
    period: str         # MT5 timeframe enum string e.g. "H1"
    from_date: str      # YYYY.MM.DD
    to_date: str        # YYYY.MM.DD
    report_path: str = "tester.xml"
    tester_log: str | None = None
    requested_from: str | None = None


def build_command(loc: TerminalLocation, ini_path: Path) -> list[str]:
    """Compose the argv for the terminal launch.

    ``/portable`` keeps the terminal self-contained (data dir = install
    dir) so we don't accidentally write into a real broker's
    ``%APPDATA%`` profile. ``/config:`` points at the tester.ini.
    """
    if loc.use_wine:
        # On Linux Wine, terminal64.exe sees Linux paths via the Z: drive
        # letter; we pass the absolute path verbatim and let Wine handle
        # it. ``wine`` must be on PATH.
        return [
            "wine",
            str(loc.path),
            f"/config:{ini_path}",
            "/portable",
        ]
    return [
        str(loc.path),
        f"/config:{ini_path}",
        "/portable",
    ]


def wait_for_report(
    report: Path,
    *,
    timeout_sec: float,
    poll_interval_sec: float = 1.0,
    sleep: "callable | None" = None,
    now: "callable | None" = None,
) -> bool:
    """Block until ``report`` exists and is non-empty.

    ``sleep`` and ``now`` are injectable for testing. Returns True when
    the file appears, False on timeout.
    """
    _sleep = sleep or time.sleep
    _now = now or time.monotonic
    deadline = _now() + timeout_sec
    while _now() < deadline:
        if report.exists() and report.stat().st_size > 0:
            return True
        _sleep(poll_interval_sec)
    return False


def run(
    spec: TesterRunSpec,
    *,
    terminal: TerminalLocation,
    ini_path: Path,
    timeout_sec: float = 600.0,
    subprocess_runner: "callable | None" = None,
) -> BacktestResult:
    """Render tester.ini, launch the terminal, wait, parse the XML.

    Raises:
        TimeoutError — terminal ran past ``timeout_sec`` without
                       emitting the XML report.
        ValueError   — the XML report exists but does not parse.
    """
    ini_path.parent.mkdir(parents=True, exist_ok=True)
    ini_path.write_text(
        render_tester_ini(
            ea_path=spec.ea_path,
            set_path=spec.set_path,
            symbol=spec.symbol,
            period=spec.period,
            from_date=spec.from_date,
            to_date=spec.to_date,
            report_path=spec.report_path,
        ),
        encoding="utf-8",
    )

    cmd = build_command(terminal, ini_path)
    runner = subprocess_runner or subprocess.run
    # We can't trust the terminal's own exit code (under Wine it
    # frequently exits non-zero even on a successful run because of GUI
    # subsystem warnings), so we drive completion off the XML report
    # file instead. The subprocess.run timeout is set to the same upper
    # bound to avoid orphaning a hung process.
    try:
        runner(cmd, timeout=timeout_sec, check=False)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(
            f"terminal exceeded timeout={timeout_sec}s: {' '.join(cmd)}"
        ) from exc

    report = Path(spec.report_path)
    if not wait_for_report(report, timeout_sec=10.0):
        raise TimeoutError(
            f"terminal exited but report {report} was not produced "
            f"(check /portable data dir for the actual write location)"
        )

    result = parse_xml_report_file(report)
    if spec.tester_log:
        log_text = Path(spec.tester_log).read_text(
            encoding="utf-8", errors="replace"
        )
        apply_tester_log(result, log_text, spec.requested_from or spec.from_date)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mql5-tester-run",
        description=__doc__.splitlines()[0] if __doc__ else None,
    )
    p.add_argument("ea", help="EA path or name (interpreted by MT5)")
    p.add_argument("set_file", help="EA input set file (.set)")
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument(
        "--period", required=True,
        help="YYYY.MM.DD-YYYY.MM.DD (FromDate-ToDate)",
    )
    p.add_argument("--tf", default="H1", help="MT5 timeframe enum, e.g. H1")
    p.add_argument(
        "--report", default="tester.xml",
        help="Report=<path> in tester.ini (relative to terminal data dir)",
    )
    p.add_argument("--ini-out", default="tester.ini",
                   help="where to write the rendered tester.ini")
    p.add_argument("--timeout", type=float, default=600.0,
                   help="upper bound on terminal run, seconds")
    p.add_argument("--terminal", default=None,
                   help="absolute path to terminal64.exe (override probe)")
    p.add_argument("--wine", action="store_true",
                   help="force Wine wrapping even on non-Linux hosts")
    p.add_argument("--no-wine", action="store_true",
                   help="force native launch even on Linux")
    p.add_argument("--tester-log", default=None,
                   help="merge a tester journal log onto the result")
    p.add_argument("--print-ini-only", action="store_true",
                   help="render tester.ini and exit (no terminal launch)")
    args = p.parse_args(argv)

    try:
        from_date, to_date = parse_period(args.period)
    except ValueError as exc:
        print(f"[tester-run] {exc}", file=sys.stderr)
        return 2

    spec = TesterRunSpec(
        ea_path=args.ea,
        set_path=args.set_file,
        symbol=args.symbol,
        period=args.tf,
        from_date=from_date,
        to_date=to_date,
        report_path=args.report,
        tester_log=args.tester_log,
        requested_from=from_date,
    )

    if args.print_ini_only:
        print(render_tester_ini(
            ea_path=spec.ea_path,
            set_path=spec.set_path,
            symbol=spec.symbol,
            period=spec.period,
            from_date=spec.from_date,
            to_date=spec.to_date,
            report_path=spec.report_path,
        ), end="")
        return 0

    use_wine: bool | None
    if args.wine and args.no_wine:
        print("[tester-run] --wine and --no-wine are mutually exclusive",
              file=sys.stderr)
        return 2
    if args.wine:
        use_wine = True
    elif args.no_wine:
        use_wine = False
    else:
        use_wine = None  # auto-detect from platform

    try:
        terminal = find_terminal(args.terminal, use_wine=use_wine)
    except FileNotFoundError as exc:
        print(f"[tester-run] {exc}", file=sys.stderr)
        return 3

    try:
        result = run(
            spec,
            terminal=terminal,
            ini_path=Path(args.ini_out),
            timeout_sec=args.timeout,
        )
    except TimeoutError as exc:
        print(f"[tester-run] {exc}", file=sys.stderr)
        return 4
    except ValueError as exc:
        print(f"[tester-run] XML parse failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
