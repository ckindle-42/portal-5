---
id: unit-model-catalog-huihui-ai-gemma-4-abliterated-e2b-qat
kind: what
title: "MODEL_CATALOG \u2014 `huihui_ai/gemma-4-abliterated:E2b-qat`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`huihui_ai/gemma-4-abliterated:E2b-qat`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6199071
updated_at: 1784946220.6199071
---

Gemma4-E2B QAT abliterated (~3GB, huihui_ai, Gemma4 base). auto-pentest PRIMARY (promoted 2026-06-25) + bench-exec-exploit PRIMARY. Thinking model — strips <think> blocks in pipeline output. Head-to-head vs baronllm 2026-06-25 (stripped final answer): composite 0.70 vs 0.50, header 0.83 vs 0.50, MITRE 1.4 vs 0.5 avg, zero refusals/disclaimers. Exec chain: 80.0% EXPLOIT slot (108/135), 71.6 t/s, zero zero-tool chains. Replaces Qwable-35B in bench chain (21GB → 3GB, +7.6pp) and baronllm on auto-pentest (8B → 2B, +0.20 composite). audit-tools 2026-06-24: tool_call confirmed.
