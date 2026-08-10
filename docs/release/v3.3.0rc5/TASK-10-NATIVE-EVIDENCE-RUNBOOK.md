# Task 10 — Trusted Native Evidence Runbook

Status: `HARNESS READY / NATIVE EXECUTION REQUIRED`

This task is the final release gate for `v3.3.0rc5`. It MUST NOT fabricate or substitute native evidence. GitHub-hosted Linux CI, synthetic fixtures, imported logs, imported Strategy Tester reports and Wine-only execution are not release authority.

## Acceptance contract

Task 10 is PASS only when all of the following are true for the exact RC5 package candidate already integrated by Task 09:

1. MetaEditor compile is executed by `actual_metaeditor` or an independently attested `remote_worker_metaeditor` backend.
2. MT5 Strategy Tester is executed by `actual_mt5_strategy_tester` or `remote_worker_strategy_tester`.
3. Compile log, EX5, Strategy Tester XML, restart/crash stress evidence and deep-review evidence all exist and match their manifest SHA-256 records.
4. Restart/crash report contains these four cases with `status=PASS`:
   - `abrupt_terminal_kill`
   - `restart_reconcile`
   - `no_duplicate_order`
   - `legacy_v1_migration_restart`
5. The signed compile provenance contains a candidate binding matching the Task-09 source tree, build input commit, package artifact hashes and runtime bundle hash.
6. `evidence/manifest.json` is signed on the native runner with an Ed25519 private key that never enters the repository.
7. The corresponding public-key fingerprint is reviewed and pinned in root `RELEASE-TRUST.yaml`.
8. `scripts/maintenance/verify_rc5_native_evidence.py --require-pass` returns PASS.
9. Existing deterministic source gates, frozen RC4 check, repository manifest check and repository hygiene remain green.

Any missing, skipped, untestable or non-PASS P0/P1 item blocks release eligibility.

## One-time runner trust bootstrap

The repository intentionally starts with a fail-closed root trust file:

```yaml
schema_version: 1
policy:
  require_pinned_runner_key: true
runner_keys: []
```

On the trusted Windows/MT5 machine, install the RC5 candidate wheel and generate a runner key:

```powershell
python -m venv C:\vck\runner-venv
C:\vck\runner-venv\Scripts\pip.exe install .\tool\vibecodekit_mql5_ea-3.3.0rc5-py3-none-any.whl
C:\vck\runner-venv\Scripts\mql5-runner-key.exe generate --key-id windows-runner-01 --out C:\vck\keys\runner.key
```

The command prints `public_key_b64` and `public_key_sha256`. Keep `runner.key` only on the native runner. Add only the public fingerprint to the reviewed root trust file. `schema_version` is the integer `1` (not the string `"1.0"`), because the verifier rejects any other type/value:

```yaml
schema_version: 1
policy:
  require_pinned_runner_key: true
runner_keys:
  - key_id: windows-runner-01
    algorithm: Ed25519
    public_key_sha256: "<PUBLIC_KEY_SHA256>"
    owner: "<responsible operator>"
    note: "Trusted Windows MetaEditor/MT5 runner"
```

Commit the trust-root change separately for review. Do not commit the private key or `public_key_b64`; only the SHA-256 public-key fingerprint is pinned in the repository.

## Required restart/crash report

Prepare a JSON file from the native restart/crash test run. Minimum structure:

```json
{
  "schema_version": "1.0",
  "source": "actual_mt5_restart_recovery",
  "restart_recovery_cases": [
    {"id": "abrupt_terminal_kill", "status": "PASS", "evidence": "<native log reference>"},
    {"id": "restart_reconcile", "status": "PASS", "evidence": "<native log reference>"},
    {"id": "no_duplicate_order", "status": "PASS", "evidence": "<native log reference>"},
    {"id": "legacy_v1_migration_restart", "status": "PASS", "evidence": "<native log reference>"}
  ]
}
```

The report is hash-bound and included in the runner signature. A status other than PASS is rejected.

## Execute the native run

Before executing, the reviewed branch must contain the real public-key fingerprint in root `RELEASE-TRUST.yaml`. From the repository checkout on the trusted Windows host:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\native\Invoke-RC5NativeEvidence.ps1 `
  -EaPath C:\path\to\generated\EA.mq5 `
  -SetFile C:\path\to\candidate.set `
  -MetaEditor "C:\Program Files\MetaTrader 5\metaeditor64.exe" `
  -Terminal "C:\Program Files\MetaTrader 5\terminal64.exe" `
  -RunnerKey C:\vck\keys\runner.key `
  -KeyId windows-runner-01 `
  -PublicKeyB64 "<PUBLIC_KEY_B64>" `
  -RestartRecoveryReport C:\vck\evidence\restart-recovery.json `
  -DeepReviewReport C:\vck\evidence\deep-review.json
```

The runner first verifies the Task-09 artifact hashes, installs the exact RC5 wheel, executes native MetaEditor and MT5 Strategy Tester, normalizes the evidence tree, requires the four restart cases, signs the manifest, creates the hash-chain/ship attestation, and finally calls the repository verifier with `--require-pass`.

## Evidence output

Successful execution materializes:

```text
docs/release/v3.3.0rc5/native-evidence/project/
  RELEASE-TRUST.yaml
  evidence/
    manifest.json
    compile/compile-log.txt
    compile/ea.ex5
    backtest/report.xml
    stress/stress-matrix-report.json
    review/deep-review.json
    attestation/hash-chain.json
    attestation/signature.json
  release/ship-manifest.json
```

Only this verified output may be proposed for the final Task-10 evidence commit. The repository candidate manifest remains `release_eligible=false` until the signed native evidence is reviewed and the final release predicate is explicitly updated.
