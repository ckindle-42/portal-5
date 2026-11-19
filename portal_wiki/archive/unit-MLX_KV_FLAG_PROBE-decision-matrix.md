---
id: unit-MLX_KV_FLAG_PROBE-decision-matrix
historical: true
kind: why
title: "MLX_KV_FLAG_PROBE \u2014 Decision matrix"
sources:
- type: design
  path: docs/MLX_KV_FLAG_PROBE.md
  section: Decision matrix
confidence: high
tags:
- docs
- MLX_KV_FLAG_PROBE

---


| Flag | mlx_lm.server | mlx_vlm.server |
|---|---|---|
| `--kv-bits` | ABSENT | PRESENT |
| `--kv-quant-scheme` | ABSENT | PRESENT |
| `--kv-cache-quantization` | ABSENT | ABSENT |
| `--kv-group-size` | ABSENT | PRESENT |
| `--max-kv-size` | ABSENT | PRESENT |
| `--draft-model` | PRESENT | PRESENT |
| `--num-draft-tokens` | PRESENT | ABSENT |
| `--draft-kind` | ABSENT | PRESENT |
| `--prefill-step-size` | PRESENT | PRESENT |
