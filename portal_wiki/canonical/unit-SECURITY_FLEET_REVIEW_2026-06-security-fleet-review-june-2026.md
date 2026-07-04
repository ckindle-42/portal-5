---
id: unit-SECURITY_FLEET_REVIEW_2026-06-security-fleet-review-june-2026
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 Security Fleet Review \u2014 June 2026"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: "Security Fleet Review \u2014 June 2026"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.913676
updated_at: 1783195000.913676
---


**Date**: 2026-06-21  
**Bench data**: `sec_bench_20260620T153821Z.json` (105 models, full fleet)  
**TPS data**: `bench_tps_20260621T030634Z.json` (286 results)  
**Completion bench A**: `sec_bench_20260621T132602Z.json` (Run A — baronllm-abl, Foundation-Sec, devstral-small-2)  
**Completion bench B**: `sec_bench_20260621T143339Z.json` (Run B — HauhauCS, lfm2.5, granite4.1, sylink)  
**Quality eval**: `config/promptfoo/security_quality.yaml` Run 3 (baronllm 4/4, redteam 4/4, pentest 4/4, blueteam 4/4, vulnllm 3/4 — 19/20 overall)  
**Prior plan**: `tests/PORTAL5_CANDIDATE_EVAL_V1.md` — covers prior removal decisions; read before changing workspace counts  
**Status**: COMPLETE — all validation data in. Config changes committed.

---
