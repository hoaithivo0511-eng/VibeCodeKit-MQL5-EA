# Verify report

Status: `LOCAL_VERIFIED` for the RC7 tool distribution.

| Gate | Result | Evidence |
|---|---|---|
| JSON/YAML/workflow parse | PASS | All tracked configuration inputs parse; workflow actions use immutable commit SHAs |
| Ruff static gate | PASS | `ruff check --no-cache scripts tests` |
| Source selftest | PASS | 13/13 checks |
| Source regression | PASS | 300/300 tests, clean JUnit |
| Source ZIP regression | PASS | 300/300 tests, clean JUnit |
| Installed-wheel regression | PASS | 300/300 tests, clean JUnit outside the checkout |
| Reproducible wheel | PASS | Two clean builds with one epoch produce the same SHA-256 |
| Public generator matrix | PASS | `trend`, `grid`, `scalper`, and `session` presets build and static-check without blocker findings |
| MCP stdio protocol | PASS | Four bridges initialize, list tools, reject missing required arguments, and reject unknown tools |
| Production literal isolation | PASS | Existing semantic-isolation guard finds no CCBSN/vendor defaults in production modules |
| Native MetaEditor compile | UNTESTABLE | No trusted MetaEditor runtime is available for the final tree |
| MT5 Strategy Tester | UNTESTABLE | No trusted terminal/tester runtime is available for the final tree |

Therefore `compile_verified=false`, `tester_verified=false`, and
`release_eligible=false`. The generated wheel and source ZIP are ready for tool
installation and evaluation, but this report does not assert live-trading or EA
release eligibility.
