---
id: unit-known-limitations-ollama-v1-ignores-options-num-ctx-and-options-num-batch
kind: what
title: "KNOWN_LIMITATIONS \u2014 Ollama /v1 ignores options.num_ctx and options.num_batch"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Ollama /v1 ignores options.num_ctx and options.num_batch
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6741362
updated_at: 1784946220.6741362
---

- **ID**: P5-OLLAMA-OPTIONS-001
- **Description**: Ollama's OpenAI-compatible `/v1/chat/completions` endpoint ignores the `options` sub-object entirely (VERIFY-1 probes, 2026-06). The pipeline still injects `options.num_ctx`, `options.num_batch`, and `options.num_predict` (the latter mapped to `max_tokens` at top level per Branch I) because a future Ollama version may honor them. Currently:
  - `context_limit` per workspace (e.g. `auto-coding: 16384`) is **not enforced** — set PARAMETER num_ctx in the model's Modelfile or OLLAMA_CONTEXT_LENGTH
  - `num_batch` injection is inert — set PARAMETER num_batch in Modelfiles for prefill tuning
  - `predict_limit` is mapped to OpenAI `max_tokens` (top-level, honored) as a workaround
- **Roadmap note:** P5-FUT: evaluate `/api/chat` as `chat_url` — it honors the Ollama-native parameter set but requires changing all payload/response shapes.

---
