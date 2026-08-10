---
id: unit-model-catalog-hf-co-unsloth-qwen-agentworld-35b-a3b-gguf-ud-q4-k-xl-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: de01e9b1e91aa629f9d80d26a890483a552e43e0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.651444
updated_at: 1784946220.651444
---

`hf.co/unsloth/Qwen-AgentWorld-35B-A3B-GGUF:UD-Q4_K_XL-ctx64k` is the 64K-context derived tag of the AgentWorld world model, and it is the id `config/portal.yaml` actually serves: the `auto-agentic` lite variant carries it as its `model_hint` with a 65536 context limit for tool-calling, MCP, SWE, and env-simulation work where the full 80B model is unnecessary. `config/backends.yaml` registers it under both `general` and `coding` with `supports_tools: true`, matching the base tag. The `PARAMETER num_ctx 65536` is baked in because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`. Full model detail lives in the base tag's entry.

## Why

The distinguishing fact is routing: `config/portal.yaml` resolves the `auto-agentic` lite variant to this exact `-ctx64k` tag, not the base id, and `config/backends.yaml` confirms the dual-group `supports_tools: true`. The num_ctx mechanism is preserved because the long context window is the reason this derived tag was created, and it can only be encoded in the model id.
