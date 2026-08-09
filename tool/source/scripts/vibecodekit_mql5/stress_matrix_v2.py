"""vkmql-check stress — broker/market stress matrix runner (v3 governance).

Reads a stress matrix (``Tester/matrix.yaml``) describing adverse broker /
market scenarios an EA must survive, evaluates each scenario, and writes a
stress report. The cardinal rule: a static / simulated check NEVER claims
``PASS`` — it can only report ``UNTESTABLE`` (needs a real MT5 tester) so the
report can never overstate what was actually proven.

Per-scenario status:
  PASS        proven on a real (local/remote) MT5 tester run
  FAIL        the EA failed the scenario on a real tester run
  SKIPPED     scenario explicitly skipped in the matrix
  UNTESTABLE  cannot be proven here (simulated/static) — needs real tester

Execution mode of each result is tagged: ``local`` | ``remote`` | ``simulated``.

Default scenarios (when no matrix file is present):
  spread_widening, high_slippage, stop_level_constraint,
  freeze_level_constraint, insufficient_margin, history_missing,
  market_closed, trade_context_busy

Outputs into ``evidence/stress/``:
  stress-matrix-report.json
  stress-matrix-report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit

TOOL = "vkmql-check-stress"
REPORT_SUBDIR = "evidence/stress"
REPORT_JSON = "stress-matrix-report.json"
REPORT_MD = "stress-matrix-report.md"

VALID_STATUSES: frozenset[str] = frozenset({"PASS", "FAIL", "SKIPPED", "UNTESTABLE"})
VALID_MODES: frozenset[str] = frozenset({"local", "remote", "simulated"})

DEFAULT_SCENARIOS: tuple[str, ...] = (
    "spread_widening",
    "high_slippage",
    "stop_level_constraint",
    "freeze_level_constraint",
    "insufficient_margin",
    "history_missing",
    "market_closed",
    "trade_context_busy",
)


@dataclass
class ScenarioResult:
    name: str
    status: str
    mode: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "mode": self.mode, "detail": self.detail}


@dataclass
class StressMatrixResult:
    ok: bool
    project_dir: str
    scenarios: list[ScenarioResult] = field(default_factory=list)
    report_json: str | None = None
    report_md: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        c = {s: 0 for s in VALID_STATUSES}
        for sc in self.scenarios:
            c[sc.status] = c.get(sc.status, 0) + 1
        return c

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "project_dir": self.project_dir,
            "counts": self.counts,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "report_json": self.report_json,
            "report_md": self.report_md,
            "errors": list(self.errors),
        }


def _load_matrix(matrix_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (scenarios, errors) parsed from a matrix.yaml file.

    Accepts BOTH supported layouts:

        scenarios:
          - name: spread_widening

    and the PRD nested form:

        stress_matrix:
          scenarios:
            - name: custom_remote
              status: PASS
              mode: remote

    A *missing* matrix file falls back to the default scenarios. But a matrix
    file that exists with a malformed structure is a hard error — it is NOT
    silently replaced by the defaults — so a typo can never hide scenarios.
    """
    if not matrix_path.is_file():
        return [{"name": n} for n in DEFAULT_SCENARIOS], []
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [], [f"invalid matrix yaml: {exc}"]

    if data is None:
        return [], [
            "matrix yaml is empty: expected a 'scenarios' "
            "(or 'stress_matrix.scenarios') list"
        ]

    # Locate the scenarios list across the supported layouts.
    if isinstance(data, list):
        raw: Any = data
    elif isinstance(data, dict):
        if isinstance(data.get("scenarios"), list):
            raw = data["scenarios"]
        elif (
            isinstance(data.get("stress_matrix"), dict)
            and isinstance(data["stress_matrix"].get("scenarios"), list)
        ):
            raw = data["stress_matrix"]["scenarios"]
        else:
            return [], [
                "matrix yaml has no 'scenarios' list "
                "(top-level or under 'stress_matrix')"
            ]
    else:
        return [], [f"matrix yaml must be a mapping or list, got {type(data).__name__}"]

    out: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, str):
            out.append({"name": entry})
        elif isinstance(entry, dict) and entry.get("name"):
            out.append(entry)
        else:
            return [], [f"invalid scenario entry (needs a 'name'): {entry!r}"]
    if not out:
        return [], ["matrix 'scenarios' list is empty"]
    return out, []


