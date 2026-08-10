# VibeCodeKit MQL5 v3.3.0rc5 — SHIP README

Status: `SHIP-READY / NATIVE-VALIDATION-PENDING`

This archive is the complete install/test handoff for RC5. `ship_ready=true` means the tool, source, package, deterministic candidate, native runner, verifier and operator templates are materialized together. It does **not** mean MetaEditor/MT5 release certification has already passed.

The shipped candidate and SHIP manifest intentionally keep `release_eligible=false` until trusted native evidence is produced later.

## Included

- Full tracked `tool/source/` tree.
- Deterministic full-source ZIP and its manifest.
- `vibecodekit_mql5_ea-3.3.0rc5` wheel.
- Task-09 runtime candidate bundle.
- Candidate manifest and SHA-256 records.
- Root `RELEASE-TRUST.yaml` fail-closed trust template.
- Task-10 Windows native runner and repository verifier.
- Candidate-bound restart/recovery and deep-review templates.
- Task-10 runbook/status and package completion evidence.
- `SHIP-CONTENTS.json` inside the archive with SHA-256 for every payload member.

## Install the tool

Run from the extracted SHIP root on Windows PowerShell:

```powershell
py -3.11 -m venv .vck-rc5
.\.vck-rc5\Scripts\python.exe -m pip install --upgrade pip
.\.vck-rc5\Scripts\pip.exe install .\tool\vibecodekit_mql5_ea-3.3.0rc5-py3-none-any.whl
.\.vck-rc5\Scripts\mql5-selftest.exe
```

The wheel must install from the archive itself. Do not substitute a different wheel with the same version string.

## Native MetaEditor/MT5 validation — run later

The native validation inputs are intentionally PENDING when shipped:

```text
docs/release/v3.3.0rc5/native-evidence/templates/
  restart-recovery.template.json
  deep-review.template.json
```

Both templates are bound to the exact `source_tree_sha` in `RC5-CANDIDATE-MANIFEST.json`.

Before native validation:

1. Use a trusted Windows machine with real MetaEditor and MetaTrader 5 installed.
2. Generate an Ed25519 runner key using `mql5-runner-key`; keep the private key only on that Windows runner.
3. Put only the public-key SHA-256 fingerprint into root `RELEASE-TRUST.yaml`.
4. Execute and document all four restart/recovery cases in the supplied restart template. Every case needs `status=PASS` and a non-empty native evidence reference.
5. Complete the deep review template. `status=PASS` is valid only with no release blockers and no unresolved P0/P1 findings.
6. Run `scripts/native/Invoke-RC5NativeEvidence.ps1` using those completed reports plus the real EA/set inputs.
7. Require `scripts/maintenance/verify_rc5_native_evidence.py --require-pass` to succeed before any release-certification claim.

The full command and key-bootstrap procedure are in:

`docs/release/v3.3.0rc5/TASK-10-NATIVE-EVIDENCE-RUNBOOK.md`

## State semantics

- `ship_ready=true`: package/tool handoff is complete and installable.
- `native_validation_status=PENDING`: MetaEditor/MT5 tests are deliberately deferred.
- `release_eligible=false`: no native-release certification may be claimed yet.

Do not manually flip `release_eligible`. The release state must be derived from trusted native evidence and the repository verifier.
