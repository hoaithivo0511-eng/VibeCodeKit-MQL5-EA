# Task 18 — Trusted Native Evidence Runbook

Status: `HARNESS READY / NATIVE EXECUTION REQUIRED`

This is the mandatory Windows release gate for `v3.3.0rc6`. Linux CI,
synthetic fixtures, imported compile logs, imported tester reports and
Wine-only execution are not release authority.

## Preconditions

1. Task 17 has committed the RC6 candidate manifest, source ZIP, source
   manifest, reproducible wheel, runtime bundle and SHA-256 inventory.
2. The reviewed EA-IR and `.set` file are frozen for the native run.
3. A trusted Windows host has the intended MetaEditor and MT5 terminal builds.
4. The operator has executed all four restart/recovery scenarios and preserved
   one real log per case.
5. The runner public-key fingerprint is reviewed and pinned in root
   `RELEASE-TRUST.yaml`; the private key remains only on the Windows runner.

## Runner trust bootstrap

On the trusted Windows machine, install the exact RC6 wheel and generate the
key once:

```powershell
python -m venv C:\vck\runner-venv
C:\vck\runner-venv\Scripts\pip.exe install `
  .\tool\vibecodekit_mql5_ea-3.3.0rc6-py3-none-any.whl
C:\vck\runner-venv\Scripts\mql5-runner-key.exe generate `
  --key-id windows-runner-01 --out C:\vck\keys\runner.key
```

Commit only the printed `public_key_sha256` to `RELEASE-TRUST.yaml`. Never
commit `runner.key` or `public_key_b64`.

## Restart/recovery inputs

Copy the template at
`native-evidence/templates/restart-recovery.template.json`, fill in the exact
Task 17 `candidate_source_tree_sha`, and set every case to `PASS` only after the
scenario actually passed. The evidence directory must contain these files:

```text
abrupt_terminal_kill.log
restart_reconcile.log
no_duplicate_order.log
legacy_v1_migration_restart.log
```

The RC6 runner copies these files into canonical paths, hashes them and binds
them into both the Ed25519 runner signature and evidence hash chain. A URI or
text-only evidence reference is rejected.

## Execute

From the reviewed repository checkout on the trusted Windows host:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\native\Invoke-RC6NativeEvidence.ps1 `
  -EaIr C:\vck\inputs\EA-IR.json `
  -SetFile C:\vck\inputs\candidate.set `
  -MetaEditor "C:\Program Files\MetaTrader 5\metaeditor64.exe" `
  -Terminal "C:\Program Files\MetaTrader 5\terminal64.exe" `
  -RunnerKey C:\vck\keys\runner.key `
  -KeyId windows-runner-01 `
  -PublicKeyB64 "<PUBLIC_KEY_B64>" `
  -RestartRecoveryReport C:\vck\evidence\restart-recovery.json `
  -RestartEvidenceDirectory C:\vck\evidence\restart-cases `
  -Symbol EURUSD `
  -Timeframe H1 `
  -Period 2025.01.01-2025.03.31
```

The runner verifies all Task 17 hashes, installs the exact wheel, checks the
installed version, generates source from EA-IR with that wheel's
`mql5-ir-build`, compiles only that source,
runs Strategy Tester with the copied `.set`, performs the candidate reviewer,
creates schema 2.1 evidence, signs every artifact and invokes:

```powershell
python .\scripts\maintenance\verify_rc6_native_evidence.py `
  --native-project .\docs\release\v3.3.0rc6\native-evidence\project `
  --require-pass
```

## Required output

```text
docs/release/v3.3.0rc6/native-evidence/project/
  RELEASE-TRUST.yaml
  evidence/
    manifest.json
    input/EA-IR.json
    input/source-manifest.json
    input/test.set
    input/project/**/*.mq5
    input/project/**/*.mqh
    compile/compile-log.txt
    compile/ea.ex5
    backtest/report.xml
    backtest/tester.ini
    backtest/tester-result.json
    stress/stress-matrix-report.json
    stress/cases/*.log
    review/deep-review.json
    attestation/hash-chain.json
    attestation/signature.json
  release/ship-manifest.json
```

Task 18 is not complete until the verifier returns `PASS` with a pinned key.
The repository candidate remains `release_eligible=false` until Task 19 reviews
the full predicate and explicitly promotes the release.
