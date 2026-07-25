---
id: unit-known-limitations-mlx-inference-proxy-retired-commit-3a0c58e
kind: what
title: "KNOWN_LIMITATIONS \u2014 MLX Inference Proxy \u2014 RETIRED (commit 3a0c58e)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "MLX Inference Proxy \u2014 RETIRED (commit 3a0c58e)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.667773
updated_at: 1784946220.667773
---

The MLX inference proxy and all its limitations (single-model eviction,
cold-boot 503 windows, admission control, deploy staleness) no longer
apply. All chat inference runs through Ollama (:11434). MLX is retained
only for speech (:8918), transcription (:8924), embeddings (:8917), and
reranking (:8925) — those have their own sections.
