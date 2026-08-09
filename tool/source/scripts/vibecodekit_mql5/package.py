"""mql5-package — produce a ship-ready EA artifact bundle.

The packager audits an ``mql5-auto-build`` output directory, writes a
``manifest.json`` with SHA-256 checksums, groups artifacts by purpose,
and creates a zip file ready to hand to an operator or attach to a
release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from . import release_policy


DEFAULT_MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class PackageArtifact:
    path: str
    group: str
    kind: str
    size: int
    sha256: str
    archive_path: str


@dataclass
class PackageManifest:
    package_version: int
    out_dir: str
    created_at: str
    zip_path: str
    artifacts: list[PackageArtifact] = field(default_factory=list)
    groups: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["artifacts"] = [asdict(a) for a in self.artifacts]
        return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_artifact(path: Path, out_dir: Path) -> tuple[str, str] | None:
    rel = path.relative_to(out_dir).as_posix()
    name = path.name.lower()
    suffix = path.suffix.lower()
    parts = {p.lower() for p in path.relative_to(out_dir).parts}

    if name == DEFAULT_MANIFEST_NAME or suffix == ".zip":
        return None
    if suffix == ".ex5":
        return "runtime", "compiled-ea"
    if suffix == ".set" or "sets" in parts:
        return "runtime", "tester-set"
    if suffix == ".mq5":
        return "source", "ea-source"
    if suffix == ".mqh":
        return "source", "include"
    if name == "readme.md":
        return "source", "scaffold-readme"
    if name == "auto-build-report.json":
        return "review", "auto-build-report"
    if name == "quality-matrix.html":
        return "review", "quality-dashboard"
    if ".docs." in name:
        return "review", f"ea-docs-{suffix.lstrip('.')}"
    if suffix == ".log":
        return "review", "compile-log"
    # LLM-driven `.docx` ship pipeline (PR ship-docx): docs-context.json
    # + docs-prompt.md are the regenerable inputs to the LLM step, and
    # guide.md is the LLM's intermediate markdown. They live in the
    # `repro` group so a reviewer can re-run the assembly later without
    # cluttering the primary `review` deliverable (`.docs.docx`).
    if name == "docs-context.json":
        return "repro", "docs-context"
    if name == "docs-prompt.md":
        return "repro", "docs-prompt"
    if name == "guide.md":
        return "repro", "docs-guide-md"
    if (
        suffix in {".yaml", ".yml", ".json"}
        and "spec" in name
        and rel != DEFAULT_MANIFEST_NAME
    ):
        return "repro", "ea-spec"
    if suffix in {".onnx", ".csv"}:
        return "repro", suffix.lstrip(".")
    return None


def _artifact_for_file(path: Path, out_dir: Path) -> PackageArtifact | None:
    classified = classify_artifact(path, out_dir)
    if classified is None:
        return None
    group, kind = classified
    rel = path.relative_to(out_dir).as_posix()
    return PackageArtifact(
        path=rel,
        group=group,
        kind=kind,
        size=path.stat().st_size,
        sha256=sha256_file(path),
        archive_path=rel,
    )


def _external_spec_artifact(spec_path: Path, out_dir: Path) -> PackageArtifact:
    archive_path = f"repro/{spec_path.name}"
    try:
        rel = spec_path.resolve().relative_to(out_dir.resolve()).as_posix()
    except ValueError:
        rel = str(spec_path)
    return PackageArtifact(
        path=rel,
        group="repro",
        kind="ea-spec",
        size=spec_path.stat().st_size,
        sha256=sha256_file(spec_path),
        archive_path=archive_path,
    )


def collect_artifacts(out_dir: Path, spec_path: Path | None = None) -> list[PackageArtifact]:
    if not out_dir.is_dir():
        raise FileNotFoundError(f"out-dir not found: {out_dir}")

    artifacts: list[PackageArtifact] = []
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file():
            continue
        artifact = _artifact_for_file(path, out_dir)
        if artifact is not None:
            artifacts.append(artifact)

    if spec_path is not None:
        if not spec_path.is_file():
            raise FileNotFoundError(f"spec not found: {spec_path}")
        try:
            spec_path.resolve().relative_to(out_dir.resolve())
            inside_out_dir = True
        except ValueError:
            inside_out_dir = False
        if not inside_out_dir:
            artifacts.append(_external_spec_artifact(spec_path, out_dir))

    return artifacts


def build_manifest(
    out_dir: Path,
    *,
    zip_path: Path,
    spec_path: Path | None = None,
    created_at: str | None = None,
) -> PackageManifest:
    artifacts = collect_artifacts(out_dir, spec_path=spec_path)
    groups: dict[str, list[str]] = {}
    for artifact in artifacts:
        groups.setdefault(artifact.group, []).append(artifact.path)
    return PackageManifest(
        package_version=1,
        out_dir=str(out_dir),
        created_at=created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        zip_path=str(zip_path),
        artifacts=artifacts,
        groups={k: sorted(v) for k, v in sorted(groups.items())},
    )


def write_manifest(manifest: PackageManifest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    return path


def write_zip(
    manifest: PackageManifest,
    out_dir: Path,
    *,
    zip_path: Path,
    manifest_path: Path,
    spec_path: Path | None = None,
) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for artifact in manifest.artifacts:
            src = out_dir / artifact.path
            if not src.is_file() and spec_path is not None and artifact.archive_path.startswith("repro/"):
                src = spec_path
            zf.write(src, artifact.archive_path)
        zf.write(manifest_path, DEFAULT_MANIFEST_NAME)
    return zip_path


def package_out_dir(
    out_dir: Path,
    *,
    manifest_path: Path | None = None,
    zip_path: Path | None = None,
    spec_path: Path | None = None,
) -> PackageManifest:
    ok, reason = release_policy.validate_release_manifest(out_dir)
    if not ok:
        raise RuntimeError(f"blocked: package is not release eligible ({reason})")
    # Docs gate (v2.6+): ship docs come from the LLM structure-driven
    # pipeline. The deterministic build-time deliverable is the docs
    # bundle (docs-context.json + docs-prompt.md) emitted by
    # mql5-docs-bundle from the REAL parsed .mq5 inputs. The legacy
    # fixed-template docx (EA-LOGIC-AND-INPUTS-vi.docx) and its
    # ea-doc-verify.json were removed, so they are no longer required.
    required_context = out_dir / "docs" / "docs-context.json"
    required_prompt = out_dir / "docs" / "docs-prompt.md"
    if not required_context.is_file() or not required_prompt.is_file():
        raise RuntimeError("blocked: missing required EA documentation bundle docs/docs-context.json + docs/docs-prompt.md (run mql5-docs-bundle)")
    manifest_target = manifest_path or (out_dir / DEFAULT_MANIFEST_NAME)
    zip_target = zip_path or (out_dir / f"{out_dir.name}-ship.zip")
    manifest = build_manifest(out_dir, zip_path=zip_target, spec_path=spec_path)
    write_manifest(manifest, manifest_target)
    write_zip(
        manifest,
        out_dir,
        zip_path=zip_target,
        manifest_path=manifest_target,
        spec_path=spec_path,
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-package")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--zip", dest="zip_path", type=Path, default=None)
    parser.add_argument("--spec", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        manifest = package_out_dir(
            args.out_dir,
            manifest_path=args.manifest,
            zip_path=args.zip_path,
            spec_path=args.spec,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"mql5-package: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
