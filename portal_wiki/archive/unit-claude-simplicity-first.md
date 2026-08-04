---
id: unit-claude-simplicity-first
kind: why
title: "CLAUDE.md \u2014 Simplicity First"
sources:
- type: design
  path: CLAUDE.md
  section: Simplicity First
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.194311
updated_at: 1785348301.194311
---


**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked. No abstractions for single-use code. No unrequested "flexibility" or "configurability". No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
- This is architectural here, not just stylistic: scope creep collides with "What Portal 5 Is NOT" at the feature level and with the lean-container rules (Rules 8–9) at the dependency level.
