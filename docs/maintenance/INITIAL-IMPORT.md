# Initial repository import — historical note

This document records the one-time bootstrap/import process that was previously kept at repository root as `PUSH-GUIDE.md`.

The repository is already initialized and synchronized. **Do not use force-push as a normal release workflow.** Current release preparation should happen on a dedicated branch, pass the release gates, then be merged to `main` before tagging.

## Current maintenance workflow

1. Create a release-prep branch from the intended `main` commit.
2. Keep `tool/source/` byte-aligned with `tool/vibecodekit-mql5-v<version>-source-full.zip` for the release candidate being audited.
3. Make repository-only documentation/hygiene changes outside canonical packaged source unless the package is deliberately rebuilt.
4. Run source regression, selftest, package/archive checks, repository hygiene checks, and any available native validation.
5. Record the test report and evidence before merging.
6. Merge only after the release-prep gate is accepted.
7. Create the version tag from the verified merged commit; do not tag an intermediate cleanup commit.

## Historical context

The original bootstrap instructions referenced an earlier temporary repository snapshot and hard-coded file counts. Those values are intentionally not carried forward because the repository now contains the fully expanded v3.3.0rc4 source tree and release evidence.
