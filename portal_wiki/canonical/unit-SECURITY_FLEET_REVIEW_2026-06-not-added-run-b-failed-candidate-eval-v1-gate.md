---
id: unit-SECURITY_FLEET_REVIEW_2026-06-not-added-run-b-failed-candidate-eval-v1-gate
kind: why
title: "SECURITY_FLEET_REVIEW_2026-06 \u2014 Not added \u2014 Run B failed CANDIDATE_EVAL_V1\
  \ gate"
sources:
- type: design
  path: docs/SECURITY_FLEET_REVIEW_2026-06.md
  section: "Not added \u2014 Run B failed CANDIDATE_EVAL_V1 gate"
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_FLEET_REVIEW_2026-06
created_at: 1783195000.916078
updated_at: 1783195000.916078
---


| Model | Fleet Cov | Run B Avg | Reason |
|---|---|---|---|
| `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4` | 1.00 | **0.50** | kerberoast WIN (depth=12, 45s) but STALLED on asrep_to_lateral (0/7, 14s — no tool calls emitted on first step). 0.50 < 2/2 WIN threshold. Stays in creative group; not cross-listed to security. Fleet bench 1.00 result may reflect VRAM-pressure variance across 105 models. Run B clean result is authoritative. |
