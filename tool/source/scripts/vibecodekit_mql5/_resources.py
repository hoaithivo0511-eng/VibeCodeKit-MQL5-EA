"""Runtime asset resolution for vibecodekit_mql5.

The kit ships runtime assets (``scaffolds/``, ``Include/``, ``profiles/`` and
the RRI step templates) *inside* the installed package under
``vibecodekit_mql5/resources/`` so they survive a non-editable wheel install.

Historically these were read via ``Path(__file__).resolve().parents[2]`` which
only works when the package is imported from the source checkout. After a
``pip install <wheel>`` that path points somewhere like ``/tmp`` and the kit
breaks. This module resolves assets from the packaged copy first and only
falls back to the source-tree layout for editable installs / dev checkouts.

Rule of thumb:
* Use :func:`asset_root` for *runtime* assets that must ship with the wheel.
* Use :func:`repo_root` only for operations that intentionally act on the
  source repository (e.g. ``mql5-doctor --check-version`` reading
  ``pyproject.toml``/``VERSION``), never for runtime asset lookups.
"""
from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

# Source-checkout repo root: .../scripts/vibecodekit_mql5/_resources.py -> parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Where runtime assets live relative to the source repo root, keyed by the
# logical asset-group name used by callers. The packaged copy always lives at
# ``resources/<name>``; the repo copy may differ (rri-templates lives under
# ``docs/`` in the source tree).
_REPO_SUBPATHS: dict[str, str] = {
    "scaffolds": "scaffolds",
    "Include": "Include",
    "profiles": "profiles",
    "rri-templates": "docs/rri-templates",
}


def _packaged_resources_root() -> Path | None:
    """Return the packaged ``resources/`` directory, or ``None`` if absent."""
    try:
        traversable = resources.files("vibecodekit_mql5") / "resources"
    except (ModuleNotFoundError, AttributeError, TypeError):
        return None
    try:
        path = Path(str(traversable))
    except TypeError:
        return None
    return path if path.is_dir() else None


def repo_root() -> Path:
    """Return the source-checkout repository root.

    Only valid in editable/dev installs. Do not use for runtime asset lookups.
    """
    return _REPO_ROOT


def distribution_root() -> Path:
    """Return metadata root for source and installed-wheel self-tests.

    A source checkout uses the repository root.  A wheel uses the immutable
    metadata snapshot shipped under ``resources/distribution``.
    """
    if (_REPO_ROOT / "pyproject.toml").is_file() and (_REPO_ROOT / "tool-catalog.json").is_file():
        return _REPO_ROOT
    packaged = _packaged_resources_root()
    if packaged is not None:
        candidate = packaged / "distribution"
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return _REPO_ROOT


def asset_root(name: str) -> Path:
    """Resolve a runtime asset group directory.

    Prefers the packaged copy (``vibecodekit_mql5/resources/<name>``) so the
    kit works after a wheel install, and falls back to the source-tree layout
    for editable installs / dev checkouts.
    """
    packaged = _packaged_resources_root()
    if packaged is not None:
        candidate = packaged / name
        if candidate.exists():
            return candidate
    repo_sub = _REPO_SUBPATHS.get(name, name)
    return _REPO_ROOT / repo_sub


def template_path(filename: str) -> Path:
    """Resolve an RRI step template file under the ``rri-templates`` group."""
    return asset_root("rri-templates") / filename


# --- Distribution flavor -------------------------------------------------
# The kit ships in two flavors:
#   * "full"  — the governance/docs source repository (references docs, plan,
#               anti-patterns, CI definitions, methodology). This is the dev /
#               source-checkout layout.
#   * "slim"  — a standalone runtime install (e.g. a wheel) that ships only the
#               runtime assets under ``resources/`` and the Python package. The
#               docs/governance repo is intentionally absent.
# Health tools (doctor/audit) must not hard-fail "missing docs repo" checks in
# slim mode — those artifacts simply do not ship there.
_VALID_FLAVORS: tuple[str, ...] = ("slim", "full", "commercial")

# Declared flavor for THIS distribution and single source of truth. The
# consolidated kit ships as "slim": the runtime tool + packaged assets, without
# the full references/governance docs corpus (50-survey, references,
# etc.) that was intentionally removed during consolidation. A distribution that
# bundles that complete corpus declares "full" (set VCK_FLAVOR=full or patch
# this constant), which re-enables the references/governance health probes.
_DECLARED_FLAVOR: str = "slim"


def kit_flavor() -> str:
    """Return the active distribution flavor: ``"full"`` or ``"slim"``.

    Resolution order:
      1. ``VCK_FLAVOR`` environment override (``slim`` / ``full``).
      2. The declared distribution flavor (:data:`_DECLARED_FLAVOR`).

    Health tools gate docs/governance-corpus probes on ``"full"`` so a slim
    runtime install does not hard-fail on artifacts it never shipped.
    """
    override = os.environ.get("VCK_FLAVOR", "").strip().lower()
    if override in _VALID_FLAVORS:
        return override
    return _DECLARED_FLAVOR
