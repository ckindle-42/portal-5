---
id: unit-known-limitations-mlx-inference-proxy-retired-commit-3a0c58e
kind: what
title: "KNOWN_LIMITATIONS \u2014 MLX Inference Proxy \u2014 RETIRED (commit 3a0c58e)"
sources:
- type: code
  path: CLAUDE.md
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: scripts/mlx-transcribe.py
last_generated_commit: c8d9c608602960d39caf3566f78450bbd9ff0eff
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.667773
updated_at: 1784946220.667773
---

The MLX inference proxy (formerly ports 8081/18081/18082) was retired in commit `3a0c58e`, and all its limitations (single-model eviction, cold-boot 503 windows, admission control, deploy staleness) no longer apply. All chat inference runs through Ollama on port 11434, which reaches parity with standalone `mlx_lm` on this hardware without the dual-stack overhead. MLX is retained only outside chat inference: speech (`scripts/mlx-speech.py`, :8918), diarized transcription (`scripts/mlx-transcribe.py`, :8924), embeddings (:8917), and the RAG reranker (:8925). Do not remove those when "cleaning up MLX".

## Why

Retiring the proxy deleted an entire failure surface at once, so the residual limitations are intentionally only the audio and retrieval runtimes that legitimately use MLX today. Recording the retirement with the surviving MLX surfaces prevents a future cleanup pass from mistaking those four services for the retired inference tier and deleting them along with the dead stack.
