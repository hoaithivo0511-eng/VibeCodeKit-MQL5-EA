"""Shared agent-friendly I/O helpers (agent contracts).

Provides a canonical JSON envelope used by every CLI that supports the
``--json`` flag so external agents (Devin, Claude Code, Codex, Cursor)
can introspect a tool's exit cleanly without parsing pretty text.

The envelope intentionally stays minimal so it stays stable:

    {
      "schema_version": "1",
      "tool":          "<cli-name>",
      "ok":            true | false,
      "exit_code":     0 | 1 | 2,
      "summary":       "<one-line human summary>",
      "data":          { ... tool-specific payload ... },
      "evidence":      ["path/to/input1", "path/to/input2", ...]
    }

A successful ``ok=True`` always pairs with ``exit_code=0``. A failing
gate uses ``ok=False`` + ``exit_code=1``. ``exit_code=2`` is reserved for
invocation errors (bad flags, missing files). Tools are free to add
additional top-level keys but **must not** rename the six core keys.

Tools opt-in by:

1. Adding ``add_json_flag(parser)`` to their argparse parser.
2. Calling ``emit(...)`` exactly once before returning.

A matching gate report writer (:func:`write_gate_report`) writes the
same envelope to disk so :mod:`vibecodekit_mql5.rri.matrix` can
auto-collect cell statuses from a directory of artifacts (§W1.4).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    """Register the standard ``--json`` flag on an argparse parser.

    Tools that have their own ``--json <file>`` flag (e.g. multibroker)
    should rename the legacy flag before calling this helper to avoid
    a conflict. The new flag is a boolean switch and writes the
    envelope to stdout.
    """

    parser.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help="Emit a stable JSON envelope (schema_version=1) on stdout "
        "instead of pretty text. Suitable for agent consumption.",
    )


def add_draft_flag(parser: argparse.ArgumentParser) -> None:
    """Register the standard ``--draft`` flag (§W2.3).

    Draft mode tells a gate to keep collecting findings but downgrade
    every ``ERROR`` to a non-blocking warning: the tool exits 0 and the
    envelope reports ``ok=true`` so a downstream pipeline (Devin chat
    loop, CI smoke job) can iterate quickly on a half-finished EA
    without the gate slamming the door on every commit.

    Draft is intentionally **different** from ``--soft`` (see
    ``mql5-doctor``): ``--soft`` relaxes environment probes (Wine /
    MetaEditor / terminal) so docs-only CI passes; ``--draft`` relaxes
    the *gate acceptance threshold* itself. Both flags can coexist on
    the same tool.
    """

    parser.add_argument(
        "--draft",
        action="store_true",
        help="Draft mode: downgrade errors to non-blocking warnings, "
        "exit 0 regardless of findings (still emits a JSON envelope "
        "marked ``draft=true``).",
    )


def apply_draft(envelope: Envelope, draft: bool) -> Envelope:
    """Mutate ``envelope`` in place when ``draft`` is true.

    Sets ``ok=True``, ``exit_code=0`` and adds ``data.draft=True`` +
    ``data.original_*`` so consumers can still see what the gate would
    have rejected in non-draft mode. The matrix status downgrades from
    ``FAIL`` to ``WARN`` (PASS stays PASS); other statuses are left
    alone so a draft run doesn't poison the quality matrix.
    """

    if not draft:
        return envelope
    envelope.data = dict(envelope.data)  # ensure we don't share mutable
    envelope.data["draft"] = True
    envelope.data["original_ok"] = envelope.ok
    envelope.data["original_exit_code"] = envelope.exit_code
    envelope.ok = True
    envelope.exit_code = 0
    if envelope.matrix_status == "FAIL":
        envelope.data["original_matrix_status"] = "FAIL"
        envelope.matrix_status = "WARN"
    envelope.summary += " (draft mode — errors downgraded to warnings)"
    return envelope


def add_gate_report_flag(parser: argparse.ArgumentParser) -> None:
    """Register the standard ``--gate-report`` flag.

    When supplied, the tool writes its envelope to the given path in
    addition to whatever stdout output it produces. The matrix collector
    reads every ``gate-report-*.json`` file under a directory tree.
    """

    parser.add_argument(
        "--gate-report",
        dest="gate_report",
        type=Path,
        default=None,
        help="Also write the envelope to this path. Used by "
        "`python -m vibecodekit_mql5.rri.matrix --collect` for matrix auto-fill.",
    )


@dataclass
class Envelope:
    tool: str
    ok: bool
    exit_code: int
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    # Optional the kit spec §10 matrix coordinates so a gate can declare
    # which cell(s) it fills when collected by `python -m
    # vibecodekit_mql5.rri.matrix --collect`. Both keys are optional; tools that don't map to the
    # matrix simply omit them.
    matrix_dim: str | None = None
    matrix_axis: str | None = None
    matrix_status: str | None = None  # "PASS" | "WARN" | "FAIL" | "N/A"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "tool": self.tool,
            "ok": self.ok,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "data": self.data,
            "evidence": list(self.evidence),
        }
        if self.matrix_dim is not None and self.matrix_axis is not None:
            out["matrix"] = {
                "dim": self.matrix_dim,
                "axis": self.matrix_axis,
                "status": self.matrix_status or ("PASS" if self.ok else "FAIL"),
            }
        return out


def emit(envelope: Envelope, *, stream=None) -> None:
    """Write the envelope to ``stream`` as a single JSON document.

    The default stream is the *current* ``sys.stdout`` resolved at call
    time, not at import time. This matters because pytest's
    ``capsys`` / ``redirect_stdout`` swap ``sys.stdout`` after import,
    and a default of ``sys.stdout`` baked in at def-time would write
    around the redirect.
    """

    if stream is None:
        stream = sys.stdout
    json.dump(envelope.to_dict(), stream, indent=2, sort_keys=False)
    stream.write("\n")


def write_gate_report(envelope: Envelope, path: Path) -> Path:
    """Persist the envelope to ``path``.

    The matrix collector recognises files matching ``gate-report-*.json``
    so picking a name with that prefix is recommended but not enforced.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope.to_dict(), indent=2, sort_keys=False) + "\n",
                    encoding="utf-8")
    return path


