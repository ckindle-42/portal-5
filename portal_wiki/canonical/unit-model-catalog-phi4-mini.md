---
id: unit-model-catalog-phi4-mini
kind: what
title: "MODEL_CATALOG \u2014 `phi4-mini`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`phi4-mini`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.602825
updated_at: 1784946220.602825
---

Microsoft Phi-4-Mini (Feb 2025, MIT, 3.8B, ~2.5GB Q4, 128K ctx). Synthetic-data training: multilingual, function calling, reasoning, math. Outperforms Llama 3.2 3B and Qwen 2.5 3B on reasoning/math. Ultra-lightweight daily fallback candidate. bench-phi4-mini target (TASK_MODEL_REFRESH_V8 A6). supports_tools=true per official model card. DO NOT PULL :math variant — bench 2026-06-21 shows quality 0.67 vs base 1.00 at same TPS.
