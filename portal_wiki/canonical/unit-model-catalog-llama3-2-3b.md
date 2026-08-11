---
id: unit-model-catalog-llama3-2-3b
kind: what
title: "MODEL_CATALOG \u2014 `llama3.2:3b`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: ed366c7a6eb34d822a5d4aa04f8072edca8acd5d
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1785940186.4107242
updated_at: 1785940186.4107242
---

`llama3.2:3b` is a stock (non-abliterated) 3B Ollama tag registered in `config/backends.yaml` under the `general` group with `supports_tools: true`, live-audited via a direct tool-call probe (`_audit_tools_probe`) rather than inferred from the model card — it emitted a structured `tool_calls` response on the first probe. The model id has no presence in `config/portal.yaml`; it is reachable only through the general routing pool (or by callers addressing it literally as `model` in `/v1/chat/completions`, resolved via the pipeline router's literal-model-id match), making this a pure backend-registry entry with no dedicated workspace.

## Why

The `general`-group placement and `supports_tools: true` are asserted directly by `config/backends.yaml`; the tool-call capability is corroborated by a live probe, not a model-card assumption (project discipline: "audit tools on every new model"). The id was added while provisioning the Ollama-side model matrix for `TASK_OMLX_OLLAMA_MULTIMODEL_BAKEOFF_V1`'s multi-model shootout gate, mirroring the equivalent oMLX-side `Llama-3.2-3B-Instruct-8bit` entry in `omlx-local`.
