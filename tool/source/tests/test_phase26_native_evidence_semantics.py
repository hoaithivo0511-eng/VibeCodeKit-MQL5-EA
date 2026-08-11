"""Semantic regressions for Task-10 native evidence artifacts."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _util import build_forged_project, refresh_artifact_hash  # type: ignore


class TestNativeEvidenceSemantics(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def validate(self, project: Path):
        from vibecodekit_mql5.provenance import validate_release_provenance
        return validate_release_provenance(project)

    def test_empty_deep_review_is_rejected_even_with_matching_hash(self) -> None:
        project = build_forged_project(self.root)
        rel = "evidence/review/deep-review.json"
        (project / rel).write_text("{}\n", encoding="utf-8")
        refresh_artifact_hash(project, rel)
        result = self.validate(project)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("review report status is not PASS" in e for e in result.errors))

    def test_unresolved_p1_review_finding_blocks_release(self) -> None:
        project = build_forged_project(self.root)
        rel = "evidence/review/deep-review.json"
        review = json.loads((project / rel).read_text(encoding="utf-8"))
        review["findings"] = [{"id": "P1-1", "severity": "P1", "status": "OPEN", "summary": "risk"}]
        (project / rel).write_text(json.dumps(review), encoding="utf-8")
        refresh_artifact_hash(project, rel)
        result = self.validate(project)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("unresolved P1" in e for e in result.errors))

    def test_missing_restart_case_blocks_release(self) -> None:
        project = build_forged_project(self.root)
        rel = "evidence/stress/stress-matrix-report.json"
        stress = json.loads((project / rel).read_text(encoding="utf-8"))
        stress["restart_recovery_cases"] = [
            item for item in stress["restart_recovery_cases"] if item["id"] != "no_duplicate_order"
        ]
        (project / rel).write_text(json.dumps(stress), encoding="utf-8")
        refresh_artifact_hash(project, rel)
        result = self.validate(project)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("missing required restart recovery case no_duplicate_order" in e for e in result.errors))

    def test_restart_case_requires_evidence_reference(self) -> None:
        project = build_forged_project(self.root)
        rel = "evidence/stress/stress-matrix-report.json"
        stress = json.loads((project / rel).read_text(encoding="utf-8"))
        stress["restart_recovery_cases"][0]["evidence"] = ""
        (project / rel).write_text(json.dumps(stress), encoding="utf-8")
        refresh_artifact_hash(project, rel)
        result = self.validate(project)
        self.assertEqual(result.status, "FAIL")
        self.assertTrue(any("has no evidence reference" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main()
