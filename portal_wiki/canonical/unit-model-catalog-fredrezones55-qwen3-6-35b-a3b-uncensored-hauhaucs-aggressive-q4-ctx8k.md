---
id: unit-model-catalog-fredrezones55-qwen3-6-35b-a3b-uncensored-hauhaucs-aggressive-q4-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.643863
updated_at: 1784946220.643863
---

`fredrezones55/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4-ctx8k` is the bounded-context form of the base HauhauCS Q4, limited to 8192 tokens. `config/backends.yaml` registers it under the `creative` group with `supports_tools: true`. `config/portal.yaml` selects this exact id as the `auto-creative` workspace `model_hint`, which is why the uncensored creative lane serves the capped variant. The window is baked in with `portal models apply-params` because the completion API refuses request-time context options, so the limit has to live in the tag name.

## Why

The `creative` group registration in `config/backends.yaml` supplies the tool flag, while the `auto-creative` `model_hint` in `config/portal.yaml` explains why the workspace reaches this variant instead of the uncapped base. Both files are cited because the serving relationship spans the backend entry and the workspace binding.
