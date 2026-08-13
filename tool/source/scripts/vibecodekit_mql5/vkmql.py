"""vkmql-* — high-level workflow verbs over the mql5-* primitives.

Three verbs front the end-to-end flow so agents (and humans) drive one stable
surface instead of memorising ~100 ``mql5-*`` commands:

    vkmql-new    init | from-prompt | build | project   (create a project)
    vkmql-check  doctor | lint | compile | test | audit  (verify it)
    vkmql-ship   report | docs | package | release       (release it)

Each verb is a thin dispatcher: it forwards the remaining arguments to the
existing tool's ``main(argv)`` unchanged, so behaviour and exit codes are
identical to calling the underlying ``mql5-*`` command directly. The legacy
commands keep working; the verbs are additive.

CLI::

    vkmql-new build grid --name GuardEA --symbol XAUUSD --tf M5
    vkmql-new --preset grid --name GuardEA --symbol XAUUSD --tf M5   # flat form
    vkmql-check doctor --soft
    vkmql-ship --json package --help   # emit a JSON status envelope on stdout
    vkmql-new --list        # show subcommands as JSON

Global flags (must precede the subcommand):
    --json    after the subcommand runs, print a JSON status envelope
              {"verb", "subcommand", "args", "exit_code"} to stdout.
    --quiet   suppress vkmql's own usage banner; emit any vkmql JSON
              (--list / --json / errors) as single-line compact JSON.

Flat form: for vkmql-new a leading flag (no subcommand) is routed to the
default ``build`` subcommand; ``--preset P`` becomes the positional preset.
"""
from __future__ import annotations

import importlib
import json
import sys

from ._deprecation import warn_deprecated

# verb -> { subcommand: "module.path" } (each module exposes main(argv)->int)
NEW_SUBCOMMANDS: dict[str, str] = {
    "init": "vibecodekit_mql5.init",
    "from-prompt": "vibecodekit_mql5.spec_from_prompt",
    "build": "vibecodekit_mql5.build",
    "project": "vibecodekit_mql5.project_gen",
    # v2.6 hardening: governance scaffolding verbs.
    "spec": "vibecodekit_mql5.scaffold_v26:spec_main",
    "contract": "vibecodekit_mql5.scaffold_v26:contract_main",
    "tip-graph": "vibecodekit_mql5.scaffold_v26:tipgraph_main",
}
CHECK_SUBCOMMANDS: dict[str, str] = {
    "doctor": "vibecodekit_mql5.doctor",
    "lint": "vibecodekit_mql5.lint",
    "compile": "vibecodekit_mql5.compile",
    "test": "vibecodekit_mql5.test_runner",
    "audit": "vibecodekit_mql5.audit",
    "selftest": "vibecodekit_mql5.selftest",
    "status": "vibecodekit_mql5.golden_flow",
    # v2.6 hardening: contract / stress / evidence / full-gate checks.
    "contract": "vibecodekit_mql5.contract_check",
    "stress": "vibecodekit_mql5.stress_matrix_v2",
    "evidence": "vibecodekit_mql5.evidence_attestation:verify_main",
    "retro": "vibecodekit_mql5.retro_guard_check",
    "retro-init": "vibecodekit_mql5.retro_init",
    "decisions": "vibecodekit_mql5.decision_ledger",
    "quality": "vibecodekit_mql5.backtest_quality",
    "hygiene": "vibecodekit_mql5.trade_hygiene",
    "all": "vibecodekit_mql5.check_all",
}
SHIP_SUBCOMMANDS: dict[str, str] = {
    "report": "vibecodekit_mql5.ea_review_report",
    "docs": "vibecodekit_mql5.docs_bundle",
    "package": "vibecodekit_mql5.package",
    "release": "vibecodekit_mql5.ship",
}

VERBS: dict[str, dict[str, str]] = {
    "vkmql-new": NEW_SUBCOMMANDS,
    "vkmql-check": CHECK_SUBCOMMANDS,
    "vkmql-ship": SHIP_SUBCOMMANDS,
}


# Verbs accepting a "flat" form: when the first token is a flag instead of a
# subcommand, args are routed to this default subcommand. So
# ``vkmql-new --preset grid --name X ...`` == ``vkmql-new build grid ...``.
_DEFAULT_SUBCOMMAND: dict[str, str] = {"vkmql-new": "build"}


