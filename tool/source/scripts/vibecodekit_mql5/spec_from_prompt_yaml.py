"""PR-11 — stdlib YAML emitter helpers used by ``spec_from_prompt``.

Kept tiny + dependency-free (no pyyaml) so it can be imported in
environments where the optional dep is missing. The two public
helpers handle the subset of types that
:func:`vibecodekit_mql5.spec_from_prompt.parse` and the PR-2 / PR-8
block matchers produce:

* scalars (``bool`` / ``int`` / ``float`` / ``str``)
* lists of scalars (``[a, b, c]`` shorthand)
* lists of single-level dicts
  (``partial_close.levels: [{at_pips, pct}]``)
* nested dicts (one level deep)

Output is deterministic — keys are sorted within each block so test
fixtures don't churn between runs.
"""

from __future__ import annotations


def emit_yaml_scalar(value: object) -> str:
    """Render a scalar to a stable YAML form."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"unsupported scalar: {value!r}")


def emit_yaml_block(block: dict, indent: int = 2) -> list[str]:
    """Render a single optional-block dict in YAML form.

    Handles scalars, lists of scalars, and lists of single-level dicts
    (e.g. ``partial_close.levels: [{at_pips, pct}]``). Sorted keys
    keep diff noise down across runs.
    """
    pad = " " * indent
    out: list[str] = []
    for key in sorted(block.keys()):
        value = block[key]
        if isinstance(value, dict):
            out.append(f"{pad}{key}:")
            out.extend(emit_yaml_block(value, indent=indent + 2))
        elif isinstance(value, list):
            if not value:
                out.append(f"{pad}{key}: []")
                continue
            if all(isinstance(v, dict) for v in value):
                out.append(f"{pad}{key}:")
                for entry in value:
                    inner_pad = " " * (indent + 2)
                    first = True
                    for ek in sorted(entry.keys()):
                        prefix = (f"{pad}  - " if first else f"{inner_pad}  ")
                        out.append(f"{prefix}{ek}: {emit_yaml_scalar(entry[ek])}")
                        first = False
            else:
                joined = ", ".join(emit_yaml_scalar(v) for v in value)
                out.append(f"{pad}{key}: [{joined}]")
        else:
            out.append(f"{pad}{key}: {emit_yaml_scalar(value)}")
    return out
