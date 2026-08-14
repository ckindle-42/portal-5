---
id: unit-model-catalog-nvidia-nemotron-3-5-lightning-30b-a3b-oq4e-mtp
kind: what
title: "MODEL_CATALOG \u2014 `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 41df61e0a6102275a700700e9765972f1508c4c5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786736000.0
updated_at: 1786736000.0
---

`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp` (`txgsync/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-oQ4e-mtp` on Hugging Face) is a 4-bit MLX side-car checkpoint for NVIDIA's Nemotron 3.5 Lightning 30B-A3B MoE model (~3B active params/token) that ships real `mtp.*` weight tensors for the `nemotron_h` architecture, quantized via oMLX's oQ4e mixed-precision format. It was added 2026-08-14 as a new model — the base BF16 release and the plain `mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` conversion ship no MTP head, matching the same checkpoint-level gap found on Qwen3.8-27B (see `unit-model-catalog-qwen3-8-27b-oq4e-mtp`). Requires oMLX 0.6.0.dev1's MTPLX side-car MTP import path. `config/backends.yaml` registers it in the `omlx-general` entry (group `general`, `priority: 10`) with `supports_tools: true`, live-audited via a direct tool-call probe; the `aliases` block maps the Ollama GGUF hint `hf.co/bartowski/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF:Q4_K_M-ctx8k` onto this oMLX name. `config/portal.yaml`'s `auto-nemotron` workspace pins the GGUF hint as its `model_hint`, so oMLX serves it via the alias with automatic Ollama fallback. With `mtp_enabled: true` set, the MTP path activates and was measured live at 70.0-70.3 tok/s versus 52.9-53.1 tok/s on the Ollama GGUF baseline (~1.33x), same prompt/hardware/session — a notably higher 76-87% MTP draft-accept rate than Qwen3.8-27B's 60-65%, because the MoE architecture's small active-parameter backbone keeps each verify cycle cheap.

## Why

Grounding anchors the model to its oMLX registration, the alias reaching it from the `auto-nemotron` workspace's GGUF hint, and the same checkpoint-level MTP-weights pattern already established for Qwen3.8-27B, cross-referenced rather than re-derived. The measured tok/s and accept-rate numbers are kept as measured results, not config facts, and the higher accept rate is attributed to the MoE active-parameter count, the specific factor that differs from the dense Qwen3.8-27B comparison.
