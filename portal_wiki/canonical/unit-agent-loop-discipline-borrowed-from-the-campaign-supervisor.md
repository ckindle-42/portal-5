---
id: unit-agent-loop-discipline-borrowed-from-the-campaign-supervisor
kind: what
title: "AGENT_LOOP \u2014 Discipline (borrowed from the Campaign Supervisor)"
sources:
- type: code
  path: portal/platform/agent/loop.py
- type: code
  path: portal/platform/agent/decide.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5058901
updated_at: 1784946220.5058901
---

`run_loop` enforces the Campaign-Supervisor discipline:

- Caps: `max_iterations` and `max_wall_clock_sec` from `goal.budget` bound the
  loop; exceeding either ends with `budget_exhausted`.
- A confidence floor: `run_loop(confidence_floor=...)` — any decision below the
  floor ends with `flagged_for_human` rather than guessing.
- A clean `blocked` stop: when `decide.py` finds no applicable capability the
  loop stops immediately — nothing grounded to try is a stop, not a flail.
- Honest outcomes, never faked-green: `LoopResult.outcome` is one of
  `completed` / `blocked` / `budget_exhausted` / `flagged_for_human` /
  `invalid_goal`, and an invalid goal short-circuits before any iteration.

## Why

The discipline matters because the loop's whole value is that a module can
point it at a goal and trust the verdict. If low-confidence guesses ran anyway,
or an ungrounded decide turn invented actions, "completed" would be meaningless
for an engagement or a code change. Budgets and the confidence floor are the
backstops that keep bounded execution honest, and the explicit invalid-goal
exit surfaces a bad spec instead of burning its budget on nothing.
