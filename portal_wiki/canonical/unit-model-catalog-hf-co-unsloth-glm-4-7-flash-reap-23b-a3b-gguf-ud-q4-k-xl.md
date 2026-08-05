---
id: unit-model-catalog-hf-co-unsloth-glm-4-7-flash-reap-23b-a3b-gguf-ud-q4-k-xl
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 778def71961fd1bb2f1088be9754388706facf7a
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.615053
updated_at: 1784946220.615053
---

`hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF:UD-Q4_K_XL` is a ~14.2GB Unsloth quant of the GLM-4.7-Flash base using REAP expert pruning plus Unsloth Dynamic imatrix, giving the fleet non-Meta/Qwen lineage diversity. `config/backends.yaml` registers it under the `general` group with `supports_tools: false` and under the `coding` group with `supports_tools: true`. `config/portal.yaml` binds it as the `bench-glm-reap` workspace `model_hint`, staged head-to-head against the standard `glm-4.7-flash:Q4_K_M` quant with a promotion policy of beating that baseline on quality and a TPS floor. The production consumption path is the `glm-coder` persona, which pins the `-ctx64k` variant onto `auto-coding`.

## Why

The `coding`-group `supports_tools: true` versus `general`-group `false` split is asserted directly by `config/backends.yaml`, and `config/portal.yaml` confirms the `bench-glm-reap` staging role. The older claim of a dedicated `auto-glm` production workspace is not supported by any current config entry and was corrected to the actual persona-pin consumption path, keeping the body aligned with what the code determines.
