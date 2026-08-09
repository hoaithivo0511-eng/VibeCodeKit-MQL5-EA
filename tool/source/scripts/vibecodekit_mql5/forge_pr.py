"""mql5-forge-pr — open a pull request on MQL5 Algo Forge.

Sibling of :mod:`vibecodekit_mql5.forge_init`. Uses the same API base and
token rules. Tests can inject a custom ``transport`` callable.

The default behaviour is to retry **once** on HTTP 401 (transient token
race or stale OAuth refresh — rare but observed in Algo Forge logs).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .forge_init import ForgeReport, DEFAULT_BASE, _default_transport


@dataclass
class PrSpec:
    repo: str
    head: str
    base: str
    title: str
    body: str = ""


def open_pr(
    spec: PrSpec, token: str, base_url: str = DEFAULT_BASE,
    transport: Callable | None = None, retry_on_401: bool = True,
) -> ForgeReport:
    endpoint = f"{base_url}/repos/{spec.repo}/pulls"
    payload = json.dumps({
        "head": spec.head,
        "base": spec.base,
        "title": spec.title,
        "body": spec.body,
    }).encode("utf-8")
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
    }

    def _do() -> tuple[int, dict]:
        req = urllib.request.Request(
            endpoint, data=payload, method="POST", headers=headers,
        )
        tx = transport or _default_transport
        return tx(req)

    status, body = _do()
    if status == 401 and retry_on_401:
        status, body = _do()

    return ForgeReport(
        ok=200 <= status < 300, endpoint=endpoint,
        status=status, body=body,
        error="" if 200 <= status < 300 else body.get("error", "unknown"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-forge-pr")
    parser.add_argument("repo", help="Repository in 'owner/name' form")
    parser.add_argument("--head", required=True, help="Source branch")
    parser.add_argument("--base", default="main", help="Target branch (default main)")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--token", default=None)
    parser.add_argument("--api-base", default=DEFAULT_BASE)
    args = parser.parse_args(argv)

    token = args.token or os.environ.get("MQL5_FORGE_TOKEN", "")
    if not token:
        print(
            "ERROR: no token — provide --token or set MQL5_FORGE_TOKEN",
            file=sys.stderr,
        )
        return 2
    spec = PrSpec(
        repo=args.repo, head=args.head, base=args.base,
        title=args.title, body=args.body,
    )
    rep = open_pr(spec, token=token, base_url=args.api_base)
    print(rep.as_json())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
