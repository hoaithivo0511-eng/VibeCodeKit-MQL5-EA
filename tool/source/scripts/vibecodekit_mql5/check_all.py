"""vkmql-check all — the full v3 release gate orchestrator.

Runs every gate stage in the canonical order and produces a single summary
envelope. Stages that require a real MT5 environment (compile / backtest)
are marked ``UNTESTABLE`` here rather than faked, so the orchestrator can
never fabricate a PASS.

Order (PRD §command surface):

    scan -> contract -> lint -> compile -> backtest
         -> stress -> review -> evidence -> release-policy

Each stage is PASS / FAIL / UNTESTABLE / SKIPPED. The overall gate is
release-eligible only when every required stage is PASS and the evidence hash
chain verifies; any UNTESTABLE stage blocks release-eligibility (it is not a
pass).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit
from . import contract_check as cc
from . import evidence_attestation as ea
from . import stress_matrix_v2 as sm
from . import release_approval as ra
from . import retro_guard_check as rgc
from . import spec_schema_v26 as sv

TOOL = "vkmql-check-all"

STAGE_ORDER: tuple[str, ...] = (
    "scan",
    "contract",
    "lint",
    "compile",
    "backtest",
    "quality",
    "forward",
    "stress",
    "review",
    "retro",
    "approval",
    "evidence",
    "release-policy",
)

# Stages that genuinely need a real MT5/Wine environment. In this sandbox they
# are reported UNTESTABLE (never PASS) unless evidence already exists on disk.
_ENV_STAGES = {"compile", "backtest"}


@dataclass
class StageResult:
    name: str
    status: str  # PASS | FAIL | UNTESTABLE | SKIPPED
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class CheckAllResult:
    ok: bool
    release_eligible: bool
    project_dir: str
    stages: list[StageResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "release_eligible": self.release_eligible,
            "project_dir": self.project_dir,
            "stages": [s.to_dict() for s in self.stages],
        }


def _stage_scan(project_dir: Path) -> StageResult:
    # Recursively scan EVERY .mq5 under Experts/. MT5 projects commonly nest as
    # Experts/<Name>/<Name>.mq5, so a flat glob would miss the real EA and
    # silently SKIP the risk scan. We scan all files, not just the first.
    experts_dir = project_dir / "Experts"
    experts = sorted(experts_dir.rglob("*.mq5")) if experts_dir.is_dir() else []
    if not experts:
        return StageResult("scan", "SKIPPED", "no Experts/**/*.mq5 to scan")
    try:
        from . import scan_ea

        total_high = 0
        total_behaviours = 0
        flagged: list[str] = []
        for src in experts:
            rep = scan_ea.analyze_source(
                src.read_text(encoding="utf-8", errors="replace"), source=str(src)
            )
            high = [f for f in rep.risk_flags if f["severity"] == "high"]
            total_behaviours += len(rep.behaviours)
            if high:
                total_high += len(high)
                flagged.append(src.name)
        if total_high:
            return StageResult(
                "scan", "FAIL",
                f"{total_high} high-severity risk flag(s) across {len(flagged)} file(s): "
                + ", ".join(flagged),
            )
        return StageResult(
            "scan", "PASS",
            f"{len(experts)} EA file(s), {total_behaviours} behaviour(s), no high-risk smells",
        )
    except Exception as exc:  # noqa: BLE001
        return StageResult("scan", "UNTESTABLE", f"scan error: {exc}")


def _stage_contract(project_dir: Path) -> StageResult:
    res = cc.check_project_contract(project_dir)
    return StageResult("contract", "PASS" if res.ok else "FAIL",
                       "; ".join(res.errors) or "contracts intact")


def _writes_blocked(project_dir: Path) -> bool:
    """True when the gate must run read-only over this project tree.

    Running the full gate against a bundled test/fixture/sample project must
    never write evidence into it. A simulated re-run produces only UNTESTABLE
    scenarios, so overwriting a *recorded* report there could silently
    downgrade a real FAIL to UNTESTABLE and mask it. Real user projects (whose
    path does not look like a fixture tree) are unaffected.
    """
    from . import release_policy

    return release_policy.is_fixture_path(project_dir)


def _prior_stress_counts(project_dir: Path) -> dict[str, int] | None:
    """Return the counts of an existing stress report on disk, if parseable."""
    import json

    p = project_dir / sm.REPORT_SUBDIR / sm.REPORT_JSON
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        counts = data.get("counts")
        return counts if isinstance(counts, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _stage_stress(project_dir: Path) -> StageResult:
    # Honest-gate guard: a simulated re-run can only ever produce UNTESTABLE
    # scenarios, so it must NEVER overwrite a report that already records real
    # results (PASS/FAIL) — doing so would mask a recorded FAIL behind a fresh
    # UNTESTABLE and risk a false release. We also never mutate a bundled
    # test/fixture tree. When either guard trips we grade from the recorded
    # report instead (worst-wins) without rewriting it.
    prior = _prior_stress_counts(project_dir)
    prior_recorded = bool(
        prior and ((prior.get("FAIL", 0) or 0) or (prior.get("PASS", 0) or 0))
    )
    # A validator must not mutate evidence that its later evidence stage is
    # about to hash and verify.  The standalone vkmql-check-stress command is
    # responsible for generating reports; check-all evaluates in read-only
    # mode and grades any pre-existing real report via ``prior``.
    res = sm.run_stress_matrix(project_dir, write=False)
    counts = prior if (prior_recorded and prior is not None) else res.counts
    if counts.get("FAIL", 0):
        return StageResult("stress", "FAIL", f"{counts['FAIL']} scenario(s) failed")
    if counts.get("UNTESTABLE", 0):
        return StageResult("stress", "UNTESTABLE",
                           f"{counts['UNTESTABLE']} scenario(s) need a real tester")
    return StageResult("stress", "PASS", "all scenarios proven")


def _stage_evidence(project_dir: Path) -> StageResult:
    chain_path = project_dir / ea.ATTEST_SUBDIR / ea.HASH_CHAIN
    read_only = _writes_blocked(project_dir)
    if read_only and not chain_path.is_file():
        # Auditing a bundled test/fixture tree read-only: we will not write an
        # attestation into it, and there is no pre-existing chain to verify.
        return StageResult("evidence", "UNTESTABLE",
                           "read-only audit (test/fixture tree); no evidence chain written")
    # (Re)build the chain unless writes are blocked: the stress stage may have
    # regenerated evidence, so a stale chain from a previous run would FAIL
    # verification against freshly-written evidence. Rebuilding keeps the gate
    # self-consistent; absence of real evidence still blocks PASS below.
    if not read_only:
        ea.build_hash_chain(project_dir, write=True)
    res = ea.verify_hash_chain(project_dir)
    if not res.ok:
        return StageResult("evidence", "FAIL", "; ".join(res.errors))
    # A valid chain over fake or imported files is still not release evidence.
    # The canonical provenance validator checks trusted execution sources,
    # report structure, artifact hashes and the manifest schema.
    evidence = ea.evaluate_release_evidence(project_dir)
    if evidence.status == "PASS":
        return StageResult("evidence", "PASS", "hash chain and execution provenance verified")
    if evidence.status == "FAIL":
        return StageResult("evidence", "FAIL", "; ".join(evidence.errors) or "provenance validation failed")
    return StageResult("evidence", "UNTESTABLE", "; ".join(evidence.missing) or "release evidence incomplete")


def _stage_quality(project_dir: Path) -> StageResult:
    """Grade the Strategy Tester report's metrics IF one exists.

    Non-breaking: with no real backtest report this is UNTESTABLE (never a
    PASS, never a FAIL), exactly like the compile/backtest env stages, so it
    cannot change the verdict of any project that has no evidence yet.
    """
    report = project_dir / "evidence" / "backtest" / "report.xml"
    if not report.is_file():
        return StageResult("quality", "UNTESTABLE",
                           "no evidence/backtest/report.xml to grade")
    try:
        from . import backtest, backtest_quality, release_policy
        result = backtest.parse_xml_report_file(report)
        trusted = not release_policy.is_fixture_path(report)
        rep = backtest_quality.evaluate(result, source=str(report),
                                        release_trusted=trusted)
        if rep.verdict == "PASS":
            return StageResult("quality", "PASS",
                               f"metrics pass (R2={round(rep.r2,3)}, "
                               f"complex={rep.complex_criterion})")
        if rep.verdict == "WARN":
            return StageResult("quality", "UNTESTABLE",
                               "metrics marginal (WARN) — not release-positive")
        return StageResult("quality", "FAIL",
                           f"metrics {rep.verdict} (R2={round(rep.r2,3)})")
    except Exception as exc:  # noqa: BLE001
        return StageResult("quality", "UNTESTABLE", f"quality error: {exc}")


def _stage_forward(project_dir: Path) -> StageResult:
    """Walk-forward / out-of-sample stability IF both IS+OOS reports exist.

    Non-breaking: UNTESTABLE when the two walk-forward reports are absent
    (the normal case), so it never alters an evidence-free verdict.
    """
    wf = project_dir / "evidence" / "walkforward"
    is_report = wf / "is_report.xml"
    oos_report = wf / "oos_report.xml"
    if not (is_report.is_file() and oos_report.is_file()):
        return StageResult("forward", "UNTESTABLE",
                           "no evidence/walkforward/{is,oos}_report.xml present")
    try:
        from . import backtest, walkforward
        res = walkforward.evaluate(
            backtest.parse_xml_report_file(is_report),
            backtest.parse_xml_report_file(oos_report),
        )
        verdict = getattr(res, "verdict", None) or getattr(res, "status", "")
        if str(verdict).upper() == "PASS":
            return StageResult("forward", "PASS", "walk-forward stable")
        if str(verdict).upper() == "WARN":
            return StageResult("forward", "UNTESTABLE",
                               "walk-forward marginal (WARN)")
        return StageResult("forward", "FAIL", f"walk-forward {verdict}")
    except Exception as exc:  # noqa: BLE001
        return StageResult("forward", "UNTESTABLE", f"forward error: {exc}")


def _stage_env(name: str, project_dir: Path) -> StageResult:
    # Honour pre-recorded evidence only when the canonical manifest proves the
    # execution source. File presence alone is intentionally insufficient.
    markers = {
        "compile": project_dir / "evidence" / "compile" / "compile-log.txt",
        "backtest": project_dir / "evidence" / "backtest" / "report.xml",
    }
    marker = markers.get(name)
    if marker and marker.is_file():
        from .provenance import validate_release_provenance
        prov = validate_release_provenance(project_dir)
        if prov.status == "PASS":
            return StageResult(name, "PASS", f"trusted evidence: {marker.name}")
        if prov.status == "FAIL":
            return StageResult(name, "FAIL", "; ".join(prov.errors) or "untrusted evidence provenance")
        return StageResult(name, "UNTESTABLE", "evidence exists but trusted provenance is incomplete")
    return StageResult(name, "UNTESTABLE", "requires a real MT5/Wine environment")


def _stage_simple(name: str) -> StageResult:
    # lint / review: advisory placeholders that don't block in this sandbox.
    return StageResult(name, "SKIPPED", "not run in this environment")


def _release_target(project_dir: Path) -> str:
    result = sv.load_spec_v26(project_dir / "EA-SPEC.yaml")
    if not result.ok:
        return "draft"
    governance = result.spec.get("governance", {})
    return governance.get("release_target", "draft") if isinstance(governance, dict) else "draft"


def _stage_retro(project_dir: Path) -> StageResult:
    result = rgc.evaluate(project_dir)
    return StageResult("retro", result.status, "; ".join(result.errors) or "guards proven")


def _stage_approval(project_dir: Path) -> StageResult:
    target = _release_target(project_dir)
    result = ra.validate(project_dir, target)
    if result.status == "NOT_REQUIRED":
        return StageResult("approval", "SKIPPED", f"not required for target={target}")
    return StageResult("approval", result.status, "; ".join(result.errors) or "approval bound to hashes")


def run_check_all(project_dir: Path | str) -> CheckAllResult:
    project_dir = Path(project_dir)
    res = CheckAllResult(ok=True, release_eligible=False, project_dir=str(project_dir))
    if not project_dir.is_dir():
        res.ok = False
        res.stages.append(StageResult("scan", "FAIL", f"project dir not found: {project_dir}"))
        return res

    runners: dict[str, Callable[[], StageResult]] = {
        "scan": lambda: _stage_scan(project_dir),
        "contract": lambda: _stage_contract(project_dir),
        "lint": lambda: _stage_simple("lint"),
        "compile": lambda: _stage_env("compile", project_dir),
        "backtest": lambda: _stage_env("backtest", project_dir),
        "quality": lambda: _stage_quality(project_dir),
        "forward": lambda: _stage_forward(project_dir),
        "stress": lambda: _stage_stress(project_dir),
        "review": lambda: _stage_simple("review"),
        "retro": lambda: _stage_retro(project_dir),
        "approval": lambda: _stage_approval(project_dir),
        "evidence": lambda: _stage_evidence(project_dir),
        "release-policy": lambda: StageResult("release-policy", "PASS", "policy evaluated"),
    }
    for name in STAGE_ORDER:
        res.stages.append(runners[name]())

    statuses = {s.name: s.status for s in res.stages}
    has_fail = any(s.status == "FAIL" for s in res.stages)
    res.ok = not has_fail
    # Route the final verdict through the kit's single canonical predicate so a
    # build can never be "release-eligible" here but "blocked" elsewhere. A
    # stage is only eligibility-positive when it is an explicit PASS;
    # UNTESTABLE / SKIPPED / FAIL all count as not-ok for that gate.
    from . import release_policy

    def _pass(name: str) -> bool:
        return statuses.get(name) == "PASS"

    res.release_eligible = release_policy.compute_release_eligible(
        command_ok=res.ok,
        compile_ok=_pass("compile"),
        backtest_ok=_pass("backtest"),
        gate_ok=_pass("contract"),
        evidence_ok=_pass("evidence"),
        stress_ok=_pass("stress"),
        hash_chain_ok=_pass("evidence"),
        quality_ok=_pass("quality"),
        forward_ok=_pass("forward"),
        retro_ok=_pass("retro"),
        owner_approval_ok=_pass("approval"),
        target_ok=_release_target(project_dir) == "live",
    )
    return res


def render_report(res: CheckAllResult) -> str:
    lines = [
        "# vkmql-check all — RELEASE GATE",
        "",
        f"- Project: `{res.project_dir}`",
        f"- Release eligible: **{res.release_eligible}**",
        "",
        "| Stage | Status | Detail |",
        "|---|---|---|",
    ]
    for s in res.stages:
        lines.append(f"| {s.name} | {s.status} | {s.detail} |")
    lines += [
        "",
        "> UNTESTABLE stages (compile/backtest/stress without a real MT5 run)",
        "> block release-eligibility. No evidence = no release.",
        "",
    ]
    # Actionable hint: a FAILing contract stage almost always means the
    # governance artifacts were never scaffolded. Point the operator at the
    # exact commands that produce them instead of leaving a bare FAIL.
    if any(s.name == "contract" and s.status == "FAIL" for s in res.stages):
        lines += [
            "> Contract stage FAILED — the project is missing required contract",
            "> artifacts (EA-SPEC.yaml, AI-BUILD-CONTRACT.md/.json). Scaffold them",
            "> with `vkmql-new spec <dir>` then `vkmql-new contract <dir>` and",
            "> re-run the gate. (A bare `build` does not emit contract artifacts.)",
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Run the full v2.6 release gate.")
    ap.add_argument("project_dir", type=Path, help="Path to the EA project directory.")
    ap.add_argument("--out", type=Path, default=None, help="Write the report markdown here.")
    ap.add_argument(
        "--require-release",
        action="store_true",
        help=(
            "CI release mode: exit non-zero unless the project is "
            "release-eligible (UNTESTABLE/SKIPPED stages block release)."
        ),
    )
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    res = run_check_all(args.project_dir)
    # In normal mode the gate is "ok" when no stage FAILs (UNTESTABLE is
    # tolerated for audit). In --require-release mode the gate only passes
    # when the canonical predicate says the build is release-eligible.
    gate_pass = res.release_eligible if args.require_release else res.ok
    exit_code = 0 if gate_pass else 1
    md = render_report(res)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
    if not args.emit_json:
        sys.stdout.write(md if args.out is None else f"wrote {args.out}\n")

    env = Envelope(
        tool=TOOL,
        ok=gate_pass,
        exit_code=exit_code,
        summary=(
            f"gate {'ok' if res.ok else 'FAILED'}; "
            f"release_eligible={res.release_eligible}"
            + ("; require-release" if args.require_release else "")
        ),
        data=res.to_dict(),
        evidence=[str(args.project_dir)],
        matrix_dim="governance",
        matrix_axis="release-gate",
        matrix_status="PASS" if res.release_eligible else ("FAIL" if not res.ok else "WARN"),
    )
    maybe_emit(args, env)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
