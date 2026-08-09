"""mql5-init — interactive 5-question wizard that emits ``ea-spec.yaml``.

Closes the "blank canvas" gap called out in the v0.0.1 review: new users
landing on the repo didn't have a one-shot path from idea → spec → build.
``mql5-spec-from-prompt`` requires the operator to already know how to
phrase a single dense sentence; ``mql5-init`` instead asks five short
questions and emits the same ``ea-spec.yaml`` artefact that
``mql5-auto-build --spec`` consumes.

The wizard is deliberately small (five questions) so it fits inside the
"first 30 seconds" budget set by ``README.md``:

    1. EA name              (free text, default "MyEA")
    2. Preset               (trend / mean-reversion / breakout / scalping /
                             hft-async / ml-onnx / stdlib / ...)
    3. Stack                (filtered to what the preset supports)
    4. Symbol + timeframe   (e.g. "EURUSD H1")
    5. Risk per trade       (percent, default 0.5)

For CI / scripted environments, ``--non-interactive`` runs with the
defaults and ``--from-answers <yaml>`` loads a pre-filled answer file
(useful for golden-output regression tests). ``--list-presets`` prints
the preset/stack matrix and exits.

The output spec is round-tripped through ``spec_schema.validate`` so
``mql5-init`` never emits anything ``mql5-auto-build`` would reject.

CLI::

    mql5-init                                   # interactive prompts
    mql5-init --non-interactive --out ea-spec.yaml
    mql5-init --from-answers answers.yaml --out ea-spec.yaml
    mql5-init --list-presets
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import _agent_io
from . import build as build_mod
from . import spec_schema
from .spec_from_prompt import to_yaml

# Default suggestions for each prompt — kept conservative so the
# non-interactive path produces a spec that compiles cleanly under
# ``mql5-build`` without any further editing.
DEFAULTS: dict[str, str] = {
    "name": "MyEA",
    "preset": "trend",
    "stack": "netting",
    "symbol": "EURUSD",
    "timeframe": "H1",
    "risk": "0.5",
}

# Sanitisation: EA name must be a valid MQL5 identifier so MetaEditor
# accepts the resulting ``.mq5``. Strip everything that isn't a letter /
# digit / underscore and ensure it starts with a letter.
_NAME_RE = re.compile(r"[^A-Za-z0-9_]")
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,12}$")
_TF_RE = re.compile(r"^(M[1-9]\d?|H[1-9]\d?|D1|W1|MN1)$")


@dataclass
class Answers:
    """Five answers collected (or defaulted) by the wizard."""

    name: str = DEFAULTS["name"]
    preset: str = DEFAULTS["preset"]
    stack: str = DEFAULTS["stack"]
    symbol: str = DEFAULTS["symbol"]
    timeframe: str = DEFAULTS["timeframe"]
    risk_per_trade_pct: float = float(DEFAULTS["risk"])
    # Echo-only metadata so the resulting spec records what was inferred
    # vs typed; useful when the wizard runs unattended in CI.
    inferred: list[str] = field(default_factory=list)

    def to_spec(self) -> dict[str, object]:
        return {
            "name": self.name,
            "preset": self.preset,
            "stack": self.stack,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "mode": "personal",
            "risk": {"per_trade_pct": self.risk_per_trade_pct},
        }


def _sanitise_name(raw: str) -> str:
    cleaned = _NAME_RE.sub("", raw.strip()) or DEFAULTS["name"]
    if cleaned[0].isdigit():
        cleaned = "EA_" + cleaned
    return cleaned


def _normalise_preset(raw: str) -> str:
    """Accept loose aliases like ``mean-rev`` for ``mean-reversion``."""

    raw = raw.strip().lower()
    aliases = {
        "mean-rev": "mean-reversion",
        "meanrev": "mean-reversion",
        "trends": "trend",
        "scalp": "scalping",
        "hft": "hft-async",
        "onnx": "ml-onnx",
        "ml": "ml-onnx",
        "wizard": "wizard-composable",
    }
    if raw in aliases:
        return aliases[raw]
    return raw


def _normalise_symbol(raw: str) -> str:
    return raw.strip().upper()


def _normalise_timeframe(raw: str) -> str:
    """Canonicalise an MT5 timeframe label.

    Accepts the lower-case shorthand operators tend to type (``h1``,
    ``m15``, ``mn``) and rewrites it to the MetaTrader 5 form
    (``H1``, ``M15``, ``MN1``). Bare ``MN`` is upgraded to ``MN1`` so the
    spec round-trips, but ``MN1``/``MN`` already-canonical must NOT be
    mangled into ``MN11`` — the previous greedy ``.replace("MN", "MN1")``
    did exactly that on every monthly-timeframe input.
    """

    s = raw.strip().upper().replace("MIN", "M")
    return "MN1" if s == "MN" else s


def _ask(prompt: str, default: str, stream_in, stream_out) -> str:
    """Print ``prompt`` (with default) to stream_out and read one line.

    Returns the typed value (stripped) or ``default`` if the user just
    pressed Enter. EOF is treated as "use default" so the wizard never
    deadlocks on a closed stdin (CI machines, piped invocations)."""

    stream_out.write(f"{prompt} [{default}]: ")
    stream_out.flush()
    line = stream_in.readline()
    if not line:
        stream_out.write("\n")
        return default
    value = line.strip()
    return value or default


def list_presets() -> str:
    """Return a human-readable preset → stack matrix for ``--list-presets``."""

    rows = []
    for preset in sorted(build_mod.PRESETS):
        stacks = ", ".join(build_mod.PRESETS[preset])
        rows.append(f"  {preset:20s} stacks: {stacks}")
    return "Available presets:\n" + "\n".join(rows) + "\n"


def collect_interactive(
    stream_in=sys.stdin, stream_out=sys.stderr,
) -> Answers:
    """Run the 5-question wizard against ``stream_in`` / ``stream_out``.

    Echoes prompts on ``stream_out`` (stderr by default so the eventual
    YAML on stdout stays parseable when the operator pipes the wizard).
    Validates each answer; on invalid input the question is re-asked
    once, then falls back to the default rather than looping forever.
    """

    stream_out.write("mql5-init — 5-question EA bootstrap\n")
    stream_out.write("Press Enter to accept the [default].\n\n")

    ans = Answers()

    raw_name = _ask("1) EA name", DEFAULTS["name"], stream_in, stream_out)
    ans.name = _sanitise_name(raw_name)
    if ans.name != raw_name:
        stream_out.write(f"   ↳ sanitised to {ans.name!r}\n")

    valid_presets = sorted(build_mod.PRESETS)
    for attempt in (1, 2):
        raw_preset = _ask(
            f"2) Preset {valid_presets[:5]}…",
            DEFAULTS["preset"], stream_in, stream_out,
        )
        candidate = _normalise_preset(raw_preset)
        if candidate in build_mod.PRESETS:
            ans.preset = candidate
            break
        stream_out.write(
            f"   ! unknown preset {candidate!r}; "
            f"run `mql5-init --list-presets` to see all.\n",
        )
        if attempt == 2:
            ans.preset = DEFAULTS["preset"]
            stream_out.write(f"   ↳ falling back to {ans.preset!r}\n")

    allowed_stacks = build_mod.PRESETS[ans.preset]
    stack_default = allowed_stacks[0] if allowed_stacks else DEFAULTS["stack"]
    for attempt in (1, 2):
        raw_stack = _ask(
            f"3) Stack for {ans.preset!r} {allowed_stacks}",
            stack_default, stream_in, stream_out,
        )
        candidate = raw_stack.strip()
        if candidate in allowed_stacks:
            ans.stack = candidate
            break
        stream_out.write(
            f"   ! {candidate!r} is not valid for preset {ans.preset!r}; "
            f"choose one of {allowed_stacks}.\n",
        )
        if attempt == 2:
            ans.stack = stack_default
            stream_out.write(f"   ↳ falling back to {ans.stack!r}\n")

    raw_sym_tf = _ask(
        "4) Symbol + timeframe (e.g. EURUSD H1)",
        f"{DEFAULTS['symbol']} {DEFAULTS['timeframe']}",
        stream_in, stream_out,
    )
    parts = raw_sym_tf.split()
    ans.symbol = _normalise_symbol(parts[0]) if parts else DEFAULTS["symbol"]
    ans.timeframe = (
        _normalise_timeframe(parts[1]) if len(parts) > 1 else DEFAULTS["timeframe"]
    )
    if not _SYMBOL_RE.match(ans.symbol):
        stream_out.write(f"   ! symbol {ans.symbol!r} looks odd; keeping it anyway\n")
    if not _TF_RE.match(ans.timeframe):
        stream_out.write(
            f"   ! timeframe {ans.timeframe!r} unrecognised; falling back to "
            f"{DEFAULTS['timeframe']!r}\n",
        )
        ans.timeframe = DEFAULTS["timeframe"]

    raw_risk = _ask("5) Risk per trade %", DEFAULTS["risk"], stream_in, stream_out)
    try:
        ans.risk_per_trade_pct = float(raw_risk)
        if not (0.01 <= ans.risk_per_trade_pct <= 5.0):
            raise ValueError("risk out of [0.01, 5.0]")
    except ValueError as exc:
        stream_out.write(
            f"   ! {exc}; falling back to {DEFAULTS['risk']!r}\n",
        )
        ans.risk_per_trade_pct = float(DEFAULTS["risk"])

    return ans


# ---------------------------------------------------------------------------
# --from-answers loader (minimal YAML subset — same shape as Answers)
# ---------------------------------------------------------------------------

def load_answers_file(path: Path) -> Answers:
    """Parse a tiny YAML answer file using stdlib only.

    Supports flat ``key: value`` lines (whitespace-tolerant, ``#`` for
    comments). This deliberately avoids the optional ``pyyaml`` dep so
    ``mql5-init`` runs on minimal CI containers."""

    ans = Answers()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower().replace("-", "_")
        value = value.strip().strip('"').strip("'")
        if key == "name":
            ans.name = _sanitise_name(value)
        elif key == "preset":
            ans.preset = _normalise_preset(value)
        elif key == "stack":
            ans.stack = value
        elif key == "symbol":
            ans.symbol = _normalise_symbol(value)
        elif key in ("tf", "timeframe"):
            ans.timeframe = _normalise_timeframe(value)
        elif key in ("risk", "risk_per_trade_pct"):
            try:
                ans.risk_per_trade_pct = float(value)
            except ValueError:
                pass
    return ans


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mql5-init",
        description=__doc__.splitlines()[0],
    )
    p.add_argument(
        "--out", type=Path,
        help="Write the resulting ea-spec.yaml here (default: stdout).",
    )
    p.add_argument(
        "--non-interactive", action="store_true",
        help="Skip prompts and use defaults (or values from --from-answers).",
    )
    p.add_argument(
        "--from-answers", type=Path, default=None,
        help="Load wizard answers from a small YAML file instead of "
             "prompting. Implies --non-interactive.",
    )
    p.add_argument(
        "--list-presets", action="store_true",
        help="Print the preset/stack matrix and exit.",
    )
    _agent_io.add_json_flag(p)
    args = p.parse_args(argv)

    if args.list_presets:
        sys.stdout.write(list_presets())
        return 0

    if args.from_answers is not None:
        if not args.from_answers.is_file():
            print(f"--from-answers: not a file: {args.from_answers}", file=sys.stderr)
            return 2
        ans = load_answers_file(args.from_answers)
    elif args.non_interactive:
        ans = Answers()
    else:
        try:
            ans = collect_interactive()
        except (KeyboardInterrupt, EOFError):
            print("\naborted", file=sys.stderr)
            return 130

    # Belt-and-braces: re-validate stack against preset so a bad
    # --from-answers file never produces an unbuildable spec.
    allowed = build_mod.PRESETS.get(ans.preset, [])
    if ans.stack not in allowed and allowed:
        ans.stack = allowed[0]

    spec = ans.to_spec()
    # Round-trip through the real validator so we catch schema breakage
    # before the operator pipes the output into mql5-auto-build.
    spec_schema.validate(spec, valid_presets=build_mod.PRESETS)
    yaml_text = to_yaml(spec)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(yaml_text, encoding="utf-8")
        wrote_to = str(args.out)
    else:
        # When --json is set the agent contract requires stdout to be a
        # pure JSON envelope (see scripts/vibecodekit_mql5/_agent_io.py).
        # Suppress the YAML pretty-print so callers can `json.loads` the
        # output without splitting on a sentinel; the spec is still
        # included verbatim under data.spec in the envelope below.
        if not args.emit_json:
            sys.stdout.write(yaml_text)
        wrote_to = "<stdout>"

    if args.emit_json:
        envelope = _agent_io.Envelope(
            tool="mql5-init",
            ok=True,
            exit_code=0,
            summary=(
                f"wrote {ans.preset}/{ans.stack} spec for {ans.name} "
                f"({ans.symbol} {ans.timeframe}, risk {ans.risk_per_trade_pct}%) "
                f"to {wrote_to}"
            ),
            data={
                "spec": spec,
                "answers": {
                    "name": ans.name,
                    "preset": ans.preset,
                    "stack": ans.stack,
                    "symbol": ans.symbol,
                    "timeframe": ans.timeframe,
                    "risk_per_trade_pct": ans.risk_per_trade_pct,
                },
                "out": wrote_to,
            },
            evidence=[wrote_to] if args.out is not None else [],
        )
        _agent_io.emit(envelope)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
