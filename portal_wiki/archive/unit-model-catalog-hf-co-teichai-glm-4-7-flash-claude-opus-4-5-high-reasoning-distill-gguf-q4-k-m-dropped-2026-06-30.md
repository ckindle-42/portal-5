---
id: unit-model-catalog-hf-co-teichai-glm-4-7-flash-claude-opus-4-5-high-reasoning-distill-gguf-q4-k-m-dropped-2026-06-30
kind: what
title: "MODEL_CATALOG \u2014 `hf.co/TeichAI/GLM-4.7-Flash-Claude-Opus-4.5-High-Reasoning-Distill-GGUF:Q4_K_M`\
  \ \u2014 DROPPED 2026-06-30"
sources:
- type: doc
  path: config/MODEL_CATALOG.md
  commit: 05e42ec2
  section: "`hf.co/TeichAI/GLM-4.7-Flash-Claude-Opus-4.5-High-Reasoning-Distill-GGUF:Q4_K_M`\
    \ \u2014 DROPPED 2026-06-30"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.636529
updated_at: 1784946220.636529
---

GLM-4.7-Flash Claude-Opus-4.5 High-Reasoning Distill Q4_K_M (~18.1GB, TeichAI, Apache 2.0, base unsloth/GLM-4.7-Flash, deepseek2/glm4_moe_lite, 30B total). 250-sample Opus-4.5 reasoning distill (NOTE: this is SFT on text outputs scraped/generated to mimic Claude's style, not true logit distillation — community discussion on the HF model page confirms this directly). V10 candidate — bench-glm47f-claude-distill. DROPPED 2026-06-30: did beat its own base (2.0/3.0 vs 1.0/3.0 on bench-glm) but not enough to justify a new lane given the 130-target persona/workspace surface already in place. Workspace removed; backends.yaml entry removed.