def _flatten_build_args(args: list[str]) -> list[str]:
    """Translate flat ``--preset VALUE`` into the positional preset that
    mql5-build expects, leaving every other flag untouched and in order."""
    preset: str | None = None
    rest: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--preset":
            if i + 1 < len(args):
                preset = args[i + 1]
                i += 2
                continue
            i += 1
            continue
        if a.startswith("--preset="):
            preset = a.split("=", 1)[1]
            i += 1
            continue
        rest.append(a)
        i += 1
    return [preset, *rest] if preset is not None else rest


def _emit(payload: dict, stream, *, quiet: bool) -> None:
    json.dump(payload, stream, indent=None if quiet else 2)
    stream.write("\n")


def _dispatch(verb: str, table: dict[str, str], argv: list[str] | None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    # Leading global flags (before the subcommand): --json / --quiet.
    json_mode = False
    quiet = False
    while args and args[0] in ("--json", "--quiet"):
        flag = args.pop(0)
        if flag == "--json":
            json_mode = True
        else:
            quiet = True

    if args and args[0] in ("--list", "-l"):
        _emit({"verb": verb, "subcommands": sorted(table)}, sys.stdout, quiet=quiet)
        return 0

    if not args or args[0] in ("-h", "--help"):
        if not quiet:
            subs = ", ".join(sorted(table))
            print(f"usage: {verb} [--json] [--quiet] <{subs}> [args...]")
            print(f"       {verb} --list   # JSON list of subcommands")
            default_sub = _DEFAULT_SUBCOMMAND.get(verb)
            if default_sub:
                print(
                    f"       {verb} --preset <P> --name <N> ...  "
                    f"# flat form of '{default_sub}'"
                )
        return 0 if args else 2

    default_sub = _DEFAULT_SUBCOMMAND.get(verb)
    if args[0].startswith("-") and default_sub:
        sub = default_sub
        rest = _flatten_build_args(args) if default_sub == "build" else list(args)
    else:
        sub, rest = args[0], args[1:]

    module_name = table.get(sub)
    if module_name is None:
        err = {
            "error": "unknown_subcommand",
            "verb": verb,
            "given": sub,
            "valid": sorted(table),
        }
        _emit(err, sys.stderr, quiet=quiet)
        return 2

    # Support "module:func" entries so one module can back several
    # subcommands; bare "module" defaults to its module-level main().
    if ":" in module_name:
        mod_path, func_name = module_name.split(":", 1)
    else:
        mod_path, func_name = module_name, "main"
    module = importlib.import_module(mod_path)
    rc = int(getattr(module, func_name)(rest) or 0)
    if json_mode:
        _emit(
            {"verb": verb, "subcommand": sub, "args": rest, "exit_code": rc},
            sys.stdout,
            quiet=quiet,
        )
    return rc


def new_main(argv: list[str] | None = None) -> int:
    return _dispatch("vkmql-new", NEW_SUBCOMMANDS, argv)


def check_main(argv: list[str] | None = None) -> int:
    return _dispatch("vkmql-check", CHECK_SUBCOMMANDS, argv)


def ship_main(argv: list[str] | None = None) -> int:
    return _dispatch("vkmql-ship", SHIP_SUBCOMMANDS, argv)


def agent_main(argv: list[str] | None = None) -> int:
    """vkmql-agent — agent orchestration over the TIP loop (v2.6)."""
    from .agent_cli import main as _agent_main

    return _agent_main(argv)


# ---- Legacy compat shims -------------------------------------------------
# Brand-new aliases that simply emit a structured deprecation notice (stderr)
# pointing at the canonical vkmql-* verb, then delegate. Zero behaviour change
# for the underlying tools; provided so external scripts can adopt the shim
# names and get a machine-readable migration breadcrumb.
_SHIM_MAP = {
    "mql5-new": ("vkmql-new", new_main),
    "mql5-check": ("vkmql-check", check_main),
    "mql5-ship-flow": ("vkmql-ship", ship_main),
}


def _shim(old: str) -> int:
    replacement, target = _SHIM_MAP[old]
    warn_deprecated(old, replacement, removed_in="3.0.0")
    return target(None)


def new_shim_main(argv: list[str] | None = None) -> int:
    warn_deprecated("mql5-new", "vkmql-new", removed_in="3.0.0")
    return new_main(argv)


def check_shim_main(argv: list[str] | None = None) -> int:
    warn_deprecated("mql5-check", "vkmql-check", removed_in="3.0.0")
    return check_main(argv)


def ship_shim_main(argv: list[str] | None = None) -> int:
    warn_deprecated("mql5-ship-flow", "vkmql-ship", removed_in="3.0.0")
    return ship_main(argv)


if __name__ == "__main__":
    sys.exit(new_main())
