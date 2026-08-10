---
id: unit-model-catalog-phi4-reasoning-plus
kind: what
title: "MODEL_CATALOG \u2014 `phi4-reasoning:plus`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 5d5f217e3cd2b239cd1a8444769243ea0a3f752e
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.608759
updated_at: 1784946220.608759
---

`phi4-reasoning:plus` is Phi-4-reasoning-plus at Q4 (~8GB, Microsoft, RL-trained with strong STEM/math capability). `config/backends.yaml` registers it in `group: coding` (`ollama-coding`) with `supports_tools: true`, so the coding lane can call a reasoning-capable model. Its derived sibling `phi4-reasoning:plus-ctx32k` sits in the same backend; a backends.yaml comment warns that the ctx32k variant is deliberately excluded from `group: reasoning` because it crashes Ollama's llama-server on load. No `config/portal.yaml` workspace pins either id as a `model_hint`.

## Why

Grounding anchors the model to the coding-group registration whose supports_tools true flag the config declares, and to the backends.yaml comment that explains why the reasoning group refuses the ctx32k sibling. The STEM/math reputation is kept as catalog context; the crash warning is the institutional reason the capped variant never reaches a production reasoning workspace.
