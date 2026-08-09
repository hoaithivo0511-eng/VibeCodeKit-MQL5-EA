"""vibecodekit-bridge tool implementations.

Thin shims over the kit's public modules so the MCP layer stays under
~250 LOC. Each tool's contract is documented in the ``inputSchema`` /
``description`` fields of ``TOOL_SCHEMAS`` so an LLM agent reading
``tools/list`` knows exactly how to call them.

PR-1 ships four tools — the minimum surface needed to drive the full
``prompt → spec → build → permission gate`` loop from a CLI agent
(``spec.from_prompt``, ``spec.validate``, ``build.auto``,
``verify.permission``). PR-2 adds the static-analysis verify suite
(``verify.lint`` + ``verify.lint_best_practice`` +
``verify.method_hiding`` + ``verify.trader17`` + ``verify.compile`` +
``verify.broker_safety`` + ``verify.audit``). PR-3 adds the runtime /
statistical verify suite (``verify.backtest`` + ``verify.walkforward``
+ ``verify.montecarlo`` + ``verify.multibroker`` + ``verify.fitness``
+ ``verify.mfe_mae`` + ``verify.overfit``). PR-4 adds the review /
RRI suite (``review.eng`` + ``review.cso`` + ``review.ceo`` +
``review.investigate`` + ``rri.persona``). PR-5 adds the ship-stage
tools (``dashboard.publish`` + ``forge.pr.create``) — the final
link in the kit's prompt → spec → build → verify → review → ship
loop over MCP. PR-7 adds the discovery / fix-loop helpers
(``discover.doctor`` + ``discover.scan`` + ``discover.llm_context``
+ ``verify.auto_fix``) so agents can self-orient in a fresh
workspace and run the AP auto-fixer without leaving the bridge.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from vibecodekit_mql5 import (
    audit as audit_mod,
    auto_build,
    auto_fix as auto_fix_mod,
    backtest as backtest_mod,
    broker_safety as broker_safety_mod,
    compile as compile_mod,
    doctor as doctor_mod,
    fitness as fitness_mod,
    lint as lint_mod,
    lint_best_practice as lint_bp_mod,
    llm_context as llm_context_mod,
    method_hiding_check as method_hiding_mod,
    mfe_mae as mfe_mae_mod,
    monte_carlo as monte_carlo_mod,
    multibroker as multibroker_mod,
    overfit_check as overfit_mod,
    scan as scan_mod,
    spec_from_prompt,
    spec_schema,
    trader_check as trader_check_mod,
    walkforward as walkforward_mod,
)
from vibecodekit_mql5 import auto_build_docs_stage as auto_build_docs_stage_mod
from vibecodekit_mql5 import build as build_mod
from vibecodekit_mql5 import dashboard as dashboard_mod
from vibecodekit_mql5 import ea_docs as ea_docs_mod
from vibecodekit_mql5 import forge_pr as forge_pr_mod
from vibecodekit_mql5.permission import orchestrator as orch_mod
from vibecodekit_mql5.review import (
    ceo_review as ceo_review_mod,
    cso as cso_mod,
    eng_review as eng_review_mod,
    investigate as investigate_mod,
    review as review_mod,
)
from vibecodekit_mql5.rri import (
    personas as rri_personas_mod,
    step_workflow as rri_steps_mod,
)


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "spec.from_prompt",
        "description": (
            "Translate a free-text EA description into a validated ea-spec.yaml. "
            "Deterministic regex parser — gaps fall back to schema defaults unless "
            "strict=true. Returns yaml + dict + lists of inferred/defaulted fields."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Free-text description of the EA."},
                "strict": {"type": "boolean", "default": False},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "spec.validate",
        "description": (
            "Validate a spec dict against the ea-spec.yaml schema. "
            "Returns ok + normalized EaSpec dict + collected errors. "
            "Errors list is empty iff ok=true."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "description": "Parsed spec dict (see spec_schema.py)."},
                "check_presets": {"type": "boolean", "default": True},
            },
            "required": ["spec"],
        },
    },
    {
        "name": "build.auto",
        "description": (
            "Run the kit's full auto-build pipeline: scaffold render → lint (23 AP "
            "detectors) → MetaEditor compile (skippable) → permission gate (7 layers, "
            "skippable) → dashboard. Returns the same report.json the CLI writes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "description": "Validated spec dict."},
                "out_dir": {"type": "string", "description": "Absolute path for the rendered project."},
                "skip_compile": {"type": "boolean", "default": False},
                "skip_gate": {"type": "boolean", "default": False},
                "skip_dashboard": {"type": "boolean", "default": True},
                "force": {"type": "boolean", "default": False},
                "publish_cmd": {"type": "string", "description": "Optional dashboard publish command."},
            },
            "required": ["spec", "out_dir"],
        },
    },
    {
        "name": "verify.permission",
        "description": (
            "Run the 7-layer permission orchestrator against a rendered .mq5. "
            "Mode personal runs layers 1/2/3/4/7; team adds 5; enterprise runs 1-7. "
            "Fail-fast: returns at the first FAIL layer with a structured report."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5 file."},
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "default": "personal",
                },
                "compile_log": {"type": "string", "description": "Optional MetaEditor compile log path."},
                "trader_check_report": {"type": "string", "description": "Optional trader-check JSON path."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.lint",
        "description": (
            "Run the 8 critical-tier anti-pattern detectors (AP-1/3/5/15/17/18/20/21) "
            "against an .mq5/.mqh. Returns ok + errors + warnings (Finding format). "
            "ok=true iff no ERROR-severity finding."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5/.mqh."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.lint_best_practice",
        "description": (
            "Run the 14 best-practice anti-pattern detectors (AP-2/4/6/7/8/9/10/11/"
            "12/13/14/16/19/22) against an .mq5/.mqh. All findings are WARN severity. "
            "Returns findings grouped by AP code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5/.mqh."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.method_hiding",
        "description": (
            "Detect method-hiding (CExpert-subclass-without-using-directive). "
            "Severity is ERROR when target_build >= 5260, WARN otherwise. "
            "Returns ok + list of HidingIssue (file/line/derived/base/method)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5."},
                "target_build": {"type": "integer", "default": 5260},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.trader17",
        "description": (
            "Run the 17-point Trader checklist on an .mq5. "
            "Pass threshold: ≥5/17 for personal/team, 17/17 for enterprise. "
            "Any FAIL fails the verdict regardless of mode. Returns ok + per-check "
            "results (PASS/WARN/FAIL/N/A) + summary string."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5."},
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "default": "personal",
                },
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.compile",
        "description": (
            "Compile an .mq5/.mqh via MetaEditor (Wine on Linux). Returns ok + "
            "errors + warnings + ex5_path. Convenience over metaeditor.compile so "
            "agents have one bridge for the full verify suite."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5/.mqh."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.broker_safety",
        "description": (
            "Check fill-policy / lot-step / min-lot / magic-range against a broker "
            "symbol-info JSON. Returns 4 PASS/WARN/FAIL flags + notes. Magic range "
            "is kit-reserved 70000-79999 per plan v5 §6."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5."},
                "symbol_info": {
                    "type": "object",
                    "description": (
                        "Broker symbol info JSON. Expected keys: filling_modes (list of "
                        "'FOK'/'IOC'/'RETURN'), volume_min (float), volume_step (float)."
                    ),
                },
            },
            "required": ["source", "symbol_info"],
        },
    },
    {
        "name": "verify.audit",
        "description": (
            "Run the kit conformance battery (~70 probes): every public module "
            "imports, every scaffold renders, every reference doc has front-matter, "
            "every methodology template exists. Returns ok + probes list (name/ok/"
            "detail)."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    # ─────────────────────────────────────────────────────────────────────
    # PR-3 — runtime / statistical verify suite
    # ─────────────────────────────────────────────────────────────────────
    {
        "name": "verify.backtest",
        "description": (
            "Parse an MT5 Strategy Tester XML report into a structured "
            "BacktestResult dict (PF, Sharpe, GHPR, DD, total_trades, MFE/MAE "
            "correlation, broker_digits, pre-start shift, …). Hermetic — only "
            "reads the XML file; no MT5 required. Use as the building block "
            "for verify.walkforward, verify.multibroker, verify.overfit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "xml_report_path": {
                    "type": "string",
                    "description": "Absolute path to the tester report XML file emitted by MT5.",
                },
            },
            "required": ["xml_report_path"],
        },
    },
    {
        "name": "verify.walkforward",
        "description": (
            "Walk-forward stability check: parse the in-sample + out-of-sample "
            "tester XML reports MT5 emits under Forward 1/4 mode, then compute "
            "OOS/IS Sharpe correlation and a PASS / WARN / FAIL verdict "
            "(thresholds 0.5 / 0.3)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "is_xml_path":  {"type": "string", "description": "In-sample XML report."},
                "oos_xml_path": {"type": "string", "description": "Out-of-sample XML report."},
            },
            "required": ["is_xml_path", "oos_xml_path"],
        },
    },
    {
        "name": "verify.montecarlo",
        "description": (
            "Monte-Carlo drawdown stress test. Bootstraps n_sims random "
            "permutations of the supplied returns series, returns the p50/p75/"
            "p95 drawdown percentiles, and a PASS / FAIL verdict (p95 ≤ 1.5× "
            "reported_dd). Returns provided inline or read from a CSV path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "returns": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Per-trade returns (P&L deltas). Mutually exclusive with returns_csv_path.",
                },
                "returns_csv_path": {
                    "type": "string",
                    "description": "CSV file: one numeric column. Mutually exclusive with returns.",
                },
                "reported_dd": {
                    "type": "number",
                    "description": "Reported drawdown percentage from the original backtest.",
                },
                "n_sims": {"type": "integer", "description": "Number of bootstrap simulations. Default 1000."},
                "seed":   {"type": "integer", "description": "Optional RNG seed for reproducibility."},
            },
            "required": ["reported_dd"],
        },
    },
    {
        "name": "verify.multibroker",
        "description": (
            "Aggregate stability across N tester XML reports from different "
            "brokers / symbols. Reports profit-factor coefficient of variation, "
            "Sharpe stdev, DD spread, optional PipNorm journal-presence check, "
            "and a PASS / FAIL verdict against the kit's standard thresholds "
            "(PF CV ≤ 0.30, Sharpe stdev ≤ 0.20, DD diff ≤ 5pp)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tester XML report paths (≥ 2).",
                },
                "journal_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of journal txt files to grep for '[PipNorm]'.",
                },
            },
            "required": ["report_paths"],
        },
    },
    {
        "name": "verify.fitness",
        "description": (
            "Return the MQL5 OnTester() expression for a named fitness template "
            "(sharpe / sortino / profit-dd / expectancy / walkforward) so a "
            "scaffold or autobuild step can paste it directly. Omit `template` "
            "to receive the sorted list of valid template names."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "template": {
                    "type": "string",
                    "description": "Template name. Omit to list all templates.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "verify.mfe_mae",
        "description": (
            "Maximum-favorable / maximum-adverse excursion analysis. Reads a "
            "CSV with profit/mfe/mae columns (path or inline text) and returns "
            "trade count + mean MFE/MAE + Pearson correlations with profit. "
            "Use when checking SL/TP placement against realised excursions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "csv_path": {"type": "string", "description": "Path to CSV with header row: profit,mfe,mae."},
                "csv_text": {"type": "string", "description": "Inline CSV text (mutually exclusive with csv_path)."},
            },
            "required": [],
        },
    },
    {
        "name": "verify.overfit",
        "description": (
            "Overfitting verdict from a pair of in-sample / out-of-sample "
            "Sharpe ratios. Computes OOS/IS ratio and returns a PASS / WARN / "
            "FAIL verdict (thresholds 0.7 / 0.5). Lightweight standalone check "
            "when you already have the two Sharpe numbers and don't need to "
            "re-parse the XML reports."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "is_sharpe":  {"type": "number", "description": "In-sample Sharpe ratio."},
                "oos_sharpe": {"type": "number", "description": "Out-of-sample Sharpe ratio."},
            },
            "required": ["is_sharpe", "oos_sharpe"],
        },
    },
    # ── PR-4: review personas + generic RRI ─────────────────────────────────
    {
        "name": "review.eng",
        "description": (
            "Engineering review (broker-engineer + devops personas). Renders "
            "the 8-step workflow's BUILD + VERIFY templates plus the active-mode "
            "RRI questions for the two personas. Returns markdown ready to drop "
            "into a PR description."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "description": "Audit depth. Default 'personal' (5 q/persona).",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": list(rri_steps_mod.STEPS)},
                    "description": "Override default step templates (default: build + verify).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "review.cso",
        "description": (
            "Chief Safety Officer review (risk-auditor persona). Single-persona "
            "drill on the risk envelope — bias toward RRI + VERIFY steps. "
            "Useful for compliance sign-off before live deployment."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "description": "Audit depth. Default 'personal'.",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": list(rri_steps_mod.STEPS)},
                    "description": "Override default step templates (default: rri + verify).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "review.ceo",
        "description": (
            "Executive review (trader + strategy-architect personas). Frames "
            "the EA in business / strategy terms — bias toward VISION + REFINE "
            "steps. Use when checking whether the strategy edge actually exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "description": "Audit depth. Default 'personal'.",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": list(rri_steps_mod.STEPS)},
                    "description": "Override default step templates (default: vision + refine).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "review.investigate",
        "description": (
            "Open-ended investigation review (perf-analyst + strategy-architect "
            "personas + SCAN/RRI templates). Use when a backtest, walkforward, "
            "or live deployment misbehaves and you need to capture hypotheses "
            "+ the data each one needs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "description": "Audit depth. Default 'personal'.",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string",
                              "enum": list(rri_steps_mod.STEPS)},
                    "description": "Override default step templates (default: scan + rri).",
                },
            },
            "required": [],
        },
    },
    # ── PR-5: ship-stage tools (dashboard + forge) ─────────────────────────
    {
        "name": "dashboard.publish",
        "description": (
            "Render the 64-cell quality-matrix dashboard for a build report "
            "and (optionally) publish it via a publish_cmd. Returns the local "
            "HTML path + public_url. Without a publish_cmd the public_url is "
            "a file:// URI — hermetic-safe. Provide an html_path to skip "
            "rendering and just publish an existing HTML; otherwise supply "
            "name + stages (and optional matrix_inputs) and the kit will "
            "render + write quality-matrix.html into out_dir first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "html_path": {
                    "type": "string",
                    "description": (
                        "Absolute path to an already-rendered dashboard HTML. "
                        "Mutually exclusive with name/stages."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "EA / pipeline name. Required when rendering.",
                },
                "ok": {
                    "type": "boolean",
                    "description": "Overall pipeline pass/fail (default True).",
                },
                "stages": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Stage entries (each {name, ok, skipped}). Required "
                        "when rendering. Stage names map to matrix cells: "
                        "build, lint, compile, gate."
                    ),
                },
                "matrix_inputs": {
                    "type": "object",
                    "description": "Optional pre-computed RRI matrix cell overrides.",
                },
                "out_dir": {
                    "type": "string",
                    "description": (
                        "Where to write quality-matrix.html when rendering. "
                        "Required iff html_path is omitted."
                    ),
                },
                "publish_cmd": {
                    "type": "string",
                    "description": (
                        "Shell command receiving the HTML path as its last "
                        "argv. Must print the public URL as its last non-blank "
                        "stdout line. Falls back to MQL5_DASHBOARD_PUBLISH_CMD "
                        "env, then to file:// fallback."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "forge.pr.create",
        "description": (
            "Open a pull request on MQL5 Algo Forge. Real HTTP call when a "
            "token is available (via the 'token' arg or the MQL5_FORGE_TOKEN "
            "env var); otherwise returns a structured dry-run dict so the "
            "agent can show the planned payload to the user without leaving "
            "the hermetic CI envelope. Pair with dashboard.publish to embed "
            "the public URL into the PR body."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo":   {"type": "string", "description": "Forge repo in 'owner/name' form."},
                "head":   {"type": "string", "description": "Source branch."},
                "base":   {"type": "string", "description": "Target branch (default 'main')."},
                "title":  {"type": "string", "description": "PR title."},
                "body":   {"type": "string", "description": "PR body (markdown)."},
                "token":  {"type": "string", "description": "Forge API token. Falls back to MQL5_FORGE_TOKEN env."},
                "api_base": {"type": "string", "description": "Override forge API base URL (advanced)."},
                "dry_run": {"type": "boolean", "description": "Force the no-token dry-run path even when a token is set."},
            },
            "required": ["repo", "head", "title"],
        },
    },
    {
        "name": "rri.persona",
        "description": (
            "Generic single-persona RRI review. Pick one of the 6 RRI personas "
            "(trader, risk-auditor, broker-engineer, strategy-architect, devops, "
            "perf-analyst), one of the 8 step templates, and an audit mode — "
            "returns the persona description, active-mode questions, and the "
            "chosen step template as markdown. Omit 'persona' to get the list "
            "of valid persona IDs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "persona": {
                    "type": "string",
                    "enum": list(rri_personas_mod.PERSONA_IDS),
                    "description": "Persona ID. Omit to list available IDs.",
                },
                "step": {
                    "type": "string",
                    "enum": list(rri_steps_mod.STEPS),
                    "description": "Step template (default: verify).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "description": "Audit depth (default: personal).",
                },
            },
            "required": [],
        },
    },
    # ─────────────────────────────────────────────────────────────────────
    # PR-7 — discovery / fix-loop helpers.
    # ─────────────────────────────────────────────────────────────────────
    {
        "name": "discover.doctor",
        "description": (
            "Run the kit's environment doctor — checks Python version, "
            "Wine/MetaEditor availability, required modules, required "
            "scaffolds, and basic git posture. Hermetic; safe to call "
            "from any agent before kicking off a build. Returns "
            "{ok, checks: [{name, status, detail}, …]}."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "discover.scan",
        "description": (
            "Inventory a workspace root: walks the tree, classifies "
            "files by extension into kit-known kinds (ea-source for "
            ".mq5, include for .mqh, tester-set for .set, compiled "
            "for .ex5, onnx-model for .onnx), and returns {root, "
            "files: [{path, kind, size}, …], counts: {kind: n, …}}. "
            "Paths in 'files' are relative to 'root'. Use this first "
            "when an agent opens an unfamiliar repo. PR-21: 'root' "
            "may also be a single classified file (e.g. a downloaded "
            "'My EA.mq5'); in that case the tool returns a 1-entry "
            "inventory with 'root' normalised to the parent directory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": {
                    "type": "string",
                    "description": (
                        "Directory or single classified source file to "
                        "scan (default: current working dir)."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "discover.llm_context",
        "description": (
            "Wire one of the three LLM-bridge patterns (cloud-api, "
            "self-hosted-ollama, embedded-onnx-llm) into an existing "
            "EA .mq5 source — adds the right #include / global instance "
            "/ OnInit() init call. Mutates the file in place. Returns "
            "{ok, mq5_path, pattern, added_include, added_global, "
            "added_init, notes}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mq5_path": {
                    "type": "string",
                    "description": "Path to the .mq5 EA source to wire.",
                },
                "pattern": {
                    "type": "string",
                    "enum": list(llm_context_mod.PATTERNS),
                    "description": "Which LLM-bridge scaffold pattern to wire in.",
                },
            },
            "required": ["mq5_path", "pattern"],
        },
    },
    {
        "name": "docs.ea_render",
        "description": (
            "Render the EA docs (Neo-Retro Dev Deck) for a validated spec "
            "+ MQL5 source. Vietnamese is the project default (lang='vi'); "
            "'en' opts back to English. Writes <EAName>.docs.{html,md,pdf} "
            "into 'out_dir' and returns the resolved file paths. Pass "
            "either 'mq5_source' (in-memory text) or 'mq5_path' (file on "
            "disk) \u2014 at least one is required. 'formats' defaults to "
            "['html','md']; include 'pdf' for headless-Chrome export. "
            "PDF gracefully falls back when no Chrome binary is found and "
            "the missing-Chrome reason is reported in 'pdf_error'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "object",
                    "description": "Parsed EA spec dict (see spec_schema.py).",
                },
                "out_dir": {
                    "type": "string",
                    "description": "Directory the .docs.{html,md,pdf} files are written into.",
                },
                "mq5_source": {
                    "type": "string",
                    "description": "In-memory MQL5 source. Use this when the EA has not been written to disk yet.",
                },
                "mq5_path": {
                    "type": "string",
                    "description": "Path to a .mq5 file on disk. Used when 'mq5_source' is not provided.",
                },
                "lang": {
                    "type": "string",
                    "enum": ["vi", "en"],
                    "default": "vi",
                    "description": "Output language. Project default is Vietnamese.",
                },
                "formats": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["html", "md", "pdf"]},
                    "default": ["html", "md"],
                    "description": "Which output formats to render.",
                },
            },
            "required": ["spec", "out_dir"],
        },
    },
    {
        "name": "verify.auto_fix",
        "description": (
            "Run the AP auto-fixer over one EA source. Either pass "
            "'path' to fix a file on disk (file is rewritten) or "
            "'source' to fix an in-memory string (file is not "
            "touched). Returns {ok, path, mutations: [...], "
            "annotations: [...], findings_before: [...], "
            "findings_after: [...], fixed_text}. Pairs naturally with "
            "verify.lint — agents call lint, see findings, call "
            "auto_fix, call lint again."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the .mq5 source to fix in place.",
                },
                "source": {
                    "type": "string",
                    "description": "In-memory MQL5 source. When provided, 'path' is treated as a label only and the file is not written.",
                },
                "label": {
                    "type": "string",
                    "description": "Label used when 'source' is given without 'path' (defaults to '<memory>').",
                },
            },
            "required": [],
        },
    },
]


def _tool_spec_from_prompt(args: dict[str, Any]) -> dict[str, Any]:
    prompt = args["prompt"]
    strict = bool(args.get("strict", False))
    result = spec_from_prompt.parse(prompt)
    if strict and result.defaulted:
        return {
            "ok": False,
            "error": f"strict mode: fields fell back to defaults: {result.defaulted}",
            "spec": result.spec,
            "yaml": spec_from_prompt.to_yaml(result.spec),
            "inferred": list(result.inferred),
            "defaulted": list(result.defaulted),
        }
    return {
        "ok": True,
        "spec": result.spec,
        "yaml": spec_from_prompt.to_yaml(result.spec),
        "inferred": list(result.inferred),
        "defaulted": list(result.defaulted),
    }


def _tool_spec_validate(args: dict[str, Any]) -> dict[str, Any]:
    spec = args["spec"]
    check_presets = bool(args.get("check_presets", True))
    valid_presets = build_mod.PRESETS if check_presets else None
    try:
        ea = spec_schema.validate(spec, valid_presets=valid_presets)
    except spec_schema.SpecValidationError as exc:
        return {"ok": False, "errors": str(exc).split("; "), "spec": None}
    return {"ok": True, "errors": [], "spec": ea.to_dict()}


def _tool_build_auto(args: dict[str, Any]) -> dict[str, Any]:
    spec = args["spec"]
    out_dir = Path(args["out_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # Validate first so we never feed a junk spec into the renderer.
    try:
        ea = spec_schema.validate(spec, valid_presets=build_mod.PRESETS)
    except spec_schema.SpecValidationError as exc:
        return {"ok": False, "stage": "validate", "errors": str(exc).split("; ")}
    report = auto_build.run_pipeline(
        spec=spec,
        out_dir=out_dir,
        skip_compile=bool(args.get("skip_compile", False)),
        skip_gate=bool(args.get("skip_gate", False)),
        skip_dashboard=bool(args.get("skip_dashboard", True)),
        force=bool(args.get("force", False)),
        ea_spec=ea,
        publish_cmd=args.get("publish_cmd"),
    )
    return report.to_dict()


def _finding_to_dict(f: Any) -> dict[str, Any]:
    return {
        "path": f.path, "line": f.line, "col": f.col,
        "severity": f.severity, "code": f.code, "message": f.message,
    }


def _tool_verify_lint(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    findings = lint_mod.lint_file(source)
    errors = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARN"]
    return {
        "ok": not errors,
        "n_errors": len(errors), "n_warnings": len(warnings),
        "errors":   [_finding_to_dict(f) for f in errors],
        "warnings": [_finding_to_dict(f) for f in warnings],
    }


def _tool_verify_lint_best_practice(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    raw = source.read_text(encoding="utf-8", errors="replace")
    # Strip comments the way the critical-AP linter does; the best-practice
    # detectors expect both the raw and the comment-stripped source.
    src = lint_mod._strip_comments(raw)
    grouped: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for code, detector in lint_bp_mod.BEST_PRACTICE_DETECTORS:
        findings = detector(str(source), raw, src)
        grouped[code] = [_finding_to_dict(f) for f in findings]
        total += len(findings)
    # WARN-only tier — ok is always True; this is informational.
    return {"ok": True, "n_warnings": total, "by_code": grouped}


def _tool_verify_method_hiding(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    target_build = int(args.get("target_build", 5260))
    report = method_hiding_mod.check_method_hiding(source, target_build=target_build)
    return {
        "ok": report.ok,
        "path": report.path,
        "target_build": report.target_build,
        "issues": [
            {
                "file": i.file, "line": i.line,
                "derived_class": i.derived_class, "base_class": i.base_class,
                "method": i.method, "severity": i.severity, "fix_hint": i.fix_hint,
            }
            for i in report.issues
        ],
    }


def _tool_verify_trader17(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    mode = args.get("mode", "personal")
    text = source.read_text(encoding="utf-8", errors="replace")
    result = trader_check_mod.evaluate(text)
    ok = trader_check_mod.verdict(result, mode=mode)
    summary = result.pop("_summary", "")
    return {"ok": ok, "mode": mode, "summary": summary, "checks": result}


def _tool_verify_compile(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    report = compile_mod.compile_mq5(source)
    return {
        "ok": bool(report.success),
        "errors": list(report.errors),
        "warnings": list(report.warnings),
        "ex5_path": report.ex5_path,
    }


def _tool_verify_broker_safety(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    symbol_info = args.get("symbol_info") or {}
    if not isinstance(symbol_info, dict):
        return {"ok": False, "error": "symbol_info must be a JSON object"}
    text = source.read_text(encoding="utf-8", errors="replace")
    result = broker_safety_mod.evaluate(text, symbol_info)
    return {"ok": result.all_pass, **result.to_dict()}


def _tool_verify_audit(args: dict[str, Any]) -> dict[str, Any]:
    rep = audit_mod.run_audit()
    return {
        "ok": rep.ok,
        "total": len(rep.probes),
        "passed": sum(1 for p in rep.probes if p.ok),
        "probes": [{"name": p.name, "ok": p.ok, "detail": p.detail} for p in rep.probes],
    }


def _tool_verify_permission(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    ns = argparse.Namespace(
        source=source,
        mode=args.get("mode", "personal"),
        compile_log=Path(args["compile_log"]) if args.get("compile_log") else None,
        trader_check_report=Path(args["trader_check_report"]) if args.get("trader_check_report") else None,
        state_dir=Path(".rri-state"),
        matrix=None,
        multibroker=None,
        journal=None,
    )
    report = orch_mod.run(ns)
    return report.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# PR-3 — runtime / statistical verify suite
# ─────────────────────────────────────────────────────────────────────────────

def _tool_verify_backtest(args: dict[str, Any]) -> dict[str, Any]:
    """Parse an MT5 tester XML report into a structured BacktestResult dict."""
    xml_path = Path(args["xml_report_path"]).resolve()
    if not xml_path.is_file():
        return {"ok": False, "error": f"xml_report_path not found: {xml_path}"}
    try:
        result = backtest_mod.parse_xml_report_file(xml_path)
    except Exception as exc:  # noqa: BLE001 — surface parser errors structurally
        return {"ok": False, "error": f"parse failed: {exc}"}
    return {"ok": True, "report": result.to_dict()}


def _tool_verify_walkforward(args: dict[str, Any]) -> dict[str, Any]:
    """OOS/IS Sharpe correlation + verdict from a pair of tester XML reports."""
    is_path  = Path(args["is_xml_path"]).resolve()
    oos_path = Path(args["oos_xml_path"]).resolve()
    for label, p in (("is_xml_path", is_path), ("oos_xml_path", oos_path)):
        if not p.is_file():
            return {"ok": False, "error": f"{label} not found: {p}"}
    try:
        is_r  = backtest_mod.parse_xml_report_file(is_path)
        oos_r = backtest_mod.parse_xml_report_file(oos_path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"parse failed: {exc}"}
    result = walkforward_mod.evaluate(is_r, oos_r)
    payload = result.to_dict()
    payload["ok"] = result.verdict == "PASS"
    return payload


def _tool_verify_montecarlo(args: dict[str, Any]) -> dict[str, Any]:
    """Bootstrap drawdown percentiles + PASS/FAIL verdict."""
    returns = args.get("returns")
    returns_csv_path = args.get("returns_csv_path")
    if returns is None and not returns_csv_path:
        return {"ok": False, "error": "either 'returns' or 'returns_csv_path' is required"}
    if returns is not None and returns_csv_path:
        return {"ok": False, "error": "'returns' and 'returns_csv_path' are mutually exclusive"}
    if returns_csv_path:
        path = Path(returns_csv_path).resolve()
        if not path.is_file():
            return {"ok": False, "error": f"returns_csv_path not found: {path}"}
        returns = monte_carlo_mod._read_returns_csv(path)
    if not isinstance(returns, list) or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in returns):
        return {"ok": False, "error": "'returns' must be a list of numbers"}
    if not returns:
        return {"ok": False, "error": "'returns' is empty"}
    try:
        reported_dd = float(args["reported_dd"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "error": "'reported_dd' must be a number"}
    n_sims = int(args.get("n_sims", 1000))
    seed   = args.get("seed")
    if n_sims < 1:
        return {"ok": False, "error": "'n_sims' must be ≥ 1"}
    result = monte_carlo_mod.evaluate(
        [float(x) for x in returns],
        reported_dd,
        n_sims=n_sims,
        seed=seed,
    )
    payload = result.to_dict()
    payload["ok"] = result.verdict == "PASS"
    return payload


def _tool_verify_multibroker(args: dict[str, Any]) -> dict[str, Any]:
    """Aggregate stability across N tester XML reports."""
    paths = args.get("report_paths") or []
    if not isinstance(paths, list) or len(paths) < 2:
        return {"ok": False, "error": "'report_paths' must be a list with at least 2 entries"}
    reports: list[backtest_mod.BacktestResult] = []
    for p in paths:
        path = Path(p).resolve()
        if not path.is_file():
            return {"ok": False, "error": f"report_paths entry not found: {path}"}
        try:
            reports.append(backtest_mod.parse_xml_report_file(path))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"parse failed for {path}: {exc}"}
    journals = args.get("journal_paths") or None
    if journals is not None and not isinstance(journals, list):
        return {"ok": False, "error": "'journal_paths' must be a list of strings"}
    result = multibroker_mod.evaluate(reports, journals=journals)
    payload = result.to_dict()
    payload["ok"] = result.verdict == "PASS"
    return payload


def _tool_verify_fitness(args: dict[str, Any]) -> dict[str, Any]:
    """Look up a fitness template by name, or list available templates."""
    name = args.get("template")
    if not name:
        return {"ok": True, "templates": fitness_mod.list_templates()}
    try:
        expr = fitness_mod.get(name)
    except KeyError:
        return {
            "ok": False,
            "error": f"unknown template: {name!r}",
            "available": fitness_mod.list_templates(),
        }
    return {"ok": True, "template": name, "expression": expr}


def _tool_verify_mfe_mae(args: dict[str, Any]) -> dict[str, Any]:
    """MFE/MAE excursion statistics from a trades CSV (path or inline text)."""
    csv_path = args.get("csv_path")
    csv_text = args.get("csv_text")
    if csv_path and csv_text:
        return {"ok": False, "error": "'csv_path' and 'csv_text' are mutually exclusive"}
    if not csv_path and not csv_text:
        return {"ok": False, "error": "either 'csv_path' or 'csv_text' is required"}
    if csv_path:
        path = Path(csv_path).resolve()
        if not path.is_file():
            return {"ok": False, "error": f"csv_path not found: {path}"}
        csv_text = path.read_text(encoding="utf-8", errors="replace")
    rows = mfe_mae_mod.parse_csv(csv_text or "")
    if not rows:
        return {"ok": False, "error": "no trade rows parsed from CSV"}
    try:
        stats = mfe_mae_mod.compute_stats(rows)
    except mfe_mae_mod.MfeMaeCsvError as exc:
        return {"ok": False, "error": str(exc)}
    except (KeyError, ValueError) as exc:
        return {"ok": False, "error": f"compute_stats failed: {exc}; expected header: {mfe_mae_mod.EXPECTED_HEADER}"}
    payload = stats.to_dict()
    payload["ok"] = True
    return payload


def _tool_verify_overfit(args: dict[str, Any]) -> dict[str, Any]:
    """IS/OOS Sharpe ratio + PASS/WARN/FAIL verdict."""
    try:
        is_sharpe  = float(args["is_sharpe"])
        oos_sharpe = float(args["oos_sharpe"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "error": "'is_sharpe' and 'oos_sharpe' must be numbers"}
    result = overfit_mod.evaluate(is_sharpe, oos_sharpe)
    payload = result.to_dict()
    payload["ok"] = result.verdict == "PASS"
    return payload


_VALID_MODES: frozenset[str] = frozenset({"personal", "team", "enterprise"})


def _normalise_mode(args: dict[str, Any]) -> tuple[str | None, str | None]:
    mode = args.get("mode", "personal")
    if not isinstance(mode, str) or mode not in _VALID_MODES:
        return None, f"mode must be one of {sorted(_VALID_MODES)}, got {mode!r}"
    return mode, None


def _normalise_steps(
    args: dict[str, Any], default: tuple[str, ...],
) -> tuple[tuple[str, ...] | None, str | None]:
    raw = args.get("steps")
    if raw is None:
        return default, None
    if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
        return None, "steps must be a list of strings"
    valid = set(rri_steps_mod.STEPS)
    bad = [s for s in raw if s not in valid]
    if bad:
        return None, f"unknown step(s): {bad} (valid: {sorted(valid)})"
    return tuple(raw), None


def _render_review(
    args: dict[str, Any],
    *,
    default_steps: tuple[str, ...],
    render: Any,
    personas: list[str],
) -> dict[str, Any]:
    mode, err = _normalise_mode(args)
    if err is not None:
        return {"ok": False, "error": err}
    steps, err = _normalise_steps(args, default_steps)
    if err is not None:
        return {"ok": False, "error": err}
    body = render(mode, steps)
    return {
        "ok": True,
        "mode": mode,
        "steps": list(steps),
        "personas": personas,
        "markdown": body,
    }


def _tool_review_eng(args: dict[str, Any]) -> dict[str, Any]:
    """Engineering review (broker-engineer + devops)."""
    return _render_review(
        args,
        default_steps=eng_review_mod.DEFAULT_STEPS,
        render=eng_review_mod.render,
        personas=list(eng_review_mod.PERSONAS),
    )


def _tool_review_cso(args: dict[str, Any]) -> dict[str, Any]:
    """Chief Safety Officer review (risk-auditor)."""
    return _render_review(
        args,
        default_steps=cso_mod.DEFAULT_STEPS,
        render=cso_mod.render,
        personas=[cso_mod.PERSONA],
    )


def _tool_review_ceo(args: dict[str, Any]) -> dict[str, Any]:
    """Executive review (trader + strategy-architect)."""
    return _render_review(
        args,
        default_steps=ceo_review_mod.DEFAULT_STEPS,
        render=ceo_review_mod.render,
        personas=list(ceo_review_mod.PERSONAS),
    )


def _tool_review_investigate(args: dict[str, Any]) -> dict[str, Any]:
    """Open-ended investigation review (perf-analyst + strategy-architect)."""
    return _render_review(
        args,
        default_steps=investigate_mod.DEFAULT_STEPS,
        render=investigate_mod.render,
        personas=list(investigate_mod.PERSONAS),
    )


def _tool_dashboard_publish(args: dict[str, Any]) -> dict[str, Any]:
    """Render + publish the quality-matrix dashboard.

    Two modes:
    * ``html_path`` supplied      → publish that file as-is.
    * ``name`` + ``stages`` + ``out_dir`` → render quality-matrix.html
      from the pipeline digest first, then publish.
    """
    html_path_raw = args.get("html_path")
    publish_cmd = args.get("publish_cmd") or None
    if html_path_raw:
        html_path = Path(html_path_raw).resolve()
    else:
        name = args.get("name")
        stages = args.get("stages")
        out_dir_raw = args.get("out_dir")
        if not (isinstance(name, str) and name):
            return {"ok": False, "error": "name is required when html_path is omitted"}
        if not (isinstance(stages, list) and all(isinstance(s, dict) for s in stages)):
            return {"ok": False, "error": "stages must be a list of objects when html_path is omitted"}
        if not (isinstance(out_dir_raw, str) and out_dir_raw):
            return {"ok": False, "error": "out_dir is required when html_path is omitted"}
        matrix_inputs = args.get("matrix_inputs") or {}
        if not isinstance(matrix_inputs, dict):
            return {"ok": False, "error": "matrix_inputs must be an object"}
        digest = dashboard_mod.PipelineDigest(
            name=name,
            ok=bool(args.get("ok", True)),
            stages=list(stages),
            matrix_inputs=matrix_inputs,
        )
        out_dir = Path(out_dir_raw).resolve()
        html_path = dashboard_mod.write_dashboard(digest, out_dir)
    location = dashboard_mod.publish(html_path, publish_cmd=publish_cmd)
    loc_dict = location.to_dict()
    return {
        "ok": location.error is None,
        **loc_dict,
    }


def _tool_forge_pr_create(args: dict[str, Any]) -> dict[str, Any]:
    """Open a PR on MQL5 Algo Forge.

    No-token / dry-run mode returns a structured planned-payload dict so
    the agent can preview the request without leaving the hermetic
    envelope. Real mode delegates to :func:`forge_pr.open_pr`.
    """
    repo = args.get("repo")
    head = args.get("head")
    title = args.get("title")
    if not (isinstance(repo, str) and repo):
        return {"ok": False, "error": "repo is required"}
    if not (isinstance(head, str) and head):
        return {"ok": False, "error": "head is required"}
    if not (isinstance(title, str) and title):
        return {"ok": False, "error": "title is required"}
    base = args.get("base", "main")
    body = args.get("body", "")
    api_base = args.get("api_base") or forge_pr_mod.DEFAULT_BASE
    token = args.get("token") or os.environ.get("MQL5_FORGE_TOKEN", "")
    spec = forge_pr_mod.PrSpec(
        repo=repo, head=head, base=base, title=title, body=body,
    )
    payload = {
        "repo": repo, "head": head, "base": base,
        "title": title, "body": body,
        "api_base": api_base,
    }
    if bool(args.get("dry_run", False)) or not token:
        return {
            "ok": False,
            "dry_run": True,
            "reason": "no MQL5_FORGE_TOKEN set" if not token else "dry_run=true",
            "endpoint": f"{api_base}/repos/{repo}/pulls",
            "planned_payload": payload,
        }
    report = forge_pr_mod.open_pr(spec, token=token, base_url=api_base)
    return {
        "ok": report.ok,
        "endpoint": report.endpoint,
        "status": report.status,
        "body": report.body,
        "error": report.error,
    }


def _tool_rri_persona(args: dict[str, Any]) -> dict[str, Any]:
    """Generic single-persona RRI review (mirrors ``mql5-review`` CLI)."""
    persona = args.get("persona")
    if persona is None:
        return {
            "ok": True,
            "available_personas": list(rri_personas_mod.PERSONA_IDS),
            "available_steps": list(rri_steps_mod.STEPS),
            "available_modes": list(rri_personas_mod.MODES),
        }
    if persona not in rri_personas_mod.PERSONA_IDS:
        return {
            "ok": False,
            "error": (
                f"unknown persona {persona!r} "
                f"(valid: {list(rri_personas_mod.PERSONA_IDS)})"
            ),
        }
    mode, err = _normalise_mode(args)
    if err is not None:
        return {"ok": False, "error": err}
    step = args.get("step", "verify")
    if step not in rri_steps_mod.STEPS:
        return {
            "ok": False,
            "error": f"unknown step {step!r} (valid: {list(rri_steps_mod.STEPS)})",
        }
    body = review_mod.render(persona, step, mode)
    return {
        "ok": True,
        "persona": persona,
        "step": step,
        "mode": mode,
        "markdown": body,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PR-7 — discovery / fix-loop helpers.
# ─────────────────────────────────────────────────────────────────────────────


def _tool_discover_doctor(args: dict[str, Any]) -> dict[str, Any]:
    """Run the kit's environment doctor (hermetic; no Wine/network needed)."""
    report = doctor_mod.run_doctor()
    return {
        "ok": bool(report.ok),
        "checks": list(report.checks),
    }


