---
id: unit-model-catalog-cybersecqwen-4b-toolfix-latest
kind: what
title: "MODEL_CATALOG \u2014 `cybersecqwen-4b-toolfix:latest`"
sources:
- type: code
  path: config/backends.yaml
- type: code
  path: config/portal.yaml
last_generated_commit: 50b73876729db7181402fcbcc48400caa1ba1e40
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.623002
updated_at: 1784946220.623002
---

`cybersecqwen-4b-toolfix:latest` is registered in `config/backends.yaml` under the `security` backend group with `supports_tools: true` (the audit comment documents the `<tool_call>` caveats) and also appears in the `general` group's intake block with `supports_tools: false`. `config/portal.yaml` binds it as the `bench-cybersecqwen-4b-toolfix` workspace `model_hint`. It is a ~2.5GB retemplated derivative of `hf.co/mradermacher/CyberSecQwen-4B-GGUF:Q4_K_M` that adds Qwen-style `<tool_call>` tag support; the base tag hard-errors "does not support tools" in Ollama. Verified tool behavior: well-formed `<tool_call>` blocks only when a system message is present (the Modelfile gates the tools block on `{{- if .System }}`) and only as plain content, which blue.py parses via `_extract_tool_calls_from_content`. It is a multi-seat V2 blue-seat bench candidate, PROMOTE_POLICY=confirm.

## Why

The dual registration is the key config fact: the `security` group grants `supports_tools: true` after audit while the `general` group keeps it false, and `config/portal.yaml` gives it the dedicated bench workspace. The institutional knowledge about the conditional `<tool_call>` emission and the blue.py content-parsing fallback is preserved because it explains why the tool flag is true only under specific prompt conditions.
