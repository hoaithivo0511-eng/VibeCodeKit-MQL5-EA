"""Evidence manifest v2 for release-grade EA builds."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json

from .execution_sources import assess_backtest_source, assess_compile_source, is_fixture_path
from .github_compile_evidence import validate_github_compile_record
from .release_policy import compute_release_eligible


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_record(path: str | Path, role: str) -> dict[str, Any]:
    p = Path(path)
    rec = {"role": role, "path": str(p), "exists": p.exists(), "fixture": is_fixture_path(p)}
    if p.exists() and p.is_file():
        rec["sha256"] = sha256_file(p)
        rec["size_bytes"] = p.stat().st_size
    return rec


@dataclass
class EvidenceManifestV2:
    schema_version: str = "2.0"
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool_policy: str = "No PASS/READY/RELEASE claim is valid without release_eligible=true and artifact hashes."
    compile: dict[str, Any] = field(default_factory=dict)
    backtest: dict[str, Any] = field(default_factory=dict)
    gates: dict[str, Any] = field(default_factory=dict)
    matrix: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    unsafe_flags_used: list[str] = field(default_factory=list)
    skipped_stages: list[str] = field(default_factory=list)
    methodology: dict[str, Any] = field(default_factory=lambda: {
        "trader_17": {"type": "internal_heuristic", "industry_standard": False, "requires_human_review": True},
        "ap_ids": {"type": "internal_heuristic", "industry_standard": False, "requires_human_review": True},
        "triangle_of_power": {"type": "internal_heuristic", "industry_standard": False, "requires_human_review": True},
    })

    def evaluate(self) -> dict[str, Any]:
        github_validation = None
        provenance_verified = False
        if self.compile.get("source") == "github_actions_metaeditor":
            github_validation = validate_github_compile_record(self.compile)
            provenance_verified = github_validation.ok
        compile_assessment = assess_compile_source(
            self.compile.get("source"), provenance_verified=provenance_verified
        )
        backtest_assessment = assess_backtest_source(
            self.backtest.get("source"), self.backtest.get("report_path")
        )

        compile_ok = bool(self.compile.get("ok")) and compile_assessment.trusted_for_release
        backtest_ok = bool(self.backtest.get("ok")) and backtest_assessment.trusted_for_release
        gate_ok = bool(self.gates.get("ok"))
        required_artifacts = [a for a in self.artifacts if a.get("required", True)]
        evidence_ok = bool(required_artifacts) and all(
            a.get("exists") and a.get("sha256") for a in required_artifacts
        )
        if not self.matrix:
            matrix_ok = True
        elif "ok" in self.matrix:
            matrix_ok = bool(self.matrix.get("ok", False))
        else:
            matrix_ok = bool(self.matrix.get("summary", {}).get("ok", False))

        release_eligible = compute_release_eligible(
            compile_ok=compile_ok,
            backtest_ok=backtest_ok,
            gate_ok=gate_ok,
            evidence_ok=evidence_ok,
            matrix_ok=matrix_ok,
            unsafe_flags=self.unsafe_flags_used,
            skipped_stages=self.skipped_stages,
        )

        summary = {
            "compile_ok": compile_ok,
            "backtest_ok": backtest_ok,
            "gate_ok": gate_ok,
            "evidence_ok": evidence_ok,
            "matrix_ok": matrix_ok,
            "release_eligible": release_eligible,
            "compile_assessment": compile_assessment.to_dict(),
            "backtest_assessment": backtest_assessment.to_dict(),
            "unsafe_flags_used": self.unsafe_flags_used,
            "skipped_stages": self.skipped_stages,
        }
        if github_validation is not None:
            summary["github_compile_validation"] = github_validation.to_dict()
        return summary

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["summary"] = self.evaluate()
        return data

    def write(self, path: str | Path) -> dict[str, Any]:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data


def write_manifest_v2(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    manifest = EvidenceManifestV2(**kwargs)
    return manifest.write(path)