def _tool_discover_scan(args: dict[str, Any]) -> dict[str, Any]:
    """Inventory a workspace root (extension → kit-known kind).

    PR-21: ``root`` may also point at a single classified source
    file. The kit's ``scan_tree`` helper normalises the reported
    ``root`` to the parent directory so the standard chain pattern
    ``Path(root) / files[i].path`` keeps working in both modes.
    """
    raw = args.get("root")
    root = Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()
    if not root.exists():
        return {"ok": False, "error": f"root does not exist: {root}"}
    if not (root.is_dir() or root.is_file()):
        return {
            "ok": False,
            "error": f"root is neither a directory nor a regular file: {root}",
        }
    report = scan_mod.scan_tree(root)
    return {
        "ok": True,
        "root": report.root,
        "files": list(report.files),
        "counts": dict(report.counts),
    }


def _tool_discover_llm_context(args: dict[str, Any]) -> dict[str, Any]:
    """Wire an LLM-bridge scaffold pattern into an existing EA .mq5 file."""
    raw_path = args.get("mq5_path")
    if not raw_path:
        return {"ok": False, "error": "mq5_path is required"}
    pattern = args.get("pattern")
    if pattern not in llm_context_mod.PATTERNS:
        return {
            "ok": False,
            "error": (
                f"unknown pattern {pattern!r} "
                f"(valid: {list(llm_context_mod.PATTERNS)})"
            ),
        }
    mq5_path = Path(raw_path).expanduser().resolve()
    if not mq5_path.exists():
        return {"ok": False, "error": f"mq5_path does not exist: {mq5_path}"}
    report = llm_context_mod.wire_llm(mq5_path, pattern)
    return {
        "ok": bool(report.ok),
        "mq5_path": report.mq5_path,
        "pattern": report.pattern,
        "added_include": bool(report.added_include),
        "added_global": bool(report.added_global),
        "added_init": bool(report.added_init),
        "notes": list(report.notes),
    }


