"""mql5-forge-init — create a new repository on MQL5 Algo Forge.

the kit spec §13 — Team Git workflow for EA development. Algo Forge is the
official Git host run by MetaQuotes; its REST API mirrors GitHub's just
enough to support repo create / list / push.

Auth: an API token is read from ``$MQL5_FORGE_TOKEN`` (preferred) or from
the ``--token`` CLI flag. The token is never logged.

This module is mock-friendly: a custom ``transport`` callable can be
injected from tests, so the unit tests do not perform real HTTP.
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

DEFAULT_BASE = "https://forge.mql5.io/api/v1"


@dataclass
class ForgeReport:
    ok: bool
    endpoint: str
    status: int
    body: dict
    error: str = ""

    def as_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def _default_transport(req: urllib.request.Request) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            data = resp.read().decode("utf-8")
            body = json.loads(data) if data else {}
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.reason}
    except urllib.error.URLError as e:
        return 0, {"error": str(e.reason)}


def init_repo(
    name: str, token: str, base: str = DEFAULT_BASE,
    private: bool = True, transport: Callable | None = None,
) -> ForgeReport:
    endpoint = f"{base}/repos"
    payload = json.dumps({"name": name, "private": private}).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=payload, method="POST",
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        },
    )
    tx = transport or _default_transport
    status, body = tx(req)
    return ForgeReport(
        ok=200 <= status < 300, endpoint=endpoint, status=status, body=body,
        error="" if 200 <= status < 300 else body.get("error", "unknown"),
    )


def list_repos(
    token: str, base: str = DEFAULT_BASE,
    transport: Callable | None = None,
) -> ForgeReport:
    endpoint = f"{base}/user/repos"
    req = urllib.request.Request(
        endpoint, method="GET",
        headers={"Authorization": f"token {token}"},
    )
    tx = transport or _default_transport
    status, body = tx(req)
    return ForgeReport(
        ok=200 <= status < 300, endpoint=endpoint, status=status, body=body,
        error="" if 200 <= status < 300 else body.get("error", "unknown"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-forge-init")
    parser.add_argument("name", help="New repo name")
    parser.add_argument("--token", default=None, help="Forge API token (overrides env)")
    parser.add_argument("--private", action="store_true", default=True)
    parser.add_argument("--public", dest="private", action="store_false")
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args(argv)

    token = args.token or os.environ.get("MQL5_FORGE_TOKEN", "")
    if not token:
        print(
            "ERROR: no token — provide --token or set MQL5_FORGE_TOKEN",
            file=sys.stderr,
        )
        return 2
    rep = init_repo(args.name, token=token, base=args.base, private=args.private)
    print(rep.as_json())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
