---
id: unit-model-catalog-supergemma4-26b-uncensored-q4-k-m-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `supergemma4-26b-uncensored:Q4_K_M-ctx64k`"
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
created_at: 1784946220.6583612
updated_at: 1784946220.6583612
---
`supergemma4-26b-uncensored:Q4_K_M-ctx64k` is the context-capped derivation of the base `supergemma4-26b-uncensored:Q4_K_M`, baked with `PARAMETER num_ctx 65536`. `config/backends.yaml` lists it with `supports_tools: true` in every group (verified 2026-09-25 by a neutral native tool-call probe — 3/3 single-call, 3/3 multi-turn exec-shaped runs with no loop at purpleteam-exec's sampling; the 2026-06-27 UAT loop that set it false was measured under the old /v1 delivery at 1.0/1.0); the router reads one flag per model id, last entry wins, so a per-group split never took effect. `config/portal.yaml` pins the tag as the `model_hint` of the auto-security `redteam-deep` and `purpleteam-exec` variants, each with `context_limit: 65536`. The 64K window is therefore the standard context for the security chain, not the base tag.

## Why

The security chain runs on the capped tag. Its tool flag is `true` since the 2026-09-25 re-verification (3/3 single-call, 3/3 multi-turn exec-shaped runs, no loop). Grounding the tag to its two group entries and to the two workspace pins that consume it ties the context cap and the tool posture to the exact config lines that set them.
