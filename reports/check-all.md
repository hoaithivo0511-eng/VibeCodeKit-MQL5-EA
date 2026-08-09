# vkmql-check all — RELEASE GATE

- Project: `/mnt/data/vkmql_v330rc4_final/demo/CCBSN_GoldenFixture`
- Release eligible: **False**

| Stage | Status | Detail |
|---|---|---|
| scan | PASS | 1 EA file(s), 4 behaviour(s), no high-risk smells |
| contract | PASS | contracts intact |
| lint | SKIPPED | not run in this environment |
| compile | UNTESTABLE | requires a real MT5/Wine environment |
| backtest | UNTESTABLE | requires a real MT5/Wine environment |
| quality | UNTESTABLE | no evidence/backtest/report.xml to grade |
| forward | UNTESTABLE | no evidence/walkforward/{is,oos}_report.xml present |
| stress | UNTESTABLE | 8 scenario(s) need a real tester |
| review | SKIPPED | not run in this environment |
| retro | UNTESTABLE | missing evidence/retro/guards.yaml |
| approval | SKIPPED | not required for target=draft |
| evidence | FAIL | manifest release_eligible is not true; manifest summary.release_eligible is not true; compile source is not trusted for release; backtest source is not trusted for release |
| release-policy | PASS | policy evaluated |

> UNTESTABLE stages (compile/backtest/stress without a real MT5 run)
> block release-eligibility. No evidence = no release.
