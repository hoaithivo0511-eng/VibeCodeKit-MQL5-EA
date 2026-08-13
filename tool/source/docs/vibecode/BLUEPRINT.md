# Blueprint — RC7 release hardening

1. Establish one include-closure resolver in `ea_doc_analyzer`.
2. Reuse that resolver in `check_all`, `ea_senior_review` and `deep_review` so
   lint, strategy detection, graphs and issue counts share one source set.
3. Keep `read_mql_files` unchanged for documentation/inventory consumers that
   intentionally need every local source.
4. Make snapshot verification ignore only named cache directory segments.
5. Enforce MCP required arguments at the dispatcher boundary for all bridges.
6. Stabilize Ruff policy explicitly, repair true F-class defects, and run it
   without writing cache into shipped data.
7. Synchronize derived metadata and the installed-wheel verification snapshot
   before building deterministic artifacts.
8. Keep native release evidence external and exact-tree-bound.
