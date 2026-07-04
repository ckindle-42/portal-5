---
id: unit-SECURITY_BENCH_CHAIN_ANALYSIS-original-4-prompts
kind: why
title: "SECURITY_BENCH_CHAIN_ANALYSIS \u2014 Original 4 prompts"
sources:
- type: design
  path: docs/SECURITY_BENCH_CHAIN_ANALYSIS.md
  section: Original 4 prompts
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_CHAIN_ANALYSIS
created_at: 1783195000.890481
updated_at: 1783195000.890481
---


| Prompt | auto-pentest chain | auto-purpleteam-exec chain | Δ from prior best |
|---|---|---|---|
| kerberoasting | **0.97** | **0.97** | stable (was 0.37/0.97) |
| linux_privesc | **1.00** | **0.97** | purpleteam recovered from 0.52 |
| redis_to_rce | **0.93** | **0.93** | massive recovery from 0.07/0.29 |
| smb_enum_relay | 0.74 | **1.00** | purpleteam breakthrough from 0.26 |
