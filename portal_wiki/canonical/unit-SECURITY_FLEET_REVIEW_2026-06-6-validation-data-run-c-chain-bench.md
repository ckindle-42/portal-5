---
id: unit-SECURITY_FLEET_REVIEW_2026-06-6-validation-data-run-c-chain-bench
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 6. Validation Data \u2014 Run C Chain\
  \ Bench"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: "6. Validation Data \u2014 Run C Chain Bench"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.91714
updated_at: 1783195000.91714
---


**File**: `sec_bench_20260621T145019Z.json`  
**Model**: `supergemma4-26b-uncensored:Q4_K_M` — clean run, no VRAM contention

| Scenario | Depth | Unique | Acc | Time | Verdict |
|---|---|---|---|---|---|
| kerberoast_to_da | 10/8 | 8/8 | 1.00 | 34s | WIN |
| asrep_to_lateral | 7/7 | 7/7 | 1.00 | 37s | WIN |
| **Average** | **8.5** | **1.00** | **1.00** | **36s** | **WIN** |

Audit-tools probe passed. Fleet bench data (1.00, depth 8.0) confirmed accurate — clean run matched.

---
