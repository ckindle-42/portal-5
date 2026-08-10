---
id: unit-model-catalog-hf-co-quantfactory-llama-3-2-3b-instruct-abliterated-gguf
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: de01e9b1e91aa629f9d80d26a890483a552e43e0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.597147
updated_at: 1784946220.597147
---

`hf.co/QuantFactory/Llama-3.2-3B-Instruct-abliterated-GGUF` is an ultra-fast 3B abliterated fallback registered in `config/backends.yaml` under the `general` group with `supports_tools: false`. The stock Llama-3.2-3B template does not declare a `.Tools` block, and the abliterated GGUF inherits that limitation, so the false flag reflects a template-level constraint rather than a per-model audit. The model id has no presence in `config/portal.yaml`; it is reachable only through the general routing pool, making this a pure backend-registry entry with no dedicated workspace.

## Why

The `general`-group placement and `supports_tools: false` are asserted directly by `config/backends.yaml`, and the absence of any `config/portal.yaml` workspace binding is itself the decisive fact: this model is a fallback-only general-pool citizen. The institutional note about the missing `.Tools` template is kept because it explains the flag without any tool-audit history, which the config comments corroborate.
