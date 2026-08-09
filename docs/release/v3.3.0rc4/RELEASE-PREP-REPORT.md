# VibeCodeKit MQL5 v3.3.0rc4 — Release Preparation Report

Branch: `release-prep/v3.3.0rc4`  
Base `main`: `df2fbf65384465316898f2426f547e6d90579d3c`  
Deterministic evidence commit: `cc0458289f2e2cb2a4c4ea52c42bb30844a875f5`  
Report status: **READY_AFTER_MANIFEST_REFRESH**

## Executive verdict

Repository cleanup and deterministic release-candidate validation are complete for the source/package surfaces. The canonical RC4 bundle, source ZIP and wheel remain frozen and hash-stable. Source checkout, fresh source archive and isolated installed-wheel regression each execute the full 126-test suite with zero failures and zero skips; all three selftest surfaces pass 13/13 invariants.

This report does **not** declare production readiness. The preserved project release gate remains `release_eligible=false` because trusted MetaEditor compile and MT5 Strategy Tester evidence are not available in the current environment. The appropriate next release state, once the repository SHA-256 manifest refresh/check passes, is **GitHub Pre-release / tag candidate only**.

## Cleanup delta

Repository-only cleanup was deliberately separated from canonical package contents:

- added root `.gitignore` and MIT `LICENSE`;
- removed the connector smoke artifact from the root;
- retired stale `PUSH-GUIDE.md` and `SETUP-CODESPACE.sh` root bootstrap material;
- archived maintenance/import guidance under `docs/maintenance/`;
- added a safe maintenance importer under `scripts/maintenance/` that never commits, pushes or force-pushes;
- rewrote root `README.md` and `STRUCTURE.md` around release semantics and integrity boundaries rather than stale file counts;
- added deterministic release and package CI workflows;
- retained `tool/source/DRAFT-NOT-VALIDATED.txt` intentionally because it is a draft-output safety notice and a canonical source-archive member;
- did not mutate `tool/source/`, the canonical source ZIP, the wheel, or the RC4 bundle during repository cleanup.

## Deterministic validation matrix

| Gate | Surface | Result | Evidence |
|---|---|---:|---|
| Source regression | expanded `tool/source/` | **126/126 PASS, 0 skip** | Release Gate run `31304351274`, job `source-regression` |
| Source selftest | expanded `tool/source/` | **13/13 PASS** | Release Gate run `31304351274` |
| Repository hygiene | Git-tracked repository | **PASS** | Release Gate run `31304351274`, job `repository-hygiene` |
| Artifact identity/parity | bundle + source ZIP + wheel + expanded source | **PASS** | Release Gate run `31304351274`, job `artifact-parity` |
| Fresh source-ZIP regression | `/tmp` extraction of canonical source ZIP | **126/126 PASS, 0 skip** | Package Regression run `31304351258`, job `source-archive-regression` |
| Fresh source-ZIP selftest | `/tmp` extraction | **13/13 PASS** | Package Regression run `31304351258` |
| Wheel runtime isolation | installed package | **PASS — imported from `site-packages`** | Package Regression run `31304351258`, job `wheel-regression` |
| Installed-wheel regression | tests outside source checkout | **126/126 PASS, 0 skip** | Package Regression run `31304351258` |
| Installed-wheel selftest | installed wheel | **13/13 PASS** | Package Regression run `31304351258` |
| Generic cross-project acceptance | clean installed wheel | **4/4 PASS** | preserved `reports/GENERIC-ACCEPTANCE.json` |
| Repository manifest | all Git-tracked regular files except manifest itself | **PENDING REFRESH** | `repo_manifest.py` + manifest CI introduced by this report batch |

The wheel regression explicitly checks that `vibecodekit_mql5.__file__` resolves under Python `site-packages`; the source package is not copied into the isolated test harness. Test-only support under `tests/` is supplied through `PYTHONPATH` because the source suite itself declares `pythonpath = ["scripts", "tests"]` in pytest configuration.

## Frozen RC4 artifact identities

```text
33af7e8326f6e373de6366600b35e7a5b465b5aee34f24af07f2ac6e36deec6c  VibecodeKit-MQL5-v3.3.0rc4-runtime-safety-fix-bundle.zip
a8e091caf35b59fbf436d10c5c8e1dc0414d3e355d029162295192c02029566f  tool/vibecodekit-mql5-v3.3.0rc4-source-full.zip
5945a91c9f2b74ee3bbe3a7977991445d3e95885e396c3f95a14262ac8eb127a  tool/vibecodekit_mql5_ea-3.3.0rc4-py3-none-any.whl
```

The source archive contains 605 regular files and the release-gate parity check compares every archive member byte-for-byte with `tool/source/`.

## Coverage evidence and residual test debt

The preserved RC4 audit coverage run records 19,310 statements, 15,790 missed and therefore 3,520 covered statements: **18.23% statement coverage**. This is historical RC4 audit evidence from `reports/source-coverage.txt`; it was not recomputed as part of the repository-only cleanup CI and must not be represented as fresh coverage.

Selected high-value module figures from that preserved run are approximately:

- `advanced_codegen.py`: 95%
- `build_planner.py`: 92%
- `ea_ir.py`: 94%
- `feature_registry.py`: 95%
- `safe_paths.py`: 95%

Overall package coverage remains the largest deterministic maintainability debt because the 139-command orchestration/legacy surface is substantially broader than the focused regression paths. This is a post-RC4 hardening target, not a reason to reinterpret passing functional/package tests as comprehensive proof.

## Genericity / fixture isolation

The preserved generic acceptance evidence reports 4/4 passing cases — NorthTrend, RangePulse, BandReturn and OrionRecovery — on a clean installed wheel, with no CCBSN-specific production literals detected. CCBSN therefore remains a golden/complex acceptance fixture rather than the production template of the generator.

## Native-validation blockers

The preserved `check-all` report is intentionally release-blocked:

- MetaEditor compile: `UNTESTABLE` in the current environment;
- MT5 backtest: `UNTESTABLE`;
- tester-derived quality/forward/stress evidence: not trusted or unavailable;
- evidence stage: `FAIL` for production release because compile/backtest evidence is not trusted;
- `release_eligible=false`.

No trusted `.ex5`, native compile log, or MT5 Strategy Tester result is claimed by this repository cleanup cycle. No profitability claim is made.

## Release decision

```text
GO_FOR_TAG_PRE_RELEASE = AFTER_REPO_MANIFEST_PASS
GO_FOR_PRODUCTION      = false
```

Once the repository manifest is regenerated from the finalized tracked tree and its read-only CI check passes together with the release/package workflows, the branch is suitable for owner review as a **pre-release tag candidate**. Merge to `main`, creation of `v3.3.0rc4`, and GitHub Pre-release publication are explicitly outside this report batch and require owner approval.