def _findings_to_dicts(findings: list[Any]) -> list[dict[str, Any]]:
    """Best-effort serialisation of lint.Finding dataclasses."""
    out: list[dict[str, Any]] = []
    for f in findings or []:
        if hasattr(f, "__dataclass_fields__"):
            out.append({k: getattr(f, k) for k in f.__dataclass_fields__})
        elif isinstance(f, dict):
            out.append(dict(f))
        else:
            out.append({"repr": repr(f)})
    return out


def _tool_verify_auto_fix(args: dict[str, Any]) -> dict[str, Any]:
    """Run the AP auto-fixer over one file or in-memory source."""
    src = args.get("source")
    raw_path = args.get("path")
    if src is None and not raw_path:
        return {"ok": False, "error": "either 'path' or 'source' is required"}
    if src is not None:
        label = raw_path or args.get("label") or "<memory>"
        report = auto_fix_mod.fix_source(str(label), src)
        path_repr = str(label)
        wrote = False
    else:
        mq5_path = Path(raw_path).expanduser().resolve()
        if not mq5_path.exists():
            return {"ok": False, "error": f"path does not exist: {mq5_path}"}
        original = mq5_path.read_text(encoding="utf-8", errors="replace")
        report = auto_fix_mod.fix_source(str(mq5_path), original)
        if report.fixed_text != original:
            mq5_path.write_text(report.fixed_text, encoding="utf-8")
            wrote = True
        else:
            wrote = False
        path_repr = str(mq5_path)
    return {
        "ok": True,
        "path": path_repr,
        "wrote_changes": wrote,
        "mutations": list(report.mutations),
        "annotations": list(report.annotations),
        "findings_before": _findings_to_dicts(report.findings_before),
        "findings_after": _findings_to_dicts(report.findings_after),
        "fixed_text": report.fixed_text,
    }


