---
id: unit-HOWTO-2-chat-with-ai
kind: why
title: "HOWTO \u2014 2. Chat with AI"
sources:
- type: design
  path: docs/HOWTO.md
  section: 2. Chat with AI
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8392
updated_at: 1783195000.8392
---


**What:** Open WebUI connects to Portal Pipeline, which routes to the best model.

**How:** Open http://localhost:8080, sign in with the admin credentials from `.env`.

**Example — general chat:**
1. Select `Portal Auto Router` from the model dropdown
2. Type: `Explain how Docker networking works`
3. The pipeline routes to `dolphin-llama3:8b` via Ollama

**Verify routing:**
```bash
