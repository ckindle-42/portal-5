---
id: unit-SEC_BENCH-execution-chain-features
kind: what
title: Security bench execution chain features (22 features)
sources:
- type: code
  path: portal/modules/security/core/chain.py
- type: code
  path: portal/modules/security/core/exec_chain.py
- type: code
  path: portal/modules/security/core/scoring.py
- type: code
  path: portal/modules/security/core/lab.py
- type: code
  path: portal/modules/security/core/_data.py
last_generated_commit: 65958b7ff433a91759bbe4778df434a744fa802c
claims: []
confidence: high
tags:
- bench
- features
- security
- verified-v1
created_at: 1784945192.269671
updated_at: 1784945192.269671
---

22 features of the execution chain (drawn from `exec_chain.py`, `scoring.py`, `lab.py`, and `_data.py`):

1. **Adaptive Retry** — `fallback_techniques` tried when primary fails
2. **Cross-Prompt Artifact Chaining** — `CHAIN_INHERITANCE` forwards credentials
3. **Blue Active Response** — `block_ip`, `disable_account`, `revoke_tgt`
4. **Step Dependency DAG** — topological sort via `build_step_dag()` in `lab.py`
5. **Lab Service Auto-Discovery** — 17 service probes in `_LAB_SERVICE_PROBES`, `--probe-lab`
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
22. **Linux/Web Telemetry** — `TelemetryBackend` protocol + platform telemetry contracts (`splunk`/`winevent`/`wazuh`)

## Why

The feature list is the map a reviewer uses to decide whether a behavior is already covered before adding a new flag or scorer. Every item traces to a concrete hook in the bench code — a data field, a CLI flag, or a scoring function — so "we should add X" is answerable by checking the list first. The execution chain is deliberately the thickest surface of the bench: it is where theory, real command dispatch, blue detection, and lab lifecycle all meet.
