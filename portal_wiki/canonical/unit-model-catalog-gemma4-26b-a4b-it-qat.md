---
id: unit-model-catalog-gemma4-26b-a4b-it-qat
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:26b-a4b-it-qat`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`gemma4:26b-a4b-it-qat`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.639137
updated_at: 1784946220.639137
---

Gemma 4 26B-A4B QAT (~15GB, Apache 2.0, 256K ctx, vision+text, QAT: near-BF16 quality at same ~15GB as production gemma4:26b-a4b-it-q4_K_M). Bench-only comparison vs production primary — if quality confirmed better at similar TPS, a separate promotion task swaps the primary. bench-gemma4-26b-qat target (TASK_MODEL_REFRESH_V8 A4). supports_tools=true per Gemma4 family; verify via --audit-tools before promotion.
