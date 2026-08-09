"""Step-output generators.

Three deterministic emitters that turn the previous step's artefact into
a draft for the next step in the 8-step RRI methodology:

* :mod:`vibecodekit_mql5.step_gen.vision_gen` — RRI answers → step-3-vision.md
* :mod:`vibecodekit_mql5.step_gen.blueprint_gen` — ea-spec.yaml + step-3-vision.md → step-4-blueprint.md
* :mod:`vibecodekit_mql5.step_gen.tip_gen` — step-4-blueprint.md → step-5-tip.md

The generators are intentionally low-magic: they parse structured sections
(``## Activities``, ``## Invariants``, ``## Constraints``), populate a
canonical skeleton, and leave manual-fill slots clearly marked with
``TODO`` so a human (or downstream LLM persona) can refine. They never
call an LLM. Determinism is pinned by golden-output regression tests.
"""

from __future__ import annotations
