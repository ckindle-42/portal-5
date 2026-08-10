---
id: unit-model-catalog-alicankiraz0-cybersecurity-baronllm-offensive-security-llm-q6-k-gguf-dropped-hf-id-only-see-baronllm-q6-k-below-for-the-fleet-entry
kind: what
title: "MODEL_CATALOG \u2014 `AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF`\
  \ \u2014 DROPPED (hf_id only \u2014 see `baronllm:q6_k` below for the fleet entry)"
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
created_at: 1784946220.627518
updated_at: 1784946220.627518
---

The Hugging Face repo `AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF` exists in `config/portal.yaml`'s model pull registry as a gated entry whose `ollama_name` is `baronllm:q6_k`; the fleet entry itself is registered in `config/backends.yaml` under the `security` backend group with `supports_tools: false`. The DROPPED note records that `ollama pull hf.co/...` fails on this gated repo regardless of `HF_TOKEN` because of a realm-host mismatch, still true as of 2026-07-21. The workaround is a one-off manual step: download via `huggingface_hub.hf_hub_download` (which handles gated-repo auth) and `ollama create` with a local Modelfile. `portal models pull` cannot automate this path, so the registry entry documents it inline rather than scripting it.

## Why

This unit is grounded in both config files because the gated source id and the served model id live in different places: `config/portal.yaml` maps the Hugging Face repo to `baronllm:q6_k` and flags it `gated`, while `config/backends.yaml` registers the fleet model in the `security` group with `supports_tools: false`. The DROPPED historical note is kept as institutional context, but every reachable claim now traces to the registry and backend entries that actually define the model.
