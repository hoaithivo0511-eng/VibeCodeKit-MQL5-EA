# Operating Loop and Artefacts

## Mode artefacts

| Mode | Required artefacts | Typical verification |
| --- | --- | --- |
| Lite | `TASK_NOTE.md`, `VERIFY_NOTE.md` | focused lint/test/diff check |
| Standard | scan, focused RRI, blueprint-lite, contract, task graph, TIP, verify report | affected tests plus backtest when behavior changes |
| Full | complete scan/RRI/spec/decisions/blueprint/contract/task graph/TIPs/completion/verify/evidence/retro | compile, backtest, stress, forward and release gates as applicable |

Use a single `docs/vibecode/PROJECT_STATE.yaml` manifest to point to active artefacts. Do not create the Full artefact set for small work.

## Phase exits

### SCAN exit

- Repository and applicable instructions are known.
- Current spec, decisions, contract, tests and evidence are located.
- Affected behavior and likely mode are identified.
- Missing environment capabilities are labelled, not guessed.

### RRI exit

- Unresolved high-impact questions have owner answers or documented assumptions.
- Runtime error policy is explicit where relevant.
- Counting, state and unit semantics include numeric examples where relevant.

### SPECIFY and DECIDE exit

- Semantic requirements are unambiguous and approved.
- Each critical owner decision has a stable ID and locking test.
- Derived metadata is distinguishable from owner-controlled fields.

### CONTRACT exit

- Allowed and forbidden paths are explicit.
- Forbidden claims are explicit.
- Triggered behavioral guards and required evidence are structured.
- Waiverability is known for every blocking rule.

### BUILD exit

- Changes stay within approved scope.
- Deviations are reported as change requests.
- No evidence or approval file is rewritten by the builder.

### VERIFY exit

- Expected values were derived independently from implementation where practical.
- Required commands and negative tests were run.
- `FAIL`, `UNTESTABLE`, and `SKIPPED` remain distinct.
- The report states which environment produced each result.

### EVIDENCE and RETRO exit

- Evidence is bound to artefact hashes.
- Human approval is bound to the reviewed build where required.
- Repeated failure patterns are recorded with promotion decisions.

## Automatic mode promotion

Promote Lite to Standard when static analysis cannot prove behavior preservation or when any trading decision input/output changes.

Promote Standard to Full when work touches risk limits, order lifecycle, live account connectivity, recovery/idempotency, architecture, platform porting, or release eligibility.
