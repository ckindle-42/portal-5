---
id: unit-known-limitations-p5-mlx-eval-003-hf-hosted-mlx-models-are-currently-unreachable-by-the-pipeline
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-003 \u2014 HF-hosted MLX models are currently\
  \ unreachable by the Pipeline"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "P5-MLX-EVAL-003 \u2014 HF-hosted MLX models are currently unreachable\
    \ by the Pipeline"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.670076
updated_at: 1784946220.670076
---

- **Description**: Ollama's `hf.co/` puller only accepts GGUF repos —
  confirmed directly: pulling any `mlx-community` (or other HF org) safetensors
  repo fails with `"Repository is not GGUF or is not compatible with
  llama.cpp"`. Only Ollama's own curated `ollama.com` library `-mlx` tags
  (a narrow set — currently just the `gemma4` and `qwen3.6` families) can be
  served through Ollama's MLX engine. A catalog sweep found HF `mlx-community`
  (or individual-uploader) conversions for ~56 of our 71 fleet models, and
  direct benching (bypassing Ollama entirely, via raw `mlx_lm`) showed large
  real gains for most of the 11 spot-checked (69% to +487%, one clear
  pre-existing-bug outlier, one regression — see below). **None of this is
  usable in production** — `BackendRegistry` only talks to Ollama's `:11434`
  API, and there is currently no way to route to a raw `mlx_lm`-served model.
- **Impact**: Real, measured speed gains exist for most of the catalog but
  are inaccessible without new serving infrastructure.
- **Future work needed**: A deliberate decision on whether to stand up a
  lightweight MLX serving layer (Ollama would remain the primary scheduler;
  this would NOT be a revival of the full retired proxy/watchdog/
  admission-control stack) to make these models reachable — or simply wait
  for Ollama to expand its official `-mlx` library coverage further (it grew
  from Gemma-only to Gemma+Qwen3.6 between the two testing sessions in this
  same evaluation). No infrastructure work has started; this is an
  evaluation finding only, pending a scope decision.
- **Tooling**: `tests/benchmarks/bench_mlx_hf.py` (committed) — ad hoc
  pull+bench of any HF MLX repo directly via `mlx_lm`, for future spot-checks.
  This is **not** a serving mechanism, just a one-shot benchmark tool. Do not
  build automation or hooks around it without a deliberate decision to revive
  MLX serving.
- **Not universal**: `huihui_ai/qwen3.5-abliterated:9b`'s MLX equivalent was
  measurably *slower* than GGUF (-17%). MLX gains are not guaranteed —
  verify per-model, don't assume.
- **Known outlier, not an MLX win**: `qwen3-coder-next`'s GGUF baseline was
  already flagged elsewhere in this file's history (MLX retirement commit)
  as broken under Ollama ("sharded GGUF incompatible with Ollama"). Its huge
  MLX gain in this evaluation reflects a pre-existing GGUF bug for this
  specific model, not a general MLX advantage.
