---
id: unit-model-catalog-hf-co-unsloth-qwen3-6-35b-a3b-gguf-ud-q4-k-xl
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 956ee226e319e701e3605c9de6950bfa437a56f0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.609513
updated_at: 1784946220.609513
---

`hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL` is a ~22GB Unsloth Dynamic 2.0 sensitivity-aware quant of the Qwen3.6-35B-A3B MoE with 3B active parameters. `config/backends.yaml` registers it under both the `general` and `coding` groups with `supports_tools: true` in each. `config/portal.yaml` binds it as the `bench-qwen36-35b-a3b-ud` `model_hint`, staged as the agentic-lane candidate C1 for the fleet refresh and compared head-to-head against the stock Q4_K_M quant. The production-validated bench history is retained as institutional knowledge, but the current config role is the bench candidate with PROMOTE_POLICY=confirm.

## Why

The dual `general`/`coding` registration with `supports_tools: true` is asserted directly by `config/backends.yaml`, and `config/portal.yaml` fixes its current status as the `bench-qwen36-35b-a3b-ud` candidate. The older promotion wording was corrected to the config's actual bench-only status, so the body states only what the registry and workspace descriptions determine.
