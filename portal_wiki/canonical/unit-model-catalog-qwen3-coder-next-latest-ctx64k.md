---
id: unit-model-catalog-qwen3-coder-next-latest-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `qwen3-coder-next:latest-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 50b73876729db7181402fcbcc48400caa1ba1e40
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.656608
updated_at: 1784946220.656608
---

`qwen3-coder-next:latest-ctx64k` is the derived tag that bakes `PARAMETER num_ctx 65536` into `qwen3-coder-next:latest` via the `apply-params` command in `portal/platform/inference/cli/models.py`. `config/backends.yaml` registers it in `group: coding` (`ollama-coding`) with `supports_tools: true`. `config/portal.yaml` pins it as the `model_hint` of the heavy auto-coding variant with `context_limit: 65536`, so every long-horizon agentic session runs against the capped tag. The derivation exists because the pipeline talks to Ollama's `/v1/chat/completions`, which ignores request-time `options.num_ctx`; the cap must be baked into the model at creation, not requested per call. See the base tag's unit for architecture and benchmark context.

## Why

The heavy auto-coding variant is the only production workspace that references this tag, and its `context_limit` must match the baked `PARAMETER num_ctx` exactly or the KV-cache reservation silently widens past the workspace's declared intent. Grounding the tag in `apply-params` and the workspace pin makes the derivation mechanism traceable to the code that creates it and to the config that consumes it.
