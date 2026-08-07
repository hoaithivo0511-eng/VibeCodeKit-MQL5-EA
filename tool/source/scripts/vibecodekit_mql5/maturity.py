"""Module maturity registry (v2.5 hardening, #5).

Separates *release-grade* implementation from *scaffold* and *placeholder* so
docs and the catalog never let a user mistake an integration skeleton (ONNX
mini, LLM bridge, service bridge, VPS worker) for finished trading logic.

Levels:
  release-grade -- implemented + tested; safe to depend on.
  scaffold      -- emits a *starting structure* the user/AI must complete
                   (the build/project generators, VPS deploy skeleton).
  placeholder   -- integration skeleton / stub; NOT production trading logic
                   (ONNX embed/export, LLM bridges).

Anything not listed defaults to ``release-grade``. The list is intentionally
conservative and honest: it is better to under-claim than to let a stub look
finished.
"""
from __future__ import annotations

RELEASE_GRADE = "release-grade"
SCAFFOLD = "scaffold"
PLACEHOLDER = "placeholder"

_MATURITY: dict[str, str] = {
    # ML / inference integration skeletons -- NOT trained models or strategies.
    "vibecodekit_mql5.onnx_embed": PLACEHOLDER,
    "vibecodekit_mql5.onnx_export": PLACEHOLDER,
    "vibecodekit_mql5.ml_validate": PLACEHOLDER,
    # LLM / service bridges -- integration skeletons, no trading logic.
    "vibecodekit_mql5.llm_review_runner": PLACEHOLDER,
    "vibecodekit_mql5.ea_auto_llm_review": PLACEHOLDER,
    # Remote execution skeletons.
    "vibecodekit_mql5.remote_worker_client": SCAFFOLD,
    "vibecodekit_mql5.deploy_vps": SCAFFOLD,
    # Code generators emit a starting structure, never a finished EA.
    "vibecodekit_mql5.build": SCAFFOLD,
    "vibecodekit_mql5.project_gen": SCAFFOLD,
    "vibecodekit_mql5.init": SCAFFOLD,
}


def maturity_of(module_name: str) -> str:
    """Return the maturity level for a module path (default release-grade)."""
    return _MATURITY.get(module_name, RELEASE_GRADE)


def placeholders() -> list[str]:
    return sorted(k for k, v in _MATURITY.items() if v == PLACEHOLDER)


def scaffolds() -> list[str]:
    return sorted(k for k, v in _MATURITY.items() if v == SCAFFOLD)


__all__ = [
    "RELEASE_GRADE", "SCAFFOLD", "PLACEHOLDER",
    "maturity_of", "placeholders", "scaffolds",
]
