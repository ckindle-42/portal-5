---
id: unit-model-catalog-gemma4-12b-it-qat-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:12b-it-qat-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: f5987f1ea6b0cdb25b66e33a02b95183205d0605
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.64424
updated_at: 1784946220.64424
---

`gemma4:12b-it-qat-ctx8k` is the 8192-token capped variant of `gemma4:12b-it-qat`. `config/backends.yaml` places it in the `vision` group with `supports_tools: true`. `config/portal.yaml` names it as the `auto-audio` workspace `model_hint`, meaning the audio-analysis lane actually serves this capped tag rather than the base model. The bound is embedded via `portal models apply-params` because the completion endpoint discards request-time `options.num_ctx`, so the cap must be encoded in a dedicated id.

## Why

The `vision` group registration in `config/backends.yaml` supplies the tool flag, and the `auto-audio` `model_hint` in `config/portal.yaml` is the production-serving fact that distinguishes this derived id from its parent. Both files are cited because together they explain both the backend placement and the workspace that consumes the tag.