def _evaluate_scenario(entry: dict[str, Any], *, mode: str) -> ScenarioResult:
    """Evaluate a single scenario.

    Without a real MT5 tester (local/remote) connected, every scenario is
    reported ``UNTESTABLE`` (never PASS). A matrix entry may carry a
    pre-recorded real-tester result via ``status`` + ``mode`` keys (e.g. from
    a remote worker run); those are honoured when the mode is real.
    """
    name = str(entry.get("name"))
    if entry.get("skip") is True:
        return ScenarioResult(name=name, status="SKIPPED", mode=mode, detail="skipped via matrix")

    recorded_status = str(entry.get("status", "")).upper()
    recorded_mode = str(entry.get("mode", "")).lower()
    if recorded_status in {"PASS", "FAIL"} and recorded_mode in {"local", "remote"}:
        # Honour an externally-recorded REAL tester result.
        return ScenarioResult(
            name=name,
            status=recorded_status,
            mode=recorded_mode,
            detail=str(entry.get("detail", "recorded from real MT5 tester run")),
        )

    # Static/simulated path: cannot prove survival — must not claim PASS.
    return ScenarioResult(
        name=name,
        status="UNTESTABLE",
        mode="simulated",
        detail="no real MT5 tester available; static check cannot assert PASS",
    )


def run_stress_matrix(
    project_dir: Path | str,
    matrix_path: Path | str | None = None,
    *,
    mode: str = "simulated",
    write: bool = True,
) -> StressMatrixResult:
    """Run the stress matrix for a project and (optionally) write the report."""
    project_dir = Path(project_dir)
    if mode not in VALID_MODES:
        mode = "simulated"
    mpath = Path(matrix_path) if matrix_path else project_dir / "Tester" / "matrix.yaml"
    res = StressMatrixResult(ok=True, project_dir=str(project_dir))

    entries, errors = _load_matrix(mpath)
    res.errors.extend(errors)
    if errors:
        res.ok = False
        return res

    for entry in entries:
        res.scenarios.append(_evaluate_scenario(entry, mode=mode))

    # The matrix "passes" only if there are no FAILs. UNTESTABLE is not a pass
    # but is not a hard fail either — it blocks release-eligibility downstream.
    res.ok = res.counts.get("FAIL", 0) == 0

    if write:
        out_dir = project_dir / REPORT_SUBDIR
        out_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "schema_version": "2.6",
            "generated_by": TOOL,
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "matrix_path": str(mpath),
            "counts": res.counts,
            "scenarios": [s.to_dict() for s in res.scenarios],
            "all_proven": all(s.status == "PASS" for s in res.scenarios) and bool(res.scenarios),
        }
        jpath = out_dir / REPORT_JSON
        mdpath = out_dir / REPORT_MD
        jpath.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        mdpath.write_text(render_report(res), encoding="utf-8")
        res.report_json = str(jpath)
        res.report_md = str(mdpath)
    return res


def render_report(res: StressMatrixResult) -> str:
    counts = res.counts
    lines = [
        "# STRESS MATRIX REPORT",
        "",
        f"- Project: `{res.project_dir}`",
        f"- Scenarios: {len(res.scenarios)} "
        f"(PASS={counts['PASS']}, FAIL={counts['FAIL']}, "
        f"SKIPPED={counts['SKIPPED']}, UNTESTABLE={counts['UNTESTABLE']})",
        "",
        "| Scenario | Status | Mode | Detail |",
        "|---|---|---|---|",
    ]
    for s in res.scenarios:
        lines.append(f"| {s.name} | {s.status} | {s.mode} | {s.detail} |")
    lines += [
        "",
        "> A simulated/static check is reported UNTESTABLE — never PASS.",
        "> Only a real MT5 Strategy Tester run (local or remote worker) can",
        "> assert PASS. UNTESTABLE scenarios block release-eligibility.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=TOOL, description="Run the broker/market stress matrix.")
    ap.add_argument("project_dir", type=Path, help="Path to the EA project directory.")
    ap.add_argument("--matrix", type=Path, default=None,
                    help="Path to matrix.yaml (default: <project>/Tester/matrix.yaml).")
    ap.add_argument("--mode", choices=sorted(VALID_MODES), default="simulated",
                    help="Execution mode hint for recorded results (default: simulated).")
    ap.add_argument("--no-write", action="store_true", help="Do not write report files.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    res = run_stress_matrix(
        args.project_dir, args.matrix, mode=args.mode, write=not args.no_write
    )
    if not args.emit_json:
        sys.stdout.write(render_report(res))

    env = Envelope(
        tool=TOOL,
        ok=res.ok,
        exit_code=0 if res.ok else 1,
        summary=(
            f"stress matrix: {res.counts['FAIL']} FAIL, "
            f"{res.counts['UNTESTABLE']} UNTESTABLE of {len(res.scenarios)}"
        ),
        data=res.to_dict(),
        evidence=[str(args.project_dir)],
        matrix_dim="robustness",
        matrix_axis="stress",
        matrix_status="PASS" if res.ok else "FAIL",
    )
    maybe_emit(args, env)
    return 0 if res.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
