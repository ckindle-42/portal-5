---
id: unit-model-catalog-phi4-mini-reasoning
kind: what
title: "MODEL_CATALOG \u2014 `phi4-mini-reasoning`"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: '`phi4-mini-reasoning`'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6350179
updated_at: 1784946220.6350179
---

Microsoft Phi-4-Mini-Reasoning (2025, MIT, 3.8B, ~2.5GB Q4, 128K ctx). RL-trained for math, formal proofs, symbolic computation. Beats 7B models on AIME/MATH-500/GPQA at 3.8B. bench-phi4-mini-reasoning target (TASK_MODEL_REFRESH_V8 A7). supports_tools=false (math reasoning specialist). DO NOT PULL :math variant — bench 2026-06-21 shows quality 0.50 vs base 1.00 at same TPS.
