---
id: unit-ADMIN_GUIDE-pull-router-model-if-not-yet-downloaded
kind: why
title: "ADMIN_GUIDE \u2014 Pull router model if not yet downloaded"
sources:
- type: code
  path: .env.example
- type: code
  path: portal/platform/inference/cli/models.py
- type: code
  path: portal/platform/inference/cli/_common.py
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.817791
updated_at: 1783195000.817791
---

The router model is an Ollama-native HuggingFace pull. The recommended path is `./launch.sh pull-models`, which runs `models_pull` in `portal/platform/inference/cli/models.py` and pulls the whole catalog via `_pull_native`; the CLI locates the `ollama` binary through `_detect_ollama_cmd` in cli/_common.py. A lone model can be pulled directly:

```bash
ollama pull hf.co/mradermacher/gemma-4-E4B-it-OBLITERATED-GGUF:Q4_K_M
```

That is the value of `LLM_ROUTER_MODEL` in `.env.example`. Until it is present, the first `auto` request after startup cold-loads it and Layer 2 keyword scoring covers the interim.

## Why

A missing router model is a warm-up cost, not an outage — the pipeline degrades to keyword scoring rather than failing, so a fresh install still serves. Pulling through the CLI matters because it keeps the installed set in sync with the catalog, so the router model and the workspace pool are provisioned together rather than piecemeal.
