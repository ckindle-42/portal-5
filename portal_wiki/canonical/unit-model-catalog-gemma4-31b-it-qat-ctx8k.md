---
id: unit-model-catalog-gemma4-31b-it-qat-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:31b-it-qat-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: ed366c7a6eb34d822a5d4aa04f8072edca8acd5d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.64515
updated_at: 1784946220.64515
---

`gemma4:31b-it-qat-ctx8k` is a derived variant of `gemma4:31b-it-qat` that pins the 8192-token window into the Modelfile. `config/backends.yaml` registers it under the `vision` group with `supports_tools: true`, the same placement as its 31B Dense QAT parent. The cap is applied with `portal models apply-params` because the chat-completions endpoint refuses per-request `options.num_ctx` overrides; a separate tag is the only way to bound context per workspace. Unlike the base model, this derived id has no workspace `model_hint` of its own in `config/portal.yaml`.

## Why

The sole config grounding is the `vision` group entry in `config/backends.yaml`; no portal workspace binds this tag directly, so citing the backend file alone is accurate. The distinction from the parent model is exactly why the derived-id mechanism exists, which is what makes the unit's registry-focused framing appropriate.
