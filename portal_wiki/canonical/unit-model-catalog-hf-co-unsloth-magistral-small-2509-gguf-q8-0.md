---
id: unit-model-catalog-hf-co-unsloth-magistral-small-2509-gguf-q8-0
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0`"
sources:
- type: code
  path: config/backends.yaml
last_generated_commit: 1896bb7da29dd96ff280b8ffb495519d507070ee
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6003342
updated_at: 1784946220.6003342
---

`hf.co/unsloth/Magistral-Small-2509-GGUF:Q8_0` is a ~25GB Unsloth GGUF of the Magistral-Small-2509 model with a `[THINK]` reasoning mode and Mistral lineage, pulled via the hf.co route because the `magistral:24b-small-2509-q8_0` tag is not in the Ollama registry. `config/backends.yaml` registers it under the `general` group with `supports_tools: false`. The template advertises an `[AVAILABLE_TOOLS]` format, but Ollama tool dispatch never fires — the model reasons about tools in prose instead of emitting tool_calls, which a direct API test confirmed. It has no `config/portal.yaml` workspace binding, so it exists purely as a general-pool entry.

## Why

The `general`-group registration with `supports_tools: false` is asserted directly by `config/backends.yaml`, and the model has no workspace in `config/portal.yaml`, making the backend registry the only source of truth. The institutional knowledge that the `[AVAILABLE_TOOLS]` template does not actually dispatch tools is preserved because it is the exact reason the flag is false and why the model never reaches a production workspace.
