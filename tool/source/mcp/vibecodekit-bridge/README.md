# vibecodekit-bridge

JSON-RPC 2.0 over stdio. Exposes the kit's high-level prompt → spec →
build → permission-gate loop to any MCP-aware AI coding agent
(Codex CLI, Claude Code, Cursor, Devin, Claude Desktop, …).

This is the 4th MCP server in the kit, joining `metaeditor-bridge`,
`mt5-bridge`, and `algo-forge-bridge`. Same wire format — same
`initialize` / `tools/list` / `tools/call` envelope.

## Tool set (30)

### PR-1: prompt → spec → build → permission-gate (4 tools)

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `spec.from_prompt` | `vibecodekit_mql5.spec_from_prompt.parse` | Free-text → validated `ea-spec.yaml`. |
| `spec.validate` | `vibecodekit_mql5.spec_schema.validate` | Schema-check a spec dict; collects every error. |
| `build.auto` | `vibecodekit_mql5.auto_build.run_pipeline` | scan → render → lint → compile → permission gate → dashboard. |
| `verify.permission` | `vibecodekit_mql5.permission.orchestrator.run` | 7-layer fail-fast gate (modes: personal/team/enterprise). |

### PR-2: verify suite + spec schema extension (7 tools)

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `verify.lint` | `vibecodekit_mql5.lint.lint_file` | 8 critical-tier AP detectors (AP-1/3/5/15/17/18/20/21). |
| `verify.lint_best_practice` | `vibecodekit_mql5.lint_best_practice.BEST_PRACTICE_DETECTORS` | 17 WARN-tier AP detectors (AP-2/4/6/7/8/9/10/11/12/13/14/16/19/22/23/24/25). |
| `verify.method_hiding` | `vibecodekit_mql5.method_hiding_check.check_method_hiding` | CExpert-subclass-without-`using` (ERROR ≥ build 5260). |
| `verify.trader17` | `vibecodekit_mql5.trader_check.evaluate` + `verdict` | 17-point reliability checklist; verdict by mode. |
| `verify.compile` | `vibecodekit_mql5.compile.compile_mq5` | MetaEditor compile (Wine on Linux) — convenience over `metaeditor.compile`. |
| `verify.broker_safety` | `vibecodekit_mql5.broker_safety.evaluate` | fill-policy / lot-step / min-lot / magic-range against a symbol-info JSON. |
| `verify.audit` | `vibecodekit_mql5.audit.run_audit` | Kit conformance battery (~70 probes). |

### PR-3: runtime / statistical verify suite (7 tools)

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `verify.backtest` | `vibecodekit_mql5.backtest.parse_xml_report_file` | Parse an MT5 tester XML report into a structured dict. |
| `verify.walkforward` | `vibecodekit_mql5.walkforward.evaluate` | OOS/IS Sharpe correlation + PASS/WARN/FAIL verdict (thresholds 0.5/0.3). |
| `verify.montecarlo` | `vibecodekit_mql5.monte_carlo.evaluate` | Bootstrap DD p50/p75/p95 + PASS/FAIL verdict (p95 ≤ 1.5× reported_dd). |
| `verify.multibroker` | `vibecodekit_mql5.multibroker.evaluate` | PF CV / Sharpe stdev / DD diff across N broker reports. |
| `verify.fitness` | `vibecodekit_mql5.fitness.get` / `list_templates` | Look up an `OnTester()` template (sharpe/sortino/profit-dd/expectancy/walkforward). |
| `verify.mfe_mae` | `vibecodekit_mql5.mfe_mae.parse_csv` + `compute_stats` | Trade CSV → mean MFE/MAE + Pearson corr with profit. |
| `verify.overfit` | `vibecodekit_mql5.overfit_check.evaluate` | Standalone IS/OOS Sharpe ratio verdict (no XML needed). |

### PR-4: review / RRI suite (5 tools)

Each review tool returns markdown ready to drop into a PR description
or a `review.md` artefact. The four named reviews each bundle a fixed
persona set plus default step templates; `rri.persona` is the generic
single-persona escape hatch.

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `review.eng` | `vibecodekit_mql5.review.eng_review.render` | Engineering review (broker-engineer + devops; default steps: build + verify). |
| `review.cso` | `vibecodekit_mql5.review.cso.render` | Chief Safety Officer review (risk-auditor; default steps: rri + verify). |
| `review.ceo` | `vibecodekit_mql5.review.ceo_review.render` | Executive review (trader + strategy-architect; default steps: vision + refine). |
| `review.investigate` | `vibecodekit_mql5.review.investigate.render` | Open-ended investigation (perf-analyst + strategy-architect; default steps: scan + rri). |
| `rri.persona` | `vibecodekit_mql5.review.review.render` | Generic single-persona drill. Pick 1 of 6 RRI personas × 1 of 8 steps × 1 of 3 modes. Omit `persona` to list IDs. |

### PR-5: ship-stage tools (2 tools)

Close the kit's full **prompt → spec → build → verify → review → ship**
loop over MCP. Both are hermetic-safe — `dashboard.publish` falls back to
a `file://` URI when no publish command is configured; `forge.pr.create`
returns a structured dry-run payload when no token is set, so CI never
touches the network.

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `dashboard.publish` | `vibecodekit_mql5.dashboard.{write_dashboard,publish}` | Render the 64-cell quality-matrix HTML from a pipeline digest (or take an existing `html_path`) and publish it via a configurable command. Returns `local_path` + `public_url`. |
| `forge.pr.create` | `vibecodekit_mql5.forge_pr.open_pr` | Open a PR on MQL5 Algo Forge. With `token` arg or `MQL5_FORGE_TOKEN` env: real HTTP call. Without: structured dry-run payload (`endpoint` + `planned_payload`). Pair with `dashboard.publish` to embed the public URL into the PR body. |

