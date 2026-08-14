---
id: unit-model-catalog-qwen3-8-27b-oq4e-mtp
kind: what
title: "MODEL_CATALOG — `Qwen3.8-27B-oQ4e-mtp`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 5acee6003d90283638510b0d65019042bf70dfc8
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1786736000.0
updated_at: 1786736000.0
---

`Qwen3.8-27B-oQ4e-mtp` (`txgsync/Qwen3.8-27B-oQ4e-mtp` on Hugging Face) is a 4-bit MLX side-car checkpoint for Qwen3.8-27B that ships real `mtp.*` weight tensors, quantized via oMLX's oQ4e mixed-precision format. It was added 2026-08-14 to replace `mlx-community/Qwen3.8-27B-4bit` in this role: that plain conversion — and the upstream `Qwen/Qwen3.8-27B` release itself — ships no MTP head at all, confirmed at the `model.safetensors.index.json` tensor-name level, so setting `mtp_enabled: true` on it in oMLX's `~/.omlx/model_settings.json` silently no-ops (oMLX logs "config declares mtp heads but checkpoint ships no mtp.* weights; MTPModule attachment skipped"). This checkpoint requires oMLX 0.6.0.dev1's MTPLX side-car MTP import path. `config/backends.yaml` registers it in the `omlx-coding` entry (group `coding`, `priority: 10`) with `supports_tools: true`, live-audited via a direct tool-call probe (clean `tool_calls`, correctly typed arguments); the `aliases` block maps the existing bench-lane GGUF hint `hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` (used by the `bench-qwen38-27b` workspace in `config/portal.yaml`) onto this oMLX name. With `mtp_enabled: true` set, the MTP path activates and was measured live at 17.5-18.6 tok/s versus 12.25 tok/s on the Ollama GGUF baseline (~1.45x), same prompt/hardware/session, with a 60-65% MTP draft-accept rate.

## Why

Grounding anchors the model to its oMLX registration, the alias that lets the existing bench-lane GGUF hint reach it unchanged, and the specific reason it replaces the prior plain conversion — a checkpoint-level MTP-weights gap, not a config mistake, verified by inspecting the safetensors index rather than assumed from the model card. The measured tok/s and accept-rate numbers are kept as measured results, not config facts.
