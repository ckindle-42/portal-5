---
id: unit-model-catalog-alicankiraz0-cybersecurity-baronllm-offensive-security-llm-q6-k-gguf-dropped-hf-id-only-see-baronllm-q6-k-below-for-the-fleet-entry
kind: what
title: "MODEL_CATALOG \u2014 `AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF`\
  \ \u2014 DROPPED (hf_id only \u2014 see `baronllm:q6_k` below for the fleet entry)"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`AlicanKiraz0/Cybersecurity-BaronLLM_Offensive_Security_LLM_Q6_K_GGUF`\
    \ \u2014 DROPPED (hf_id only \u2014 see `baronllm:q6_k` below for the fleet entry)"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.627518
updated_at: 1784946220.627518
---

Red EXPLOIT-slot candidate. Historically blocked — `ollama pull hf.co/...` fails on this gated repo
regardless of `HF_TOKEN` ("realm host huggingface.co does not match original host hf.co", still true
as of 2026-07-21). Un-blocked for the GATE-D Expert-candidate pool by downloading via
`huggingface_hub.hf_hub_download` (correctly handles gated-repo auth) and `ollama create` with a
local Modelfile — see `baronllm:q6_k` below for the fleet entry. `portal models pull` still can't do
this automatically; the workaround is a one-off manual step, not scripted.
