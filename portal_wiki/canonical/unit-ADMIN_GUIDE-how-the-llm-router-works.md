---
id: unit-ADMIN_GUIDE-how-the-llm-router-works
kind: why
title: "ADMIN_GUIDE \u2014 How the LLM Router Works"
sources:
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: portal/platform/inference/router/lifespan.py
- type: code
  path: .env.example
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.8151271
updated_at: 1783195000.8151271
---

Every `auto` request goes through two layers in routing.py. Layer 1 `_route_with_llm` sends the last user message to Ollama `/api/generate` with `format: _ROUTER_JSON_SCHEMA` — grammar-enforced JSON returning `{"workspace": ..., "confidence": ...}` — and accepts the result only when confidence is at least `LLM_ROUTER_CONFIDENCE_THRESHOLD`. Layer 2 `_detect_workspace` runs weighted keyword scoring over `_WORKSPACE_ROUTING` and fires on timeout, low confidence, or error. Variant recovery (`_infer_variant`) exists only on Layer 1: with the router down, a defensive intent lands on the `auto-security` base rather than `auto-security::blueteam`, a coarser but not incorrect decision. lifespan.py pre-warms the router model with `keep_alive: -1`.

## Why

The keyword scorer exists so the router model is never a hard dependency of serving — it is the guaranteed-latency path while the LLM layer buys accuracy. The variant asymmetry is a direct consequence: variant vocabulary lives in `_SECURITY_VARIANT_SIGNALS`, which Layer 2's scorer has no entry for, so an outage degrades variant precision rather than correctness.
