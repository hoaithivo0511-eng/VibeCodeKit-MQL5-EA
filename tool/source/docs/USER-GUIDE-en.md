---
id: user-guide-en
title: User guide — step-by-step EA build with vibecodekit-mql5-ea
audience: end_user, dev_team, ai_agent_operator
---

# Step-by-step guide: build an EA project with `vibecodekit-mql5-ea`

> Walks you from **zero → compiled `.ex5` + published dashboard +
> Neo-Retro Dev Deck docs** with the exact commands and expected output
> for each step. Counts in this document are kept in sync with the
> current `v2.4.3` baseline: **118 CLI commands**, **4 MCP servers**,
> **26 anti-pattern detectors (25 numbered AP-1…AP-25 + 1 build-aware
> method-hiding)**, **8 optional schema blocks** on `ea-spec.yaml`.
> Live test count is recorded in <code>README.md</code> and verified
> by CI on each push (see <code>pytest tests/gates -q</code>).
>
> Note: docs default to **Vietnamese** (project default). Pass
> `--docs-lang en` to opt back to English.

> 🇻🇳 Vietnamese master guide (single source): [HUONG-DAN-TOAN-TAP-vi.md](HUONG-DAN-TOAN-TAP-vi.md)
> 📖 Full reference manual: [USAGE-en.md](USAGE-en.md)
> 🔧 Env setup + IDE/CLI integration: see master guide §2/§12
> 💬 Prompt-driven build: see master guide §4

---

## Table of contents

