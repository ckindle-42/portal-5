---
id: unit-known-limitations-p5-mlx-eval-005-two-security-tier-fine-tunes-have-no-working-mlx-conversion
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-005 \u2014 Two security-tier fine-tunes\
  \ have no working MLX conversion"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: tests/benchmarks/bench_mlx_hf.py
last_generated_commit: 3cdc95603cf1faa41ddd64aa3eaad1ec45a113ce
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6709208
updated_at: 1784946220.6709208
---

- **Description**: `supergemma4-26b-uncensored` (the `redteam-deep` and `purpleteam-exec` variant `model_hint` in `config/portal.yaml`, and registered in `config/backends.yaml`) and `huihui_ai/gemma-4-abliterated:E2b-qat` were searched across multiple HF uploaders for a text-only MLX conversion. Every MLX conversion found for these specific fine-tunes is a multimodal/vision-language checkpoint whose weights crash on plain text-only `mlx_lm` load with a parameter-count mismatch. The GGUF paths remain the only working forms.
- **Impact**: These models stay GGUF-only for the foreseeable future; the pipeline serves them through Ollama's GGUF path regardless.
- **Do not** spend further time searching for a working MLX conversion for either unless a new text-only-compatible upload appears.

## Why

A fine-tune's MLX port can quietly change modality — producing a vision-language checkpoint that a text-only loader rejects — so the search for a working conversion is a bounded cost that should not be re-litigated on every model refresh. Recording the two known failures with their exact symptom prevents repeated dead-end hunting, while the note that they are GGUF-only matches the fact that the serving tier is Ollama.
