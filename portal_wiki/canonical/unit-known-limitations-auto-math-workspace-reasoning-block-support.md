---
id: unit-known-limitations-auto-math-workspace-reasoning-block-support
kind: what
title: "KNOWN_LIMITATIONS \u2014 auto-math Workspace \u2014 Reasoning Block Support"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: "auto-math Workspace \u2014 Reasoning Block Support"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.665893
updated_at: 1784946220.665893
---

- **ID**: P5-MATH-001
- **Status**: ✅ RESOLVED (V8 model refresh — 2026-06-10)
- **History**: Original limitation was `Qwen2.5-Math-7B-Instruct` (MLX, no `reasoning_content` blocks). Model replaced in V8 by `phi4-mini-reasoning` (RL-trained, Phi-4-Mini-Reasoning, ~2.5GB). The new model has `emits_reasoning: True` — math reasoning appears in the collapsible thinking panel.
- **Alternative**: For even heavier reasoning, `auto-reasoning` (DeepSeek-R1-0528-Qwen3-8B) also separates reasoning content.
