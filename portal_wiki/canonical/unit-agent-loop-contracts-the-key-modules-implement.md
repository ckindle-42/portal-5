---
id: unit-agent-loop-contracts-the-key-modules-implement
kind: what
title: "AGENT_LOOP \u2014 Contracts (the \"key\" modules implement)"
sources:
- type: code
  path: portal/platform/agent/interfaces.py
- type: code
  path: portal/platform/agent/decide.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.505333
updated_at: 1784946220.505333
---

The `interfaces.py` protocols are the contracts every module implements to
unlock the loop:

- `CapabilityProvider.query(observations, *, domain, goal, limit)` grounds the
  decide-turn: `decide.py` calls it to retrieve real candidates, narrowed by
  goal intent first, and the loop chooses only from what it returns — never
  free-form. An empty result stops the loop with `blocked`.
- `Executor.execute(decision, state)` performs one action and returns
  `{"observation_delta", "oracle_result", "raw"}`. Errors ride in the return,
  not exceptions, so the loop can score a failed step instead of crashing.
- `Capability` is structural (`.id`, `.tools`) — modules keep their own rich
  type and still satisfy the engine.

## Why

The contracts are deliberately small and duck-typed so no module pays a
coupling cost to join the loop. Security's `Capability` already carries
`oracle` and `phase`; the protocol only requires `id` and `tools`, letting the
engine reason over candidates without knowing security internals. Returning
errors in-band keeps a failed action a scored observation rather than a crash,
which is what lets the loop report honest outcomes instead of dying mid-run.