# --- diagnostic channel -----------------------------------------------------
# Contract: ``stdout`` is reserved for a tool's primary machine-readable
# payload (a single JSON envelope, SARIF document, or the intended human
# report). EVERY diagnostic line - progress, info, warnings, errors,
# deprecation notices - goes to ``stderr`` so an agent piping stdout gets a
# clean channel and ``tool > out.json`` never captures log noise. Tools should
# route diagnostics through these helpers instead of bare ``print``.
# ``mql5-doctor --check-io-contract`` statically enforces this across the kit.


def diag(message: str, *, prefix: str = "") -> None:
    """Write a diagnostic line to the *current* ``sys.stderr``.

    Resolved at call time (not import time) so a redirected stderr in tests
    is honoured, mirroring :func:`emit`.
    """
    line = f"{prefix}{message}" if prefix else message
    print(line, file=sys.stderr)


def info(message: str) -> None:
    """Informational diagnostic (stderr)."""
    diag(message)


def warn(message: str) -> None:
    """Warning diagnostic (stderr), prefixed ``warning: ``."""
    diag(message, prefix="warning: ")


def error(message: str) -> None:
    """Error diagnostic (stderr), prefixed ``error: ``."""
    diag(message, prefix="error: ")


def maybe_emit(args: argparse.Namespace, envelope: Envelope) -> None:
    """Convenience: emit JSON if ``--json`` was set and/or write gate report.

    Tools that registered ``--json`` and/or ``--gate-report`` via the
    helpers above can call this once at the end of ``main()``.
    """

    if getattr(args, "emit_json", False):
        emit(envelope)
    gate_report = getattr(args, "gate_report", None)
    if gate_report is not None:
        write_gate_report(envelope, Path(gate_report))
