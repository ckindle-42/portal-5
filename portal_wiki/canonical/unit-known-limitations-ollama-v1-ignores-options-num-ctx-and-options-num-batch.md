---
id: unit-known-limitations-ollama-v1-ignores-options-num-ctx-and-options-num-batch
kind: what
title: "KNOWN_LIMITATIONS \u2014 Ollama /v1 ignores options.num_ctx and options.num_batch"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Ollama /v1 ignores options.num_ctx and options.num_batch
- type: code
  path: config/portal.yaml
- type: code
  path: portal/modules/security/core/benign_corpus_bench.py
- type: code
  path: portal/modules/security/core/corpus_replay_bench.py
- type: code
  path: portal/modules/security/tests/test_benign_corpus_bench.py
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6741362
updated_at: 1785460800
---

- **ID**: P5-OLLAMA-OPTIONS-001
- **Description**: Ollama's OpenAI-compatible `/v1/chat/completions` endpoint ignores the `options` sub-object entirely (VERIFY-1 probes, 2026-06). The pipeline still injects `options.num_ctx`, `options.num_batch`, and `options.num_predict` (the latter mapped to `max_tokens` at top level per Branch I) because a future Ollama version may honor them. Currently:
  - `context_limit` per workspace (e.g. `auto-coding: 16384`) is **not enforced** — set PARAMETER num_ctx in the model's Modelfile or OLLAMA_CONTEXT_LENGTH
  - `num_batch` injection is inert — set PARAMETER num_batch in Modelfiles for prefill tuning
  - `predict_limit` is mapped to OpenAI `max_tokens` (top-level, honored) as a workaround
- **Roadmap note:** P5-FUT: evaluate `/api/chat` as `chat_url` — it honors the Ollama-native parameter set but requires changing all payload/response shapes.
- **2026-07-30 mitigation proof**: A benign-corpus replay demonstrated the
  operational consequence on current Ollama: raw `granite4.1:30b` loaded at
  131,072 tokens and about 91 GB, while raw `granite4.1:8b` loaded at 131,072
  tokens and about 51 GB. The security evaluation workspaces now use baked
  `granite4.1:30b-ctx16k` and `granite4.1:8b-ctx8k` tags and explicit workspace
  IDs. Live pipeline route-identity probes returned those exact tags; Ollama
  reported contexts 16,384 and 8,192 respectively. This mitigates these
  operated workspaces but does not resolve the general `/v1` limitation.

---
