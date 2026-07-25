---
id: unit-agent-loop-consumers
kind: what
title: "AGENT_LOOP \u2014 Consumers"
sources:
- type: doc
  path: docs/AGENT_LOOP.md
  commit: 05e42ec2
  section: Consumers
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5072598
updated_at: 1784946220.5072598
---

Security is the first consumer: `security.core.goal` / `decision_engine` /
`goal_decide` re-home onto this core while keeping their public symbols. Other
modules (compliance, research, coding) implement `CapabilityProvider` +
`Executor` to unlock the loop. Full-loop runtime wiring + MCP/OWUI entry are
slices 2-3 (see `coding_task/TASK_AGENT_LOOP_PLATFORM_V1.md`).
