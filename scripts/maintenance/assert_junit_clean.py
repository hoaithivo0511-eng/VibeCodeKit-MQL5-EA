"""Fail a CI gate when a JUnit report contains failures, errors or skips."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def _count(root: ET.Element, key: str) -> int:
    if root.tag == "testsuite":
        return int(root.attrib.get(key, 0))
    return sum(int(suite.attrib.get(key, 0)) for suite in root.findall("testsuite"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)

    if not args.report.is_file():
        parser.error(f"JUnit report not found: {args.report}")

    root = ET.parse(args.report).getroot()
    totals = {
        key: _count(root, key)
        for key in ("tests", "failures", "errors", "skipped")
    }
    print(
        "JUnit summary: "
        + ", ".join(f"{key}={value}" for key, value in totals.items())
    )
    if totals["tests"] <= 0:
        raise SystemExit("JUnit gate failed: no tests were executed")
    if totals["failures"] or totals["errors"] or totals["skipped"]:
        raise SystemExit("JUnit gate failed: failures/errors/skips must all be zero")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
