#!/usr/bin/env python3
"""Build and verify the RC6 candidate distribution from tracked tool/source.

Task 17 is a package-integration gate only. It deliberately keeps
release_eligible=false until Task 18 supplies trusted native evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tool" / "source"
SOURCE_SCRIPTS = SOURCE / "scripts"
if str(SOURCE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SOURCE_SCRIPTS))

from vibecodekit_mql5.wheel_repro import normalize_wheel, verify_wheel

VERSION = "3.3.0rc6"
SOURCE_ZIP = ROOT / "tool" / f"vibecodekit-mql5-v{VERSION}-source-full.zip"
SOURCE_MANIFEST = (
    ROOT / "tool" / f"vibecodekit-mql5-v{VERSION}-source-full.manifest.json"
)
WHEEL = ROOT / "tool" / f"vibecodekit_mql5_ea-{VERSION}-py3-none-any.whl"
RELEASE_DIR = ROOT / "docs" / "release" / f"v{VERSION}"
CANDIDATE_MANIFEST = RELEASE_DIR / "RC6-CANDIDATE-MANIFEST.json"
ARTIFACT_SUMS = RELEASE_DIR / "RC6-ARTIFACTS.sha256"
COMPLETION_REPORT = RELEASE_DIR / "TASK-17-COMPLETION.md"
RUNTIME_BUNDLE = ROOT / f"VibecodeKit-MQL5-v{VERSION}-runtime-candidate-bundle.zip"
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
SOURCE_DATE_EPOCH = "315532800"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def tracked_source_files() -> list[tuple[str, Path]]:
    raw = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "tool/source"], cwd=ROOT
    )
    names = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    files: list[tuple[str, Path]] = []
    for name in names:
        path = ROOT / name
        if not path.is_file():
            raise SystemExit(f"tracked source path is not a file: {name}")
        rel = path.relative_to(SOURCE).as_posix()
        if rel.startswith("../") or rel == ".":
            raise SystemExit(f"source path escaped tool/source: {name}")
        files.append((rel, path))
    if not files:
        raise SystemExit("no tracked files found under tool/source")
    return sorted(files, key=lambda item: item[0])


def zip_write_file(zf: zipfile.ZipFile, arcname: str, path: Path) -> None:
    pure = PurePosixPath(arcname)
    if pure.is_absolute() or ".." in pure.parts:
        raise SystemExit(f"unsafe archive path: {arcname}")
    info = zipfile.ZipInfo(pure.as_posix(), ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    executable = bool(path.stat().st_mode & 0o111)
    info.external_attr = (0o100755 if executable else 0o100644) << 16
    zf.writestr(info, path.read_bytes())


def source_tree_sha() -> str:
    return git("rev-parse", "HEAD:tool/source")


def build_source_archive(build_input_sha: str) -> dict:
    files = tracked_source_files()
    entries = [
        {"path": rel, "size": path.stat().st_size, "sha256": sha256(path)}
        for rel, path in files
    ]
    manifest = {
        "schema_version": "1.1",
        "kind": "kit-distribution",
        "kit_version": VERSION,
        "flavor": "full",
        "build_input_commit": build_input_sha,
        "source_tree_sha": source_tree_sha(),
        "file_count": len(entries),
        "files": entries,
    }
    SOURCE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    SOURCE_ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(SOURCE_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, path in files:
            zip_write_file(zf, rel, path)
    return manifest


def build_wheel(destination: Path = WHEEL) -> None:
    with tempfile.TemporaryDirectory(prefix="rc6-wheel-") as temp:
        env = os.environ.copy()
        env["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--disable-pip-version-check",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                temp,
                str(SOURCE),
            ],
            cwd=ROOT,
            env=env,
        )
        built = Path(temp) / WHEEL.name
        if not built.is_file():
            candidates = sorted(Path(temp).glob("*.whl"))
            raise SystemExit(
                f"expected wheel {WHEEL.name} not produced; got {[p.name for p in candidates]}"
            )
        normalize_wheel(built, destination)
        verify_wheel(destination)


def artifact_record(path: Path) -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


def build_candidate_manifest(build_input_sha: str, source_manifest: dict) -> dict:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "1.0",
        "kind": "rc6-candidate",
        "kit_version": VERSION,
        "status": "package-integrated-native-pending",
        "release_eligible": False,
        "release_blockers": [
            "Task 18 trusted native MetaEditor/MT5 compile evidence is pending",
            "Task 18 Strategy Tester evidence is pending",
            "Task 18 crash/restart recovery evidence is pending",
        ],
        "build_input_commit": build_input_sha,
        "source_tree_sha": source_manifest["source_tree_sha"],
        "artifacts": [
            artifact_record(SOURCE_ZIP),
            artifact_record(SOURCE_MANIFEST),
            artifact_record(WHEEL),
        ],
    }
    CANDIDATE_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return manifest


def build_runtime_bundle() -> None:
    members = [SOURCE_ZIP, SOURCE_MANIFEST, WHEEL, CANDIDATE_MANIFEST]
    RUNTIME_BUNDLE.unlink(missing_ok=True)
    with zipfile.ZipFile(RUNTIME_BUNDLE, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in members:
            zip_write_file(zf, path.relative_to(ROOT).as_posix(), path)


def write_artifact_sums() -> None:
    paths = [SOURCE_ZIP, SOURCE_MANIFEST, WHEEL, CANDIDATE_MANIFEST, RUNTIME_BUNDLE]
    ARTIFACT_SUMS.write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in paths
        ),
        encoding="utf-8",
        newline="\n",
    )


def verify_source_manifest() -> None:
    data = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if data.get("kit_version") != VERSION:
        raise SystemExit("source manifest version mismatch")
    if data.get("source_tree_sha") != source_tree_sha():
        raise SystemExit("source tree SHA drifted after candidate build")
    actual = {
        rel: (path.stat().st_size, sha256(path)) for rel, path in tracked_source_files()
    }
    declared = {
        item["path"]: (int(item["size"]), item["sha256"])
        for item in data.get("files", [])
    }
    if actual != declared:
        missing = sorted(set(actual) - set(declared))
        extra = sorted(set(declared) - set(actual))
        changed = sorted(
            path
            for path in set(actual) & set(declared)
            if actual[path] != declared[path]
        )
        raise SystemExit(
            f"source manifest mismatch: missing={missing[:10]} extra={extra[:10]} changed={changed[:10]}"
        )
    with zipfile.ZipFile(SOURCE_ZIP) as zf:
        names = sorted(info.filename for info in zf.infolist() if not info.is_dir())
        if names != sorted(declared):
            raise SystemExit("source ZIP member set does not match source manifest")
        for name in names:
            payload = zf.read(name)
            digest = hashlib.sha256(payload).hexdigest()
            size, expected = declared[name]
            if len(payload) != size or digest != expected:
                raise SystemExit(f"source ZIP payload mismatch: {name}")


def verify_candidate_manifest() -> None:
    data = json.loads(CANDIDATE_MANIFEST.read_text(encoding="utf-8"))
    if data.get("kit_version") != VERSION:
        raise SystemExit("candidate manifest version mismatch")
    if data.get("release_eligible") is not False:
        raise SystemExit("Task 17 candidate must remain release_eligible=false")
    expected_paths = {SOURCE_ZIP, SOURCE_MANIFEST, WHEEL}
    records = {ROOT / item["path"]: item for item in data.get("artifacts", [])}
    if set(records) != expected_paths:
        raise SystemExit("candidate manifest artifact set mismatch")
    for path, record in records.items():
        if (
            path.stat().st_size != int(record["size"])
            or sha256(path) != record["sha256"]
        ):
            raise SystemExit(f"candidate artifact digest mismatch: {path}")


def verify_runtime_bundle() -> None:
    expected = {
        SOURCE_ZIP.relative_to(ROOT).as_posix(): sha256(SOURCE_ZIP),
        SOURCE_MANIFEST.relative_to(ROOT).as_posix(): sha256(SOURCE_MANIFEST),
        WHEEL.relative_to(ROOT).as_posix(): sha256(WHEEL),
        CANDIDATE_MANIFEST.relative_to(ROOT).as_posix(): sha256(CANDIDATE_MANIFEST),
    }
    with zipfile.ZipFile(RUNTIME_BUNDLE) as zf:
        names = sorted(info.filename for info in zf.infolist() if not info.is_dir())
        if names != sorted(expected):
            raise SystemExit(f"runtime bundle member set mismatch: {names}")
        for name, digest in expected.items():
            payload = zf.read(name)
            if hashlib.sha256(payload).hexdigest() != digest:
                raise SystemExit(f"runtime bundle payload mismatch: {name}")


def verify_artifact_sums() -> None:
    declared: dict[str, str] = {}
    for raw in ARTIFACT_SUMS.read_text(encoding="utf-8").splitlines():
        digest, name = raw.split("  ", 1)
        declared[name] = digest
    paths = [SOURCE_ZIP, SOURCE_MANIFEST, WHEEL, CANDIDATE_MANIFEST, RUNTIME_BUNDLE]
    expected = {path.relative_to(ROOT).as_posix(): sha256(path) for path in paths}
    if declared != expected:
        raise SystemExit("RC6 artifact SHA-256 manifest mismatch")


def junit_summary(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    result = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in result:
            result[key] += int(suite.attrib.get(key, "0"))
    if result["failures"] or result["errors"] or result["skipped"]:
        raise SystemExit(f"unclean JUnit evidence {path}: {result}")
    return result


def selftest_summary(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "selftest "
    lines = [
        line
        for line in text.splitlines()
        if marker in line and "invariants passed" in line
    ]
    if not lines:
        raise SystemExit(f"selftest completion marker missing: {path}")
    tail = lines[-1].split(marker, 1)[1].split(" invariants passed", 1)[0]
    passed, total = (int(part) for part in tail.split("/", 1))
    if passed != total:
        raise SystemExit(f"selftest not clean: {path}: {passed}/{total}")
    return passed, total


def write_completion_report(args: argparse.Namespace) -> None:
    channels = {
        "live source": (Path(args.live_junit), Path(args.live_selftest)),
        "source ZIP": (Path(args.zip_junit), Path(args.zip_selftest)),
        "installed wheel": (Path(args.wheel_junit), Path(args.wheel_selftest)),
    }
    evidence: dict[str, dict] = {}
    for name, (junit, selftest) in channels.items():
        evidence[name] = {
            "junit": junit_summary(junit),
            "selftest": selftest_summary(selftest),
        }
    candidate = json.loads(CANDIDATE_MANIFEST.read_text(encoding="utf-8"))
    sums = ARTIFACT_SUMS.read_text(encoding="utf-8").rstrip()
    lines = [
        "# Task 17 Completion — RC6 Package Integration",
        "",
        "**Status:** PACKAGE INTEGRATION PASS — OWNER REVIEW REQUIRED",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Workflow run:** `{args.run_id}`",
        f"**Build input commit:** `{candidate['build_input_commit']}`",
        f"**Source tree SHA:** `{candidate['source_tree_sha']}`",
        "**Release eligible:** `false` — Task 18 trusted native evidence remains mandatory.",
        "",
        "## Parity evidence",
        "",
        "| Channel | Tests | Failures | Errors | Skips | Selftest |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, item in evidence.items():
        j = item["junit"]
        passed, total = item["selftest"]
        lines.append(
            f"| {name} | {j['tests']} | {j['failures']} | {j['errors']} | {j['skipped']} | {passed}/{total} PASS |"
        )
    lines.extend(
        [
            "",
            "## Candidate contract",
            "",
            "- `tool/source/` is the canonical RC6 source snapshot.",
            "- Source ZIP file set and every file digest match the tracked source snapshot.",
            "- Wheel regression executes the same shipped test suite outside the source checkout.",
            "- Runtime candidate bundle contains the source ZIP, source manifest, wheel and candidate manifest with verified payload hashes.",
            "- RC4 artifacts are not overwritten or repacked.",
            "- Candidate manifest is fail-closed with `release_eligible=false` until Task 18 native compile/test/restart evidence is bound.",
            "",
            "## Artifact SHA-256",
            "",
            "```text",
            sums,
            "```",
            "",
            "## Gate decision",
            "",
            "Task 17 deterministic package integration is complete at source/ZIP/wheel/runtime-bundle level. Task 18 remains fail-closed until trusted native evidence is supplied.",
            "",
        ]
    )
    COMPLETION_REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def cmd_build(args: argparse.Namespace) -> None:
    build_input_sha = args.build_input_sha or git("rev-parse", "HEAD")
    if git("status", "--porcelain", "--", "tool/source"):
        raise SystemExit(
            "tool/source contains uncommitted changes; refusing candidate build"
        )
    subprocess.check_call(
        [
            sys.executable,
            str(ROOT / "scripts/maintenance/sync_distribution_snapshot.py"),
            "verify",
        ],
        cwd=ROOT,
    )
    source_manifest = build_source_archive(build_input_sha)
    build_wheel()
    build_candidate_manifest(build_input_sha, source_manifest)
    build_runtime_bundle()
    write_artifact_sums()
    print(f"RC6 candidate built from source tree {source_manifest['source_tree_sha']}")


def cmd_verify(_: argparse.Namespace) -> None:
    required = [
        SOURCE_ZIP,
        SOURCE_MANIFEST,
        WHEEL,
        CANDIDATE_MANIFEST,
        ARTIFACT_SUMS,
        RUNTIME_BUNDLE,
    ]
    missing = [
        path.relative_to(ROOT).as_posix() for path in required if not path.is_file()
    ]
    if missing:
        raise SystemExit(f"candidate artifacts missing: {missing}")
    verify_source_manifest()
    verify_wheel(WHEEL)
    verify_candidate_manifest()
    verify_runtime_bundle()
    verify_artifact_sums()
    print("RC6 candidate package verification: PASS")


def cmd_repro_check(_: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(prefix="rc6-wheel-repro-") as temp:
        first = Path(temp) / "first.whl"
        second = Path(temp) / "second.whl"
        build_wheel(first)
        build_wheel(second)
        first_hash = sha256(first)
        second_hash = sha256(second)
        if first_hash != second_hash or first.read_bytes() != second.read_bytes():
            raise SystemExit(
                f"RC6 wheel reproducibility failed: first={first_hash} second={second_hash}"
            )
        print(f"RC6 wheel reproducibility: PASS ({first_hash})")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--build-input-sha", default="")
    build.set_defaults(func=cmd_build)
    verify = sub.add_parser("verify")
    verify.set_defaults(func=cmd_verify)
    repro = sub.add_parser("repro-check")
    repro.set_defaults(func=cmd_repro_check)
    report = sub.add_parser("report")
    report.add_argument("--run-id", required=True)
    report.add_argument("--live-junit", required=True)
    report.add_argument("--zip-junit", required=True)
    report.add_argument("--wheel-junit", required=True)
    report.add_argument("--live-selftest", required=True)
    report.add_argument("--zip-selftest", required=True)
    report.add_argument("--wheel-selftest", required=True)
    report.set_defaults(func=write_completion_report)
    return ap


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
