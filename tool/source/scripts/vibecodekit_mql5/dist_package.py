"""mql5-dist - build a clean end-user distribution zip of the kit itself.

Unlike :mod:`vibecodekit_mql5.package` (which packages a *built EA's*
output directory), this command packages the **kit** for hand-off to an
end user. It deliberately excludes maintainer / dev-only files so the
shipped zip matches what the README promises:

  * VCS plumbing            - ``.git/``, ``.github/``, ``.gitignore``,
                              ``.gitattributes``
  * test + CI scaffolding   - ``tests/``, ``scripts/ci.sh``,
                              ``requirements.lock``
  * tool caches             - ``__pycache__/``, ``.pytest_cache/``,
                              ``.ruff_cache/``, ``.mypy_cache/``,
                              ``.mql5-audit/``
  * build leftovers         - ``*.pyc``/``*.pyo``, ``*.zip``, the dist
                              output dir itself

The zip is written **deterministically** (sorted entries + a fixed
timestamp) so two runs over the same tree produce byte-identical output,
and a ``dist-manifest.json`` records the kit version, flavor and a
SHA-256 for every shipped file.

Usage::

    mql5-dist [--repo-root DIR] [--out ZIP] [--manifest JSON]
              [--created-at ISO8601] [--include-dev]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import _resources, _version

DIST_MANIFEST_NAME = "dist-manifest.json"

# Reproducible-zip epoch (zip format cannot represent < 1980).
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

# Directory names excluded anywhere in the path.
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".github",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".mql5-audit",
        "_audit",
        "_deep_review",
        "_demo",
        "_stress",
        "releases",
        "dist",
        "build",
        "tests",
        "fixtures",
        "evidence",
        ".rri-state",
    }
)

# Exact basenames excluded anywhere.
EXCLUDED_FILE_NAMES: frozenset[str] = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        "requirements.lock",
        DIST_MANIFEST_NAME,
    }
)

# Exact repo-relative POSIX paths excluded.
EXCLUDED_RELPATHS: frozenset[str] = frozenset({"scripts/ci.sh"})

# Repo-relative POSIX path prefixes excluded from the end-user slim.
# ``docs/maintainer/`` holds internal/contributor docs that would only
# confuse end users and LLM agents consuming the kit; they stay in the
# repo (and in the ``full`` maintainer bundle) but never ship in the slim.
EXCLUDED_RELPATH_PREFIXES: tuple[str, ...] = ("docs/maintainer/",)

# File suffixes excluded anywhere.
EXCLUDED_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo", ".zip"})


def is_excluded(rel: Path, *, include_dev: bool = False) -> bool:
    """Return True when ``rel`` (repo-relative) is a dev/maintainer-only path.

    With ``include_dev=True`` only never-ship plumbing (VCS dirs, caches,
    build leftovers) is dropped; the maintainer surface (tests, CI,
    ``.github``, lockfile) is kept - useful for a ``full`` maintainer bundle.
    """
    parts = rel.parts
    never_ship_dirs = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".mql5-audit",
        "dist",
        "build",
    }
    excluded_dirs = never_ship_dirs if include_dev else set(EXCLUDED_DIR_NAMES)
    if any(part in excluded_dirs or part.endswith(".egg-info") for part in parts):
        return True
    # Runtime coverage databases are generated test artifacts, never source.
    if rel.name in {".coverage", "coverage.json"}:
        return True
    if not include_dev and any(part.startswith("vck-retro-") for part in parts):
        return True
    if not include_dev and any(part.startswith(".tmp-") for part in parts):
        return True
    if not include_dev and rel.name.endswith(".bak"):
        return True
    if rel.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if not include_dev:
        if rel.name in EXCLUDED_FILE_NAMES:
            return True
        if rel.as_posix() in EXCLUDED_RELPATHS:
            return True
        if any(rel.as_posix().startswith(p) for p in EXCLUDED_RELPATH_PREFIXES):
            return True
    else:
        if rel.name == DIST_MANIFEST_NAME:
            return True
    return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_dist_files(repo_root: Path, *, include_dev: bool = False) -> list[Path]:
    """Return sorted repo-relative paths that belong in the distribution."""
    if not repo_root.is_dir():
        raise FileNotFoundError(f"repo-root not found: {repo_root}")
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        if is_excluded(rel, include_dev=include_dev):
            continue
        files.append(rel)
    return sorted(files, key=lambda p: p.as_posix())


def build_dist_manifest(
    repo_root: Path,
    rel_files: list[Path],
    *,
    flavor: str | None = None,
    created_at: str | None = None,
) -> dict:
    entries = []
    for rel in rel_files:
        src = repo_root / rel
        entries.append(
            {
                "path": rel.as_posix(),
                "size": src.stat().st_size,
                "sha256": sha256_file(src),
            }
        )
    return {
        "schema_version": "1.0",
        "kind": "kit-distribution",
        "kit_version": _version.get_version(),
        "flavor": flavor or _resources.kit_flavor(),
        "created_at_utc": created_at
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file_count": len(entries),
        "files": entries,
    }


# 3-command quickstart injected into a "commercial" bundle so a non-developer
# buyer can go from unzip -> verified build with no repo knowledge.
_COMMERCIAL_QUICKSTART = """\
# Quick start (commercial bundle)

