---
id: unit-SECURITY_FLEET_REVIEW_2026-06-context-from-candidate-eval-v1
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 Context from CANDIDATE_EVAL_V1"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: Context from CANDIDATE_EVAL_V1
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.9140549
updated_at: 1783195000.9140549
---


Key decisions already locked in before this review cycle:

- **3 Qwable-27B dense variants were removed** — all <15 TPS. Not candidates.
- **Huihui-Qwen3.6-27B dense gate failed** — pipeline TPS 12.5, below 15 TPS threshold. Chain bench skipped; model out.
- **Qwable-35B security chain = FAIL** — 0.64 coverage, below 2/2 WIN threshold. Per CANDIDATE_EVAL_V1 Step 0, this required removal. Commit `9d3a63f` promoted it instead — this review corrects that.
- **devstral-small-2**: 15.5 TPS pipeline — below 20 TPS interactive floor. Stays in coding pool per Step 3. Chain bench (Run A) informs cross-listing only.

---
