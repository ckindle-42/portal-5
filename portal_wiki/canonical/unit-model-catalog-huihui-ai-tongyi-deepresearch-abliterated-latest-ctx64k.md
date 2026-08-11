---
id: unit-model-catalog-huihui-ai-tongyi-deepresearch-abliterated-latest-ctx64k
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: d19bcd41d50c690918807eab095f1f738f9798d5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.654283
updated_at: 1784946220.654283
---

`huihui_ai/tongyi-deepresearch-abliterated:latest-ctx64k` is the 64K-context derived tag of the deepresearch abliterated model, and it is the id `config/portal.yaml` serves through the `auto-research` workspace `model_hint` with a 65536 context limit. `config/backends.yaml` registers it under the `reasoning` group with `supports_tools: true`. The `PARAMETER num_ctx 65536` is baked into the tag because Ollama's `/v1/chat/completions` ignores request-time `options.num_ctx`, so the research lane's long context window is a distinct model id. Full model detail lives in the base `huihui_ai/tongyi-deepresearch-abliterated` entry; this tag exists to give web research the context it needs.

## Why

The `auto-research` routing in `config/portal.yaml` is the decisive binding — the base id has no workspace of its own, so this derived tag is what actually serves research traffic — and `config/backends.yaml` confirms the `reasoning` group and `supports_tools: true`. The num_ctx mechanism is preserved because it explains why the derived tag exists: a long context window that cannot be passed at request time must be a separate model id.
