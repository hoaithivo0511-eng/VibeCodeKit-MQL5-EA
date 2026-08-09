"""Actor-to-actor escalation audit log.

When one Triangle-of-Power actor cannot proceed without input from
another, they raise an *escalation*. The escalation is the kit's
canonical, append-only audit trail proving who asked whom for help,
when, and how it was resolved. The log is what
``mql5-permission-layer5 --enforce-no-open-escalation`` consults to
decide whether a TEAM / ENTERPRISE gate can ship.

Three escalation levels are supported:

* **Level 1 — note / observation.** Informational; never blocks any
  gate. Equivalent to "please be aware of X".
* **Level 2 — warning / question.** Requires explicit acknowledgement
  but does not by itself block enterprise sign-off. Surfaces in the
  Verify Report so the Homeowner sees it.
* **Level 3 — hard block.** While the escalation is OPEN, the
  layer-5 hook fails for TEAM and ENTERPRISE mode. Personal mode is
  always informational.

The log lives at ``.mql5-audit/escalations.jsonl`` by default — one
JSON record per line — so it composes with normal git workflows
(append-only diffs, deterministic ordering) and stays grep-able
without a database. Each record carries::

    {
      "id":             "ESC-YYYYMMDD-NNN",
      "from":           "chu-nha" | "chu-thau" | "tho-thi-cong",
      "to":             "chu-nha" | "chu-thau" | "tho-thi-cong",
      "level":          1 | 2 | 3,
      "reason":         "<human-readable>",
      "artefact":       "<relative path>" | null,
      "raised_at":      "<ISO-8601 UTC>",
      "raised_by":      "<actor>",
      "status":         "OPEN" | "RESOLVED",
      "resolved_at":    "<ISO-8601 UTC>" | null,
      "resolved_by":    "<actor>" | null,
      "resolution":     "<human-readable>" | null
    }

The module is deterministic: same input → same record byte-for-byte
(modulo the timestamp the caller controls). IDs are generated
``ESC-YYYYMMDD-NNN`` where ``NNN`` is a zero-padded counter (at least
three digits, but widens to four+ if the per-day count exceeds 999)
scoped to the date, allocated from a single scan of the existing log
so two calls
on the same day never collide.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .._agent_io import (
    Envelope,
    add_gate_report_flag,
    add_json_flag,
    maybe_emit,
)

TOOL = "mql5-escalation"

ACTORS: tuple[str, ...] = ("chu-nha", "chu-thau", "tho-thi-cong")
LEVELS: tuple[int, ...] = (1, 2, 3)
DEFAULT_LOG = Path(".mql5-audit/escalations.jsonl")
_ID_PATTERN = re.compile(r"^ESC-(\d{8})-(\d{3,})$")


@dataclass(frozen=True)
class Escalation:
    """One immutable escalation record."""

    id: str
    from_actor: str
    to_actor: str
    level: int
    reason: str
    raised_at: str
    raised_by: str
    status: str = "OPEN"
    artefact: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    resolution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from": self.from_actor,
            "to": self.to_actor,
            "level": self.level,
            "reason": self.reason,
            "artefact": self.artefact,
            "raised_at": self.raised_at,
            "raised_by": self.raised_by,
            "status": self.status,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Escalation:
        return cls(
            id=str(payload["id"]),
            from_actor=str(payload["from"]),
            to_actor=str(payload["to"]),
            level=int(payload["level"]),
            reason=str(payload["reason"]),
            raised_at=str(payload["raised_at"]),
            raised_by=str(payload["raised_by"]),
            status=str(payload.get("status", "OPEN")),
            artefact=(
                None
                if payload.get("artefact") in (None, "")
                else str(payload["artefact"])
            ),
            resolved_at=(
                None
                if payload.get("resolved_at") in (None, "")
                else str(payload["resolved_at"])
            ),
            resolved_by=(
                None
                if payload.get("resolved_by") in (None, "")
                else str(payload["resolved_by"])
            ),
            resolution=(
                None
                if payload.get("resolution") in (None, "")
                else str(payload["resolution"])
            ),
        )


def _validate_actor(name: str, *, field_name: str) -> str:
    if name not in ACTORS:
        raise ValueError(
            f"{field_name}={name!r} is not a valid actor; "
            f"expected one of {list(ACTORS)}"
        )
    return name


def _validate_level(level: int) -> int:
    if level not in LEVELS:
        raise ValueError(
            f"level={level!r} is invalid; expected one of {list(LEVELS)}"
        )
    return level


def _now_iso(*, _now: datetime | None = None) -> str:
    """Return UTC ISO-8601 timestamp with second precision."""

    dt = _now if _now is not None else datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_log(log_path: Path) -> list[Escalation]:
    """Load every escalation record from ``log_path``.

    Missing files are treated as an empty log so callers do not have to
    pre-create the parent directory. Lines that fail to parse raise
    ``ValueError`` because a corrupt audit log must surface loudly
    rather than silently dropping records.
    """

    if not log_path.exists():
        return []
    out: list[Escalation] = []
    text = log_path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{log_path}:{lineno}: invalid JSON: {exc}"
            ) from exc
        out.append(Escalation.from_dict(payload))
    return out


def _next_id(existing: list[Escalation], *, today: str) -> str:
    """Return the next ``ESC-YYYYMMDD-NNN`` id for ``today``."""

    used: set[int] = set()
    for esc in existing:
        match = _ID_PATTERN.match(esc.id)
        if match is None or match.group(1) != today:
            continue
        used.add(int(match.group(2)))
    counter = 1
    while counter in used:
        counter += 1
    return f"ESC-{today}-{counter:03d}"


def raise_escalation(
    *,
    from_actor: str,
    to_actor: str,
    level: int,
    reason: str,
    artefact: str | None = None,
    log_path: Path = DEFAULT_LOG,
    _now: datetime | None = None,
) -> Escalation:
    """Append a new escalation record to ``log_path`` and return it.

    Validates that both actors are members of :data:`ACTORS`, level
    is one of :data:`LEVELS`, ``reason`` is non-empty after stripping,
    and ``from_actor != to_actor`` (escalating to yourself is a
    misuse). The log file's parent directory is created on demand so a
    fresh repo can ``mql5-escalation --from … --to …`` without
    pre-mkdir.
    """

    from_actor = _validate_actor(from_actor, field_name="from")
    to_actor = _validate_actor(to_actor, field_name="to")
    if from_actor == to_actor:
        raise ValueError(
            "from and to must differ; escalating to yourself is a no-op"
        )
    level = _validate_level(level)
    cleaned_reason = (reason or "").strip()
    if not cleaned_reason:
        raise ValueError("reason must be a non-empty string")
    cleaned_artefact: str | None
    if artefact is None:
        cleaned_artefact = None
    else:
        stripped = str(artefact).strip()
        cleaned_artefact = stripped if stripped else None
    raised_at = _now_iso(_now=_now)
    today = raised_at[:10].replace("-", "")
    existing = load_log(log_path)
    esc_id = _next_id(existing, today=today)
    record = Escalation(
        id=esc_id,
        from_actor=from_actor,
        to_actor=to_actor,
        level=level,
        reason=cleaned_reason,
        artefact=cleaned_artefact,
        raised_at=raised_at,
        raised_by=from_actor,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_dict(), sort_keys=False) + "\n")
    return record


def resolve_escalation(
    esc_id: str,
    *,
    resolved_by: str,
    resolution: str | None = None,
    log_path: Path = DEFAULT_LOG,
    _now: datetime | None = None,
) -> Escalation:
    """Mark ``esc_id`` as ``RESOLVED`` and rewrite the log in place.

    Raises ``KeyError`` if the id is unknown and ``ValueError`` if the
    escalation is already resolved (re-resolving would silently lose
    the previous resolution note).
    """

    resolved_by = _validate_actor(resolved_by, field_name="resolved-by")
    records = load_log(log_path)
    if not records:
        raise KeyError(f"escalation {esc_id!r} not found (log is empty)")
    note: str | None
    if resolution is None:
        note = None
    else:
        stripped = resolution.strip()
        note = stripped if stripped else None
    new_records: list[Escalation] = []
    target_idx: int | None = None
    for idx, esc in enumerate(records):
        if esc.id == esc_id:
            target_idx = idx
            if esc.status == "RESOLVED":
                raise ValueError(
                    f"escalation {esc_id!r} is already RESOLVED"
                )
            new_records.append(
                Escalation(
                    id=esc.id,
                    from_actor=esc.from_actor,
                    to_actor=esc.to_actor,
                    level=esc.level,
                    reason=esc.reason,
                    artefact=esc.artefact,
                    raised_at=esc.raised_at,
                    raised_by=esc.raised_by,
                    status="RESOLVED",
                    resolved_at=_now_iso(_now=_now),
                    resolved_by=resolved_by,
                    resolution=note,
                )
            )
        else:
            new_records.append(esc)
    if target_idx is None:
        raise KeyError(f"escalation {esc_id!r} not found")
    payload = "".join(
        json.dumps(r.to_dict(), sort_keys=False) + "\n" for r in new_records
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(payload, encoding="utf-8")
    return new_records[target_idx]


def filter_records(
    records: list[Escalation],
    *,
    status: str = "ALL",
    level: int | None = None,
) -> list[Escalation]:
    """Return ``records`` filtered by ``status`` and optionally ``level``.

    ``status`` must be one of ``OPEN`` / ``RESOLVED`` / ``ALL`` (case
    insensitive). ``level`` filters on the numeric level when given.
    """

    status_upper = status.upper()
    if status_upper not in ("OPEN", "RESOLVED", "ALL"):
        raise ValueError(
            f"status={status!r} is invalid; expected OPEN, RESOLVED, or ALL"
        )
    out: list[Escalation] = []
    for esc in records:
        if status_upper != "ALL" and esc.status != status_upper:
            continue
        if level is not None and esc.level != level:
            continue
        out.append(esc)
    return out


def open_level3_count(records: list[Escalation]) -> int:
    """Number of OPEN level-3 escalations — the layer-5 enforcement metric."""

    return sum(1 for r in records if r.status == "OPEN" and r.level == 3)


def render_list(records: list[Escalation]) -> str:
    """Render ``records`` as a stable human-readable summary string."""

    if not records:
        return "(no escalations)\n"
    lines: list[str] = []
    for esc in records:
        head = (
            f"[{esc.status}] {esc.id} L{esc.level} "
            f"{esc.from_actor} -> {esc.to_actor}"
        )
        lines.append(head)
        lines.append(f"  raised_at={esc.raised_at} raised_by={esc.raised_by}")
        if esc.artefact:
            lines.append(f"  artefact={esc.artefact}")
        lines.append(f"  reason={esc.reason}")
        if esc.status == "RESOLVED":
            lines.append(
                f"  resolved_at={esc.resolved_at} resolved_by={esc.resolved_by}"
            )
            if esc.resolution:
                lines.append(f"  resolution={esc.resolution}")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Append-only escalation audit log for the Triangle of "
            "Power (). Raise / list / resolve actor-to-actor "
            "escalations stored at .mql5-audit/escalations.jsonl."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--list", action="store_true",
        help="List existing escalations instead of raising a new one.",
    )
    mode.add_argument(
        "--resolve", dest="resolve_id", default=None,
        help="Mark the given escalation id as RESOLVED.",
    )
    parser.add_argument(
        "--from", dest="from_actor", default=None,
        choices=ACTORS,
        help="Actor raising the escalation (raise mode).",
    )
    parser.add_argument(
        "--to", dest="to_actor", default=None,
        choices=ACTORS,
        help="Actor the escalation is directed at (raise mode).",
    )
    parser.add_argument(
        "--level", type=int, default=None, choices=LEVELS,
        help="Severity 1 (note), 2 (warning), 3 (hard block). "
        "Filters --list output when supplied with --list.",
    )
    parser.add_argument(
        "--reason", default=None,
        help="Free-text reason for the escalation (raise mode).",
    )
    parser.add_argument(
        "--artefact", default=None,
        help="Optional path / identifier the escalation references.",
    )
    parser.add_argument(
        "--status", default="OPEN", choices=("OPEN", "RESOLVED", "ALL"),
        help="Filter for --list output (default: OPEN).",
    )
    parser.add_argument(
        "--resolved-by", dest="resolved_by", default=None,
        choices=ACTORS,
        help="Actor recording the resolution (resolve mode).",
    )
    parser.add_argument(
        "--note", default=None,
        help="Optional resolution note (resolve mode).",
    )
    parser.add_argument(
        "--audit-log", dest="audit_log", type=Path, default=DEFAULT_LOG,
        help=f"Path to the JSONL audit log (default: {DEFAULT_LOG}).",
    )
    add_json_flag(parser)
    add_gate_report_flag(parser)
    return parser


def _envelope(
    *,
    ok: bool,
    exit_code: int,
    summary: str,
    data: dict[str, Any],
    evidence: list[str],
) -> Envelope:
    return Envelope(
        tool=TOOL,
        ok=ok,
        exit_code=exit_code,
        summary=summary,
        data=data,
        evidence=evidence,
    )


def _cli_list(args: argparse.Namespace) -> int:
    records = load_log(args.audit_log)
    filtered = filter_records(
        records, status=args.status, level=args.level
    )
    rendered = render_list(filtered)
    if not args.emit_json:
        sys.stdout.write(rendered)
    envelope = _envelope(
        ok=True,
        exit_code=0,
        summary=(
            f"{len(filtered)} escalation(s) matched "
            f"(status={args.status}, level={args.level})"
        ),
        data={
            "mode": "list",
            "status_filter": args.status,
            "level_filter": args.level,
            "count": len(filtered),
            "open_level3_count": open_level3_count(records),
            "records": [r.to_dict() for r in filtered],
        },
        evidence=[str(args.audit_log)],
    )
    maybe_emit(args, envelope)
    return 0


def _cli_resolve(args: argparse.Namespace) -> int:
    if args.resolved_by is None:
        sys.stderr.write(
            "error: --resolve requires --resolved-by <actor>\n"
        )
        return 2
    try:
        record = resolve_escalation(
            args.resolve_id,
            resolved_by=args.resolved_by,
            resolution=args.note,
            log_path=args.audit_log,
        )
    except KeyError as exc:
        sys.stderr.write(f"error: {exc}\n")
        envelope = _envelope(
            ok=False,
            exit_code=2,
            summary=f"escalation {args.resolve_id!r} not found",
            data={"mode": "resolve", "id": args.resolve_id, "error": str(exc)},
            evidence=[str(args.audit_log)],
        )
        maybe_emit(args, envelope)
        return 2
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        envelope = _envelope(
            ok=False,
            exit_code=2,
            summary=f"cannot resolve {args.resolve_id!r}: {exc}",
            data={"mode": "resolve", "id": args.resolve_id, "error": str(exc)},
            evidence=[str(args.audit_log)],
        )
        maybe_emit(args, envelope)
        return 2
    if not args.emit_json:
        sys.stdout.write(f"resolved {record.id}\n")
    envelope = _envelope(
        ok=True,
        exit_code=0,
        summary=f"resolved {record.id} by {record.resolved_by}",
        data={"mode": "resolve", "record": record.to_dict()},
        evidence=[str(args.audit_log)],
    )
    maybe_emit(args, envelope)
    return 0


def _cli_raise(args: argparse.Namespace) -> int:
    missing: list[str] = []
    if args.from_actor is None:
        missing.append("--from")
    if args.to_actor is None:
        missing.append("--to")
    if args.level is None:
        missing.append("--level")
    if args.reason is None:
        missing.append("--reason")
    if missing:
        sys.stderr.write(
            "error: raise mode requires " + ", ".join(missing) + "\n"
        )
        return 2
    try:
        record = raise_escalation(
            from_actor=args.from_actor,
            to_actor=args.to_actor,
            level=args.level,
            reason=args.reason,
            artefact=args.artefact,
            log_path=args.audit_log,
        )
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        envelope = _envelope(
            ok=False,
            exit_code=2,
            summary=f"invalid escalation: {exc}",
            data={"mode": "raise", "error": str(exc)},
            evidence=[str(args.audit_log)],
        )
        maybe_emit(args, envelope)
        return 2
    if not args.emit_json:
        sys.stdout.write(f"raised {record.id}\n")
    envelope = _envelope(
        ok=True,
        exit_code=0,
        summary=(
            f"raised {record.id} L{record.level} "
            f"{record.from_actor} -> {record.to_actor}"
        ),
        data={"mode": "raise", "record": record.to_dict()},
        evidence=[str(args.audit_log)],
    )
    maybe_emit(args, envelope)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.list:
        return _cli_list(args)
    if args.resolve_id is not None:
        return _cli_resolve(args)
    return _cli_raise(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
