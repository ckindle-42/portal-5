---
id: SEC_BENCH-agentic-blue-winning-20260706
kind: what
title: 'Agentic Blue Winning Config: granite4.1:8b-ctx8k (raw)'
sources:
- type: bench-security
  path: /tmp/agentic_blue_sweep.json
last_generated_commit: ''
confidence: high
tags:
- agentic-blue
- maturation
- winning-config
- granite4.1-8b-ctx8k
- raw
created_at: 1783347779.178504
updated_at: 1783347779.178504
---

# Agentic Blue Eval — Winning Configuration

**Model:** `granite4.1:8b-ctx8k`  
**Arm:** raw  
**Trials per cell:** 3  
**Scenarios:** asrep_to_lateral, kerberoast_to_da, meta3_ftp_backdoor  
**Sweep date:** 2026-07-06 14:22 UTC

## Tiered Recall Summary

| Tier | Mean Recall | Pass@3 | Classification |
|------|------------|---------|----------------|
| exact | 0.222 | 2/3 | unreliable |
| parent | 0.333 | 3/3 | reliable |
| tactic | 0.333 | 3/3 | reliable |

## Per-Scenario Results (winning model: granite4.1:8b-ctx8k)

- **kerberoast_to_da**: exact=0.222 parent=0.333 tactic=0.333
- **asrep_to_lateral**: exact=0.000 parent=0.111 tactic=0.222
- **meta3_ftp_backdoor**: exact=0.167 parent=0.167 tactic=0.167
