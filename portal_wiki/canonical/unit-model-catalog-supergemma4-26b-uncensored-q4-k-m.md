---
id: unit-model-catalog-supergemma4-26b-uncensored-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `supergemma4-26b-uncensored:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.632792
updated_at: 1784946220.632792
---
`supergemma4-26b-uncensored:Q4_K_M` is the abliterated SuperGemma4 26B A4B MoE. `config/backends.yaml` lists it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — sibling -ctx64k tag: 3/3 single-call, 3/3 multi-turn exec-shaped runs with no loop; the 2026-06-27 UAT loop that set it false was measured under the old /v1 delivery at 1.0/1.0); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` pins the derived `-ctx64k` tag on the auto-security redteam-deep and purpleteam-exec variants; `bench-supergemma4-sec` (whose `model_hint` is the base tag) records a completed 2026-06-17 bench at avg 0.783 with zero disclaimers and its promotion as auto-redteam-deep primary.

## Why

The `false` flags came from a 2026-06-27 UAT loop with tools in context, measured when Ollama's `/v1` served every seat at 1.0/1.0 with no top_k/min_p/repeat_penalty. Re-probed 2026-09-25 on the native path at the seat's sampling, it called tools cleanly and finished multi-turn exec-shaped runs in two turns, so every entry is now `true`. The bench workspace records a finished bench and a promotion; a lab UAT still has to confirm the live exec loop (`docs/TASK_SEAT_SAMPLING_AB_V1.md` B8).
