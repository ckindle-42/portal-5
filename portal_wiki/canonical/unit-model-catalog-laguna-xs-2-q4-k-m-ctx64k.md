---
id: unit-model-catalog-laguna-xs-2-q4-k-m-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `laguna-xs.2:Q4_K_M-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 3cdc95603cf1faa41ddd64aa3eaad1ec45a113ce
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.654656
updated_at: 1784946220.654656
---

`laguna-xs.2:Q4_K_M-ctx64k` is the derived tag of `laguna-xs.2:Q4_K_M` with `PARAMETER num_ctx 65536` baked in via the `apply-params` command in `portal/platform/inference/cli/models.py`, because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`. `config/backends.yaml` registers it only in `group: coding` with `supports_tools: true`; the `omlx-coding` `aliases` block additionally maps it to the oMLX `Laguna-XS.2-4bit` model. `config/portal.yaml` sets it as the auto-coding laguna variant `model_hint` with `context_limit: 65536`, so the agentic lane runs on the capped tag. See the base tag's unit for model detail.

## Why

The ctx64k variant exists because the completion endpoint discards per-request context options, so a workspace-level context bound has to be baked into a dedicated id. Grounding to the coding-group registration, the omlx alias, and the auto-coding laguna variant's context_limit makes the cap's mechanism and its consumer traceable to config rather than to template prose.
