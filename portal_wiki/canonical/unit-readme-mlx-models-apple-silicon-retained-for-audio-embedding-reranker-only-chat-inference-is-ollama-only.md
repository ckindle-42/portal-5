---
id: unit-readme-mlx-models-apple-silicon-retained-for-audio-embedding-reranker-only-chat-inference-is-ollama-only
kind: what
title: "README \u2014 MLX models (Apple Silicon, retained for audio/embedding/reranker\
  \ only \u2014 chat inference is Ollama-only)"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: "MLX models (Apple Silicon, retained for audio/embedding/reranker only\
    \ \u2014 chat inference is Ollama-only)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.686982
updated_at: 1784946220.686982
---

- **Speech:** MLX speech server (:8918) — Kokoro + Qwen3-TTS/ASR, host-native
- **Transcription:** MLX Transcribe (:8924) — mlx-whisper + pyannote diarization, host-native
- **Embedding:** Harrier-0.6B TEI (:8917)
- **Reranker:** Qwen3-Reranker-0.6B-mxfp8 (:8925)
- Chat model inference runs exclusively through Ollama (:11434) — GGUF format, pulled via `ollama pull`

The MLX inference proxy (:8081/:18081/:18082) was retired in commit 3a0c58e.
