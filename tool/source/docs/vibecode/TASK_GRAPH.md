# Task graph — RC7 release hardening

| ID | Dependency | Deliverable | Exit gate |
|---|---|---|---|
| T1 | baseline | Metadata parity | Source selftest 13/13 |
| T2 | T1 | Include-aware analyzer | Focused analyzer + public preset tests |
| T3 | T2 | Hermetic cache policy | Snapshot negative/positive tests |
| T4 | T1 | Runtime/MCP fixes | Type-hint + four-server protocol tests |
| T5 | T1–T4 | Docs and derived metadata | Docs truth + manifest checks |
| T6 | T5 | Source/ZIP/wheel artifacts | Full clean JUnit and selftests |
| T7 | T6 | Evidence/retro handoff | Honest final release state |
