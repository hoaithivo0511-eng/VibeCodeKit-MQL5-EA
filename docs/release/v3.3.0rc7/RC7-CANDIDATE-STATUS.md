# VibeCodeKit MQL5 v3.3.0rc7 — Candidate Status

## Scope

RC7 adds the GitHub Actions Windows native MetaEditor compile backend and unifies compile policy across local, GitHub, remote-worker and Wine execution paths.

## Candidate policy

This branch is a **pre-candidate** until all source/package regression gates pass. It is not a production release and must remain fail-closed.

Current intended compile policy:

- 0 MetaEditor errors;
- 0 MetaEditor warnings by default;
- parseable `Result:` summary;
- physical `.ex5` output;
- stale log/binary removal;
- source + commit/tree + workflow run/job + artifact hash binding for GitHub execution.

## Native evidence status

Repository secret `MT5_INSTALLER_URL` was not configured during RC7 PR verification on 2026-08-12. Therefore the GitHub Windows `native-compile` job is intentionally **SKIPPED / UNTESTABLE**, not PASS.

The Linux fast gate validates parser/backend/provenance/security contracts but cannot substitute for a native MetaEditor execution.

## Release eligibility

`release_eligible=false` remains the required state until the independent runtime evidence required by the release policy is present and validated.

In particular RC7 native compile support does not establish:

- Strategy Tester PASS;
- forward-test eligibility;
- restart/recovery PASS;
- broker parity;
- live eligibility.

GitHub Strategy Tester remains outside RC7 and is planned as a later phase.

## CI gates

The RC7 PR must keep these checks green before it can be considered merge-ready:

1. RC7 GitHub Native Compile fast-gate.
2. Existing RC5/RC6 native contract regression.
3. Existing RC6 development regression.
4. RC7 Package Integration Gate:
   - canonical version check;
   - full source pytest suite;
   - source selftest;
   - two deterministic wheel builds with identical SHA-256;
   - clean wheel installation outside the checkout;
   - installed-wheel selftest.
5. Repository manifest must be refreshed after the final code/doc change.

## Promotion condition

A merge-ready RC7 PR may still carry native compile status `UNTESTABLE` when the repository has no configured native installer secret, but it must not claim native compile PASS or release eligibility. A real native smoke run is required before any release process that depends on this new backend as execution authority.