Three commands take you from this zip to a verified Expert Advisor build.

```bash
# 1. Verify the bundle imports cleanly on your machine
python3 -m vibecodekit_mql5.selftest

# 2. Build an EA from a preset into ./MyEA
python3 -m vibecodekit_mql5.build grid --name MyEA --symbol XAUUSD --tf M5 --out ./MyEA

# 3. See where the build stands in the golden flow
python3 -m vibecodekit_mql5.golden_flow --out-dir ./MyEA
```

Everything else (compile, backtest, gate, ship) is described in `docs/COMMANDS.md`.
"""

# Extra in-zip files generated per flavor (repo-relative posix path -> text).
_GENERATED_BY_FLAVOR: dict[str, dict[str, str]] = {
    "commercial": {"QUICKSTART-COMMERCIAL.md": _COMMERCIAL_QUICKSTART},
}


def write_dist_zip(
    repo_root: Path,
    rel_files: list[Path],
    zip_path: Path,
    *,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Write a deterministic (byte-stable) zip of ``rel_files``.

    ``extra_files`` are generated (not-on-disk) entries merged in by posix path;
    they participate in the same sort so output stays byte-stable.
    """
    extra_files = extra_files or {}
    on_disk = {rel.as_posix(): ("disk", rel) for rel in rel_files}
    generated = {name: ("gen", text) for name, text in extra_files.items()}
    merged = {**on_disk, **generated}
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(merged):
            kind, payload = merged[name]
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            data = (repo_root / payload).read_bytes() if kind == "disk" else payload.encode("utf-8")
            zf.writestr(info, data)
    return zip_path


def package_distribution(
    repo_root: Path,
    *,
    zip_path: Path,
    manifest_path: Path | None = None,
    include_dev: bool = False,
    flavor: str | None = None,
    created_at: str | None = None,
) -> dict:
    """Collect, manifest and zip the kit. Returns the manifest dict.

    ``flavor`` selects the bundle profile. When omitted it is derived from
    ``include_dev`` (full vs slim) to preserve legacy behaviour. ``commercial``
    ships the slim runtime surface plus generated buyer-facing files and is
    mutually exclusive with ``include_dev``.
    """
    if flavor is None:
        flavor = "full" if include_dev else "slim"
    if flavor not in _resources._VALID_FLAVORS:
        raise RuntimeError(
            f"unknown flavor {flavor!r}; valid: {_resources._VALID_FLAVORS}"
        )
    if flavor == "commercial" and include_dev:
        raise RuntimeError("--flavor commercial cannot be combined with --include-dev")
    # commercial uses the same end-user exclusions as slim (no tests/CI/.github/
    # maintainer docs); only full keeps the dev surface.
    use_include_dev = include_dev or flavor == "full"
    rel_files = collect_dist_files(repo_root, include_dev=use_include_dev)
    if not rel_files:
        raise RuntimeError(f"no shippable files found under {repo_root}")
    extra_files = _GENERATED_BY_FLAVOR.get(flavor, {})
    manifest = build_dist_manifest(
        repo_root, rel_files, flavor=flavor, created_at=created_at
    )
    # Generated files are part of the shipped bundle, so they belong in the
    # manifest (with hashes) too, not just the zip.
    if extra_files:
        for name, text in sorted(extra_files.items()):
            data = text.encode("utf-8")
            manifest["files"].append(
                {
                    "path": name,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "generated": True,
                }
            )
        manifest["files"].sort(key=lambda e: e["path"])
        manifest["file_count"] = len(manifest["files"])
    write_dist_zip(repo_root, rel_files, zip_path, extra_files=extra_files)
    manifest["zip_path"] = str(zip_path)
    manifest["zip_sha256"] = sha256_file(zip_path)
    target = manifest_path or (zip_path.parent / DIST_MANIFEST_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str(target)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-dist")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Kit source root (defaults to the installed/source repo root).",
    )
    parser.add_argument(
        "--out",
        dest="zip_path",
        type=Path,
        default=None,
        help="Output zip path (default: dist/<dist-name>-<version>.zip).",
    )
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--created-at", default=None, help="Fixed ISO-8601 UTC stamp.")
    parser.add_argument(
        "--include-dev",
        action="store_true",
        help="Build a maintainer (full) bundle that keeps tests/CI/.github.",
    )
    parser.add_argument(
        "--flavor",
        choices=sorted(_resources._VALID_FLAVORS),
        default=None,
        help="Bundle profile: slim (default), full (=--include-dev), or "
             "commercial (end-user hand-off with generated quickstart).",
    )
    args = parser.parse_args(argv)
    if args.flavor == "full":
        args.include_dev = True

    repo_root = (args.repo_root or _resources.repo_root()).resolve()
    version = _version.get_version()
    zip_path = (
        args.zip_path
        or repo_root / "dist" / f"{_version._DIST_NAME}-{version}.zip"
    )
    try:
        manifest = package_distribution(
            repo_root,
            zip_path=zip_path,
            manifest_path=args.manifest,
            include_dev=args.include_dev,
            flavor=args.flavor,
            created_at=args.created_at,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"mql5-dist: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
