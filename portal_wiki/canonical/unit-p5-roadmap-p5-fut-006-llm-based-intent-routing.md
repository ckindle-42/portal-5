---
id: unit-p5-roadmap-p5-fut-006-llm-based-intent-routing
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-006: LLM-Based Intent Routing"
sources:
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: .env.example
- type: code
  path: config/routing_descriptions.json
- type: code
  path: config/routing_examples.json
- type: code
  path: tests/unit/test_routing.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.591037
updated_at: 1784946220.591037
---

P5-FUT-006 is implemented as Layer 1 of auto-routing. `_route_with_llm()`
(`portal/platform/inference/router/routing.py`) calls the Ollama `/api/generate`
endpoint with `format: _ROUTER_JSON_SCHEMA`, grammar-enforced JSON that can only
emit a valid workspace id plus a confidence score. The request uses
`temperature: 0`, `num_predict: 40`, `num_ctx: 2048`, and `keep_alive: -1` so
the classifier is deterministic and stays resident. It returns `None` on low
confidence (below `_LLM_ROUTER_CONFIDENCE_THRESHOLD`, default 0.5), on timeout
(`_LLM_ROUTER_TIMEOUT_MS`, default 1000), on `LLM_ROUTER_ENABLED=false`, and on
any parse or HTTP error — the caller then falls back to `_detect_workspace()`,
the weighted keyword scorer. `bench-*` workspaces are excluded from
`_VALID_WORKSPACE_IDS`. The model is chosen by `LLM_ROUTER_MODEL` (default
`hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M`); all five env vars
are in `.env.example`. Operator-editable inputs are
`config/routing_descriptions.json` (workspace capability descriptions) and
`config/routing_examples.json` (44 few-shot examples under its `examples` key).
The router behavior is covered by 32 test functions in
`tests/unit/test_routing.py`.

## Why

Layer 1 exists because keyword scoring alone cannot reliably separate the more
similar workspaces in the fleet; grammar-enforced JSON guarantees the model
answer is structurally valid, and the hard 1000ms timeout plus `keep_alive: -1`
turn the classifier into a cheap, always-warm first opinion. Routing is
non-fatal by design — every failure mode degrades to the deterministic keyword
scorer rather than erroring the request.
