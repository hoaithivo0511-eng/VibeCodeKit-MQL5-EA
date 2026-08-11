# Wave 1 Completion — runtime semantics and transaction safety

Date: `2026-08-09`

Status: `DONE — OWNER REVIEW REQUIRED`

Release eligible: `false`

Wave 1 completed four sequential runtime contracts:

1. Generated parameter docs preserve `input` and `sinput` semantics and ignore
   commented declarations without corrupting quoted delimiters.
2. Operational inputs have field-level unit, range, sign and zero contracts;
   invalid configurations fail before generation or during `OnInit()`.
3. Pending-order remote commands require explicit ownership and a durable
   claim/delete/apply lifecycle that blocks replay after uncertain recovery.
4. Trade intents use terminal identities, operation-specific retcodes and
   distinct asynchronous states with persistence at critical boundaries.

## Gate summary

| Task | Requirements | Focused tests | Coverage | Status |
|---|---|---:|---:|---|
| 03 Input semantics | REQ-009 | 4/4 | 96.34% | PASS |
| 04 Runtime input contracts | REQ-010–011 | 6/6 | 96.76% combined | PASS |
| 05 Remote command lifecycle | REQ-012–014 | 7/7 | 97% generator | PASS |
| 06 Trade lifecycle v2 | REQ-015–019 | 6/6 | 96.94% generator | PASS |
| Full RC5 regression | P1 Wave 1 | 182/182 | 0 skipped | PASS |
| RC5 selftest | Distribution invariants | 13/13 | — | PASS |

The generated Task 06 EA also passed `mql5-lint` with zero errors and one
unrelated UX warning, and passed the method-hiding scan at target build 5260.
The enterprise Trader-17 scan remains blocked at 6/17 PASS, 3 WARN and 8 N/A
because operational/native evidence is incomplete. No MetaEditor compile,
Strategy Tester, asynchronous broker-fill or crash/restart evidence was
produced locally. Those remain Task 10 release blockers. Wave 2 Tasks 07 and 08
require explicit owner approval.
