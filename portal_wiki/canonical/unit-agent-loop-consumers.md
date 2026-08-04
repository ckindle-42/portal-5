---
id: unit-agent-loop-consumers
kind: what
title: "AGENT_LOOP \u2014 Consumers"
sources:
- type: code
  path: portal/modules/security/core/goal.py
- type: code
  path: portal/modules/security/core/decision_engine.py
- type: code
  path: portal/modules/security/core/goal_decide.py
- type: code
  path: portal/modules/security/core/objective_executor.py
- type: code
  path: portal/modules/security/core/objective_entry.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5072598
updated_at: 1784946220.5072598
---

Security is the only live consumer: `security.core.goal` / `decision_engine`
/ `goal_decide` re-home onto this core while keeping their public symbols —
`EngagementGoal` subclasses the platform `Goal`, `decision_engine` re-exports
the `rank` functions, and `goal_decide` delegates its decide-turn to
`portal.platform.agent.decide`.

Security also supplies the two concrete contract implementations: the
`_SecurityCapabilityProvider` adapter (wraps `capability.query`) and
`SecurityExecutor`, which implements the platform `Executor` over
`lab.lab_dispatch` + `oracles.verify_finding`. `objective_entry.py` wires the
platform `run_loop` live against the lab behind `PORTAL_EMERGENT`.

No other module implements the contracts yet. Generalizing beyond security is
named follow-on work: re-homing security's orchestration onto `run_loop` and
standing up the `portal-agent` MCP server plus OWUI entry remain open slices
of the `portal/platform/agent/` surface.

## Why

Security was the proving ground because it already owned the pieces a loop
needs — a capability index, a decision engine, and a lab — so re-homing it
first validated the platform contracts without any module-coupling risk. The
security shims stay byte-compatible so the existing suite and CLI never notice
the engine moved. Other modules are deliberately not claimed as consumers
until they actually implement the contracts; a roadmap is not an implementation.
