---
id: unit-model-catalog-phi4-mini
kind: what
title: "MODEL_CATALOG \u2014 `phi4-mini`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 0fec84d46a8898b1b5baf0508af1e25634b099af
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.602825
updated_at: 1784946220.602825
---

`phi4-mini` is Microsoft Phi-4-Mini (Feb 2025, MIT, 3.8B, ~2.5GB Q4, 128K ctx), trained on synthetic data for multilingual, function-calling, reasoning, and math tasks, outperforming Llama 3.2 3B and Qwen 2.5 3B on reasoning and math. `config/backends.yaml` registers it in `group: general` with `supports_tools: true`. `config/portal.yaml` does not pin the base id directly; the auto-math workspace serves the reasoning sibling `phi4-mini-reasoning:latest-ctx24k` as its `model_hint`. The catalog warns against pulling the `:math` variant — the 2026-06-21 bench scored it 0.67 quality versus the base's 1.00 at equal TPS.

## Why

Grounding anchors the model to the general-group registration whose supports_tools true flag the config carries, and honestly records that no portal.yaml workspace uses the base id — auto-math consumes the reasoning sibling instead. The ultra-lightweight daily-fallback intent is kept from the catalog because the registration exists precisely to make that fallback available.
