---
id: unit-p5-roadmap-p5-fut-006-llm-based-intent-routing
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-006: LLM-Based Intent Routing"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: 'P5-FUT-006: LLM-Based Intent Routing'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.591037
updated_at: 1784946220.591037
---

IMPLEMENTED in v6.0.0 (`portal_pipeline/router_pipe.py`). `_route_with_llm()` uses
`hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` as a semantic intent classifier, replacing keyword-based
workspace detection for the primary routing path.

**What was built:**
- `_route_with_llm()` in `router_pipe.py` — Ollama grammar-enforced JSON output (guaranteed valid workspace ID + confidence)
- `temperature: 0`, `num_predict: 20`, `num_ctx: 512` — deterministic, fast; `keep_alive: "-1"` keeps model loaded
- Falls back to `_detect_workspace()` on `confidence < 0.5` or timeout
- `config/routing_descriptions.json` — operator-editable workspace capability descriptions
- `config/routing_examples.json` — 25 few-shot routing examples (operator-editable)
- 16 unit tests in `tests/unit/test_routing.py` (mocked Ollama)

**Configuration (`.env`):**
```
LLM_ROUTER_ENABLED=true
LLM_ROUTER_MODEL=hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF
LLM_ROUTER_CONFIDENCE_THRESHOLD=0.5
LLM_ROUTER_TIMEOUT_MS=500
LLM_ROUTER_OLLAMA_URL=http://localhost:11434
```
