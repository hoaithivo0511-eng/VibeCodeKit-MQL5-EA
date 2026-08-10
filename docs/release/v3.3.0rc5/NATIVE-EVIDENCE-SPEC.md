# RC5 Native Evidence Specification

Version: `1.0`
Release: `3.3.0rc5`
Canonical evidence root: `release-evidence/v3.3.0rc5/`

## Trust boundary

Native evidence is release-positive only when all of the following are true:

1. Generic `validate_release_provenance()` returns `PASS`.
2. The evidence manifest is signed by an Ed25519 key pinned in the evidence project's `RELEASE-TRUST.yaml`.
3. The verifier receives the matching public key through `VCK_RUNNER_PUBLIC_KEY_B64`; the private key stays on the Windows runner.
4. Compile and backtest provenance bind the exact Task-09 RC5 package identity.
5. Async partial-fill and restart/crash reports satisfy the semantic rules below and their SHA-256 digests are included inside the signed backtest provenance block.

A missing item is `BLOCKED`; a present but inconsistent/untrusted item is `FAIL`.

## Candidate binding

Both `manifest.compile.candidate_binding` and `manifest.backtest.candidate_binding` must exactly match:

- `kit_version`
- `source_tree_sha`
- `build_input_commit`
- SHA-256 of the Task-09 source ZIP
- SHA-256 of the Task-09 source manifest
- SHA-256 of the Task-09 wheel
- SHA-256 of the Task-09 runtime candidate bundle

Expected values are read from `docs/release/v3.3.0rc5/RC5-CANDIDATE-MANIFEST.json` and `RC5-ARTIFACTS.sha256`; they are not supplied by the native runner.

## Canonical files

```text
release-evidence/v3.3.0rc5/
├── RELEASE-TRUST.yaml
└── evidence/
    ├── manifest.json
    ├── compile/
    │   ├── source.mq5
    │   ├── compile-log.txt
    │   └── ea.ex5
    ├── backtest/
    │   ├── report.xml
    │   └── tester.ini
    ├── native/
    │   ├── async-fill.json
    │   └── restart-recovery.json
    ├── stress/stress-matrix-report.json
    ├── review/deep-review.json
    └── attestation/
        ├── hash-chain.json
        └── signature.json
```

Do not place real release evidence under `docs/`, `tests/`, `fixtures/`, `examples/` or `samples/`; the generic execution-source policy deliberately treats those as fixture space.

## Async-fill report schema

Required fields:

```json
{
  "schema_version": "1.0",
  "status": "PASS",
  "source": "actual_mt5_strategy_tester",
  "partial_fill_observed": true,
  "duplicate_order_count": 0,
  "intent_ids_unique": true,
  "state_sequence": ["PREPARED", "SUBMITTED", "PARTIAL", "COMPLETED"]
}
```

Additional broker/tester identifiers, timestamps, tickets and raw-log hashes are encouraged. `SUBMITTED`, `PARTIAL` and `COMPLETED` are mandatory states.

## Restart-recovery report schema

Required fields:

```json
{
  "schema_version": "1.0",
  "status": "PASS",
  "source": "actual_mt5_strategy_tester",
  "interruption_observed": true,
  "persisted_intent_reloaded": true,
  "duplicate_order_count": 0,
  "resolution": "TERMINAL_PROOF"
}
```

`resolution` may be `TERMINAL_PROOF` or `OPERATOR_REQUIRED`. Any blind retry outcome is a release failure.

## Operator sequence

1. Install the exact RC5 candidate/wheel and generate the EA probe from the intended generic project.
2. On the Windows MT5 runner, generate an Ed25519 key with `mql5-runner-key generate` if no approved key exists.
3. Commit/review only its public-key fingerprint in the evidence project's `RELEASE-TRUST.yaml`; never commit the private key.
4. Produce stress/deep-review outputs and the two native lifecycle reports from the actual test run.
5. Run `tool/native/collect-rc5-evidence.ps1` with the MetaEditor/terminal paths, build numbers, test period and evidence inputs.
6. The script performs native compile, Strategy Tester execution, canonicalization, signing, hash-chain generation and local RC5 validation.
7. Commit the resulting `release-evidence/v3.3.0rc5/` directory except any private key.
8. Configure GitHub `VCK_RUNNER_PUBLIC_KEY_B64` with the public key and let `RC5 Native Evidence Gate` independently validate the committed bytes.

Only after the independent gate returns `PASS` may a separate reviewed commit change the RC5 candidate from `release_eligible=false` to `true`.
