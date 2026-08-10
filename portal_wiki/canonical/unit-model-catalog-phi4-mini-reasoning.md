---
id: unit-model-catalog-phi4-mini-reasoning
kind: what
title: "MODEL_CATALOG \u2014 `phi4-mini-reasoning`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: fb9979b75eb4d70f331e849b80fc7326e8e61847
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6350179
updated_at: 1784946220.6350179
---

`phi4-mini-reasoning` is Microsoft Phi-4-Mini-Reasoning (2025, MIT, 3.8B, ~2.5GB Q4, 128K ctx), RL-trained for math, formal proofs, and symbolic computation, beating 7B models on AIME, MATH-500, and GPQA at its size. `config/backends.yaml` registers it in `group: reasoning` with `supports_tools: false`, consistent with a math specialist that does not route tools. `config/portal.yaml`'s auto-math workspace describes the model in its text and serves the derived `phi4-mini-reasoning:latest-ctx24k` tag as `model_hint`. The catalog warns against pulling the `:math` variant — the 2026-06-21 bench scored it 0.50 quality versus the base's 1.00 at equal TPS.

## Why

Grounding anchors the model to the reasoning-group registration whose supports_tools false flag matches its specialist role, and to the auto-math workspace text that names it. The base id is the reasoning-group entry, while the workspace consumes the ctx24k sibling — a distinction the doc collapsed. The bench `:math` warning is kept as recorded institutional guidance.
