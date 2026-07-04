---
id: unit-SECURITY_BENCH_CHAIN_ANALYSIS-log4shell-rce-strong-both-workspaces
kind: why
title: "SECURITY_BENCH_CHAIN_ANALYSIS \u2014 log4shell_rce \u2014 STRONG both workspaces"
sources:
- type: design
  path: docs/SECURITY_BENCH_CHAIN_ANALYSIS.md
  section: "log4shell_rce \u2014 STRONG both workspaces"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_CHAIN_ANALYSIS
created_at: 1783195000.892938
updated_at: 1783195000.892938
---


**Steps**: `detect → server → payload → rce_confirm`

Pentest 1.00: VulnLLM covers detect (curl jndi payload); Qwable covers server (marshalsec LDAPRefServer in R2 after retry); BaronLLM... partially misses payload but rce_confirm covered.

Purpleteam 0.97: Same — payload step slightly inconsistent (BaronLLM does web_search for jndi referral server), but detect/server/rce_confirm all covered.

---
