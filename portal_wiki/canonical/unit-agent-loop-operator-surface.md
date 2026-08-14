---
id: unit-agent-loop-operator-surface
kind: what
title: "AGENT_LOOP \u2014 Operator surface"
sources:
- type: code
  path: portal/platform/inference/cli/agent.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.506887
updated_at: 1784946220.506887
---

The `portal agent` CLI (`portal/platform/inference/cli/agent.py`) is the
operator surface for the loop:

- `portal agent explain <goal.yaml>` — one dry decide-turn: loads the goal
  spec, validates it, and reports a missing module `provider` rather than
  faking a decide-turn.
- `portal agent proposed [--status ...]` — lists pending loop writebacks via
  `wiki.writeback.list_proposed`; this is the CI-gate view over `proposed` /
  `confirmed` / `rejected`.

There is intentionally no `run` command that fakes an engagement: a full loop
needs a module-supplied `provider` and `executor`, so `explain` is the honest
dry-run surface until slice-2 wiring lands.

## Why

The operator surface exists so a human can inspect what the loop would do
without letting it act. `explain` proves a goal spec is valid and shows the
grounding requirement, while `proposed` exposes the confirm/reject gate — the
only way a loop's learning reaches the canonical wiki. Both commands are
read-only, keeping operator power bounded until a module actually wires a live
executor.
