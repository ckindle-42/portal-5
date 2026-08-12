---
id: unit-model-catalog-hf-co-nguuma-security-slm-unsloth-1-5b-latest
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Nguuma/security-slm-unsloth-1.5b:latest`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 10c7734f3f87df5a9d525bb5c1f3970c96a73a91
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.622539
updated_at: 1784946220.622539
---

`hf.co/Nguuma/security-slm-unsloth-1.5b:latest` is a ~1.1GB DeepSeek-R1-distill fine-tune on security corpora, registered in `config/backends.yaml` under both the `general` and `security` groups with `supports_tools: false` in each. The security-group entry's comment explains the flag: a direct Ollama audit found the Modelfile TEMPLATE is a bare DeepSeek-R1-style chat template with no `{{ .Tools }}` handling, so the model hallucinates freeform as-if tool usage in prose instead of emitting a real call. `config/portal.yaml` binds it only to the `bench-security-slm-1p5b` bench workspace with `tools` deliberately empty, scoring prose and chain-of-thought alone.

## Why

The `supports_tools: false` verdict is asserted twice in `config/backends.yaml` and is the mechanical reason the model can only be bench-scored on prose: with no template tool block, tool dispatch is structurally impossible. `config/portal.yaml` confirms the bench-only assignment. This grounding keeps the old institutional note about the missing `.Tools` handling because it is exactly the justification the config comment records.
