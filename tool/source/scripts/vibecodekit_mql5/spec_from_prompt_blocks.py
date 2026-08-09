"""PR-11 — block matchers + YAML helpers for ``spec_from_prompt``.

Carved out of :mod:`vibecodekit_mql5.spec_from_prompt` so the parser
module stays under the 400-LOC audit ceiling. Each
``match_<block>`` recogniser is regex-only (stdlib re), deterministic,
and returns ``None`` when nothing in the prompt mentions that block —
preserving back-compat with prompts that don't use any PR-2/PR-8
feature.

The :data:`OPTIONAL_BLOCKS` tuple is the single source of truth for
the 8 optional schema blocks the parser can infer:

* PR-2: ``prop_firm``, ``time_exit``, ``stealth``
* PR-8: ``trailing``, ``partial_close``, ``correlation``,
  ``swap_filter``, ``logs``

For the YAML emitter helpers see
:mod:`vibecodekit_mql5.spec_from_prompt_yaml` — split out to keep this
module under the audit LOC ceiling.
"""

from __future__ import annotations

import re


OPTIONAL_BLOCKS: tuple[str, ...] = (
    "prop_firm", "time_exit", "stealth",
    "trailing", "partial_close", "correlation",
    "swap_filter", "logs",
)


# ─────────────────────────────────────────────────────────────────────────────
# PR-2 / PR-8 block matchers
# ─────────────────────────────────────────────────────────────────────────────

def match_prop_firm(text: str) -> dict[str, object] | None:
    """PR-2 ``prop_firm`` — FTMO / funded-account guardrails."""
    out: dict[str, object] = {}

    m = re.search(r"\bdaily[\s_-]?dd\s*[:=]?\s*([\d.]+)\s*%?", text, re.IGNORECASE)
    if m:
        out["daily_dd_pct"] = float(m.group(1))

    m = re.search(r"\bmax[\s_-]?dd\s*[:=]?\s*([\d.]+)\s*%?", text, re.IGNORECASE)
    if m:
        out["max_dd_pct"] = float(m.group(1))

    m = re.search(
        r"\bprofit[\s_-]?target\s*[:=]?\s*([\d.]+)\s*%?",
        text, re.IGNORECASE,
    )
    if m:
        out["profit_target_pct"] = float(m.group(1))

    m = re.search(
        r"\bnews[\s_-]?(?:block|blackout)\s*[:=]?\s*([\d]+)\s*(?:min(?:ute)?s?)?",
        text, re.IGNORECASE,
    )
    if m:
        out["news_block_min"] = int(m.group(1))

    if re.search(r"\bweekend[\s_-]?flat\b", text, re.IGNORECASE):
        out["weekend_flat"] = True
    if re.search(r"\bcopy[\s_-]?trad(?:e|ing)[\s_-]?lock\b", text, re.IGNORECASE):
        out["copy_trading_lock"] = True

    # Bare keyword triggers: even just "FTMO" / "prop firm" / "funded" gives
    # us a hint to enable the block with schema defaults.
    if not out and re.search(
        r"\b(?:ftmo|prop[\s_-]?firm|funded(?:[\s_-]account)?)\b",
        text, re.IGNORECASE,
    ):
        out["daily_dd_pct"] = 5.0
    return out or None


def match_time_exit(text: str) -> dict[str, object] | None:
    """PR-2 ``time_exit`` — session windows + Friday close."""
    out: dict[str, object] = {}

    if re.search(
        r"\bclose[\s_-]?(?:on[\s_-])?friday\b|\bfriday[\s_-]?close\b|\bflat[\s_-]?friday\b",
        text, re.IGNORECASE,
    ):
        out["close_on_friday"] = True

    m = re.search(
        r"\bfriday[\s_-]?(?:close[\s_-])?(?:hour|at)?\s*[:=]?\s*([\d]{1,2})\s*(?:h|hour|hours|hrs|:00)?",
        text, re.IGNORECASE,
    )
    if m:
        out["friday_close_hour"] = int(m.group(1))

    m = re.search(
        r"\bmax[\s_-]?(?:trade[\s_-]?)?hours?\s*[:=]?\s*([\d]+)",
        text, re.IGNORECASE,
    )
    if m:
        out["max_trade_hours"] = int(m.group(1))

    m = re.search(
        r"\bsession[\s_-]?start\s*[:=]?\s*([\d]{1,2})",
        text, re.IGNORECASE,
    )
    if m:
        out["session_start_hour"] = int(m.group(1))
    m = re.search(
        r"\bsession[\s_-]?end\s*[:=]?\s*([\d]{1,2})",
        text, re.IGNORECASE,
    )
    if m:
        out["session_end_hour"] = int(m.group(1))

    # Bare keyword fallback so "time exit" alone still opts in.
    if not out and re.search(
        r"\btime[\s_-]?exit\b", text, re.IGNORECASE,
    ):
        out["close_on_friday"] = True
    return out or None


