---
id: unit-agent-loop-contracts-the-key-modules-implement
kind: what
title: "AGENT_LOOP \u2014 Contracts (the \"key\" modules implement)"
sources:
- type: doc
  path: docs/AGENT_LOOP.md
  commit: 05e42ec2
  section: Contracts (the "key" modules implement)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.505333
updated_at: 1784946220.505333
---

- `CapabilityProvider.query(observations, *, domain, goal, limit)` — grounds the
  decide-turn. The loop chooses only from returned candidates; never free-form.
- `Executor.execute(decision, state) -> {observation_delta, oracle_result, raw}`
  — performs one action, returns what changed. Errors ride in the return.
- `Capability` is structural (`.id`, `.tools`) — modules keep their own type.
