---
id: unit-claude-what-portal-5-is
kind: why
title: "CLAUDE.md \u2014 What Portal 5 Is"
sources:
- type: design
  path: CLAUDE.md
  section: What Portal 5 Is
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.805106
updated_at: 1783195000.805106
---


Portal 5 is an **Open WebUI enhancement layer** — not a replacement web stack. It extends Open WebUI through its Pipeline server (:9099) and MCP Tool Servers. Result: local AI platform for text, code, security, images, video, music, documents, voice — all on your hardware, one interface.

**Architecture**: Open WebUI → Portal Pipeline (:9099) → Ollama (:11434) → local models. MCP servers (:8910–8928) provide tools (documents, code sandbox, TTS, research, memory, RAG, browser, proxmox, pipeline introspection).

**Inference**: Single tier — **Ollama** (GGUF models, Ollama 0.30.7+ with native MLX Metal backend on Apple Silicon). The MLX inference proxy was retired in commit 3a0c58e; Ollama now matches or beats standalone mlx_lm throughput while removing the dual-stack operational overhead. Host-native, not Docker. NOTE: MLX is still used outside inference — for speech (mlx-speech :8918), diarized transcription (mlx-transcribe :8924), embeddings (:8917), and reranking (:8925). Those are audio/retrieval runtimes, not the chat inference tier.

**Core values**: Privacy-first, fully local, zero cloud dependencies, launch in one command.

---
