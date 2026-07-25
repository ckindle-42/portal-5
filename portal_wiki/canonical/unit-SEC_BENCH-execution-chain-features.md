---
id: unit-SEC_BENCH-execution-chain-features
kind: what
title: Security bench execution chain features (22 features)
sources:
- type: doc
  path: docs/SECURITY_BENCH_EXEC.md
  commit: ddb1cc61
- type: code
  path: portal/modules/security/core/chain.py
  commit: ddb1cc61
- type: code
  path: portal/modules/security/core/scoring.py
  commit: ddb1cc61
last_generated_commit: ddb1cc61
confidence: high
tags:
- security
- bench
- features
created_at: 1784945192.269671
updated_at: 1784945192.269671
---

22 features of the execution chain:

1. **Adaptive Retry** — `fallback_techniques` tried when primary fails
2. **Cross-Prompt Artifact Chaining** — `CHAIN_INHERITANCE` forwards credentials
3. **Blue Active Response** — `block_ip`, `disable_account`, `revoke_tgt`
4. **Step Dependency DAG** — topological sort via `_build_step_dag()`
5. **Lab Service Auto-Discovery** — 19 service probes, `--probe-lab`
6. **Stealth Scoring** — Windows Event Log queries, `stealth_event_ids`
7. **Proxmox VM Snapshot/Restore** — `--lab-snapshot`
8. **Per-Step Time Budgets** — `time_budget_s`, `speed_score`
9. **Conditional Branching** — `condition` field evaluated against observations
10. **Dynamic CVE Research** — `--dynamic-cve`, model must `web_search` CVE
11. **Sequence Adherence** — LIS of matched tool call indices
12. **Success Gating** — `success_indicators` required for 'proven' status
13. **False Positive Testing** — `--false-positive-test`
14. **Defense Efficacy Testing** — `--defense-efficacy`
15. **Detection Latency** — `detection_latency_s` in blue turn results
16. **Defense Verification** — `verify_defense` probes target after blue action
17. **Rescore** — `--rescore FILE` re-derives metrics without re-executing
18. **Retry Failed** — `--retry-failed FILE`, `--retry-prompts PROMPT`
19. **Full Output Capture** — `tool_calls`, `lab_outputs`, `lab_observations`
20. **Proven Scoring** — `proven_coverage` in lab-exec mode
21. **Library x Container Matrix** — `--matrix` / `--matrix-all`
22. **Linux/Web Telemetry** — `TelemetryBackend` protocol, Wazuh adapter
