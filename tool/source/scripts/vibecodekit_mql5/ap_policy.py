"""Profile-aware anti-pattern policy.

AP checks are internal heuristics. This policy makes thresholds explicit and
profile-aware instead of pretending one rule fits all EA architectures.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
import json
from pathlib import Path
import re

from . import rule_registry as rr


def read_mql_text(path: Path, project: Path | None = None) -> str:
    chunks = []
    if project is not None:
        for p in project.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".mq5", ".mqh"}:
                chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
    if path.is_file():
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


@dataclass
class APPolicy:
    profile: str
    ap5_input_threshold: int
    ap5_severity: str
    ml_release_blocking: bool

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["methodology"] = "internal_heuristic"
        d["industry_standard"] = False
        return d


PROFILE_POLICIES = {
    "simple-scalper": APPolicy("simple-scalper", 8, "warn", True),
    "trend-following": APPolicy("trend-following", 12, "info", True),
    "grid": APPolicy("grid", 30, "info", True),
    "dca": APPolicy("dca", 30, "info", True),
    "portfolio": APPolicy("portfolio", 25, "info", True),
    "ml-assisted": APPolicy("ml-assisted", 20, "warn", True),
    "prop-firm-risk": APPolicy("prop-firm-risk", 12, "warn", True),
    "default": APPolicy("default", 12, "info", True),
}


def policy_for_profile(profile: str | None) -> APPolicy:
    return PROFILE_POLICIES.get((profile or "default").strip().lower(), PROFILE_POLICIES["default"])


def count_inputs_mql5(text: str) -> int:
    return len(re.findall(r"^\s*input\s+", text, flags=re.M))


def detect_ml_usage(text: str) -> bool:
    patterns = [r"OnnxCreate", r"OnnxRun", r"#include\s+<ONNX\.mqh>", r"\.onnx\b", r"model\.onnx"]
    return any(re.search(p, text, flags=re.I) for p in patterns)


def evaluate_ap5(text: str, profile: str | None = None) -> dict[str, Any]:
    policy = policy_for_profile(profile)
    n = count_inputs_mql5(text)
    triggered = n > policy.ap5_input_threshold
    return {
        "ap_id": "AP-5",
        "rule_id": "LINT-AP-5",
        "profile": policy.profile,
        "input_count": n,
        "threshold": policy.ap5_input_threshold,
        "triggered": triggered,
        "severity": policy.ap5_severity if triggered else "none",
        "message": "Input count is high for selected profile; group/document parameters." if triggered else "Input count within selected profile threshold.",
        "methodology": "internal_heuristic",
        "industry_standard": False,
    }


def evaluate_ap19_ml(text: str, ml_validation: dict[str, Any] | None = None, profile: str | None = None) -> dict[str, Any]:
    policy = policy_for_profile(profile)
    uses_ml = detect_ml_usage(text)
    validation = ml_validation or {}
    required_keys = ["model_sha256", "feature_schema_sha256", "oos_report_sha256", "strategy_tester_report_sha256", "fallback_defined"]
    missing = [k for k in required_keys if not validation.get(k)]
    release_blocking = bool(uses_ml and policy.ml_release_blocking and missing)
    return {
        "ap_id": "AP-19",
        "rule_id": "BP-19",
        "profile": policy.profile,
        "uses_ml_or_onnx": uses_ml,
        "required_validation": required_keys if uses_ml else [],
        "missing_validation": missing if uses_ml else [],
        "severity": "error" if release_blocking else ("warn" if uses_ml else "none"),
        "release_blocking": release_blocking,
        "message": "ML/ONNX EA requires model, feature, OOS, Strategy Tester, and fallback evidence." if release_blocking else "No blocking ML validation issue detected.",
        "methodology": "internal_heuristic",
        "industry_standard": False,
    }



def evaluate_architecture_ap_rules(text: str, profile: str | None = None) -> list[dict[str, Any]]:
    prof = (profile or "default").lower()
    is_grid_like = prof in {"grid", "dca", "grid-safe", "portfolio"} or any(k in text.lower() for k in ["grid", "basket", "dca", "hedge"])
    checks: list[dict[str, Any]] = []
    raw_close_loop = bool(re.search(r"for\s*\([^)]*PositionsTotal\s*\([^)]*\)[\s\S]{0,1500}?\.PositionClose\s*\(", text, flags=re.I | re.M))
    has_async = "CAsyncTradeExecutor" in text or "AsyncTradeExecutor" in text
    has_hook = "OnTradeTransaction" in text
    has_retry = "Fallback" in text or "retry" in text.lower()
    has_state = "PersistentStateStore" in text or "GlobalVariable" in text or "StateStore" in text
    has_seed = "AccountSeed" in text or "ACCOUNT_LOGIN" in text
    has_dd_stop = bool(re.search(r"MaxDD|MustStop|Stop\s*\(", text, flags=re.I))
    has_freeze = bool(re.search(r"Freeze|ShouldFreeze", text, flags=re.I))

    if is_grid_like:
        checks.append({
            "ap_id": rr.ARCH_GRID_SYNC_CLOSE,
            "legacy_ap_id": "AP-22",
            "name": "Grid/Basket sync close loop",
            "triggered": raw_close_loop and not has_async,
            "severity": "error" if raw_close_loop and not has_async else "none",
            "release_blocking": raw_close_loop and not has_async,
            "message": "Grid/basket EA should not use raw synchronous PositionClose loop without AsyncTradeExecutor.",
            "methodology": "internal_heuristic",
            "industry_standard": False,
        })
        checks.append({
            "ap_id": rr.ARCH_ASYNC_HOOK_MISSING,
            "legacy_ap_id": "AP-23",
            "name": "Missing async transaction hook",
            "triggered": has_async and not has_hook,
            "severity": "error" if has_async and not has_hook else "none",
            "release_blocking": has_async and not has_hook,
            "message": "Async execution requires OnTradeTransaction forwarding to executor.",
            "methodology": "internal_heuristic",
            "industry_standard": False,
        })
        checks.append({
            "ap_id": rr.ARCH_CLOSE_RETRY_MISSING,
            "legacy_ap_id": "AP-24",
            "name": "Async close retry/fallback",
            "triggered": has_async and not has_retry,
            "severity": "warn" if has_async and not has_retry else "none",
            "release_blocking": False,
            "message": "Async close engine should expose retry/fallback behavior.",
            "methodology": "internal_heuristic",
            "industry_standard": False,
        })
        checks.append({
            "ap_id": rr.ARCH_STATE_PERSIST_MISSING,
            "legacy_ap_id": "AP-25",
            "name": "Grid/DCA persistent state",
            "triggered": not has_state,
            "severity": "error" if not has_state else "none",
            "release_blocking": not has_state,
            "message": "Grid/DCA EA should persist recovery state.",
            "methodology": "internal_heuristic",
            "industry_standard": False,
        })
        checks.append({
            "ap_id": rr.ARCH_ACCOUNT_SEED_MISSING,
            "legacy_ap_id": "AP-26",
            "name": "Multi-account deterministic seed",
            "triggered": "multi" in text.lower() and not has_seed,
            "severity": "warn" if "multi" in text.lower() and not has_seed else "none",
            "release_blocking": False,
            "message": "Multi-account strategy should use deterministic account seed divergence.",
            "methodology": "internal_heuristic",
            "industry_standard": False,
        })
        checks.append({
            "ap_id": rr.ARCH_DD_FREEZE_MISSING,
            "legacy_ap_id": "AP-27",
            "name": "Basket trailing without hard DD/freeze stop",
            "triggered": not (has_dd_stop and has_freeze),
            "severity": "error" if not (has_dd_stop and has_freeze) else "none",
            "release_blocking": not (has_dd_stop and has_freeze),
            "message": "Grid/basket EA requires hard max DD stop and freeze logic.",
            "methodology": "internal_heuristic",
            "industry_standard": False,
        })
    return checks

def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Evaluate profile-aware AP policy.")
    ap.add_argument("file")
    ap.add_argument("--project", help="Project root; when provided AP checks read .mq5/.mqh include tree")
    ap.add_argument("--profile", default="default")
    ap.add_argument("--ml-validation-json")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    text = read_mql_text(Path(args.file), Path(args.project) if args.project else None)
    mlv = json.loads(Path(args.ml_validation_json).read_text()) if args.ml_validation_json else None
    report = {
        "profile_policy": policy_for_profile(args.profile).to_dict(),
        "checks": [evaluate_ap5(text, args.profile), evaluate_ap19_ml(text, mlv, args.profile)] + evaluate_architecture_ap_rules(text, args.profile),
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if any(c.get("release_blocking") or c.get("severity") == "error" for c in report["checks"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
