---
id: unit-p5-roadmap-speculative-decoding-mtp-retired-commit-3a0c58e
kind: what
title: "P5_ROADMAP \u2014 Speculative Decoding / MTP \u2014 RETIRED (commit 3a0c58e)"
sources:
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py
- type: code
  path: scripts/_archive/mlx-retired-3a0c58e/README.md
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.589885
updated_at: 1784946220.589885
---

Speculative decoding and MTP support lived in the retired MLX proxy and are not
part of the current serving stack. The archived
`scripts/_archive/mlx-retired-3a0c58e/mlx-proxy.py` reads the draft-model map
(`speculative_decoding.draft_models` in `config/backends.yaml`) into
`DRAFT_MODEL_MAP` and passes `--draft-model` when the draft for a target model is
present locally; that surface was deleted with the proxy at commit 3a0c58e. The
archive README confirms the scripts are not runnable at HEAD and that any future
speculation work targets Ollama's native path rather than MLX — the archive exists
as reference for the admission-control pattern and the draft-model mapping.

## Why

The MLX-proxy speculative-decoding and MTP unblock paths were removed with the
proxy because Ollama's native MLX Metal backend reached throughput parity without
the dual-stack admission and thread-patch complexity. The archived implementation
is intentionally retained as reference but is not runnable at HEAD, so this unit
records the removal and the surviving reference rather than describing a live
feature.
