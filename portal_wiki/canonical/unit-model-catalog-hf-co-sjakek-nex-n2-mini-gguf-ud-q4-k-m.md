---
id: unit-model-catalog-hf-co-sjakek-nex-n2-mini-gguf-ud-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M`"
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
created_at: 1784946220.612376
updated_at: 1784946220.612376
---

`hf.co/sjakek/Nex-N2-mini-GGUF:UD-Q4_K_M` is a ~22GB imatrix quant of a 35B-total / 3B-active MoE post-trained on Qwen3.5-35B-A3B-Base, multimodal with image and text input. `config/backends.yaml` registers it twice with conflicting flags: the `general` group sets `supports_tools: false` while the `coding` group sets `supports_tools: true`, so tool support is asserted only in the agentic-coding lane, not as a global property. `config/portal.yaml` binds it to the `bench-nex-n2-mini` workspace `model_hint` with a Terminal-Bench 2.1 score of 60.7 and PROMOTE_POLICY=confirm. The flag split is the config's way of being conservative outside the coding lane.

## Why

The group-split `supports_tools` values are the core config fact: `config/backends.yaml` grants tool use only under `coding` and denies it under `general`, which `config/portal.yaml`'s bench-only binding reinforces. The institutional note that the model card claims function-calling is retained, but the authoritative verdict is the flag pair in the registry, so the body states the split rather than the marketing claim.
