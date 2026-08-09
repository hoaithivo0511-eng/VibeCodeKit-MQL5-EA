"""Single source of truth for every rule identifier the kit can emit.

Before this module, rule IDs were defined inline in three places that had
*drifted and collided*:

* :mod:`vibecodekit_mql5.lint` owned the critical anti-pattern detector codes
  (``AP-1`` … ``AP-25``) and their SARIF metadata.
* :mod:`vibecodekit_mql5.lint_best_practice` emitted the warn-only subset of
  those same ``AP-*`` codes.
* :mod:`vibecodekit_mql5.ap_policy` *reused* ``AP-22`` … ``AP-27`` for a
  completely different family of profile/architecture checks, so ``AP-22`` from
  the linter and ``AP-22`` from the policy engine meant different things.

This registry gives every rule one canonical, namespaced ID:

* ``LINT-AP-*``  — critical static-lint detectors (gate, ERROR severity).
* ``BP-*``       — best-practice static-lint detectors (WARN, non-gating).
* ``ARCH-*``     — profile/architecture compliance checks.

The historical bare ``AP-N`` code is preserved per rule as ``legacy_code`` so
existing SARIF output, evidence files, and external consumers keep working
while the codebase migrates to the namespaced IDs.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── Namespaces ───────────────────────────────────────────────────────────────
NS_LINT_AP = "LINT-AP"
NS_BP = "BP"
NS_ARCH = "ARCH"
NS_UX = "UX"
NAMESPACES = (NS_LINT_AP, NS_BP, NS_ARCH, NS_UX)

SEVERITY_ERROR = "ERROR"
SEVERITY_WARN = "WARN"


@dataclass(frozen=True)
class Rule:
    """One canonical rule definition.

    rule_id     fully-qualified, namespaced id (e.g. ``LINT-AP-1``, ``BP-2``,
                ``ARCH-GRID-SYNC-CLOSE``). Globally unique.
    namespace   one of :data:`NAMESPACES`.
    slug        stable short/SARIF id (e.g. ``no-sl``). Unique across all rules.
    title       human-readable one-line description.
    severity    default severity, :data:`SEVERITY_ERROR` or :data:`SEVERITY_WARN`.
    legacy_code historical bare code (e.g. ``AP-1``) for backward compatibility,
                or ``None`` for rules that never had one.
    """

    rule_id: str
    namespace: str
    slug: str
    title: str
    severity: str
    legacy_code: str | None = None


def _ap(num: int, namespace: str, slug: str, title: str, severity: str) -> Rule:
    return Rule(
        rule_id=f"{namespace}-{num}",
        namespace=namespace,
        slug=slug,
        title=title,
        severity=severity,
        legacy_code=f"AP-{num}",
    )


# ── LINT-AP: critical static detectors (ERROR, gating) ───────────────────────
_LINT_AP_RULES = [
    _ap(1, NS_LINT_AP, "no-sl", "OrderSend / CTrade.Buy without stop-loss", SEVERITY_ERROR),
    _ap(3, NS_LINT_AP, "lot-hardcoded", "Hardcoded fixed lot size", SEVERITY_ERROR),
    _ap(5, NS_LINT_AP, "optimizer-overfit", ">6 optimization input params", SEVERITY_ERROR),
    _ap(15, NS_LINT_AP, "raw-ordersend", "Raw OrderSend bypasses CTrade", SEVERITY_ERROR),
    _ap(17, NS_LINT_AP, "webrequest-in-ontick", "WebRequest inside OnTick / OnTimer", SEVERITY_ERROR),
    _ap(18, NS_LINT_AP, "ordersend-async-unhandled", "OrderSendAsync without OnTradeTransaction", SEVERITY_ERROR),
    _ap(20, NS_LINT_AP, "hardcoded-pip", "Hardcoded pip math, not CPipNormalizer", SEVERITY_ERROR),
    _ap(21, NS_LINT_AP, "digits-class-untested", "`digits-tested:` meta covers <2 digit classes", SEVERITY_ERROR),
]

# ── BP: best-practice static detectors (WARN, non-gating) ────────────────────
_BP_RULES = [
    _ap(2, NS_BP, "magic-static", "Static magic number, not CMagicRegistry", SEVERITY_WARN),
    _ap(4, NS_BP, "trailing-stop-missing", "No trailing-stop / break-even logic", SEVERITY_WARN),
    _ap(6, NS_BP, "spread-unchecked", "No spread guard before OrderSend", SEVERITY_WARN),
    _ap(7, NS_BP, "news-session-unguarded", "No news / session guard", SEVERITY_WARN),
    _ap(8, NS_BP, "daily-loss-uncapped", "No daily-loss CRiskGuard wiring", SEVERITY_WARN),
    _ap(9, NS_BP, "multibroker-untested", "No multi-broker stability evidence", SEVERITY_WARN),
    _ap(10, NS_BP, "walkforward-missing", "No walkforward OOS test", SEVERITY_WARN),
    _ap(11, NS_BP, "montecarlo-missing", "No monte-carlo stress run", SEVERITY_WARN),
    _ap(12, NS_BP, "overfit-unchecked", "No overfit check / IS-OOS split", SEVERITY_WARN),
    _ap(13, NS_BP, "mfemae-unlogged", "No MFE / MAE journal logging", SEVERITY_WARN),
    _ap(14, NS_BP, "journal-unobservable", "No Print/PrintFormat journal lines", SEVERITY_WARN),
    _ap(16, NS_BP, "external-fallback-missing", "External dependency without fallback", SEVERITY_WARN),
    _ap(19, NS_BP, "vps-undeployed", "Missing VPS deployment evidence", SEVERITY_WARN),
    _ap(22, NS_BP, "ontick-no-orderplace", "OnTick reaches no order-placing call", SEVERITY_WARN),
    _ap(23, NS_BP, "ontick-leaks-resources", "OnTick creates/leaks heap resources", SEVERITY_WARN),
    _ap(24, NS_BP, "ontick-mq5-state-leak", "OnTick mutates global state outside guards", SEVERITY_WARN),
    _ap(25, NS_BP, "llm-fallback-missing", "LLM bridge without deterministic fallback", SEVERITY_WARN),
]

# ── ARCH: profile / architecture compliance checks ───────────────────────────
# These previously collided with LINT ``AP-22``..``AP-27`` inside ap_policy.py.
# The ``legacy_code`` keeps the old (ambiguous) id discoverable for traceability.
ARCH_GRID_SYNC_CLOSE = "ARCH-GRID-SYNC-CLOSE"
ARCH_ASYNC_HOOK_MISSING = "ARCH-ASYNC-HOOK-MISSING"
ARCH_CLOSE_RETRY_MISSING = "ARCH-CLOSE-RETRY-MISSING"
ARCH_STATE_PERSIST_MISSING = "ARCH-STATE-PERSIST-MISSING"
ARCH_ACCOUNT_SEED_MISSING = "ARCH-ACCOUNT-SEED-MISSING"
ARCH_DD_FREEZE_MISSING = "ARCH-DD-FREEZE-MISSING"

_ARCH_RULES = [
    Rule(ARCH_GRID_SYNC_CLOSE, NS_ARCH, "grid-sync-close", "Grid/basket EA uses raw synchronous PositionClose loop without AsyncTradeExecutor", SEVERITY_ERROR, "AP-22"),
    Rule(ARCH_ASYNC_HOOK_MISSING, NS_ARCH, "async-hook-missing", "Async execution without OnTradeTransaction forwarding", SEVERITY_ERROR, "AP-23"),
    Rule(ARCH_CLOSE_RETRY_MISSING, NS_ARCH, "close-retry-missing", "Async close engine without retry/fallback behavior", SEVERITY_WARN, "AP-24"),
    Rule(ARCH_STATE_PERSIST_MISSING, NS_ARCH, "state-persist-missing", "Grid/DCA EA does not persist recovery state", SEVERITY_ERROR, "AP-25"),
    Rule(ARCH_ACCOUNT_SEED_MISSING, NS_ARCH, "account-seed-missing", "Multi-account strategy without deterministic seed divergence", SEVERITY_WARN, "AP-26"),
    Rule(ARCH_DD_FREEZE_MISSING, NS_ARCH, "dd-freeze-missing", "Grid/basket EA without hard max-DD stop and freeze logic", SEVERITY_ERROR, "AP-27"),
    # Profile-manifest forbidden-pattern ids (declared in profiles/*.json).
    Rule("ARCH-RAW-CLOSE-LOOP", NS_ARCH, "raw_position_close_loop", "Raw CTrade.PositionClose inside basket/grid loops", SEVERITY_ERROR, None),
    Rule("ARCH-SYNC-TRADE-NO-ASYNC", NS_ARCH, "sync_trade_without_async_executor", "Raw CTrade without AsyncTradeExecutor in grid-safe profile", SEVERITY_ERROR, None),
    Rule("ARCH-SEND-NO-RISK-GUARD", NS_ARCH, "order_send_without_risk_guard", "Trade open without a RiskGuard gate (prop-firm caps)", SEVERITY_ERROR, None),
    Rule("ARCH-TRADE-NO-INFERENCE-GUARD", NS_ARCH, "trade_without_inference_guard", "Trade without InferenceGuard confidence gate (ml-assisted)", SEVERITY_ERROR, None),
]

_UX_RULES = [
    Rule("UX-04", NS_UX, "panel-object-cleanup", "Panel objects use a stable prefix and are removed on deinit", SEVERITY_ERROR),
    Rule("UX-05", NS_UX, "panel-no-blocking-hotpath", "Panel has no blocking or expensive work in hot-path handlers", SEVERITY_ERROR),
    Rule("UX-06", NS_UX, "panel-layout-contract", "Panel layout declares anchor, resize and DPI strategy", SEVERITY_WARN),
    Rule("UX-07", NS_UX, "panel-contrast-surface", "Panel text has an owned contrast surface", SEVERITY_WARN),
    Rule("UX-08", NS_UX, "panel-dirty-redraw", "Panel redraw is dirty-state and cadence guarded", SEVERITY_WARN),
    Rule("UX-09", NS_UX, "panel-destructive-confirm", "Destructive panel actions require confirmation and risk gates", SEVERITY_ERROR),
    Rule("UX-10", NS_UX, "panel-error-remediation", "Panel errors expose actionable remediation", SEVERITY_WARN),
    Rule("UX-11", NS_UX, "panel-safe-labels", "Labels avoid decorative or ambiguous glyphs", SEVERITY_WARN),
    Rule("UX-12", NS_UX, "panel-token-colors", "Colors are declared by UI token contract", SEVERITY_WARN),
    Rule("UI-PERF-01", NS_UX, "panel-ontick-budget", "Panel overhead stays within declared OnTick budget", SEVERITY_WARN),
    Rule("UI-PERF-02", NS_UX, "panel-renderer-pure", "Renderer cannot call execution, network or heavy data APIs", SEVERITY_ERROR),
    Rule("UI-PERF-03", NS_UX, "panel-resource-lifecycle", "Panel releases objects and resources on deinit", SEVERITY_WARN),
    Rule("UI-PERF-04", NS_UX, "panel-evidence-provenance", "Visual and performance evidence has provenance sidecar", SEVERITY_WARN),
]

RULES: tuple[Rule, ...] = tuple(_LINT_AP_RULES + _BP_RULES + _ARCH_RULES + _UX_RULES)

# ── Indices ──────────────────────────────────────────────────────────────────
_BY_ID: dict[str, Rule] = {}
_BY_SLUG: dict[str, Rule] = {}
_BY_LEGACY: dict[str, Rule] = {}
for _r in RULES:
    if _r.rule_id in _BY_ID:
        raise AssertionError(f"duplicate rule_id in registry: {_r.rule_id}")
    if _r.slug in _BY_SLUG:
        raise AssertionError(f"duplicate slug in registry: {_r.slug}")
    _BY_ID[_r.rule_id] = _r
    _BY_SLUG[_r.slug] = _r
    if _r.legacy_code is not None:
        # legacy codes are intentionally namespace-scoped (AP-22 exists in both
        # BP and ARCH); index the first occurrence per namespace.
        _BY_LEGACY.setdefault((_r.namespace, _r.legacy_code), _r)


def all_rules() -> tuple[Rule, ...]:
    return RULES


def by_namespace(namespace: str) -> list[Rule]:
    return [r for r in RULES if r.namespace == namespace]


def get(rule_id: str) -> Rule:
    return _BY_ID[rule_id]


def by_slug(slug: str) -> Rule | None:
    return _BY_SLUG.get(slug)


def legacy(namespace: str, code: str) -> Rule | None:
    return _BY_LEGACY.get((namespace, code))


# ── Consumer-facing helpers (keep lint.py / ap_policy.py thin) ───────────────
def lint_meta() -> dict[str, tuple[str, str]]:
    """``{legacy_code: (slug, title)}`` for the full static-lint catalogue.

    Covers both LINT-AP (critical) and BP (best-practice) namespaces — i.e.
    every ``AP-*`` code a source linter can emit. Used to build SARIF rule
    metadata in :mod:`vibecodekit_mql5.lint`.
    """
    meta: dict[str, tuple[str, str]] = {}
    for r in RULES:
        if r.namespace in (NS_LINT_AP, NS_BP) and r.legacy_code:
            meta[r.legacy_code] = (r.slug, r.title)
        elif r.namespace == NS_UX:
            meta[r.rule_id] = (r.slug, r.title)
    return meta


def lint_error_codes() -> set[str]:
    """Legacy codes whose default severity is ERROR (the gating critical set)."""
    return {
        (r.legacy_code if r.namespace == NS_LINT_AP else r.rule_id)
        for r in RULES
        if ((r.namespace == NS_LINT_AP and r.legacy_code) or r.namespace == NS_UX)
        and r.severity == SEVERITY_ERROR
    }


def arch_rule_id(legacy_code: str) -> str:
    """Map a historical ap_policy ``AP-N`` code to its namespaced ARCH id."""
    rule = _BY_LEGACY.get((NS_ARCH, legacy_code))
    if rule is None:
        raise KeyError(f"no ARCH rule for legacy code {legacy_code!r}")
    return rule.rule_id
