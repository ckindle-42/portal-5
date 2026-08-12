---
id: unit-model-catalog-hf-co-bartowski-thudm-glm-z1-rumination-32b-0414-gguf-thudm-glm-z1-rumination-32b-0414-q4-k-m-gguf
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 640a004e4a83811639544dfada51fcd1268b0688
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.631008
updated_at: 1784946220.631008
---

`hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF:THUDM_GLM-Z1-Rumination-32B-0414-Q4_K_M.gguf` is GLM-Z1-Rumination-32B Q4_K_M (~20GB, THUDM/ZhipuAI, April 2026), ZhipuAI's reasoning answer to QwQ/DeepSeek-R1 with multi-step chain-of-thought. `config/backends.yaml` registers it in three groups — `general`, `coding`, and `reasoning` — with `supports_tools: false` in every one; the coding entry inherits the same false flag, so it is a no-tools reasoning model fleet-wide. `config/portal.yaml` selects it as the `model_hint` for `bench-glm-z1-rumination`, which describes it as a candidate for the auto-reasoning pool alongside `deepseek-r1:32b-q4_k_m` under PROMOTE_POLICY quality ≥ 0.83 and TPS ≥ 15. The doc body's older promotion note is not reflected in config — the bench lane still frames it as a candidate, not the auto-reasoning primary.

## Why

The prior body claimed a 2026-06-21 promotion with quality 1.00 and 12.1 TPS; `config/portal.yaml` shows the model still sitting in `bench-glm-z1-rumination` as a candidate under a TPS-floor policy, so re-grounding corrects that claim to the config's candidate status. `config/backends.yaml` supplies the three groups and the uniform `supports_tools: false` values. The reasoning-identity knowledge (ZhipuAI, QwQ/DeepSeek-R1 competition) is kept because the bench description records it.
