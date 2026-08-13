---
id: unit-HOWTO-14-document-rag-knowledge-base
kind: why
title: "HOWTO \u2014 14. Document RAG (Knowledge Base)"
sources:
- type: code
  path: portal/platform/inference/router/context_inject.py
- type: code
  path: config/portal.yaml
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.8519108
updated_at: 1783195000.8519108
---

**What:** Upload documents in Open WebUI and have conversations grounded in their content.

**How:** Two layers provide this. Open WebUI owns the knowledge base itself — chat uploads become a searchable collection through its native RAG, which is out of Portal 5's scope by design. On the pipeline side, workspaces with `auto_rag: true` in `config/portal.yaml` (e.g. `auto-daily`) get automatic knowledge-base context: before answering, the router dispatches a `kb_search` against the `portal-rag` MCP (port 8921) and injects the top snippets into the prompt (`inject_retrieved_context` in `portal/platform/inference/router/context_inject.py`). Workspaces can also grant the explicit `kb_search` / `kb_list` tools for the model to call on demand.

## Why

Document grounding is deliberately split: Open WebUI keeps the uploaded corpus and search index — the durable knowledge store — while the pipeline only reads it at request time through tool dispatch. That separation means a knowledge base works without Portal touching Open WebUI internals, and auto-injection is an opt-in workspace flag so RAG latency only affects lanes that opt into it.
