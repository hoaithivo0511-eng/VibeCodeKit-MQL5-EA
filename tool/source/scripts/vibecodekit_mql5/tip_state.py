"""TIP state machine + persistence (v3 governance).

A TASK-GRAPH decomposes an EA build into TIPs (Technical Implementation
Plan units). Each TIP moves through a strict lifecycle so a build can never
silently mark itself done:

    planned -> assigned -> reported -> verified -> accepted
                              |            |
                              v            v
                           failed  ->  repair_required -> assigned
                              |
                              v
                           blocked

Key rules enforced here:
  * a TIP cannot be ``assigned``/run while any dependency is not ``accepted``;
  * a Completion Report STATUS=DONE does NOT auto-accept — it moves the TIP to
    ``reported`` and acceptance only happens via :func:`verify_tip`;
  * a ``BLOCKED`` report records a blocking issue;
  * every transition is appended to the TIP's ``history``.

State is persisted to ``TIP-STATE.json`` in the project dir.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_FILE = "TIP-STATE.json"
STATE_SCHEMA_VERSION = "2.6"

VALID_STATES: tuple[str, ...] = (
    "planned",
    "assigned",
    "reported",
    "verified",
    "failed",
    "repair_required",
    "accepted",
    "blocked",
)

# States from which a dependent TIP is considered satisfied.
SATISFIED_STATES: frozenset[str] = frozenset({"accepted"})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Tip:
    id: str
    title: str = ""
    state: str = "planned"
    depends_on: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    # v2.6 BIG HARDENING (PRD section 8): a TIP carries its full edit +
    # acceptance contract so an AI coding tool can never touch protected
    # paths, claim done without the required commands/evidence, or leave no
    # rollback path.
    forbidden_paths: list[str] = field(default_factory=list)
    acceptance_commands: list[str] = field(default_factory=list)
    evidence_required: list[str] = field(default_factory=list)
    rollback_plan: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    blocking_issue: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "state": self.state,
            "depends_on": list(self.depends_on),
            "allowed_paths": list(self.allowed_paths),
            "forbidden_paths": list(self.forbidden_paths),
            "acceptance_commands": list(self.acceptance_commands),
            "evidence_required": list(self.evidence_required),
            "rollback_plan": self.rollback_plan,
            "history": list(self.history),
            "blocking_issue": self.blocking_issue,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Tip":
        return cls(
            id=str(d.get("id")),
            title=str(d.get("title", "")),
            state=str(d.get("state", "planned")),
            depends_on=[str(x) for x in d.get("depends_on", []) or []],
            allowed_paths=[str(x) for x in d.get("allowed_paths", []) or []],
            forbidden_paths=[str(x) for x in d.get("forbidden_paths", []) or []],
            acceptance_commands=[str(x) for x in d.get("acceptance_commands", []) or []],
            evidence_required=[str(x) for x in d.get("evidence_required", []) or []],
            rollback_plan=d.get("rollback_plan"),
            history=list(d.get("history", []) or []),
            blocking_issue=d.get("blocking_issue"),
        )


@dataclass
class TipState:
    tips: dict[str, Tip] = field(default_factory=dict)
    schema_version: str = STATE_SCHEMA_VERSION

    # -- ordering / lookup --------------------------------------------------
    def ordered(self) -> list[Tip]:
        return list(self.tips.values())

    def get(self, tip_id: str) -> Tip | None:
        return self.tips.get(tip_id)

    def deps_satisfied(self, tip: Tip) -> bool:
        for dep_id in tip.depends_on:
            dep = self.tips.get(dep_id)
            if dep is None or dep.state not in SATISFIED_STATES:
                return False
        return True

    def _record(self, tip: Tip, frm: str, to: str, note: str = "") -> None:
        tip.history.append({"at": _now(), "from": frm, "to": to, "note": note})
        tip.state = to

    # -- transitions --------------------------------------------------------
    def next_tip(self) -> Tip | None:
        """Return the next runnable TIP.

        A TIP is runnable when it is ``planned`` (or ``repair_required``) and
        every dependency is ``accepted``. Returns ``None`` if nothing can run
        right now (all done, or everything is blocked on deps).
        """
        for tip in self.ordered():
            if tip.state in ("planned", "repair_required") and self.deps_satisfied(tip):
                return tip
        return None

    def assign(self, tip_id: str) -> Tip:
        tip = self._require(tip_id)
        if not self.deps_satisfied(tip):
            unmet = [
                d for d in tip.depends_on
                if not (self.tips.get(d) and self.tips[d].state in SATISFIED_STATES)
            ]
            raise ValueError(
                f"cannot assign {tip_id}: unmet dependencies {unmet} (must be accepted)"
            )
        if tip.state not in ("planned", "repair_required"):
            raise ValueError(f"cannot assign {tip_id} from state {tip.state!r}")
        self._record(tip, tip.state, "assigned", "assigned to builder")
        return tip

    def update_tip_from_report(self, tip_id: str, report: Any) -> Tip:
        """Apply a parsed Completion Report. DONE != accepted.

        - STATUS=DONE     -> ``reported`` (awaits verify_tip).
        - STATUS=PARTIAL  -> ``repair_required``.
        - STATUS=BLOCKED  -> ``blocked`` (+ records a blocking issue).
        """
        tip = self._require(tip_id)
        status = (getattr(report, "status", None) or "").upper()
        if status == "DONE":
            self._record(tip, tip.state, "reported", "completion report: DONE (awaiting verify)")
        elif status == "PARTIAL":
            self._record(tip, tip.state, "repair_required", "completion report: PARTIAL")
        elif status == "BLOCKED":
            tip.blocking_issue = _blocking_note(report)
            self._record(tip, tip.state, "blocked", f"BLOCKED: {tip.blocking_issue}")
        else:
            raise ValueError(f"unknown completion report status {status!r}")
        return tip

    def verify_tip(self, tip_id: str, *, passed: bool, note: str = "") -> Tip:
        """Verify a ``reported`` TIP. Only a passing verify accepts it."""
        tip = self._require(tip_id)
        if tip.state != "reported":
            raise ValueError(
                f"cannot verify {tip_id} from state {tip.state!r} (must be 'reported')"
            )
        if passed:
            self._record(tip, "reported", "verified", note or "verify passed")
            self._record(tip, "verified", "accepted", "accepted after verify")
        else:
            self._record(tip, "reported", "failed", note or "verify failed")
            self._record(tip, "failed", "repair_required", "needs repair after failed verify")
        return tip

    def _require(self, tip_id: str) -> Tip:
        tip = self.tips.get(tip_id)
        if tip is None:
            raise KeyError(f"unknown TIP id: {tip_id}")
        return tip

    # -- (de)serialisation --------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tips": [t.to_dict() for t in self.tips.values()],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TipState":
        state = cls(schema_version=str(d.get("schema_version", STATE_SCHEMA_VERSION)))
        for raw in d.get("tips", []) or []:
            tip = Tip.from_dict(raw)
            state.tips[tip.id] = tip
        return state


def _blocking_note(report: Any) -> str:
    devs = getattr(report, "deviations", None) or []
    if devs:
        return "; ".join(str(d) for d in devs)
    return "blocked (see completion report)"


def load_tip_state(project_dir: Path | str) -> TipState:
    """Load TIP-STATE.json from a project dir (empty state if absent)."""
    path = Path(project_dir) / STATE_FILE
    if not path.is_file():
        return TipState()
    return TipState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_tip_state(project_dir: Path | str, state: TipState) -> Path:
    """Persist TIP-STATE.json into a project dir."""
    path = Path(project_dir) / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def state_from_task_graph(graph: dict[str, Any]) -> TipState:
    """Build an initial TipState from a TASK-GRAPH.yaml-style dict.

    Accepts ``{"tips": [{id,title,depends_on,allowed_paths}, ...]}``.
    """
    state = TipState()
    for raw in graph.get("tips", []) or []:
        tip = Tip(
            id=str(raw.get("id")),
            title=str(raw.get("title", "")),
            depends_on=[str(x) for x in raw.get("depends_on", []) or []],
            allowed_paths=[str(x) for x in raw.get("allowed_paths", []) or []],
            forbidden_paths=[str(x) for x in raw.get("forbidden_paths", []) or []],
            acceptance_commands=[str(x) for x in raw.get("acceptance_commands", []) or []],
            evidence_required=[str(x) for x in raw.get("evidence_required", []) or []],
            rollback_plan=raw.get("rollback_plan"),
        )
        state.tips[tip.id] = tip
    return state


__all__ = [
    "VALID_STATES",
    "Tip",
    "TipState",
    "load_tip_state",
    "save_tip_state",
    "state_from_task_graph",
]


def main(argv: list[str] | None = None) -> int:
    """CLI: show TIP state, or initialise it from a TASK-GRAPH.yaml."""
    import argparse
    import sys

    from ._agent_io import Envelope, add_gate_report_flag, add_json_flag, maybe_emit

    ap = argparse.ArgumentParser(
        prog="mql5-tip-state",
        description="Inspect or initialise the per-project TIP state machine.",
    )
    ap.add_argument("project_dir", type=Path, help="EA project directory.")
    ap.add_argument("--init-from", type=Path, default=None,
                    help="Initialise TIP-STATE.json from this TASK-GRAPH.yaml.")
    add_json_flag(ap)
    add_gate_report_flag(ap)
    args = ap.parse_args(argv)

    if args.init_from is not None:
        if not args.init_from.is_file():
            if not args.emit_json:
                sys.stderr.write(f"error: task graph not found: {args.init_from}\n")
            env = Envelope(tool="mql5-tip-state", ok=False, exit_code=2,
                           summary=f"task graph not found: {args.init_from}")
            maybe_emit(args, env)
            return 2
        try:
            import yaml  # type: ignore

            graph = yaml.safe_load(args.init_from.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            graph = json.loads(args.init_from.read_text(encoding="utf-8"))
        state = state_from_task_graph(graph)
        path = save_tip_state(args.project_dir, state)
        summary = f"initialised {len(state.tips)} TIP(s) -> {path}"
    else:
        state = load_tip_state(args.project_dir)
        summary = f"{len(state.tips)} TIP(s)"

    by_state: dict[str, int] = {}
    for tip in state.tips.values():
        by_state[tip.state] = by_state.get(tip.state, 0) + 1
    env = Envelope(
        tool="mql5-tip-state", ok=True, exit_code=0,
        summary=summary,
        data={"tip_count": len(state.tips), "by_state": by_state,
              "tips": [{"id": t.id, "state": t.state, "title": t.title}
                       for t in state.tips.values()]},
        evidence=[str(args.project_dir)],
    )
    if not args.emit_json:
        sys.stdout.write(summary + "\n")
        for t in state.tips.values():
            sys.stdout.write(f"  {t.id} [{t.state}] {t.title}\n")
    maybe_emit(args, env)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
