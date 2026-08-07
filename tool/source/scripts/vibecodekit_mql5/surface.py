"""Public command-surface tiers (v2.5 hardening, #4).

118 console-scripts overwhelm an end-user. This module is the single source of
truth for the *tier* of every command so docs, the tool catalog and onboarding
can lead with a tiny public surface and keep advanced/internal tooling behind
it. It removes nothing -- every legacy command still works -- it only labels.

Tiers:
  public    -- the 5 commands a normal user ever needs to type. Every other
               capability is reachable through these verbs (the ``vkmql-*``
               verbs dispatch into the ``mql5-*`` primitives).
  internal  -- plumbing / shims / metadata emitters; correct to exist but not
               something a human is expected to call directly.
  advanced  -- everything else: power-user / dev tools.
"""
from __future__ import annotations

# The five canonical end-user commands.
PUBLIC_COMMANDS: tuple[str, ...] = (
    "vkmql-new",
    "vkmql-check",
    "vkmql-ship",
    "mql5-ea-deep-review",
    "mql5-doctor",
)

# Plumbing / deprecated shims / machine-only emitters.
INTERNAL_COMMANDS: frozenset[str] = frozenset({
    "mql5-manifest",
    "mql5-agent-contract",
    "mql5-new",        # deprecated shim -> vkmql-new
    "mql5-check",      # deprecated shim -> vkmql-check
    "mql5-ship-flow",  # deprecated shim -> vkmql-ship
    "mql5-selftest",
})

PUBLIC = "public"
ADVANCED = "advanced"
INTERNAL = "internal"


def tier_of(name: str) -> str:
    """Classify a console-script name into its UX tier."""
    if name in PUBLIC_COMMANDS:
        return PUBLIC
    if name in INTERNAL_COMMANDS:
        return INTERNAL
    return ADVANCED


__all__ = ["PUBLIC_COMMANDS", "INTERNAL_COMMANDS", "PUBLIC", "ADVANCED", "INTERNAL", "tier_of"]
