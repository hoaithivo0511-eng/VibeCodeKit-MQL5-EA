# Retro Guards — runtime guide (v3)

Retro A1–A14 are machine-readable safety checks carried from the Vibecode
retro rubric into the MQL5 runtime. They are intentionally conservative:
configuration and evidence can be checked locally, while compile/backtest and
full source semantics still require the appropriate MT5/MetaEditor evidence.

## Quick path

```bash
mql5-retro-init ./MyEA
vkmql-check retro ./MyEA
```

The initializer creates `evidence/retro/guards.yaml` with every guard marked
`UNTESTABLE`. Replace those records only after attaching a hashed artifact and
the corresponding `checker_result`. A missing proof is not a pass.

Release provenance is a separate hard gate: Retro PASS records do not make a
project release-eligible by themselves. The compile/backtest artifacts must
also carry canonical execution provenance and pass `mql5-evidence-attestation`.

## Record shape

```yaml
guards:
  - id: A6
    canonical_id: RETRO-A6
    status: PASS
    checker: retro.async_idempotency
    checker_result:
      status: PASS
      findings: []
    evidence:
      idempotency_key: "trade-operation-id"
      duplicate_retry_test: "evidence/tests/a6-duplicate-retry.json"
    artifacts:
      - path: evidence/tests/a6-duplicate-retry.json
        sha256: "<sha256>"
```

The executable checker returns `PASS`, `FAIL`, or `UNTESTABLE`; `WAIVED` is
allowed only for non-hard guards and requires owner, reason, scope, expiry and
explicit risk acknowledgement. A `PASS` record without hashed artifacts is
invalid. A v2.6 record without `checker_result` remains readable for backward
compatibility but is not a substitute for semantic proof in new projects.

## Coverage boundary

The checkers prove numeric/declared policies, ledger integrity, evidence
linkage, and source-level trigger detection. They do not claim that an EA is
profitable, broker-safe, compiled, or live eligible. Those claims still require
the compile, tester, stress, approval and release gates.
