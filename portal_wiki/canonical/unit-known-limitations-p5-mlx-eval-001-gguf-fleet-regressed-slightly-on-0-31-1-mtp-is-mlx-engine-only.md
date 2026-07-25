---
id: unit-known-limitations-p5-mlx-eval-001-gguf-fleet-regressed-slightly-on-0-31-1-mtp-is-mlx-engine-only
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-001 \u2014 GGUF fleet regressed slightly\
  \ on 0.31.1; MTP is MLX-engine-only"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "P5-MLX-EVAL-001 \u2014 GGUF fleet regressed slightly on 0.31.1; MTP is\
    \ MLX-engine-only"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.669174
updated_at: 1784946220.669174
---

- **Description**: Ollama 0.31.1's claimed MTP speedup applies only when Ollama
  selects its own MLX engine subprocess (triggered by official `-mlx`-tagged
  models). Our entire GGUF fleet routes through `llama-server` regardless of
  Ollama version — confirmed via server log (`spec common_specu: no
  implementations specified for speculative decoding`). Separately, the GGUF
  fleet got measurably *slower* after the 0.31.1 upgrade (~5-11% across 15+
  models tested, clean warm-up-matched methodology). Tested `num_batch=512`
  (pre-upgrade default) vs 0.31.1's auto-selected 1024/2048 — **zero
  measurable difference**, ruling out batch-size as the cause. Root cause is
  presumably the bundled llama.cpp engine version bump itself; no known
  workaround.
- **Impact**: None today (no config changed). Documented so a future Ollama
  upgrade isn't mistaken for a routing/pipeline regression.
