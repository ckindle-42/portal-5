---
id: unit-known-limitations-ollama-native-mlx-engine-evaluation-findings-2026-07-01
kind: what
title: "KNOWN_LIMITATIONS \u2014 Ollama Native MLX Engine \u2014 Evaluation Findings\
  \ (2026-07-01)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "Ollama Native MLX Engine \u2014 Evaluation Findings (2026-07-01)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6687732
updated_at: 1784946220.6687732
---

Ollama 0.31.1 added a built-in MLX engine (distinct from the retired standalone
`mlx_lm`/`mlx_vlm` proxy above) that claims ~90% faster Gemma 4 via multi-token
prediction (MTP). This section documents a same-day evaluation of that engine
plus a broader catalog sweep for MLX equivalents of the fleet. **No production
config was changed** — `config/backends.yaml` was reverted, all pulled MLX
models (4 Ollama-native + 16 HF-sourced, ~254GB total) were deleted, and disk
usage is back at baseline (`hf-cache` exactly 280GB, matching pre-evaluation).
