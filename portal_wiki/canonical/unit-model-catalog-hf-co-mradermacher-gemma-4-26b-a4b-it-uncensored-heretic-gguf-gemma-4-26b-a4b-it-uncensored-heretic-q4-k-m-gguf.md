---
id: unit-model-catalog-hf-co-mradermacher-gemma-4-26b-a4b-it-uncensored-heretic-gguf-gemma-4-26b-a4b-it-uncensored-heretic-q4-k-m-gguf
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 86e6f142c0069ca2d4824b4721a545e64bd585b3
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.600791
updated_at: 1784946220.600791
---

`hf.co/mradermacher/gemma-4-26B-A4B-it-uncensored-heretic-GGUF:gemma-4-26B-A4B-it-uncensored-heretic.Q4_K_M.gguf` is the mradermacher "heretic" uncensored Q4 of Gemma 4 26B A4B (~17GB). `config/backends.yaml` registers it in the `general` group only, with `supports_tools: false`. It is NOT present in `config/portal.yaml`: no workspace `model_hint` references it, consistent with the mapping's `in_portal: false`. The doc body's "auto-creative primary" label is historical — `auto-creative` has since been upgraded to the HauhauCS uncensored Qwen3.6-35B model, whose description records that upgrade away from gemma-4-heretic. The general-group registration keeps the heretic Q4 as a fallback-pool entry rather than a pinned creative lane.

## Why

The prior body claimed "auto-creative primary" from doc prose; re-grounding shows `config/backends.yaml` places the model in `general` only with `supports_tools: false`, and `config/portal.yaml` never selects it (in_portal false). The auto-creative upgrade is verified through that workspace's description naming the heretic-Q4 replacement. Re-grounding therefore corrects the primary-label claim to the config reality of a general-pool entry, while retaining the ~17GB/uncensored identity as card metadata.
