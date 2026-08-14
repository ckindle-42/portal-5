---
id: unit-known-limitations-p5-mlx-eval-002-ollama-s-official-gemma4-mlx-tags-are-not-drop-in-swaps
kind: what
title: "KNOWN_LIMITATIONS \u2014 P5-MLX-EVAL-002 \u2014 Ollama's official gemma4 `-mlx`\
  \ tags are not drop-in swaps"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: tests/benchmarks/bench_mlx_hf.py
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.669585
updated_at: 1784946220.669585
---

- **Description**: Ollama's official `gemma4:{e2b,e4b,12b}-mlx` library tags are not drop-in replacements for the production `gemma4:{e2b,e4b,12b}-it-qat` GGUF models. The evaluation in `coding_task/TASK_EVAL_GEMMA4_MLX_TAGS_V1.md` documents the swap-blocking differences: parameter counts differ per tier, the quantization schemes differ (QAT versus nvfp4), and the 12b tag reports a different architecture name (`gemma4_unified` vs `gemma4`). At the time of the original evaluation the `-mlx` tags lacked the vision/audio capability that the QAT variants' multimodal projection provides.
- **Impact**: Cannot be swapped in as a pure speed upgrade. A workspace routing image/audio input to the QAT tags would silently lose that capability if swapped to `-mlx`. Output quality is also unverified — QAT training targets low-precision quality retention, which nvfp4 post-training quant does not guarantee.
- **Future work needed**: (1) Audit which workspaces using these models rely on vision/audio input vs text-only. (2) Run a live tool-call probe on any candidate before promotion — never infer `supports_tools` from the model card. (3) Run a quality eval, not just TPS, before promoting. **Do not add `gemma4:*-mlx` tags to `config/backends.yaml` until all three are done.**

## Why

A model tag that is faster but semantically different — different weights, different quant scheme, different architecture, and originally missing a modality — is a regression wearing a speedup costume. The eval task doc records the exact deltas so a swap is never justified on TPS alone, and the three-step future-work gate keeps the decision mechanical: capability audit, live tool probe, quality eval.
