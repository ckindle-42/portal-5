---
id: unit-model-catalog-gemma4-e2b-it-qat
kind: what
title: "MODEL_CATALOG \u2014 `gemma4:e2b-it-qat`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`gemma4:e2b-it-qat`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.63803
updated_at: 1784946220.63803
---

Gemma 4 E2B QAT (~3GB, Apache 2.0, 128K ctx, audio+image+video+text, QAT near-BF16 quality at 4-bit, thinking mode, PLE: ~5.1B representational depth from 2.3B active). Fastest model in fleet by TPS. bench-gemma4-e2b target (TASK_MODEL_REFRESH_V8 A1). supports_tools=true per Gemma4 family; verify via --audit-tools before promotion.
