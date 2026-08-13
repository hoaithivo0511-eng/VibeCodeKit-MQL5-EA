# RRI — RC7 release hardening

## Resolved high-impact questions

- Scope approval: the owner requested all remediation items from the RC7 deep
  audit.
- Release truth: no native or tester PASS may be inferred from Python tests.
- Compatibility: preserve the five-command public surface and 139-entry tool
  catalog.
- Genericity: CCBSN remains only a golden acceptance fixture.
- Analyzer behavior: project-level findings must be based on MQL sources
  reachable from actual `.mq5` entrypoints; explicit single-file review remains
  single-file.
- Cache policy: known tool caches are runtime residue, not distribution input;
  arbitrary undeclared files remain integrity failures.

## Independent acceptance oracles

- Source metadata parity is checked by parsing every shipped
  `agent-contract.json`, not by trusting the generator exit code.
- Include reachability is tested with a clean reachable header and an unsafe
  unreachable header; only the reachable closure may affect the verdict.
- Snapshot isolation is tested by creating cache files and a non-cache rogue
  file; caches are ignored and the rogue file is rejected.
- MCP validation is checked directly against every server's declared
  `inputSchema.required` list.
- Release truth is checked by requiring `release_eligible=false` without native
  compile and Strategy Tester provenance.
