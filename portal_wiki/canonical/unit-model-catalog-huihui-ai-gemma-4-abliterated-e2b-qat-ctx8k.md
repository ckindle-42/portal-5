---
id: unit-model-catalog-huihui-ai-gemma-4-abliterated-e2b-qat-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.652983
updated_at: 1784946220.652983
---

`huihui_ai/gemma-4-abliterated:E2b-qat-ctx8k` is the 8K-context derived tag of the Gemma4-E2B QAT abliterated security model, registered in `config/backends.yaml` under the `security` group with `supports_tools: true`. The `PARAMETER num_ctx 8192` is baked into the tag because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, making a per-workspace context cap a distinct model id. It has no standalone `config/portal.yaml` workspace binding of its own; its base `E2b-qat` tag carries the `bench-e2b-pentest` and `bench-exec-reasoning` roles. Full model detail lives in the base tag's entry; this tag exists to satisfy registry parity and to provide a capped variant.

## Why

The `security`-group placement with `supports_tools: true` is asserted directly by `config/backends.yaml`, and the absence of an independent `config/portal.yaml` binding is itself the fact to record — the derived tag is a parity entry, not a routed workspace model. The num_ctx mechanism is preserved because it explains why the tag was created: a context limit that cannot be passed at request time must be a separate model id.
