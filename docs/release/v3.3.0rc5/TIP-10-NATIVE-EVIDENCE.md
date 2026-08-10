# TIP-10 — Trusted Native Evidence Gate

Task: `10 / Native evidence`
Branch: `native-evidence/v3.3.0rc5-pr10`
Base: `hardening/v3.3.0rc5@66a4914469614253a0f493b47a6daeb9b3d8aed6`
Severity: `P0 / release blocker`
Method: VibeCodeMaster `SCAN → RRI → VISION → BLUEPRINT → TASK GRAPH → BUILD → VERIFY → REFINE`

## Problem

Task 09 proves deterministic parity for live source, source ZIP and installed wheel, but cannot prove that generated MQL5 compiles and survives broker/runtime lifecycle boundaries in MetaTrader 5. The Task 06 ledger explicitly defers async-fill and restart/crash recovery to Task 10. A Python-only PASS is therefore forbidden.

## Existing controls reused

- `execution_sources.py` trusts only actual/remote MetaEditor and MT5 Strategy Tester sources for release evidence.
- `provenance.py` validates canonical artifact hashes, report structure and an Ed25519 runner attestation against a pinned `RELEASE-TRUST.yaml` fingerprint.
- `runner_key.py` keeps the private key on the native runner and refuses to sign artifact hashes that do not match bytes on disk.
- `evidence_attestation.py` binds core release evidence into the existing tamper-evident hash chain.

PR-10 extends these controls; it does not introduce a parallel trust mechanism.

## Task graph

| ID | Scope | Acceptance |
|---|---|---|
| T10.1 | Candidate binding | Native manifest signs exact Task-09 build input, source tree and package hashes |
| T10.2 | Native finalizer | Canonical compile/backtest/static evidence copied, hashed and Ed25519-signed on Windows runner |
| T10.3 | Runtime lifecycle | Partial-fill and restart reports are hash-bound inside signed backtest provenance; duplicate order count must be zero |
| T10.4 | Release gate | GitHub validator returns PASS only for trusted complete evidence; missing evidence is BLOCKED and never release-positive |

## Native acceptance contract

### Compile

- source = `actual_metaeditor` or a separately trusted remote-worker equivalent;
- actual MetaEditor build recorded;
- canonical `source.mq5`, `compile-log.txt` and `ea.ex5` hashes match;
- final MetaEditor summary contains `0 errors`;
- EX5 is non-trivial and covered by generic provenance.

### Strategy Tester

- source = `actual_mt5_strategy_tester` or trusted remote-worker equivalent;
- actual MT5 terminal build recorded;
- symbol/timeframe/model/date window and `tester.ini` are retained;
- report is real XML with trade count and performance metrics;
- report is covered by generic provenance and the runner signature.

### Async partial fill

Native report must state `PASS`, prove a real partial fill, contain a sequence including `SUBMITTED → PARTIAL → COMPLETED`, unique intent ids and `duplicate_order_count=0`.

### Restart/crash recovery

Native report must state `PASS`, prove an interruption/restart boundary and persisted-intent reload, contain `duplicate_order_count=0`, and finish in `TERMINAL_PROOF` or `OPERATOR_REQUIRED`. `BLIND_RETRY` is a hard failure.

## Fail-closed rules

- `BLOCKED` is not PASS.
- A parseable file is not execution proof.
- Imported/stub/Wine evidence cannot become release authority.
- A self-generated unpinned signing key is FAIL.
- A candidate hash mismatch is FAIL.
- No script may set the repository RC5 candidate `release_eligible=true` before the native gate itself returns PASS.
- The runner private key must never enter Git, Actions artifacts or the evidence directory.

## Current gate

Implementation infrastructure may be verified on GitHub-hosted Linux runners. T10.4 remains `BLOCKED_NATIVE_EXECUTION` until a real Windows MetaEditor/MT5 runner produces the signed evidence set and the independent GitHub validator accepts it.
