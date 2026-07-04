---
id: unit-claude-8-single-inference-tier-ollama
kind: why
title: "CLAUDE.md \u2014 8 \u2014 Single Inference Tier: Ollama"
sources:
- type: design
  path: CLAUDE.md
  section: "8 \u2014 Single Inference Tier: Ollama"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.808287
updated_at: 1783195000.808287
---


Portal 5 runs one inference backend: **Ollama** (port 11434, Ollama 0.30.7+ with native MLX Metal backend on Apple Silicon). GGUF models, pulled via `ollama pull` or `hf.co/`, registered in `config/backends.yaml` under backend groups (general / coding / security / reasoning / vision / creative).

The MLX inference proxy (formerly :8081/:18081/:18082) was retired in commit `3a0c58e` — Ollama's MLX Metal backend reaches parity on this hardware without the thread-patch maintenance, admission-control complexity, and dual-stack overhead.

**MLX is NOT gone from the project — only from chat inference.** It still serves: speech/TTS+ASR (`scripts/mlx-speech.py`, :8918), diarized transcription (`scripts/mlx-transcribe.py`, :8924), embeddings (:8917), and the RAG reranker (:8925, `mlx-community/Qwen3-Reranker-0.6B-mxfp8`). Do not remove those when "cleaning up MLX."

Never add `transformers` or `torch` to `portal_pipeline/` — it runs lean. Full model catalog with memory budgets is in `config/backends.yaml`.
