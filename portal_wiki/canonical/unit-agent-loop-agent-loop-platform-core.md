---
id: unit-agent-loop-agent-loop-platform-core
kind: what
title: "AGENT_LOOP \u2014 Agent Loop (platform core)"
sources:
- type: doc
  path: docs/AGENT_LOOP.md
  commit: 05e42ec2
  section: Agent Loop (platform core)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.4984078
updated_at: 1784946220.4984078
---

`portal/platform/agent/` is the discipline-agnostic agent loop: a bounded,
grounded, writeback-capable engine that any module drives with its own action
space. It is **platform core** — always present, never a toggleable module.
