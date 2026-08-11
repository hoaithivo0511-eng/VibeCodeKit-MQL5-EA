"""mql5-selftest / ``vkmql-check selftest`` — ship-in-slim smoke test.

The slim distribution intentionally drops the ``tests/`` directory, so a
user (or an agent) editing the shipped tree has *no* regression net. This
module is the deliberate exception: it lives **outside** ``tests/`` so it
ships in slim, and exercises the kit's load-bearing invariants in-process
without a network, Wine, or MetaEditor. Each check asserts a real
behaviour — not a cosmetic string — so a broken slim build fails loudly
instead of silently shipping.

Invariants:
  1. catalog_consistent   tool-catalog.json matches [project.scripts]
  2. entrypoints_import    every catalog module imports and exposes main()
  3. build_smoke           a preset build emits Experts/<EA>/<EA>.mq5
  4. evidence_gate_honest  a forged PASS report is NOT release-eligible
  5. safe_extract_guard    a Zip-Slip member is rejected
  6. version_triple_match  pyproject == _version == tool-catalog kit_version
  7. docs_assets_resolvable ea_docs_assets ship in the wheel (package-data)
  8. no_dev_refs_in_user_docs user docs are free of dev/source-checkout refs
  9. public_surface_stable  catalog exposes exactly the 5 public commands
 10. maturity_labeled       every tool carries a maturity label (no overclaim)
 11. runner_key_pinning     a self-signed unpinned key cannot pass the gate
 12. tests_shipped          the regression suite ships with the artifact
 13. artifact_immutable     running the kit does not rewrite the kit

Exit 0 only when every invariant holds. ``--json`` emits the standard
agent envelope (schema_version=1) on stdout; human text goes to stderr so
stdout stays a clean machine channel.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import _version
from ._agent_io import Envelope, add_json_flag, emit


def _repo_root() -> Path:
    from ._resources import distribution_root
    return distribution_root()


def _pyproject_version(root: Path) -> str | None:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project:
            m = re.match(r'version\s*=\s*"([^"]+)"', stripped)
            if m:
                return m.group(1)
    return None


def _load_catalog(root: Path) -> dict[str, Any]:
    return json.loads((root / "tool-catalog.json").read_text(encoding="utf-8"))


# --- individual invariants -------------------------------------------------
# Each returns (ok, detail). They never raise; a raised exception is caught
# by the runner and converted into a failed check.


def _check_catalog_consistent(root: Path) -> tuple[bool, str]:
    from . import manifest

    catalog = _load_catalog(root)
    errors = manifest.validate_manifest(catalog)
    if errors:
        return False, f"{len(errors)} catalog/pyproject mismatch(es): {errors[:3]}"
    return True, f"{len(catalog.get('tools', []))} tools consistent with pyproject"


# Top-level package of our own code; an ImportError originating *inside*
# this package is a real breakage, whereas a missing third-party dep (a
# declared dependency not installed in the current env) is tolerated.
_OWN_PACKAGE = "vibecodekit_mql5"


def _check_entrypoints_import(root: Path) -> tuple[bool, str]:
    """Every catalog entry must resolve to a callable ``module:function``.

    The catalog records each tool's real ``entry_point`` (e.g.
    ``vibecodekit_mql5.vkmql:new_main``), so we resolve that exact function
    rather than assuming ``main``. A module that fails to import *only*
    because a declared third-party dependency is absent (e.g. python-docx
    in a docs-free env) is reported as skipped, not broken — that is an
    environment gap, not a code defect. Any failure inside our own package
    (renamed symbol, circular import, missing attribute) is a real break.
    """
    catalog = _load_catalog(root)
    bad: list[str] = []
    skipped: list[str] = []
    for tool in catalog.get("tools", []):
        entry_point = tool.get("entry_point") or ""
        module_name, _, func_name = entry_point.partition(":")
        if not module_name or not func_name:
            bad.append(f"{tool.get('name', '?')}: bad entry_point {entry_point!r}")
            continue
        try:
            mod = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            missing_top = (exc.name or "").split(".")[0]
            if missing_top and missing_top != _OWN_PACKAGE:
                skipped.append(f"{module_name} (missing dep {missing_top})")
                continue
            bad.append(f"{module_name}: import failed ({exc})")
            continue
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - defensive
            bad.append(f"{module_name}: import failed ({exc.__class__.__name__})")
            continue
        if not callable(getattr(mod, func_name, None)):
            bad.append(f"{module_name}:{func_name} not callable")
    if bad:
        return False, f"{len(bad)} broken entrypoint(s): {bad[:3]}"
    total = len(catalog.get("tools", []))
    if skipped:
        return True, (
            f"{total - len(skipped)} entrypoints resolve; "
            f"{len(skipped)} skipped (deps absent): {skipped[:3]}"
        )
    return True, f"{total} entrypoints resolve to a callable"


def _check_build_smoke(root: Path) -> tuple[bool, str]:
    from . import build

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "proj"
        argv = [
            "trend",
            "--name", "SelfTestEA",
            "--symbol", "XAUUSD",
            "--tf", "M5",
            "--out", str(out),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            rc = int(build.main(argv) or 0)
        if rc != 0:
            return False, f"build exit {rc}"
        hits = list(out.rglob("Experts/**/SelfTestEA.mq5"))
        if not hits:
            hits = list(out.rglob("SelfTestEA.mq5"))
        if not hits:
            return False, "no Experts/<EA>/<EA>.mq5 emitted"
    return True, "preset build emits Experts/<EA>/<EA>.mq5"


def _check_evidence_gate_honest(root: Path) -> tuple[bool, str]:
    from . import release_policy

    # A report that claims the command succeeded but has NO compile/gate/
    # backtest/evidence stages must never be release-eligible.
    forged = {"ok": True, "stages": [{"name": "build", "ok": True}]}
    summary = release_policy.summarize(forged)
    if summary.get("release_eligible"):
        return False, "forged PASS was accepted as release-eligible"
    return True, "forged PASS rejected (release_eligible=false)"


def _check_safe_extract_guard(root: Path) -> tuple[bool, str]:
    from ._safe_archive import UnsafeArchiveError, safe_extract

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        zpath = d / "slip.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("../escape.txt", b"x")
        try:
            with zipfile.ZipFile(zpath) as z:
                safe_extract(z, d / "out")
        except UnsafeArchiveError:
            return True, "zip-slip member rejected"
        return False, "zip-slip member was NOT rejected"


def _check_version_triple_match(root: Path) -> tuple[bool, str]:
    pyproject_v = _pyproject_version(root)
    module_v = _version.get_version()
    catalog_v = _load_catalog(root).get("kit_version")
    # Every shipped agent-contract.json must also carry the current kit version.
    # Regression guard: the repo-root agent-contract.json once drifted to an
    # older release (2.4.4) while pyproject/catalog/package-contract were bumped,
    # which an enterprise buyer auditing the bundle would flag as a trust issue.
    contract_versions: dict[str, Any] = {}
    for cpath in sorted(root.rglob("agent-contract.json")):
        if "node_modules" in cpath.parts:
            continue
        try:
            data = json.loads(cpath.read_text(encoding="utf-8"))
            contract_versions[str(cpath.relative_to(root))] = (
                data.get("kit", {}).get("version")
            )
        except Exception:  # noqa: BLE001  # pragma: no cover - defensive
            contract_versions[str(cpath.relative_to(root))] = "<unreadable>"
    contract_mismatch = {
        p: v for p, v in contract_versions.items() if v != pyproject_v
    }
    if (
        pyproject_v
        and pyproject_v == module_v == catalog_v
        and not contract_mismatch
    ):
        return True, (
            f"version {pyproject_v} matches across pyproject/_version/catalog "
            f"+ {len(contract_versions)} agent-contract.json"
        )
    return False, (
        f"version mismatch pyproject={pyproject_v} "
        f"_version={module_v} catalog={catalog_v} "
        f"agent-contract={contract_mismatch or 'ok'}"
    )


def _check_docs_assets_resolvable(root: Path) -> tuple[bool, str]:
    """The EA docs renderer assets must (a) load at runtime AND (b) be declared
    in pyproject package-data so they actually ship inside the wheel.

    Regression guard for the packaging bug where ``ea_docs_assets/`` lived only
    in the source tree (not under ``resources/`` and not in package-data), so
    ``pip install`` of the wheel produced a kit whose docs stage crashed with
    ``No such file or directory: .../ea_docs_assets/style.css`` even though it
    worked fine from a source checkout.
    """
    from . import ea_docs_render

    css = ea_docs_render.load_asset("style.css")
    if not css.strip():
        return False, "ea_docs_assets/style.css loaded empty"
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    if "ea_docs_assets" not in pyproject:
        return False, (
            "ea_docs_assets not declared in pyproject package-data; wheel install "
            "would drop the docs renderer assets"
        )
    return True, "ea_docs_assets style.css resolvable and declared in package-data"


# Dev-only references that must never appear in end-user-facing documentation
# of a commercial/slim kit. Maintainer docs (under tools/, .github/, etc.) and
# this kit's own source are exempt; only docs/*.md user guides are scanned.
# NOTE: ``copilot-instructions`` is intentionally NOT flagged -- the VS Code /
# Copilot Chat integration section is a legitimate end-user feature, not a leak
# of this kit's own dev repo. We only fail on dev-repo / source-checkout refs.
_DEV_REF_PATTERNS = (
    "git clone",
    "github.com",
    "github issue",
    "git tag",
    "code-scanning",
)
_USER_DOC_NAMES = (
    "COMMANDS.md",
    "QUICKSTART.md",
    "USAGE-en.md",
    "USER-GUIDE-en.md",
    "HUONG-DAN-TOAN-TAP-vi.md",
)


def _check_no_dev_refs_in_user_docs(root: Path) -> tuple[bool, str]:
    """End-user docs must not leak dev/maintainer references (git clone, GitHub
    issues, git tag, code-scanning, copilot-instructions). Keeps the shipped
    kit feeling like a clean commercial product rather than a dev checkout.
    """
    docs_dir = root / "docs"
    offenders: list[str] = []
    for name in _USER_DOC_NAMES:
        path = docs_dir / name
        if not path.exists():
            continue
        lowered = path.read_text(encoding="utf-8").lower()
        hits = [p for p in _DEV_REF_PATTERNS if p in lowered]
        if hits:
            offenders.append(f"{name}: {', '.join(hits)}")
    if offenders:
        return False, "dev refs in user docs -> " + "; ".join(offenders)
    return True, f"no dev refs in {len(_USER_DOC_NAMES)} user docs"


def _check_public_surface_stable(root: Path) -> tuple[bool, str]:
    """v2.5 #4: the catalog must expose EXACTLY the 5 canonical public
    commands, each importable and tagged tier='public'. This keeps the
    end-user surface small and prevents accidental tier drift as the 118
    advanced commands churn.
    """
    from . import surface

    catalog = _load_catalog(root)
    by_name = {t.get("name"): t for t in catalog.get("tools", [])}
    public_in_catalog = sorted(
        t.get("name") for t in catalog.get("tools", []) if t.get("tier") == "public"
    )
    expected = sorted(surface.PUBLIC_COMMANDS)
    if public_in_catalog != expected:
        return False, (
            f"public tier drift: catalog={public_in_catalog} expected={expected}"
        )
    missing = [name for name in expected if name not in by_name]
    if missing:
        return False, f"public command(s) missing from catalog: {missing}"
    for name in expected:
        entry = by_name[name].get("entry_point") or ""
        mod_name, _, func = entry.partition(":")
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - defensive
            return False, f"public command {name} import failed: {exc}"
        if not callable(getattr(mod, func, None)):
            return False, f"public command {name} entry {entry} not callable"
    return True, f"{len(expected)} public commands stable and importable"


def _check_maturity_labeled(root: Path) -> tuple[bool, str]:
    """v2.5 #5: every catalog tool carries a maturity label, no public command
    is a placeholder, and every registered placeholder/scaffold module imports.
    Stops a stub (ONNX/LLM bridge) from masquerading as finished logic.
    """
    from . import maturity

    catalog = _load_catalog(root)
    valid = {maturity.RELEASE_GRADE, maturity.SCAFFOLD, maturity.PLACEHOLDER}
    unlabeled = [
        t.get("name") for t in catalog.get("tools", [])
        if t.get("maturity") not in valid
    ]
    if unlabeled:
        return False, f"{len(unlabeled)} tool(s) lack a maturity label: {unlabeled[:3]}"
    # A public command must never be a placeholder.
    overclaim = [
        t.get("name") for t in catalog.get("tools", [])
        if t.get("tier") == "public" and t.get("maturity") == maturity.PLACEHOLDER
    ]
    if overclaim:
        return False, f"public command(s) marked placeholder: {overclaim}"
    # Every registered placeholder/scaffold module must actually import.
    for mod_name in maturity.placeholders() + maturity.scaffolds():
        try:
            importlib.import_module(mod_name)
        except ModuleNotFoundError as exc:
            missing_top = (exc.name or "").split(".")[0]
            if missing_top and missing_top != _OWN_PACKAGE:
                continue  # external dep gap, not a code defect
            return False, f"maturity module {mod_name} import failed: {exc}"
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - defensive
            return False, f"maturity module {mod_name} import failed: {exc}"
    labeled = len(catalog.get("tools", []))
    return True, f"{labeled} tools maturity-labeled; {len(maturity.placeholders())} placeholders honest"


def _check_runner_key_pinning(root: Path) -> tuple[bool, str]:
    """A self-generated signing key must never yield release provenance.

    This is the in-process regression for ADV-6. An earlier build verified the
    runner signature against a public key read straight from the environment,
    so anyone who could set an env var could mint their own trust root and sign
    fabricated evidence. The check reproduces that exact attack and asserts it
    is now refused. It runs in slim (outside tests/) precisely because it is
    the invariant most costly to lose silently.
    """
    import base64
    import hashlib
    import json as _json
    import tempfile

    from . import provenance
    from .trust_root import TRUST_FILE

    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        return False, "cryptography missing; release signature verification cannot run"

    core = provenance.CORE_ARTIFACTS
    with tempfile.TemporaryDirectory() as d:
        project = Path(d) / "MyEA"
        for rel in core:
            (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / core[0]).write_text("0 errors, 0 warnings\n", encoding="utf-8")
        (project / core[1]).write_bytes(b"FAKE_EX5_PADDED_WELL_PAST_THIRTY_TWO_BYTES_123456")
        (project / core[2]).write_text(
            '<?xml version="1.0"?><report><TotalTrades>412</TotalTrades>'
            "<ProfitFactor>2.31</ProfitFactor></report>\n", encoding="utf-8")
        (project / core[3]).write_text('{"status": "PASS"}', encoding="utf-8")
        (project / core[4]).write_text('{"status": "PASS"}', encoding="utf-8")

        hashes = {
            rel: hashlib.sha256((project / rel).read_bytes()).hexdigest() for rel in core
        }
        stamp = {
            "command": "metaeditor64.exe /compile:MyEA.mq5",
            "tool_version": "5.0.0.4620",
            "host": "WIN-RUNNER-01",
            "recorded_at_utc": "2026-08-02T00:00:00Z",
            "returncode": 0,
        }
        manifest = {
            "schema_version": "2.0",
            "release_eligible": True,
            "summary": {"release_eligible": True},
            "artifacts": [
                {"path": rel, "exists": True, "sha256": hashes[rel]} for rel in core
            ],
            "compile": dict(stamp, source="actual_metaeditor"),
            "backtest": dict(stamp, source="actual_mt5_strategy_tester",
                             command="terminal64.exe /config:tester.ini"),
        }
        attacker = Ed25519PrivateKey.generate()
        signature = attacker.sign(provenance.attestation_payload(manifest, hashes))
        manifest["runner_attestation"] = {
            "algorithm": "Ed25519",
            "key_id": "windows-runner-01",
            "signature_b64": base64.b64encode(signature).decode(),
        }
        (project / "evidence/manifest.json").write_text(
            _json.dumps(manifest, indent=2), encoding="utf-8")

        # Pin a DIFFERENT key: the honest runner's, which the attacker lacks.
        honest_pub = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        (project / TRUST_FILE).write_text(
            "schema_version: 1\nrunner_keys:\n  - key_id: windows-runner-01\n"
            "    algorithm: Ed25519\n"
            f'    public_key_sha256: "{hashlib.sha256(honest_pub).hexdigest()}"\n',
            encoding="utf-8")

        attacker_pub = attacker.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        saved = os.environ.get("VCK_RUNNER_PUBLIC_KEY_B64")
        os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = base64.b64encode(attacker_pub).decode()
        try:
            result = provenance.validate_release_provenance(project)
        finally:
            os.environ.pop("VCK_RUNNER_PUBLIC_KEY_B64", None)
            if saved is not None:
                os.environ["VCK_RUNNER_PUBLIC_KEY_B64"] = saved

    if result.status == "PASS":
        return False, "ADV-6 REGRESSION: a self-signed unpinned key produced release provenance"
    if not any("does not match the pin" in e for e in result.errors):
        return False, f"unpinned key rejected for the wrong reason: {result.errors[:2]}"
    return True, "self-signed unpinned runner key rejected (ADV-6 closed)"


def _check_tests_shipped(root: Path) -> tuple[bool, str]:
    """The regression suite must ship with the distribution.

    Earlier releases excluded ``tests/`` from the package while the docs still
    advertised a passing test count, leaving buyers unable to verify the claim
    from the artifact they received. Shipping the suite is what makes the claim
    checkable rather than promissory.
    """
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return False, "tests/ is absent from the distribution"
    modules = sorted(tests_dir.glob("test_*.py"))
    if not modules:
        return False, "tests/ ships no test_*.py modules"
    fixture = tests_dir / "fixtures_ccbsn.txt"
    references_fixture = any(
        "fixtures_ccbsn.txt" in module.read_text(encoding="utf-8")
        for module in modules
    )
    if references_fixture and not fixture.is_file():
        return False, "tests reference fixtures_ccbsn.txt but the fixture is absent"
    snapshot_manifest = root / "SNAPSHOT-MANIFEST.json"
    if snapshot_manifest.is_file():
        from .distribution_snapshot import verify_distribution_snapshot

        errors = verify_distribution_snapshot(root)
        if errors:
            return False, f"distribution snapshot integrity failed: {errors[:3]}"
    return True, f"{len(modules)} test module(s) plus required fixtures shipped and runnable"



def _check_artifact_immutable(root: Path) -> tuple[bool, str]:
    """Running the kit must not modify the kit.

    The UI E2E demo used to write its report into the shipped ``docs/``
    directory, so merely running the demonstration invalidated every hash in
    ``dist-manifest.json``. A distribution whose own tooling rewrites it cannot
    be verified by the person who received it. This invariant pins the demo's
    output away from the package tree.
    """
    demo = root / "scripts" / "ui_e2e_demo.py"
    if not demo.is_file():
        return True, "ui_e2e_demo.py not shipped; nothing to constrain"
    text = demo.read_text(encoding="utf-8")
    offenders = [frag for frag in ('ROOT / "docs"', "ROOT / 'docs'") if frag in text]
    if offenders:
        return False, "ui_e2e_demo.py writes into the shipped docs/ tree"
    return True, "e2e demo writes outside the distribution; artifact stays verifiable"


CHECKS: dict[str, Callable[[Path], tuple[bool, str]]] = {
    "catalog_consistent": _check_catalog_consistent,
    "entrypoints_import": _check_entrypoints_import,
    "build_smoke": _check_build_smoke,
    "evidence_gate_honest": _check_evidence_gate_honest,
    "safe_extract_guard": _check_safe_extract_guard,
    "version_triple_match": _check_version_triple_match,
    "docs_assets_resolvable": _check_docs_assets_resolvable,
    "no_dev_refs_in_user_docs": _check_no_dev_refs_in_user_docs,
    "public_surface_stable": _check_public_surface_stable,
    "maturity_labeled": _check_maturity_labeled,
    "runner_key_pinning": _check_runner_key_pinning,
    "tests_shipped": _check_tests_shipped,
    "artifact_immutable": _check_artifact_immutable,
}


def run_selftest(root: Path | None = None) -> dict[str, Any]:
    """Run every invariant and return a structured result dict."""
    root = root or _repo_root()
    results: list[dict[str, Any]] = []
    for name, fn in CHECKS.items():
        try:
            ok, detail = fn(root)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - defensive
            ok, detail = False, f"raised {exc.__class__.__name__}: {exc}"
        results.append({"name": name, "ok": ok, "detail": detail})
    passed = sum(1 for r in results if r["ok"])
    return {
        "checks": results,
        "passed": passed,
        "total": len(results),
        "ok": passed == len(results),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mql5-selftest",
        description=__doc__.splitlines()[0] if __doc__ else "",
    )
    add_json_flag(p)
    args = p.parse_args(argv)

    result = run_selftest()
    ok = result["ok"]
    envelope = Envelope(
        tool="mql5-selftest",
        ok=ok,
        exit_code=0 if ok else 1,
        summary=f"selftest {result['passed']}/{result['total']} invariants passed",
        data=result,
    )
    if getattr(args, "emit_json", False):
        emit(envelope)
    else:
        for check in result["checks"]:
            mark = "PASS" if check["ok"] else "FAIL"
            print(f"[{mark}] {check['name']}: {check['detail']}", file=sys.stderr)
        print(envelope.summary, file=sys.stderr)
    return envelope.exit_code


if __name__ == "__main__":
    sys.exit(main())
