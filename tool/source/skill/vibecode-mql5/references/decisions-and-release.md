# Decisions, Approval, and Release

## Separate three records

Keep these concerns independent:

1. `DECISIONS.yaml` records semantic intent, owner, rationale, examples, tests and supersession.
2. `EVIDENCE_MANIFEST.json` records commands, environment, artefacts, hashes and gate results.
3. `OWNER_APPROVAL.json` records which human approved which spec/build/evidence hashes.

A hash chain proves artefact integrity. It does not by itself prove human identity or informed intent.

## Semantic change request

When approved meaning must change, propose:

```yaml
id: CR-001
current: "max_daily_loss_pct: 3"
proposed: "max_daily_loss_pct: 2"
reason: "Stress evidence exceeded the approved envelope"
affected_tests:
  - test_daily_loss_limit
owner_approval_required: true
```

Do not implement the proposed semantic value before approval.

## Guard hierarchy

Apply this order:

1. System, security, legal and repository policy.
2. Non-waivable P0 guards.
3. Approved EA-SPEC and Decision Ledger.
4. Waivable guards with an explicit recorded waiver.
5. Methodology recommendations.
6. Agent preferences.

Classify guards as:

- `hard`: cannot be overridden by owner text.
- `waivable`: requires owner, reason, scope, expiry and risk acknowledgement.
- `advisory`: owner decision may override; record the choice and lock it with tests.

## Release levels

- `DRAFT`: development only; evidence incomplete.
- `BACKTEST_ELIGIBLE`: specification and contract allow a backtest run.
- `FORWARD_ELIGIBLE`: required backtest/stress evidence and explicit owner approval exist.
- `LIVE_ELIGIBLE`: all mandatory real-environment gates pass and approval is bound to the exact build and evidence hashes.

Never present `LIVE_ELIGIBLE` as a profitability or safety guarantee.

## Approval strength

For the initial product:

- Backtest eligibility needs no human signature.
- Forward eligibility needs an explicit owner confirmation.
- Live eligibility needs authenticated owner approval bound to build and evidence hashes.
- Organizational use should add an independent risk reviewer or cryptographic signature.
