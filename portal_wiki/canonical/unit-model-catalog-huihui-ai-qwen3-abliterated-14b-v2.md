---
id: unit-model-catalog-huihui-ai-qwen3-abliterated-14b-v2
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/qwen3-abliterated:14b-v2`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`huihui_ai/qwen3-abliterated:14b-v2`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5983932
updated_at: 1784946220.5983932
---

huihui-ai Qwen3-14B-abliterated v2 (Qwen3-14B base, huihui_ai native Ollama tag). V13-B candidate intake — TIER-GAP fill for the 9B <-> 27B/35B space, no 14B representation currently. v1 explicitly retired by huihui-ai for garbled-output bugs; task pulls only v2. Same trusted lineage class as E2b-qat, gemma-4-abliterated, baronllm-abliterated. supports_tools=true (clean, well-formed tool_calls in direct /api/chat probe). Native <think> emission: MISSING from probe (opening tag absent; abliteration sometimes disrupts native reasoning emission) — soft warning, does not block intake per task policy. bench-qwen3-14b-abliterated target. PROMOTE_POLICY=confirm.
