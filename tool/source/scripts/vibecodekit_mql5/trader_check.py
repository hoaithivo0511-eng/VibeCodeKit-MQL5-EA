"""mql5-trader-check — Trader-17 safety + technical checklist.

Inspects a `.mq5` source file and returns a 17-key dict where each value
is one of: ``"PASS" | "WARN" | "FAIL" | "N/A"``.

Acceptance modes:
    personal:   >= 15/17 PASS
    enterprise: == 17/17 PASS

CLI:
    python -m vibecodekit_mql5.trader_check <ea.mq5> [--mode personal|enterprise]
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# The linter checks share fixture-level semantics; re-use its detectors.
from vibecodekit_mql5 import lint as ap_lint


def _ap_findings(detector, text: str) -> list:
    """Call a lint detector with the (path, raw, src) signature it expects."""
    src = ap_lint._strip_comments(text)
    return detector("<inline>", text, src)


CHECKS = [
    "sl_set_every_trade",
    "lot_risk_based",
    "magic_reserved_unique",
    "spread_guarded",
    "daily_loss_capped",
    "news_session_guarded",
    "pip_normalized_via_kit",
    "multi_broker_tested",
    "walkforward_passed",
    "monte_carlo_validated",
    "overfit_checked",
    "mfe_mae_logged",
    "journal_observable",
    "external_dependency_fallback",
    "vps_deployed",
    "llm_fallback_defined",
    "pip_normalized_across_brokers",
]


# Regex tags that can be embedded in a source file as `// @trader17:key=PASS`
_TAG_RX = re.compile(r"//\s*@trader17\s*:\s*(?P<k>\w+)\s*=\s*(?P<v>PASS|WARN|FAIL|N/A)",
                     re.IGNORECASE)


def _scan_tags(text: str) -> dict[str, str]:
    return {m["k"].lower(): m["v"].upper() for m in _TAG_RX.finditer(text)}


def _check_sl_set_every_trade(text: str) -> str:
    findings = _ap_findings(ap_lint.detect_ap1, text)
    return "FAIL" if findings else "PASS"


def _check_lot_risk_based(text: str) -> str:
    findings = _ap_findings(ap_lint.detect_ap3, text)
    return "FAIL" if findings else "PASS"


def _check_pip_normalized_via_kit(text: str) -> str:
    if "CPipNormalizer" in text and "pip.Pips" in text:
        return "PASS"
    findings = _ap_findings(ap_lint.detect_ap20, text)
    return "FAIL" if findings else "WARN"


def _check_magic_reserved_unique(text: str) -> str:
    if "CMagicRegistry" in text and "Reserve(" in text:
        return "PASS"
    return "WARN"


def _check_spread_guarded(text: str) -> str:
    return "PASS" if "CSpreadGuard" in text or "MaxSpread" in text else "WARN"


def _check_daily_loss_capped(text: str) -> str:
    return "PASS" if "CRiskGuard" in text and "DailyLoss" in text else "WARN"


def _check_mfe_mae_logged(text: str) -> str:
    return "PASS" if "CMfeMaeLogger" in text else "WARN"


def _check_journal_observable(text: str) -> str:
    return "PASS" if "Print(" in text or "PrintFormat(" in text else "WARN"


def _check_pip_normalized_across_brokers(text: str) -> str:
    findings = _ap_findings(ap_lint.detect_ap21, text)
    return "FAIL" if findings else ("PASS" if "// digits-tested:" in text else "WARN")


# Items that are operational rather than source-detectable — default N/A but
# can be set explicitly via `// @trader17:<key>=PASS`.
_OPERATIONAL = {
    "news_session_guarded",
    "multi_broker_tested",
    "walkforward_passed",
    "monte_carlo_validated",
    "overfit_checked",
    "external_dependency_fallback",
    "vps_deployed",
    "llm_fallback_defined",
}


def evaluate(text: str) -> dict[str, str]:
    tags = _scan_tags(text)
    out: dict[str, str] = {}
    detectors = {
        "sl_set_every_trade": _check_sl_set_every_trade,
        "lot_risk_based": _check_lot_risk_based,
        "magic_reserved_unique": _check_magic_reserved_unique,
        "spread_guarded": _check_spread_guarded,
        "daily_loss_capped": _check_daily_loss_capped,
        "pip_normalized_via_kit": _check_pip_normalized_via_kit,
        "mfe_mae_logged": _check_mfe_mae_logged,
        "journal_observable": _check_journal_observable,
        "pip_normalized_across_brokers": _check_pip_normalized_across_brokers,
    }
    for key in CHECKS:
        if key in tags:                       # explicit tag overrides
            out[key] = tags[key]
            continue
        if key in detectors:
            out[key] = detectors[key](text)
        elif key in _OPERATIONAL:
            out[key] = "N/A"
        else:
            out[key] = "WARN"
    pass_count = sum(1 for v in out.values() if v == "PASS")
    warn_count = sum(1 for v in out.values() if v == "WARN")
    na_count = sum(1 for v in out.values() if v == "N/A")
    fail_count = sum(1 for v in out.values() if v == "FAIL")
    out["_summary"] = (f"{pass_count}/17 PASS, {warn_count} WARN, "
                       f"{na_count} N/A, {fail_count} FAIL")
    return out


def verdict(result: dict[str, str], *, mode: str = "personal") -> bool:
    pass_count = sum(1 for k, v in result.items() if not k.startswith("_") and v == "PASS")
    fail_count = sum(1 for k, v in result.items() if not k.startswith("_") and v == "FAIL")
    if fail_count > 0:
        return False
    return pass_count >= (17 if mode == "enterprise" else 15)


def main(argv: list[str] | None = None) -> int:
    from . import _agent_io

    p = argparse.ArgumentParser(prog="mql5-trader-check", description=__doc__.splitlines()[0])
    p.add_argument("ea")
    p.add_argument("--mode", choices=["personal", "enterprise"], default="personal")
    _agent_io.add_json_flag(p)
    _agent_io.add_gate_report_flag(p)
    _agent_io.add_draft_flag(p)
    args = p.parse_args(argv)

    from .mq5_io import read_mq5_text

    text = read_mq5_text(args.ea, errors="replace")
    result = evaluate(text)
    ok = verdict(result, mode=args.mode)

    envelope = _agent_io.Envelope(
        tool="mql5-trader-check",
        ok=ok,
        exit_code=0 if ok else 1,
        summary=result.get("_summary", "trader-17 evaluated"),
        data={"mode": args.mode, "result": result},
        evidence=[args.ea],
        matrix_dim="d_risk",
        matrix_axis="design",
        matrix_status="PASS" if ok else "FAIL",
    )
    _agent_io.apply_draft(envelope, args.draft)

    if args.emit_json:
        _agent_io.emit(envelope)
    else:
        # Legacy behaviour: pretty-print the 17-key dict directly.
        print(json.dumps(result, indent=2))

    if args.gate_report is not None:
        _agent_io.write_gate_report(envelope, args.gate_report)

    return envelope.exit_code


if __name__ == "__main__":
    sys.exit(main())
