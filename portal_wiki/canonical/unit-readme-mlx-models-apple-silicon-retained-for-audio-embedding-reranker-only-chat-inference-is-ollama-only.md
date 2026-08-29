---
id: unit-readme-mlx-models-apple-silicon-retained-for-audio-embedding-reranker-only-chat-inference-is-ollama-only
kind: what
title: "README \u2014 MLX models (Apple Silicon, retained for audio/embedding/reranker\
  \ only \u2014 chat inference is Ollama-only)"
sources:
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: scripts/mlx-transcribe.py
- type: code
  path: scripts/embedding-server.py
- type: code
  path: .env.example
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.686982
updated_at: 1787936130.0
---

MLX survives in four non-chat runtimes, each started by its own launcher:

- **Speech:** the host-native MLX speech server on port 8918 (`scripts/mlx-speech.py`,
  started by `start-speech` in `scripts/lib/services.sh`) — Kokoro + Higgs Audio v2
  voice clone + Qwen3-TTS/ASR.
- **Transcription:** MLX Transcribe on port 8924 (`scripts/mlx-transcribe.py`) —
  Parakeet-TDT-v3 (transcript + word timestamps); `transcribe_with_speakers` adds
  Sortformer speaker diarization merged at the word level (up to 4 speakers, no HF
  token), host-native.
- **Embedding:** Harrier-0.6B on port 8917 (`scripts/embedding-server.py`, default
  `EMBEDDING_MODEL=microsoft/harrier-oss-v1-0.6b`) — the RAG/memory embedding
  endpoint (`MLX_EMBEDDING_URL` in `rag_mcp.py`).
- **Reranker:** Qwen3-Reranker-0.6B on port 8925 (`RERANKER_MODEL` in `.env.example`,
  `mlx-community/Qwen3-Reranker-0.6B-mxfp8`) for two-stage RAG.

Chat model inference runs exclusively through Ollama on port 11434 — GGUF format,
pulled via `ollama pull` and cataloged in `config/backends.yaml`. The MLX
inference proxy that previously served ports 8081/18081/18082 was retired in
commit 3a0c58e, so no MLX runtime participates in conversation routing.

## Why

Retiring the MLX proxy removed a second chat-serving stack while keeping MLX where
Ollama has no equivalent: Ollama does not host Kokoro/Qwen3 TTS, diarized
transcription, sentence embeddings or reranking. Those four runtimes stay host-native on
Apple Silicon because the MPS path is substantially faster than the equivalent
Docker images, and none of them touch the router.