def _tool_docs_ea_render(args: dict[str, Any]) -> dict[str, Any]:
    """Render the Neo-Retro EA docs for one validated spec (PR-19).

    Thin shim over ``auto_build_docs_stage.write_docs_to_disk``: validates
    the spec the same way ``build.auto`` does, resolves the MQL5 source
    from either ``mq5_source`` (in-memory) or ``mq5_path`` (file on
    disk), and forwards to the shared renderer so the on-disk artifacts
    are byte-identical to what the pipeline stage produces.
    """
    spec = args["spec"]
    out_dir = Path(args["out_dir"]).resolve()
    mq5_source = args.get("mq5_source", "")
    mq5_path_arg = args.get("mq5_path", "")

    # Resolve MQL5 text. Prefer in-memory source so callers don't need
    # a real file on disk; fall back to reading from path.
    if mq5_source:
        mq5_text = mq5_source
    elif mq5_path_arg:
        try:
            mq5_text = Path(mq5_path_arg).read_text(
                encoding="utf-8", errors="replace",
            )
        except OSError as exc:
            return {
                "ok": False,
                "error": f"failed to read mq5_path: {exc}",
            }
    else:
        return {
            "ok": False,
            "error": "either 'mq5_source' or 'mq5_path' must be provided",
        }

    try:
        ea = spec_schema.validate(spec, valid_presets=build_mod.PRESETS)
    except spec_schema.SpecValidationError as exc:
        return {
            "ok": False,
            "stage": "validate",
            "errors": str(exc).split("; "),
        }

    lang = str(args.get("lang", "vi"))
    formats_in = args.get("formats", ("html", "md"))
    formats: tuple[str, ...] = tuple(formats_in) if formats_in else ("html", "md")

    build_meta = ea_docs_mod.BuildMeta.now(
        ea_version=str(spec.get("version", "0.1.0")),
        kit_version=ea_docs_mod._kit_version(),
        built_from=str(spec.get("name", ea.name)),
    )
    return auto_build_docs_stage_mod.write_docs_to_disk(
        ea, mq5_text, out_dir,
        lang=lang, formats=formats, build_meta=build_meta,
    )


