"""Cross-feature invariants for EA-IR build plans.

Range validation is insufficient for an EA assembled from independent engines.
This module validates ownership, time, concurrency and execution contracts
across feature boundaries before source generation.
"""
from __future__ import annotations

from typing import Any, Iterable

from .ea_ir import EAIR


def _parameters(ir: EAIR) -> dict[str, Any]:
    value = ir.strategy.get("parameters") or {}
    return value if isinstance(value, dict) else {}


def validate(ir: EAIR, requested: Iterable[str]) -> list[dict[str, Any]]:
    paths = set(requested)
    p = _parameters(ir)
    blockers: list[dict[str, Any]] = []

    zone_peers = {
        "strategy.hedge.standard", "strategy.reverse_entry",
        "strategy.lot_balance",
    } & paths
    if "strategy.hedge.zone" in paths and zone_peers:
        policy = p.get("hedge_zone_concurrency_policy")
        if policy not in {"exclusive", "explicit_cooperative"}:
            blockers.append({
                "id": "MISSING-HEDGE-ZONE-CONCURRENCY-POLICY",
                "path": "strategy.parameters.hedge_zone_concurrency_policy",
                "features": sorted(zone_peers),
                "supported": ["exclusive", "explicit_cooperative"],
                "message": "Recovery engines cannot be composed around Hedge Zone without an explicit concurrency contract.",
            })
        elif policy == "explicit_cooperative":
            allowed = set(p.get("hedge_zone_allowed_engines") or [])
            unknown = zone_peers - allowed
            if unknown:
                blockers.append({
                    "id": "INCOMPLETE-HEDGE-ZONE-COOPERATION",
                    "path": "strategy.parameters.hedge_zone_allowed_engines",
                    "missing": sorted(unknown),
                })

    if "strategy.exit.account_money" in paths:
        if p.get("ownership_scope") != "account" or ir.controls.get("account_wide_close_approved") is not True:
            blockers.append({
                "id": "ACCOUNT-WIDE-OWNERSHIP-NOT-APPROVED",
                "path": "strategy.parameters.ownership_scope",
                "message": "Account-wide exits require ownership_scope=account and explicit operator approval.",
            })

    has_daily = "strategy.exit.daily_target" in paths or "risk.daily_loss" in paths
    has_sessions = "strategy.time.sessions" in paths
    if has_daily or has_sessions:
        policy = ir.runtime.get("time_policy")
        if not isinstance(policy, dict):
            blockers.append({
                "id": "MISSING-TIME-POLICY", "path": "runtime.time_policy",
                "message": "Daily accounting and session scheduling require an explicit clock policy.",
            })
        else:
            daily_basis = policy.get("daily_basis")
            session_basis = policy.get("session_basis")
            valid_bases = {"server", "local", "utc", "fixed_offset"}
            used_bases: set[Any] = set()
            if has_daily:
                used_bases.add(daily_basis)
                if daily_basis not in valid_bases:
                    blockers.append({"id": "INVALID-DAILY-TIME-BASIS", "path": "runtime.time_policy.daily_basis", "value": daily_basis})
                if policy.get("history_sync_required") is not True:
                    blockers.append({"id": "HISTORY-SYNC-MUST-BE-REQUIRED", "path": "runtime.time_policy.history_sync_required"})
                if policy.get("cashflow_policy") not in {"exclude", "include"}:
                    blockers.append({"id": "MISSING-CASHFLOW-POLICY", "path": "runtime.time_policy.cashflow_policy"})
                boundary = policy.get("day_boundary_minutes", 0)
                if not isinstance(boundary, int) or not 0 <= boundary < 24 * 60:
                    blockers.append({"id": "INVALID-DAY-BOUNDARY", "path": "runtime.time_policy.day_boundary_minutes", "value": boundary})
            if has_sessions:
                used_bases.add(session_basis)
                if session_basis not in valid_bases:
                    blockers.append({"id": "INVALID-SESSION-TIME-BASIS", "path": "runtime.time_policy.session_basis", "value": session_basis})
            used_bases.discard(None)
            required_dst = "platform_clock" if used_bases & {"server", "local"} else "fixed_no_dst"
            if policy.get("dst_policy") != required_dst:
                blockers.append({
                    "id": "INVALID-DST-POLICY", "path": "runtime.time_policy.dst_policy",
                    "value": policy.get("dst_policy"), "required": required_dst,
                    "message": "Clock/DST behavior must be explicit for reproducible day and session boundaries.",
                })
            if has_daily and has_sessions and daily_basis != session_basis and policy.get("mixed_clock_approved") is not True:
                blockers.append({
                    "id": "TIME-BASIS-MISMATCH", "path": "runtime.time_policy",
                    "daily_basis": daily_basis, "session_basis": session_basis,
                    "message": "Daily accounting and sessions must share a clock unless mixed-clock behavior is explicitly approved.",
                })
            if "fixed_offset" in used_bases:
                offset = policy.get("utc_offset_minutes")
                if not isinstance(offset, int) or not -14 * 60 <= offset <= 14 * 60:
                    blockers.append({"id": "INVALID-TIME-OFFSET", "path": "runtime.time_policy.utc_offset_minutes", "value": offset})

    recovery_features = {
        "strategy.hedge.standard", "strategy.hedge.zone",
        "strategy.reverse_entry", "strategy.lot_balance",
    } & paths
    if has_sessions and recovery_features:
        recovery_policy = p.get("recovery_session_policy")
        if recovery_policy not in {"respect_sessions", "allow_recovery_outside_sessions"}:
            blockers.append({
                "id": "RECOVERY-SESSION-POLICY-REQUIRED",
                "path": "strategy.parameters.recovery_session_policy",
                "features": sorted(recovery_features),
                "supported": ["respect_sessions", "allow_recovery_outside_sessions"],
            })

    if "strategy.sniper.cross_chain" in paths and p.get("cross_sniper_magic_pair_only") is False:
        if p.get("ownership_scope") != "account" or ir.controls.get("account_wide_close_approved") is not True:
            blockers.append({
                "id": "CROSS-SNIPER-ACCOUNT-SCOPE-NOT-APPROVED",
                "path": "strategy.parameters.cross_sniper_magic_pair_only",
                "message": "Account-wide cross-chain Sniper requires account ownership and explicit operator approval.",
            })

    unknown_policy = p.get("unknown_outcome_policy", "block_until_reconciled")
    if unknown_policy not in {"block_until_reconciled", "retry_after_timeout"}:
        blockers.append({
            "id": "INVALID-UNKNOWN-OUTCOME-POLICY",
            "path": "strategy.parameters.unknown_outcome_policy",
            "value": unknown_policy,
        })
    if bool(p.get("async_execution")):
        if p.get("execution_idempotency_policy") != "reconcile_before_retry":
            blockers.append({
                "id": "ASYNC-IDEMPOTENCY-POLICY-REQUIRED",
                "path": "strategy.parameters.execution_idempotency_policy",
                "message": "Async execution is blocked without reconcile-before-retry semantics.",
            })
        if unknown_policy != "block_until_reconciled":
            blockers.append({
                "id": "ASYNC-UNKNOWN-OUTCOME-MUST-BLOCK",
                "path": "strategy.parameters.unknown_outcome_policy",
                "message": "Async requests may not be retried from timeout alone; terminal truth or operator reconciliation is required.",
            })

    if "strategy.sniper.cross_chain" in paths and bool(p.get("stop_sniper_during_hedge")):
        if p.get("sniper_hedge_pause_scope") not in {"hedge_origin_only", "any_opposite_position"}:
            blockers.append({
                "id": "SNIPER-HEDGE-PAUSE-SCOPE-REQUIRED",
                "path": "strategy.parameters.sniper_hedge_pause_scope",
            })

    if bool(p.get("dca_outside_session")) and (
        "strategy.exit.daily_target" in paths or "risk.daily_loss" in paths
    ):
        if p.get("risk_precedence_policy", "daily_halt_preempts_exposure") != "daily_halt_preempts_exposure":
            blockers.append({
                "id": "INVALID-RISK-PRECEDENCE",
                "path": "strategy.parameters.risk_precedence_policy",
                "message": "Daily halt must preempt all exposure, including DCA outside session.",
            })

    return blockers