def match_stealth(text: str) -> dict[str, object] | None:
    """PR-2 ``stealth`` — broker anti-detection knobs."""
    out: dict[str, object] = {}

    m = re.search(
        r"\b(?:randomi[sz]e[\s_-]?)?slippage\s*[:=]?\s*([\d.]+)\s*(?:pips?)?",
        text, re.IGNORECASE,
    )
    if m:
        out["randomize_slippage_pips"] = float(m.group(1))

    m = re.search(
        r"\b(?:lot[\s_-]?jitter|jitter[\s_-]?lot)\s*[:=]?\s*([\d.]+)\s*%?",
        text, re.IGNORECASE,
    )
    if m:
        out["randomize_lot_jitter_pct"] = float(m.group(1))

    if re.search(r"\bsplit[\s_-]?orders?\b", text, re.IGNORECASE):
        out["split_orders"] = True
    if re.search(
        r"\bavoid[\s_-]?round[\s_-]?numbers?\b|\bno[\s_-]?round[\s_-]?numbers?\b",
        text, re.IGNORECASE,
    ):
        out["avoid_round_numbers"] = True
    if re.search(
        r"\brandomi[sz]e[\s_-]?comments?\b|\bcomment[\s_-]?pool\b",
        text, re.IGNORECASE,
    ):
        out["randomize_comment_pool"] = ["alpha", "beta", "gamma"]

    if not out and re.search(r"\bstealth\b", text, re.IGNORECASE):
        out["split_orders"] = True
    return out or None


def match_trailing(text: str) -> dict[str, object] | None:
    """PR-8 ``trailing`` — trailing stop config (fixed / atr / parabolic)."""
    if not re.search(
        r"\btrailing(?:[\s_-]?stop)?\b|\btrail[\s_-]?sl\b",
        text, re.IGNORECASE,
    ):
        return None
    out: dict[str, object] = {"enabled": True}

    if re.search(r"\batr[\s_-]?trailing\b|\btrailing[\s_-]?atr\b", text, re.IGNORECASE):
        out["mode"] = "atr"
    elif re.search(
        r"\bparabolic[\s_-]?trailing\b|\bsar[\s_-]?trailing\b|\btrailing[\s_-]?sar\b",
        text, re.IGNORECASE,
    ):
        out["mode"] = "parabolic"
    elif re.search(r"\bfixed[\s_-]?trailing\b|\btrailing[\s_-]?fixed\b", text, re.IGNORECASE):
        out["mode"] = "fixed"

    m = re.search(
        r"\btrailing[\s_-]?start\s*[:=]?\s*([\d.]+)\s*(?:pips?)?"
        r"|\bstart\s*[:=]?\s*([\d.]+)\s*(?:pips?)?\s*(?:trail|trailing)",
        text, re.IGNORECASE,
    )
    if m:
        out["start_pips"] = float(m.group(1) or m.group(2))

    m = re.search(
        r"\btrailing[\s_-]?step\s*[:=]?\s*([\d.]+)\s*(?:pips?)?"
        r"|\bstep\s*[:=]?\s*([\d.]+)\s*(?:pips?)?\s*(?:trail|trailing)",
        text, re.IGNORECASE,
    )
    if m:
        out["step_pips"] = float(m.group(1) or m.group(2))

    m = re.search(
        r"\batr[\s_-]?mult(?:iplier)?\s*[:=]?\s*([\d.]+)",
        text, re.IGNORECASE,
    )
    if m:
        out["atr_mult"] = float(m.group(1))
    return out


def match_partial_close(text: str) -> dict[str, object] | None:
    """PR-8 ``partial_close`` — pyramid-style scaling out at price levels."""
    if not re.search(
        r"\bpartial[\s_-]?close\b|\bscale[\s_-]?out\b|\btake[\s_-]?partial\b",
        text, re.IGNORECASE,
    ):
        return None
    out: dict[str, object] = {"enabled": True}

    levels: list[dict[str, float]] = []
    for m in re.finditer(
        r"(?:close[\s_-])?([\d.]+)\s*%\s*(?:at|@)\s*([\d.]+)\s*(?:pips?)?",
        text, re.IGNORECASE,
    ):
        levels.append({
            "at_pips": float(m.group(2)),
            "pct":     float(m.group(1)),
        })
    if levels:
        out["levels"] = levels

    if re.search(
        r"\bmove[\s_-]?sl[\s_-]?to[\s_-]?breakeven\b|\bbreakeven[\s_-]?after\b",
        text, re.IGNORECASE,
    ):
        out["move_sl_to_breakeven_after_first"] = True

    m = re.search(
        r"\bbreakeven[\s_-]?buffer\s*[:=]?\s*([\d.]+)\s*(?:pips?)?",
        text, re.IGNORECASE,
    )
    if m:
        out["breakeven_buffer_pips"] = float(m.group(1))
    return out


