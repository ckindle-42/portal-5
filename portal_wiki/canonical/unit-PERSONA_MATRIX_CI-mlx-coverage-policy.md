---
id: unit-PERSONA_MATRIX_CI-mlx-coverage-policy
kind: why
title: "PERSONA_MATRIX_CI \u2014 MLX coverage policy"
sources:
- type: design
  path: docs/PERSONA_MATRIX_CI.md
  section: MLX coverage policy
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_MATRIX_CI
created_at: 1783195000.882566
updated_at: 1783195000.882566
---


**MLX inference is retired (commit 3a0c58e).** All chat inference runs through
Ollama (:11434). The `--mlx-warmup` flag and `mlx_models:` key in `backends.yaml`
described here no longer exist — they were part of the pre-retirement MLX proxy.

CI sweeps are Ollama-only. MLX is retained only for non-chat runtimes:
speech (:8918), transcription (:8924), embeddings (:8917), and reranking (:8925).
Those runtimes are not exercised by the persona matrix driver.
