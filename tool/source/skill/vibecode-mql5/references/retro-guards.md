# Retro Behavioral Guards (runtime-aligned)

The runtime exposes this catalog through `AI-BUILD-CONTRACT.json`,
`mql5-retro-init`, and `vkmql-check retro`. Runtime IDs are `A1`–`A14` with
canonical aliases `RETRO-A1`–`RETRO-A14`; both forms are accepted.

## Guard catalog

| ID | Trigger | Required proof | Default severity |
| --- | --- | --- | --- |
| A1 | count, order, index, state | numeric examples and boundary tests | P1 |
| A2 | runtime error or dependency failure | explicit fail-fast/degrade policy and failure test | P0/P1 |
| A3 | approved owner decision | Decision Ledger entry and locking test | P1 |
| A4 | expected values in tests | independent derivation or oracle | P1 |
| A5 | cached runtime value | freshness policy and stale-value test | P0/P1 |
| A6 | async side effect | idempotency key/journal and duplicate test | P0/P1 |
| A7 | persisted test state | isolated environment and reset proof | P1 |
| A8 | event before retryable step | persist-until-consumed test | P0/P1 |
| A9 | pip/point/lot/time scale | single conversion point and unit tests | P0/P1 |
| A10 | platform or broker port | parity table and differential tests | P1 |
| A11 | performance claim | anti-optimization benchmark proof | P1 |
| A12 | multi-file edit-by-match | exact target and post-edit validation | P1/P2 |
| A13 | visible UI claim, freshness, or scope | source resolution and freshness evidence | P1 |
| A14 | panel rendering or hot-path work | render profile and hot-path isolation evidence | P0 |

## Required machine-readable shape

```yaml
id: RETRO-A6-ASYNC-IDEMPOTENCY
severity: P0
class: hard
triggered_by:
  - order_retry
rule: "A retryable order side effect must be idempotent"
required_evidence:
  - idempotency_key
  - duplicate_retry_test
checker: retro.async_idempotency
remediation: "Persist the operation identity before sending and reuse it on retry"
waiver_allowed: false
```

## Application rules

- Trigger only relevant guards; do not attach all guards ceremonially.
- A guard is satisfied only by its executable checker plus hashed evidence, not by prose claiming compliance.
- P0 guards block forward/live eligibility unless the policy explicitly defines a safe waiver; default P0 is non-waivable.
- Promote an item repeated in two or more projects into the universal catalog only when it is domain-independent. Keep domain-bound lessons in an adapter-specific catalog.
