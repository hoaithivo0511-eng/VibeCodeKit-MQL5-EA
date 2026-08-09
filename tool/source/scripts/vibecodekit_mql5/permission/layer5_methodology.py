"""Permission Layer 5 — METHODOLOGY-GATE (RRI 8-step completed).

Asks :mod:`vibecodekit_mql5.rri.step_workflow` whether the steps required
by ``mode`` all have ``.done`` sentinels in the state directory.

This layer is only enforced for TEAM and ENTERPRISE modes. Personal mode
trivially passes — but we still emit a JSON report so the orchestrator
can show why the layer was skipped.

when ``activity_threshold`` is supplied (or the mode default
in :data:`step_sentinel.DEFAULT_THRESHOLDS` is honoured via
``enforce_activities=True``), the layer additionally audits each
sentinel's companion ``step-N-<name>.md`` for ticked ``## Activities``
checkboxes and fails the gate when the ratio is below the threshold.
This prevents an operator (or LLM agent) from rubber-stamping the
methodology gate by ``touch``-ing the sentinel without filling the step
output.

when ``enforce_sign_off`` is supplied, the layer additionally
audits ``step-4-blueprint.md`` for the homeowner ``APPROVED by …`` line
and (in team / enterprise modes) ``contract.md`` for the ``CONFIRM by
…`` line. This wires the Triangle of Power sign-off ritual into the
permission gate so a build cannot ship while the human Homeowner has
not personally approved the architecture and the contract.

when ``enforce_no_open_escalation`` is supplied, the layer
additionally consults the actor-to-actor escalation audit log
(``.mql5-audit/escalations.jsonl`` by default) and fails the gate while
any **level-3** escalation is still OPEN. Personal mode treats this as
informational (the count is still reported in the envelope), TEAM and
ENTERPRISE modes treat any OPEN level-3 escalation as a hard block.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..rri import escalation as esc
from ..rri import sign_off as so
from ..rri import step_sentinel as ss
from ..rri import step_workflow as sw


def gate(
    state_dir: Path,
    mode: str = "personal",
    *,
    enforce_activities: bool = False,
    activity_threshold: float | None = None,
    enforce_sign_off: bool = False,
    blueprint_path: Path | None = None,
    contract_path: Path | None = None,
    enforce_no_open_escalation: bool = False,
    escalation_log: Path | None = None,
) -> dict:
    """Run the methodology gate.

    Parameters
    ----------
    state_dir:
        Directory containing ``<step>.done`` sentinels (and optionally
        their companion ``step-N-<name>.md`` outputs).
    mode:
        ``personal`` / ``team`` / ``enterprise``.
    enforce_activities:
        When ``True``, additionally audit ticked ``## Activities``
        checkboxes in each step output and fail the gate if the ratio
        drops below ``activity_threshold`` (or the mode default).
    activity_threshold:
        Override the ratio used by ``enforce_activities``. Falls back to
        :data:`step_sentinel.DEFAULT_THRESHOLDS[mode]`.
    enforce_sign_off:
        when ``True``, additionally audit the homeowner
        sign-off lines (``APPROVED by …`` on blueprint, ``CONFIRM by
        …`` on contract). Personal mode requires only the blueprint
        line; team / enterprise require both.
    blueprint_path / contract_path:
        Optional explicit paths used by the sign-off audit. When
        ``None``, the audit falls back to ``DEFAULT_BLUEPRINT_NAMES`` /
        ``DEFAULT_CONTRACT_NAMES`` resolution.
    enforce_no_open_escalation:
        when ``True``, consult the escalation audit log
        and fail TEAM / ENTERPRISE gates while any level-3 escalation
        remains OPEN. Personal mode reports the count without
        failing.
    escalation_log:
        Override path for the JSONL audit log used by
        ``enforce_no_open_escalation``. Defaults to
        ``rri.escalation.DEFAULT_LOG`` (``.mql5-audit/escalations.jsonl``).
    """
    if mode not in sw.MODE_REQUIRED_STEPS:
        raise ValueError(f"unknown mode: {mode!r}")
    if (
        mode == "personal"
        and not enforce_activities
        and not enforce_sign_off
        and not enforce_no_open_escalation
    ):
        return {
            "ok": True,
            "mode": mode,
            "skipped": True,
            "reason": "personal mode does not require methodology gate",
            "state_dir": str(state_dir),
        }
    required = sw.required_steps(mode)
    completed = sw.completed_steps(state_dir) if state_dir.exists() else ()
    missing = [s for s in required if s not in completed]

    result: dict = {
        "ok": not missing,
        "mode": mode,
        "state_dir": str(state_dir),
        "required_steps": list(required),
        "completed_steps": list(completed),
        "missing_steps": missing,
    }

    if enforce_activities:
        threshold = (
            activity_threshold
            if activity_threshold is not None
            else ss.DEFAULT_THRESHOLDS.get(mode, 1.0)
        )
        audits: list[dict] = []
        under_threshold: list[str] = []
        for step in required:
            if step not in completed:
                continue
            audit = ss.audit_step_output(step, state_dir=state_dir)
            audits.append(audit.to_dict())
            if not ss.passes_threshold(audit, threshold):
                under_threshold.append(step)
        result["activity_threshold"] = threshold
        result["activity_audits"] = audits
        result["activity_under_threshold"] = under_threshold
        if under_threshold:
            result["ok"] = False

    if enforce_no_open_escalation:
        log_path = escalation_log if escalation_log is not None else esc.DEFAULT_LOG
        records = esc.load_log(log_path)
        open_level3 = [
            r.to_dict() for r in records
            if r.status == "OPEN" and r.level == 3
        ]
        result["escalation_log"] = str(log_path)
        result["escalation_open_level3_count"] = len(open_level3)
        result["escalation_open_level3"] = open_level3
        result["escalation_enforced"] = mode != "personal"
        if open_level3 and mode != "personal":
            result["ok"] = False

    if enforce_sign_off:
        # Personal mode only requires the BLUEPRINT APPROVED line; the
        # contract is a team/enterprise artefact in .
        require_contract = mode != "personal"
        ok, sign_off_audits = so.audit_sign_off(
            blueprint_path=blueprint_path,
            contract_path=contract_path,
            require_contract=require_contract,
            state_dir=state_dir,
        )
        result["sign_off_required_contract"] = require_contract
        result["sign_off_audits"] = [a.to_dict() for a in sign_off_audits]
        result["sign_off_ok"] = ok
        if not ok:
            result["ok"] = False

    return result


def main() -> int:
    ap = argparse.ArgumentParser(prog="mql5-permission-layer5")
    ap.add_argument("--state-dir", type=Path, default=Path(".rri-state"))
    ap.add_argument("--mode", choices=tuple(sw.MODE_REQUIRED_STEPS), default="personal")
    ap.add_argument(
        "--enforce-activities", action="store_true",
        help="Audit each step output for ticked ## Activities checkboxes "
        "and fail the gate when below threshold ().",
    )
    ap.add_argument(
        "--activity-threshold", type=float, default=None,
        help="Fractional activity-completion threshold (0.0..1.0). "
        "Defaults to mode-based value in step_sentinel.DEFAULT_THRESHOLDS.",
    )
    ap.add_argument(
        "--enforce-sign-off", action="store_true",
        help="\u2014 audit the homeowner APPROVED line on "
        "step-4-blueprint.md and CONFIRM line on contract.md.",
    )
    ap.add_argument(
        "--blueprint", type=Path, default=None,
        help="Path to step-4-blueprint.md (sign-off). Auto-resolved "
        "from state-dir / cwd when omitted.",
    )
    ap.add_argument(
        "--contract", type=Path, default=None,
        help="Path to contract.md (sign-off). Auto-resolved "
        "from state-dir / cwd when omitted.",
    )
    ap.add_argument(
        "--enforce-no-open-escalation", action="store_true",
        help="fail TEAM / ENTERPRISE gates while any "
        "level-3 escalation in .mql5-audit/escalations.jsonl is OPEN.",
    )
    ap.add_argument(
        "--escalation-log", type=Path, default=None,
        help="Override the JSONL audit log consulted by "
        "--enforce-no-open-escalation (default: .mql5-audit/escalations.jsonl).",
    )
    args = ap.parse_args()
    result = gate(
        args.state_dir, args.mode,
        enforce_activities=args.enforce_activities,
        activity_threshold=args.activity_threshold,
        enforce_sign_off=args.enforce_sign_off,
        blueprint_path=args.blueprint,
        contract_path=args.contract,
        enforce_no_open_escalation=args.enforce_no_open_escalation,
        escalation_log=args.escalation_log,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
