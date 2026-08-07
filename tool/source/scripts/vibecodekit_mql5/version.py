"""mql5-version — print the single-source kit version."""
from __future__ import annotations

import argparse
import json
import sys

from . import _version


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-version")
    p.add_argument("--json", action="store_true", dest="as_json")
    args = p.parse_args(argv)
    data = {"kit": "vibecodekit-mql5-ea", "version": _version.get_version()}
    if args.as_json:
        sys.stdout.write(json.dumps(data) + "\\n")
    else:
        print(f"{data['kit']} {data['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