- [0. TL;DR — the shortest path](#0-tldr--the-shortest-path)
- [1. Environment prep](#1-environment-prep)
- [2. Health check `mql5-doctor`](#2-health-check-mql5-doctor)
- [3. Choose one of two paths](#3-choose-one-of-two-paths)
- [4. Path A — CLI hands-on, 7 steps](#4-path-a--cli-hands-on-7-steps)
  - [4.1. Idea → `ea-spec.yaml`](#41-idea--ea-specyaml)
  - [4.2. Validate the spec (8 blocks)](#42-validate-the-spec-8-blocks)
  - [4.3. Build with `mql5-auto-build`](#43-build-with-mql5-auto-build)
  - [4.3.1. EA docs auto-generation (Neo-Retro Dev Deck)](#431-ea-docs-auto-generation-neo-retro-dev-deck)
  - [4.4. Verify — lint, method-hiding, trader17, permission](#44-verify--lint-method-hiding-trader17-permission)
  - [4.5. Test — backtest, walkforward, Monte Carlo](#45-test--backtest-walkforward-monte-carlo)
  - [4.6. Review — engineering, CSO, CEO, RRI](#46-review--engineering-cso-ceo-rri)
  - [4.7. Ship — dashboard + Algo Forge PR](#47-ship--dashboard--algo-forge-pr)
- [5. Path B — AI coding agent over MCP](#5-path-b--ai-coding-agent-over-mcp)
  - [5.1. Install `vibecodekit-bridge` into your tool](#51-install-vibecodekit-bridge-into-your-tool)
  - [5.2. Sample agent prompt](#52-sample-agent-prompt)
  - [5.3. Fix-loop `verify.lint` ↔ `verify.auto_fix`](#53-fix-loop-verifylint--verifyauto_fix)
  - [5.4. Re-render docs over `docs.ea_render`](#54-re-render-docs-over-docsea_render)
- [6. `ea-spec.yaml` — 8 optional blocks](#6-ea-specyaml--8-optional-blocks)
- [7. Troubleshooting & FAQ](#7-troubleshooting--faq)
- [8. Appendix — 118 CLI commands by group](#8-appendix--118-cli-commands-by-group)

---

## 0. TL;DR — the shortest path

Five commands to a compiled `.ex5`. Everything else in this doc is
elaboration on these.

```bash
# (1) One-time setup
./scripts/setup-wine-metaeditor.sh && python -m venv .venv && \
    source .venv/bin/activate && pip install -e .

# (2) Health check
python -m vibecodekit_mql5.doctor

# (3) Free-text → ea-spec.yaml
python -m vibecodekit_mql5.spec_from_prompt \
    "trend EA EURUSD H1 MACD + EMA cross, risk 0.5%, SL 30 TP 60, FTMO prop firm" \
    --out ea-spec.yaml

# (4) Build + lint + compile + permission gate + dashboard, one command
python -m vibecodekit_mql5.auto_build --spec ea-spec.yaml \
    --out ./dist --mode personal

# (5) Trader-17 + RRI sanity check before backtesting
python -m vibecodekit_mql5.trader_check ./dist/MyEA.mq5
```

Produces:

- `./dist/MyEA.mq5` — fully rendered source with RiskGuard,
  PipNormalizer, same-bar guard, all 8 TIPs.
- `./dist/MyEA.ex5` — compiled clean.
- `./dist/dashboard.html` — 64-cell quality matrix.
- `./dist/lint.json`, `./dist/permission.json` — audit artefacts.

---

## 1. Environment prep

Once per machine. For deeper config (proxy, custom Wine prefix,
Docker), see the master guide §2 (Environment).

### 1.1. Requirements

| Component | Version | Required? |
|-----------|---------|-----------|
| Python | ≥ 3.10 | ✅ |
| Wine | 8.0.2 (Linux/macOS) | ✅ for headless MetaEditor |
| MetaEditor | build ≥ 5260 | ✅ (method-hiding stays at ERROR) |
| MT5 terminal | build ≥ 4885 | ⚙️ only for local backtesting |
| ONNX runtime | 1.14 | ⚙️ `ml-onnx` scaffold only |
| Xvfb | any | ⚙️ headless CI on Linux only |

### 1.2. Linux (Ubuntu 22.04+) — one shot

```bash
# Unzip the downloaded release (.zip) to get started
cd vibecodekit-mql5-ea

# Wine + headless MetaEditor via wineboot (~3 min, idempotent)
./scripts/setup-wine-metaeditor.sh

# Dedicated venv, editable install
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 1.3. Windows native

- Install Python ≥ 3.10 from [python.org](https://python.org).
- Install MetaTrader 5 at `C:\Program Files\MetaTrader 5\` (native
  MetaEditor included).
- Set env var (PowerShell):

  ```powershell
  setx MQL5_TERMINAL_PATH "C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\<HASH>"
  ```

- Activate venv:

  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -e .
  ```

### 1.4. Docker (Devin / CI / VPS)

```bash
docker build -f Dockerfile.devin -t vck-mql5 .
docker run --rm -it -v "$PWD":/workspace vck-mql5 bash
```

Image already includes Wine 8.0.2 + MetaEditor + Python venv + frozen
`requirements.lock`. Same image powers the `linux-tests` and
`windows-tests` CI lanes.

---

## 2. Health check `mql5-doctor`

Run right after install. Doctor probes Python deps, Wine, MetaEditor,
PipNormalizer, the scaffold tree, and all 4 MCP servers.

```bash
python -m vibecodekit_mql5.doctor
```

Expected:

```json
{
  "ok": true,
  "probes": [
    {"name": "python", "ok": true, "detail": "3.11.4"},
    {"name": "wine", "ok": true, "detail": "8.0.2"},
    {"name": "metaeditor", "ok": true, "detail": "build 5260"},
    {"name": "pipnormalizer", "ok": true},
    {"name": "scaffolds", "ok": true, "detail": "23 preset×stack"},
    {"name": "mcp_servers", "ok": true, "detail": "4 servers"}
  ]
}
```

Any failing probe surfaces a fix hint in `detail` (e.g. `re-run
setup-wine-metaeditor.sh`, `pip install onnxruntime==1.14`, …).

> 💡 **Agent tip**: doctor is also wrapped as the MCP tool
> `discover.doctor` — agents can call it via the bridge without
> spawning a shell. See [section 5](#5-path-b--ai-coding-agent-over-mcp).

---

## 3. Choose one of two paths

The kit deliberately supports **two parallel paths**:

| | **Path A — CLI hands-on** | **Path B — AI agent over MCP** |
|---|---|---|
| Audience | Devs typing commands & reading output | Codex CLI / Claude Code / Cursor / Devin / Claude Desktop |
| Transport | Shell / venv | JSON-RPC 2.0 over stdio |
| Tool surface | 118 CLI commands | 30 MCP tools wrapping the main commands + 4 helpers |
| Best for | Learning, debugging, teaching, client demos | Batch builds, automatic fix-loops, in-IDE coding agents |
| Pipeline | **Identical** — same `auto_build`, lint, permission gate, dashboard | |

You can use both in the same project. The final `.mq5` / `.ex5` /
dashboard are bit-identical.

[Section 4](#4-path-a--cli-hands-on-7-steps) walks the 7 CLI steps.
[Section 5](#5-path-b--ai-coding-agent-over-mcp) covers the bridge
install for 5 agent tools.

---

## 4. Path A — CLI hands-on, 7 steps

```
prompt → spec → build → verify → test → review → ship
        4.1 4.2 4.3-4.4 4.5 4.6 4.7
```

### 4.1. Idea → `ea-spec.yaml`

Two ways to land on a spec:

**(a) Free-text → spec (chat-driven)**

Fastest for classic EAs:

```bash
python -m vibecodekit_mql5.spec_from_prompt \
    "trend EA EURUSD H1 MACD + EMA cross, risk 0.5%, SL 30 pips TP 60 pips, prop firm FTMO daily-DD 5%, close Friday 20h" \
    --out ea-spec.yaml
```

The parser infers `preset`, `stack` (default `wizard-composable`),
`signals`, `filters`, and the three PR-2 blocks (`prop_firm`,
`time_exit`, `stealth`) when the prompt mentions them. Output
includes `inferred` (auto-derived) and `defaulted` (fallback)
sections so you can review before building.

```yaml
name: TrendEA_EURUSD_H1
preset: standard
stack: wizard-composable
symbol: EURUSD
timeframe: H1
mode: personal
risk:
  per_trade_pct: 0.5
  sl_pips: 30
  tp_pips: 60
signals:
  - kind: macd
    fast: 12
    slow: 26
    signal: 9
  - kind: ema_cross
    fast: 9
    slow: 21
signal_logic: AND
prop_firm:
  daily_dd_pct: 5.0
  weekend_flat: true
time_exit:
  close_on_friday: true
  friday_close_hour: 20
```

**(b) Hand-write from template**

Required for EAs with custom hooks or the 5 new PR-8 blocks
(`trailing`, `partial_close`, `correlation`, `swap_filter`, `logs`).
See [section 6](#6-ea-specyaml--8-optional-blocks) for valid fields.

### 4.2. Validate the spec (8 blocks)

```bash
python -m vibecodekit_mql5.spec_validate ea-spec.yaml
```

Aggregates every schema error into one message (joined by `"; "`) —
does not bail on the first one. Example with 3 errors:

```
SpecValidationError: spec.timeframe must be a non-empty string; spec.risk.per_trade_pct=15.0 must satisfy 0 < x <= 10.0; spec.partial_close.levels[0].pct=-0.5 must satisfy -1e-9 < x <= 100.0
```

Eight optional, fully back-compat blocks:

| Block | Purpose |
|-------|---------|
| `prop_firm` | FTMO/MFF DD limits, news block, weekend-flat, copy-trade lock |
| `time_exit` | Close on Friday, max trade hours, session windows |
| `stealth` | Slippage / comment / lot-jitter randomisation, split orders |
| `trailing` | Trailing stop: fixed / ATR / parabolic |
| `partial_close` | Scale-out levels + move-SL-to-breakeven |
| `correlation` | Max correlated positions, Pearson threshold, symbol group |
| `swap_filter` | Daily swap pip caps per side, skip Wednesday triple-swap |
| `logs` | Level (debug/info/warn/error), file pattern, account redaction |

Specs without these blocks still validate cleanly.

### 4.3. Build with `mql5-auto-build`

The workhorse. Runs 6 stages sequentially with rollback on failure:

```
scan → build → lint → compile → permission-gate → dashboard
```

```bash
python -m vibecodekit_mql5.auto_build \
    --spec ea-spec.yaml \
    --out ./dist \
    --mode personal
```

`--mode` selects the permission profile:

| `--mode` | Layers enforced | Best for |
|----------|-----------------|----------|
| `personal` | 1, 2, 3, 4, 7 (5 layers) | Retail traders, personal accounts |
| `team` | adds 5 (commit signing) | Dev team shared repo |
| `enterprise` | all 1-7 | Prop firms, funds, brokers |

Output tree at `./dist`:

```
dist/
├── TrendEA_EURUSD_H1.mq5
├── TrendEA_EURUSD_H1.ex5
├── TrendEA_EURUSD_H1.docs.html # Neo-Retro Dev Deck docs (open in browser)
├── TrendEA_EURUSD_H1.docs.md # Markdown twin for git/agents
├── lint.json
├── permission.json
├── quality-matrix.html # 64-cell matrix + docs embed card
└── build.log
```

If any stage fails (e.g. compile reports `unknown identifier`),
`auto_build` does **not** run permission-gate / dashboard. You fix
first.

> **`auto-build` does not run the full release gate, nor emit the
> governance contract artifacts.** It scaffolds, compiles and runs the
> permission-gate, but the release gate's `contract` stage needs
> `EA-SPEC.yaml` + `AI-BUILD-CONTRACT.md/.json`. Before `vkmql-check all`,
> generate them once with `vkmql-new spec <dir>` then
> `vkmql-new contract <dir>` (a bare build emits neither). The gate
> itself prints these exact fix commands when the `contract` stage FAILs.

### 4.3.1. EA docs auto-generation (Neo-Retro Dev Deck)

After compile + gate, the pipeline auto-renders a per-EA user guide
following the **Neo-Retro Dev Deck** design system (cream grid-paper
bg, thick-bordered hot-pink / yellow / cyan blocks, pixel-art icons).
Language defaults to **Vietnamese** for the project. MQL5 identifiers
(`InpMagic`, `InpRiskMoney`, `CRiskGuard`, `ema_cross`, ...) are kept
verbatim regardless of language.

**Generated docs structure**

| Section | Content |
|---------|---------|
| Frontmatter | `ea_name`, `ea_version`, `kit_version`, `built_at`, `compile` + `gate` verdicts |
| Hero manifesto | Slogan + EA name |
| System architecture | 3-layer block: Risk guard / Signal fusion / Execution |
| Strategy evolution | 4-step timeline: Scan → Compose → Verify → Ship |
| EA inputs | `Name · Type · Default · Note` table parsed from every `input` declaration in the `.mq5` |
| Take notes | Auto-derived from the 8 PR-2/PR-8 spec blocks (prop-firm, trailing, partial close, ONNX, ...) |

Vietnamese is the default (override with `--docs-lang en`):

![EA docs Neo-Retro VN — hero + architecture](https://app.devin.ai/attachments/5678d878-23f9-433c-a6f2-b4f4c39bade5/screenshot-ea-docs-vi-top.png)

![EA docs Neo-Retro VN — timeline + params + take-notes](https://app.devin.ai/attachments/cb444a06-96e7-46f3-bdaa-b4d9f3adef72/screenshot-ea-docs-vi-middle.png)

The `quality-matrix.html` dashboard grows a yellow embed card linking
to whichever doc formats actually landed on disk (PDF only appears if
Chrome was available):

![Dashboard with EA Docs embed card](https://app.devin.ai/attachments/c6618a98-d836-4494-9a71-491c1202b18b/screenshot-dashboard-embed.png)

**Docs flags**

| Flag | Default | Effect |
|------|---------|--------|
| `--no-docs` | (off) | Skip the docs stage entirely |
| `--docs-lang vi\|en` | `vi` | Doc language. `en` opts back to English; default is Vietnamese |
| `--docs-formats html,md` | `html,md` | Output formats. Add `pdf` to render via headless Chrome |

**Example — export PDF via headless Chrome:**

```bash
python -m vibecodekit_mql5.auto_build \
    --spec ea-spec.yaml \
    --out ./dist \
    --mode personal \
    --docs-formats html,md,pdf
```

When `pdf` is requested, the pipeline discovers Chrome in this order:

1. `$MQL5_CHROME_PATH` env var (strongest override)
2. Chrome for Testing in the Devin sandbox
3. Playwright chromium, if installed
4. `chromium` / `chrome` on `PATH`

If no host has Chrome, the build still passes; `auto-build-report.json`
records `docs.pdf_error` with the env-var hint for overriding. The
dashboard only shows links to formats that actually exist on disk
(PR-18.1).

**Re-generate docs standalone (no EA rebuild)** — the LLM docgen pipeline:

```bash
# 1) Rebuild the deterministic context bundle from the real .mq5
python -m vibecodekit_mql5.docs_bundle \
    ea-spec.yaml \
    ./dist/TrendEA_EURUSD_H1.mq5 \
    --out-dir ./dist/docs
# 2) LLM authors ./dist/docs/guide.md from docs-context.json + docs-prompt.md
# 3) Render guide.md → Word .docx
python -m vibecodekit_mql5.docs_assemble \
    ./dist/docs/guide.md \
    --out ./dist/docs/TrendEA_EURUSD_H1.docs.docx
```

The bundle is derived straight from the parsed source inputs, so the
docs can never describe an input the EA does not expose. The legacy
fixed-template renderer (`mql5-ea-docs`) was removed in v2.6.

### 4.4. Verify — lint, method-hiding, trader17, permission

`auto_build` already runs lint, method-hiding, and permission for you.
You can also run them individually:

**Lint — 23 anti-patterns (8 ERROR + 14 WARN + 1 method-hiding)**

```bash
python -m vibecodekit_mql5.lint ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.lint_best_practice ./dist/TrendEA_EURUSD_H1.mq5
```

ERROR breaks CI; WARN is logged. Full catalog of 23 APs is in
[USAGE-en.md §6](USAGE-en.md#6-23-anti-pattern-detector).

**Method-hiding check** (kicks in at MetaEditor build ≥ 5260)

```bash
python -m vibecodekit_mql5.method_hiding_check ./dist/TrendEA_EURUSD_H1.mq5
```

**Trader-17 checklist** — 17 reliability points for live trading

```bash
python -m vibecodekit_mql5.trader_check ./dist/TrendEA_EURUSD_H1.mq5
```

**Permission gate** (re-run if `--mode` changes)

```bash
python -m vibecodekit_mql5.permission --mode personal --in ./dist
```

### 4.5. Test — backtest, walkforward, Monte Carlo

The kit deliberately doesn't auto-run MT5 — you stay in control of
the tester (local terminal, Wine, or MT5 Cloud Network). The kit
handles parsing + verdicts.

**Single backtest (XML already from tester)**

```bash
python -m vibecodekit_mql5.backtest ./reports/run1.xml
```

→ JSON with 14 metrics (PF, Sharpe, GHPR, expected payoff, MFE/MAE, …).

**Drive `terminal64.exe` end-to-end**

```bash
python -m vibecodekit_mql5.tester_run \
    --ea ./dist/TrendEA_EURUSD_H1.ex5 \
    --tester-ini tester.ini \
    --out ./reports/run1.xml
```

(Requires `MQL5_TERMINAL_PATH` or the `--terminal-path` flag.)

**Walkforward IS/OOS**

```bash
python -m vibecodekit_mql5.walkforward ./reports/is.xml ./reports/oos.xml
```

PASS/WARN/FAIL verdict at Sharpe correlation 0.5 / 0.3 thresholds.

**Monte Carlo bootstrap DD**

```bash
python -m vibecodekit_mql5.monte_carlo ./reports/returns.csv --reported-dd 12.5
```

PASS if p95 ≤ 1.5 × reported DD.

**Multibroker stability** (N XML reports from N brokers)

```bash
python -m vibecodekit_mql5.multibroker --reports ic.xml,ftmo.xml,exness.xml
```

**Overfit sanity** (OOS/IS Sharpe ratio, no XML needed)

```bash
python -m vibecodekit_mql5.overfit_check ./reports/is.xml ./reports/oos.xml
```

### 4.6. Review — engineering, CSO, CEO, RRI

Five review personas + six RRI personas — each opens a structured
template for you (or your agent) to fill:

```bash
python -m vibecodekit_mql5.eng_review ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.cso ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.ceo_review ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.investigate ./reports/incident.log

# RRI: backtest review, risk & robustness, indicator-dev
python -m vibecodekit_mql5.rri_bt ./reports/oos.xml
python -m vibecodekit_mql5.rri_rr ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.rri_chart ./dist/TrendEA_EURUSD_H1.mq5
```

Output: a Markdown template with 5 personas × 7 dimensions × 8 axes
(280 cells) for RRI-bt, and 25 questions × persona × 3 modes for
RRI-rr.

### 4.7. Ship — dashboard + Algo Forge PR

**Render + publish dashboard**

```bash
python -m vibecodekit_mql5.dashboard \
    --in ./dist \
    --publish-cmd 'rsync -az ./dist/dashboard.html user@host:/var/www/'
```

Without `--publish-cmd` the dashboard returns a local `file://` URI
(hermetic-safe for CI).

**Open a PR on MQL5 Algo Forge**

```bash
export MQL5_FORGE_TOKEN=...
python -m vibecodekit_mql5.forge_pr \
    --repo my-org/my-ea \
    --title "TrendEA v1.0" \
    --body "Dashboard: $(cat ./dist/dashboard_url.txt)"
```

Without a token → dry-run dict (`endpoint` + `planned_payload`) for
debugging.

**Tag + push (release)**

```bash
python -m vibecodekit_mql5.ship --tag v1.0.0 --push
```

---

## 5. Path B — AI coding agent over MCP

The kit ships **4 MCP servers** (JSON-RPC 2.0 over stdio):

| Server | Tools | Read/Write | Purpose |
|--------|-------|-----------|---------|
| `metaeditor-bridge` | 3 | Write | Compile EAs via headless MetaEditor (Wine) |
| `mt5-bridge` | 10 | **READ-ONLY** | Read account, position, history, symbol info |
| `algo-forge-bridge` | 6 | Write | CRUD repos, open PRs on MQL5 Algo Forge |
| `vibecodekit-bridge` | **30** | Write | Full EA build pipeline (spec → ship + docs) |

`vibecodekit-bridge` is the one you want. The 30 tools group as:

| Group | Tool count | Names |
|-------|------------|-------|
| `spec.*` | 2 | `spec.from_prompt`, `spec.validate` |
| `build.*` | 1 | `build.auto` |
| `verify.*` | 14 | `verify.lint`, `verify.lint_best_practice`, `verify.method_hiding`, `verify.compile`, `verify.permission`, `verify.trader17`, `verify.broker_safety`, `verify.backtest`, `verify.walkforward`, `verify.montecarlo`, `verify.multibroker`, `verify.fitness`, `verify.mfe_mae`, `verify.overfit`, `verify.auto_fix` |
| `review.*` | 4 | `review.eng`, `review.cso`, `review.ceo`, `review.investigate` |
| `rri.*` | 1 | `rri.persona` |
| `dashboard.*` | 1 | `dashboard.publish` |
| `forge.*` | 1 | `forge.pr.create` |
| `discover.*` | 3 | `discover.doctor`, `discover.scan`, `discover.llm_context` |
| `docs.*` | 1 | `docs.ea_render` (PR-19) |

### 5.1. Install `vibecodekit-bridge` into your tool

**Claude Code CLI**

```bash
claude mcp add vibecodekit-bridge -- \
    python /abs/path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py
```

**Cursor IDE** — `.cursor/mcp.json` at repo root:

```json
{
  "mcpServers": {
    "vibecodekit-bridge": {
      "command": "python",
      "args": ["/abs/path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py"]
    }
  }
}
```

**Codex CLI** — `~/.codex/config.toml`:

```toml
[mcp.servers.vibecodekit-bridge]
command = "python"
args = ["/abs/path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py"]
```

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS:

```json
{
  "mcpServers": {
    "vibecodekit-bridge": {
      "command": "python",
      "args": ["C:\\path\\to\\vibecodekit-mql5-ea\\mcp\\vibecodekit-bridge\\server.py"]
    }
  }
}
```

**Devin** — pre-installed in the default snapshot when you clone this
repo; nothing extra to configure.

### 5.2. Sample agent prompt

After installing, just type the prompt in your agent tool. The bridge
picks the right tools and the kit pipeline runs in full.

**In Claude Code CLI:**

```
I need a mean-reversion EA for XAUUSD M15.
- Risk 0.3% per trade
- SL 50 pips, TP 100 pips
- Bollinger Bands 20/2 + RSI < 30 → buy
- Trailing stop ATR 14, multiplier 2.5
- Close Friday positions
- Build in personal mode, output to ./out/

After building, run verify.lint + verify.trader17 and publish the
local dashboard.
```

The agent will chain:

1. `spec.from_prompt` — generate `ea-spec.yaml`.
2. `spec.validate` — confirm schema OK.
3. `build.auto` — render + compile + permission gate + docs + dashboard.
4. `verify.lint` — scan 23 anti-patterns.
5. `verify.trader17` — 17-point checklist.
6. `dashboard.publish` — produce `dashboard.html`.
7. `docs.ea_render` (PR-19) — optional, re-render docs in another
   language or with PDF without re-running the full build (see
   [5.4](#54-re-render-docs-over-docsea_render)).

**In Cursor (chat sidebar):**

```
@vibecodekit-bridge build a scalper EA EURUSD M5 risk 0.2% SL 10 TP 15, ema cross 5/13, no news 30 min before/after, output ./scalper/
```

### 5.3. Fix-loop `verify.lint` ↔ `verify.auto_fix`

This is the killer pattern that PR-7 unlocked — especially powerful
for coding agents:

```
Loop:
  lint_result = call('verify.lint', {'path': './out/MyEA.mq5'})
  if lint_result['errors_count'] == 0: break
  call('verify.auto_fix', {'path': './out/MyEA.mq5'}) # rewrite in-place
```

`verify.auto_fix` closes 8 critical APs automatically (AP-1 missing
SL, AP-3 missing magic, AP-15 race, AP-17 sync I/O, AP-18 method
shadow, AP-20 deinit leak, AP-21 OnTester missing, AP-22 init-fail
handler). An agent typically clears all ERRORs in ≤ 3 iterations.

> ⚠️ `verify.auto_fix` reads files with `errors='replace'` (PR-7.1
> hotfix) — `.mq5` files containing Windows-1252 characters (©,
> em-dash) won't crash the bridge.

### 5.4. Re-render docs over `docs.ea_render`

PR-19 added the 30th tool: `docs.ea_render`. An agent can call it
directly when it only needs to re-render docs — switch language, add
PDF output, regenerate after tweaking the spec — without re-running
the full `build.auto` pipeline.

```python
out = call('docs.ea_render', {
  'spec': spec_dict, # the parsed dict, same shape spec.validate returns
  'mq5_source': open('./out/MyEA.mq5').read(),
  'out_dir': './out',
  'lang': 'vi', # default; 'en' opts out
  'formats': ['html', 'md', 'pdf'], # default ['html','md']
})
# → {'ok': True, 'lang': 'vi', 'formats': [...],
# 'outputs': {'html': '.../MyEA.docs.html',
# 'md': '.../MyEA.docs.md',
# 'pdf': '.../MyEA.docs.pdf'},
# 'pdf_error': null}
```

Missing required keys in `spec` → server returns JSON-RPC `-32602
Invalid params` immediately (PR-13). A spec that fails schema validation
returns `{ok: false, stage: 'validate', errors: [...]}`. If Chrome is
unavailable and `formats` includes `pdf`, the other formats still emit
fine and `pdf_error` records the reason.

To read the `.mq5` from disk instead of passing it in-memory:

```python
call('docs.ea_render', {
  'spec': spec_dict,
  'mq5_path': './out/MyEA.mq5',
  'out_dir': './out',
})
```

**`discover.*` tools for agent context priming:**

- `discover.doctor` — JSON wrapper around `mql5-doctor`, lets the
  agent see what's available before planning.
- `discover.scan` — workspace inventory, classifies files by
  extension (`.mq5` → ea-source, `.mqh` → include, `.set` →
  tester-set, `.ex5` → compiled, `.onnx` → model).
- `discover.llm_context` — wires one of three LLM-bridge scaffold
  patterns (`cloud-api` / `self-hosted-ollama` /
  `embedded-onnx-llm`) into an existing EA.

---

## 6. `ea-spec.yaml` — 8 optional blocks

All blocks below are **optional + back-compat**. Specs that don't
supply them validate unchanged.

### 6.1. `prop_firm` (PR-2)

```yaml
prop_firm:
  daily_dd_pct: 5.0 # 0 < x <= 100
  max_dd_pct: 10.0 # 0 < x <= 100
  profit_target_pct: 8.0 # 0 < x <= 100
  news_block_min: 30 # 0 < x <= 1440
  weekend_flat: true
  copy_trading_lock: false
```

### 6.2. `time_exit` (PR-2)

```yaml
time_exit:
  close_on_friday: true
  friday_close_hour: 20 # 0 <= x <= 23
  max_trade_hours: 48 # 0 < x <= 720
  session_start_hour: 8 # 0 <= x <= 23
  session_end_hour: 22 # 0 <= x <= 23
```

### 6.3. `stealth` (PR-2)

```yaml
stealth:
  randomize_slippage_pips: 2.0
  randomize_comment_pool: [alpha, beta, gamma]
  randomize_lot_jitter_pct: 1.5
  split_orders: true
  avoid_round_numbers: true
```

### 6.4. `trailing` (PR-8)

```yaml
trailing:
  enabled: true
  mode: atr # fixed | atr | parabolic
  start_pips: 20.0
  step_pips: 5.0
  min_distance_pips: 3.0
  atr_period: 14 # required when mode=atr
  atr_mult: 2.5 # required when mode=atr
```

### 6.5. `partial_close` (PR-8)

```yaml
partial_close:
  enabled: true
  levels:
    - { at_pips: 20.0, pct: 50.0 } # close 50% at 20-pip profit
    - { at_pips: 50.0, pct: 30.0 } # close another 30% at 50-pip profit
  move_sl_to_breakeven_after_first: true
  breakeven_buffer_pips: 2.0
```

> 🔒 `pct` ∈ `[0, 100]`. Negative values are rejected (PR-8.1 hotfix);
> `pct=0` is still valid (no-op level).

### 6.6. `correlation` (PR-8)

```yaml
correlation:
  max_correlated_positions: 2
  correlation_threshold: 0.8 # Pearson |r|, ∈ (-1, 1]
  correlation_window_bars: 100
  symbol_group: [EURUSD, GBPUSD, AUDUSD]
  block_if_correlated_loss: true
```

### 6.7. `swap_filter` (PR-8)

```yaml
swap_filter:
  max_long_swap_pips_per_day: -1.0 # negatives are valid (brokers charging negative swaps)
  max_short_swap_pips_per_day: -1.5
  max_hold_bars_if_negative_swap: 24
  skip_wednesday_triple_swap: true
```

### 6.8. `logs` (PR-8)

```yaml
logs:
  enabled: true
  level: info # debug | info | warn | error
  to_file: true
  file_pattern: "logs/{ea}_{date}.log"
  to_terminal: false
  redact_account_numbers: true
```

> ℹ️ At this release, the 5 PR-8 blocks are **metadata** — `EaSpec`
> round-trips them through YAML and validates them, but scaffold
> templates don't yet consume the fields. Scaffold integration ships
> in a follow-up PR (out of scope for this guide).

---

## 7. Troubleshooting & FAQ

### 7.1. `mql5-doctor` reports Wine failing

```bash
./scripts/setup-wine-metaeditor.sh --reset
```

`--reset` clears the old Wine prefix and bootstraps a fresh one.
Safe — the kit doesn't store credentials inside the prefix.

### 7.2. Compile reports `metaeditor build < 5260`

Download MetaTrader 5 build ≥ 5260 from your broker or MetaQuotes.
If you must keep an older build, the method-hiding linter auto-
downgrades from ERROR to WARN, but you shouldn't ship live EAs on
< 5260.

### 7.3. `spec_validate` reports `unknown top-level key`

You used a block name not in the 5 required fields + 8 optional
PR-2/PR-8 blocks. Check spelling (e.g. `prop-firm` vs `prop_firm` —
the kit uses underscores).

### 7.4. `auto_build` fails permission-gate at layer 5

Layer 5 = commit signing. Either run `git config commit.gpgsign true`
and set up a GPG key, or use `--mode personal` to skip layer 5.

### 7.5. `forge.pr.create` returns a dry-run dict instead of a real PR

Missing `MQL5_FORGE_TOKEN`. Export it and retry:

```bash
export MQL5_FORGE_TOKEN="..."
```

### 7.6. CI reports `LOC ceiling exceeded`

Modules under `scripts/vibecodekit_mql5/` have a 400 effective-LOC
ceiling. Split overflow into a helper module (see
`spec_extensions.py` / `spec_blocks_extra.py` for the pattern).

### 7.7. AI agent invokes MCP but receives no tools

- Confirm the path to `server.py` is **absolute**.
- Confirm the kit venv has run `pip install -e .` before the server
  is launched.
- Smoke the stdio loop manually:

  ```bash
  echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' \
      | python mcp/vibecodekit-bridge/server.py
  ```

  Expect a response with `protocolVersion`, `capabilities`,
  `serverInfo`.

---

## 8. Appendix — 118 CLI commands by group

Quick reference; full docs in [USAGE-en.md](USAGE-en.md).

**Discovery (4)** — `scan`, `survey`, `doctor`, `audit`

**Plan (4)** — `rri`, `vision`, `blueprint`, `tip`

**Build (12)** — `build`, `auto_build`, `auto_fix`, `spec_from_prompt`,
`dashboard`, `wizard`, `pip_normalize`, `async_build`, `onnx_export`,
`onnx_embed`, `llm_context`, `forge_init`

**Verify (11)** — `compile`, `lint`, `method_hiding_check`,
`backtest`, `tester_run`, `walkforward`, `monte_carlo`,
`overfit_check`, `multibroker`, `fitness`, `mfe_mae`

(`lint_best_practice` exists as a Python module — invokable via
`python -m vibecodekit_mql5.lint_best_practice` — but is not
registered as a console script in `pyproject.toml`, so it doesn't
count toward the Verify CLI group.)

**RRI methodology (3)** — `rri_bt`, `rri_rr`, `rri_chart`

**Review (5)** — `review`, `eng_review`, `ceo_review`, `cso`,
`investigate`

**Deploy (3)** — `deploy_vps`, `cloud_optimize`, `canary`

**Ship (3)** — `forge_pr`, `ship`, `refine`

**Other (4)** — `broker_safety`, `trader_check`, `install`,
`second_opinion`

Total: **49 CLI** + 1 meta router = **50 entries**.

---

## Wrap-up

- **Path A (CLI)** suits learning, debugging, teaching, demos.
  7 explicit steps from prompt → ship.
- **Path B (MCP)** suits in-IDE coding agents (Codex / Claude /
  Cursor / Devin / Claude Desktop). 30 tools cover the full
  pipeline (including `docs.ea_render` for on-demand re-renders).
- The kit pipeline is the **source of truth**. Path B is just a
  JSON-RPC wrapper over Path A — no stage is bypassed.
- Every build auto-generates a Vietnamese-by-default Neo-Retro Dev
  Deck user guide for the EA (`<name>.docs.html` + `.docs.md`, plus
  `.docs.pdf` when Chrome is available). The dashboard links to
  whichever formats actually landed on disk.
- The `ea-spec.yaml` schema now covers 8 optional blocks (3 PR-2 +
  5 PR-8) for prop-firm, trailing, partial close, correlation,
  swap filter, and logs configuration.
- Latest baseline (v2.4.3): **38 unit tests passed** + **selftest 8/8 invariants passed** (the MetaEditor compile probe runs only on Wine/Windows), ruff clean,
  release audit passes.

For issues not in [section 7](#7-troubleshooting--faq), contact the official
release support channel and include the output of
`python -m vibecodekit_mql5.doctor`.


## Quality gates — added in v2.6.1

Three new commands add quantitative quality checks. Building an EA does **not** auto-run them — `mql5-build` / `mql5-project-gen` only scaffold code. Quality checking is a **separate, explicit** step via the `vkmql-check` gate.

| Command | Auto-runs inside `vkmql-check all`? | Notes |
| --- | --- | --- |
| `mql5-backtest-quality` | Yes — stage `quality` | Grades a tester XML on PF/RF/Sharpe/R²/MaxDD → PASS/WARN/FAIL/INSUFFICIENT. Advisory; blocks release only with `--require-release`. |
| stage `forward` (uses `mql5-walkforward`) | Yes — stage `forward` | Needs `evidence/walkforward/{is,oos}_report.xml`; absent → UNTESTABLE (not FAIL). |
| `mql5-trade-hygiene` | No — run separately (`vkmql-check hygiene`) | Static trade-call hygiene scan; advisory only, never blocks the gate. |
| `mql5-mt5-python` | No — standalone | MetaTrader5 worker (needs a live terminal); offline → UNTESTABLE (exit 3). |

```bash
# Full gate: quality + forward auto-run here (advisory)
vkmql-check all <project-dir>
vkmql-check all <project-dir> --require-release   # stricter: quality/forward block release

# Run SEPARATELY (not part of build or the default gate)
vkmql-check quality tester.xml        # = mql5-backtest-quality
vkmql-check hygiene Experts/MyEA.mq5  # = mql5-trade-hygiene
mql5-mt5-python probe --json          # needs a live MT5
```
