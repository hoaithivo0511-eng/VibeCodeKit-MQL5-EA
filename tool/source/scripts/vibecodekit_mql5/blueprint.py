"""/mql5-blueprint — open the Step 4 (BLUEPRINT) template.

Thin wrapper: prints the Markdown template body
from ``docs/rri-templates/step-4-blueprint.md.tmpl`` to stdout so the caller can
pipe it into an editor or PR description.  No state, no side effect.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._resources import template_path

TEMPLATE = template_path("step-4-blueprint.md.tmpl")


def render() -> str:
    if not TEMPLATE.exists():
        return f"# BLUEPRINT\\n\\n(template not installed: {TEMPLATE})\\n"
    return TEMPLATE.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-blueprint")
    parser.parse_args(argv)
    sys.stdout.write(render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
