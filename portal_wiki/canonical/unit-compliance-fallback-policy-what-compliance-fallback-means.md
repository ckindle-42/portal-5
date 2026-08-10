---
id: unit-compliance-fallback-policy-what-compliance-fallback-means
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 What \"compliance fallback\" means"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
- type: code
  path: portal/platform/inference/router/handlers.py
- type: code
  path: portal/platform/inference/router/preinject.py
- type: code
  path: portal/platform/inference/cluster_backends.py
last_generated_commit: 3cdc95603cf1faa41ddd64aa3eaad1ec45a113ce
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5637708
updated_at: 1784946220.5637708
---

Compliance fallback means the `auto-compliance` workspace's routing chain in `config/backends.yaml`: `workspace_routing` routes the workspace through the reasoning group and then the general group, in that priority order. `config/portal.yaml` sets the workspace `model_hint` to `granite4.1:8b-ctx16k`, the 16K-context derived tag of Granite 4.1 8B, which is registered in both the reasoning and general groups with `supports_tools: true`. In the request path, `_prioritize_hinted_backend` moves the backend able to serve the hint to the front of the candidates; if the hint cannot be resolved, the handler falls back to that backend's first model and records the event on the `_hint_fallback_total` metric. The candidate set is ordered by `workspace_routing` group priority, and `get_backend_candidates` appends the `fallback_group` and any remaining healthy backends as degrade-don't-fail tiers, so any Ollama model in `ollama-reasoning` or `ollama-general` can become the served handler when the hint is unavailable. The former MLX proxy priority, a chain that began with an mlx group, was retired in commit 3a0c58e and no mlx entry remains in the chain.

## Why

The source document named the primary hint `granite4.1:8b`, but the live workspace config selects the context-capped `granite4.1:8b-ctx16k` tag, and the "falls through" behavior lives in the request handler, not in policy prose. Re-grounding fixes the tag and pins the fallback to its actual mechanism — hint prioritization, first-model fallback and the metric that counts it — so the claim is testable against the router code rather than trusted from a sentence.
