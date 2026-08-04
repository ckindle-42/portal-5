---
id: unit-known-limitations-p5-mlx-eval-003-hf-hosted-mlx-models-are-currently-unreachable-by-the-pipeline
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-003 \u2014 HF-hosted MLX models are currently\
  \ unreachable by the Pipeline"
sources:
- type: code
  path: tests/benchmarks/bench_mlx_hf.py
- type: code
  path: portal/platform/inference/cluster_backends.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.670076
updated_at: 1784946220.670076
---

- **Description**: Ollama's `hf.co/` puller only accepts GGUF repos; pulling any `mlx-community` safetensors repo fails with the "Repository is not GGUF or is not compatible with llama.cpp" error, as `tests/benchmarks/bench_mlx_hf.py` documents. Only Ollama's curated `-mlx` library tags can be served through its MLX engine. None of the HF-hosted MLX conversions is usable in production because `BackendRegistry` in `portal/platform/inference/cluster_backends.py` talks only to Ollama's OpenAI-compatible endpoint (`chat_url` appends `/v1/chat/completions`), so a raw `mlx_lm`-served model is unreachable without new serving infrastructure.
- **Impact**: Real, measured speed gains exist for part of the catalog but are inaccessible through the pipeline as built.
- **Tooling**: `tests/benchmarks/bench_mlx_hf.py` (committed) pulls and benches any HF MLX repo directly via `mlx_lm`. It is not a serving mechanism; its docstring forbids adding launch hooks or pipeline integration without a deliberate decision to revive MLX serving.
- **Not universal**: MLX gains are not guaranteed — at least one model's MLX equivalent measured slower than its GGUF, and one large apparent gain reflects a pre-existing GGUF incompatibility for that specific model, not a general MLX advantage. Verify per-model.
- **Future work needed**: A deliberate decision on whether to stand up a lightweight MLX serving layer (Ollama would remain the primary scheduler; this would not revive the retired proxy/watchdog/admission-control stack) or wait for Ollama to expand its official `-mlx` library coverage. No infrastructure work has started; this is an evaluation finding only.

## Why

The pipeline's backend contract is one endpoint family, and its URL construction proves it — every model must speak Ollama's OpenAI-compatible API. HF MLX models break that contract, so measuring their speed with a throwaway bench tool records the opportunity without pretending it exists in production; the explicit no-hooks warning on the tool preserves the retired-proxy boundary.
