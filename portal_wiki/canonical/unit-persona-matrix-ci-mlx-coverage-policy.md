---
id: unit-persona-matrix-ci-mlx-coverage-policy
kind: what
title: "PERSONA_MATRIX_CI \u2014 MLX coverage policy"
sources:
- type: code
  path: portal/modules/eval/persona_matrix/cli.py
- type: code
  path: portal/modules/eval/persona_matrix/ollama_client.py
- type: code
  path: config/backends.yaml
- type: code
  path: .github/workflows/persona_matrix_nightly.yml
- type: code
  path: scripts/mlx-speech.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.568525
updated_at: 1784946220.568525
---

MLX chat inference was retired in commit `3a0c58e` (`feat: retire MLX proxy — migrate to Ollama-only inference stack`); the persona-matrix driver now talks only to Ollama at the `OLLAMA_URL` constant (`http://localhost:11434`) via `_chat_direct`, and the CLI restricts `--backend` to `ollama`. The workflow's `backend` input offers only `ollama` as a choice, so CI sweeps are Ollama-only by construction. The `--mlx-warmup` flag and a `mlx_models:` key in `backends.yaml` no longer exist anywhere in the current tree — the only `MLX_MODELS` reference left is a comment in `backends.yaml` about the embedding pull list.

MLX survives only outside chat inference as separate non-chat runtimes the matrix driver never calls: speech (`scripts/mlx-speech.py`, port 8918), diarized transcription (launch.sh, port 8924), embeddings (port 8917), and reranking (`.env.example` RERANKER, port 8925). Those runtimes are excluded from persona-matrix sweeps because `run_cell` only ever issues an OpenAI-compatible chat request to the Ollama URL; no MLX endpoint is consulted during a sweep.

## Why

This unit exists to keep a stale doc from resurrecting a retired stack: the MLX-proxy era had warmup flags and big-model handling that no longer compile against the driver's CLI. Grounding the boundary to commit `3a0c58e`, the `OLLAMA_URL` constant, and the `ollama`-only backend choice makes it checkable — if MLX ever re-enters chat inference, the cited source files change first, which is the only way this policy can stay honest.
