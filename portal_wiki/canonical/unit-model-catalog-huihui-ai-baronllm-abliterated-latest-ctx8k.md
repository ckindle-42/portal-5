---
id: unit-model-catalog-huihui-ai-baronllm-abliterated-latest-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/baronllm-abliterated:latest-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: a23f47b3e687df1693600eeea5b4f3f381b9da20
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.652317
updated_at: 1784946220.652317
---

`huihui_ai/baronllm-abliterated:latest-ctx8k` is the 8K-context derived tag of the BaronLLM abliterated fork, and it is the id `config/portal.yaml` routes through the `auto-security` uncensored variant's `model_hint`. `config/backends.yaml` registers it under both the `security` and `creative` groups with `supports_tools: true`. The `PARAMETER num_ctx 8192` is baked into the tag because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so the per-workspace context cap is a distinct model id. Full model detail lives in the base `huihui_ai/baronllm-abliterated` entry; this tag exists to satisfy registry parity and the uncensored security lane's context limit.

## Why

The routing fact is decisive: `config/portal.yaml` resolves the `auto-security` uncensored variant to this exact `-ctx8k` tag, while `config/backends.yaml` fixes its `security`/`creative` placement with `supports_tools: true`. The num_ctx mechanism is preserved because it explains why a derived tag was minted — a context cap that cannot be passed at request time has to be encoded in the model id.