### `ea-spec.yaml` schema additions (PR-2)

Three optional, back-compat blocks were added so AI agents can talk
about prop-firm constraints, time-based exits, and broker-stealth
toggles without round-tripping through free-text comments:

| Block | What it captures |
|-------|------------------|
| `prop_firm` | `daily_dd_pct`, `max_dd_pct`, `profit_target_pct`, `news_block_min`, `weekend_flat`, `copy_trading_lock`. |
| `time_exit` | `close_on_friday`, `friday_close_hour`, `max_trade_hours`, `session_start_hour`, `session_end_hour`. |
| `stealth` | `randomize_slippage_pips`, `randomize_comment_pool`, `randomize_lot_jitter_pct`, `split_orders`, `avoid_round_numbers`. |

Specs that don't supply these blocks validate unchanged — the kit's
existing scaffolds continue to render exactly as before. Templates
that *do* want to consume these blocks can read them from the
normalised `EaSpec` dataclass.

### PR-7: discovery / fix-loop helpers (4 tools)

Give an AI agent the two things it always asks first — *"what's in
this repo?"* and *"how do I fix the lint errors I just got?"* —
without leaving the bridge. All four tools are hermetic (no
Wine / no network).

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `discover.doctor` | `vibecodekit_mql5.doctor.run_doctor` | Run the kit's environment doctor — checks Python version, Wine / MetaEditor, required modules, required scaffolds, and basic git posture. Returns `{ok, checks: [{name, status, detail}, …]}`. |
| `discover.scan` | `vibecodekit_mql5.scan.scan_tree` | Walk a workspace tree, classify by extension (`.mq5` → `ea-source`, `.mqh` → `include`, `.set` → `tester-set`, `.ex5` → `compiled`, `.onnx` → `onnx-model`), return `{root, files: [{path, kind, size}, …], counts: {kind: n, …}}`. Paths are root-relative. |
| `discover.llm_context` | `vibecodekit_mql5.llm_context.wire_llm` | Wire one of the 3 LLM-bridge scaffold patterns (`cloud-api`, `self-hosted-ollama`, `embedded-onnx-llm`) into an existing EA `.mq5` — adds the right `#include` / global instance / `OnInit()` init call. Mutates the file in place. |
| `verify.auto_fix` | `vibecodekit_mql5.auto_fix.fix_source` | Run the AP auto-fixer over an EA source. Pass `path` (file is rewritten) or `source` (in-memory). Returns `{ok, path, wrote_changes, mutations, annotations, findings_before, findings_after, fixed_text}`. Designed to chain with `verify.lint`: lint → see findings → auto_fix → lint again. |

### PR-19: EA docs renderer (1 tool)

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `docs.ea_render` | `vibecodekit_mql5.auto_build_docs_stage.write_docs_to_disk` | Render `<EAName>.docs.{html,md,pdf}` (Neo-Retro Dev Deck) for a validated spec + MQL5 source. Vietnamese default (`lang="vi"`); `lang="en"` opts back to English. Accept either `mq5_source` (in-memory) or `mq5_path`. PDF requires headless Chrome — falls back gracefully and reports the reason in `pdf_error`. |

All seven plan-β rút gọn milestones (PR-1 → PR-5, then PR-7, then
PR-19) are now in `DISPATCH`. The wire format is unchanged across
all of them and stays stable for future extensions.

## Launch directly

```bash
python mcp/vibecodekit-bridge/server.py < requests.ndjson
```

Each line of stdin is one JSON-RPC request; each line of stdout is one
JSON-RPC response. Notifications (`notifications/*`) produce no output.

## Argument validation (PR-13)

`tools/call` enforces every tool's `inputSchema.required` keys
**before** dispatching to the handler. Missing required keys (absent
or explicitly `null`) return a JSON-RPC `-32602 Invalid params` error
envelope listing each missing key. Empty strings, zeros, and empty
lists are treated as intentional values, not missing. Unknown tool
names still return `-32601 Method not found`.

Example — a call to `discover.llm_context` missing `pattern`:

```json
{"jsonrpc": "2.0", "id": 1, "error": {
  "code": -32602,
  "message": "tool discover.llm_context: missing required arguments: ['pattern']"
}}
```

## Smoke test

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' \
  | python mcp/vibecodekit-bridge/server.py
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python mcp/vibecodekit-bridge/server.py
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"spec.from_prompt","arguments":{"prompt":"build EA trend EURUSD H1 risk 0.5%"}}}' \
  | python mcp/vibecodekit-bridge/server.py
```

## Tests

Hermetic pytest cases (no Wine / MetaTrader5 needed):

```bash
pytest tests/test_vibecodekit_bridge.py -v
```

## Client configuration

See [`docs/HUONG-DAN-TOAN-TAP-vi.md`](../../docs/HUONG-DAN-TOAN-TAP-vi.md) (§12 MCP/IDE) for ready-to-paste
configs for Codex CLI, Claude Code, Cursor, and Codex Desktop. The
1-line summary is the same as the other bridges: add a
`command: python` + `args: [.../mcp/vibecodekit-bridge/server.py]`
entry to the client's MCP config.
