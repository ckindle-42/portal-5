---
id: unit-readme-architecture
kind: what
title: "README \u2014 Architecture"
sources:
- type: doc
  path: README.md
  commit: 05e42ec2
  section: Architecture
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6922922
updated_at: 1784946220.6922922
---

```
┌──────────────┐
│  Open WebUI  │
│    :8080     │
└──────┬───────┘
                │
                     ┌────────────▼───────────────────┐
                     │    Portal Pipeline :9099         │
                     │  (routing, auth, metrics, MCP)  │
                     └──┬───┬───┬───┬─────────────────┘
                        │   │   │   │
           ┌────────────┘   │   │   └─────────────┐
           │                │   │                 │
    ┌──────▼──────┐  ┌──────▼──┐  ┌──────────────────▼──┐
    │  Ollama      │  │ Ollama  │  │  MCP Servers          │
    │  :11434      │  │ :11434  │  │  :8910–8916 (tools)   │
    │  (LLMs)      │  │ (LLMs)  │  │  :8917 (embedding)    │
    └─────────────┘  └─────────┘  │  :8918 (speech)       │
                                  │  :8924 (transcribe)   │
    Ollama is the single          │  :8925 (reranker)     │
    inference tier (:11434).      └─────────────────────┘
    MLX speech/transcription/
    embedding/reranker are
    retained for non-chat use.

    Telegram Bot ──► Portal Pipeline    Slack Bot ──► Portal Pipeline
    (profile: telegram)                 (profile: slack)

    Grafana :3000 ◄── Prometheus :9090 ◄── /metrics
```

All chat inference runs through Ollama (:11434) with its native MLX Metal backend on
Apple Silicon. The MLX inference proxy (:8081/:18081/:18082) was retired in commit 3a0c58e.
MLX is retained for speech (:8918), transcription (:8924), embeddings (:8917),
and reranking (:8925) — non-chat-inference runtimes only.

---
