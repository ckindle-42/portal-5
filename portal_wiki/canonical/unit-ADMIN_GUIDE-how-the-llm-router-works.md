---
id: unit-ADMIN_GUIDE-how-the-llm-router-works
kind: why
title: "ADMIN_GUIDE \u2014 How the LLM Router Works"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: How the LLM Router Works
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.8151271
updated_at: 1783195000.8151271
---


The pipeline routes every `auto` workspace request through a **two-layer intent classifier**:

- **Layer 1 — LLM router** (`portal_pipeline/router/routing.py`): A small model classifies intent via Ollama `/api/generate` with grammar-enforced JSON output. Result: `{"workspace": "<id>", "confidence": 0.0–1.0}`. Fast, accurate.
- **Layer 2 — Keyword scoring** (`portal_pipeline/router/routing.py`): Weighted keyword match. Fires when LLM router times out, returns low confidence, or errors.
