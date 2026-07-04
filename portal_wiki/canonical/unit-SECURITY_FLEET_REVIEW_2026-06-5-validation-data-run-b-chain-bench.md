---
id: unit-SECURITY_FLEET_REVIEW_2026-06-5-validation-data-run-b-chain-bench
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 5. Validation Data \u2014 Run B Chain\
  \ Bench"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: "5. Validation Data \u2014 Run B Chain Bench"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.916874
updated_at: 1783195000.916874
---


**File**: `sec_bench_20260621T143339Z.json`  
**Scenario averages** (kerberoast_to_da + asrep_to_lateral):

| Model | Unique | Acc | Depth | Avg Time | Verdict |
|---|---|---|---|---|---|
| `lfm2.5:8b` | 1.00 | 1.00 | 11.5 | 30s | **WIN** |
| `granite4.1:8b` | 1.00 | 1.00 | 8.0 | 15s | **WIN** |
| `sylink/sylink:8b` | 1.00 | 1.00 | 12.0 | 242s | **WIN** |
| `HauhauCS-Aggressive:Q4` | 0.50 | 0.50 | 6.0 | 30s | **FAIL** |

Per-scenario detail:

| Model | kerberoast_to_da | asrep_to_lateral |
|---|---|---|
| HauhauCS:Q4 | depth=12/8, 1.00, 45s WIN | depth=0/7, 0.00, 14s **STALLED** |
| lfm2.5:8b | depth=14/8, 1.00, 32s WIN | depth=9/7, 1.00, 28s WIN |
| granite4.1:8b | depth=8/8, 1.00, 15s WIN | depth=8/7, 1.00, 14s WIN |
| sylink/sylink:8b | depth=14/8, 1.00, 237s WIN | depth=10/7, 1.00, 247s WIN |

All 4 models passed audit-tools probe (emitted valid `get_current_time` tool_call).

SYLink confirms: depth 12.0 avg, 1.00/1.00 — **auto-blueteam anchor validated**.

---
