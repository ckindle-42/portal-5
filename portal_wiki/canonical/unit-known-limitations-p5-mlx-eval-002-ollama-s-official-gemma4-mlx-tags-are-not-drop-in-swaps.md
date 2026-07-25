---
id: unit-known-limitations-p5-mlx-eval-002-ollama-s-official-gemma4-mlx-tags-are-not-drop-in-swaps
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-002 \u2014 Ollama's official gemma4 `-mlx`\
  \ tags are not drop-in swaps"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "P5-MLX-EVAL-002 \u2014 Ollama's official gemma4 `-mlx` tags are not drop-in\
    \ swaps"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.669585
updated_at: 1784946220.669585
---

- **Description**: `gemma4:{e2b,e4b,12b}-mlx` (Ollama's own curated library
  tags) showed real, large gains over our current `gemma4:{e2b,e4b,12b}-it-qat`
  GGUF models: +93%, +61%, +30% respectively (clean, isolated, warm-up-matched
  benching). However `ollama show` reveals these are **not the same
  checkpoint in a different format** — they differ in parameter count
  (4.6B→5.2B, 7.5B→8.1B, 11.9B→12.4B), quantization scheme (Q4_0
  quantization-aware-trained vs nvfp4 post-training quant), and the 12b tag
  even reports a different architecture name (`gemma4_unified` vs `gemma4`).
  Critically, **none of the `-mlx` tags have vision or audio capability** —
  the `Projector` block present on our current QAT variants is entirely
  absent from the MLX tags.
- **Impact**: Cannot be swapped in as a pure speed upgrade. Any workspace
  routing image/audio input to `gemma4:e2b/e4b/12b-it-qat` would silently
  lose that capability if swapped to the `-mlx` tag. Output quality is also
  unverified — QAT training specifically targets low-precision quality
  retention; nvfp4 post-training quant is a different tradeoff entirely.
- **Future work needed**: (1) Audit which workspaces using these three models
  actually rely on vision/audio input vs text-only — if none do, a text-only
  swap may be viable for those specific workspaces. (2) Run a live tool-call
  probe on any candidate before promotion — never infer `supports_tools` from
  the model card (see `P5-TOOL-001` above for why). (3) Run a quality eval,
  not just TPS, before promoting — QAT vs nvfp4 is not guaranteed equivalent.
  **Do not add `gemma4:*-mlx` tags to `config/backends.yaml` until all three
  are done.**
