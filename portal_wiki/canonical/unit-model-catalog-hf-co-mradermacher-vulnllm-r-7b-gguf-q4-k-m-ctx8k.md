---
id: unit-model-catalog-hf-co-mradermacher-vulnllm-r-7b-gguf-q4-k-m-ctx8k
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.649809
updated_at: 1784946220.649809
---

`hf.co/mradermacher/VulnLLM-R-7B-GGUF:q4_K_M-ctx8k` is the derived 8K-context tag of the AppSec specialist and the only VulnLLM tag `config/portal.yaml` routes in production: it is the `model_hint` of the `auto-security` workspace, whose description binds it to authorized CVE/CWE analysis and hardening. `config/backends.yaml` registers it under the `security` group with `supports_tools: true`, while the base `Q4_K_M` id carries the bench and exec-chain roles. The lowercased `q4_K_M` quant segment is the pullable form `ollama create` mints for derived tags, so this spelling is authoritative over any uppercase variant.

## Why

The distinction that matters here is routing: `config/portal.yaml` resolves the `auto-security` workspace to this exact `-ctx8k` tag, not to the base id, and `config/backends.yaml` confirms the `security`-group `supports_tools: true` flag beside it. The derived-tag mechanism is preserved because the context cap is a routing requirement enforced by the model id itself, which is precisely what the two cited files determine.