def match_correlation(text: str) -> dict[str, object] | None:
    """PR-8 ``correlation`` — block correlated symbol exposure."""
    if not re.search(
        r"\bcorrelation(?:[\s_-]?(?:filter|block|guard))?\b|\bcorrelated\b",
        text, re.IGNORECASE,
    ):
        return None
    out: dict[str, object] = {}

    m = re.search(
        r"\bmax[\s_-]?correlated(?:[\s_-]?positions?)?\s*[:=]?\s*([\d]+)",
        text, re.IGNORECASE,
    )
    if m:
        out["max_correlated_positions"] = int(m.group(1))

    m = re.search(
        r"\bcorrelation[\s_-]?threshold\s*[:=]?\s*([\d.]+)",
        text, re.IGNORECASE,
    )
    if m:
        out["correlation_threshold"] = float(m.group(1))

    m = re.search(
        r"\bcorrelation[\s_-]?window\s*[:=]?\s*([\d]+)",
        text, re.IGNORECASE,
    )
    if m:
        out["correlation_window_bars"] = int(m.group(1))

    if re.search(
        r"\bblock[\s_-]?(?:if[\s_-])?correlated[\s_-]?loss\b",
        text, re.IGNORECASE,
    ):
        out["block_if_correlated_loss"] = True

    if not out:
        out["max_correlated_positions"] = 2
    return out


def match_swap_filter(text: str) -> dict[str, object] | None:
    """PR-8 ``swap_filter`` — refuse trades with painful overnight swap."""
    if not re.search(
        r"\bswap[\s_-]?filter\b|\bnegative[\s_-]?swap\b|\btriple[\s_-]?swap\b|\bwednesday[\s_-]?swap\b",
        text, re.IGNORECASE,
    ):
        return None
    out: dict[str, object] = {}

    m = re.search(
        r"\bmax[\s_-]?long[\s_-]?swap\s*[:=]?\s*(-?[\d.]+)",
        text, re.IGNORECASE,
    )
    if m:
        out["max_long_swap_pips_per_day"] = float(m.group(1))

    m = re.search(
        r"\bmax[\s_-]?short[\s_-]?swap\s*[:=]?\s*(-?[\d.]+)",
        text, re.IGNORECASE,
    )
    if m:
        out["max_short_swap_pips_per_day"] = float(m.group(1))

    m = re.search(
        r"\bmax[\s_-]?hold[\s_-]?bars\s*[:=]?\s*([\d]+)",
        text, re.IGNORECASE,
    )
    if m:
        out["max_hold_bars_if_negative_swap"] = int(m.group(1))

    if re.search(
        r"\bskip[\s_-]?wednesday\b|\bwednesday[\s_-]?swap\b|\btriple[\s_-]?swap\b",
        text, re.IGNORECASE,
    ):
        out["skip_wednesday_triple_swap"] = True

    if not out:
        out["skip_wednesday_triple_swap"] = True
    return out


def match_logs(text: str) -> dict[str, object] | None:
    """PR-8 ``logs`` — structured logging + account-number redaction."""
    has_log_kw = re.search(
        r"\blogs?\b|\blogging\b|\bredact\b",
        text, re.IGNORECASE,
    )
    if not has_log_kw:
        return None
    out: dict[str, object] = {"enabled": True}

    m = re.search(
        r"\blog[\s_-]?level\s*[:=]?\s*(debug|info|warn(?:ing)?|error)\b",
        text, re.IGNORECASE,
    )
    if m:
        level = m.group(1).lower()
        if level == "warning":
            level = "warn"
        out["level"] = level

    if re.search(r"\b(?:log[\s_-]?to[\s_-]?)?file\b", text, re.IGNORECASE):
        out["to_file"] = True
    if re.search(
        r"\b(?:log[\s_-]?to[\s_-]?)?terminal\b|\bto[\s_-]?terminal\b",
        text, re.IGNORECASE,
    ):
        out["to_terminal"] = True
    if re.search(
        r"\bredact(?:[\s_-]account(?:[\s_-]numbers?)?)?\b",
        text, re.IGNORECASE,
    ):
        out["redact_account_numbers"] = True
    return out


# Registry mapping block name → matcher callable. Iterating this keeps
# ``spec_from_prompt.parse`` short and lets callers add custom blocks
# without editing the parser module.
BLOCK_MATCHERS = {
    "prop_firm":     match_prop_firm,
    "time_exit":     match_time_exit,
    "stealth":       match_stealth,
    "trailing":      match_trailing,
    "partial_close": match_partial_close,
    "correlation":   match_correlation,
    "swap_filter":   match_swap_filter,
    "logs":          match_logs,
}
