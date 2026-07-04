---
id: unit-SECURITY_BENCH_CHAIN_ANALYSIS-workspace-comparison
kind: why
title: "SECURITY_BENCH_CHAIN_ANALYSIS \u2014 Workspace Comparison"
sources:
- type: design
  path: docs/SECURITY_BENCH_CHAIN_ANALYSIS.md
  section: Workspace Comparison
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_CHAIN_ANALYSIS
created_at: 1783195000.894202
updated_at: 1783195000.894202
---


| Workspace | Theory avg | Chain avg | Best exec prompt |
|---|---|---|---|
| `auto-purpleteam-exec` | 0.921 | ~0.97 | log4shell (1.00), pth (1.00), web_shell (1.00) |
| `auto-pentest` | 0.459 | ~0.85 | linux_privesc (1.00), log4shell (1.00), kerberoast (0.97) |

Purpleteam consistently outperforms pentest on theory (ATT&CK IDs, headers) and typically on chain execution too. Exception: linux_privesc where pentest model is more tool-permissive.

---
