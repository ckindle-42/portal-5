---
id: unit-model-catalog-cybersecqwen-4b-toolfix-latest
kind: what
title: "MODEL_CATALOG \u2014 `cybersecqwen-4b-toolfix:latest`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`cybersecqwen-4b-toolfix:latest`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.623002
updated_at: 1784946220.623002
---

cybersecqwen-4b-toolfix (~2.5GB, retemplated from mradermacher/CyberSecQwen-4B-GGUF Q4_K_M to add Qwen-style `<tool_call>` tag support — the base tag hard-errors "does not support tools" in Ollama). Multi-seat V2 bench candidate (2026-07-05) — blue seat. supports_tools=true: verified it emits well-formed `<tool_call>` blocks, but only when a system message is present (Modelfile gates the `{{ .Tools }}` block on `{{- if .System }}`) and as plain content rather than a structured tool_calls array (blue.py works around this — see blue.py's `_extract_tool_calls_from_content`). bench-only, PROMOTE_POLICY=confirm.
