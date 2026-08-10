---
id: unit-model-catalog-hf-co-mradermacher-vulnllm-r-7b-gguf-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 9c0a4efa9fea8836ee3466b206c01b042c59455f
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.619392
updated_at: 1784946220.619392
---

`hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M` appears in `config/backends.yaml` under the `general` group with `supports_tools: false` and under the `security` group with `supports_tools: true`, so its tool flag is group-specific rather than global. `config/portal.yaml` binds the base id to the `bench-vulnllm-r-7b` and `bench-vulnllm-r7b` bench workspaces and the `bench-exec-recon` exec-chain role, while the `auto-security` workspace routes the `q4_K_M-ctx8k` variant and its description records the 2026-07-16 reselection note: the older fast-chain claim predates the reliability-scoring fix, the live re-bench found valid_rate 0.89 with redundant_call_rate 0.50, and `glm-4.7-flash:Q4_K_M` is staged as the reselection primary pending an analytical-workload test.

## Why

The group-split `supports_tools` value is the key config fact: `config/backends.yaml` grants tool support only under `security`, and `config/portal.yaml` keeps the model as the auto-security incumbent while documenting the reliability-gate correction. The reselection knowledge about `glm-4.7-flash:Q4_K_M` is preserved because the same files name it as the staged primary, so both models are grounded in the cited config.
