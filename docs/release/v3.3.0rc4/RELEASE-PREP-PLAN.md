# VibeCodeKit MQL5 v3.3.0rc4 — release preparation plan

Target branch: `release-prep/v3.3.0rc4`
Base commit: `df2fbf65384465316898f2426f547e6d90579d3c`
Target tag after approval: `v3.3.0rc4`

No tag or GitHub Release is created by this plan. Native MetaEditor compile and MT5 Strategy Tester evidence remain separate release blockers until proven.

## Phase 0 — freeze and branch

- Freeze `main` as the comparison baseline.
- Perform all cleanup on `release-prep/v3.3.0rc4`.
- Preserve canonical RC4 package/source archive bytes unless the package is intentionally rebuilt and fully retested.

Gate: release-prep branch points to the verified base before cleanup.

## Phase 1 — inventory and classification

Classify tracked content as `KEEP`, `MOVE/REWRITE`, `DELETE`, or `DEFER`.

Mandatory checks:
- cache/build/editor/OS junk;
- credential-like filenames and local environment files;
- stale bootstrap instructions;
- stale hard-coded file counts;
- duplicate release artifacts;
- packaged-source parity risks;
- release evidence and native-validation status.

Gate: no destructive change to canonical packaged source without a rebuild decision.

## Phase 2 — repository cleanup

Planned repository-only cleanup:
- add `.gitignore`;
- add root `LICENSE` matching packaged source;
- remove connector smoke artifact;
- archive the one-time import guide under `docs/maintenance/`;
- replace the hard-coded bootstrap/push script with a safe maintenance importer under `scripts/maintenance/`;
- rewrite root `README.md` and `STRUCTURE.md` so they do not depend on stale hard-coded file counts;
- keep `tool/source/DRAFT-NOT-VALIDATED.txt` because it is a draft-artifact safety notice and is part of the canonical source archive.

Gate: root is release-oriented; canonical source ZIP/wheel hashes remain unchanged.

## Phase 3 — automation and integrity metadata

- Add Linux CI for source regression/selftest and repository hygiene.
- Regenerate `REPO-MANIFEST.sha256` after all tracked cleanup/report files are finalized.
- Keep `BUNDLE-MANIFEST.json` and bundle `SHA256SUMS.txt` immutable because they attest the original RC4 bundle.

Gate: repository manifest validates the release-prep tree excluding itself; bundle attestation remains unchanged.

## Phase 4 — deterministic test matrix

Run and record:
- source regression: expected 126/126;
- source selftest: expected 13/13;
- source archive regression/selftest from a fresh extraction;
- wheel install/selftest and regression compatibility checks;
- package metadata/version triple;
- safe-path and semantic-isolation regression suites;
- production hard-code scan;
- generic cross-project acceptance;
- repository hygiene scan;
- checksum verification for bundle, source ZIP, and wheel.

Gate: all deterministic gates PASS with no new P0/P1 regression.

## Phase 5 — release review

Produce `RELEASE-PREP-REPORT.md` and a machine-readable ledger summarizing:
- cleanup delta;
- test commands/results;
- hashes;
- unresolved warnings;
- native compile/tester status;
- tag recommendation.

Gate: `GO_FOR_TAG_PRE_RELEASE` only if deterministic gates pass. `GO_FOR_PRODUCTION` requires independent native MetaEditor compile + MT5 Strategy Tester evidence.

## Phase 6 — merge/tag (not executed until explicitly approved)

- Merge the verified release-prep branch to `main`.
- Confirm the merged commit is exactly the reviewed content.
- Create annotated tag `v3.3.0rc4` from that commit.
- Publish as GitHub **Pre-release** while native validation is pending.
