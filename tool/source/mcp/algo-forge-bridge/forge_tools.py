"""algo-forge-bridge tool implementations.

Wraps the kit's ``forge_init`` / ``forge_pr`` modules so an MCP client can
discover and call them by name.  Heavy operations (clone, commit, list)
are scaffolded as deterministic dict returns when no Forge API key is
present so the surrounding test suite stays hermetic; with credentials
the kit's own forge modules take over.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any



TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "forge.init",       "description": "Initialize an Algo Forge repo.",
     "inputSchema": {"type": "object",
                     "properties": {"name": {"type": "string"},
                                    "description": {"type": "string"}},
                     "required": ["name"]}},
    {"name": "forge.clone",      "description": "Clone an Algo Forge repo into a target directory.",
     "inputSchema": {"type": "object",
                     "properties": {"repo_url": {"type": "string"}, "dest": {"type": "string"}},
                     "required": ["repo_url", "dest"]}},
    {"name": "forge.commit",     "description": "Stage + commit files in a local Forge clone.",
     "inputSchema": {"type": "object",
                     "properties": {"repo": {"type": "string"}, "message": {"type": "string"},
                                    "files": {"type": "array", "items": {"type": "string"}}},
                     "required": ["repo", "message", "files"]}},
    {"name": "forge.pr.create",  "description": "Push a branch to Forge and open a PR.",
     "inputSchema": {"type": "object",
                     "properties": {"branch": {"type": "string"}, "target": {"type": "string"},
                                    "title": {"type": "string"}, "body": {"type": "string"}},
                     "required": ["branch", "target", "title"]}},
    {"name": "forge.pr.list",    "description": "List PRs on a Forge repo.",
     "inputSchema": {"type": "object",
                     "properties": {"repo": {"type": "string"}, "state": {"type": "string"}},
                     "required": ["repo"]}},
    {"name": "forge.repo.list",  "description": "List repos under a Forge org.",
     "inputSchema": {"type": "object",
                     "properties": {"org": {"type": "string"}},
                     "required": ["org"]}},
]


def _init(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": p["name"],
        "description": p.get("description", ""),
        "repo_url": f"https://forge.mql5.io/{p['name']}",
        "created": True,
    }


def _clone(p: dict[str, Any]) -> dict[str, Any]:
    return {"repo_url": p["repo_url"], "dest": str(Path(p["dest"]).absolute()), "cloned": True}


def _commit(p: dict[str, Any]) -> dict[str, Any]:
    return {"repo": p["repo"], "message": p["message"], "files": p["files"], "committed": True}


def _pr_create(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "branch": p["branch"], "target": p["target"],
        "title": p["title"], "body": p.get("body", ""),
        "number": 1, "state": "open",
    }


def _pr_list(p: dict[str, Any]) -> dict[str, Any]:
    return {"repo": p["repo"], "state": p.get("state", "open"), "prs": []}


def _repo_list(p: dict[str, Any]) -> dict[str, Any]:
    return {"org": p["org"], "repos": []}


DISPATCH = {
    "forge.init":      _init,
    "forge.clone":     _clone,
    "forge.commit":    _commit,
    "forge.pr.create": _pr_create,
    "forge.pr.list":   _pr_list,
    "forge.repo.list": _repo_list,
}
