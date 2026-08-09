"""Homeowner sign-off audit (BLUEPRINT APPROVED + CONTRACT CONFIRM).

The Triangle of Power introduced in adds two human-driven
sign-off gates between the deterministic steps:

* **CHECKPOINT** — at the bottom of ``step-4-blueprint.md`` the Homeowner
  appends a line matching::

      APPROVED by <name> at <YYYY-MM-DD>

* **CONFIRM** — at the bottom of ``contract.md`` the Homeowner appends::

      CONFIRM by <name> at <YYYY-MM-DD>

This module is the audit half of those gates. It is read-only: it never
modifies the artefact bodies and never invents signatures. The
``audit_sign_off`` function returns a structured verdict that the
layer-5 methodology gate consumes when ``--enforce-sign-off`` is passed.

Hash semantics:

* For each artefact we strip the matching sign-off line, take the
  sha256 of the remaining canonical body, and return the digest in the
  verdict. The Contractor LLM can store the digest in its session log
  so a later re-audit catches "body silently swapped after APPROVED"
  attacks.
* No HMAC / GPG / asymmetric crypto in . The pure-hash approach
  is enough to block the most common failure mode (operator forgets to
  re-sign after editing) and stays compatible with markdown-only diffs
  on every code-review platform.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

APPROVED_PATTERN = re.compile(
    r"^\s*APPROVED\s+by\s+(?P<name>\S.*?)\s+at\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)
CONFIRM_PATTERN = re.compile(
    r"^\s*CONFIRM\s+by\s+(?P<name>\S.*?)\s+at\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)

# Default artefact filenames the layer-5 sentinel looks for. The
# operator can override via ``audit_sign_off`` arguments, but these
# defaults match the generator output (``mql5-blueprint-gen``
# default ``--out step-4-blueprint.md`` and ``mql5-contract-gen`` default
# ``--out contract.md``).
DEFAULT_BLUEPRINT_NAMES = (
    "step-4-blueprint.md",
    "blueprint.md",
)
DEFAULT_CONTRACT_NAMES = (
    "contract.md",
    "step-4-5-contract.md",
)


@dataclass(frozen=True)
class SignOffAudit:
    """Structured outcome of a single artefact sign-off audit."""

    artefact: str           # "blueprint" or "contract"
    path: Path | None
    found: bool
    signer: str | None
    signed_at: str | None
    canonical_sha256: str | None
    error: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "artefact": self.artefact,
            "path": str(self.path) if self.path else None,
            "found": self.found,
            "signer": self.signer,
            "signed_at": self.signed_at,
            "canonical_sha256": self.canonical_sha256,
            "error": self.error,
        }


def _canonical_sha256(body: str, pattern: re.Pattern[str]) -> str:
    """Hash the body with any sign-off line(s) stripped."""

    canonical = pattern.sub("", body).strip() + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve(path: Path | None, candidates: tuple[str, ...], *,
             search_dirs: tuple[Path, ...]) -> Path | None:
    """Best-effort artefact resolution.

    Precedence:
    1. Explicit ``path`` argument (if it is a file).
    2. First matching ``candidates`` filename in any of ``search_dirs``.
    """

    if path is not None and path.is_file():
        return path
    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for name in candidates:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def audit_artefact(
    *,
    artefact: str,
    path: Path | None,
    pattern: re.Pattern[str],
    candidates: tuple[str, ...],
    search_dirs: tuple[Path, ...],
) -> SignOffAudit:
    """Run the audit for a single artefact (blueprint or contract)."""

    resolved = _resolve(path, candidates, search_dirs=search_dirs)
    if resolved is None:
        return SignOffAudit(
            artefact=artefact,
            path=path,
            found=False,
            signer=None,
            signed_at=None,
            canonical_sha256=None,
            error=(
                f"{artefact} not found "
                f"(searched: {', '.join(candidates)} in "
                f"{', '.join(str(d) for d in search_dirs)})"
            ),
        )
    try:
        body = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return SignOffAudit(
            artefact=artefact,
            path=resolved,
            found=False,
            signer=None,
            signed_at=None,
            canonical_sha256=None,
            error=f"read failed: {exc}",
        )
    match = pattern.search(body)
    if match is None:
        return SignOffAudit(
            artefact=artefact,
            path=resolved,
            found=False,
            signer=None,
            signed_at=None,
            canonical_sha256=_canonical_sha256(body, pattern),
            error=f"{artefact} body lacks a sign-off line",
        )
    return SignOffAudit(
        artefact=artefact,
        path=resolved,
        found=True,
        signer=match.group("name").strip(),
        signed_at=match.group("date").strip(),
        canonical_sha256=_canonical_sha256(body, pattern),
        error=None,
    )


def audit_sign_off(
    *,
    blueprint_path: Path | None = None,
    contract_path: Path | None = None,
    require_contract: bool = True,
    state_dir: Path | None = None,
) -> tuple[bool, list[SignOffAudit]]:
    """Audit both BLUEPRINT and (optionally) CONTRACT sign-off lines.

    Parameters
    ----------
    blueprint_path:
        Explicit path to ``step-4-blueprint.md``. When ``None``, the
        layer searches ``.``, ``state_dir``, and ``state_dir.parent``.
    contract_path:
        Explicit path to ``contract.md``. Same search rules apply.
    require_contract:
        When ``True`` (the default, enabled by team / enterprise mode),
        a missing or unsigned contract fails the audit. Personal mode
        callers may pass ``False`` to only require the blueprint
        sign-off (the contract is then optional).
    state_dir:
        Optional sentinel state directory (``.rri-state/``). Used as an
        additional search root.

    Returns
    -------
    tuple
        ``(ok, audits)`` — ``ok`` is ``True`` only when every required
        artefact has a sign-off line; ``audits`` is the list of
        per-artefact :class:`SignOffAudit` records.
    """

    search_dirs: list[Path] = []
    if state_dir is not None:
        search_dirs.append(state_dir)
        # The kit's convention puts step output files alongside the
        # state dir's parent (repo root) so we also probe there.
        search_dirs.append(state_dir.parent if state_dir.parent != state_dir else Path("."))
    search_dirs.append(Path("."))
    search_dirs.append(Path("docs"))
    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduped: list[Path] = []
    for d in search_dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)
    search_tuple = tuple(deduped)

    audits: list[SignOffAudit] = []
    audits.append(
        audit_artefact(
            artefact="blueprint",
            path=blueprint_path,
            pattern=APPROVED_PATTERN,
            candidates=DEFAULT_BLUEPRINT_NAMES,
            search_dirs=search_tuple,
        )
    )
    if require_contract or contract_path is not None:
        audits.append(
            audit_artefact(
                artefact="contract",
                path=contract_path,
                pattern=CONFIRM_PATTERN,
                candidates=DEFAULT_CONTRACT_NAMES,
                search_dirs=search_tuple,
            )
        )

    required_ok = [a.found for a in audits]
    # If contract is optional and missing, drop it from the required set.
    if not require_contract and len(audits) > 1 and not audits[1].found:
        required_ok = [audits[0].found]
    ok = all(required_ok)
    return ok, audits


__all__ = [
    "APPROVED_PATTERN",
    "CONFIRM_PATTERN",
    "DEFAULT_BLUEPRINT_NAMES",
    "DEFAULT_CONTRACT_NAMES",
    "SignOffAudit",
    "audit_artefact",
    "audit_sign_off",
]
