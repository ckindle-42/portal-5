---
id: unit-agent-loop-shape
kind: what
title: "AGENT_LOOP \u2014 Shape"
sources:
- type: code
  path: portal/platform/agent/loop.py
- type: code
  path: portal/platform/agent/decide.py
- type: code
  path: portal/platform/agent/goal.py
- type: code
  path: portal/platform/agent/writeback.py
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5049548
updated_at: 1784946220.5049548
---

The loop's shape is a single bounded engine over a module's contracts:

```
goal --> [validate_goal bounds] --> loop:
           decide (grounded via provider.query)  ->  execute (module Executor)
             ^                                         ->  fold observation_delta
             +----------- iterate until stop_when / budget -----------+
         record (optional, via record_outcome)  ->  portal_wiki/proposed/
             (CI gate: confirm_unit / reject_unit)
```

`run_loop` validates the goal first (`invalid_goal` short-circuits), then
cycles decide → execute → fold until `stop_when` is satisfied, a budget is
exhausted, or the loop blocks or flags for a human. `record_outcome` is
optional and runs outside the iteration body, so writing never affects the
loop's trajectory.

## Why

The shape is a pipeline with the fold-back arrow exactly where it is because
the loop is event-driven: each executor result becomes the next decide-turn's
observations, and stop/budget conditions are checked after each fold. Keeping
record outside the body means a wiki write can never change what the loop does
next — learning is a side channel, not control flow.
