---
id: unit-model-catalog-hf-co-nguuma-security-slm-unsloth-1-5b-latest
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/Nguuma/security-slm-unsloth-1.5b:latest`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`hf.co/Nguuma/security-slm-unsloth-1.5b:latest`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.622539
updated_at: 1784946220.622539
---

security-slm-unsloth-1.5b (~1.1GB, Nguuma, DeepSeek-R1-distill base finetuned on security corpora). Multi-seat V2 bench candidate (2026-07-05) — red+blue+CoT+mcp-security seats. supports_tools=false: audited directly against Ollama, Modelfile TEMPLATE is a bare DeepSeek-R1-style chat template with zero `{{ .Tools }}` handling — given tool defs it hallucinates freeform "as-if" tool usage in prose rather than emitting a real tool call. Scored on prose/CoT only, not tool dispatch. bench-only, PROMOTE_POLICY=confirm.
