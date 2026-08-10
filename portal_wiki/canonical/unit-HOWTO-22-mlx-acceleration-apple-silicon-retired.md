---
id: unit-HOWTO-22-mlx-acceleration-apple-silicon-retired
kind: why
title: "HOWTO \u2014 22. MLX Acceleration (Apple Silicon) \u2014 RETIRED"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: de01e9b1e91aa629f9d80d26a890483a552e43e0
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.862881
updated_at: 1783195000.862881
---

**Retired (commit 3a0c58e).** The MLX inference proxy was removed; all chat inference now runs through Ollama (port 11434) with its native MLX Metal backend on Apple Silicon. This is a standing decision, not a gap: Ollama 0.32.4+ carries the Metal-residency fix that keeps pinned router and inference models loaded together, reaching parity with standalone `mlx_lm` throughput while removing the dual-stack operational overhead. The Ollama-only inference tier is recorded in `config/backends.yaml` (every backend is `type: ollama`) and enforced as a project rule; see the MLX notes in `KNOWN_LIMITATIONS.md`.

The MLX speech (port 8918), transcription (port 8924), embedding (port 8917), and reranker (port 8925) servers documented elsewhere in this guide are unaffected and remain in use — MLX is not gone from the project, only from chat inference. `COMPUTE_BACKEND=mps` in `.env.example` records the Apple Silicon Metal target.

## Why

Retiring the proxy kept one inference tier instead of two, which removed a whole class of admission-control and thread-patch maintenance at the cost of a hardware-accelerated fallback that no longer outperformed the native path. The distinction matters for future work: a regression in Ollama Metal performance is a reason to revisit, not evidence that the retired proxy should return, and the audio and retrieval runtimes legitimately keep using MLX.
