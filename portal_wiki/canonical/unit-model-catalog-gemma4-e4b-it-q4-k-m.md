---
id: unit-model-catalog-gemma4-e4b-it-q4-k-m
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:e4b-it-q4_K_M`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`gemma4:e4b-it-q4_K_M`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.63768
updated_at: 1784946220.63768
---

Gemma 4 E4B standard Q4 (~5GB). CORRECTED NOTES: supports audio+image+video input and thinking mode (<|think|> token). Per-Layer Embeddings (PLE) give representational depth well above 4B weight count. supports_tools=true: audit-tools 2026-06-18 confirmed tool_call. queue for --audit-tools re-verification (Gemma4 family supports function calling). Retained as production vision fallback; bench-gemma4-e4b-qat benchmarks the QAT upgrade (TASK_MODEL_REFRESH_V8 A18).
