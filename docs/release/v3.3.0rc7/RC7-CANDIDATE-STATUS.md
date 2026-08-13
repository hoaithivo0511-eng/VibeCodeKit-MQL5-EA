# VibeCodeKit MQL5 v3.3.0rc7 — candidate status

Status date: **2026-08-13**

## Verdict

RC7 is the current source/tool candidate. The 2026-08-13 hardening pass closes
the source/wheel version drift, optional-header false positives, cache-order
instability, runtime annotation defect, MCP invalid-parameter inconsistency,
methodology drift and mutable GitHub Action references found by the Full
VibecodeV5 audit.

```text
repository/source/package/static E2E       VERIFIED LOCALLY
source archive / installed wheel parity    VERIFIED LOCALLY
Windows MetaEditor on final hardening tree UNTESTABLE
MT5 Strategy Tester                        UNTESTABLE
restart/recovery and broker parity         UNTESTABLE
forward/live readiness                     UNTESTABLE
release_eligible                           false
```

This is a tool-distribution candidate, not an EA profitability, production or
live-trading claim.

## Online baseline and hardening identity

The hardening branch starts from the latest integrated online `main`:

```text
baseline commit : c4924211d3dee507957c6ec2590c21d0563cfc59
baseline tree   : c444cfc3389719ac5ef8a5aaf32d2f1eed6c287d
merge           : PR #13 — RC7 Full E2E audit and docs truth sync
version         : 3.3.0rc7
```

Latest published GitHub pre-release remains `v3.3.0rc6`. RC7 has not been
tagged or published.

## Hardening verification

Current clean local gate:

```text
source tests               : 300 PASS
JUnit failures/errors/skip : 0 / 0 / 0
selftest                   : 13/13 PASS
Ruff E4/E7/E9/F            : PASS (--no-cache)
catalog                    : 139 tools consistent
entrypoints                : 139 callable
distribution snapshot      : PASS
public preset matrix       : trend / mean-reversion / breakout / hedging-multi PASS
MCP protocol matrix        : 4/4 bridges PASS
release fail-closed        : PASS
```

The RC7 package workflow now verifies the source checkout, a deterministic
source archive and the installed wheel with the full shipped suite. Its source
selftest is forced through `PYTHONPATH=scripts`, so it can no longer
accidentally import an already-installed wheel and hide source metadata drift.

## Closed findings

1. Package-local `agent-contract.json` is synchronized from the canonical RC7
   contract by the distribution maintenance workflow.
2. Project lint, senior review and deep review follow transitive local includes
   from `.mq5` entrypoints; copied but unused optional headers do not affect the
   strategy or release verdict.
3. Cross-file `OnTradeTransaction` satisfies AP-18, and UX-09/UX-10 require
   actual panel context.
4. Snapshot integrity ignores only named runtime cache directories while still
   rejecting arbitrary undeclared files.
5. `backtest._number` runtime type hints resolve successfully.
6. All four MCP bridges return JSON-RPC `-32602` for missing required
   arguments.
7. Retro documentation and runtime both expose A1–A14.
8. RC7 CI dependencies are constrained and official GitHub Actions are pinned
   to immutable commit SHAs.

## Native evidence boundary

PR #13's final head `4aca1bbf005ce8cb7d8ddd8a0f0097f8ffcc4c18`
has the same tree as baseline `main` and has trusted Windows MetaEditor evidence
with `0 errors, 0 warnings`. The hardening changes modify Python, docs and CI,
so that earlier evidence is not relabeled as exact-tree evidence for the new
candidate.

RC7 remains `release_eligible=false` until a final-tree Windows run supplies:

- trusted MetaEditor compile log and EX5 provenance;
- real MT5 Strategy Tester report;
- required stress/restart-recovery evidence;
- evidence manifest and approval bound to the final hashes.

## Historical audit record

`FULL-E2E-AUDIT-2026-08-12.md` is retained as a point-in-time report for the
older `44d449` baseline. It is not the current candidate status.