DISPATCH = {
    "spec.from_prompt":         _tool_spec_from_prompt,
    "spec.validate":            _tool_spec_validate,
    "build.auto":               _tool_build_auto,
    "verify.permission":        _tool_verify_permission,
    "verify.lint":              _tool_verify_lint,
    "verify.lint_best_practice": _tool_verify_lint_best_practice,
    "verify.method_hiding":     _tool_verify_method_hiding,
    "verify.trader17":          _tool_verify_trader17,
    "verify.compile":           _tool_verify_compile,
    "verify.broker_safety":     _tool_verify_broker_safety,
    "verify.audit":             _tool_verify_audit,
    "verify.backtest":          _tool_verify_backtest,
    "verify.walkforward":       _tool_verify_walkforward,
    "verify.montecarlo":        _tool_verify_montecarlo,
    "verify.multibroker":       _tool_verify_multibroker,
    "verify.fitness":           _tool_verify_fitness,
    "verify.mfe_mae":           _tool_verify_mfe_mae,
    "verify.overfit":           _tool_verify_overfit,
    "verify.auto_fix":          _tool_verify_auto_fix,
    "review.eng":               _tool_review_eng,
    "review.cso":               _tool_review_cso,
    "review.ceo":               _tool_review_ceo,
    "review.investigate":       _tool_review_investigate,
    "rri.persona":              _tool_rri_persona,
    "dashboard.publish":        _tool_dashboard_publish,
    "forge.pr.create":          _tool_forge_pr_create,
    "discover.doctor":          _tool_discover_doctor,
    "discover.scan":            _tool_discover_scan,
    "discover.llm_context":     _tool_discover_llm_context,
    "docs.ea_render":           _tool_docs_ea_render,
}
