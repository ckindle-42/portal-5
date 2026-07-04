---
id: unit-SECURITY_BENCH_CHAIN_ANALYSIS-new-6-prompts-first-baselines
kind: why
title: "SECURITY_BENCH_CHAIN_ANALYSIS \u2014 New 6 prompts \u2014 first baselines"
sources:
- type: design
  path: docs/SECURITY_BENCH_CHAIN_ANALYSIS.md
  section: "New 6 prompts \u2014 first baselines"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_CHAIN_ANALYSIS
created_at: 1783195000.8907142
updated_at: 1783195000.8907142
---


| Prompt | auto-pentest chain | auto-purpleteam-exec chain | Notes |
|---|---|---|---|
| pass_the_hash | 0.93 | **1.00** | strong debut |
| eternalblue_ms17010 | 0.74 | **0.97** | flags step missed |
| log4shell_rce | **1.00** | 0.97 | solid across both |
| rbcd_attack | 0.71 | 0.78 | set_rbcd step: tool mismatch (fixed) |
| bloodhound_ad_recon | 0.71 | **0.97** | shortest_path: tool mismatch (fixed) |
| web_shell_upload | 0.74 | **1.00** | purpleteam perfect |
